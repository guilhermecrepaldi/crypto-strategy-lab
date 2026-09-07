"""Independent exact-money reconstruction; retrospective only, never decision input."""

from __future__ import annotations

from bisect import bisect_left
from copy import deepcopy
from datetime import UTC, datetime, time
from decimal import Decimal, localcontext
from typing import Any

import numpy as np

from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    SerialReplayResult,
    SerialTape,
    _datetime_to_micros,
    _event_to_datetime,
)

D = Decimal
HOUR = 3600 * 1_000_000 * EVENT_ORDER_SCALE


def _audit_ledger(
    result: SerialReplayResult,
    tape: SerialTape,
    skim_rate: Decimal,
    expected_reserve: Decimal,
    releases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replay money movements and mark every price extremum in chronological order."""
    releases = deepcopy(releases)
    cash, reserve = D(100), D(5)
    peak, drawdown, operating_peak, operating_drawdown = D(105), D(0), D(100), D(0)
    reserve_min, total_skim, total_loss = reserve, D(0), D(0)
    depletion_count = 0
    empty_since: int | None = None
    empty_duration = longest_empty = 0
    start = _datetime_to_micros(result.start) * EVENT_ORDER_SCALE
    end = _datetime_to_micros(result.end_exclusive) * EVENT_ORDER_SCALE
    series: list[dict[str, Any]] = []
    markers: list[dict[str, Any]] = []
    last_day: str | None = None
    completed = 0
    by_event = {int(item["event"]): item for item in releases}
    if set(by_event) != {item.exit_event for item in result.release_closures}:
        raise ValueError("RESERVE_RELEASE_LEDGER_MISMATCH")
    for day, cycles in result.daily_cycles.items():
        if cycles == 0:
            event = _datetime_to_micros(datetime.combine(day, time.min, tzinfo=UTC))
            markers.append({"event": event * EVENT_ORDER_SCALE, "type": "ZERO_CYCLE_DAY"})

    def mark(operating: Decimal) -> None:
        nonlocal peak, drawdown, operating_peak, operating_drawdown
        equity = operating + reserve
        peak = max(peak, equity)
        operating_peak = max(operating_peak, operating)
        drawdown = max(drawdown, (peak - equity) / peak)
        operating_drawdown = max(operating_drawdown, (operating_peak - operating) / operating_peak)

    def point(
        event: int, residual: Decimal, quantity: Decimal, price: Decimal, *, force: bool = False
    ) -> None:
        nonlocal last_day
        day = _event_to_datetime(event).date().isoformat()
        if force or day != last_day:
            series.append(
                {
                    "event": event,
                    "timestamp": _event_to_datetime(event).isoformat(),
                    "operating_cash": str(residual),
                    "inventory_mark": str(quantity * price),
                    "operating_bank": str(residual + quantity * price),
                    "reserve": str(reserve),
                    "total_equity": str(residual + quantity * price + reserve),
                    "cumulative_cycles": completed,
                }
            )
            last_day = day

    def position(entry: int, exit_event: int, residual: Decimal, quantity: Decimal) -> None:
        lo, hi = bisect_left(tape.events, entry), bisect_left(tape.events, exit_event)
        ticks = np.asarray(tape.price_ticks[lo:hi], dtype=np.int64)
        if len(ticks):
            # Same exact chronological-extrema technique as the existing canonical autopsy.
            maxima = np.maximum.accumulate(ticks)
            starts = np.r_[0, np.flatnonzero(maxima[1:] != maxima[:-1]) + 1]
            minima = np.minimum.reduceat(ticks, starts)
            for index, minimum in zip(starts, minima, strict=True):
                mark(residual + quantity * D(int(maxima[index])) * tape.tick_size)
                mark(residual + quantity * D(int(minimum)) * tape.tick_size)
        for boundary in range(((entry // (24 * HOUR)) + 1) * 24 * HOUR, exit_event, 24 * HOUR):
            price = D(tape.last_price_before(boundary)) * tape.tick_size
            point(boundary, residual, quantity, price)
        if entry + 24 * HOUR < exit_event:
            markers.append({"event": entry + 24 * HOUR, "type": "CAPITAL_LOCK_START"})

    point(start, cash, D(0), D(0), force=True)
    pending: list[dict[str, Any]] = []
    for cycle in sorted(
        (*result.cycles, *result.release_closures), key=lambda item: item.exit_event
    ):
        before = cash
        cost = cycle.quantity * cycle.low + cycle.buy_fee_quote
        cash -= cost
        mark(cash + cycle.quantity * cycle.low)
        point(cycle.entry_event, cash, cycle.quantity, cycle.low)
        position(cycle.entry_event, cycle.exit_event, cash, cycle.quantity)
        mark(cash + cycle.quantity * cycle.high)
        net_sale = cycle.quantity * cycle.high - cycle.sell_fee_quote
        cash += net_sale
        mark(cash)
        prior_reserve = reserve
        if cycle.exit_event in by_event:
            row = by_event[cycle.exit_event]
            deficit = cost - net_sale
            if deficit <= 0 or D(row["reserve_transfer"]) != deficit or reserve < deficit:
                raise ValueError("RESERVE_EXACT_DEFICIT_VIOLATION")
            if (
                D(row["operating_bank_before"]) != before
                or D(row["operating_bank_after_sale"]) != cash
            ):
                raise ValueError("RESERVE_OPERATING_RECONCILIATION_FAILED")
            point(cycle.exit_event, cash, D(0), D(0), force=True)
            reserve -= deficit
            cash += deficit
            total_loss += deficit
            if (
                cash != before
                or D(row["reserve_after"]) != reserve
                or D(row["reserve_before"]) != prior_reserve
            ):
                raise ValueError("RESERVE_TRANSFER_RECONCILIATION_FAILED")
            pending.append(
                {
                    "event": cycle.exit_event,
                    "target": str(prior_reserve),
                    "completed_at_release": completed,
                    "time_to_replenish_seconds": None,
                    "cycles_to_replenish": None,
                }
            )
            for kind in ("RECOVERY_RELEASE", "RESERVE_TRANSFER", "NEW_RANGE"):
                markers.append({"event": cycle.exit_event, "type": kind})
            high_tick = int(D(row["original_high"]) / tape.tick_size)
            high_events = tape.occurrences.get(high_tick, [])
            index = bisect_left(high_events, cycle.exit_event)
            returned = (
                int(high_events[index])
                if index < len(high_events) and high_events[index] < end
                else None
            )
            row["retrospective"] = {
                "classification": "RETROSPECTIVE_DIAGNOSTIC_ONLY",
                "original_high_return_event": returned,
                "right_censored": returned is None,
                "waiting_seconds_or_lower_bound": str(
                    D((returned or end) - cycle.exit_event) / HOUR * 3600
                ),
                "subsequent_cycles": result.completed_cycles - completed,
            }
        else:
            completed += 1
            contribution = max(D(0), net_sale - cost) * skim_rate
            cash -= contribution
            reserve += contribution
            total_skim += contribution
        reserve_min = min(reserve_min, reserve)
        if reserve == 0 and prior_reserve > 0:
            depletion_count += 1
            empty_since = cycle.exit_event
        if reserve > 0 and empty_since is not None:
            duration = cycle.exit_event - empty_since
            empty_duration += duration
            longest_empty = max(longest_empty, duration)
            empty_since = None
        for target in pending:
            if target["time_to_replenish_seconds"] is None and reserve >= D(target["target"]):
                target["time_to_replenish_seconds"] = str(
                    D(cycle.exit_event - target["event"]) / HOUR * 3600
                )
                target["cycles_to_replenish"] = completed - target["completed_at_release"]
                markers.append({"event": cycle.exit_event, "type": "RESERVE_REPLENISHED"})
        mark(cash)
        point(cycle.exit_event, cash, D(0), D(0), force=cycle.exit_event in by_event)
    if result.open_entry_event is not None:
        assert result.open_entry_price is not None and result.open_buy_fee_quote is not None
        cash -= result.final_inventory * result.open_entry_price + result.open_buy_fee_quote
        mark(cash + result.final_inventory * result.open_entry_price)
        position(result.open_entry_event, end, cash, result.final_inventory)
    if cash != result.final_cash or reserve != expected_reserve:
        raise ValueError("RESERVE_FINAL_LEDGER_RECONCILIATION_FAILED")
    if empty_since is not None:
        duration = end - empty_since
        empty_duration += duration
        longest_empty = max(longest_empty, duration)
    mark(result.final_marked_equity)
    point(end, cash, result.final_inventory, result.last_price, force=True)
    return {
        "integrity_pass": True,
        "maximum_drawdown": str(drawdown),
        "operating_maximum_drawdown": str(operating_drawdown),
        "min_reserve_balance": str(reserve_min),
        "max_reserve_balance": str(
            max((D(point["reserve"]) for point in series), default=D(5))
        ),
        "reserve_depletion_events": depletion_count,
        "total_skim": str(total_skim),
        "total_release_loss": str(total_loss),
        "reserve_empty_fraction": str(D(empty_duration) / (end - start)),
        "longest_reserve_empty_hours": str(D(longest_empty) / HOUR),
        "series": series,
        "markers": sorted(markers, key=lambda row: row["event"]),
        "replenishments": pending,
        "releases": releases,
        "series_sampling": (
            "UTC_DAY_BOUNDARIES_AND_SETTLEMENT_EVENTS; drawdown uses all tape extrema"
        ),
    }


def audit_ledger(
    result: SerialReplayResult,
    tape: SerialTape,
    skim_rate: Decimal,
    expected_reserve: Decimal,
    releases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Audit with an independent high-precision money context."""
    with localcontext() as context:
        context.prec = 128
        return _audit_ledger(result, tape, skim_rate, expected_reserve, releases)
