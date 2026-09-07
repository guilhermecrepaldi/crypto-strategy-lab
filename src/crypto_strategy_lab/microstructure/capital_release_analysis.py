"""Post-mortem release accounting; never an input to the trading policy."""

from __future__ import annotations

from bisect import bisect_left
from decimal import ROUND_DOWN, Decimal
from typing import Any

import numpy as np

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.capital_release import _fixed_100_transform
from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    SerialReplayResult,
    SerialTape,
    _datetime_to_micros,
)
from crypto_strategy_lab.microstructure.temporal_analysis import (
    TemporalReplayAnalysis,
    analyze_replay_temporally,
)

D = Decimal


def _quantile(values: list[Decimal], fraction: str) -> str | None:
    if not values:
        return None
    ordered = sorted(values)
    position = D(fraction) * (len(ordered) - 1)
    lo = int(position)
    hi = min(lo + 1, len(ordered) - 1)
    return str(ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo))


def _seconds(start: int, end: int) -> Decimal:
    return D(end // EVENT_ORDER_SCALE - start // EVENT_ORDER_SCALE) / D(1000000)


def audit_legacy_m007_event_projection(
    original: SerialReplayResult, corrected: SerialReplayResult
) -> dict[str, Any]:
    """Audit only the demonstrated legacy NumPy-to-Pydantic integer precision loss.

    This is a directed evidence projection, never a trading-time conversion or
    substitute for exact corrected-M007 versus M010 behavioral comparison.
    """
    if original.model_id != "M007" or corrected.model_id != "M007":
        raise ValueError("LEGACY_EVENT_AUDIT_REQUIRES_M007")
    if corrected.release_closures or corrected.release_evaluations:
        raise ValueError("TECHNICAL_PARENT_RECONSTRUCTION_MUST_NOT_APPLY_RELEASE")
    legacy = original.model_dump(mode="json")
    exact = corrected.model_dump(mode="json")
    projected = corrected.model_dump(mode="json")
    changed = {"cycle_entry_event": 0, "cycle_exit_event": 0, "selection_event": 0}
    examples: list[dict[str, Any]] = []

    def project(row: dict[str, Any], field: str, group: str, index: int) -> None:
        value = row[field]
        old_value = int(float(value))
        if value != old_value:
            changed[group] += 1
            if len(examples) < 20:
                examples.append(
                    {
                        "field": group,
                        "index": index,
                        "exact_event": value,
                        "legacy_event": old_value,
                    }
                )
        row[field] = old_value

    for index, cycle in enumerate(projected["cycles"]):
        for field in ("entry_event", "exit_event"):
            project(cycle, field, f"cycle_{field}", index)
    for index, selection in enumerate(projected["selection_changes"]):
        project(selection, "event", "selection_event", index)
    if legacy != projected:
        differences = sorted(
            key for key in legacy.keys() | projected.keys() if legacy.get(key) != projected.get(key)
        )
        raise ValueError("LEGACY_PARENT_RECONSTRUCTION_DIVERGENCE: " + ",".join(differences))
    return {
        "classification": "TECHNICAL_EVENT_ID_SERIALIZATION_CORRECTION",
        "legacy_behavior_hash": canonical_hash(legacy),
        "reconstructed_behavior_hash": canonical_hash(exact),
        "legacy_projection_hash": canonical_hash(projected),
        "projection": "INT_FLOAT_INT_ONLY_CYCLE_AND_SELECTION_EVENT_IDS",
        "changed_event_id_counts": changed,
        "examples": examples,
        "all_other_fields_exactly_equal": True,
        "immutable_legacy_artifact_modified": False,
    }


def compare_zero_release(
    parent: SerialReplayResult, challenger: SerialReplayResult
) -> dict[str, Any]:
    """Prove equality of the entire observable parent behavior, not just totals."""
    if challenger.release_closures:
        return {"M010_BEHAVIORALLY_EQUIVALENT_TO_M007": "NOT_APPLICABLE_RELEASE_OCCURRED"}
    exclude = {"model_id", "model_hash", "release_evaluations", "release_closures"}
    left = parent.model_dump(mode="json", exclude=exclude)
    right = challenger.model_dump(mode="json", exclude=exclude)
    if left != right:
        differences = sorted(
            key for key in left.keys() | right.keys() if left.get(key) != right.get(key)
        )
        raise ValueError("ZERO_RELEASE_BEHAVIORAL_DIVERGENCE: " + ",".join(differences))
    return {
        "M010_BEHAVIORALLY_EQUIVALENT_TO_M007": "YES",
        "behavior_hash": canonical_hash(left),
        "compared_fields": sorted(left),
        "FROZEN_RULE_DID_NOT_TRIGGER": True,
    }


def analyze_capital_release(
    result: SerialReplayResult,
    tape: SerialTape,
    *,
    temporal_analysis: TemporalReplayAnalysis | None = None,
) -> dict[str, Any]:
    """Account for all serial closures and censored exposure with exact money."""
    if result.initial_quote != D(100):
        raise ValueError("INITIAL_CAPITAL_INVARIANT_VIOLATION")
    closures = sorted((*result.cycles, *result.release_closures), key=lambda item: item.exit_event)
    releases = {item.exit_event: item for item in result.release_closures}
    snapshots = {
        int(item["checkpoint_event"]): item
        for item in result.release_evaluations
        if item["candidate_rule"]["would_release"]
    }
    if set(releases) != set(snapshots):
        raise ValueError("RELEASE_CLOSURE_SNAPSHOT_MISMATCH")
    end = _datetime_to_micros(result.end_exclusive) * EVENT_ORDER_SCALE
    cash = result.initial_quote
    fixed_pnl = D(0)
    fixed_release_loss = D(0)
    peak = cash
    drawdown = D(0)
    holds: list[Decimal] = []
    losses: list[Decimal] = []
    pending: list[dict[str, Any]] = []
    recovered_rows: list[dict[str, Any]] = []
    completed = 0

    def mark(value: Decimal) -> None:
        nonlocal peak, drawdown
        peak = max(peak, value)
        if peak > 0:
            drawdown = max(drawdown, (peak - value) / peak)

    def position_marks(entry: int, exit_event: int, residual: Decimal, quantity: Decimal) -> None:
        # Running integer maxima preserve chronology; only extrema need Decimal valuation.
        lo = bisect_left(tape.events, entry)
        hi = bisect_left(tape.events, exit_event)
        ticks = np.asarray(tape.price_ticks[lo:hi], dtype=np.int64)
        if not len(ticks):
            return
        maxima = np.maximum.accumulate(ticks)
        starts = np.r_[0, np.flatnonzero(maxima[1:] != maxima[:-1]) + 1]
        minima = np.minimum.reduceat(ticks, starts)
        for index, minimum in zip(starts, minima, strict=True):
            mark(residual + quantity * D(int(maxima[index])) * tape.tick_size)
            mark(residual + quantity * D(int(minimum)) * tape.tick_size)

    for cycle in closures:
        before = cash
        residual = cash - cycle.quantity * cycle.low - cycle.buy_fee_quote
        mark(residual + cycle.quantity * cycle.low)
        position_marks(cycle.entry_event, cycle.exit_event, residual, cycle.quantity)
        mark(residual + cycle.quantity * cycle.high)
        cash = residual + cycle.quantity * cycle.high - cycle.sell_fee_quote
        mark(cash)
        holds.append(_seconds(cycle.entry_event, cycle.exit_event))
        buy_rate = cycle.buy_fee_quote / (cycle.quantity * cycle.low)
        sell_rate = cycle.sell_fee_quote / (cycle.quantity * cycle.high)
        _, fixed_delta = _fixed_100_transform(cycle.low, cycle.high, buy_rate, sell_rate)
        fixed_pnl += fixed_delta
        is_release = cycle.exit_event in releases
        if not is_release:
            completed += 1
        for row in pending:
            for target in ("B", "K"):
                if row[f"time_to_recovery_{target}"] is None and cash >= D(row[f"target_{target}"]):
                    row[f"time_to_recovery_{target}"] = str(
                        _seconds(row["release_event"], cycle.exit_event)
                    )
                    row[f"cycles_to_recovery_{target}"] = completed - row["completed_at_release"]
        if is_release:
            snapshot = snapshots[cycle.exit_event]
            if (
                D(snapshot["B_cash_before_buy"]) != before
                or D(snapshot["release_cash_R_T"]) != cash
            ):
                raise ValueError("RELEASE_CASH_RECONCILIATION_FAILED")
            losses.append(before - cash)
            fixed_release_loss -= fixed_delta
            row = {
                "release_event": cycle.exit_event,
                "timestamp": cycle.exit_timestamp.isoformat(),
                "completed_at_release": completed,
                "target_B": str(before),
                "target_K": snapshot["target_cash_K_at_high"],
                "cycles_to_recovery_B": None,
                "cycles_to_recovery_K": None,
                "time_to_recovery_B": None,
                "time_to_recovery_K": None,
                "causal_snapshot": snapshot,
                "classification": "RETROSPECTIVE_DIAGNOSTIC_ONLY",
                "direct_realized_contribution_usdt": str(cash - before),
                "final_counterfactual_contribution": "UNKNOWN_NO_KEEP_BRANCH_REPLAY",
            }
            pending.append(row)
            recovered_rows.append(row)
    if result.open_cycle_censored:
        assert result.open_entry_event is not None and result.open_entry_price is not None
        assert result.open_buy_fee_quote is not None
        residual = (
            cash - result.final_inventory * result.open_entry_price - result.open_buy_fee_quote
        )
        if residual != result.final_cash:
            raise ValueError("TERMINAL_CASH_RECONCILIATION_FAILED")
        mark(residual + result.final_inventory * result.open_entry_price)
        position_marks(result.open_entry_event, end, residual, result.final_inventory)
        holds.append(_seconds(result.open_entry_event, end))
        fee = result.open_buy_fee_quote / (result.final_inventory * result.open_entry_price)
        quantity = (D(100) / (result.open_entry_price * (1 + fee)) / D("0.01")).to_integral_value(
            rounding=ROUND_DOWN
        ) * D("0.01")
        fixed_pnl += quantity * (result.last_price - result.open_entry_price * (1 + fee))
    elif cash != result.final_cash:
        raise ValueError("FINAL_CASH_RECONCILIATION_FAILED")
    mark(result.final_marked_equity)
    for row in recovered_rows:
        row["observed_followup_seconds"] = str(_seconds(row["release_event"], end))
        row["recovery_B_censored"] = row["time_to_recovery_B"] is None
        row["recovery_K_censored"] = row["time_to_recovery_K"] is None
    total_seconds = D(
        _datetime_to_micros(result.end_exclusive) - _datetime_to_micros(result.start)
    ) / D(1000000)
    daily = [D(value) for value in result.daily_cycles.values()]
    output: dict[str, Any] = {
        "classification": "RETROSPECTIVE_DIAGNOSTIC_ONLY",
        "INITIAL_CAPITAL": str(result.initial_quote),
        "FINAL_CAPITAL": str(result.final_marked_equity),
        "RETURN": str(result.return_fraction),
        "COMPLETED_CYCLES": result.completed_cycles,
        "AVG_CYCLES_DAY": str(D(result.completed_cycles) / len(daily)) if daily else None,
        "MEDIAN_CYCLES_DAY": _quantile(daily, "0.5"),
        "ZERO_CYCLE_DAYS": result.zero_cycle_days,
        "DAYS_GE_2000": sum(value >= 2000 for value in daily),
        "CAPITAL_RELEASE_COUNT": len(releases),
        "TOTAL_RELEASE_LOSS": str(sum(losses, D(0))),
        "AVG_RELEASE_LOSS": str(sum(losses, D(0)) / len(losses)) if losses else None,
        "MAX_RELEASE_LOSS": str(max(losses)) if losses else None,
        "RELEASE_LOSS_CURRENCY": "USDT",
        "MAX_HOLD": str(max(holds, default=D(0))),
        "P95_HOLD": _quantile(holds, "0.95"),
        "HOLD_UNIT": "SECONDS_INCLUDING_TERMINAL_CENSORING",
        "TIME_INVENTORY_OPEN": str(sum(holds, D(0))),
        "HOURS_POSITION_OLDER_THAN_24H": str(
            sum((max(value - D(86400), D(0)) for value in holds), D(0)) / 3600
        ),
        "IDLE_HOURS": str((total_seconds - sum(holds, D(0))) / 3600),
        "MAX_DRAWDOWN": str(drawdown),
        "TEMPORAL_STABILITY": (
            temporal_analysis or analyze_replay_temporally(result, tape)
        ).temporal_stability,
        "FIXED_NOTIONAL_100": {
            "initial_reference_capital": "100",
            "capital_mode": "FIXED_NOTIONAL_100",
            "additive_pnl": str(fixed_pnl),
            "final_reference_equity": str(100 + fixed_pnl),
            "total_release_loss": str(fixed_release_loss),
            "terminal_mark_included": result.open_cycle_censored,
        },
        "release_recoveries": recovered_rows,
        "recovery_primary_target": "K",
        "EXECUTABLE_RELEASE_LOSS": "UNKNOWN",
        "FROZEN_RULE_DID_NOT_TRIGGER": not bool(releases),
    }
    for target in ("B", "K"):
        recovered = [row for row in recovered_rows if row[f"time_to_recovery_{target}"] is not None]
        output[f"RELEASES_RECOVERED_{target}"] = len(recovered)
        output[f"RELEASES_NOT_RECOVERED_{target}"] = len(releases) - len(recovered)
        for metric, field in (("CYCLES", "cycles"), ("TIME", "time")):
            for suffix, fraction in (("P50", "0.5"), ("P90", "0.9")):
                output[f"RECOVERY_{metric}_{suffix}_{target}"] = _quantile(
                    [D(row[f"{field}_to_recovery_{target}"]) for row in recovered], fraction
                )
    for key in (
        "RELEASES_RECOVERED",
        "RELEASES_NOT_RECOVERED",
        "RECOVERY_CYCLES_P50",
        "RECOVERY_CYCLES_P90",
        "RECOVERY_TIME_P50",
        "RECOVERY_TIME_P90",
    ):
        output[key] = output[f"{key}_K"]
    return output
