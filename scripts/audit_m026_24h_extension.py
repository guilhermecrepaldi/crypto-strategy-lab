"""Independent result-layer audit for the unchanged M026 kernel over 24 hours."""

from __future__ import annotations

from decimal import Decimal as D
from typing import Any

from scripts.audit_dynamic_hotline_321 import independent_dynamic_hotline_audit

HOURS = D(24)
M026_3H_INITIAL = D("156.25220000")
M026_3H_FINAL = D("156.2972000000000000")
START_US = 1_735_689_600_000_000
END_US = 1_735_776_000_000_000


def _s(value: D) -> str:
    return format(value, "f")


def normalize_full_day_metrics(
    metrics: dict[str, Any], *, model_id: str = "M028"
) -> dict[str, Any]:
    """Replace M026's frozen 3h report labels without changing engine economics."""
    value = dict(metrics)
    initial = D(value["INITIAL_TOTAL_MARKED"])
    final = D(value["FINAL_TOTAL_MARKED"])
    if initial != M026_3H_INITIAL:
        raise ValueError(f"{model_id}_INITIAL_CAPITAL_DIVERGED_FROM_M026")
    gain = final - initial
    post_3h_gain = final - M026_3H_FINAL
    value.update(
        {
            "MODEL": model_id,
            "PARENT_STRATEGY": "M026",
            "PERIOD": "24H",
            "PHYSICAL_CYCLES_PER_HOUR": _s(D(value["PHYSICAL_CYCLES"]) / HOURS),
            "SLOT_EQUIVALENT_CYCLES_PER_HOUR": _s(
                D(value["SLOT_EQUIVALENT_CYCLES"]) / HOURS
            ),
            "INITIAL_MARKED_EQUITY_BEFORE": _s(initial),
            "FINAL_MARKED_EQUITY_AFTER": _s(final),
            "TOTAL_MARKED_GAIN": _s(gain),
            "TOTAL_MARKED_GAIN_PCT": _s(gain / initial * D(100)),
            "M026_3H_MARKED_EQUITY": _s(M026_3H_FINAL),
            "POST_3H_MARKED_GAIN": _s(post_3h_gain),
            "POST_3H_MARKED_GAIN_PCT": _s(post_3h_gain / M026_3H_FINAL * D(100)),
            "AUXILIARY_PHYSICAL_RULER_304_PASS": value["PHYSICAL_CYCLES"] >= 304,
            "AUXILIARY_SLOT_RULER_480_PASS": value["SLOT_EQUIVALENT_CYCLES"] >= 480,
            "AUXILIARY_RULERS_ARE_NOT_OWNER_PROMISES": True,
        }
    )
    for key in (
        "PHYSICAL_GATE_GT_12_3333_PASS",
        "PHYSICAL_GATE_EXACT_RULE",
        "SLOT_GATE_20_PER_HOUR_PASS",
    ):
        value.pop(key, None)
    return value


def independent_m026_24h_audit(
    rows: list[dict[str, Any]],
    terminal: dict[str, Any],
    metrics: dict[str, Any],
    canonical: dict[int, Any],
    prefix: dict[str, Any],
    *,
    model_id: str = "M028",
) -> dict[str, Any]:
    """Reuse the physical M026 audit, then independently verify 24h reporting."""
    base = independent_dynamic_hotline_audit(rows, terminal, metrics, canonical)

    def require(condition: bool, reason: str) -> None:
        if not condition:
            raise ValueError(f"{model_id}_AUDIT_{reason}")

    initial = D(metrics["INITIAL_TOTAL_MARKED"])
    final = D(metrics["FINAL_TOTAL_MARKED"])
    config = terminal.get("state", {}).get("parent", {}).get("config", {})
    require(metrics["MODEL"] == model_id, "MODEL")
    require(metrics["PARENT_STRATEGY"] == "M026", "PARENT")
    require(metrics["PERIOD"] == "24H", "PERIOD")
    require(config.get("start_us") == START_US, "TERMINAL_START")
    require(config.get("end_us") == END_US, "TERMINAL_END")
    require(
        D(metrics["PHYSICAL_CYCLES_PER_HOUR"])
        == D(metrics["PHYSICAL_CYCLES"]) / HOURS,
        "PHYSICAL_RATE",
    )
    require(
        D(metrics["SLOT_EQUIVALENT_CYCLES_PER_HOUR"])
        == D(metrics["SLOT_EQUIVALENT_CYCLES"]) / HOURS,
        "SLOT_RATE",
    )
    require(D(metrics["TOTAL_MARKED_GAIN"]) == final - initial, "GAIN")
    require(D(metrics["INITIAL_MARKED_EQUITY_BEFORE"]) == initial, "INITIAL_ALIAS")
    require(D(metrics["FINAL_MARKED_EQUITY_AFTER"]) == final, "FINAL_ALIAS")
    require(
        D(metrics["TOTAL_MARKED_GAIN_PCT"]) == (final - initial) / initial * D(100),
        "GAIN_PCT",
    )
    require(D(metrics["M026_3H_MARKED_EQUITY"]) == M026_3H_FINAL, "M026_3H_REFERENCE")
    require(
        D(metrics["POST_3H_MARKED_GAIN"]) == final - M026_3H_FINAL,
        "POST_3H_GAIN",
    )
    require(
        D(metrics["POST_3H_MARKED_GAIN_PCT"])
        == (final - M026_3H_FINAL) / M026_3H_FINAL * D(100),
        "POST_3H_GAIN_PCT",
    )
    require(
        metrics["AUXILIARY_PHYSICAL_RULER_304_PASS"]
        is (int(metrics["PHYSICAL_CYCLES"]) >= 304),
        "PHYSICAL_RULER",
    )
    require(
        metrics["AUXILIARY_SLOT_RULER_480_PASS"]
        is (int(metrics["SLOT_EQUIVALENT_CYCLES"]) >= 480),
        "SLOT_RULER",
    )
    require(metrics["AUXILIARY_RULERS_ARE_NOT_OWNER_PROMISES"] is True, "RULER_SCOPE")
    require(prefix.get("STATUS") == "PASS_EXACT_M026_3H_PREFIX_EQUIVALENCE", "PREFIX")
    require(prefix.get("LEDGER_EXACT_MATCH") is True, "PREFIX_LEDGER")
    require(prefix.get("ECONOMIC_STATE_MATCH") is True, "PREFIX_STATE")
    return {
        **base,
        "status": f"PASS_{model_id}_M026_24H_LEDGER_TERMINAL_PREFIX_AND_RETURN_AUDIT",
        "prefix_equivalence": True,
        "full_day_reporting_reconciled": True,
        "marked_gain_reconciled": True,
    }
