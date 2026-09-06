from __future__ import annotations

from array import array
from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from crypto_strategy_lab.domain import canonical_hash, require_utc
from crypto_strategy_lab.microstructure.data import (
    HistoryManifest,
    iter_history,
)

EVENT_ORDER_SCALE = 4096
MICROS_PER_SECOND = 1_000_000
SERIAL_TAPE_QUANTUM = Decimal("0.00001")
USDCUSDT_TICK_CATALOG_SOURCE: Final[Literal["BINANCE_OFFICIAL"]] = "BINANCE_OFFICIAL"
USDCUSDT_TICK_CHANGE = datetime(2026, 4, 14, 5, tzinfo=UTC)
USDCUSDT_TICK_SOURCE_URL = (
    "https://www.binance.com/en/support/announcement/detail/1f1ee792db2d445eb967aa09f6c05138"
)
USDCUSDT_TICK_SOURCE_PUBLISHED = datetime(2026, 4, 7, tzinfo=UTC)
USDCUSDT_FINE_GRID_OBSERVED_FROM = datetime(2026, 4, 14, 4, 59, 57, 245631, tzinfo=UTC)


class TickPeriod(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: datetime
    end_exclusive: datetime | None = None
    tick_size: Decimal = Field(gt=0)
    evidence_class: str = Field(default="DECLARED_CATALOG_PERIOD", min_length=1)

    @model_validator(mode="after")
    def validate_period(self) -> TickPeriod:
        require_utc(self.start)
        if self.end_exclusive is not None:
            require_utc(self.end_exclusive)
            if self.start >= self.end_exclusive:
                raise ValueError("tick period must have positive duration")
        return self


class TickTransition(BaseModel):
    """Short exchange rollout window in which either adjacent grid is valid."""

    model_config = ConfigDict(frozen=True)

    start: datetime
    end_exclusive: datetime
    allowed_tick_sizes: tuple[Decimal, ...]
    evidence: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_transition(self) -> TickTransition:
        require_utc(self.start)
        require_utc(self.end_exclusive)
        if self.start >= self.end_exclusive:
            raise ValueError("tick transition must have positive duration")
        if not self.allowed_tick_sizes or any(item <= 0 for item in self.allowed_tick_sizes):
            raise ValueError("tick transition requires positive allowed grids")
        return self


class TickCatalog(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: Literal["USDCUSDT"] = "USDCUSDT"
    periods: tuple[TickPeriod, ...]
    source: Literal["BINANCE_OFFICIAL"] = USDCUSDT_TICK_CATALOG_SOURCE
    source_url: str = USDCUSDT_TICK_SOURCE_URL
    source_published_at: datetime = USDCUSDT_TICK_SOURCE_PUBLISHED
    price_quantum: Decimal = Field(default=SERIAL_TAPE_QUANTUM, gt=0)
    transitions: tuple[TickTransition, ...] = ()

    @model_validator(mode="after")
    def validate_periods(self) -> TickCatalog:
        if not self.periods:
            raise ValueError("tick catalog cannot be empty")
        for index, period in enumerate(self.periods):
            if index and self.periods[index - 1].end_exclusive != period.start:
                raise ValueError("tick catalog contains a gap or overlap")
        if self.periods[-1].end_exclusive is not None:
            raise ValueError("tick catalog must have an open-ended final period")
        for period in self.periods:
            scaled = period.tick_size / self.price_quantum
            if scaled != scaled.to_integral_value():
                raise ValueError("catalog tick is not representable on its price quantum")
        for index, transition in enumerate(self.transitions):
            if index and self.transitions[index - 1].end_exclusive > transition.start:
                raise ValueError("tick transition windows overlap")
            if any(
                item not in {period.tick_size for period in self.periods}
                for item in transition.allowed_tick_sizes
            ):
                raise ValueError("transition grid is absent from the tick periods")
        require_utc(self.source_published_at)
        return self

    @property
    def catalog_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))

    def tick_size_at(self, timestamp: datetime) -> Decimal:
        moment = require_utc(timestamp)
        for period in self.periods:
            if moment >= period.start and (
                period.end_exclusive is None or moment < period.end_exclusive
            ):
                return period.tick_size
        raise ValueError("timestamp is outside the tick catalog")

    def is_price_compatible(self, timestamp: datetime, price: Decimal) -> bool:
        """Allow the observed transition window to contain either exchange grid."""
        moment = require_utc(timestamp)
        grids: tuple[Decimal, ...] = (self.tick_size_at(moment),)
        for transition in self.transitions:
            if transition.start <= moment < transition.end_exclusive:
                grids = transition.allowed_tick_sizes
                break
        return any((price / grid).to_integral_value() == price / grid for grid in grids)

    def transition_at(self, timestamp: datetime) -> TickTransition | None:
        moment = require_utc(timestamp)
        return next(
            (item for item in self.transitions if item.start <= moment < item.end_exclusive),
            None,
        )

    def allowed_tick_sizes_at(self, timestamp: datetime) -> tuple[Decimal, ...]:
        transition = self.transition_at(timestamp)
        if transition is not None:
            return transition.allowed_tick_sizes
        return (self.tick_size_at(timestamp),)

    def tick_size_at_decision(
        self,
        timestamp: datetime,
        *,
        decision_event: int,
        observed_tick_evidence_event: int | None,
    ) -> Decimal:
        """Resolve a causal selection grid without reading a future rollout event."""
        moment = require_utc(timestamp)
        tick_size = self.tick_size_at(moment)
        for transition in self.transitions:
            if transition.start <= moment < transition.end_exclusive:
                if (
                    observed_tick_evidence_event is not None
                    and decision_event > observed_tick_evidence_event
                ):
                    return min(transition.allowed_tick_sizes)
                break
        return tick_size

    def absolute_distances(self, model_distances: tuple[int, ...]) -> tuple[int, ...]:
        """Convert exchange-tick counts to distinct integer price-quantum distances."""
        return tuple(
            sorted(
                {
                    int(period.tick_size / self.price_quantum) * distance
                    for period in self.periods
                    for distance in model_distances
                }
            )
        )

    def absolute_distances_at(
        self, timestamp: datetime, model_distances: tuple[int, ...]
    ) -> tuple[int, ...]:
        tick_size = self.tick_size_at(timestamp)
        multiplier = tick_size / self.price_quantum
        if multiplier != multiplier.to_integral_value():  # pragma: no cover - model validation
            raise ValueError("tick is not representable on the catalog quantum")
        return tuple(int(multiplier) * distance for distance in model_distances)

    def validate_interval(self, start: datetime, end_exclusive: datetime) -> None:
        start = require_utc(start)
        end_exclusive = require_utc(end_exclusive)
        if start >= end_exclusive:
            raise ValueError("tick catalog interval must be positive")
        cursor = start
        for period in self.periods:
            if cursor < period.start:
                break
            if period.end_exclusive is None:
                cursor = end_exclusive
                break
            if cursor < period.end_exclusive:
                cursor = min(end_exclusive, period.end_exclusive)
            if cursor >= end_exclusive:
                break
        if cursor < end_exclusive:
            raise ValueError("tick catalog does not cover requested interval")


USDCUSDT_TICK_CATALOG = TickCatalog(
    periods=(
        TickPeriod(
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end_exclusive=USDCUSDT_TICK_CHANGE,
            tick_size=Decimal("0.0001"),
            evidence_class="OLD_GRID_ASSUMPTION_COMPATIBLE_WITH_OBSERVED_TRADES",
        ),
        TickPeriod(
            start=USDCUSDT_TICK_CHANGE,
            tick_size=Decimal("0.00001"),
            evidence_class="OFFICIAL_COMPLETION_BOUND",
        ),
    ),
    transitions=(
        TickTransition(
            start=USDCUSDT_FINE_GRID_OBSERVED_FROM,
            end_exclusive=USDCUSDT_TICK_CHANGE,
            allowed_tick_sizes=(Decimal("0.0001"), Decimal("0.00001")),
            evidence=(
                "validated trade 413387230 first uses the fine grid before the official "
                "rollout-complete boundary"
            ),
        ),
    ),
)


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
    distance_semantics: Literal["ONE_EXCHANGE_TICK_AT_LEVEL_SELECTION"] | None = None
    selection_moment: Literal["AT_LEVEL_SELECTION"] | None = None
    tick_source: Literal["BINANCE_ANNOUNCEMENT_PLUS_CAUSAL_TRADE_PREFIX"] | None = None
    tick_evidence_class: Literal["OBSERVED_ACCEPTED_GRID"] | None = None
    selected_levels_remain_absolute: bool | None = None

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
        historical_tick_fields = (
            self.distance_semantics,
            self.selection_moment,
            self.tick_source,
            self.tick_evidence_class,
            self.selected_levels_remain_absolute,
        )
        if any(item is not None for item in historical_tick_fields) and any(
            item is None for item in historical_tick_fields
        ):
            raise ValueError("historical tick semantics must be specified as one complete set")
        if self.distance_semantics is not None and not self.selected_levels_remain_absolute:
            raise ValueError("historical tick models must keep selected levels absolute")
        return self

    @property
    def model_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"model_id", "parent_model_id"})
        if self.distance_semantics is None:
            for field_name in (
                "distance_semantics",
                "selection_moment",
                "tick_source",
                "tick_evidence_class",
                "selected_levels_remain_absolute",
            ):
                payload.pop(field_name)
        return canonical_hash(payload)


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
    historical_tick_catalog_hash: str | None = None
    historical_tick_source_url: str | None = None
    historical_tick_policy: (
        Literal["CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND"] | None
    ) = None

    @model_validator(mode="after")
    def prohibit_forced_close(self) -> SerialScenarioConfig:
        if self.forced_terminal_liquidation:
            raise ValueError("the reference strategy cannot force terminal liquidation")
        catalog_fields = (
            self.historical_tick_catalog_hash,
            self.historical_tick_source_url,
            self.historical_tick_policy,
        )
        if any(item is not None for item in catalog_fields) and any(
            item is None for item in catalog_fields
        ):
            raise ValueError("historical tick scenario provenance must be complete")
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


def preregistered_corrected_block() -> tuple[SerialModelConfig, ...]:
    """Corrected equivalents with an internal M005→M008 lineage."""
    originals = preregistered_first_block()
    corrected: list[SerialModelConfig] = []
    for index, original in enumerate(originals, start=5):
        parent = f"M{index - 1:03d}" if index > 5 else None
        corrected.append(
            original.model_copy(
                update={
                    "model_id": f"M{index:03d}",
                    "parent_model_id": parent,
                    "distance_semantics": "ONE_EXCHANGE_TICK_AT_LEVEL_SELECTION",
                    "selection_moment": "AT_LEVEL_SELECTION",
                    "tick_source": "BINANCE_ANNOUNCEMENT_PLUS_CAUSAL_TRADE_PREFIX",
                    "tick_evidence_class": "OBSERVED_ACCEPTED_GRID",
                    "selected_levels_remain_absolute": True,
                }
            )
        )
    return tuple(corrected)


class SerialCycle(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_event: int
    exit_event: int
    entry_timestamp: datetime
    exit_timestamp: datetime
    low: Decimal
    high: Decimal
    tick_at_selection: Decimal | None = None
    quantity: Decimal
    buy_fee_quote: Decimal
    sell_fee_quote: Decimal


class SelectionChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    event: int
    timestamp: datetime
    previous_low: Decimal | None
    previous_high: Decimal | None
    selected_low: Decimal | None
    selected_high: Decimal | None
    previous_tick_at_selection: Decimal | None = None
    selected_tick_at_selection: Decimal | None = None


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
    open_entry_event: int | None
    open_entry_timestamp: datetime | None
    open_entry_price: Decimal | None
    open_buy_fee_quote: Decimal | None
    open_holding_seconds: Decimal | None
    open_cycle_censored: bool
    execution_class: str
    capacity_capped_final_capital: None = None
    selection_changes: tuple[SelectionChange, ...]
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
    low_events: Any
    high_events: Any
    cycle_entries: array[int] = field(default_factory=lambda: array("q"))
    cycle_exits: array[int] = field(default_factory=lambda: array("q"))

    def build(self) -> None:
        after = -1
        low_index = high_index = 0
        while low_index < len(self.low_events):
            low_index = bisect_right(self.low_events, after, lo=low_index)
            if low_index >= len(self.low_events):
                break
            entry = self.low_events[low_index]
            high_index = bisect_right(self.high_events, entry, lo=high_index)
            if high_index >= len(self.high_events):
                break
            exit_event = self.high_events[high_index]
            self.cycle_entries.append(entry)
            self.cycle_exits.append(exit_event)
            after = exit_event
            low_index += 1
            high_index += 1

    def contained_cycles(self, start: int, end: int) -> int:
        if start >= end or not self.cycle_entries:
            return 0
        first_global = bisect_left(self.cycle_entries, start)
        first_before_start = first_global - 1
        if first_before_start >= 0 and self.cycle_exits[first_before_start] >= start:
            # At most one global cycle can cross the left boundary.  A fresh
            # causal window may reuse its exit with the first LOW after start.
            crossing_exit = self.cycle_exits[first_before_start]
            first_window_low = bisect_left(self.low_events, start)
            if (
                first_window_low < len(self.low_events)
                and self.low_events[first_window_low] < crossing_exit
            ):
                first_count = int(crossing_exit < end)
                suffix_end = bisect_left(self.cycle_exits, end, lo=first_global)
                return first_count + max(0, suffix_end - first_global)
        suffix_end = bisect_left(self.cycle_exits, end, lo=first_global)
        return max(0, suffix_end - first_global)

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
    occurrences: dict[int, Any]
    events: Any
    price_ticks: Any
    last_event: int
    last_price_tick: int
    observed_tick_evidence_event: int | None = None
    tape_hash: str | None = None
    tape_cache_key: str | None = None

    @classmethod
    def from_events(
        cls,
        events: Iterable[tuple[datetime, Decimal]],
        *,
        tick_size: Decimal,
        tick_catalog: TickCatalog | None = None,
    ) -> SerialTape:
        if not events:
            raise ValueError("event tape cannot be empty")
        if tick_size <= 0:
            raise ValueError("tape price quantum must be positive")
        occurrences: dict[int, array[int]] = {}
        encoded_events = array("q")
        price_ticks = array("i")
        previous_timestamp: datetime | None = None
        previous_event = -1
        ordinal = 0
        last_price = 0
        observed_tick_evidence_event: int | None = None
        for timestamp, price in events:
            normalized = require_utc(timestamp)
            if previous_timestamp is not None and normalized < previous_timestamp:
                raise ValueError("events must be chronological")
            ordinal = ordinal + 1 if normalized == previous_timestamp else 0
            if ordinal >= EVENT_ORDER_SCALE:
                raise ValueError("too many events share one timestamp")
            if tick_catalog is not None and not tick_catalog.is_price_compatible(normalized, price):
                raise ValueError("event price is incompatible with the historical tick catalog")
            scaled = price / tick_size
            if scaled != scaled.to_integral_value():
                raise ValueError(f"price {price} is off the configured tape price quantum")
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
            if tick_catalog is not None and observed_tick_evidence_event is None:
                scheduled_grid = tick_catalog.tick_size_at(normalized)
                scaled_to_scheduled = price / scheduled_grid
                if scaled_to_scheduled != scaled_to_scheduled.to_integral_value():
                    observed_tick_evidence_event = event
        return cls(
            tick_size,
            occurrences,
            encoded_events,
            price_ticks,
            previous_event,
            last_price,
            observed_tick_evidence_event,
        )

    def last_price_before(self, end_exclusive: int) -> int:
        index = bisect_left(self.events, end_exclusive) - 1
        if index < 0:
            raise ValueError("replay interval has no observed mark price")
        return int(self.price_ticks[index])

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
    tick_catalog: TickCatalog | None = None,
) -> SerialTape:
    """Load one already-verified, gap-free manifest interval into integer ticks."""
    start = require_utc(start)
    end_exclusive = require_utc(end_exclusive)
    if tick_catalog is not None:
        tick_catalog.validate_interval(start, end_exclusive)
        if tick_catalog.price_quantum != tick_size:
            raise ValueError("tape price quantum must match the tick catalog")
    if manifest.symbol != "USDCUSDT":
        raise ValueError("the active serial campaign accepts only USDCUSDT")
    if manifest.integrity_status != "VALID" or manifest.invalidity_reasons:
        raise ValueError("serial replay requires a VALID history manifest")
    if start < manifest.first_timestamp:
        raise ValueError("requested tape start precedes validated history")
    physical_end_exclusive = manifest.last_timestamp + timedelta(microseconds=1)
    if end_exclusive > physical_end_exclusive:
        raise ValueError("requested tape end exceeds validated history")

    def events() -> Iterator[tuple[datetime, Decimal]]:
        for event in iter_history(manifest, start=start, end_exclusive=end_exclusive):
            yield event.timestamp, event.price

    return SerialTape.from_events(events(), tick_size=tick_size, tick_catalog=tick_catalog)


@dataclass
class _State:
    cash: Decimal
    candidate: tuple[int, int] | None = None
    candidate_tick_size: Decimal | None = None
    entry_event: int | None = None
    inventory: Decimal = Decimal("0")
    inventory_cost: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    realized_profit: Decimal = Decimal("0")
    cycles: list[SerialCycle] = field(default_factory=list)
    changes: list[
        tuple[
            int,
            tuple[int, int] | None,
            Decimal | None,
            tuple[int, int] | None,
            Decimal | None,
        ]
    ] = field(default_factory=list)
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
    tick_catalog: TickCatalog | None = None,
) -> SerialReplayResult:
    start = require_utc(start)
    end_exclusive = require_utc(end_exclusive)
    if start >= end_exclusive:
        raise ValueError("start must precede end_exclusive")
    if scenario.tick_size != tape.tick_size:
        raise ValueError("scenario tick size must match the physical event tape")
    historical_ticks = config.distance_semantics is not None
    if historical_ticks:
        if tick_catalog is None:
            raise ValueError("historical tick model requires a verified tick catalog")
        tick_catalog.validate_interval(start, end_exclusive)
        if tick_catalog.price_quantum != tape.tick_size:
            raise ValueError("tick catalog quantum must match the physical event tape")
        if scenario.historical_tick_catalog_hash != tick_catalog.catalog_hash:
            raise ValueError("scenario does not bind the supplied historical tick catalog")
    elif tick_catalog is not None:
        raise ValueError("legacy fixed-grid model cannot silently use a historical tick catalog")
    start_event = _datetime_to_micros(start) * EVENT_ORDER_SCALE
    end_event = _datetime_to_micros(end_exclusive) * EVENT_ORDER_SCALE
    last_timestamp_exclusive = (tape.last_event // EVENT_ORDER_SCALE + 1) * EVENT_ORDER_SCALE
    if end_event > last_timestamp_exclusive:
        raise ValueError("replay end exceeds the physical event tape")
    absolute_distances = (
        tick_catalog.absolute_distances(config.distances)
        if tick_catalog is not None
        else config.distances
    )
    timelines = tape.timelines(absolute_distances)
    lookback = _minutes_to_events(config.lookback_minutes)
    state = _State(cash=scenario.initial_quote, flat_since=start_event)
    selection_tick_size, eligible_distances, grid_multiple = _selection_grid(
        config,
        tick_catalog,
        start_event,
        tape.tick_size,
        tape.observed_tick_evidence_event,
    )
    selected = _select(
        timelines,
        config,
        start_event - lookback,
        start_event,
        eligible_distances=eligible_distances,
        grid_multiple=grid_multiple,
    )
    state.candidate = selected
    state.candidate_tick_size = selection_tick_size if selected is not None else None
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
            tick_catalog=tick_catalog,
            tape_quantum=tape.tick_size,
            observed_tick_evidence_event=tape.observed_tick_evidence_event,
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
                tick_catalog=tick_catalog,
                tape_quantum=tape.tick_size,
                observed_tick_evidence_event=tape.observed_tick_evidence_event,
            )
            if boundary < end_event:
                _decision(
                    state,
                    timelines,
                    config,
                    boundary,
                    lookback,
                    tick_catalog=tick_catalog,
                    tape_quantum=tape.tick_size,
                    observed_tick_evidence_event=tape.observed_tick_evidence_event,
                )
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
        high_tick = low + distance
        edge = Decimal(high_tick) / Decimal(low) - Decimal("1")
        results.append(
            OracleCandidateResult(
                low_tick=low,
                high_tick=high_tick,
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
    *,
    tick_catalog: TickCatalog | None,
    tape_quantum: Decimal,
    observed_tick_evidence_event: int | None,
) -> None:
    if state.entry_event is not None:
        state.blocked_checks += 1
        return
    tick_size, eligible_distances, grid_multiple = _selection_grid(
        config,
        tick_catalog,
        now,
        tape_quantum,
        observed_tick_evidence_event,
    )
    selected = _select(
        timelines,
        config,
        now - lookback,
        now,
        eligible_distances=eligible_distances,
        grid_multiple=grid_multiple,
    )
    if config.strategy != SerialStrategy.IDLE_TRIGGERED:
        _switch(state, selected, tick_size, now, allow_none=True)
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
    _switch(state, selected, tick_size, now)
    state.idle_challenger = None
    state.idle_confirmations = 0


def _switch(
    state: _State,
    selected: tuple[int, int] | None,
    selected_tick_size: Decimal | None,
    now: int,
    *,
    allow_none: bool = False,
) -> None:
    if (selected is None and not allow_none) or selected == state.candidate:
        return
    previous = state.candidate
    previous_tick_size = state.candidate_tick_size
    state.candidate = selected
    state.candidate_tick_size = selected_tick_size if selected is not None else None
    state.changes.append((now, previous, previous_tick_size, selected, state.candidate_tick_size))
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
    tick_catalog: TickCatalog | None,
    tape_quantum: Decimal,
    observed_tick_evidence_event: int | None,
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
            low = _price(state.candidate[0], tape_quantum)
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
        low = _price(low_tick, tape_quantum)
        high = _price(low_tick + distance, tape_quantum)
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
                tick_at_selection=state.candidate_tick_size,
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
            tick_size, eligible_distances, grid_multiple = _selection_grid(
                config,
                tick_catalog,
                exit_event,
                tape_quantum,
                observed_tick_evidence_event,
            )
            selected = _select(
                timelines,
                config,
                exit_event - lookback,
                exit_event,
                eligible_distances=eligible_distances,
                grid_multiple=grid_multiple,
            )
            _switch(state, selected, tick_size, exit_event, allow_none=True)


def _select(
    timelines: dict[tuple[int, int], CandidateTimeline],
    config: SerialModelConfig,
    start: int,
    end: int,
    *,
    eligible_distances: tuple[int, ...] | None = None,
    grid_multiple: int | None = None,
) -> tuple[int, int] | None:
    ranked: list[tuple[Decimal, int, int, int]] = []
    for candidate, timeline in timelines.items():
        if eligible_distances is not None and candidate[1] not in eligible_distances:
            continue
        if grid_multiple is not None and (
            candidate[0] % grid_multiple != 0 or (candidate[0] + candidate[1]) % grid_multiple != 0
        ):
            continue
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
            and earlier[3] is not None
            and earlier[3] == current[3]
            and prior[3] != current[3]
        ):
            reversals += 1
    active_low = _price(state.candidate[0], tape.tick_size) if state.candidate is not None else None
    active_high = (
        _price(_high_tick(state.candidate), tape.tick_size) if state.candidate is not None else None
    )
    open_at = _event_to_datetime(state.entry_event) if state.entry_event is not None else None
    open_price = active_low if state.entry_event is not None else None
    open_buy_fee = (
        state.inventory_cost - state.inventory * open_price
        if state.entry_event is not None and open_price is not None
        else None
    )
    changes = tuple(
        SelectionChange(
            event=event,
            timestamp=_event_to_datetime(event),
            previous_low=(_price(previous[0], tape.tick_size) if previous is not None else None),
            previous_high=(
                _price(_high_tick(previous), tape.tick_size) if previous is not None else None
            ),
            selected_low=(_price(selected[0], tape.tick_size) if selected is not None else None),
            selected_high=(
                _price(_high_tick(selected), tape.tick_size) if selected is not None else None
            ),
            previous_tick_at_selection=previous_tick_size,
            selected_tick_at_selection=selected_tick_size,
        )
        for event, previous, previous_tick_size, selected, selected_tick_size in state.changes
    )
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
        open_entry_event=state.entry_event,
        open_entry_timestamp=open_at,
        open_entry_price=open_price,
        open_buy_fee_quote=open_buy_fee,
        open_holding_seconds=(
            Decimal((end - open_at).total_seconds()) if open_at is not None else None
        ),
        open_cycle_censored=open_at is not None,
        execution_class=scenario.execution_class,
        selection_changes=changes,
        cycles=tuple(state.cycles),
    )


def symmetric_break_even_fee(low: Decimal, high: Decimal) -> Decimal:
    if low <= 0 or high <= low:
        raise ValueError("break-even requires 0 < low < high")
    return (high - low) / (high + low)


def _selection_grid(
    config: SerialModelConfig,
    tick_catalog: TickCatalog | None,
    decision_event: int,
    tape_quantum: Decimal,
    observed_tick_evidence_event: int | None,
) -> tuple[Decimal | None, tuple[int, ...] | None, int | None]:
    if config.distance_semantics is None:
        return None, None, None
    if tick_catalog is None:  # pragma: no cover - checked at replay entry
        raise ValueError("historical tick model requires a verified tick catalog")
    if tick_catalog.price_quantum != tape_quantum:
        raise ValueError("tick catalog quantum must match the tape")
    timestamp = _event_to_datetime(decision_event)
    tick_size = tick_catalog.tick_size_at_decision(
        timestamp,
        decision_event=decision_event,
        observed_tick_evidence_event=observed_tick_evidence_event,
    )
    multiplier = tick_size / tick_catalog.price_quantum
    if multiplier != multiplier.to_integral_value():  # pragma: no cover - catalog validation
        raise ValueError("selection tick is not representable on the tape quantum")
    grid_multiple = int(multiplier)
    return (
        tick_size,
        tuple(grid_multiple * item for item in config.distances),
        grid_multiple,
    )


def _price(ticks: int, tick_size: Decimal) -> Decimal:
    return Decimal(ticks) * tick_size


def _high_tick(
    candidate: tuple[int, int] | None,
) -> int:
    if candidate is None:
        raise ValueError("candidate is required")
    return candidate[0] + candidate[1]


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


__all__ = [
    "USDCUSDT_TICK_CATALOG",
    "USDCUSDT_TICK_CATALOG_SOURCE",
    "USDCUSDT_TICK_CHANGE",
    "USDCUSDT_TICK_SOURCE_PUBLISHED",
    "USDCUSDT_TICK_SOURCE_URL",
    "CandidateTimeline",
    "SerialCycle",
    "SerialModelConfig",
    "SerialReplayResult",
    "SerialScenarioConfig",
    "SerialStrategy",
    "SerialTape",
    "TickCatalog",
    "TickPeriod",
    "preregistered_corrected_block",
    "preregistered_first_block",
    "replay_serial_model",
    "scan_oracle_cpu",
    "symmetric_break_even_fee",
]
