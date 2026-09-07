import gzip
import hashlib
import importlib.util
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.recovery_reserve import grid_configs
from crypto_strategy_lab.microstructure.serial_replay import SerialReplayResult

_SPEC = importlib.util.spec_from_file_location(
    "autopsy_recovery_reserve_cli",
    Path(__file__).parents[1] / "scripts" / "autopsy_recovery_reserve.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
build_autopsy = _MODULE.build_autopsy


def _result() -> SerialReplayResult:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return SerialReplayResult(
        model_id="RECOVERY_RESERVE_PHASE_A",
        model_hash="m",
        scenario_id="s",
        scenario_hash="s",
        start=now,
        end_exclusive=datetime(2026, 1, 2, tzinfo=UTC),
        initial_quote=Decimal(100),
        final_cash=Decimal(100),
        final_inventory=Decimal(0),
        last_price=Decimal(1),
        final_marked_equity=Decimal(100),
        return_fraction=Decimal(0),
        realized_profit=Decimal(0),
        unrealized_profit=Decimal(0),
        total_fees=Decimal(0),
        completed_cycles=0,
        daily_cycles={},
        zero_cycle_days=1,
        reselection_count=0,
        blocked_reselection_checks=0,
        cooldown_violations=0,
        reversal_24h_count=0,
        active_low=None,
        active_high=None,
        open_entry_event=None,
        open_entry_timestamp=None,
        open_entry_price=None,
        open_buy_fee_quote=None,
        open_holding_seconds=None,
        open_cycle_censored=False,
        execution_class="PRICE_PATH",
        selection_changes=(),
        cycles=(),
        release_closures=(),
        release_evaluations=(),
    )


def _fixture(tmp_path: Path, *, tamper: bool = False) -> Path:
    root = tmp_path / "root"
    configs = grid_configs()
    identity = {
        "git_commit_sha": "a" * 40,
        "schema": "test",
        "grid": [config.payload() for config in configs],
    }
    (root).mkdir()
    (root / "identity.json").write_text(json.dumps(identity), encoding="utf-8")
    result = _result()
    rows = []
    for config in configs:
        path = root / config.scenario_id
        path.mkdir()
        replay = path / "replay.json.gz"
        with gzip.open(replay, "wt", encoding="utf-8") as stream:
            json.dump(json.loads(result.model_dump_json()), stream)
        audit = path / "audit.json"
        audit.write_text(json.dumps({"releases": [], "replenishments": []}), encoding="utf-8")
        runtime = path / "runtime.json"
        runtime.write_text("{}", encoding="utf-8")
        row = {"scenario_id": config.scenario_id}
        payload = {
            "identity": {**identity, "reserve_config": config.payload()},
            "replay_sha256": hashlib.sha256(replay.read_bytes()).hexdigest(),
            "summary": row,
            "artifact_hashes": {
                name: hashlib.sha256((path / name).read_bytes()).hexdigest()
                for name in ("audit.json", "runtime.json")
            },
        }
        completion = {**payload, "payload_sha256": canonical_hash(payload)}
        (path / "completed.json").write_text(json.dumps(completion), encoding="utf-8")
        rows.append(row)
    if tamper:
        rows[0]["tampered"] = True
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"artifact_root": str(root), "identity": identity, "scenarios": rows}),
        encoding="utf-8",
    )
    return report


def test_incomplete_report_fails_closed(tmp_path: Path):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"scenarios": [], "identity": {}, "artifact_root": "x"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="COMPLETE_GRID"):
        build_autopsy(report)


def test_completion_hash_failure_is_closed(tmp_path: Path):
    report = _fixture(tmp_path)
    completion = next((tmp_path / "root").glob("*/completed.json"))
    value = json.loads(completion.read_text(encoding="utf-8"))
    value["payload_sha256"] = "0" * 64
    completion.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="COMPLETION_HASH"):
        build_autopsy(report)


def test_valid_fixture_produces_lightweight_rows_without_aggregate(tmp_path: Path):
    output = build_autopsy(_fixture(tmp_path))
    assert output["classification"] == "RETROSPECTIVE_DIAGNOSTIC_ONLY"
    assert len(output["scenarios"]) == 18
    assert output["NO_AGGREGATE_SUM"] is True
