"""Deterministic post-replay productivity and temporal-regime analysis.

This module is deliberately downstream of :mod:`serial_replay`: none of its outputs can
change a model decision, stop a replay, or close an open position.  All window boundaries
are UTC and all financial arithmetic remains ``Decimal`` based.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Any, Final, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from crypto_strategy_lab.domain import canonical_hash, require_utc
from crypto_strategy_lab.microstructure.market_profile import MarketHour, MarketHourlyProfile
from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    MICROS_PER_SECOND,
    SerialReplayResult,
    SerialTape,
)

EPS_PROFIT: Final = Decimal("0.00000001")
EPS_RATE: Final = Decimal("0.000000000001")
HORIZON_HOURS: Final = (1, 4, 12, 24, 72, 168, 336, 720)
HOUR_MICROS: Final = 3_600 * MICROS_PER_SECOND


class WindowMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: datetime
    end_exclusive: datetime
    complete: bool
    start_equity: Decimal
    end_equity: Decimal
    mtm_delta: Decimal
    realized_net_profit: Decimal
    gross_edge_quote: Decimal
    fees_quote: Decimal
    completed_cycles: int
    idle_hours: Decimal
    holding_hours: Decimal
    capital_hours: Decimal
    net_profit_per_hour: Decimal
    net_productivity_per_hour: Decimal | None
    capital_hour_return: Decimal | None
    terminal_position_open: bool
    classification: Literal["UNKNOWN", "FAILURE", "HOT", "COLD", "NORMAL"] = "UNKNOWN"
    raw_negative_mtm: bool = False
    raw_negative_realized: bool = False
    raw_zero_cycles: bool = False


class HorizonMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    horizon_hours: int
    baseline_net_productivity: Decimal | None
    mad_net_productivity: Decimal | None
    band: Decimal | None
    complete_block_count: int
    rolling: tuple[WindowMetrics, ...]
    blocks: tuple[WindowMetrics, ...]
    incomplete_tail: WindowMetrics | None
    top10: tuple[WindowMetrics, ...]
    bottom10: tuple[WindowMetrics, ...]
    top_bottom_overlap: bool
    longest_hot_streak: dict[str, Any] | None
    longest_cold_streak: dict[str, Any] | None
    temporal_stability: dict[str, Any]


class TemporalReplayAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "usdcusdt-temporal-productivity-v1"
    model_id: str
    start: datetime
    end_exclusive: datetime
    data_support: dict[str, str]
    daily: tuple[dict[str, Any], ...]
    weekly: tuple[dict[str, Any], ...]
    monthly: tuple[dict[str, Any], ...]
    hour_of_day: tuple[dict[str, Any], ...]
    day_of_week: tuple[dict[str, Any], ...]
    horizons: tuple[HorizonMetrics, ...]
    concentration: dict[str, Any]
    temporal_stability: dict[str, Any]
    regime_contrasts: dict[str, Any]
    productivity_distribution: dict[str, Any]
    productivity_fingerprint: dict[str, Any]


class MarketProductivityRegime(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "usdcusdt-market-productivity-cohort-v1"
    cohort_hash: str
    model_ids: tuple[str, ...]
    dataset_hash: str
    scenario_hash: str
    start: datetime
    end_exclusive: datetime
    horizon_hours: int
    required_consensus: int
    blocks: tuple[dict[str, Any], ...]
    caveat: str = (
        "Observed cohort productivity regime; correlated models are not independent and "
        "consensus does not prove an exogenous market cause."
    )


@dataclass(frozen=True, slots=True)
class _LedgerEvent:
    event: int
    cash_delta: Decimal
    inventory_delta: Decimal


class _PriceIntegral:
    """Exact integer-tick integral of the last observed trade price."""

    def __init__(self, tape: SerialTape) -> None:
        self._tape = tape
        count = len(tape.events)
        self._areas = np.empty(count, dtype=np.int64)
        self._areas[0] = 0
        chunk_size = 5_000_000
        prior_area = 0
        for start in range(1, count, chunk_size):
            stop = min(start + chunk_size, count)
            encoded = np.frombuffer(
                tape.events,
                dtype=np.int64,
                count=stop - start + 1,
                offset=(start - 1) * np.dtype(np.int64).itemsize,
            )
            micros = encoded // EVENT_ORDER_SCALE
            deltas = np.diff(micros)
            prices = np.frombuffer(
                tape.price_ticks,
                dtype=np.int32,
                count=stop - start,
                offset=(start - 1) * np.dtype(np.int32).itemsize,
            ).astype(np.int64)
            cumulative = np.cumsum(deltas * prices, dtype=np.int64)
            self._areas[start:stop] = prior_area + cumulative
            prior_area = int(self._areas[stop - 1])

    def mark(self, boundary_event: int) -> Decimal:
        tick = self._tape.last_price_before(boundary_event)
        return Decimal(tick) * self._tape.tick_size

    def quote_hours(self, start_event: int, end_event: int) -> Decimal:
        if end_event <= start_event:
            return Decimal("0")
        start_micros = start_event // EVENT_ORDER_SCALE
        end_micros = end_event // EVENT_ORDER_SCALE
        tick_micros = self._prefix(end_micros) - self._prefix(start_micros)
        return Decimal(tick_micros) * self._tape.tick_size / Decimal(HOUR_MICROS)

    def _prefix(self, micros: int) -> int:
        timestamp_end = micros * EVENT_ORDER_SCALE + EVENT_ORDER_SCALE
        index = bisect_left(self._tape.events, timestamp_end) - 1
        if index < 0:
            raise ValueError("price integral precedes the first observed trade")
        return int(self._areas[index]) + self._tape.price_ticks[index] * (
            micros - self._tape.events[index] // EVENT_ORDER_SCALE
        )


class TemporalAnalysisContext:
    """Reusable immutable market math shared by every model on one tape."""

    def __init__(self, tape: SerialTape) -> None:
        self.tape = tape
        self.price_integral = _PriceIntegral(tape)


class _Ledger:
    def __init__(
        self,
        result: SerialReplayResult,
        tape: SerialTape,
        price_integral: _PriceIntegral | None = None,
    ) -> None:
        self.result = result
        self.price = price_integral or _PriceIntegral(tape)
        events: list[_LedgerEvent] = []
        for cycle in result.cycles:
            buy_notional = cycle.quantity * cycle.low
            events.append(
                _LedgerEvent(
                    cycle.entry_event,
                    -(buy_notional + cycle.buy_fee_quote),
                    cycle.quantity,
                )
            )
            events.append(
                _LedgerEvent(
                    cycle.exit_event,
                    cycle.quantity * cycle.high - cycle.sell_fee_quote,
                    -cycle.quantity,
                )
            )
        if result.open_cycle_censored:
            if (
                result.open_entry_event is None
                or result.open_entry_price is None
                or result.open_buy_fee_quote is None
            ):
                raise ValueError("open cycle accounting evidence is incomplete")
            events.append(
                _LedgerEvent(
                    result.open_entry_event,
                    -(result.final_inventory * result.open_entry_price) - result.open_buy_fee_quote,
                    result.final_inventory,
                )
            )
        self.events = sorted(events, key=lambda item: item.event)
        self.event_ids = [item.event for item in self.events]
        self.cash_after: list[Decimal] = []
        self.inventory_after: list[Decimal] = []
        self.integral_at: list[Decimal] = []
        self.holding_at: list[Decimal] = []
        cash = result.initial_quote
        inventory = Decimal("0")
        integral = Decimal("0")
        holding = Decimal("0")
        previous = _event(result.start)
        for item in self.events:
            integral += self._segment_integral(previous, item.event, cash, inventory)
            if inventory > 0:
                holding += _hours(previous, item.event)
            cash += item.cash_delta
            inventory += item.inventory_delta
            if inventory < 0:
                raise ValueError("reconstructed inventory became negative")
            self.cash_after.append(cash)
            self.inventory_after.append(inventory)
            self.integral_at.append(integral)
            self.holding_at.append(holding)
            previous = item.event

    def state(self, boundary: int) -> tuple[Decimal, Decimal]:
        index = bisect_left(self.event_ids, boundary) - 1
        if index < 0:
            return self.result.initial_quote, Decimal("0")
        return self.cash_after[index], self.inventory_after[index]

    def equity(self, boundary: int) -> Decimal:
        cash, inventory = self.state(boundary)
        return cash + inventory * self.price.mark(boundary)

    def integral(self, boundary: int) -> Decimal:
        start = _event(self.result.start)
        if boundary <= start:
            return Decimal("0")
        index = bisect_left(self.event_ids, boundary) - 1
        if index < 0:
            return self._segment_integral(start, boundary, self.result.initial_quote, Decimal("0"))
        return self.integral_at[index] + self._segment_integral(
            self.event_ids[index],
            boundary,
            self.cash_after[index],
            self.inventory_after[index],
        )

    def holding(self, boundary: int) -> Decimal:
        start = _event(self.result.start)
        if boundary <= start:
            return Decimal("0")
        index = bisect_left(self.event_ids, boundary) - 1
        if index < 0:
            return Decimal("0")
        value = self.holding_at[index]
        if self.inventory_after[index] > 0:
            value += _hours(self.event_ids[index], boundary)
        return value

    def _segment_integral(self, start: int, end: int, cash: Decimal, inventory: Decimal) -> Decimal:
        if end <= start:
            return Decimal("0")
        return cash * _hours(start, end) + inventory * self.price.quote_hours(start, end)


def analyze_replay_temporally(
    result: SerialReplayResult,
    tape: SerialTape,
    market_profile: MarketHourlyProfile | None = None,
    context: TemporalAnalysisContext | None = None,
) -> TemporalReplayAnalysis:
    """Build the frozen post-replay temporal analysis without changing the replay."""
    if context is not None and context.tape is not tape:
        raise ValueError("temporal analysis context belongs to another tape")
    ledger = _Ledger(
        result,
        tape,
        context.price_integral if context is not None else None,
    )
    cycles = tuple(result.cycles)
    exit_events = [item.exit_event for item in cycles]
    gross_prefix = [Decimal("0")]
    fee_prefix = [Decimal("0")]
    for cycle in cycles:
        gross_prefix.append(gross_prefix[-1] + cycle.quantity * (cycle.high - cycle.low))
        fee_prefix.append(fee_prefix[-1] + cycle.buy_fee_quote + cycle.sell_fee_quote)
    reselections = [item.event for item in result.selection_changes]

    def bucket(start: datetime, end: datetime, *, complete: bool) -> WindowMetrics:
        return _window(
            ledger,
            cycles,
            exit_events,
            gross_prefix,
            fee_prefix,
            reselections,
            start,
            end,
            complete=complete,
        )

    daily_windows = [
        bucket(start, end, complete=complete)
        for start, end, complete in _calendar_intervals(result.start, result.end_exclusive, "day")
    ]
    weekly_windows = [
        bucket(start, end, complete=complete)
        for start, end, complete in _calendar_intervals(result.start, result.end_exclusive, "week")
    ]
    monthly_windows = [
        bucket(start, end, complete=complete)
        for start, end, complete in _calendar_intervals(result.start, result.end_exclusive, "month")
    ]
    hourly_windows = [
        bucket(start, end, complete=complete)
        for start, end, complete in _fixed_intervals(
            result.start, result.end_exclusive, timedelta(hours=1)
        )
    ]

    horizons = tuple(
        _horizon(result.start, result.end_exclusive, hours, bucket) for hours in HORIZON_HOURS
    )
    classified_hourly = _replace_complete_windows(hourly_windows, horizons[0].blocks)
    classified_daily = _replace_complete_windows(
        daily_windows, next(item for item in horizons if item.horizon_hours == 24).blocks
    )
    daily = tuple(_period_row(item, cycles, reselections, "day") for item in classified_daily)
    weekly = tuple(_period_row(item, cycles, reselections, "week") for item in weekly_windows)
    monthly = tuple(
        _monthly_row(item, classified_daily, cycles, reselections) for item in monthly_windows
    )
    concentration: dict[str, Any] = {
        "daily": _concentration(daily_windows, "day"),
        "weekly": _concentration(weekly_windows, "week"),
        "monthly": _concentration(monthly_windows, "month"),
    }
    concentration["PROFIT_CONCENTRATION_WARNING"] = _concentration_warning(
        concentration, daily_windows, weekly_windows, monthly_windows
    )
    stability = _aggregate_stability(horizons, result.final_marked_equity - result.initial_quote)
    if market_profile is not None and (
        market_profile.start != result.start or market_profile.end_exclusive != result.end_exclusive
    ):
        raise ValueError("market profile and replay interval differ")
    regime_contrasts = _regime_contrasts(classified_hourly, tape, market_profile)
    regime_contrasts["tick_distance"] = _tick_distance_summary(cycles, tape.tick_size)
    fingerprint = _fingerprint(classified_daily, monthly_windows, horizons)
    return TemporalReplayAnalysis(
        model_id=result.model_id,
        start=result.start,
        end_exclusive=result.end_exclusive,
        data_support={
            "price": "OBSERVED_TRADES",
            "trade_intensity": "OBSERVED_TRADES",
            "gross_trade_volume": (
                "OBSERVED_TRADES" if market_profile is not None else "PROFILE_NOT_PROVIDED"
            ),
            "spread_bid_ask": "UNKNOWN",
            "mid": "UNKNOWN",
            "book_depth": "UNKNOWN",
            "queue_ahead": "UNKNOWN",
            "fills_partial_fills": "UNKNOWN_PRICE_PATH_ONLY",
            "latency": "COUNTERFACTUAL_ZERO",
            "executable_capacity": "UNKNOWN",
        },
        daily=daily,
        weekly=weekly,
        monthly=monthly,
        hour_of_day=_calendar_group(classified_hourly, lambda item: item.start.hour, "hour_utc"),
        day_of_week=_calendar_group(classified_daily, lambda item: item.start.weekday(), "weekday"),
        horizons=horizons,
        concentration=concentration,
        temporal_stability=stability,
        regime_contrasts=regime_contrasts,
        productivity_distribution={
            "daily": _productivity_distribution(classified_daily),
            "weekly": _productivity_distribution(weekly_windows),
            "monthly": _productivity_distribution(monthly_windows),
        },
        productivity_fingerprint=fingerprint,
    )


def analyze_market_productivity_regime(
    analyses: Sequence[TemporalReplayAnalysis],
    *,
    dataset_hash: str,
    scenario_hash: str,
    horizon_hours: int = 24,
) -> MarketProductivityRegime:
    """Classify common independent blocks for one frozen, comparable model cohort."""
    if len(analyses) < 3:
        raise ValueError("market productivity regime requires at least three distinct models")
    model_ids = tuple(sorted(item.model_id for item in analyses))
    if len(set(model_ids)) != len(model_ids):
        raise ValueError("cohort models must be distinct strategy identities")
    starts = {item.start for item in analyses}
    ends = {item.end_exclusive for item in analyses}
    if len(starts) != 1 or len(ends) != 1:
        raise ValueError("cohort models must share one replay interval")
    by_model: dict[str, dict[datetime, WindowMetrics]] = {}
    for analysis in analyses:
        horizon = next(
            (item for item in analysis.horizons if item.horizon_hours == horizon_hours),
            None,
        )
        if horizon is None:
            raise ValueError(f"analysis lacks the {horizon_hours}h horizon")
        by_model[analysis.model_id] = {item.start: item for item in horizon.blocks}
    common = set.intersection(*(set(items) for items in by_model.values()))
    required = (2 * len(analyses) + 2) // 3
    blocks: list[dict[str, Any]] = []
    for start in sorted(common):
        classifications = {
            model_id: by_model[model_id][start].classification for model_id in model_ids
        }
        names = ("FAILURE", "HOT", "COLD", "NORMAL")
        counts = {name: sum(value == name for value in classifications.values()) for name in names}
        consensus = "MIXED"
        for name in names:
            if counts[name] >= required:
                consensus = f"CONSENSUS_{name}"
                break
        blocks.append(
            {
                "start": start,
                "end_exclusive": by_model[model_ids[0]][start].end_exclusive,
                "classification": consensus,
                "counts": counts,
                "models": classifications,
            }
        )
    identity = {
        "model_ids": model_ids,
        "dataset_hash": dataset_hash,
        "scenario_hash": scenario_hash,
        "start": next(iter(starts)),
        "end_exclusive": next(iter(ends)),
        "horizon_hours": horizon_hours,
    }
    return MarketProductivityRegime(
        cohort_hash=canonical_hash(identity),
        model_ids=model_ids,
        dataset_hash=dataset_hash,
        scenario_hash=scenario_hash,
        start=next(iter(starts)),
        end_exclusive=next(iter(ends)),
        horizon_hours=horizon_hours,
        required_consensus=required,
        blocks=tuple(blocks),
    )


def _window(
    ledger: _Ledger,
    cycles: Sequence[Any],
    exit_events: Sequence[int],
    gross_prefix: Sequence[Decimal],
    fee_prefix: Sequence[Decimal],
    reselections: Sequence[int],
    start: datetime,
    end: datetime,
    *,
    complete: bool,
) -> WindowMetrics:
    start_event = _event(start)
    end_event = _event(end)
    left = bisect_left(exit_events, start_event)
    right = bisect_left(exit_events, end_event)
    gross = gross_prefix[right] - gross_prefix[left]
    fees = fee_prefix[right] - fee_prefix[left]
    realized = gross - fees
    duration = _hours(start_event, end_event)
    holding = ledger.holding(end_event) - ledger.holding(start_event)
    capital_hours = ledger.integral(end_event) - ledger.integral(start_event)
    start_equity = ledger.equity(start_event)
    end_equity = ledger.equity(end_event)
    delta = end_equity - start_equity
    net_productivity = realized / capital_hours if capital_hours > 0 else None
    capital_return = delta / capital_hours if capital_hours > 0 else None
    _cash, inventory = ledger.state(end_event)
    return WindowMetrics(
        start=start,
        end_exclusive=end,
        complete=complete,
        start_equity=start_equity,
        end_equity=end_equity,
        mtm_delta=delta,
        realized_net_profit=realized,
        gross_edge_quote=gross,
        fees_quote=fees,
        completed_cycles=right - left,
        idle_hours=duration - holding,
        holding_hours=holding,
        capital_hours=capital_hours,
        net_profit_per_hour=realized / duration,
        net_productivity_per_hour=net_productivity,
        capital_hour_return=capital_return,
        terminal_position_open=inventory > 0,
        raw_negative_mtm=delta < -EPS_PROFIT,
        raw_negative_realized=realized < -EPS_PROFIT,
        raw_zero_cycles=right == left,
    )


def _horizon(
    campaign_start: datetime,
    campaign_end: datetime,
    hours: int,
    bucket: Any,
) -> HorizonMetrics:
    duration = timedelta(hours=hours)
    intervals = list(_fixed_intervals(campaign_start, campaign_end, duration))
    raw_blocks = [bucket(start, end, complete=complete) for start, end, complete in intervals]
    blocks = [item for item in raw_blocks if item.complete]
    tail = next((item for item in raw_blocks if not item.complete), None)
    valid = [item.net_productivity_per_hour for item in blocks]
    valid_values = [item for item in valid if item is not None]
    baseline: Decimal | None = None
    mad: Decimal | None = None
    band: Decimal | None = None
    if len(valid_values) >= 4:
        baseline = median(valid_values)
        mad = median([abs(item - baseline) for item in valid_values])
        band = max(mad, EPS_RATE)
    classified_blocks = tuple(_classify(item, baseline, band) for item in blocks)
    rolling: list[WindowMetrics] = []
    cursor = campaign_start
    while cursor + duration <= campaign_end:
        rolling.append(_classify(bucket(cursor, cursor + duration, complete=True), baseline, band))
        cursor += timedelta(hours=1)
    ranked = [item for item in classified_blocks if item.capital_hour_return is not None]
    best = sorted(
        ranked,
        key=lambda item: (-(item.capital_hour_return or Decimal("0")), item.start),
    )[:10]
    worst = sorted(
        ranked,
        key=lambda item: (item.capital_hour_return or Decimal("0"), item.start),
    )[:10]
    return HorizonMetrics(
        horizon_hours=hours,
        baseline_net_productivity=baseline,
        mad_net_productivity=mad,
        band=band,
        complete_block_count=len(classified_blocks),
        rolling=tuple(rolling),
        blocks=classified_blocks,
        incomplete_tail=tail,
        top10=tuple(best),
        bottom10=tuple(worst),
        top_bottom_overlap=bool({item.start for item in best} & {item.start for item in worst}),
        longest_hot_streak=_longest_streak(classified_blocks, "HOT"),
        longest_cold_streak=_longest_streak(classified_blocks, "COLD"),
        temporal_stability=_stability(classified_blocks, mad),
    )


def _classify(item: WindowMetrics, baseline: Decimal | None, band: Decimal | None) -> WindowMetrics:
    productivity = item.net_productivity_per_hour
    if productivity is None or baseline is None or band is None:
        classification = "UNKNOWN"
    elif item.mtm_delta < -EPS_PROFIT or item.realized_net_profit < -EPS_PROFIT:
        classification = "FAILURE"
    elif item.realized_net_profit > EPS_PROFIT and productivity > baseline + band:
        classification = "HOT"
    elif item.completed_cycles == 0 or productivity < baseline - band:
        classification = "COLD"
    else:
        classification = "NORMAL"
    return item.model_copy(update={"classification": classification})


def _stability(blocks: Sequence[WindowMetrics], mad: Decimal | None) -> dict[str, Any]:
    valid = [item for item in blocks if item.net_productivity_per_hour is not None]
    if len(valid) < 4 or mad is None:
        return {"score": None, "reason": "INSUFFICIENT_COMPLETE_BLOCKS"}
    count = Decimal(len(valid))
    profitable_fraction = (
        Decimal(sum(item.realized_net_profit > EPS_PROFIT for item in valid)) / count
    )
    failure_fraction = Decimal(sum(item.classification == "FAILURE" for item in valid)) / count
    magnitude = median([abs(item.net_productivity_per_hour or Decimal("0")) for item in valid])
    relative_variability = mad / (magnitude + mad + EPS_RATE)
    score = (
        Decimal("100")
        * profitable_fraction
        * (Decimal("1") - failure_fraction)
        * (Decimal("1") - relative_variability)
    )
    return {
        "score": score,
        "profitable_fraction": profitable_fraction,
        "failure_fraction": failure_fraction,
        "median_absolute_productivity": magnitude,
        "mad": mad,
        "relative_variability": relative_variability,
    }


def _aggregate_stability(
    horizons: Sequence[HorizonMetrics], full_mtm_delta: Decimal
) -> dict[str, Any]:
    subscores = {f"{item.horizon_hours}h": item.temporal_stability for item in horizons}
    scores = [item.temporal_stability.get("score") for item in horizons]
    if full_mtm_delta <= EPS_PROFIT:
        aggregate: Decimal | None = Decimal("0")
        reason = "FULL_REPLAY_MTM_NOT_POSITIVE"
    elif any(score is None for score in scores):
        aggregate = None
        reason = "NOT_ALL_EIGHT_HORIZONS_ELIGIBLE"
    else:
        aggregate = sum((Decimal(str(score)) for score in scores), Decimal("0")) / Decimal(
            len(scores)
        )
        reason = "DESCRIPTIVE_ONLY"
    return {"aggregate": aggregate, "reason": reason, "horizons": subscores}


def _period_row(
    item: WindowMetrics,
    cycles: Sequence[Any],
    reselections: Sequence[int],
    period: str,
) -> dict[str, Any]:
    start_event, end_event = _event(item.start), _event(item.end_exclusive)
    holding_values = [
        Decimal((cycle.exit_timestamp - cycle.entry_timestamp).total_seconds()) / Decimal(3600)
        for cycle in cycles
        if start_event <= cycle.exit_event < end_event
    ]
    return {
        "period_type": period,
        "period": _period_label(item.start, period),
        **item.model_dump(mode="json"),
        "return_fraction": item.end_equity / item.start_equity - Decimal("1"),
        "reselection_count": _count_between(reselections, start_event, end_event),
        "median_completed_cycle_holding_hours": (
            median(holding_values) if holding_values else None
        ),
    }


def _monthly_row(
    item: WindowMetrics,
    days: Sequence[WindowMetrics],
    cycles: Sequence[Any],
    reselections: Sequence[int],
) -> dict[str, Any]:
    row = _period_row(item, cycles, reselections, "month")
    included = [
        day for day in days if item.start <= day.start and day.end_exclusive <= item.end_exclusive
    ]
    counts = [day.completed_cycles for day in included]
    duration_days = Decimal((item.end_exclusive - item.start).total_seconds()) / Decimal(86_400)
    row.update(
        {
            "cycles_per_day": Decimal(item.completed_cycles) / duration_days,
            "median_daily_cycles": median(counts) if counts else None,
            "days_at_least_2000_cycles": sum(value >= 2_000 for value in counts),
            "zero_cycle_days": sum(value == 0 for value in counts),
        }
    )
    return row


def _concentration(windows: Sequence[WindowMetrics], granularity: str) -> dict[str, Any]:
    def calculation(items: Sequence[WindowMetrics]) -> dict[str, Any]:
        positive = sorted((item.mtm_delta for item in items if item.mtm_delta > 0), reverse=True)
        gross = sum(positive, Decimal("0"))
        losses = sum((-item.mtm_delta for item in items if item.mtm_delta < 0), Decimal("0"))
        if gross == 0:
            return {
                "gross_positive": gross,
                "gross_losses": losses,
                "net": gross - losses,
                "best_share": None,
                "top5_share": None,
                "top10_share": None,
                "net_profit_status": "NET_PROFIT_NONPOSITIVE",
            }
        net = gross - losses
        return {
            "gross_positive": gross,
            "gross_losses": losses,
            "net": net,
            "best_share": positive[0] / gross,
            "top5_share": sum(positive[:5], Decimal("0")) / gross,
            "top10_share": sum(positive[:10], Decimal("0")) / gross,
            "net_profit_status": "POSITIVE" if net > 0 else "NET_PROFIT_NONPOSITIVE",
        }

    return {
        "granularity": granularity,
        "all_periods": calculation(windows),
        "complete_periods": calculation([item for item in windows if item.complete]),
        "period_count": len(windows),
        "complete_period_count": sum(item.complete for item in windows),
    }


def _concentration_warning(
    concentration: dict[str, Any],
    days: Sequence[WindowMetrics],
    weeks: Sequence[WindowMetrics],
    months: Sequence[WindowMetrics],
) -> str:
    conditions: list[bool] = []
    daily = concentration["daily"]["complete_periods"]
    weekly = concentration["weekly"]["complete_periods"]
    monthly = concentration["monthly"]["complete_periods"]
    if sum(item.complete for item in days) >= 30 and daily["best_share"] is not None:
        conditions.extend(
            [
                daily["best_share"] > Decimal("0.20"),
                daily["top5_share"] > Decimal("0.50"),
                daily["top10_share"] > Decimal("0.75"),
            ]
        )
    if sum(item.complete for item in weeks) >= 8 and weekly["best_share"] is not None:
        conditions.append(weekly["best_share"] > Decimal("0.35"))
    if sum(item.complete for item in months) >= 6 and monthly["best_share"] is not None:
        conditions.append(monthly["best_share"] > Decimal("0.50"))
    return "YES" if any(conditions) else ("NO" if conditions else "UNKNOWN")


def _longest_streak(blocks: Sequence[WindowMetrics], classification: str) -> dict[str, Any] | None:
    best: list[WindowMetrics] = []
    current: list[WindowMetrics] = []
    for item in blocks:
        if item.classification == classification:
            current.append(item)
            if len(current) > len(best):
                best = list(current)
        else:
            current.clear()
    if not best:
        return None
    return {
        "start": best[0].start,
        "end_exclusive": best[-1].end_exclusive,
        "blocks": len(best),
        "duration_hours": Decimal((best[-1].end_exclusive - best[0].start).total_seconds())
        / Decimal(3600),
    }


def _fingerprint(
    days: Sequence[WindowMetrics],
    months: Sequence[WindowMetrics],
    horizons: Sequence[HorizonMetrics],
) -> dict[str, Any]:
    by_horizon = {item.horizon_hours: item for item in horizons}
    full_months = [item for item in months if item.complete]
    best_month = max(
        full_months,
        key=lambda item: (item.mtm_delta, -item.start.timestamp()),
        default=None,
    )
    worst_month = min(
        full_months,
        key=lambda item: (item.mtm_delta, item.start.timestamp()),
        default=None,
    )
    day_horizon = by_horizon[24]
    best_day_block = max(
        day_horizon.blocks,
        key=lambda item: (
            item.capital_hour_return or Decimal("-Infinity"),
            -item.start.timestamp(),
        ),
        default=None,
    )
    return {
        "BEST_1D_CYCLES": max((item.completed_cycles for item in days if item.complete), default=0),
        "BEST_7D_CYCLES": max(
            (item.completed_cycles for item in by_horizon[168].blocks), default=0
        ),
        "BEST_30D_CYCLES": max(
            (item.completed_cycles for item in by_horizon[720].blocks), default=0
        ),
        "BEST_MONTH": best_month.start.strftime("%Y-%m") if best_month else None,
        "BEST_REGIME": best_day_block.classification if best_day_block else None,
        "WORST_MONTH": worst_month.start.strftime("%Y-%m") if worst_month else None,
        "LONGEST_HOT_STREAK": (day_horizon.longest_hot_streak or {"blocks": 0})["blocks"],
        "LONGEST_COLD_STREAK": (day_horizon.longest_cold_streak or {"blocks": 0})["blocks"],
        "HOT_PERIOD_COUNT": sum(item.classification == "HOT" for item in day_horizon.blocks),
    }


def _regime_contrasts(
    hourly: Sequence[WindowMetrics],
    tape: SerialTape,
    market_profile: MarketHourlyProfile | None,
) -> dict[str, Any]:
    event_ids = tape.events
    market_by_start = (
        {item.start: item for item in market_profile.hours} if market_profile is not None else {}
    )

    def event_count(item: WindowMetrics) -> int:
        return bisect_left(event_ids, _event(item.end_exclusive)) - bisect_left(
            event_ids, _event(item.start)
        )

    groups: dict[str, list[WindowMetrics]] = defaultdict(list)
    for item in hourly:
        groups[item.classification].append(item)
    contrasts: dict[str, Any] = {}
    for name in ("HOT", "COLD", "FAILURE", "NORMAL", "UNKNOWN"):
        items = groups[name]
        counts = [event_count(item) for item in items]
        market = [market_by_start[item.start] for item in items if item.start in market_by_start]
        contrasts[name] = {
            "hours": len(items),
            "median_trade_events_per_hour": median(counts) if counts else None,
            "median_cycles_per_hour": (
                median([item.completed_cycles for item in items]) if items else None
            ),
            "median_idle_hours": median([item.idle_hours for item in items]) if items else None,
            "median_base_volume": _median_market(market, "base_volume"),
            "median_quote_volume": _median_market(market, "quote_volume"),
            "median_price_range_ticks": _median_market(market, "range_ticks"),
            "median_one_tick_price_changes": _median_market(market, "one_tick_price_changes"),
            "spread": "UNKNOWN",
            "book_liquidity": "UNKNOWN",
            "fill_probability": "UNKNOWN",
        }
    return {
        "method": "DESCRIPTIVE_POST_REPLAY_NOT_A_TRADING_FILTER",
        "hourly_classification_contrast": contrasts,
        "market_feature_buckets": _market_feature_buckets(hourly, market_by_start),
    }


def _median_market(items: Sequence[MarketHour], field: str) -> Any:
    values = [getattr(item, field) for item in items if getattr(item, field) is not None]
    return median(values) if values else None


def _market_feature_buckets(
    hourly: Sequence[WindowMetrics], market: dict[datetime, MarketHour]
) -> dict[str, Any]:
    if not market:
        return {"status": "UNKNOWN_PROFILE_NOT_PROVIDED"}
    features = (
        "trade_records",
        "individual_trades",
        "base_volume",
        "quote_volume",
        "range_ticks",
        "one_tick_price_changes",
        "absolute_tick_movement",
    )
    result: dict[str, Any] = {}
    for feature in features:
        available = [
            (item, getattr(market[item.start], feature))
            for item in hourly
            if item.start in market and getattr(market[item.start], feature) is not None
        ]
        ordered = sorted(value for _, value in available)
        if not ordered:
            result[feature] = {"status": "UNKNOWN"}
            continue
        lower = ordered[(len(ordered) - 1) // 3]
        upper = ordered[(2 * (len(ordered) - 1)) // 3]
        groups: dict[str, list[WindowMetrics]] = defaultdict(list)
        for item, value in available:
            name = "LOW" if value <= lower else ("MEDIUM" if value <= upper else "HIGH")
            groups[name].append(item)
        result[feature] = {
            "status": "OBSERVED_DESCRIPTIVE",
            "lower_tercile_boundary": lower,
            "upper_tercile_boundary": upper,
            "buckets": {
                name: {
                    "hours": len(items),
                    "completed_cycles": sum(item.completed_cycles for item in items),
                    "realized_net_profit": sum(
                        (item.realized_net_profit for item in items), Decimal("0")
                    ),
                    "idle_hours": sum((item.idle_hours for item in items), Decimal("0")),
                    "classifications": {
                        classification: sum(item.classification == classification for item in items)
                        for classification in (
                            "HOT",
                            "NORMAL",
                            "COLD",
                            "FAILURE",
                            "UNKNOWN",
                        )
                    },
                }
                for name, items in sorted(groups.items())
            },
        }
    price_groups: dict[str, list[WindowMetrics]] = defaultdict(list)
    peg = Decimal("1")
    for item in hourly:
        market_hour = market.get(item.start)
        close = market_hour.close_price if market_hour is not None else None
        if close is None:
            price_groups["UNKNOWN"].append(item)
        else:
            name = "BELOW_PEG" if close < peg else ("ABOVE_PEG" if close > peg else "AT_PEG")
            price_groups[name].append(item)
    result["close_price_regime"] = {
        name: {
            "hours": len(items),
            "completed_cycles": sum(item.completed_cycles for item in items),
            "realized_net_profit": sum((item.realized_net_profit for item in items), Decimal("0")),
        }
        for name, items in sorted(price_groups.items())
    }
    return result


def _tick_distance_summary(cycles: Sequence[Any], tick_size: Decimal) -> dict[str, Any]:
    groups: dict[int, list[Any]] = defaultdict(list)
    for cycle in cycles:
        selection_tick = cycle.tick_at_selection or tick_size
        groups[int((cycle.high - cycle.low) / selection_tick)].append(cycle)
    return {
        str(distance): {
            "completed_cycles": len(items),
            "gross_edge_quote": sum(
                (item.quantity * (item.high - item.low) for item in items), Decimal("0")
            ),
            "fees_quote": sum(
                (item.buy_fee_quote + item.sell_fee_quote for item in items), Decimal("0")
            ),
        }
        for distance, items in sorted(groups.items())
    }


def _productivity_distribution(windows: Sequence[WindowMetrics]) -> dict[str, Any]:
    complete = [item for item in windows if item.complete]
    cycles = sorted(item.completed_cycles for item in complete)
    returns = sorted(
        item.capital_hour_return for item in complete if item.capital_hour_return is not None
    )
    return {
        "complete_periods": len(complete),
        "cycles": _percentiles(cycles),
        "capital_hour_return": _percentiles(returns),
        "best": (
            max(complete, key=lambda item: (item.completed_cycles, -item.start.timestamp())).start
            if complete
            else None
        ),
        "worst": (
            min(complete, key=lambda item: (item.completed_cycles, item.start.timestamp())).start
            if complete
            else None
        ),
    }


def _percentiles(values: Sequence[Any]) -> dict[str, Any]:
    if not values:
        return {key: None for key in ("min", "p10", "p50", "p90", "max")}

    def at(fraction: Decimal) -> Any:
        position = int((Decimal(len(values) - 1) * fraction).to_integral_value())
        return values[position]

    return {
        "min": values[0],
        "p10": at(Decimal("0.10")),
        "p50": at(Decimal("0.50")),
        "p90": at(Decimal("0.90")),
        "max": values[-1],
    }


def _calendar_group(
    windows: Sequence[WindowMetrics], key: Any, key_name: str
) -> tuple[dict[str, Any], ...]:
    groups: dict[Any, list[WindowMetrics]] = defaultdict(list)
    for item in windows:
        groups[key(item)].append(item)
    return tuple(
        {
            key_name: group,
            "periods": len(items),
            "completed_cycles": sum(item.completed_cycles for item in items),
            "realized_net_profit": sum((item.realized_net_profit for item in items), Decimal("0")),
            "mtm_delta": sum((item.mtm_delta for item in items), Decimal("0")),
            "idle_hours": sum((item.idle_hours for item in items), Decimal("0")),
        }
        for group, items in sorted(groups.items())
    )


def _replace_complete_windows(
    original: Sequence[WindowMetrics], classified: Sequence[WindowMetrics]
) -> list[WindowMetrics]:
    by_start = {item.start: item for item in classified}
    return [by_start.get(item.start, item) if item.complete else item for item in original]


def _fixed_intervals(
    start: datetime, end: datetime, duration: timedelta
) -> Iterable[tuple[datetime, datetime, bool]]:
    cursor = start
    while cursor < end:
        boundary = min(cursor + duration, end)
        yield cursor, boundary, boundary - cursor == duration
        cursor = boundary


def _calendar_intervals(
    start: datetime,
    end: datetime,
    period: Literal["day", "week", "month"],
) -> Iterable[tuple[datetime, datetime, bool]]:
    cursor = start
    while cursor < end:
        natural_start, natural_end = _natural_period(cursor, period)
        boundary = min(natural_end, end)
        yield cursor, boundary, cursor == natural_start and boundary == natural_end
        cursor = boundary


def _natural_period(
    value: datetime, period: Literal["day", "week", "month"]
) -> tuple[datetime, datetime]:
    value = require_utc(value)
    day_start = datetime(value.year, value.month, value.day, tzinfo=UTC)
    if period == "day":
        return day_start, day_start + timedelta(days=1)
    if period == "week":
        start = day_start - timedelta(days=day_start.weekday())
        return start, start + timedelta(days=7)
    start = datetime(value.year, value.month, 1, tzinfo=UTC)
    if value.month == 12:
        end = datetime(value.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(value.year, value.month + 1, 1, tzinfo=UTC)
    return start, end


def _period_label(value: datetime, period: str) -> str:
    if period == "month":
        return value.strftime("%Y-%m")
    if period == "week":
        iso = value.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return value.date().isoformat()


def _count_between(values: Sequence[int], start: int, end: int) -> int:
    return bisect_left(values, end) - bisect_left(values, start)


def _event(value: datetime) -> int:
    normalized = require_utc(value)
    micros = int(normalized.timestamp()) * MICROS_PER_SECOND + normalized.microsecond
    return micros * EVENT_ORDER_SCALE


def _hours(start_event: int, end_event: int) -> Decimal:
    micros = end_event // EVENT_ORDER_SCALE - start_event // EVENT_ORDER_SCALE
    return Decimal(micros) / Decimal(HOUR_MICROS)


__all__ = [
    "EPS_PROFIT",
    "EPS_RATE",
    "HORIZON_HOURS",
    "HorizonMetrics",
    "MarketProductivityRegime",
    "TemporalAnalysisContext",
    "TemporalReplayAnalysis",
    "WindowMetrics",
    "analyze_market_productivity_regime",
    "analyze_replay_temporally",
]
