from decimal import Decimal as D

import pytest

import scripts.audit_m026_24h_extension as audit_module
from scripts.audit_m026_24h_extension import (
    independent_m026_24h_audit,
    normalize_full_day_metrics,
)


def base_metrics() -> dict:
    return {
        "INITIAL_TOTAL_MARKED": "156.25220000",
        "FINAL_TOTAL_MARKED": "157.81472200",
        "PHYSICAL_CYCLES": 240,
        "SLOT_EQUIVALENT_CYCLES": 720,
        "PHYSICAL_GATE_GT_12_3333_PASS": True,
        "PHYSICAL_GATE_EXACT_RULE": "PHYSICAL_CYCLES >= 38 IN 3H",
        "SLOT_GATE_20_PER_HOUR_PASS": True,
    }


def test_full_day_reporting_uses_24_hours_and_marked_return() -> None:
    value = normalize_full_day_metrics(base_metrics())
    assert value["MODEL"] == "M028"
    assert value["PERIOD"] == "24H"
    assert D(value["PHYSICAL_CYCLES_PER_HOUR"]) == D(10)
    assert D(value["SLOT_EQUIVALENT_CYCLES_PER_HOUR"]) == D(30)
    assert D(value["TOTAL_MARKED_GAIN"]) == D("1.562522")
    assert D(value["TOTAL_MARKED_GAIN_PCT"]) == D(1)
    assert "PHYSICAL_GATE_GT_12_3333_PASS" not in value
    assert value["AUXILIARY_PHYSICAL_RULER_304_PASS"] is False
    assert value["AUXILIARY_SLOT_RULER_480_PASS"] is True


def test_full_day_reporting_rejects_changed_initial_bank() -> None:
    metrics = base_metrics()
    metrics["INITIAL_TOTAL_MARKED"] = "100"
    with pytest.raises(ValueError, match="M028_INITIAL_CAPITAL_DIVERGED_FROM_M026"):
        normalize_full_day_metrics(metrics)


def test_result_audit_reconciles_rates_return_and_prefix(monkeypatch) -> None:
    monkeypatch.setattr(
        audit_module,
        "independent_dynamic_hotline_audit",
        lambda *_: {"status": "PASS_PARENT", "physical_cycles_reconciled": 240},
    )
    metrics = normalize_full_day_metrics(base_metrics())
    terminal = {
        "state": {
            "parent": {
                "config": {
                    "start_us": audit_module.START_US,
                    "end_us": audit_module.END_US,
                }
            }
        }
    }
    result = independent_m026_24h_audit(
        [],
        terminal,
        metrics,
        {},
        {
            "STATUS": "PASS_EXACT_M026_3H_PREFIX_EQUIVALENCE",
            "LEDGER_EXACT_MATCH": True,
            "ECONOMIC_STATE_MATCH": True,
        },
    )
    assert result["prefix_equivalence"] is True
    assert result["marked_gain_reconciled"] is True
    assert result["status"].startswith("PASS_M028")


def test_result_audit_rejects_missing_prefix(monkeypatch) -> None:
    monkeypatch.setattr(
        audit_module,
        "independent_dynamic_hotline_audit",
        lambda *_: {"status": "PASS_PARENT"},
    )
    with pytest.raises(ValueError, match="M028_AUDIT_PREFIX"):
        independent_m026_24h_audit(
            [],
            {
                "state": {
                    "parent": {
                        "config": {
                            "start_us": audit_module.START_US,
                            "end_us": audit_module.END_US,
                        }
                    }
                }
            },
            normalize_full_day_metrics(base_metrics()),
            {},
            {},
        )


@pytest.mark.parametrize(
    ("field", "replacement", "reason"),
    (
        ("INITIAL_MARKED_EQUITY_BEFORE", "999", "INITIAL_ALIAS"),
        ("FINAL_MARKED_EQUITY_AFTER", "999", "FINAL_ALIAS"),
        ("M026_3H_MARKED_EQUITY", "999", "M026_3H_REFERENCE"),
        ("POST_3H_MARKED_GAIN", "999", "POST_3H_GAIN"),
        ("POST_3H_MARKED_GAIN_PCT", "999", "POST_3H_GAIN_PCT"),
        ("AUXILIARY_PHYSICAL_RULER_304_PASS", True, "PHYSICAL_RULER"),
        ("AUXILIARY_SLOT_RULER_480_PASS", False, "SLOT_RULER"),
    ),
)
def test_result_audit_rejects_derived_metric_tampering(
    monkeypatch, field: str, replacement, reason: str
) -> None:
    monkeypatch.setattr(
        audit_module,
        "independent_dynamic_hotline_audit",
        lambda *_: {"status": "PASS_PARENT"},
    )
    metrics = normalize_full_day_metrics(base_metrics())
    metrics[field] = replacement
    terminal = {
        "state": {
            "parent": {
                "config": {
                    "start_us": audit_module.START_US,
                    "end_us": audit_module.END_US,
                }
            }
        }
    }
    with pytest.raises(ValueError, match=f"M028_AUDIT_{reason}"):
        independent_m026_24h_audit(
            [],
            terminal,
            metrics,
            {},
            {
                "STATUS": "PASS_EXACT_M026_3H_PREFIX_EQUIVALENCE",
                "LEDGER_EXACT_MATCH": True,
                "ECONOMIC_STATE_MATCH": True,
            },
        )


def test_result_audit_rejects_non_24h_terminal(monkeypatch) -> None:
    monkeypatch.setattr(
        audit_module,
        "independent_dynamic_hotline_audit",
        lambda *_: {"status": "PASS_PARENT"},
    )
    terminal = {
        "state": {"parent": {"config": {"start_us": audit_module.START_US, "end_us": 3}}}
    }
    with pytest.raises(ValueError, match="M028_AUDIT_TERMINAL_END"):
        independent_m026_24h_audit(
            [],
            terminal,
            normalize_full_day_metrics(base_metrics()),
            {},
            {
                "STATUS": "PASS_EXACT_M026_3H_PREFIX_EQUIVALENCE",
                "LEDGER_EXACT_MATCH": True,
                "ECONOMIC_STATE_MATCH": True,
            },
        )
