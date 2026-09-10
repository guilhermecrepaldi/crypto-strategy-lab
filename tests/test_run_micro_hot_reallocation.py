from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts import run_micro_hot_reallocation as runner
from scripts.register_micro_hot_reallocation import validate_registration_design
from scripts.run_micro_hot_reallocation import compare


def metrics(cycles: int, slots: int, initial: str = "156") -> dict:
    return {
        "PHYSICAL_CYCLES": cycles,
        "PHYSICAL_CYCLES_PER_HOUR": str(cycles / 3),
        "SLOT_EQUIVALENT_CYCLES": slots,
        "SLOT_EQUIVALENT_CYCLES_PER_HOUR": str(slots / 3),
        "INITIAL_TOTAL": initial,
        "MICRO_HOT_PHYSICAL_CYCLES": 6,
        "MICRO_C1_CYCLES": 3,
        "MICRO_C2_CYCLES": 3,
        "HOT_RANK1_CYCLES": 7,
        "FAR14_CYCLES": 0,
        "FAR15_CYCLES": 0,
        "AUDIT": "PASS_TEST",
    }


def test_compare_applies_favorable_and_strong_gates_without_hiding_result() -> None:
    control, treatment = {"METRICS": metrics(10, 30)}, {"METRICS": metrics(13, 28, "156.001")}
    result = compare(control, treatment, {"VALIDATED_TICK_SIZE": "0.00001"})
    assert result["PHYSICAL_DELTA"] == 3
    assert result["MICRO_HOT_MECHANICS_FAVORABLE"] is True
    assert result["MICRO_HOT_STRONG_FREQUENCY_GATE_PASS"] is True
    assert result["NET_NEAR_HOT_CYCLE_GAIN"] == 6


def test_compare_rejects_unmatched_capital() -> None:
    with pytest.raises(ValueError, match="CAPITAL_MATCH"):
        compare({"METRICS": metrics(10, 30)}, {"METRICS": metrics(11, 31, "160")}, {})


def test_registration_rejects_a_third_scenario() -> None:
    import json
    from pathlib import Path

    design = json.loads(Path("docs/microstructure/M027_MODEL_SPEC.json").read_text())
    validate_registration_design(design)
    changed = deepcopy(design)
    changed["scenarios"].append("SWEEP")
    with pytest.raises(ValueError, match="M027_OWNER_POLICY"):
        validate_registration_design(changed)


def test_tick_gate_rejects_fine_trade_when_l2_is_coarse(monkeypatch) -> None:
    lines = [
        't {"data":{"e":"depthUpdate","b":[["1.00010000","1"],["1.00020000","1"]],"a":[]}}',
        't {"data":{"e":"trade","p":"1.00001000"}}',
    ]
    monkeypatch.setattr(runner, "raw_lines", lambda *_args: iter(lines))
    with pytest.raises(ValueError, match="BLOCKED_FINE_TICK"):
        runner.validate_fine_tick((), {1: SimpleNamespace()})


def test_strong_gate_is_false_and_delta_undefined_when_control_zero() -> None:
    result = compare({"METRICS": metrics(0, 0)}, {"METRICS": metrics(0, 0)}, {})
    assert result["MICRO_HOT_STRONG_FREQUENCY_GATE_PASS"] is False
    assert result["PHYSICAL_DELTA_PCT"] == "UNDEFINED_CONTROL_ZERO"
