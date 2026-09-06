from __future__ import annotations

from array import array
from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from crypto_strategy_lab.domain import canonical_hash, require_utc
from crypto_strategy_lab.microstructure.data import (
    HistoryManifest,
    MicrostructureManifest,
    iter_archive,
)

EVENT_ORDER_SCALE = 4096
MICROS_PER_SECOND = 1_000_000


class SerialStrategy(StrEnum):
    STATIC = "STATIC"
    PERIODIC_RESELECT = "PERIODIC_RESELECT"
    ALWAYS_BEST = "ALWAYS_BEST"
    IDLE_TRIGGERED = "IDLE_TRIGGERED"


class SerialModelConfig(BaseModel):
    """Complete decision configuration for one immutable strategy model."""

    model_config = ConfigDict(frozen=True)

    model_id: str = Field(pattern=r"^M\d{3,}$")
    parent_model_id: str | None
    symbol: str = "USDCUSDT"
    strategy: SerialStrategy
    distances: tuple[int, ...] = (1,)
    lookback_minutes: int = Field(default=1_440, gt=0)
    decision_interval_minutes: int | None = Field(default=None, gt=0)
    idle_threshold_minutes: int | None = Field(default=None, gt=0)
    confirmation_checks: int | None = Field(default=None, gt=0)
    switch_advantage: Decimal | None = Field(default=None, ge=0)
    cooldown_minutes: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_strategy_fields(self) -> SerialModelConfig:
        if not self.distances or any(item <= 0 for item in self.distances):
            raise ValueError("distances must contain positive tick counts")
        adaptive = self.strategy != SerialStrategy.STATIC
        if adaptive != (self.decision_interval_minutes is not None):
            raise ValueError("only adaptive strategies require a decision interval")
        idle_fields = (
            self.idle_threshold_minutes,
            self.confirmation_checks,
            self.switch_advantage,
            self.cooldown_minutes,
        )
        if self.strategy == SerialStrategy.IDLE_TRIGGERED:
            if any(item is None for item in idle_fields):
                raise ValueError("IDLE_TRIGGERED requires every idle-control parameter")
        elif any(item is not None for item in idle_fields):
            raise ValueError("idle-control parameters are exclusive to IDLE_TRIGGERED")
        return self

    @property
    def model_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json", exclude={"model_id", "parent_model_id"}))


class SerialScenarioConfig(BaseModel):
    """Execution/accounting assumptions shared by strategy models in one comparison."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str = "PRICE_PATH_MATHEMATICAL_ZERO_FEE_V1"
    initial_quote: Decimal = Field(default=Decimal("100"), gt=0)
    tick_size: Decimal = Field(gt=0)
    quantity_step: Decimal = Field(default=Decimal("0.01"), gt=0)
    minimum_notional: Decimal = Field(default=Decimal("0"), ge=0)
    maker_fee_per_leg: Decimal = Field(default=Decimal("0"), ge=0)
    forced_terminal_liquidation: bool = False
    queue_assumption: str = "NOT_MODELED"
    latency_assumption: str = "ZERO_COUNTERFACTUAL"
    execution_class: str = "PRICE_PATH_NOT_FILL_EVIDENCE"

    @model_validator(mode="after")
    def prohibit_forced_close(self) -> SerialScenarioConfig:
        if self.forced_terminal_liquidation:
            raise ValueError("the reference strategy cannot force terminal liquidation")
        return self

    @property
    def scenario_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json", exclude={"scenario_id"}))


def preregistered_first_block() -> tuple[SerialModelConfig, ...]:
    return (
        SerialModelConfig(
            model_id="M001",
            parent_model_id=None,
            strategy=SerialStrategy.STATIC,
            distances=(1,),
            lookback_minutes=1_440,
        ),
        SerialModelConfig(
            model_id="M002",
            parent_model_id="M001",
            strategy=SerialStrategy.PERIODIC_RESELECT,
            decision_interval_minutes=60,
            distances=(1,),
            lookback_minutes=1_440,
        ),
        SerialModelConfig(
            model_id="M003",
            parent_model_id="M002",
            strategy=SerialStrategy.ALWAYS_BEST,
            decision_interval_minutes=1,
            distances=(1,),
            lookback_minutes=1_440,
        ),
        SerialModelConfig(
            model_id="M004",
            parent_model_id="M003",
            strategy=SerialStrategy.IDLE_TRIGGERED,
            decision_interval_minutes=1,
            idle_threshold_minutes=30,
            confirmation_checks=5,
            switch_advantage=Decimal("0.10"),
            cooldown_minutes=60,
            distances=(1,),
            lookback_minutes=1_440,
        ),
    )


class SerialCycle(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_event: int
    exit_event: int
    entry_timestamp: datetime
    exit_timestamp: datetime
    low: Decimal
    high: Decimal
    quantity: Decimal
    buy_fee_quote: Decimal
    sell_fee_quote: Decimal


class SerialReplayResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    model_hash: str
    scenario_id: str
    scenario_hash: str
    start: datetime
    end_exclusive: datetime
    initial_quote: Decimal
    final_cash: Decimal
    final_inventory: Decimal
    last_price: Decimal
    final_marked_equity: Decimal
    return_fraction: Decimal
    realized_profit: Decimal
    unrealized_profit: Decimal
    total_fees: Decimal
    completed_cycles: int
    daily_cycles: dict[date, int]
    zero_cycle_days: int
    reselection_count: int
    blocked_reselection_checks: int
    cooldown_violations: int
    reversal_24h_count: int
    active_low: Decimal | None
    active_high: Decimal | None
    open_entry_timestamp: datetime | None
    open_holding_seconds: Decimal | None
    open_cycle_censored: bool
    execution_class: str
    capacity_capped_final_capital: None = None
    cycles: tuple[SerialCycle, ...]


class OracleCandidateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    low_tick: int
    high_tick: int
    distance_ticks: int
    cycles: int
    gross_edge: Decimal
    gross_edge_throughput: Decimal
    entry_events: tuple[int, ...]
    exit_events: tuple[int, ...]


@dataclass(frozen=True)
class CandidateTimeline:
    low_tick: int
    distance: int
    low_events: array[int]
    high_events: array[int]
    cycle_entries: array[int] = field(default_factory=lambda: array("q"))
    cycle_exits: array[int] = field(default_factory=lambda: array("q"))

    def build(self) -> None:
        after = -1
        low_index = high_index = 0
        while low_index < len(self.low_events):
            low_index = bisect_right(self.low_events, after, lo=low_index)
            if low_index >= len(self.low_events):
                return
            entry = self.low_events[low_index]
            high_index = bisect_right(self.high_events, entry, lo=high_index)
            if high_index >= len(self.high_events):
                return
            exit_event = self.high_events[high_index]
            self.cycle_entries.append(entry)
            self.cycle_exits.append(exit_event)
            after = exit_event
            low_index += 1
            high_index += 1

    def contained_cycles(self, start: int, end: int) -> int:
        return len(self.cycle_events(start, end)[0])

    def cycle_events(self, start: int, end: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
        entries: list[int] = []
        exits: list[int] = []
        low_index = bisect_left(self.low_events, start)
        high_index = bisect_left(self.high_events, start)
        after = start - 1
        while low_index < len(self.low_events):
            low_index = bisect_right(self.low_events, after, lo=low_index)
            if low_index >= len(self.low_events) or self.low_events[low_index] >= end:
                break
            entry = self.low_events[low_index]
            high_index = bisect_right(self.high_events, entry, lo=high_index)
            if high_index >= len(self.high_events) or self.high_events[high_index] >= end:
                break
            exit_event = self.high_events[high_index]
            entries.append(entry)
            exits.append(exit_event)
            after = exit_event
            low_index += 1
            high_index += 1
        return tuple(entries), tuple(exits)


@dataclass(frozen=True)
class SerialTape:
    """Compact, ordered price-event tape on one exact fixed-point grid."""

    tick_size: Decimal
    occurrences: dict[int, array[int]]
    events: array[int]
    price_ticks: array[int]
    last_event: int
    last_price_tick: int

    @classmethod
    def from_events(
        cls,
        events: Iterable[tuple[datetime, Decimal]],
        *,
        tick_size: Decimal,
    ) -> SerialTape:
        if not events:
            raise ValueError("event tape cannot be empty")
        occurrences: dict[int, array[int]] = {}
        encoded_events = array("q")
        price_ticks = array("i")
        previous_timestamp: datetime | None = None
        previous_event = -1
        ordinal = 0
        last_price = 0
        for timestamp, price in events:
            normalized = require_utc(timestamp)
            if previous_timestamp is not None and normalized < previous_timestamp:
                raise ValueError("events must be chronological")
            ordinal = ordinal + 1 if normalized == previous_timestamp else 0
            if ordinal >= EVENT_ORDER_SCALE:
                raise ValueError("too many events share one timestamp")
            scaled = price / tick_size
            if scaled != scaled.to_integral_value():
                raise ValueError(f"price {price} is off the configured tick grid")
            tick = int(scaled)
            event = _datetime_to_micros(normalized) * EVENT_ORDER_SCALE + ordinal
            if event <= previous_event:
                raise ValueError("event ordering is not strictly increasing")
            occurrences.setdefault(tick, array("q")).append(event)
            encoded_events.append(event)
            price_ticks.append(tick)
            previous_timestamp = normalized
            previous_event = event
            last_price = tick
        return cls(tick_size, occurrences, encoded_events, price_ticks, previous_event, last_price)

    def last_price_before(self, end_exclusive: int) -> int:
        index = bisect_left(self.events, end_exclusive) - 1
        if index < 0:
            raise ValueError("replay interval has no observed mark price")
        return self.price_ticks[index]

    def timelines(self, distances: tuple[int, ...]) -> dict[tuple[int, int], CandidateTimeline]:
        result: dict[tuple[int, int], CandidateTimeline] = {}
        for low_tick, lows in self.occurrences.items():
            for distance in distances:
                highs = self.occurrences.get(low_tick + distance)
                if highs is None:
                    continue
                timeline = CandidateTimeline(low_tick, distance, lows, highs)
                timeline.build()
                result[(low_tick, distance)] = timeline
        return result


def load_serial_tape(
    manifest: HistoryManifest,
    *,
    tick_size: Decimal,
    start: datetime,
    end_exclusive: datetime,
) -> SerialTape:
    """Load one already-verified, gap-free manifest interval into integer ticks."""
    start = require_utc(start)
    end_exclusive = require_utc(end_exclusive)
    if manifest.symbol != "USDCUSDT":
        raise ValueError("the active serial campaign accepts only USDCUSDT")
    if manifest.integrity_status != "VALID" or manifest.invalidity_reasons:
        raise ValueError("serial replay requires a VALID history manifest")
    if start < manifest.first_timestamp:
        raise ValueError("requested tape start precedes validated history")
    physical_end_exclusive = manifest.last_timestamp + timedelta(microseconds=1)
    if end_exclusive > physical_end_exclusive:
        raise ValueError("requested tape end exceeds validated history")
    selected = tuple(
        item
        for item in manifest.archives
        if item.last_timestamp >= start and item.first_timestamp < end_exclusive
    )
    if not selected:
        raise ValueError("requested tape interval has no archives")

    # A reconciled manifest already excludes replaced daily archives.  Apply the
    # same authority rule at load time so an older/mixed manifest cannot double-count
    # a day when a complete monthly archive is present.
    monthly = tuple(item for item in selected if item.cadence == "monthly")
    if monthly:
        selected = tuple(
            item
            for item in selected
            if item.cadence == "monthly"
            or not any(_archive_coverage_overlaps(item, replacement) for replacement in monthly)
        )
    selected = tuple(sorted(selected, key=_archive_coverage_start))

    def events() -> Iterator[tuple[datetime, Decimal]]:
        for item in selected:
            for event in iter_archive(Path(item.local_path), manifest.kind):
                if not start <= event.timestamp < end_exclusive:
                    continue
                yield event.timestamp, event.price

    return SerialTape.from_events(events(), tick_size=tick_size)


def _archive_coverage_start(item: MicrostructureManifest) -> datetime:
    coverage_start = item.coverage_start
    if coverage_start is not None:
        return coverage_start
    return datetime.combine(item.utc_date, time.min, tzinfo=UTC)


def _archive_coverage_end(item: MicrostructureManifest) -> datetime:
    coverage_end = item.coverage_end
    if coverage_end is not None:
        return coverage_end
    return datetime.combine(item.utc_date, time.max, tzinfo=UTC)


def _archive_coverage_overlaps(left: MicrostructureManifest, right: MicrostructureManifest) -> bool:
    left_start = _archive_coverage_start(left)
    right_start = _archive_coverage_start(right)
    return left_start <= _archive_coverage_end(right) and right_start <= _archive_coverage_end(left)


@dataclass
class _State:
    cash: Decimal
    candidate: tuple[int, int] | None = None
    entry_event: int | None = None
    inventory: Decimal = Decimal("0")
    inventory_cost: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    realized_profit: Decimal = Decimal("0")
    cycles: list[SerialCycle] = field(default_factory=list)
    changes: list[tuple[int, tuple[int, int] | None, tuple[int, int] | None]] = field(
        default_factory=list
    )
    flat_since: int = 0
    idle_challenger: tuple[int, int] | None = None
    idle_confirmations: int = 0
    last_change: int | None = None
    blocked_checks: int = 0


def replay_serial_model(
    tape: SerialTape,
    config: SerialModelConfig,
    scenario: SerialScenarioConfig,
    *,
    start: datetime,
    end_exclusive: datetime,
) -> SerialReplayResult:
    start = require_utc(start)
    end_exclusive = require_utc(end_exclusive)
    if start >= end_exclusive:
        raise ValueError("start must precede end_exclusive")
    if scenario.tick_size != tape.tick_size:
        raise ValueError("scenario tick size must match the physical event tape")
    start_event = _datetime_to_micros(start) * EVENT_ORDER_SCALE
    end_event = _datetime_to_micros(end_exclusive) * EVENT_ORDER_SCALE
    last_timestamp_exclusive = (tape.last_event // EVENT_ORDER_SCALE + 1) * EVENT_ORDER_SCALE
    if end_event > last_timestamp_exclusive:
        raise ValueError("replay end exceeds the physical event tape")
    timelines = tape.timelines(config.distances)
    lookback = _minutes_to_events(config.lookback_minutes)
    state = _State(cash=scenario.initial_quote, flat_since=start_event)
    selected = _select(timelines, config, start_event - lookback, start_event)
    state.candidate = selected
    cursor = start_event
    if config.strategy == SerialStrategy.STATIC:
        _advance(
            state,
            timelines,
            config,
            scenario,
            cursor,
            end_event,
            recalculate_after_exit=False,
        )
    else:
        interval = _minutes_to_events(config.decision_interval_minutes or 1)
        while cursor < end_event:
            boundary = min(cursor + interval, end_event)
            _advance(
                state,
                timelines,
                config,
                scenario,
                cursor,
                boundary,
                recalculate_after_exit=config.strategy != SerialStrategy.IDLE_TRIGGERED,
            )
            if boundary < end_event:
                _decision(state, timelines, config, boundary, lookback)
            cursor = boundary
    return _result(state, tape, config, scenario, start, end_exclusive, end_event)


def scan_oracle_cpu(
    tape: SerialTape,
    *,
    distances: tuple[int, ...],
    start: datetime,
    end_exclusive: datetime,
) -> tuple[OracleCandidateResult, ...]:
    """Exact CPU Oracle; each candidate starts flat at the requested boundary."""
    start = require_utc(start)
    end_exclusive = require_utc(end_exclusive)
    if start >= end_exclusive:
        raise ValueError("start must precede end_exclusive")
    start_event = _datetime_to_micros(start) * EVENT_ORDER_SCALE
    end_event = _datetime_to_micros(end_exclusive) * EVENT_ORDER_SCALE
    last_timestamp_exclusive = (tape.last_event // EVENT_ORDER_SCALE + 1) * EVENT_ORDER_SCALE
    if end_event > last_timestamp_exclusive:
        raise ValueError("oracle end exceeds the physical event tape")
    results: list[OracleCandidateResult] = []
    for (low, distance), timeline in tape.timelines(distances).items():
        entries, exits = timeline.cycle_events(start_event, end_event)
        if not entries:
            continue
        edge = Decimal(low + distance) / Decimal(low) - Decimal("1")
        results.append(
            OracleCandidateResult(
                low_tick=low,
                high_tick=low + distance,
                distance_ticks=distance,
                cycles=len(entries),
                gross_edge=edge,
                gross_edge_throughput=Decimal(len(entries)) * edge,
                entry_events=entries,
                exit_events=exits,
            )
        )
    return tuple(
        sorted(
            results,
            key=lambda item: (
                -item.cycles,
                -item.distance_ticks,
                item.low_tick,
                item.high_tick,
            ),
        )
    )


def _decision(
    state: _State,
    timelines: dict[tuple[int, int], CandidateTimeline],
    config: SerialModelConfig,
    now: int,
    lookback: int,
) -> None:
    if state.entry_event is not None:
        state.blocked_checks += 1
        return
    selected = _select(timelines, config, now - lookback, now)
    if config.strategy != SerialStrategy.IDLE_TRIGGERED:
        _switch(state, selected, now, allow_none=True)
        return
    idle_threshold = _minutes_to_events(config.idle_threshold_minutes or 0)
    if now - state.flat_since < idle_threshold or selected is None or selected == state.candidate:
        state.idle_challenger = None
        state.idle_confirmations = 0
        return
    current_score = _score(state.candidate, timelines, config, now - lookback, now)
    selected_score = _score(selected, timelines, config, now - lookback, now)
    required = current_score * (Decimal("1") + (config.switch_advantage or Decimal("0")))
    if selected_score <= 0 or (current_score > 0 and selected_score <= required):
        state.idle_challenger = None
        state.idle_confirmations = 0
        return
    if selected != state.idle_challenger:
        state.idle_challenger = selected
        state.idle_confirmations = 1
        return
    state.idle_confirmations += 1
    if state.idle_confirmations < (config.confirmation_checks or 1):
        return
    cooldown = _minutes_to_events(config.cooldown_minutes or 0)
    if state.last_change is not None and now - state.last_change < cooldown:
        return
    _switch(state, selected, now)
    state.idle_challenger = None
    state.idle_confirmations = 0


def _switch(
    state: _State,
    selected: tuple[int, int] | None,
    now: int,
    *,
    allow_none: bool = False,
) -> None:
    if (selected is None and not allow_none) or selected == state.candidate:
        return
    previous = state.candidate
    state.candidate = selected
    state.changes.append((now, previous, selected))
    state.last_change = now


def _advance(
    state: _State,
    timelines: dict[tuple[int, int], CandidateTimeline],
    config: SerialModelConfig,
    scenario: SerialScenarioConfig,
    start: int,
    end: int,
    *,
    recalculate_after_exit: bool,
) -> None:
    cursor = start
    lookback = _minutes_to_events(config.lookback_minutes)
    while state.candidate is not None:
        timeline = timelines[state.candidate]
        if state.entry_event is None:
            low_index = bisect_left(timeline.low_events, cursor)
            if low_index >= len(timeline.low_events) or timeline.low_events[low_index] >= end:
                return
            entry = timeline.low_events[low_index]
            low = _price(state.candidate[0], scenario.tick_size)
            fee_rate = scenario.maker_fee_per_leg
            affordable = state.cash / (low * (Decimal("1") + fee_rate))
            quantity = (affordable / scenario.quantity_step).to_integral_value(
                rounding=ROUND_DOWN
            ) * scenario.quantity_step
            notional = quantity * low
            if quantity <= 0 or notional < scenario.minimum_notional:
                return
            buy_fee = notional * fee_rate
            state.cash -= notional + buy_fee
            state.fees += buy_fee
            state.inventory = quantity
            state.inventory_cost = notional + buy_fee
            state.entry_event = entry
            cursor = entry + 1
        high_index = bisect_left(timeline.high_events, cursor)
        if high_index >= len(timeline.high_events) or timeline.high_events[high_index] >= end:
            return
        exit_event = timeline.high_events[high_index]
        low_tick, distance = state.candidate
        low = _price(low_tick, scenario.tick_size)
        high = _price(low_tick + distance, scenario.tick_size)
        proceeds = state.inventory * high
        sell_fee = proceeds * scenario.maker_fee_per_leg
        state.cash += proceeds - sell_fee
        state.fees += sell_fee
        state.realized_profit += proceeds - sell_fee - state.inventory_cost
        state.cycles.append(
            SerialCycle(
                entry_event=state.entry_event,
                exit_event=exit_event,
                entry_timestamp=_event_to_datetime(state.entry_event),
                exit_timestamp=_event_to_datetime(exit_event),
                low=low,
                high=high,
                quantity=state.inventory,
                buy_fee_quote=state.inventory_cost - state.inventory * low,
                sell_fee_quote=sell_fee,
            )
        )
        state.entry_event = None
        state.inventory = Decimal("0")
        state.inventory_cost = Decimal("0")
        state.flat_since = exit_event
        cursor = exit_event + 1
        if recalculate_after_exit:
            selected = _select(timelines, config, exit_event - lookback, exit_event)
            _switch(state, selected, exit_event, allow_none=True)


def _select(
    timelines: dict[tuple[int, int], CandidateTimeline],
    config: SerialModelConfig,
    start: int,
    end: int,
) -> tuple[int, int] | None:
    ranked: list[tuple[Decimal, int, int, int]] = []
    for candidate, timeline in timelines.items():
        cycles = timeline.contained_cycles(start, end)
        if cycles <= 0:
            continue
        edge = _gross_edge(candidate, config, timelines)
        if edge <= 0:
            continue
        low, distance = candidate
        ranked.append((Decimal(cycles) * edge, cycles, -low, -distance))
    if not ranked:
        return None
    _score_value, _cycles, negative_low, negative_distance = max(ranked)
    return -negative_low, -negative_distance


def _score(
    candidate: tuple[int, int] | None,
    timelines: dict[tuple[int, int], CandidateTimeline],
    config: SerialModelConfig,
    start: int,
    end: int,
) -> Decimal:
    if candidate is None or candidate not in timelines:
        return Decimal("0")
    cycles = timelines[candidate].contained_cycles(start, end)
    return Decimal(cycles) * _gross_edge(candidate, config, timelines)


def _gross_edge(
    candidate: tuple[int, int],
    config: SerialModelConfig,
    timelines: dict[tuple[int, int], CandidateTimeline],
) -> Decimal:
    # Selection compares candidates on the tape's integer price scale. The constant tick
    # cancels in HIGH / LOW, so execution/scenario parameters cannot change MODEL_HASH.
    if candidate not in timelines:  # pragma: no cover - guarded by callers
        return Decimal("0")
    low, distance = candidate
    if distance not in config.distances:
        return Decimal("0")
    return Decimal(low + distance) / Decimal(low) - Decimal("1")


def _result(
    state: _State,
    tape: SerialTape,
    config: SerialModelConfig,
    scenario: SerialScenarioConfig,
    start: datetime,
    end: datetime,
    end_event: int,
) -> SerialReplayResult:
    last_price = _price(tape.last_price_before(end_event), tape.tick_size)
    marked = state.cash + state.inventory * last_price
    unrealized = (
        state.inventory * last_price - state.inventory_cost
        if state.entry_event is not None
        else Decimal("0")
    )
    counts = Counter(item.exit_timestamp.date() for item in state.cycles)
    calendar = _interval_dates(start, end)
    daily = {day: counts[day] for day in calendar}
    reversals = 0
    window = _minutes_to_events(24 * 60)
    for index in range(2, len(state.changes)):
        current = state.changes[index]
        prior = state.changes[index - 1]
        earlier = state.changes[index - 2]
        if (
            current[0] - earlier[0] <= window
            and earlier[2] is not None
            and earlier[2] == current[2]
            and prior[2] != current[2]
        ):
            reversals += 1
    active_low = (
        _price(state.candidate[0], scenario.tick_size) if state.candidate is not None else None
    )
    active_high = (
        _price(state.candidate[0] + state.candidate[1], scenario.tick_size)
        if state.candidate is not None
        else None
    )
    open_at = _event_to_datetime(state.entry_event) if state.entry_event is not None else None
    return SerialReplayResult(
        model_id=config.model_id,
        model_hash=config.model_hash,
        scenario_id=scenario.scenario_id,
        scenario_hash=scenario.scenario_hash,
        start=start,
        end_exclusive=end,
        initial_quote=scenario.initial_quote,
        final_cash=state.cash,
        final_inventory=state.inventory,
        last_price=last_price,
        final_marked_equity=marked,
        return_fraction=marked / scenario.initial_quote - Decimal("1"),
        realized_profit=state.realized_profit,
        unrealized_profit=unrealized,
        total_fees=state.fees,
        completed_cycles=len(state.cycles),
        daily_cycles=daily,
        zero_cycle_days=sum(value == 0 for value in daily.values()),
        reselection_count=len(state.changes),
        blocked_reselection_checks=state.blocked_checks,
        cooldown_violations=0,
        reversal_24h_count=reversals,
        active_low=active_low,
        active_high=active_high,
        open_entry_timestamp=open_at,
        open_holding_seconds=(
            Decimal((end - open_at).total_seconds()) if open_at is not None else None
        ),
        open_cycle_censored=open_at is not None,
        execution_class=scenario.execution_class,
        cycles=tuple(state.cycles),
    )


def symmetric_break_even_fee(low: Decimal, high: Decimal) -> Decimal:
    if low <= 0 or high <= low:
        raise ValueError("break-even requires 0 < low < high")
    return (high - low) / (high + low)


def _price(ticks: int, tick_size: Decimal) -> Decimal:
    return Decimal(ticks) * tick_size


def _minutes_to_events(minutes: int) -> int:
    return minutes * 60 * MICROS_PER_SECOND * EVENT_ORDER_SCALE


def _datetime_to_micros(value: datetime) -> int:
    return int(value.timestamp()) * MICROS_PER_SECOND + value.microsecond


def _event_to_datetime(value: int) -> datetime:
    micros = value // EVENT_ORDER_SCALE
    seconds, remainder = divmod(micros, MICROS_PER_SECOND)
    return datetime.fromtimestamp(seconds, UTC).replace(microsecond=remainder)


def _interval_dates(start: datetime, end: datetime) -> tuple[date, ...]:
    last = (end - timedelta(microseconds=1)).date()
    return tuple(
        start.date() + timedelta(days=index) for index in range((last - start.date()).days + 1)
    )
