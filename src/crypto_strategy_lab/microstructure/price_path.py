from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.data import parse_archive
from crypto_strategy_lab.microstructure.models import TradeEvent

CapitalState = tuple[Decimal, Decimal, Decimal, Decimal]
CapitalCacheKey = tuple[Decimal, bool, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]
CapitalCache = dict[CapitalCacheKey, list[CapitalState]]


class PricePathIntegrityError(ValueError):
    pass


class FeeScenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    maker_rate_per_leg: Decimal = Field(ge=0)
    source: str = "EXPLICIT_BACKTEST_ASSUMPTION_NOT_ACCOUNT_VERIFIED"


DEFAULT_FEE_SCENARIOS = (
    FeeScenario(name="SCENARIO_ZERO_MAKER", maker_rate_per_leg=Decimal("0")),
    FeeScenario(name="SCENARIO_EFFECTIVE_MAKER_A", maker_rate_per_leg=Decimal("0.00002")),
    FeeScenario(name="SCENARIO_EFFECTIVE_MAKER_B", maker_rate_per_leg=Decimal("0.00005")),
    FeeScenario(name="SCENARIO_STRESS_MAKER_1BP", maker_rate_per_leg=Decimal("0.0001")),
)

DEFAULT_CAPITAL_SCENARIOS = tuple(
    Decimal(value) for value in ("100", "500", "1000", "2500", "5000", "10000")
)


class PricePathCycle(BaseModel):
    model_config = ConfigDict(frozen=True)

    cycle_number: int
    entry_timestamp: datetime
    exit_timestamp: datetime
    holding_seconds: Decimal
    entry_trade_id: int
    exit_trade_id: int


class Distribution(BaseModel):
    model_config = ConfigDict(frozen=True)

    count: int
    mean: Decimal | None
    minimum: Decimal | None
    p10: Decimal | None
    p25: Decimal | None
    p50: Decimal | None
    p75: Decimal | None
    p90: Decimal | None
    p95: Decimal | None
    p99: Decimal | None
    maximum: Decimal | None


class CapitalOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    initial_capital: Decimal
    fee_scenario: FeeScenario
    completed_cycles: int
    gross_edge_fraction: Decimal
    gross_edge_bps: Decimal
    break_even_fee_per_leg: Decimal
    net_edge_fraction_before_rounding: Decimal
    economic_status: Literal["POSITIVE", "BREAK_EVEN", "ECONOMIC_NO_GO_FOR_THIS_FEE_SCENARIO"]
    capital_at_period_start_fixed_lot: Decimal
    capital_at_period_start_compounding: Decimal
    final_capital_fixed_lot: Decimal
    final_capital_compounding: Decimal
    gross_profit_fixed_lot: Decimal
    gross_profit_compounding: Decimal
    fees_fixed_lot: Decimal
    fees_compounding: Decimal
    net_profit_fixed_lot: Decimal
    net_profit_compounding: Decimal
    return_fixed_lot: Decimal
    return_compounding: Decimal
    dust_fixed_lot: Decimal
    dust_compounding: Decimal


class OpenPosition(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["OPEN_AT_PERIOD_END", "OPEN_AT_DATASET_END"]
    entry_price: Decimal
    entry_time: datetime
    entry_trade_id: int
    holding_age_seconds: Decimal
    last_market_price: Decimal
    last_market_timestamp: datetime
    last_market_stale_seconds: Decimal
    mark_to_market_fraction: Decimal
    primary_quantity_1000_zero_maker: Decimal


class PeriodBacktest(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    period_type: Literal["HORIZON", "ROLLING"]
    start: datetime
    end: datetime
    elapsed_days: Decimal
    observed_low_events: int
    observed_high_events: int
    low_to_high_paths: int
    completed_serial_cycles: int
    cycles_per_day: Decimal
    cycles_per_week: Decimal
    cycles_per_month: Decimal
    zero_cycle_days: int
    best_day: str | None
    best_day_cycles: int
    worst_day: str | None
    worst_day_cycles: int
    best_week: str | None
    best_week_cycles: int
    worst_week: str | None
    worst_week_cycles: int
    daily_cycle_distribution: Distribution
    weekly_cycle_distribution: Distribution
    holding_time_seconds: Distribution
    carried_in_position: bool
    opened_in_window: int
    closed_in_window: int
    carried_out_position: bool
    open_position_at_end: OpenPosition | None
    capital_locked_duration_seconds: Decimal
    capital_outcomes: tuple[CapitalOutcome, ...]
    price_paths_are_fills: bool = False
    execution_status: Literal["INCONCLUSIVE"] = "INCONCLUSIVE"


class PriceHistory(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    relevant_events: tuple[TradeEvent, ...]
    day_last_prices: dict[date, tuple[datetime, Decimal]]
    first_timestamp: datetime
    last_timestamp: datetime


class BacktestCampaign(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "s0-price-path-backtest-v1"
    strategy_id: str = "S0_FROZEN_LEVELS-v1"
    symbol: str = "FDUSDUSDC"
    lower: Decimal = Decimal("0.9988")
    upper: Decimal = Decimal("0.9989")
    dataset_hash: str
    run_id: str
    first_timestamp: datetime
    last_timestamp: datetime
    archive_count: int
    total_records: int
    unavailable_horizons: tuple[str, ...]
    horizon_results: tuple[PeriodBacktest, ...]
    rolling_results: tuple[PeriodBacktest, ...]
    cycles: tuple[PricePathCycle, ...]
    backtest_classification: Literal["BACKTEST_PASS", "BACKTEST_FAIL", "BACKTEST_INCONCLUSIVE"]
    classification_reason: str
    execution_status: Literal["INCONCLUSIVE"] = "INCONCLUSIVE"
    shadow_authorized: bool = False


def load_price_history(
    archives: list[Path],
    *,
    kind: Literal["trades", "aggTrades"],
    lower: Decimal,
    upper: Decimal,
) -> tuple[PriceHistory, int]:
    if not archives:
        raise PricePathIntegrityError("no validated archives supplied")
    relevant: list[TradeEvent] = []
    last_by_day: dict[date, tuple[datetime, Decimal]] = {}
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    previous: TradeEvent | None = None
    total_records = 0
    for archive in archives:
        events = parse_archive(archive, kind)
        if not events:
            raise PricePathIntegrityError(f"empty archive: {archive}")
        total_records += len(events)
        if previous is not None and (events[0].timestamp, events[0].trade_id) <= (
            previous.timestamp,
            previous.trade_id,
        ):
            raise PricePathIntegrityError("archives overlap or are not chronologically ordered")
        first_timestamp = first_timestamp or events[0].timestamp
        last_timestamp = events[-1].timestamp
        last_by_day[events[-1].timestamp.date()] = (events[-1].timestamp, events[-1].price)
        relevant.extend(event for event in events if event.price in {lower, upper})
        previous = events[-1]
    if first_timestamp is None or last_timestamp is None:  # pragma: no cover - guarded above
        raise PricePathIntegrityError("history has no timestamps")
    return (
        PriceHistory(
            relevant_events=tuple(relevant),
            day_last_prices=last_by_day,
            first_timestamp=first_timestamp,
            last_timestamp=last_timestamp,
        ),
        total_records,
    )


def run_campaign(
    history: PriceHistory,
    *,
    dataset_hash: str,
    archive_count: int,
    total_records: int,
    lower: Decimal = Decimal("0.9988"),
    upper: Decimal = Decimal("0.9989"),
    capital_scenarios: tuple[Decimal, ...] = DEFAULT_CAPITAL_SCENARIOS,
    fee_scenarios: tuple[FeeScenario, ...] = DEFAULT_FEE_SCENARIOS,
    step_size: Decimal = Decimal("0.01"),
    min_quantity: Decimal = Decimal("0.01"),
    min_notional: Decimal = Decimal("5"),
) -> BacktestCampaign:
    full_cycles, terminal_entry = _serial_cycles(
        history.relevant_events,
        start=history.first_timestamp,
        end=history.last_timestamp,
        lower=lower,
        upper=upper,
    )
    event_times = tuple(item.timestamp for item in history.relevant_events)
    entry_times = tuple(item.entry_timestamp for item in full_cycles)
    exit_times = tuple(item.exit_timestamp for item in full_cycles)
    capital_cache: CapitalCache = {}
    horizons: list[PeriodBacktest] = []
    unavailable_horizons: list[str] = []
    available_days = (history.last_timestamp.date() - history.first_timestamp.date()).days + 1
    for days in (1, 7, 30, 60, 90, 180, 365):
        if available_days < days:
            unavailable_horizons.append(f"{days}_DAY")
            continue
        end = min(
            _day_end(history.first_timestamp.date() + timedelta(days=days - 1)),
            history.last_timestamp,
        )
        horizons.append(
            run_period(
                history,
                full_cycles=full_cycles,
                terminal_entry=terminal_entry,
                label=f"{days}_DAY",
                period_type="HORIZON",
                start=history.first_timestamp,
                end=end,
                lower=lower,
                upper=upper,
                capital_scenarios=capital_scenarios,
                fee_scenarios=fee_scenarios,
                step_size=step_size,
                min_quantity=min_quantity,
                min_notional=min_notional,
                event_times=event_times,
                entry_times=entry_times,
                exit_times=exit_times,
                capital_cache=capital_cache,
            )
        )
    horizons.append(
        run_period(
            history,
            full_cycles=full_cycles,
            terminal_entry=terminal_entry,
            label="MAX_AVAILABLE_HISTORY",
            period_type="HORIZON",
            start=history.first_timestamp,
            end=history.last_timestamp,
            lower=lower,
            upper=upper,
            capital_scenarios=capital_scenarios,
            fee_scenarios=fee_scenarios,
            step_size=step_size,
            min_quantity=min_quantity,
            min_notional=min_notional,
            event_times=event_times,
            entry_times=entry_times,
            exit_times=exit_times,
            capital_cache=capital_cache,
        )
    )
    rolling: list[PeriodBacktest] = []
    for days in (7, 30, 90):
        if available_days < days:
            continue
        cursor = history.first_timestamp.date()
        last_start = history.last_timestamp.date() - timedelta(days=days - 1)
        while cursor <= last_start:
            window_end = min(_day_end(cursor + timedelta(days=days - 1)), history.last_timestamp)
            rolling.append(
                run_period(
                    history,
                    full_cycles=full_cycles,
                    terminal_entry=terminal_entry,
                    label=f"ROLLING_{days}D_{cursor.isoformat()}",
                    period_type="ROLLING",
                    start=max(_day_start(cursor), history.first_timestamp),
                    end=window_end,
                    lower=lower,
                    upper=upper,
                    capital_scenarios=capital_scenarios,
                    fee_scenarios=fee_scenarios,
                    step_size=step_size,
                    min_quantity=min_quantity,
                    min_notional=min_notional,
                    event_times=event_times,
                    entry_times=entry_times,
                    exit_times=exit_times,
                    capital_cache=capital_cache,
                )
            )
            cursor += timedelta(days=1)
    identity = {
        "strategy_id": "S0_FROZEN_LEVELS-v1",
        "dataset_hash": dataset_hash,
        "lower": lower,
        "upper": upper,
        "capitals": capital_scenarios,
        "fees": [item.model_dump(mode="json") for item in fee_scenarios],
        "step_size": step_size,
        "min_quantity": min_quantity,
        "min_notional": min_notional,
    }
    return BacktestCampaign(
        dataset_hash=dataset_hash,
        run_id=canonical_hash(identity),
        first_timestamp=history.first_timestamp,
        last_timestamp=history.last_timestamp,
        archive_count=archive_count,
        total_records=total_records,
        unavailable_horizons=tuple(unavailable_horizons),
        horizon_results=tuple(horizons),
        rolling_results=tuple(rolling),
        cycles=full_cycles,
        backtest_classification="BACKTEST_INCONCLUSIVE",
        classification_reason=(
            "Price recurrence can be measured, but historical bulk trades do not identify "
            "our queue/fills and the frozen levels were selected from the terminal discovery day."
        ),
    )


def run_period(
    history: PriceHistory,
    *,
    full_cycles: tuple[PricePathCycle, ...],
    terminal_entry: TradeEvent | None,
    label: str,
    period_type: Literal["HORIZON", "ROLLING"],
    start: datetime,
    end: datetime,
    lower: Decimal,
    upper: Decimal,
    capital_scenarios: tuple[Decimal, ...],
    fee_scenarios: tuple[FeeScenario, ...],
    step_size: Decimal,
    min_quantity: Decimal,
    min_notional: Decimal,
    event_times: tuple[datetime, ...] | None = None,
    entry_times: tuple[datetime, ...] | None = None,
    exit_times: tuple[datetime, ...] | None = None,
    capital_cache: CapitalCache | None = None,
) -> PeriodBacktest:
    event_times = event_times or tuple(item.timestamp for item in history.relevant_events)
    entry_times = entry_times or tuple(item.entry_timestamp for item in full_cycles)
    exit_times = exit_times or tuple(item.exit_timestamp for item in full_cycles)
    event_start = bisect_left(event_times, start)
    event_end = bisect_right(event_times, end)
    cycle_start = bisect_left(exit_times, start)
    cycle_end = bisect_right(exit_times, end)
    events = history.relevant_events[event_start:event_end]
    cycles = full_cycles[cycle_start:cycle_end]
    cycles_before = cycle_start
    open_at_start = _position_at_fast(
        full_cycles,
        entry_times=entry_times,
        terminal_entry=terminal_entry,
        timestamp=start,
        include_at_boundary=True,
    )
    open_at_end = _position_at_fast(
        full_cycles,
        entry_times=entry_times,
        terminal_entry=terminal_entry,
        timestamp=end,
        include_at_boundary=False,
    )
    calendar_days = list(_dates(start.date(), end.date()))
    daily = Counter(cycle.exit_timestamp.date() for cycle in cycles)
    daily_values = [Decimal(daily[item]) for item in calendar_days]
    weekly_labels = sorted(
        {f"{item.isocalendar().year}-W{item.isocalendar().week:02d}" for item in calendar_days}
    )
    weekly = Counter(
        f"{cycle.exit_timestamp.date().isocalendar().year}-W"
        f"{cycle.exit_timestamp.date().isocalendar().week:02d}"
        for cycle in cycles
    )
    weekly_values = [Decimal(weekly[item]) for item in weekly_labels]
    elapsed_seconds = _seconds(end - start) + Decimal("0.000001")
    elapsed_days = elapsed_seconds / Decimal("86400")
    outcomes = tuple(
        _capital_outcome(
            cycles=len(cycles),
            prior_cycles=cycles_before,
            initial=capital,
            fee=fee,
            lower=lower,
            upper=upper,
            step_size=step_size,
            min_quantity=min_quantity,
            min_notional=min_notional,
            capital_cache=capital_cache,
        )
        for capital in capital_scenarios
        for fee in fee_scenarios
    )
    open_position: OpenPosition | None = None
    intersect_start = bisect_left(exit_times, start)
    intersect_end = bisect_right(entry_times, end)
    capital_locked = sum(
        (
            _interval_seconds(cycle.entry_timestamp, cycle.exit_timestamp, start, end)
            for cycle in full_cycles[intersect_start:intersect_end]
        ),
        Decimal("0"),
    )
    if terminal_entry is not None:
        capital_locked += _interval_seconds(terminal_entry.timestamp, end, start, end)
    if open_at_end is not None:
        last_market_timestamp, last_price = _last_price(history.day_last_prices, end.date())
        age = _seconds(end - open_at_end.timestamp)
        open_position = OpenPosition(
            status=(
                "OPEN_AT_DATASET_END" if end == history.last_timestamp else "OPEN_AT_PERIOD_END"
            ),
            entry_price=lower,
            entry_time=open_at_end.timestamp,
            entry_trade_id=open_at_end.trade_id,
            holding_age_seconds=age,
            last_market_price=last_price,
            last_market_timestamp=last_market_timestamp,
            last_market_stale_seconds=_seconds(end - last_market_timestamp),
            mark_to_market_fraction=(last_price / lower) - Decimal("1"),
            primary_quantity_1000_zero_maker=(Decimal("1000") / lower // step_size) * step_size,
        )
    best_day = max(calendar_days, key=lambda item: (daily[item], item)) if calendar_days else None
    worst_day = min(calendar_days, key=lambda item: (daily[item], item)) if calendar_days else None
    best_week = max(weekly_labels, key=lambda item: (weekly[item], item)) if weekly_labels else None
    worst_week = (
        min(weekly_labels, key=lambda item: (weekly[item], item)) if weekly_labels else None
    )
    return PeriodBacktest(
        label=label,
        period_type=period_type,
        start=start,
        end=end,
        elapsed_days=elapsed_days,
        observed_low_events=sum(event.price == lower for event in events),
        observed_high_events=sum(event.price == upper for event in events),
        low_to_high_paths=len(cycles),
        completed_serial_cycles=len(cycles),
        cycles_per_day=Decimal(len(cycles)) / elapsed_days,
        cycles_per_week=Decimal(len(cycles)) / elapsed_days * Decimal("7"),
        cycles_per_month=Decimal(len(cycles)) / elapsed_days * Decimal("30.436875"),
        zero_cycle_days=sum(daily[item] == 0 for item in calendar_days),
        best_day=best_day.isoformat() if best_day else None,
        best_day_cycles=daily[best_day] if best_day else 0,
        worst_day=worst_day.isoformat() if worst_day else None,
        worst_day_cycles=daily[worst_day] if worst_day else 0,
        best_week=best_week,
        best_week_cycles=weekly[best_week] if best_week else 0,
        worst_week=worst_week,
        worst_week_cycles=weekly[worst_week] if worst_week else 0,
        daily_cycle_distribution=_distribution(daily_values),
        weekly_cycle_distribution=_distribution(weekly_values),
        holding_time_seconds=_distribution([item.holding_seconds for item in cycles]),
        carried_in_position=open_at_start is not None,
        opened_in_window=bisect_right(entry_times, end)
        - bisect_left(entry_times, start)
        + int(terminal_entry is not None and start <= terminal_entry.timestamp <= end),
        closed_in_window=len(cycles),
        carried_out_position=open_at_end is not None,
        open_position_at_end=open_position,
        capital_locked_duration_seconds=capital_locked,
        capital_outcomes=outcomes,
    )


def _serial_cycles(
    events: tuple[TradeEvent, ...],
    *,
    start: datetime,
    end: datetime,
    lower: Decimal,
    upper: Decimal,
) -> tuple[tuple[PricePathCycle, ...], TradeEvent | None]:
    entry: TradeEvent | None = None
    cycles: list[PricePathCycle] = []
    for event in events:
        if not (start <= event.timestamp <= end):
            continue
        if entry is None and event.price == lower:
            entry = event
        elif entry is not None and event.price == upper:
            cycles.append(
                PricePathCycle(
                    cycle_number=len(cycles) + 1,
                    entry_timestamp=entry.timestamp,
                    exit_timestamp=event.timestamp,
                    holding_seconds=_seconds(event.timestamp - entry.timestamp),
                    entry_trade_id=entry.trade_id,
                    exit_trade_id=event.trade_id,
                )
            )
            entry = None
    return tuple(cycles), entry


def _capital_outcome(
    *,
    cycles: int,
    prior_cycles: int,
    initial: Decimal,
    fee: FeeScenario,
    lower: Decimal,
    upper: Decimal,
    step_size: Decimal,
    min_quantity: Decimal,
    min_notional: Decimal,
    capital_cache: CapitalCache | None,
) -> CapitalOutcome:
    fixed_start = _capital_path_cached(
        cycles=prior_cycles,
        initial=initial,
        fixed=True,
        rate=fee.maker_rate_per_leg,
        lower=lower,
        upper=upper,
        step_size=step_size,
        min_quantity=min_quantity,
        min_notional=min_notional,
        cache=capital_cache,
    )
    compound_start = _capital_path_cached(
        cycles=prior_cycles,
        initial=initial,
        fixed=False,
        rate=fee.maker_rate_per_leg,
        lower=lower,
        upper=upper,
        step_size=step_size,
        min_quantity=min_quantity,
        min_notional=min_notional,
        cache=capital_cache,
    )
    fixed = _capital_path_cached(
        cycles=prior_cycles + cycles,
        initial=initial,
        fixed=True,
        rate=fee.maker_rate_per_leg,
        lower=lower,
        upper=upper,
        step_size=step_size,
        min_quantity=min_quantity,
        min_notional=min_notional,
        cache=capital_cache,
    )
    compound = _capital_path_cached(
        cycles=prior_cycles + cycles,
        initial=initial,
        fixed=False,
        rate=fee.maker_rate_per_leg,
        lower=lower,
        upper=upper,
        step_size=step_size,
        min_quantity=min_quantity,
        min_notional=min_notional,
        cache=capital_cache,
    )
    gross_edge = upper / lower - Decimal("1")
    net_edge = upper * (Decimal("1") - fee.maker_rate_per_leg) / (
        lower * (Decimal("1") + fee.maker_rate_per_leg)
    ) - Decimal("1")
    status: Literal["POSITIVE", "BREAK_EVEN", "ECONOMIC_NO_GO_FOR_THIS_FEE_SCENARIO"]
    if net_edge > 0:
        status = "POSITIVE"
    elif net_edge == 0:
        status = "BREAK_EVEN"
    else:
        status = "ECONOMIC_NO_GO_FOR_THIS_FEE_SCENARIO"
    return CapitalOutcome(
        initial_capital=initial,
        fee_scenario=fee,
        completed_cycles=cycles,
        gross_edge_fraction=gross_edge,
        gross_edge_bps=gross_edge * Decimal("10000"),
        break_even_fee_per_leg=(upper - lower) / (upper + lower),
        net_edge_fraction_before_rounding=net_edge,
        economic_status=status,
        capital_at_period_start_fixed_lot=fixed_start[0],
        capital_at_period_start_compounding=compound_start[0],
        final_capital_fixed_lot=fixed[0],
        final_capital_compounding=compound[0],
        gross_profit_fixed_lot=fixed[1] - fixed_start[1],
        gross_profit_compounding=compound[1] - compound_start[1],
        fees_fixed_lot=fixed[2] - fixed_start[2],
        fees_compounding=compound[2] - compound_start[2],
        net_profit_fixed_lot=fixed[0] - fixed_start[0],
        net_profit_compounding=compound[0] - compound_start[0],
        return_fixed_lot=(fixed[0] / fixed_start[0]) - Decimal("1"),
        return_compounding=(compound[0] / compound_start[0]) - Decimal("1"),
        dust_fixed_lot=fixed[3],
        dust_compounding=compound[3],
    )


def _capital_path(
    *,
    cycles: int,
    initial: Decimal,
    fixed: bool,
    rate: Decimal,
    lower: Decimal,
    upper: Decimal,
    step_size: Decimal,
    min_quantity: Decimal,
    min_notional: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    balance = initial
    gross_profit = Decimal("0")
    fees = Decimal("0")
    dust = Decimal("0")
    fixed_budget = initial
    for _ in range(cycles):
        budget = min(fixed_budget, balance) if fixed else balance
        spendable = budget / (Decimal("1") + rate)
        quantity = (spendable / lower // step_size) * step_size
        if quantity < min_quantity or quantity * lower < min_notional:
            break
        buy_notional = quantity * lower
        sell_notional = quantity * upper
        buy_fee = buy_notional * rate
        sell_fee = sell_notional * rate
        cycle_dust = budget - buy_notional - buy_fee
        balance += sell_notional - sell_fee - buy_notional - buy_fee
        gross_profit += sell_notional - buy_notional
        fees += buy_fee + sell_fee
        dust = cycle_dust
    return balance, gross_profit, fees, dust


def _capital_path_cached(
    *,
    cycles: int,
    initial: Decimal,
    fixed: bool,
    rate: Decimal,
    lower: Decimal,
    upper: Decimal,
    step_size: Decimal,
    min_quantity: Decimal,
    min_notional: Decimal,
    cache: CapitalCache | None,
) -> CapitalState:
    if cache is None:
        return _capital_path(
            cycles=cycles,
            initial=initial,
            fixed=fixed,
            rate=rate,
            lower=lower,
            upper=upper,
            step_size=step_size,
            min_quantity=min_quantity,
            min_notional=min_notional,
        )
    key: CapitalCacheKey = (
        initial,
        fixed,
        rate,
        lower,
        upper,
        step_size,
        min_quantity,
        min_notional,
    )
    states = cache.setdefault(key, [(initial, Decimal("0"), Decimal("0"), Decimal("0"))])
    fixed_budget = initial
    while len(states) <= cycles:
        balance, gross_profit, fees, previous_dust = states[-1]
        budget = min(fixed_budget, balance) if fixed else balance
        spendable = budget / (Decimal("1") + rate)
        quantity = (spendable / lower // step_size) * step_size
        if quantity < min_quantity or quantity * lower < min_notional:
            states.append((balance, gross_profit, fees, previous_dust))
            continue
        buy_notional = quantity * lower
        sell_notional = quantity * upper
        buy_fee = buy_notional * rate
        sell_fee = sell_notional * rate
        states.append(
            (
                balance + sell_notional - sell_fee - buy_notional - buy_fee,
                gross_profit + sell_notional - buy_notional,
                fees + buy_fee + sell_fee,
                budget - buy_notional - buy_fee,
            )
        )
    return states[cycles]


def _distribution(values: list[Decimal]) -> Distribution:
    if not values:
        return Distribution(
            count=0,
            mean=None,
            minimum=None,
            p10=None,
            p25=None,
            p50=None,
            p75=None,
            p90=None,
            p95=None,
            p99=None,
            maximum=None,
        )
    ordered = sorted(values)
    return Distribution(
        count=len(ordered),
        mean=sum(ordered, Decimal("0")) / Decimal(len(ordered)),
        minimum=ordered[0],
        p10=_percentile(ordered, Decimal("0.10")),
        p25=_percentile(ordered, Decimal("0.25")),
        p50=_percentile(ordered, Decimal("0.50")),
        p75=_percentile(ordered, Decimal("0.75")),
        p90=_percentile(ordered, Decimal("0.90")),
        p95=_percentile(ordered, Decimal("0.95")),
        p99=_percentile(ordered, Decimal("0.99")),
        maximum=ordered[-1],
    )


def _percentile(ordered: list[Decimal], quantile: Decimal) -> Decimal:
    position = Decimal(len(ordered) - 1) * quantile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - Decimal(lower_index)
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def _position_at_fast(
    cycles: tuple[PricePathCycle, ...],
    *,
    entry_times: tuple[datetime, ...],
    terminal_entry: TradeEvent | None,
    timestamp: datetime,
    include_at_boundary: bool,
) -> TradeEvent | None:
    candidate_index = bisect_right(entry_times, timestamp) - 1
    if candidate_index >= 0:
        cycle = cycles[candidate_index]
        active = (
            cycle.entry_timestamp < timestamp <= cycle.exit_timestamp
            if include_at_boundary
            else cycle.entry_timestamp <= timestamp < cycle.exit_timestamp
        )
        if active:
            return TradeEvent(
                trade_id=cycle.entry_trade_id,
                timestamp=cycle.entry_timestamp,
                sequence=cycle.entry_trade_id,
                price=Decimal("0.9988"),
                quantity=Decimal("1"),
                buyer_is_maker=True,
            )
    if terminal_entry is not None and (
        terminal_entry.timestamp < timestamp
        if include_at_boundary
        else terminal_entry.timestamp <= timestamp
    ):
        return terminal_entry
    return None


def _interval_seconds(
    interval_start: datetime,
    interval_end: datetime,
    period_start: datetime,
    period_end: datetime,
) -> Decimal:
    overlap_start = max(interval_start, period_start)
    overlap_end = min(interval_end, period_end)
    return max(Decimal("0"), _seconds(overlap_end - overlap_start))


def _last_price(
    day_last_prices: dict[date, tuple[datetime, Decimal]], end_day: date
) -> tuple[datetime, Decimal]:
    eligible = [item for item in day_last_prices if item <= end_day]
    if not eligible:
        raise PricePathIntegrityError("no mark price available at period end")
    return day_last_prices[max(eligible)]


def _dates(start: date, end: date) -> tuple[date, ...]:
    return tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))


def _day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _day_end(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=UTC)


def _seconds(delta: timedelta) -> Decimal:
    return Decimal(delta.days * 86_400 + delta.seconds) + Decimal(delta.microseconds) / Decimal(
        "1000000"
    )
