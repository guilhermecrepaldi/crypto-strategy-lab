from __future__ import annotations

import csv
import io
import json
import zipfile
from array import array
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import mean, median
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.data import HistoryManifest

MICROS_PER_SECOND = 1_000_000
MICROS_PER_MINUTE = 60 * MICROS_PER_SECOND
EVENT_ORDER_SCALE = 4096
EVENT_UNITS_PER_DAY = 86_400 * MICROS_PER_SECOND * EVENT_ORDER_SCALE
TICK_SIZE = Decimal("0.0001")
TICK_SCALE = 10_000
DISTANCE_SETS = ((1,), (2,), (3,), (1, 2, 3))
LOOKBACK_MINUTES = (30, 60, 120, 240, 360, 720, 1_440)
WINDOW_MINUTES = (15, 30, 60, 120, 240, 360)
SCORES: tuple[Literal["FREQUENCY", "FREQUENCY_MARGIN"], ...] = (
    "FREQUENCY",
    "FREQUENCY_MARGIN",
)


class CandidateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    rank: int
    utc_date: date
    low: Decimal
    high: Decimal
    tick_distance: int
    spread_pct: Decimal
    gross_edge_bps: Decimal
    break_even_fee_per_leg: Decimal
    net_edge_scenarios: dict[str, Decimal]
    cycles: int
    cycle_p50_seconds: Decimal | None
    cycle_p90_seconds: Decimal | None
    cycle_p95_seconds: Decimal | None
    cycle_p99_seconds: Decimal | None
    max_cycle_seconds: Decimal | None
    low_visits: int
    high_visits: int
    low_trade_count: int
    high_trade_count: int
    volume_at_low: Decimal
    volume_at_high: Decimal


class DailyOracle(BaseModel):
    model_config = ConfigDict(frozen=True)

    utc_date: date
    best: CandidateResult | None
    top10: tuple[CandidateResult, ...]
    zero_reason: Literal["NONE", "NO_1_TO_3_TICK_CYCLE", "NO_ASCENDING_CYCLE"]


class CausalConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    lookback_minutes: int
    operating_minutes: int
    distances: tuple[int, ...]
    score: Literal["FREQUENCY", "FREQUENCY_MARGIN"]
    maker_rate_per_leg: Decimal = Decimal("0")

    @property
    def identity(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class DailyCausal(BaseModel):
    model_config = ConfigDict(frozen=True)

    utc_date: date
    cycles: int
    oracle_cycles: int
    capture_ratio: Decimal | None
    last_selected_low: Decimal | None
    last_selected_high: Decimal | None
    pending_reselection: bool
    open_position: bool
    active_low: Decimal | None
    active_high: Decimal | None
    pending_low: Decimal | None
    pending_high: Decimal | None
    marked_equity: Decimal


@dataclass
class PriceStats:
    trade_count: int = 0
    visit_count: int = 0
    volume: Decimal = Decimal("0")
    quote_volume: Decimal = Decimal("0")
    individual_trade_count: int = 0
    active_minutes: set[int] = field(default_factory=set)


@dataclass
class DayEvents:
    utc_date: date
    timestamps: array[int]
    prices: array[int]
    quantities: list[Decimal]
    stats: dict[int, PriceStats]


@dataclass
class CandidateTimeline:
    low_times: array[int]
    high_times: array[int]
    cycle_entries: array[int] = field(default_factory=lambda: array("q"))
    cycle_exits: array[int] = field(default_factory=lambda: array("q"))

    def build_cycles(self) -> None:
        low_index = 0
        high_index = 0
        after = -1
        while low_index < len(self.low_times):
            low_index = bisect_right(self.low_times, after, lo=low_index)
            if low_index >= len(self.low_times):
                break
            entry = self.low_times[low_index]
            high_index = bisect_right(self.high_times, entry, lo=high_index)
            if high_index >= len(self.high_times):
                break
            exit_at = self.high_times[high_index]
            self.cycle_entries.append(entry)
            self.cycle_exits.append(exit_at)
            after = exit_at
            low_index += 1
            high_index += 1

    def contained_cycles(self, start: int, end: int) -> int:
        return max(
            0,
            bisect_left(self.cycle_exits, end) - bisect_left(self.cycle_entries, start),
        )


@dataclass
class CausalState:
    cash: Decimal = Decimal("1000")
    active: tuple[int, int] | None = None
    pending: tuple[int, int] | None = None
    has_pending: bool = False
    entry_time: int | None = None
    quantity: Decimal = Decimal("0")
    cycles: list[tuple[int, int, int, int, Decimal]] = field(default_factory=list)
    last_selected: tuple[int, int] | None = None
    pending_seen_by_day: set[date] = field(default_factory=set)


def scan_campaign(
    manifest: HistoryManifest,
    *,
    start: date = date(2026, 1, 1),
    end: date = date(2026, 8, 1),
) -> dict[str, Any]:
    archive_by_date = {item.utc_date: Path(item.local_path) for item in manifest.archives}
    required = tuple(_dates(start - timedelta(days=1), end))
    missing = [item for item in required if item not in archive_by_date]
    if missing:
        raise ValueError(f"missing causal warmup/history days: {missing}")

    occurrences: dict[int, array[int]] = {}
    market_last: dict[date, int] = {}
    oracle: list[DailyOracle] = []
    price_maps: list[dict[str, Any]] = []
    for day in required:
        parsed = _load_day(archive_by_date[day], day)
        prior_timestamp: int | None = None
        ordinal = 0
        for timestamp, price in zip(parsed.timestamps, parsed.prices, strict=True):
            ordinal = ordinal + 1 if timestamp == prior_timestamp else 0
            if ordinal >= EVENT_ORDER_SCALE:
                raise ValueError("too many aggTrades share one timestamp for order encoding")
            occurrences.setdefault(price, array("q")).append(
                timestamp * EVENT_ORDER_SCALE + ordinal
            )
            prior_timestamp = timestamp
        market_last[day] = parsed.prices[-1]
        if day >= start:
            daily, price_map = _oracle_day(parsed)
            oracle.append(daily)
            price_maps.extend(price_map)

    timelines = _build_timelines(occurrences)
    oracle_counts = {item.utc_date: item.best.cycles if item.best else 0 for item in oracle}
    configs = tuple(
        CausalConfig(
            lookback_minutes=lookback,
            operating_minutes=window,
            distances=distances,
            score=score,
        )
        for lookback in LOOKBACK_MINUTES
        for window in WINDOW_MINUTES
        for distances in DISTANCE_SETS
        for score in SCORES
    )
    train_end = date(2026, 5, 1)
    train_results = [
        _evaluate_config(
            config,
            timelines,
            oracle_counts,
            market_last,
            start=start,
            end=train_end,
        )
        for config in configs
    ]
    winner = min(
        train_results,
        key=lambda item: (
            -Decimal(item["marked_return"]),
            -int(item["cycles"]),
            len(item["config"].distances),
            item["config"].identity,
        ),
    )
    frozen: CausalConfig = winner["config"]
    causal_full = _evaluate_config(
        frozen,
        timelines,
        oracle_counts,
        market_last,
        start=start,
        end=end,
        include_daily=True,
    )
    daily_causal: list[DailyCausal] = causal_full["daily"]
    splits = {
        "TRAIN": (date(2026, 1, 1), date(2026, 5, 1)),
        "VALIDATION": (date(2026, 5, 1), date(2026, 6, 16)),
        "OUT_OF_SAMPLE": (date(2026, 6, 16), date(2026, 8, 1)),
    }
    split_metrics = {
        name: _split_metrics(daily_causal, begin, finish)
        for name, (begin, finish) in splits.items()
    }
    oracle_metrics = _oracle_metrics(oracle)
    oracle_pattern = _oracle_classification(oracle_metrics)
    causal_classification = _causal_classification(oracle_pattern, split_metrics)
    payload: dict[str, Any] = {
        "schema_version": "daily-level-scanner-v1",
        "dataset_hash": manifest.dataset_hash,
        "symbol": manifest.symbol,
        "period": {"start": start.isoformat(), "end_exclusive": end.isoformat()},
        "tick_size": str(TICK_SIZE),
        "tick_size_status": "OBSERVED_GRID_COMPATIBLE_NOT_HISTORICAL_FILTER_PROOF",
        "oracle_method": "daily-constant-band-serial-low-then-high",
        "oracle": [item.model_dump(mode="json") for item in oracle],
        "oracle_metrics": oracle_metrics,
        "price_map": price_maps,
        "causal_grid_size": len(configs),
        "causal_train_results": [
            {**item, "config": item["config"].model_dump(mode="json")} for item in train_results
        ],
        "frozen_config": frozen.model_dump(mode="json"),
        "causal_daily": [item.model_dump(mode="json") for item in daily_causal],
        "split_metrics": split_metrics,
        "oracle_pattern": oracle_pattern,
        "causal_selector": causal_classification,
        "execution": "INCONCLUSIVE",
        "real_fills": "NOT_MEASURED",
        "real_capital_authorized": False,
        "protocol": {
            "distances": [1, 2, 3],
            "lookbacks_minutes": list(LOOKBACK_MINUTES),
            "operating_windows_minutes": list(WINDOW_MINUTES),
            "scores": list(SCORES),
            "primary_fee_per_leg": "0",
            "oracle_is_fixed_daily_reference_not_adaptive_upper_bound": True,
        },
    }
    payload["run_id"] = canonical_hash(
        {
            "dataset_hash": manifest.dataset_hash,
            "period": payload["period"],
            "protocol": payload["protocol"],
        }
    )
    return payload


def _load_day(path: Path, utc_date: date) -> DayEvents:
    timestamps = array("q")
    prices = array("i")
    quantities: list[Decimal] = []
    stats: dict[int, PriceStats] = {}
    previous_price: int | None = None
    with zipfile.ZipFile(path) as archive:
        names = [item for item in archive.namelist() if not item.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"invalid ZIP members: {path}")
        rows = csv.reader(io.TextIOWrapper(archive.open(names[0]), encoding="utf-8", newline=""))
        for row in rows:
            if not row or not row[0].isdigit():
                continue
            price_decimal = Decimal(row[1])
            scaled = price_decimal * TICK_SCALE
            if scaled != scaled.to_integral_value():
                raise ValueError(f"price off observed tick grid: {price_decimal}")
            price = int(scaled)
            quantity = Decimal(row[2])
            stamp = _stamp_micros(row[5])
            timestamps.append(stamp)
            prices.append(price)
            quantities.append(quantity)
            item = stats.setdefault(price, PriceStats())
            item.trade_count += 1
            item.volume += quantity
            item.quote_volume += quantity * price_decimal
            item.individual_trade_count += int(row[4]) - int(row[3]) + 1
            item.active_minutes.add(stamp // MICROS_PER_MINUTE)
            if price != previous_price:
                item.visit_count += 1
            previous_price = price
    if not timestamps:
        raise ValueError(f"empty archive: {path}")
    if _micros_to_datetime(timestamps[0]).date() != utc_date:
        raise ValueError(f"wrong archive date: {path}")
    return DayEvents(utc_date, timestamps, prices, quantities, stats)


def _oracle_day(day: DayEvents) -> tuple[DailyOracle, list[dict[str, Any]]]:
    states: dict[tuple[int, int], int | None] = {}
    durations: dict[tuple[int, int], list[int]] = {}
    cycles: Counter[tuple[int, int]] = Counter()
    for timestamp, price in zip(day.timestamps, day.prices, strict=True):
        for distance in (1, 2, 3):
            closing = (price - distance, distance)
            entry = states.get(closing)
            if entry is not None:
                cycles[closing] += 1
                durations.setdefault(closing, []).append(timestamp - entry)
                states[closing] = None
            opening = (price, distance)
            if opening not in states or states[opening] is None:
                states[opening] = timestamp
    ranked = sorted(
        (key for key, count in cycles.items() if count > 0),
        key=lambda key: (-cycles[key], -key[1], key[0], key[0] + key[1]),
    )
    top = tuple(
        _candidate_result(day, key, cycles[key], durations[key], rank)
        for rank, key in enumerate(ranked[:10], start=1)
    )
    zero_reason: Literal["NONE", "NO_1_TO_3_TICK_CYCLE", "NO_ASCENDING_CYCLE"] = "NONE"
    if not top:
        zero_reason = (
            "NO_ASCENDING_CYCLE"
            if not _has_any_ascending_path(day.prices)
            else "NO_1_TO_3_TICK_CYCLE"
        )
    price_map = [
        {
            "date": day.utc_date.isoformat(),
            "price": str(_price(price)),
            "trade_count": item.trade_count,
            "visit_count": item.visit_count,
            "volume": str(item.volume),
            "quote_volume": str(item.quote_volume),
            "individual_trade_count": item.individual_trade_count,
            "active_minutes": len(item.active_minutes),
        }
        for price, item in sorted(day.stats.items())
    ]
    return DailyOracle(
        utc_date=day.utc_date, best=top[0] if top else None, top10=top, zero_reason=zero_reason
    ), price_map


def _candidate_result(
    day: DayEvents,
    key: tuple[int, int],
    cycle_count: int,
    duration_micros: list[int],
    rank: int,
) -> CandidateResult:
    low_tick, distance = key
    high_tick = low_tick + distance
    seconds = sorted(Decimal(item) / MICROS_PER_SECOND for item in duration_micros)
    low_stats, high_stats = day.stats[low_tick], day.stats[high_tick]
    low, high = _price(low_tick), _price(high_tick)
    fee_scenarios = {
        "ZERO": Decimal("0"),
        "MAKER_A_0.2BP": Decimal("0.00002"),
        "MAKER_B_0.5BP": Decimal("0.00005"),
        "STRESS_1BP": Decimal("0.0001"),
    }
    return CandidateResult(
        rank=rank,
        utc_date=day.utc_date,
        low=low,
        high=high,
        tick_distance=distance,
        spread_pct=(high / low - 1) * 100,
        gross_edge_bps=(high / low - 1) * 10_000,
        break_even_fee_per_leg=(high - low) / (high + low),
        net_edge_scenarios={
            name: high * (1 - rate) / (low * (1 + rate)) - 1 for name, rate in fee_scenarios.items()
        },
        cycles=cycle_count,
        cycle_p50_seconds=_percentile(seconds, Decimal("0.50")),
        cycle_p90_seconds=_percentile(seconds, Decimal("0.90")),
        cycle_p95_seconds=_percentile(seconds, Decimal("0.95")),
        cycle_p99_seconds=_percentile(seconds, Decimal("0.99")),
        max_cycle_seconds=seconds[-1],
        low_visits=low_stats.visit_count,
        high_visits=high_stats.visit_count,
        low_trade_count=low_stats.trade_count,
        high_trade_count=high_stats.trade_count,
        volume_at_low=low_stats.volume,
        volume_at_high=high_stats.volume,
    )


def _build_timelines(
    occurrences: dict[int, array[int]],
) -> dict[tuple[int, int], CandidateTimeline]:
    result: dict[tuple[int, int], CandidateTimeline] = {}
    for low, low_times in occurrences.items():
        for distance in (1, 2, 3):
            high_times = occurrences.get(low + distance)
            if high_times is None:
                continue
            timeline = CandidateTimeline(low_times=low_times, high_times=high_times)
            timeline.build_cycles()
            result[(low, distance)] = timeline
    return result


def _evaluate_config(
    config: CausalConfig,
    timelines: dict[tuple[int, int], CandidateTimeline],
    oracle_counts: dict[date, int],
    market_last: dict[date, int],
    *,
    start: date,
    end: date,
    include_daily: bool = False,
) -> dict[str, Any]:
    state = CausalState()
    start_us = _datetime_to_micros(datetime.combine(start, time.min, tzinfo=UTC))
    end_us = _datetime_to_micros(datetime.combine(end, time.min, tzinfo=UTC))
    boundary = start_us * EVENT_ORDER_SCALE
    end_event = end_us * EVENT_ORDER_SCALE
    window_us = config.operating_minutes * MICROS_PER_MINUTE * EVENT_ORDER_SCALE
    lookback_us = config.lookback_minutes * MICROS_PER_MINUTE * EVENT_ORDER_SCALE
    last_by_day: dict[date, tuple[int, int] | None] = {}
    state_by_day: dict[
        date,
        tuple[
            tuple[int, int] | None,
            tuple[int, int] | None,
            bool,
            Decimal,
        ],
    ] = {}
    while boundary < end_event:
        selected = _select_candidate(
            config,
            timelines,
            start=boundary - lookback_us,
            end=boundary,
        )
        state.last_selected = selected
        boundary_day = _event_to_datetime(boundary).date()
        last_by_day[boundary_day] = selected
        if state.entry_time is None:
            state.active = selected
        else:
            state.pending = selected
            state.has_pending = True
            state.pending_seen_by_day.add(boundary_day)
        next_boundary = min(end_event, boundary + window_us)
        _advance_state(state, timelines, boundary, next_boundary)
        if next_boundary % EVENT_UNITS_PER_DAY == 0:
            completed_day = _event_to_datetime(next_boundary - 1).date()
            mark = _price(market_last[completed_day])
            equity = state.cash + (state.quantity * mark if state.entry_time is not None else 0)
            state_by_day[completed_day] = (
                state.active,
                state.pending,
                state.entry_time is not None,
                equity,
            )
        boundary = next_boundary
    marked = state.cash
    if state.entry_time is not None and state.active is not None:
        marked += state.quantity * _price(market_last[end - timedelta(days=1)])
    marked_return = marked / Decimal("1000") - 1
    result: dict[str, Any] = {
        "config": config,
        "cycles": len(state.cycles),
        "marked_return": str(marked_return),
        "open_position": state.entry_time is not None,
    }
    if include_daily:
        cycle_days = Counter(_event_to_datetime(item[1]).date() for item in state.cycles)
        daily: list[DailyCausal] = []
        for day in _dates(start, end):
            selected = last_by_day.get(day)
            active, pending, is_open, equity = state_by_day[day]
            oracle_value = oracle_counts.get(day, 0)
            causal_value = cycle_days[day]
            daily.append(
                DailyCausal(
                    utc_date=day,
                    cycles=causal_value,
                    oracle_cycles=oracle_value,
                    capture_ratio=(
                        Decimal(causal_value) / Decimal(oracle_value) if oracle_value else None
                    ),
                    last_selected_low=_price(selected[0]) if selected else None,
                    last_selected_high=(_price(selected[0] + selected[1]) if selected else None),
                    pending_reselection=day in state.pending_seen_by_day,
                    open_position=is_open,
                    active_low=_price(active[0]) if active else None,
                    active_high=_price(active[0] + active[1]) if active else None,
                    pending_low=_price(pending[0]) if pending else None,
                    pending_high=_price(pending[0] + pending[1]) if pending else None,
                    marked_equity=equity,
                )
            )
        result["daily"] = daily
        result["cycles_raw"] = state.cycles
    return result


def _select_candidate(
    config: CausalConfig,
    timelines: dict[tuple[int, int], CandidateTimeline],
    *,
    start: int,
    end: int,
) -> tuple[int, int] | None:
    ranked: list[tuple[Decimal, int, int, int]] = []
    for (low, distance), timeline in timelines.items():
        if distance not in config.distances:
            continue
        cycles = timeline.contained_cycles(start, end)
        if cycles <= 0:
            continue
        low_price, high_price = _price(low), _price(low + distance)
        edge = (
            high_price
            * (1 - config.maker_rate_per_leg)
            / (low_price * (1 + config.maker_rate_per_leg))
            - 1
        )
        if edge <= 0:
            continue
        score = Decimal(cycles) if config.score == "FREQUENCY" else Decimal(cycles) * edge
        ranked.append((score, cycles, distance, low))
    if not ranked:
        return None
    _, _, distance, low = max(ranked, key=lambda item: (item[0], item[1], item[2], -item[3]))
    return low, distance


def _advance_state(
    state: CausalState,
    timelines: dict[tuple[int, int], CandidateTimeline],
    start: int,
    end: int,
) -> None:
    cursor = start
    while state.active is not None:
        timeline = timelines[state.active]
        if state.entry_time is None:
            index = bisect_left(timeline.low_times, cursor)
            if index >= len(timeline.low_times) or timeline.low_times[index] >= end:
                return
            state.entry_time = timeline.low_times[index]
            low = _price(state.active[0])
            state.quantity = (state.cash / low // Decimal("0.01")) * Decimal("0.01")
            state.cash -= state.quantity * low
            cursor = state.entry_time + 1
        high_index = bisect_left(timeline.high_times, cursor)
        if high_index >= len(timeline.high_times) or timeline.high_times[high_index] >= end:
            return
        exit_at = timeline.high_times[high_index]
        low_tick, distance = state.active
        state.cash += state.quantity * _price(low_tick + distance)
        state.cycles.append((state.entry_time, exit_at, low_tick, distance, state.quantity))
        state.entry_time = None
        state.quantity = Decimal("0")
        if state.has_pending:
            state.active = state.pending
        state.pending = None
        state.has_pending = False
        cursor = exit_at + 1


def _oracle_metrics(values: list[DailyOracle]) -> dict[str, Any]:
    counts = [item.best.cycles if item.best else 0 for item in values]
    ordered = sorted(Decimal(item) for item in counts)
    zero_dates = [item.utc_date.isoformat() for item in values if item.best is None]
    return {
        "days": len(values),
        "minimum": min(counts),
        "minimum_dates": [
            item.utc_date.isoformat()
            for item in values
            if (item.best.cycles if item.best else 0) == min(counts)
        ],
        "maximum": max(counts),
        "maximum_dates": [
            item.utc_date.isoformat()
            for item in values
            if (item.best.cycles if item.best else 0) == max(counts)
        ],
        "average": str(mean(counts)),
        "median": str(median(counts)),
        **{
            f"p{int(q * 100)}": str(_percentile(ordered, Decimal(str(q))))
            for q in (0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
        },
        "days_zero": len(zero_dates),
        "zero_dates": zero_dates,
        **{
            f"days_ge_{limit}": sum(item >= limit for item in counts)
            for limit in (100, 250, 500, 1000, 1500, 2000, 3000, 4000)
        },
        "max_zero_streak": _max_zero_streak(counts),
    }


def _split_metrics(values: list[DailyCausal], start: date, end: date) -> dict[str, Any]:
    selected = [item for item in values if start <= item.utc_date < end]
    counts = [item.cycles for item in selected]
    ratios = [item.capture_ratio for item in selected if item.capture_ratio is not None]
    oracle_total = sum(item.oracle_cycles for item in selected)
    prior = [item for item in values if item.utc_date < start]
    starting_equity = prior[-1].marked_equity if prior else Decimal("1000")
    ending_equity = selected[-1].marked_equity
    return {
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "days": len(selected),
        "minimum": min(counts),
        "maximum": max(counts),
        "average": str(mean(counts)),
        "median": str(median(counts)),
        "days_zero": sum(item == 0 for item in counts),
        "starting_marked_equity": str(starting_equity),
        "ending_marked_equity": str(ending_equity),
        "marked_return": str(ending_equity / starting_equity - 1),
        "days_with_cycles_fraction": str(Decimal(sum(item > 0 for item in counts)) / len(counts)),
        "aggregate_capture_ratio": str(Decimal(sum(counts)) / oracle_total)
        if oracle_total
        else None,
        "median_daily_capture_ratio": str(median(ratios)) if ratios else None,
        "p10_daily_capture_ratio": str(_percentile(sorted(ratios), Decimal("0.10")))
        if ratios
        else None,
        "p25_daily_capture_ratio": str(_percentile(sorted(ratios), Decimal("0.25")))
        if ratios
        else None,
        "p75_daily_capture_ratio": str(_percentile(sorted(ratios), Decimal("0.75")))
        if ratios
        else None,
        "p90_daily_capture_ratio": str(_percentile(sorted(ratios), Decimal("0.90")))
        if ratios
        else None,
    }


def _oracle_classification(metrics: dict[str, Any]) -> str:
    if metrics["maximum"] == 0:
        return "ABSENT"
    if (
        (metrics["days"] - metrics["days_zero"]) / metrics["days"] >= 0.95
        and Decimal(metrics["median"]) >= 500
        and Decimal(metrics["p10"]) >= 100
        and metrics["max_zero_streak"] <= 2
    ):
        return "STRONG"
    return "WEAK"


def _causal_classification(oracle_pattern: str, splits: dict[str, dict[str, Any]]) -> str:
    if oracle_pattern != "STRONG":
        return "FAIL"
    for name in ("VALIDATION", "OUT_OF_SAMPLE"):
        item = splits[name]
        if (
            Decimal(item["days_with_cycles_fraction"]) < Decimal("0.80")
            or item["aggregate_capture_ratio"] is None
            or Decimal(item["aggregate_capture_ratio"]) < Decimal("0.25")
            or item["median_daily_capture_ratio"] is None
            or Decimal(item["median_daily_capture_ratio"]) < Decimal("0.10")
            or Decimal(item["marked_return"]) <= 0
        ):
            return "FAIL"
    return "PASS"


def _has_any_ascending_path(prices: array[int]) -> bool:
    minimum: int | None = None
    for price in prices:
        if minimum is not None and price > minimum:
            return True
        minimum = price if minimum is None else min(minimum, price)
    return False


def _percentile(values: list[Decimal], quantile: Decimal) -> Decimal | None:
    if not values:
        return None
    position = Decimal(len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def _max_zero_streak(values: list[int]) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if value == 0 else 0
        best = max(best, current)
    return best


def _price(ticks: int) -> Decimal:
    return Decimal(ticks) / TICK_SCALE


def _stamp_micros(raw: str) -> int:
    value = int(raw)
    return value if abs(value) >= 10**14 else value * 1_000


def _micros_to_datetime(value: int) -> datetime:
    seconds, micros = divmod(value, MICROS_PER_SECOND)
    return datetime.fromtimestamp(seconds, UTC).replace(microsecond=micros)


def _event_to_datetime(value: int) -> datetime:
    return _micros_to_datetime(value // EVENT_ORDER_SCALE)


def _datetime_to_micros(value: datetime) -> int:
    return int(value.timestamp()) * MICROS_PER_SECOND + value.microsecond


def _dates(start: date, end: date) -> tuple[date, ...]:
    return tuple(start + timedelta(days=index) for index in range((end - start).days))


def write_scanner_reports(payload: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": output_dir / "daily-level-scanner.json",
        "oracle": output_dir / "oracle-daily.csv",
        "top10": output_dir / "oracle-top10-daily.csv",
        "causal": output_dir / "causal-daily.csv",
        "comparison": output_dir / "selector-comparison.csv",
        "html": output_dir / "daily-level-scanner.html",
        "markdown": Path("docs/microstructure/DAILY_LEVEL_SCANNER.md"),
    }
    paths["summary"].write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    oracle_rows = [
        item["best"] or {"utc_date": item["utc_date"], "cycles": 0} for item in payload["oracle"]
    ]
    top_rows = [candidate for item in payload["oracle"] for candidate in item["top10"]]
    _dict_csv(paths["oracle"], oracle_rows)
    _dict_csv(paths["top10"], top_rows)
    _dict_csv(paths["causal"], payload["causal_daily"])
    _dict_csv(
        paths["comparison"],
        [
            {**item, "config": json.dumps(item["config"], sort_keys=True)}
            for item in payload["causal_train_results"]
        ],
    )
    paths["html"].write_text(_scanner_html(payload), encoding="utf-8")
    paths["markdown"].parent.mkdir(parents=True, exist_ok=True)
    paths["markdown"].write_text(_scanner_markdown(payload), encoding="utf-8")
    return paths


def _dict_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _scanner_html(payload: dict[str, Any]) -> str:
    metrics = payload["oracle_metrics"]
    daily = payload["causal_daily"]
    bars = "".join(
        f"<tr><td>{item['utc_date']}</td><td>{item['oracle_cycles']}</td><td>{item['cycles']}</td>"
        f"<td>{item['last_selected_low'] or ''}</td><td>{item['last_selected_high'] or ''}</td>"
        f"<td>{item['capture_ratio'] or ''}</td></tr>"
        for item in daily
    )
    return (
        "<!doctype html><meta charset='utf-8'><title>Daily level scanner</title>"
        "<style>body{font:14px system-ui;max-width:1200px;margin:auto;padding:32px;"
        "background:#f6f8f7}"
        "section{background:white;padding:18px;border-radius:12px;margin:16px 0;overflow:auto}"
        "table{border-collapse:collapse;width:100%}td,th{padding:6px;"
        "border-bottom:1px solid #ddd;text-align:right}"
        "td:first-child,th:first-child{text-align:left}</style>"
        f"<h1>{payload['symbol']} daily level scanner</h1>"
        f"<p>ORACLE_PATTERN={payload['oracle_pattern']} · "
        f"CAUSAL_SELECTOR={payload['causal_selector']} · EXECUTION=INCONCLUSIVE</p>"
        f"<section><b>Min</b> {metrics['minimum']} · <b>Max</b> {metrics['maximum']} · "
        f"<b>Mean</b> {metrics['average']} · <b>Median</b> {metrics['median']} · "
        f"<b>Zero days</b> {metrics['days_zero']}</section>"
        "<section><h2>Oracle vs causal, selected LOW/HIGH and daily distribution</h2><table>"
        "<tr><th>Date</th><th>Oracle</th><th>Causal</th><th>LOW</th><th>HIGH</th><th>Ratio</th></tr>"
        f"{bars}</table></section>"
    )


def _scanner_markdown(payload: dict[str, Any]) -> str:
    metrics = payload["oracle_metrics"]
    frozen = payload["frozen_config"]
    return "\n".join(
        [
            f"# {payload['symbol']} daily level scanner",
            "",
            f"Run `{payload['run_id']}` used dataset `{payload['dataset_hash']}` over "
            f"`{payload['period']['start']}` to `{payload['period']['end_exclusive']}`.",
            "",
            "## ORACLE daily constant-band reference",
            "",
            f"- Minimum: `{metrics['minimum']}`",
            f"- Maximum: `{metrics['maximum']}`",
            f"- Mean: `{metrics['average']}`",
            f"- Median: `{metrics['median']}`",
            f"- Zero days: `{metrics['days_zero']}`",
            f"- Classification: **{payload['oracle_pattern']}**",
            "",
            "## Frozen causal selector",
            "",
            f"- Lookback: `{frozen['lookback_minutes']} minutes`",
            f"- Operating window: `{frozen['operating_minutes']} minutes`",
            f"- Distances: `{frozen['distances']}`",
            f"- Score: `{frozen['score']}`",
            f"- Classification: **{payload['causal_selector']}**",
            "",
            "ORACLE sees its complete day and is only a fixed-band retrospective reference. "
            "The causal selector uses `[decision-lookback, decision)` and preserves an open "
            "position and its original target across reselection boundaries. The comparison ratio "
            "is not clamped and can exceed one because the causal policy adapts intraday.",
            "",
            "`EXECUTION=INCONCLUSIVE`: aggTrades prove observed price paths, not queue position or "
            "fills. No real capital, account, Testnet, order or credential was used.",
            "",
        ]
    )
