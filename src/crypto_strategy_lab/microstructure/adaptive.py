from __future__ import annotations

import csv
import json
from array import array
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import mean, median
from typing import Any, Literal

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.data import HistoryManifest
from crypto_strategy_lab.microstructure.level_scanner import (
    EVENT_ORDER_SCALE,
    EVENT_UNITS_PER_DAY,
    MICROS_PER_MINUTE,
    CandidateTimeline,
    CausalState,
    _advance_state,
    _build_timelines,
    _datetime_to_micros,
    _event_to_datetime,
    _load_day,
    _price,
)


@dataclass(frozen=True)
class AdaptiveConfig:
    lookback_minutes: int
    profile: Literal["MODERATE", "STRICT"]
    confirmation_minutes: int
    cooldown_minutes: int
    advantage: Decimal

    @property
    def identity(self) -> str:
        return canonical_hash(self.__dict__)


@dataclass
class AdaptiveResult:
    config: AdaptiveConfig
    state: CausalState
    changes: list[dict[str, Any]] = field(default_factory=list)
    idle_candidates: int = 0
    idle_recoveries: int = 0
    analysis_count: int = 0
    snapshots: dict[date, Decimal] = field(default_factory=dict)


def run_adaptive_campaign(
    manifest: HistoryManifest,
    scanner_payload: dict[str, Any],
    *,
    start: date = date(2026, 1, 1),
    end: date = date(2026, 8, 1),
) -> dict[str, Any]:
    archive_by_date = {item.utc_date: Path(item.local_path) for item in manifest.archives}
    occurrences: dict[int, array[int]] = {}
    price_rows: list[dict[str, Any]] = []
    market_last: dict[date, int] = {}
    for day_offset in range(-1, (end - start).days):
        day = start + timedelta(days=day_offset)
        parsed = _load_day(archive_by_date[day], day)
        prior: int | None = None
        ordinal = 0
        for timestamp, price in zip(parsed.timestamps, parsed.prices, strict=True):
            ordinal = ordinal + 1 if timestamp == prior else 0
            occurrences.setdefault(price, array("q")).append(
                timestamp * EVENT_ORDER_SCALE + ordinal
            )
            prior = timestamp
        market_last[day] = parsed.prices[-1]
        if day >= start:
            for price, stats in parsed.stats.items():
                price_rows.append(
                    {
                        "date": day.isoformat(),
                        "month": day.strftime("%Y-%m"),
                        "price": str(_price(price)),
                        "aggtrade_count": stats.trade_count,
                        "individual_trade_count": stats.individual_trade_count,
                        "visit_count": stats.visit_count,
                        "base_volume": str(stats.volume),
                        "quote_volume": str(stats.quote_volume),
                        "active_minutes": len(stats.active_minutes),
                    }
                )
    timelines = _build_timelines(occurrences)
    train_end = date(2026, 5, 1)
    profiles: tuple[Literal["MODERATE", "STRICT"], ...] = ("MODERATE", "STRICT")
    configs = tuple(
        AdaptiveConfig(lookback, profile, confirmation, cooldown, advantage)
        for lookback in (240, 720, 1440)
        for profile in profiles
        for confirmation in (15, 30)
        for cooldown in (60, 240)
        for advantage in (Decimal("0.25"), Decimal("1"))
    )
    always_train = {
        lookback: _always_best(timelines, market_last, start, train_end, lookback)
        for lookback in (240, 720, 1440)
    }
    train_results = [
        _run_idle(config, timelines, market_last, start, train_end) for config in configs
    ]
    eligible = [
        item
        for item in train_results
        if len(item.state.cycles)
        >= Decimal("0.80") * len(always_train[item.config.lookback_minutes].state.cycles)
        and _ending_equity(item, market_last, train_end) > Decimal("1000")
    ]
    winner = min(
        eligible or train_results,
        key=lambda item: (
            0 if item in eligible else 1,
            len(item.changes),
            -len(item.state.cycles),
            -_ending_equity(item, market_last, train_end),
            item.config.identity,
        ),
    )
    adaptive = _run_idle(winner.config, timelines, market_last, start, end)
    always = _always_best(timelines, market_last, start, end, winner.config.lookback_minutes)
    static = _static(timelines, market_last, start, end, winner.config.lookback_minutes)
    oracle_by_day = {
        date.fromisoformat(item["utc_date"]): (item["best"] or {}).get("cycles", 0)
        for item in scanner_payload["oracle"]
    }
    daily = _daily_rows(adaptive, always, static, oracle_by_day, start, end)
    split_metrics = {
        name: _adaptive_split(daily, begin, finish)
        for name, (begin, finish) in {
            "TRAIN": (start, train_end),
            "VALIDATION": (train_end, date(2026, 6, 16)),
            "OUT_OF_SAMPLE": (date(2026, 6, 16), end),
        }.items()
    }
    adaptive_pattern = _adaptive_gate(split_metrics)
    anti_thrashing = _thrashing_gate(adaptive, always, daily)
    monthly_price, monthly_cycles, monthly_regimes = _monthly_profiles(price_rows, scanner_payload)
    return {
        "schema_version": "adaptive-idle-engine-v1",
        "dataset_hash": manifest.dataset_hash,
        "period": {"start": start.isoformat(), "end_exclusive": end.isoformat()},
        "grid_size": len(configs),
        "frozen_config": {**winner.config.__dict__, "advantage": str(winner.config.advantage)},
        "train_selection_satisfied_80pct": bool(eligible),
        "daily": daily,
        "reselections": adaptive.changes,
        "split_metrics": split_metrics,
        "monthly_price_profile": monthly_price,
        "monthly_cycle_profile": monthly_cycles,
        "monthly_regime_profile": monthly_regimes,
        "comparators": {
            "STATIC_LEVELS": _result_summary(static, market_last, end),
            "ALWAYS_BEST": _result_summary(always, market_last, end),
            "IDLE_TRIGGERED": _result_summary(adaptive, market_last, end),
        },
        "adaptive_pattern": adaptive_pattern,
        "anti_thrashing": anti_thrashing,
        "execution": "INCONCLUSIVE",
        "real_fills": "NOT_MEASURED",
        "real_capital_authorized": False,
        "run_id": canonical_hash(
            {
                "dataset": manifest.dataset_hash,
                "strategy": "IDLE_TRIGGERED-v1",
                "grid": [item.__dict__ for item in configs],
            }
        ),
    }


def _run_idle(
    config: AdaptiveConfig,
    timelines: dict[tuple[int, int], CandidateTimeline],
    marks: dict[date, int],
    start: date,
    end: date,
) -> AdaptiveResult:
    state = CausalState()
    result = AdaptiveResult(config=config, state=state)
    now = _datetime_to_micros(datetime.combine(start, time.min, tzinfo=UTC)) * EVENT_ORDER_SCALE
    finish = _datetime_to_micros(datetime.combine(end, time.min, tzinfo=UTC)) * EVENT_ORDER_SCALE
    step = 5 * MICROS_PER_MINUTE * EVENT_ORDER_SCALE
    lookback = config.lookback_minutes * MICROS_PER_MINUTE * EVENT_ORDER_SCALE
    active = _best(timelines, now - lookback, now)
    state.active = active
    reference = _reference(timelines[active], now - lookback, now) if active else None
    activated = now
    last_change = now - config.cooldown_minutes * MICROS_PER_MINUTE * EVENT_ORDER_SCALE
    idle_since: int | None = None
    while now < finish:
        next_at = min(now + step, finish)
        before_cycles = len(state.cycles)
        _advance_state(state, timelines, now, next_at)
        if next_at % EVENT_UNITS_PER_DAY == 0:
            day = _event_to_datetime(next_at - 1).date()
            result.snapshots[day] = _equity(state, marks[day])
        if len(state.cycles) > before_cycles:
            idle_since = None
        if state.entry_time is not None or state.active is None or reference is None:
            now = next_at
            continue
        recent = lookback // 4
        timeline = timelines[state.active]
        recent_cycles = timeline.contained_cycles(next_at - recent, next_at)
        recent_lows = _count(timeline.low_times, next_at - recent, next_at)
        alpha = Decimal("0.25") if config.profile == "MODERATE" else Decimal("0.10")
        multiplier = 2 if config.profile == "MODERATE" else 4
        free_since = max(state.cycles[-1][1] if state.cycles else activated, activated)
        idle = (
            next_at - free_since
            > multiplier * max(reference[2], 5 * MICROS_PER_MINUTE * EVENT_ORDER_SCALE)
            and Decimal(recent_cycles) / recent <= alpha * reference[0]
            and Decimal(recent_lows) / recent <= alpha * reference[1]
        )
        if not idle:
            if idle_since is not None:
                result.idle_recoveries += 1
            idle_since = None
            now = next_at
            continue
        if idle_since is None:
            idle_since = next_at
            result.idle_candidates += 1
        confirmed = (
            next_at - idle_since
            >= config.confirmation_minutes * MICROS_PER_MINUTE * EVENT_ORDER_SCALE
        )
        cooled = (
            next_at - last_change >= config.cooldown_minutes * MICROS_PER_MINUTE * EVENT_ORDER_SCALE
        )
        if confirmed and cooled:
            result.analysis_count += 1
            replacement = _best(
                timelines,
                next_at - lookback,
                next_at,
                current=state.active,
                advantage=config.advantage,
            )
            if replacement is not None and replacement != state.active:
                old = state.active
                state.active = replacement
                reference = _reference(timelines[replacement], next_at - lookback, next_at)
                activated = next_at
                last_change = next_at
                idle_since = None
                result.changes.append(
                    {
                        "timestamp": _event_to_datetime(next_at).isoformat(),
                        "old_low": str(_price(old[0])),
                        "old_high": str(_price(old[0] + old[1])),
                        "new_low": str(_price(replacement[0])),
                        "new_high": str(_price(replacement[0] + replacement[1])),
                        "old_distance": old[1],
                        "new_distance": replacement[1],
                    }
                )
        now = next_at
    return result


def _best(
    timelines: dict[tuple[int, int], CandidateTimeline],
    start: int,
    end: int,
    *,
    current: tuple[int, int] | None = None,
    advantage: Decimal = Decimal("0"),
) -> tuple[int, int] | None:
    candidates: list[tuple[Decimal, int, int, int]] = []
    current_score = Decimal("0")
    for (low, distance), timeline in timelines.items():
        reference = _reference(timeline, start, end)
        if reference is None:
            continue
        cycles = timeline.contained_cycles(start, end)
        edge = _price(low + distance) / _price(low) - 1
        score = Decimal(cycles) * edge
        if (low, distance) == current:
            current_score = score
        candidates.append((score, cycles, distance, low))
    if not candidates:
        return None
    ordered = sorted(
        candidates,
        key=lambda item: (
            -item[0],
            -item[1],
            abs(item[3] - current[0]) if current else 0,
            item[3],
            item[3] + item[2],
        ),
    )
    if current is not None:
        same_distance_near = [
            x for x in ordered if x[2] == current[1] and abs(x[3] - current[0]) <= 3
        ]
        same_distance = [x for x in ordered if x[2] == current[1]]
        ordered = same_distance_near or same_distance or ordered
    score, cycles, distance, low = ordered[0]
    if current is not None:
        current_edge = _price(current[0] + current[1]) / _price(current[0]) - 1
        if score < (1 + advantage) * current_score or score - current_score < current_edge:
            return current
    return low, distance


def _reference(
    timeline: CandidateTimeline, start: int, end: int
) -> tuple[Decimal, Decimal, int] | None:
    cycles = timeline.contained_cycles(start, end)
    lows = _count(timeline.low_times, start, end)
    highs = timeline.high_times[
        bisect_left(timeline.high_times, start) : bisect_left(timeline.high_times, end)
    ]
    waits = []
    for high in highs:
        index = bisect_left(timeline.low_times, high + 1)
        if index < len(timeline.low_times) and timeline.low_times[index] < end:
            waits.append(timeline.low_times[index] - high)
    if cycles < 20 or len(waits) < 10:
        return None
    waits.sort()
    p95 = waits[int((len(waits) - 1) * 0.95)]
    span = Decimal(end - start)
    return Decimal(cycles) / span, Decimal(lows) / span, p95


def _count(values: array[int], start: int, end: int) -> int:
    return bisect_left(values, end) - bisect_left(values, start)


def _always_best(
    timelines: dict[tuple[int, int], CandidateTimeline],
    marks: dict[date, int],
    start: date,
    end: date,
    lookback: int,
) -> AdaptiveResult:
    config = AdaptiveConfig(lookback, "MODERATE", 15, 60, Decimal("0"))
    state = CausalState()
    result = AdaptiveResult(config, state)
    now = _datetime_to_micros(datetime.combine(start, time.min, tzinfo=UTC)) * EVENT_ORDER_SCALE
    finish = _datetime_to_micros(datetime.combine(end, time.min, tzinfo=UTC)) * EVENT_ORDER_SCALE
    step = 15 * MICROS_PER_MINUTE * EVENT_ORDER_SCALE
    lb = lookback * MICROS_PER_MINUTE * EVENT_ORDER_SCALE
    while now < finish:
        selected = _best(timelines, now - lb, now)
        if state.entry_time is None:
            if selected != state.active and state.active is not None:
                result.changes.append({"timestamp": _event_to_datetime(now).isoformat()})
            state.active = selected
        else:
            state.pending = selected
            state.has_pending = True
        next_at = min(now + step, finish)
        _advance_state(state, timelines, now, next_at)
        if next_at % EVENT_UNITS_PER_DAY == 0:
            day = _event_to_datetime(next_at - 1).date()
            result.snapshots[day] = _equity(state, marks[day])
        now = next_at
    return result


def _static(
    timelines: dict[tuple[int, int], CandidateTimeline],
    marks: dict[date, int],
    start: date,
    end: date,
    lookback: int,
) -> AdaptiveResult:
    config = AdaptiveConfig(lookback, "MODERATE", 15, 60, Decimal("0"))
    state = CausalState()
    result = AdaptiveResult(config, state)
    begin = _datetime_to_micros(datetime.combine(start, time.min, tzinfo=UTC)) * EVENT_ORDER_SCALE
    finish = _datetime_to_micros(datetime.combine(end, time.min, tzinfo=UTC)) * EVENT_ORDER_SCALE
    state.active = _best(timelines, begin - lookback * MICROS_PER_MINUTE * EVENT_ORDER_SCALE, begin)
    cursor = begin
    while cursor < finish:
        next_at = min(cursor + EVENT_UNITS_PER_DAY, finish)
        _advance_state(state, timelines, cursor, next_at)
        day = _event_to_datetime(next_at - 1).date()
        result.snapshots[day] = _equity(state, marks[day])
        cursor = next_at
    return result


def _equity(state: CausalState, mark_tick: int) -> Decimal:
    return state.cash + (state.quantity * _price(mark_tick) if state.entry_time is not None else 0)


def _ending_equity(result: AdaptiveResult, marks: dict[date, int], end: date) -> Decimal:
    return _equity(result.state, marks[end - timedelta(days=1)])


def _daily_rows(
    adaptive: AdaptiveResult,
    always: AdaptiveResult,
    static: AdaptiveResult,
    oracle: dict[date, int],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    counts = {
        name: Counter(_event_to_datetime(cycle[1]).date() for cycle in item.state.cycles)
        for name, item in (("idle", adaptive), ("always", always), ("static", static))
    }
    changes = Counter(date.fromisoformat(item["timestamp"][:10]) for item in adaptive.changes)
    return [
        {
            "date": day.isoformat(),
            "oracle_cycles": oracle.get(day, 0),
            "static_cycles": counts["static"][day],
            "always_best_cycles": counts["always"][day],
            "idle_triggered_cycles": counts["idle"][day],
            "reselection_count": changes[day],
            "marked_equity": str(adaptive.snapshots[day]),
        }
        for day in (start + timedelta(days=i) for i in range((end - start).days))
    ]


def _adaptive_split(rows: list[dict[str, Any]], start: date, end: date) -> dict[str, Any]:
    selected = [row for row in rows if start <= date.fromisoformat(row["date"]) < end]
    idle = [row["idle_triggered_cycles"] for row in selected]
    always = sum(row["always_best_cycles"] for row in selected)
    previous = [row for row in rows if date.fromisoformat(row["date"]) < start]
    starting_equity = Decimal(previous[-1]["marked_equity"]) if previous else Decimal("1000")
    ending_equity = Decimal(selected[-1]["marked_equity"])
    active_blocks = sum(
        all(value > 0 for value in idle[offset : offset + 7])
        for offset in range(0, len(idle) - 6, 7)
    )
    return {
        "days": len(selected),
        "cycles": sum(idle),
        "minimum": min(idle),
        "maximum": max(idle),
        "mean": str(mean(idle)),
        "median": str(median(idle)),
        "zero_days": sum(value == 0 for value in idle),
        "active_day_fraction": str(Decimal(sum(value > 0 for value in idle)) / len(idle)),
        "always_best_cycles": always,
        "throughput_ratio": str(Decimal(sum(idle)) / always) if always else None,
        "reselection_count": sum(row["reselection_count"] for row in selected),
        "ending_equity": selected[-1]["marked_equity"],
        "marked_return": str(ending_equity / starting_equity - 1),
        "non_overlapping_active_7d_blocks": active_blocks,
    }


def _adaptive_gate(splits: dict[str, dict[str, Any]]) -> str:
    for name in ("VALIDATION", "OUT_OF_SAMPLE"):
        item = splits[name]
        if (
            Decimal(item["active_day_fraction"]) < Decimal("0.80")
            or item["throughput_ratio"] is None
            or Decimal(item["throughput_ratio"]) < Decimal("0.80")
            or Decimal(item["marked_return"]) <= 0
            or item["non_overlapping_active_7d_blocks"] < 2
        ):
            return "FAIL"
    return "PASS"


def _thrashing_gate(
    adaptive: AdaptiveResult, always: AdaptiveResult, rows: list[dict[str, Any]]
) -> str:
    changes = sorted(row["reselection_count"] for row in rows)
    p95 = changes[int((len(changes) - 1) * 0.95)]
    relative_ok = (
        len(adaptive.changes) <= Decimal("0.5") * len(always.changes)
        if always.changes
        else not adaptive.changes
    )
    return "PASS" if relative_ok and median(changes) <= 4 and p95 <= 8 else "FAIL"


def _result_summary(result: AdaptiveResult, marks: dict[date, int], end: date) -> dict[str, Any]:
    return {
        "cycles": len(result.state.cycles),
        "level_changes": len(result.changes),
        "ending_equity": str(_ending_equity(result, marks, end)),
        "idle_candidates": result.idle_candidates,
        "idle_recoveries": result.idle_recoveries,
        "analysis_count": result.analysis_count,
    }


def _monthly_profiles(
    price_rows: list[dict[str, Any]], scanner: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], dict[str, Decimal | int]] = defaultdict(
        lambda: {
            "aggtrade_count": 0,
            "individual_trade_count": 0,
            "visit_count": 0,
            "base_volume": Decimal("0"),
            "quote_volume": Decimal("0"),
            "active_minutes": 0,
        }
    )
    for row in price_rows:
        item = grouped[(row["month"], row["price"])]
        for key in ("aggtrade_count", "individual_trade_count", "visit_count", "active_minutes"):
            item[key] += int(row[key])
        for key in ("base_volume", "quote_volume"):
            item[key] += Decimal(row[key])
    price_profile = [
        {
            "month": month,
            "price": price,
            **{k: str(v) if isinstance(v, Decimal) else v for k, v in values.items()},
        }
        for (month, price), values in sorted(grouped.items())
    ]
    pair_totals: Counter[tuple[str, str, str, int]] = Counter()
    for day in scanner["oracle"]:
        month = day["utc_date"][:7]
        for candidate in day["top10"]:
            pair_totals[
                (month, candidate["low"], candidate["high"], candidate["tick_distance"])
            ] += int(candidate["cycles"])
    cycle_profile = [
        {"month": key[0], "low": key[1], "high": key[2], "tick_distance": key[3], "cycles": cycles}
        for key, cycles in sorted(pair_totals.items(), key=lambda item: (item[0][0], -item[1]))
    ]
    train_prices = sorted(Decimal(row["price"]) for row in price_rows if row["date"] < "2026-05-01")
    q1, q2 = train_prices[len(train_prices) // 3], train_prices[2 * len(train_prices) // 3]
    regimes: dict[tuple[str, str], dict[str, Decimal | int]] = defaultdict(
        lambda: {"aggtrade_count": 0, "base_volume": Decimal("0")}
    )
    for row in price_rows:
        value = Decimal(row["price"])
        regime = "LOW_REGIME" if value <= q1 else "CENTRAL_REGIME" if value <= q2 else "HIGH_REGIME"
        target = regimes[(row["month"], regime)]
        target["aggtrade_count"] += int(row["aggtrade_count"])
        target["base_volume"] += Decimal(row["base_volume"])
    regime_profile = [
        {
            "month": month,
            "regime": regime,
            "train_q1": str(q1),
            "train_q2": str(q2),
            **{
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in data.items()
            },
        }
        for (month, regime), data in sorted(regimes.items())
    ]
    return price_profile, cycle_profile, regime_profile


def write_adaptive_reports(payload: dict[str, Any], root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    mapping = {
        "summary": root / "adaptive-summary.json",
        "prices": root / "monthly-price-profile.csv",
        "regimes": root / "monthly-regime-profile.csv",
        "cycles": root / "monthly-cycle-profile.csv",
        "daily": root / "adaptive-daily.csv",
        "reselections": root / "reselections.csv",
        "html": root / "adaptive-report.html",
        "markdown": Path("docs/microstructure/ADAPTIVE_IDLE_ENGINE.md"),
    }
    mapping["summary"].write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    for key, rows in (
        ("prices", payload["monthly_price_profile"]),
        ("regimes", payload["monthly_regime_profile"]),
        ("cycles", payload["monthly_cycle_profile"]),
        ("daily", payload["daily"]),
        ("reselections", payload["reselections"]),
    ):
        _write_csv(mapping[key], rows)
    mapping["markdown"].parent.mkdir(parents=True, exist_ok=True)
    markdown = "\n".join(
        [
            "# Adaptive idle engine",
            "",
            f"Run `{payload['run_id']}`.",
            "",
            f"- ADAPTIVE_PATTERN: **{payload['adaptive_pattern']}**",
            f"- ANTI_THRASHING: **{payload['anti_thrashing']}**",
            "- EXECUTION: `INCONCLUSIVE`",
            "",
            "The engine stays on current levels until statistically degraded while flat. "
            "An open position always retains its original HIGH.",
            "",
        ]
    )
    mapping["markdown"].write_text(markdown, encoding="utf-8")
    mapping["html"].write_text(_html(payload), encoding="utf-8")
    return mapping


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)


def _html(payload: dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{x['date']}</td><td>{x['static_cycles']}</td><td>{x['always_best_cycles']}</td><td>{x['idle_triggered_cycles']}</td><td>{x['reselection_count']}</td></tr>"
        for x in payload["daily"]
    )
    return (
        "<!doctype html><meta charset='utf-8'><style>"
        "body{font:14px system-ui;max-width:1100px;margin:auto}"
        "table{width:100%;border-collapse:collapse}"
        "td,th{padding:6px;border-bottom:1px solid #ddd;text-align:right}</style>"
        "<h1>Adaptive idle engine</h1>"
        f"<p>ADAPTIVE_PATTERN={payload['adaptive_pattern']} · "
        f"ANTI_THRASHING={payload['anti_thrashing']} · EXECUTION=INCONCLUSIVE</p>"
        "<table><tr><th>Date</th><th>Static</th><th>Always best</th>"
        f"<th>Idle triggered</th><th>Changes</th></tr>{rows}</table>"
    )
