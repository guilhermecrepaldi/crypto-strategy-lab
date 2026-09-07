import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from crypto_strategy_lab.microstructure import replay_workflow as workflow
from crypto_strategy_lab.microstructure.serial_replay import (
    SERIAL_TAPE_QUANTUM,
    USDCUSDT_TICK_CATALOG,
    SerialModelConfig,
    SerialScenarioConfig,
    SerialTape,
    preregistered_corrected_block,
    replay_serial_model,
)


def test_recovery_keeps_simulation_identity_and_never_replays_m010(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(minutes=2)
    parent = preregistered_corrected_block()[2]
    model = SerialModelConfig.model_validate(
        {
            **parent.model_dump(),
            "model_id": "M010",
            "parent_model_id": "M007",
            "capital_release_protocol": "OWNER_EXPLORATORY_OVERRIDE_FROZEN_V1",
        }
    )
    scenario = SerialScenarioConfig(
        tick_size=SERIAL_TAPE_QUANTUM,
        historical_tick_catalog_hash=USDCUSDT_TICK_CATALOG.catalog_hash,
        historical_tick_source_url=USDCUSDT_TICK_CATALOG.source_url,
        historical_tick_policy="CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
    )
    tape = SerialTape.from_events(
        [
            (start - timedelta(minutes=1), Decimal("1")),
            (start, Decimal("1.0001")),
            (end, Decimal("1")),
        ],
        tick_size=SERIAL_TAPE_QUANTUM,
    )
    result = replay_serial_model(
        tape,
        model,
        scenario,
        start=start,
        end_exclusive=end,
        tick_catalog=USDCUSDT_TICK_CATALOG,
        release_support_tape=tape,
    )
    provenance = dict(
        model_id="M010",
        run_hash="original-run",
        code_commit="simulation-sha",
        scenario_hash=scenario.scenario_hash,
        dataset_hash="dataset",
        campaign_snapshot_id="snapshot",
    )
    raw_path = workflow._persist_completed_replay(
        result, run_root=tmp_path / "run", provenance=provenance
    )
    (raw_path.parent / "technical-failure.json").write_text(
        json.dumps(
            {
                "error_type": "ValidationError",
                "error": "model_id parent_model_id Field required",
            }
        )
    )
    (tmp_path / "reports" / "usdcusdt").mkdir(parents=True)
    recovered = []
    registry = SimpleNamespace(
        artifact_root=tmp_path,
        report_root=tmp_path / "reports",
        get=lambda model_id: SimpleNamespace(
            model_id="M007",
            model=parent.model_dump(exclude={"model_id", "parent_model_id"}),
            lineage=SimpleNamespace(parent_model_id=parent.parent_model_id),
        ),
        journal=lambda: [
            {
                "event_type": "EVALUATION_RECORDED",
                "payload": {
                    "model_id": "M010",
                    "EVALUATION_HASH": "new-evaluation",
                },
            }
        ],
        complete_m010_report_recovery=lambda *args: recovered.append(args),
    )
    assert workflow._registered_parent_config(registry) == parent
    monkeypatch.setattr(workflow, "_git_head", lambda: "analysis-sha")
    monkeypatch.setattr(
        workflow.subprocess,
        "check_output",
        lambda args, **kw: "analysis-sha refs/heads/main" if "ls-remote" in args else "",
    )
    monkeypatch.setattr(
        workflow, "replay_serial_model", lambda *a, **kw: pytest.fail("saved M010 must not replay")
    )
    monkeypatch.setattr(workflow, "analyze_replay_temporally", lambda *a: "analysis")
    monkeypatch.setattr(workflow, "_capital_release_report", lambda *a, **kw: {})
    monkeypatch.setattr(workflow, "_record_evaluation", lambda *a, **kw: None)
    record, _ = workflow._recover_m010_postprocessing(
        registry,
        model,
        scenario,
        tape,
        SimpleNamespace(dataset_hash="dataset"),
        "snapshot",
        end,
        None,
        None,
        {"RUN_HASH": "original-run", "code_commit": "simulation-sha"},
        raw_path,
    )
    assert record["run_hash"] == "original-run"
    assert recovered == [("original-run", "new-evaluation", "analysis-sha")]
    report = json.loads((tmp_path / "reports/usdcusdt/M010-capital-release.json").read_text())
    assert report["code_commit"] == "simulation-sha"
    assert report["analysis_code_commit"] == "analysis-sha"
    assert report["computation_reused_without_replay"] is True
