import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from crypto_strategy_lab.ml.model_registry import (
    BackendSpec,
    Hypothesis,
    InvalidStatusTransition,
    ModelLineage,
    ModelRegistry,
    ModelSpec,
    ModelStatus,
    RunSpec,
    run_artifact_dir,
)

AT = datetime(2026, 1, 1, tzinfo=UTC)
ERROR = "conversion from numpy.int64 to Decimal is not supported"


def _setup(tmp_path: Path) -> tuple[ModelRegistry, str, RunSpec]:
    registry = ModelRegistry(tmp_path / "artifacts", tmp_path / "reports")
    ancestors: tuple[str, ...] = ()
    for number in range(1, 11):
        model_id = f"M{number:03}"
        registry.register(
            ModelSpec(
                model_id=model_id,
                model={"capital_release_protocol": "OWNER_EXPLORATORY_OVERRIDE_FROZEN_V1"}
                if model_id == "M010"
                else {"model": model_id},
                hypothesis=Hypothesis(
                    observation="o",
                    hypothesis="h",
                    change="c",
                    expected_effect="e",
                    reason_for_new_model="r",
                ),
                lineage=ModelLineage(
                    parent_model_id=f"M{number - 1:03}" if number > 1 else None,
                    ancestor_chain=ancestors,
                    change_category="x",
                    change_summary="x",
                    authorization_class="OWNER_EXPLORATORY_OVERRIDE",
                ),
                status=ModelStatus.CREATED,
                registered_at=AT,
            )
        )
        ancestors = (*ancestors, model_id)
    scenario = registry.append_scenario("M010", {"scenario": {"frozen": True}}, occurred_at=AT)
    run = RunSpec(
        scenario_hash=scenario["payload"]["SCENARIO_HASH"],
        dataset_hash="dataset",
        campaign_snapshot_id="snapshot",
        interval={"start": "2026-01-01", "end": "2026-01-02"},
        code_commit="old-sha",
        technical_revision="revision",
        backend=BackendSpec(backend="CPU"),
        run={"frozen": True},
    )
    event = registry.append_run("M010", run, occurred_at=AT)
    registry.transition("M010", ModelStatus.RUNNING, reason="execute", occurred_at=AT)
    registry.transition("M010", ModelStatus.INVALIDATED_TECHNICAL, reason="bug", occurred_at=AT)
    failure = (
        run_artifact_dir("M010", event["payload"]["RUN_HASH"], registry.artifact_root)
        / "technical-failure.json"
    )
    failure.write_text(
        '{"classification":"INVALIDATED_TECHNICAL","error_type":"TypeError",'
        f'"error":"{ERROR}","run_hash":"{event["payload"]["RUN_HASH"]}"}}',
        encoding="utf-8",
    )
    return registry, event["payload"]["RUN_HASH"], run


def test_m010_retry_requires_new_code_and_reopens_only_m010(tmp_path: Path) -> None:
    registry, failed_hash, old = _setup(tmp_path)
    event = registry.retry_m010_technical_failure(
        failed_hash,
        old.model_copy(update={"code_commit": "new-sha"}),
        "normalize runtime integers",
        occurred_at=AT,
    )
    assert event["payload"]["RUN_HASH"] != failed_hash
    assert registry.current_status("M010") == ModelStatus.RUNNING
    assert registry.entries()[-1].model_id == "M010"
    assert registry.journal()[-1]["payload"]["retry_run_hash"] == event["payload"]["RUN_HASH"]


def test_m010_retry_rejects_same_code_changed_identity_or_evaluation(tmp_path: Path) -> None:
    registry, failed_hash, old = _setup(tmp_path)
    with pytest.raises(ValueError, match="different code"):
        registry.retry_m010_technical_failure(failed_hash, old, "retry", occurred_at=AT)
    changed = old.model_copy(update={"code_commit": "new", "dataset_hash": "other"})
    with pytest.raises(ValueError, match="dataset_hash"):
        registry.retry_m010_technical_failure(failed_hash, changed, "retry", occurred_at=AT)
    evaluation_dir = run_artifact_dir("M010", failed_hash, registry.artifact_root) / "evaluations"
    evaluation_dir.mkdir()
    (evaluation_dir / "replay.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="evaluation"):
        registry.retry_m010_technical_failure(
            failed_hash, old.model_copy(update={"code_commit": "newer"}), "retry", occurred_at=AT
        )


def test_generic_transition_does_not_allow_invalidated_to_running(tmp_path: Path) -> None:
    registry, _, _ = _setup(tmp_path)
    with pytest.raises(InvalidStatusTransition):
        registry.transition("M010", ModelStatus.RUNNING, reason="generic", occurred_at=AT)


def test_retry_accepts_only_diagnosed_legacy_event_projection_failure(tmp_path: Path) -> None:
    registry, failed_hash, old = _setup(tmp_path)
    failure = (
        run_artifact_dir("M010", failed_hash, registry.artifact_root) / "technical-failure.json"
    )
    payload = json.loads(failure.read_text())
    payload.update(error_type="ValueError", error="ZERO_RELEASE_BEHAVIORAL_DIVERGENCE: final_cash")
    failure.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="diagnosed failure"):
        registry.retry_m010_technical_failure(
            failed_hash, old.model_copy(update={"code_commit": "new"}), "audit event projection"
        )
    payload["error"] = "ZERO_RELEASE_BEHAVIORAL_DIVERGENCE: cycles,selection_changes"
    failure.write_text(json.dumps(payload))
    registry.retry_m010_technical_failure(
        failed_hash, old.model_copy(update={"code_commit": "new"}), "audit event projection"
    )
    assert registry.current_status("M010") == ModelStatus.RUNNING


@pytest.mark.parametrize("tamper", [None, "hash", "evaluation", "analysis_sha"])
def test_completed_report_recovery_is_evidence_bound(tmp_path: Path, tamper: str | None) -> None:
    registry, run_hash, run = _setup(tmp_path)
    root = run_artifact_dir("M010", run_hash, registry.artifact_root)
    raw = {"model_id": "M010", "initial_quote": "100", "completed_cycles": 3}
    payload = {
        "status": "COMPUTATION_COMPLETE_PENDING_VALIDATION",
        "result": raw,
        "result_sha256": hashlib.sha256(
            json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "provenance": {
            "model_id": "M010",
            "run_hash": run_hash,
            "code_commit": "old-sha",
            "scenario_hash": run.scenario_hash,
            "dataset_hash": run.dataset_hash,
            "campaign_snapshot_id": run.campaign_snapshot_id,
        },
    }
    (root / "completed-replay.json").write_text(json.dumps(payload))
    failure = {
        "classification": "INVALIDATED_TECHNICAL",
        "run_hash": run_hash,
        "error_type": "ValidationError",
        "error": "model_id parent_model_id Field required",
    }
    (root / "technical-failure.json").write_text(json.dumps(failure))
    event = registry.append_evaluation(
        "M010",
        {
            "run_hash": run_hash,
            "scenario_hash": run.scenario_hash,
            "campaign_snapshot_id": run.campaign_snapshot_id,
            "comparison": {},
            "criteria": {},
            "replay": raw,
            "metrics": {
                "capital_release": {
                    "code_commit": "old-sha",
                    "analysis_code_commit": "new-sha",
                    "equivalence": {
                        "M010_BEHAVIORALLY_EQUIVALENT_TO_M007": "YES",
                        "legacy_m007_event_id_audit": {"all_other_fields_exactly_equal": True},
                    },
                }
            },
        },
    )
    if tamper == "hash":
        payload["result_sha256"] = "invalid"
        (root / "completed-replay.json").write_text(json.dumps(payload))
    if tamper == "evaluation":
        (Path(event["payload"]["artifact_directory"]) / "replay.json").write_text("{}")
    if tamper is not None:
        with pytest.raises(ValueError):
            registry.complete_m010_report_recovery(
                run_hash,
                event["payload"]["EVALUATION_HASH"],
                "old-sha" if tamper == "analysis_sha" else "new-sha",
            )
        assert registry.current_status("M010") == ModelStatus.INVALIDATED_TECHNICAL
        return
    registry.complete_m010_report_recovery(run_hash, event["payload"]["EVALUATION_HASH"], "new-sha")
    assert registry.current_status("M010") == ModelStatus.EVALUATED
    assert json.loads((root / "technical-failure.json").read_text()) == failure
    assert registry.journal()[-2]["event_type"] == "POSTPROCESSING_RECOVERY_COMPLETED"
    with pytest.raises(InvalidStatusTransition):
        registry.complete_m010_report_recovery(
            run_hash, event["payload"]["EVALUATION_HASH"], "new-sha"
        )
