"""Segregated recovery accounting for historical M007 scenario research only."""

from bisect import bisect_left
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import ROUND_DOWN, Decimal, localcontext
from itertools import product
from typing import Any

from crypto_strategy_lab.domain import canonical_hash

from .serial_replay import (
    EVENT_ORDER_SCALE,
    MICROS_PER_SECOND,
    CandidateTimeline,
    SerialCycle,
    SerialModelConfig,
    SerialScenarioConfig,
    SerialTape,
    TickCatalog,
    _event_to_datetime,
    _minutes_to_events,
    _score,
    _select,
    _selection_grid,
    _State,
    _switch,
)

D = Decimal
HOUR = 3600 * MICROS_PER_SECOND * EVENT_ORDER_SCALE
INITIAL_OPERATING = D("100")
INITIAL_RESERVE = D("5")
ZERO = D("0")
RESERVE_SKIM_RATE = D("0.02")
LEDGER_PRECISION = 128
DESTINATION_MIN_CYCLES_1H = 1
DESTINATION_MIN_CYCLES_4H = 3
ORIGINAL_MAX_CYCLES_1H = 0


@dataclass(frozen=True)
class ReserveConfig:
    skim_rate: Decimal
    lock_hours: int
    max_loss_bps: Decimal
    reserve_floor: Decimal = ZERO
    initial_operating: Decimal = INITIAL_OPERATING
    initial_reserve: Decimal = INITIAL_RESERVE

    def __post_init__(self) -> None:
        if self.initial_operating != D("100"):
            raise ValueError("INITIAL_CAPITAL_INVARIANT_VIOLATION")
        if self.initial_reserve != D("5"):
            raise ValueError("INITIAL_RESERVE_INVARIANT_VIOLATION")
        if self.skim_rate != RESERVE_SKIM_RATE or self.lock_hours <= 0:
            raise ValueError("INVALID_RESERVE_CONFIG")
        if not self.max_loss_bps.is_finite() or self.max_loss_bps <= 0:
            raise ValueError("INVALID_RELEASE_LOSS_CAP")
        if not self.reserve_floor.is_finite() or not D(0) <= self.reserve_floor <= D("5"):
            raise ValueError("INVALID_RESERVE_FLOOR")

    @property
    def scenario_id(self) -> str:
        return f"RRV2_H{self.lock_hours}_B{self.max_loss_bps:g}_F{self.reserve_floor:g}"

    def payload(self) -> dict[str, Any]:
        return {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in asdict(self).items()
        }


def grid_configs() -> tuple[ReserveConfig, ...]:
    return tuple(
        ReserveConfig(RESERVE_SKIM_RATE, hours, D(loss), D(floor))
        for hours, loss, floor in product((1, 4, 12), ("2", "5", "10"), ("0", "2.5"))
    )


def _event_count(events: Any, start: int, end: int) -> int:
    return bisect_left(events, end) - bisect_left(events, start)


def _activity(timeline: CandidateTimeline, boundary: int) -> dict[str, Any]:
    exit_index = bisect_left(timeline.cycle_exits, boundary) - 1
    last_exit = int(timeline.cycle_exits[exit_index]) if exit_index >= 0 else None
    return {
        "cycles_1h": timeline.contained_cycles(boundary - HOUR, boundary),
        "cycles_4h": timeline.contained_cycles(boundary - 4 * HOUR, boundary),
        "cycles_24h": timeline.contained_cycles(boundary - 24 * HOUR, boundary),
        "low_visits_1h": _event_count(timeline.low_events, boundary - HOUR, boundary),
        "low_visits_4h": _event_count(timeline.low_events, boundary - 4 * HOUR, boundary),
        "low_visits_24h": _event_count(timeline.low_events, boundary - 24 * HOUR, boundary),
        "high_visits_1h": _event_count(timeline.high_events, boundary - HOUR, boundary),
        "high_visits_4h": _event_count(timeline.high_events, boundary - 4 * HOUR, boundary),
        "high_visits_24h": _event_count(timeline.high_events, boundary - 24 * HOUR, boundary),
        "last_complete_cycle_event": last_exit,
        "seconds_since_last_complete_cycle": (
            str(D(boundary - last_exit) / D(HOUR) * 3600) if last_exit is not None else None
        ),
    }


class RecoveryReserveRuntime:
    def __init__(
        self,
        config: ReserveConfig,
        parent: SerialModelConfig,
        scenario: SerialScenarioConfig,
        tape: SerialTape,
        timelines: dict[tuple[int, int], CandidateTimeline],
        tick_catalog: TickCatalog | None,
    ) -> None:
        self.config, self.parent, self.scenario = config, parent, scenario
        self.tape, self.timelines, self.tick_catalog = tape, timelines, tick_catalog
        self.reserve = config.initial_reserve
        self.total_skim = D(0)
        self.releases: list[dict[str, Any]] = []
        self.evaluations: Counter[str] = Counter()
        self.replenishments: list[dict[str, Any]] = []
        self.cycles_settled = 0

    def schedule(self, entry: int, previous: int | None) -> int:
        if previous is not None:
            return previous + HOUR
        return entry // EVENT_ORDER_SCALE * EVENT_ORDER_SCALE + self.config.lock_hours * HOUR

    def cycle_settled(self, state: _State, cycle: SerialCycle) -> None:
        with localcontext() as context:
            context.prec = LEDGER_PRECISION
            profit = (
                cycle.quantity * cycle.high
                - cycle.sell_fee_quote
                - (cycle.quantity * cycle.low + cycle.buy_fee_quote)
            )
            skim = max(D(0), profit) * self.config.skim_rate
            if skim > state.cash:
                raise ValueError("RESERVE_SKIM_CASH_RECONCILIATION_FAILED")
            state.cash -= skim
            self.reserve += skim
            self.total_skim += skim
        self.cycles_settled += 1
        for target in self.replenishments:
            if target["replenished_event"] is None and self.reserve >= D(target["target_balance"]):
                target["replenished_event"] = int(cycle.exit_event)
                with localcontext() as context:
                    context.prec = LEDGER_PRECISION
                    target["time_to_replenish_seconds"] = str(
                        D(cycle.exit_event - target["release_event"]) / D(HOUR) * 3600
                    )
                target["cycles_to_replenish"] = self.cycles_settled - target["cycles_at_release"]

    def _keep(self, reason: str) -> bool:
        self.evaluations[reason] += 1
        return False

    def __call__(self, state: _State, event: int) -> bool:
        event = int(event)
        self.evaluations["TOTAL"] += 1
        if state.entry_event is None or state.candidate is None:
            return self._keep("NO_POSITION")
        boundary = event // EVENT_ORDER_SCALE * EVENT_ORDER_SCALE
        if boundary < self.schedule(state.entry_event, None):
            return self._keep("AGE")
        index = bisect_left(self.tape.events, boundary) - 1
        if index < 0:
            return self._keep("NO_CAUSAL_PRICE")
        price = D(int(self.tape.price_ticks[index])) * self.tape.tick_size
        with localcontext() as context:
            context.prec = LEDGER_PRECISION
            proceeds = state.inventory * price
            fee = proceeds * self.scenario.maker_fee_per_leg
            net = proceeds - fee
            target = state.cash + state.inventory_cost
            deficit = state.inventory_cost - net
            reserve_after_release = self.reserve - deficit
        if deficit <= 0:
            return self._keep("NONPOSITIVE_DEFICIT")
        with localcontext() as context:
            context.prec = LEDGER_PRECISION
            loss_bps = deficit / target * 10000
        if loss_bps > self.config.max_loss_bps:
            return self._keep("LOSS_CAP")
        if deficit > self.reserve:
            return self._keep("INSUFFICIENT_RESERVE")
        if reserve_after_release < self.config.reserve_floor:
            return self._keep("RESERVE_FLOOR")
        tick, distances, multiple = _selection_grid(
            self.parent,
            self.tick_catalog,
            boundary,
            self.tape.tick_size,
            self.tape.observed_tick_evidence_event,
        )
        start = boundary - _minutes_to_events(self.parent.lookback_minutes)
        candidate = _select(
            self.timelines,
            self.parent,
            start,
            boundary,
            eligible_distances=distances,
            grid_multiple=multiple,
        )
        if candidate is None:
            return self._keep("NO_VALID_CANDIDATE")
        if candidate == state.candidate:
            return self._keep("SAME_CANDIDATE")
        score = _score(candidate, self.timelines, self.parent, start, boundary)
        if score <= 0:
            return self._keep("NONPOSITIVE_SCORE")
        destination = self.timelines[candidate]
        original_timeline = self.timelines[state.candidate]
        destination_activity = _activity(destination, boundary)
        original_activity = _activity(original_timeline, boundary)
        if original_activity["cycles_1h"] > ORIGINAL_MAX_CYCLES_1H:
            return self._keep("ORIGINAL_RANGE_ACTIVE")
        if destination_activity["cycles_1h"] < DESTINATION_MIN_CYCLES_1H:
            return self._keep("DESTINATION_INACTIVE_1H")
        if destination_activity["cycles_4h"] < DESTINATION_MIN_CYCLES_4H:
            return self._keep("DESTINATION_INACTIVE_4H")
        # Repeat the causal selection after eligibility; never substitute a future winner.
        selected = _select(
            self.timelines,
            self.parent,
            start,
            boundary,
            eligible_distances=distances,
            grid_multiple=multiple,
        )
        if selected != candidate:
            raise ValueError("NONDETERMINISTIC_RECOVERY_SELECTION")
        original = state.candidate
        low = D(original[0]) * self.tape.tick_size
        with localcontext() as context:
            context.prec = LEDGER_PRECISION
            release_buy_fee = state.inventory_cost - state.inventory * low
        closure = SerialCycle(
            entry_event=int(state.entry_event),
            exit_event=event,
            entry_timestamp=_event_to_datetime(state.entry_event),
            exit_timestamp=_event_to_datetime(event),
            low=low,
            high=price,
            tick_at_selection=state.candidate_tick_size,
            quantity=state.inventory,
            buy_fee_quote=release_buy_fee,
            sell_fee_quote=fee,
        )
        new_low = D(candidate[0]) * self.tape.tick_size
        new_high = D(sum(candidate)) * self.tape.tick_size
        with localcontext() as context:
            context.prec = LEDGER_PRECISION
            cash_after_sale = state.cash + net
            affordable = target / (new_low * (D("1") + self.scenario.maker_fee_per_leg))
            recovery_quantity = (affordable / self.scenario.quantity_step).to_integral_value(
                rounding=ROUND_DOWN
            ) * self.scenario.quantity_step
            recovery_cycle_profit = (
                recovery_quantity * new_high
                - recovery_quantity * new_high * self.scenario.maker_fee_per_leg
                - recovery_quantity * new_low
                - recovery_quantity * new_low * self.scenario.maker_fee_per_leg
            )
            recovery_cost_in_cycles = (
                deficit / recovery_cycle_profit if recovery_cycle_profit > 0 else None
            )
        record = {
            "event": event,
            "entry_event": int(state.entry_event),
            "timestamp": _event_to_datetime(event).isoformat(),
            "position_entry": _event_to_datetime(state.entry_event).isoformat(),
            "position_age_seconds": str(
                D(boundary - state.entry_event // EVENT_ORDER_SCALE * EVENT_ORDER_SCALE)
                / D(HOUR)
                * 3600
            ),
            "quantity": str(state.inventory),
            "original_low": str(low),
            "original_high": str(D(sum(original)) * self.tape.tick_size),
            "release_price": str(price),
            "price_observation_event": int(self.tape.events[index]),
            "loss_usdt": str(deficit),
            "loss_bps": str(loss_bps),
            "sell_fee": str(fee),
            "operating_bank_before": str(target),
            "operating_bank_after_sale": str(cash_after_sale),
            "reserve_before": str(self.reserve),
            "reserve_transfer": str(deficit),
            "reserve_after": str(reserve_after_release),
            "reserve_floor": str(self.config.reserve_floor),
            "operating_bank_restored": str(target),
            "new_low": str(new_low),
            "new_high": str(new_high),
            "new_candidate_score": str(score),
            "original_activity": original_activity,
            "destination_activity": destination_activity,
            "recovery_cycle_profit": str(recovery_cycle_profit),
            "recovery_cost_in_cycles": (
                str(recovery_cost_in_cycles) if recovery_cost_in_cycles is not None else None
            ),
            "cycles_at_release": self.cycles_settled,
            "price_class": "THEORETICAL_RELEASE_PRICE_PATH",
            "executable_release_loss": "UNKNOWN",
            "peg_risk_warning": abs(price - D(1)) * 10000 >= 50 or loss_bps >= 50,
        }
        with localcontext() as context:
            context.prec = LEDGER_PRECISION
            equity_before_transfer = cash_after_sale + self.reserve
            self.reserve = reserve_after_release
            state.cash = cash_after_sale + deficit
            if state.cash != target or state.cash + self.reserve != equity_before_transfer:
                raise ValueError("RESERVE_ACCOUNTING_RECONCILIATION_FAILED")
            state.fees += fee
            state.realized_profit -= deficit
        state.release_closures.append(closure)
        state.inventory = D(0)
        state.inventory_cost = D(0)
        state.entry_event = None
        state.next_release_event = None
        state.flat_since = event
        _switch(state, selected, tick, event)
        self.releases.append(record)
        self.replenishments.append(
            {
                "release_event": event,
                "target_balance": record["reserve_before"],
                "cycles_at_release": self.cycles_settled,
                "replenished_event": None,
                "time_to_replenish_seconds": None,
                "cycles_to_replenish": None,
            }
        )
        self.evaluations["RELEASE"] += 1
        return True

    def snapshot(self) -> dict[str, Any]:
        import copy

        payload = copy.deepcopy(
            {
                "config": self.config.payload(),
                "reserve": str(self.reserve),
                "total_skim": str(self.total_skim),
                "releases": self.releases,
                "evaluations": dict(self.evaluations),
                "replenishments": self.replenishments,
                "cycles_settled": self.cycles_settled,
            }
        )
        payload["sha256"] = canonical_hash(payload)
        return payload

    def restore(self, snapshot: dict[str, Any]) -> None:
        import copy

        snapshot = copy.deepcopy(snapshot)
        digest = snapshot.pop("sha256", None)
        if digest != canonical_hash(snapshot):
            raise ValueError("RECOVERY_RESTART_RECONCILIATION_FAILED")
        if snapshot["config"] != self.config.payload():
            raise ValueError("RECOVERY_RESTART_CONFIG_MISMATCH")
        reserve, skim = D(snapshot["reserve"]), D(snapshot["total_skim"])
        # Ordered money reconstruction is the audit's authority. Regrouping rounded
        # Decimal additions as initial + total_skim - total_loss is not equivalent.
        if not reserve.is_finite() or not skim.is_finite() or reserve < 0 or skim < 0:
            raise ValueError("RECOVERY_RESTART_RECONCILIATION_FAILED")
        self.reserve, self.total_skim = reserve, skim
        self.releases, self.replenishments = snapshot["releases"], snapshot["replenishments"]
        self.evaluations = Counter(snapshot["evaluations"])
        self.cycles_settled = int(snapshot["cycles_settled"])
