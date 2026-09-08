import hashlib
import json

from scripts.report_continuous_multi_queue import publish


def test_report_validates_prefix_and_preserves_missing_fields(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    scoreboard = {
        "RUN_ID": "m013-fixture",
        "MODEL_ID": "M013",
        "MODEL_HASH": "abc",
        "CAPITAL_MODE": "COMPOUNDING",
        "RUN_STATUS": "RUNNING",
        "SIMULATION_TIMESTAMP": "2026-01-02T00:00:00+00:00",
        "CHECKPOINT_REASON": "DAY_1",
        "TOTAL_EQUITY": 110,
        "OPERATING_CAPITAL": 100,
        "VERDICT": "PENDING",
    }
    rows = (json.dumps(scoreboard) + "\n").encode()
    (run / "capital-curve.jsonl").write_bytes(rows + b'{"incomplete":')
    binding = {"bytes": len(rows), "sha256": hashlib.sha256(rows).hexdigest()}
    physical = json.dumps({"capital_curve": binding}).encode()
    (run / "checkpoint.json").write_bytes(physical)
    scoreboard.update(
        CAPITAL_CURVE_PREFIX=binding, CHECKPOINT_SHA256=hashlib.sha256(physical).hexdigest()
    )
    (run / "scoreboard.json").write_text(json.dumps(scoreboard), encoding="utf-8")
    result = publish(run, tmp_path / "reports", tmp_path / "state" / "CURRENT_STATE.md")
    assert result["VERDICT"] == "PENDING"
    assert result["CHECKPOINTS"]["DAY_1"]["TOTAL_EQUITY"] == 110
    assert result["CHECKPOINTS"]["DAY_7"]["TOTAL_EQUITY"] is None
    assert len(list((tmp_path / "reports").glob("M013-*.svg"))) == 7
    assert result["OPERATING_CAPITAL"] == 100
    state = tmp_path / "state" / "CURRENT_STATE.md"
    assert "OPERATING_CAPITAL=100" in state.read_text(encoding="utf-8")
    journal = state.parent / "M013_JOURNAL.md"
    before = journal.read_bytes()
    publish(run, tmp_path / "reports", state)
    assert journal.read_bytes() == before
    scoreboard["TOTAL_EQUITY"] = 9000
    (run / "scoreboard.json").write_text(json.dumps(scoreboard), encoding="utf-8")
    import pytest

    with pytest.raises(ValueError, match="SCOREBOARD_DIFFERS"):
        publish(run, tmp_path / "reports", state)


def test_hash_mismatch_fails_closed(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "capital-curve.jsonl").write_bytes(b"{}\n")
    scoreboard = {
        "MODEL_ID": "M013",
        "CAPITAL_MODE": "COMPOUNDING",
        "CAPITAL_CURVE_PREFIX": {"bytes": 3, "sha256": "0" * 64},
    }
    (run / "scoreboard.json").write_text(json.dumps(scoreboard), encoding="utf-8")
    try:
        publish(run, tmp_path / "reports", tmp_path / "state.md")
    except ValueError as exc:
        assert str(exc) == "CAPITAL_CURVE_PREFIX_HASH_MISMATCH"
    else:
        raise AssertionError("expected hash validation failure")
