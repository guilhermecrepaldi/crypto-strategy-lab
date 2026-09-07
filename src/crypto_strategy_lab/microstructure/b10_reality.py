"""Offline B10 execution primitives. No account, order endpoint or replay launcher.

This kernel is deliberately not a historical fill claim. Rules and envelopes must
be supplied with provenance; the campaign runner must bind them to event dates.
Binance authority: Spot filters, commission FAQ, REST LIMIT_MAKER and trade stream.
Queue depletion is a conservative parameterized model, not observed queue rank.
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, fields, is_dataclass
from decimal import ROUND_DOWN, ROUND_UP, Decimal, localcontext
from typing import Any, Literal, cast

from crypto_strategy_lab.domain import canonical_hash

D = Decimal
ZERO = D(0)


@dataclass(frozen=True)
class ExecutionProfile:
    name: str
    evidence_sha256: str
    latency_us: int
    cancel_latency_us: int
    queue_ahead: Decimal
    maker_fee: Decimal
    taker_fee: Decimal

    def __post_init__(self) -> None:
        if len(self.evidence_sha256) != 64:
            raise ValueError("PROFILE_PROVENANCE_REQUIRED")
        if self.latency_us <= 0 or self.cancel_latency_us <= 0 or self.queue_ahead <= 0:
            raise ValueError("ZERO_LATENCY_OR_QUEUE_FORBIDDEN")
        if any(not v.is_finite() or v < 0 or v >= 1 for v in (self.maker_fee, self.taker_fee)):
            raise ValueError("INVALID_COMMISSION")


@dataclass(frozen=True)
class SymbolRules:
    tick_size: Decimal
    step_size: Decimal
    min_quantity: Decimal
    max_quantity: Decimal
    min_notional: Decimal
    max_notional: Decimal
    min_price: Decimal
    max_price: Decimal
    evidence_sha256: str
    # Caller must derive side-specific dynamic bounds from the causal official
    # weighted average and historically applicable multiplier, when applicable.
    buy_bounds: tuple[Decimal, Decimal] | None = None
    sell_bounds: tuple[Decimal, Decimal] | None = None
    orders_per_window: int = 1
    window_us: int = 1

    def validate(self, side: str, price: Decimal, quantity: Decimal) -> None:
        if len(self.evidence_sha256) != 64:
            raise ValueError("RULE_PROVENANCE_REQUIRED")
        if self.tick_size <= 0 or self.step_size <= 0:
            raise ValueError("INVALID_FILTER_CONFIGURATION")
        if not price.is_finite() or not quantity.is_finite() or price <= 0 or quantity <= 0:
            raise ValueError("NONPOSITIVE_ORDER")
        if price % self.tick_size or not self.min_price <= price <= self.max_price:
            raise ValueError("PRICE_FILTER")
        if quantity % self.step_size or not self.min_quantity <= quantity <= self.max_quantity:
            raise ValueError("LOT_SIZE")
        if not self.min_notional <= price * quantity <= self.max_notional:
            raise ValueError("NOTIONAL")
        bounds = self.buy_bounds if side == "BUY" else self.sell_bounds
        if bounds is not None and not bounds[0] <= price <= bounds[1]:
            raise ValueError("PERCENT_PRICE_BY_SIDE")


@dataclass(frozen=True)
class Trade:
    time_us: int
    trade_id: int
    price: Decimal
    quantity: Decimal
    buyer_maker: bool
    canonical_event: int | None = None


@dataclass
class Order:
    order_id: int
    side: Literal["BUY", "SELL"]
    price: Decimal
    quantity: Decimal
    submitted_us: int
    active_us: int
    queue: Decimal
    release: bool = False
    filled: Decimal = ZERO
    status: str = "PENDING"
    cancel_us: int | None = None
    had_partial: bool = False


def round_quantity(quantity: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        raise ValueError("INVALID_STEP")
    return (quantity / step).to_integral_value(rounding=ROUND_DOWN) * step


def _encode(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    if is_dataclass(value):
        return {
            "dataclass": type(value).__name__,
            "fields": {field.name: _encode(getattr(value, field.name)) for field in fields(value)},
        }
    if isinstance(value, tuple):
        return {"tuple": [_encode(item) for item in value]}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {"decimal"}:
            return D(value["decimal"])
        if set(value) == {"tuple"}:
            return tuple(_decode(item) for item in value["tuple"])
        if set(value) == {"dataclass", "fields"}:
            cls = {
                "ExecutionProfile": ExecutionProfile,
                "SymbolRules": SymbolRules,
                "Order": Order,
            }[value["dataclass"]]
            return cls(**{key: _decode(item) for key, item in value["fields"].items()})
        return {key: _decode(item) for key, item in value.items()}
    return value


class B10Execution:
    """One order / one serial lot, exact ledger, explicit observation ordering.

    Normal orders are LIMIT_MAKER. Release is marketable LIMIT IOC against a
    supplied book/envelope and may expire partially. Another liquidation needs
    an explicit subsequent submission; inventory cannot disappear on expiry.
    All book updates carry a unique source ID; the same depth cannot fill twice.
    """

    def __init__(self, profile: ExecutionProfile, rules: SymbolRules) -> None:
        self.profile, self.rules = profile, rules
        self.cash, self.reserve = D(100), D(5)
        self.inventory = self.dust = self.cost = ZERO
        self.buy_cost = self.sell_net = self.fees = ZERO
        self.sold_cost = self.dust_cost = ZERO
        self.buy_fee_basis = self.realized_cycle_fees = ZERO
        self.reserve_funding = self.reserve_consumption = ZERO
        self.reserve_min = self.reserve
        self.order: Order | None = None
        self.orders: list[Order] = []
        self.audit: list[dict[str, Any]] = []
        self.settlements: list[dict[str, Any]] = []
        self.counts: Counter[str] = Counter()
        self.last_trade: tuple[int, int] | None = None
        self.last_book_us = -1
        self.book_id: int | None = None
        self.book_valid = False
        self.bids: list[list[Decimal]] = []
        self.ask: Decimal | None = None
        self.messages: list[int] = []
        self.last_cancel_ack_us = -1
        self.entry_us: int | None = None
        self.releasing = False
        self.release_execution_started = False
        self.release_signal_bank: Decimal | None = None
        self.release_signal_id: int | None = None
        self.buy_complete = False

    def _record(self, kind: str, **values: Any) -> None:
        record = {"kind": kind, **values}
        self.audit.append(record)
        if kind == "SETTLEMENT":
            self.settlements.append(record)

    def book(
        self,
        time_us: int,
        source_id: int,
        bids: list[tuple[Decimal, Decimal]],
        ask: Decimal,
        *,
        valid: bool = True,
    ) -> None:
        if time_us < self.last_book_us or (self.book_id is not None and source_id <= self.book_id):
            raise ValueError("NONCAUSAL_BOOK")
        if not bids or any(p <= 0 or q < 0 for p, q in bids) or bids[0][0] >= ask:
            raise ValueError("INVALID_BOOK")
        if bids != sorted(bids, reverse=True):
            raise ValueError("UNSORTED_BIDS")
        self.last_book_us, self.book_id = time_us, source_id
        self.bids, self.ask, self.book_valid = [list(v) for v in bids], ask, valid
        self._advance(time_us)

    def gap(self) -> None:
        self.book_valid = False
        self.counts["DATA_GAP"] += 1

    def submit(
        self,
        side: Literal["BUY", "SELL"],
        price: Decimal,
        time_us: int,
        *,
        release: bool = False,
        continuation: bool = False,
    ) -> Order | None:
        if self.order is not None:
            raise ValueError("SERIAL_ORDER_INVARIANT")
        if time_us <= self.last_cancel_ack_us:
            return None
        if not self.book_valid or self.last_book_us > time_us:
            raise ValueError("NO_CAUSAL_BOOK")
        if side == "BUY" and ((self.inventory > 0 and not continuation) or self.releasing):
            raise ValueError("SERIAL_LOT_INVARIANT")
        if side == "SELL" and not self.buy_complete and not release:
            raise ValueError("BUY_NOT_FULLY_FILLED")
        if release and side != "SELL":
            raise ValueError("RELEASE_MUST_SELL")
        with localcontext() as ctx:
            ctx.prec = 128
            quantity = (
                round_quantity(min(D(100) - self.buy_cost, self.cash) / price, self.rules.step_size)
                if side == "BUY"
                else round_quantity(self.inventory, self.rules.step_size)
            )
            try:
                self.rules.validate(side, price, quantity)
            except ValueError as exc:
                self.counts["ORDER_REJECTION_COUNT"] += 1
                self._record("REJECTION", time_us=time_us, reason=str(exc))
                return None
            window = time_us // self.rules.window_us
            self.messages = [t for t in self.messages if t // self.rules.window_us == window]
            if (
                sum(t // self.rules.window_us == window for t in self.messages)
                >= self.rules.orders_per_window
            ):
                self.counts["RATE_LIMIT_REJECTION"] += 1
                return None
            self.messages.append(time_us)
            order = Order(
                len(self.orders) + 1,
                side,
                price,
                quantity,
                time_us,
                time_us + self.profile.latency_us,
                self.profile.queue_ahead,
                release,
            )
            self.order = order
            self.orders.append(order)
            self.releasing |= release
            self._record("SUBMIT", **asdict(order))
            return order

    def cancel(self, time_us: int) -> None:
        if self.order is None:
            return
        if self.order.cancel_us is None:
            self.counts["CANCEL_REQUEST_COUNT"] += 1
            self.order.cancel_us = time_us + self.profile.cancel_latency_us
            self._record(
                "CANCEL_REQUEST",
                order_id=self.order.order_id,
                time_us=time_us,
                effective_us=self.order.cancel_us,
            )

    def _advance(self, time_us: int) -> None:
        order = self.order
        if order is None:
            return
        # Strictly later observations: equal-time cross-stream priority unknown.
        if order.cancel_us is not None and time_us > order.cancel_us:
            order.status = "CANCELED"
            self.last_cancel_ack_us = order.cancel_us + self.profile.latency_us
            self._record("CANCELED", order_id=order.order_id, time_us=order.cancel_us)
            self._record(
                "CANCEL_ACK_SCHEDULED",
                order_id=order.order_id,
                time_us=self.last_cancel_ack_us,
                evidence_class="PARAMETERIZED_RETURN_EQUALS_ORDER_LATENCY",
            )
            self.order = None
            return
        if order.status != "PENDING" or time_us <= order.active_us or not self.book_valid:
            return
        try:
            self.rules.validate(order.side, order.price, order.quantity)
        except ValueError as exc:
            order.status = "REJECTED"
            self.counts["ORDER_REJECTION_COUNT"] += 1
            self._record("REJECTION", order_id=order.order_id, reason=str(exc))
            self.order = None
            return
        assert self.ask is not None
        crossing = (
            order.price >= self.ask if order.side == "BUY" else order.price <= self.bids[0][0]
        )
        if crossing and not order.release:
            order.status = "REJECTED"
            self.counts["ORDER_REJECTION_COUNT"] += 1
            self._record("REJECTION", order_id=order.order_id, reason="LIMIT_MAKER_WOULD_TAKE")
            self.order = None
            return
        order.status = "ACTIVE"
        self._record(
            "ORDER_ACTIVE",
            order_id=order.order_id,
            time_us=order.active_us,
            evaluated_at_us=time_us,
            best_bid=str(self.bids[0][0]),
            ask=str(self.ask),
        )
        if order.release:
            budget_before = sum((level[1] for level in self.bids), ZERO)
            self._record(
                "RELEASE_BOOK_EVALUATION",
                order_id=order.order_id,
                time_us=time_us,
                book_source_id=self.book_id,
                limit_price=str(order.price),
                best_bid=str(self.bids[0][0]),
                available_budget_before=str(budget_before),
            )
            for level in self.bids:
                if level[0] < order.price or self.order is None:
                    break
                quantity = min(order.quantity - order.filled, level[1])
                if quantity:
                    self._fill(order, quantity, level[0], time_us, "BOOK", self.book_id)
                    level[1] -= quantity
            if self.order is not None:
                order.status = "EXPIRED"
                self.order = None
                self._record(
                    "IOC_EXPIRED",
                    order_id=order.order_id,
                    time_us=time_us,
                    filled=str(order.filled),
                    remaining=str(order.quantity - order.filled),
                    book_source_id=self.book_id,
                    best_bid=str(self.bids[0][0]),
                    available_budget_before=str(budget_before),
                    available_budget_after=str(sum((level[1] for level in self.bids), ZERO)),
                )
                self.counts["RELEASE_PARTIAL" if order.filled else "RELEASE_UNFILLED"] += 1

    def trade(self, trade: Trade) -> None:
        key = trade.time_us, trade.trade_id
        if trade.time_us < self.last_book_us:
            raise ValueError("FUTURE_BOOK_AT_TRADE")
        if self.last_trade is not None and key <= self.last_trade:
            raise ValueError("NONCAUSAL_TRADE")
        if trade.quantity <= 0 or trade.price <= 0:
            raise ValueError("INVALID_TRADE")
        self.last_trade = key
        self._advance(trade.time_us)
        order = self.order
        if order is None or order.release or not self.book_valid:
            return
        if order.status == "PENDING":
            if trade.price == order.price:
                self.counts["MISSED_BY_LATENCY"] += 1
            return
        if trade.price != order.price:
            return
        self.counts["TRADE_AT_PRICE"] += 1
        if trade.buyer_maker != (order.side == "BUY"):
            return
        self.counts["COMPATIBLE_AGGRESSOR_FLOW"] += 1
        with localcontext() as ctx:
            ctx.prec = 128
            queue_before = order.queue
            consumed = min(order.queue, trade.quantity)
            order.queue -= consumed
            remaining = trade.quantity - consumed
            self._record(
                "QUEUE_FLOW",
                order_id=order.order_id,
                time_us=trade.time_us,
                trade_id=trade.trade_id,
                quantity=str(trade.quantity),
                buyer_maker=trade.buyer_maker,
                queue_before=str(queue_before),
                queue_after=str(order.queue),
                available_after_queue=str(remaining),
            )
            if not remaining:
                self.counts["MISSED_BY_QUEUE"] += 1
                return
            self._fill(
                order,
                min(remaining, order.quantity - order.filled),
                order.price,
                trade.time_us,
                "TRADE",
                trade.trade_id,
            )

    def _fill(
        self,
        order: Order,
        quantity: Decimal,
        price: Decimal,
        time_us: int,
        source: str,
        source_id: int | None,
    ) -> None:
        with localcontext() as ctx:
            ctx.prec = 128
            fee_rate = self.profile.taker_fee if order.release else self.profile.maker_fee
            self.release_execution_started |= order.release
            gross, fee = quantity * price, quantity * price * fee_rate
            self.fees += fee
            order.filled += quantity
            order.had_partial |= order.filled < order.quantity
            if order.side == "BUY":
                base_fee = quantity * fee_rate
                self.cash -= gross
                self.inventory += quantity - base_fee
                self.cost += gross
                self.buy_cost += gross
                self.buy_fee_basis += fee
                if self.entry_us is None:
                    self.entry_us = time_us
            else:
                allocated_cost = self.cost * quantity / self.inventory
                allocated_buy_fee = self.buy_fee_basis * quantity / self.inventory
                self.buy_fee_basis -= allocated_buy_fee
                self.realized_cycle_fees += allocated_buy_fee + fee
                self.cost -= allocated_cost
                self.sold_cost += allocated_cost
                self.cash += gross - fee
                self.sell_net += gross - fee
                self.inventory -= quantity
            self._record(
                "FILL",
                order_id=order.order_id,
                side=order.side,
                quantity=str(quantity),
                price=str(price),
                time_us=time_us,
                source=source,
                source_id=source_id,
                fee_quote=str(fee),
                commission_asset="USDC" if order.side == "BUY" else "USDT",
                commission=str(quantity * fee_rate if order.side == "BUY" else fee),
                release=order.release,
            )
            self.counts[f"{order.side}_PARTIAL"] += int(order.filled < order.quantity)
            if order.filled == order.quantity:
                order.status = "FILLED"
                self.order = None
                self.counts[f"{order.side}_FULL"] += 1
                if order.side == "BUY":
                    self.buy_complete = True
                if order.side == "SELL":
                    self._settle(time_us)

    def _settle(self, time_us: int) -> None:
        # Unsellable base and its basis remain segregated unrealized dust.
        # Reserve covers executed deficits only, never unsold dust basis.
        self.dust += self.inventory
        self.dust_cost += self.cost
        self.inventory = ZERO
        profit = self.sell_net - self.sold_cost
        deficit = max(ZERO, -profit) if self.release_execution_started else ZERO
        actual_bps_lot = deficit / self.sold_cost * 10000 if self.sold_cost else ZERO
        actual_bps_bank = (
            deficit / self.release_signal_bank * 10000 if self.release_signal_bank else None
        )
        if self.release_execution_started:
            transfer = min(deficit, self.reserve)
            self.reserve -= transfer
            self.cash += transfer
            self.reserve_consumption += transfer
            self.counts["RESERVE_DEPLETION_EVENTS"] += int(transfer < deficit)
            self.counts["RELEASE_FILLED"] += 1
            self.counts["RELEASES_ACTUAL_GT10BPS"] += int(deficit / self.buy_cost * 10000 > 10)
            self.counts["RELEASES_GT10BPS_EXECUTED_LOT"] += int(actual_bps_lot > 10)
            self.counts["RELEASES_GT10BPS_SIGNAL_BANK"] += int(
                actual_bps_bank is not None and actual_bps_bank > 10
            )
        else:
            transfer = max(ZERO, profit) * D("0.02")
            self.cash -= transfer
            self.reserve += transfer
            self.reserve_funding += transfer
            self.counts["FULLY_FILLED_CYCLES"] += 1
            self.counts["NET_POSITIVE_CYCLES"] += int(profit > 0)
        self.reserve_min = min(self.reserve_min, self.reserve)
        self._record(
            "SETTLEMENT",
            time_us=time_us,
            net_profit=str(profit),
            release=self.release_execution_started,
            reserve=str(self.reserve),
            cash=str(self.cash),
            dust=str(self.dust),
            dust_cost=str(self.dust_cost),
            sold_cost=str(self.sold_cost),
            gross_pnl=str(profit + self.realized_cycle_fees),
            realized_fees_quote=str(self.realized_cycle_fees),
            actual_release_loss=str(deficit),
            actual_loss_bps_executed_lot=str(actual_bps_lot),
            actual_loss_bps_signal_bank=str(actual_bps_bank)
            if actual_bps_bank is not None
            else None,
            release_signal_id=self.release_signal_id,
            release_signal_bank=str(self.release_signal_bank)
            if self.release_signal_bank is not None
            else None,
            reserve_transfer=str(transfer),
        )
        self.cost = self.buy_cost = self.sell_net = ZERO
        self.sold_cost = ZERO
        self.buy_fee_basis = self.realized_cycle_fees = ZERO
        self.entry_us = None
        self.releasing = False
        self.release_execution_started = False
        self.release_signal_bank = None
        self.release_signal_id = None
        self.buy_complete = False

    def checkpoint(self) -> dict[str, Any]:
        """JSON-safe exact checkpoint; caller must persist atomically."""
        state = _encode(self.__dict__)
        return {"state": state, "sha256": canonical_hash(state)}

    def restore(self, checkpoint: dict[str, Any]) -> None:
        if canonical_hash(checkpoint["state"]) != checkpoint["sha256"]:
            raise ValueError("CHECKPOINT_HASH_MISMATCH")
        state = _decode(checkpoint["state"])
        if state["profile"] != self.profile or state["rules"] != self.rules:
            raise ValueError("CHECKPOINT_CONFIG_MISMATCH")
        self.__dict__ = copy.deepcopy(state)
        self.counts = Counter(self.counts)
        if self.order is not None:
            self.order = self.orders[self.order.order_id - 1]


class FrozenB10Decisions:
    """Reuse frozen strategy authorities against actual execution state.

    No price-path winning cycle schedule is accepted. The caller advances the
    canonical decision clock and feeds actual executed inventory/cash. This is
    not an automatic driver: cancellation and release execution stay asynchronous.
    """

    def __init__(self, recovery_runtime: Any, *, start_event: int) -> None:
        from .recovery_reserve import ReserveConfig
        from .serial_replay import _State

        if recovery_runtime.config != ReserveConfig(D("0.02"), 1, D(10), ZERO):
            raise ValueError("B10_FROZEN_CONFIG_MISMATCH")
        if recovery_runtime.parent.model_id != "M007":
            raise ValueError("B10_SELECTOR_ANCESTRY_MISMATCH")
        if recovery_runtime.scenario.maker_fee_per_leg != 0:
            raise ValueError("THEORETICAL_B10_TRIGGER_MUST_REMAIN_FROZEN_ZERO_FEE")
        self.runtime = recovery_runtime
        self.state = _State(cash=D(100), flat_since=start_event)
        self.release_evaluations: Counter[str] = Counter()
        from .serial_replay import _minutes_to_events, _select, _selection_grid

        tick, distances, multiple = _selection_grid(
            self.runtime.parent,
            self.runtime.tick_catalog,
            start_event,
            self.runtime.tape.tick_size,
            self.runtime.tape.observed_tick_evidence_event,
        )
        self.state.candidate = _select(
            self.runtime.timelines,
            self.runtime.parent,
            start_event - _minutes_to_events(self.runtime.parent.lookback_minutes),
            start_event,
            eligible_distances=distances,
            grid_multiple=multiple,
        )
        self.state.candidate_tick_size = tick if self.state.candidate is not None else None

    def select(self, event: int, execution: B10Execution) -> tuple[int, int] | None:
        from .serial_replay import EVENT_ORDER_SCALE, _decision, _minutes_to_events

        if execution.inventory or execution.releasing:
            return cast(tuple[int, int] | None, self.state.candidate)
        self.state.cash = execution.cash
        self.state.entry_event = None
        _decision(
            self.state,
            self.runtime.timelines,
            self.runtime.parent,
            event,
            _minutes_to_events(self.runtime.parent.lookback_minutes),
            tick_catalog=self.runtime.tick_catalog,
            tape_quantum=self.runtime.tape.tick_size,
            observed_tick_evidence_event=self.runtime.tape.observed_tick_evidence_event,
        )
        if execution.entry_us is not None:
            self.state.entry_event = execution.entry_us * EVENT_ORDER_SCALE
        return cast(tuple[int, int] | None, self.state.candidate)

    def release_signal(self, event: int, execution: B10Execution) -> dict[str, Any] | None:
        from .serial_replay import EVENT_ORDER_SCALE

        if execution.entry_us is None or execution.releasing:
            return None
        # Copies exclude the large tape/timelines; only financial state is isolated.
        probe = copy.copy(self.runtime)
        probe.reserve = execution.reserve
        probe.releases, probe.replenishments = [], []
        probe.evaluations = Counter()
        state = copy.deepcopy(self.state)
        state.cash = execution.cash
        state.inventory = execution.inventory
        state.inventory_cost = execution.cost
        state.entry_event = execution.entry_us * EVENT_ORDER_SCALE
        released = probe(state, event)
        self.release_evaluations.update(probe.evaluations)
        if not released:
            return None
        return cast(dict[str, Any], copy.deepcopy(probe.releases[-1]))

    def after_ordinary_exit(self, event: int) -> None:
        from .serial_replay import (
            SerialStrategy,
            _minutes_to_events,
            _select,
            _selection_grid,
            _switch,
            _switch_if_score_advantaged,
        )

        runtime = self.runtime
        tick, distances, multiple = _selection_grid(
            runtime.parent,
            runtime.tick_catalog,
            event,
            runtime.tape.tick_size,
            runtime.tape.observed_tick_evidence_event,
        )
        lookback = _minutes_to_events(runtime.parent.lookback_minutes)
        candidate = _select(
            runtime.timelines,
            runtime.parent,
            event - lookback,
            event,
            eligible_distances=distances,
            grid_multiple=multiple,
        )
        if runtime.parent.strategy == SerialStrategy.RELATIVE_SCORE_HYSTERESIS:
            _switch_if_score_advantaged(
                self.state, runtime.timelines, runtime.parent, candidate, tick, event, lookback
            )
        else:
            _switch(self.state, candidate, tick, event, allow_none=True)


@dataclass(frozen=True)
class BookEnvelope:
    """Prospectively calibrated, parameterized historical book proxy, never L2 backfill."""

    evidence_sha256: str
    half_spread: Decimal
    release_slippage: Decimal
    release_depth: Decimal
    release_limit_distance: Decimal
    depth_refresh_us: int

    def __post_init__(self) -> None:
        if len(self.evidence_sha256) != 64 or self.half_spread <= 0 or self.release_depth <= 0:
            raise ValueError("CALIBRATED_BOOK_ENVELOPE_REQUIRED")
        if self.release_slippage < 0 or self.release_limit_distance <= 0:
            raise ValueError("INVALID_RELEASE_ENVELOPE")
        if self.depth_refresh_us <= 0:
            raise ValueError("CALIBRATED_DEPTH_REFRESH_REQUIRED")

    def quote(
        self, mark: Decimal, tick: Decimal, release: bool, buyer_maker: bool
    ) -> tuple[Decimal, Decimal]:
        # Inferred trade-side alignment: m=true print at bid; m=false at ask.
        # Neither historical best quote nor resting queue rank is observed.
        bid = mark - (ZERO if buyer_maker else self.half_spread * 2)
        ask = mark + (self.half_spread * 2 if buyer_maker else ZERO)
        bid -= self.release_slippage if release else ZERO
        return (bid / tick).to_integral_value(rounding=ROUND_DOWN) * tick, (
            ask / tick
        ).to_integral_value(rounding=ROUND_UP) * tick


class B10RealityReplay:
    """Causal serial orchestration of the frozen selector and execution kernel.

    Pass the full frozen interval, including days with no fills. Rules are an
    explicit date-dispatch function; its provenance is a required run input.
    Trades must contain exchange quantity, aggressor and unique ordered IDs.
    Synthetic book estimates are made from the *current observed trade* before
    executing an already submitted order, never from a subsequent trade.
    """

    def __init__(
        self,
        runtime: Any,
        profile: ExecutionProfile,
        rules_at: Callable[[int], SymbolRules],
        envelope: BookEnvelope,
        *,
        start_us: int,
        end_us: int,
        identity: dict[str, Any],
        gaps: tuple[tuple[int, int], ...] = (),
    ) -> None:
        from .serial_replay import EVENT_ORDER_SCALE

        if start_us >= end_us:
            raise ValueError("INVALID_INTERVAL")
        if not identity.get("published_config_sha") or not identity.get("data_manifest_sha256"):
            raise ValueError("PUBLISHED_CONFIG_AND_DATA_MANIFEST_REQUIRED")
        self.start_us, self.end_us, self.identity = start_us, end_us, identity
        self.rules_at, self.envelope, self.gaps = rules_at, envelope, gaps
        self.execution = B10Execution(profile, rules_at(start_us))
        self.decisions = FrozenB10Decisions(runtime, start_event=start_us * EVENT_ORDER_SCALE)
        self.interval = (runtime.parent.decision_interval_minutes or 1) * 60_000_000
        self.next_decision = start_us + self.interval
        self.next_release: int | None = None
        self.order_candidate: tuple[int, int] | None = None
        self.order_candidate_tick: Decimal | None = None
        self.position_candidate: tuple[int, int] | None = None
        self.position_candidate_tick: Decimal | None = None
        self.release_destination: tuple[int, int] | None = None
        self.release_destination_tick: Decimal | None = None
        self.release_signals: list[dict[str, Any]] = []
        self.last_mark: Decimal | None = None
        self.last_us = start_us
        self.last_clock_us = start_us
        self.processed_trades = 0
        self.completed = False
        self.depth_remaining = envelope.release_depth
        self.depth_epoch = start_us
        self.holds_us: list[int] = []
        self.peak_equity = D(105)
        self.max_drawdown = ZERO
        self.last_settlement = 0
        self.full_days: Counter[str] = Counter()
        self.net_days: Counter[str] = Counter()

    def _clock(self, timestamp: int) -> None:
        from .serial_replay import EVENT_ORDER_SCALE

        engine = self.execution
        self.last_clock_us = timestamp
        engine.rules = self.rules_at(timestamp)
        if engine.order is not None and not engine.order.release:
            engine._advance(timestamp)
        if engine.inventory > 0 and not engine.releasing:
            if self.position_candidate is not None:
                self.decisions.state.candidate = self.position_candidate
                self.decisions.state.candidate_tick_size = self.position_candidate_tick
            if self.next_release is not None and timestamp >= self.next_release:
                signal = self.decisions.release_signal(timestamp * EVENT_ORDER_SCALE, engine)
                self.next_release += 3_600_000_000
                if signal is not None:
                    self.release_signals.append(signal)
                    engine.release_signal_bank = D(signal["operating_bank_before"])
                    engine.release_signal_id = len(self.release_signals) - 1
                    engine._record(
                        "RELEASE_SIGNAL",
                        time_us=timestamp,
                        signal_id=engine.release_signal_id,
                        operating_bank_before=signal["operating_bank_before"],
                        theoretical_loss_bps_operating_bank=signal["loss_bps"],
                    )
                    tick = self.decisions.runtime.tape.tick_size
                    low = int(D(signal["new_low"]) / tick)
                    high = int(D(signal["new_high"]) / tick)
                    self.release_destination = (low, high - low)
                    from .serial_replay import _selection_grid

                    self.release_destination_tick = _selection_grid(
                        self.decisions.runtime.parent,
                        self.decisions.runtime.tick_catalog,
                        timestamp * EVENT_ORDER_SCALE,
                        tick,
                        self.decisions.runtime.tape.observed_tick_evidence_event,
                    )[0]
                    self.next_release = None
                    engine.releasing = True
                    engine.counts["RELEASE_SIGNALS"] += 1
                    engine.cancel(timestamp)
        if timestamp >= self.next_decision:
            old = self.decisions.state.candidate
            self.decisions.select(timestamp * EVENT_ORDER_SCALE, engine)
            self.next_decision += self.interval
            if (
                engine.order is not None
                and engine.order.side == "BUY"
                and old != self.decisions.state.candidate
            ):
                engine.cancel(timestamp)
        self._submit_next(timestamp)

    def _next_clock(self) -> int:
        engine = self.execution
        clocks = [self.next_decision, self.next_release or self.end_us]
        if engine.order is not None:
            if engine.order.status == "PENDING" and not engine.order.release:
                clocks.append(engine.order.active_us + 1)
            if engine.order.cancel_us is not None:
                clocks.append(engine.order.cancel_us + 1)
        if engine.last_cancel_ack_us + 1 > self.last_clock_us:
            clocks.append(engine.last_cancel_ack_us + 1)
        return min(clock for clock in clocks if clock > self.last_clock_us)

    def _submit_next(self, timestamp: int) -> None:
        engine = self.execution
        if engine.order is not None or not engine.book_valid:
            return
        if engine.releasing:
            limit = engine.bids[0][0] - self.envelope.release_limit_distance
            limit = (limit / engine.rules.tick_size).to_integral_value(
                rounding=ROUND_DOWN
            ) * engine.rules.tick_size
            if limit > 0:
                engine.submit("SELL", limit, timestamp, release=True)
            return
        if engine.inventory > 0:
            candidate = self.position_candidate
            if candidate is None:
                raise ValueError("UNBOUND_EXECUTED_POSITION_RANGE")
            tick = self.decisions.runtime.tape.tick_size
            if engine.buy_complete:
                engine.submit("SELL", D(sum(candidate)) * tick, timestamp)
            else:
                # A canceled partial entry stays the same serial lot and range.
                engine.submit("BUY", D(candidate[0]) * tick, timestamp, continuation=True)
            return
        candidate = self.decisions.state.candidate
        if candidate is not None:
            order = engine.submit(
                "BUY", D(candidate[0]) * self.decisions.runtime.tape.tick_size, timestamp
            )
            if order is not None:
                self.order_candidate = candidate
                self.order_candidate_tick = self.decisions.state.candidate_tick_size

    def step(self, trade: Trade) -> None:
        from .serial_replay import EVENT_ORDER_SCALE

        if self.completed or not self.start_us <= trade.time_us < self.end_us:
            raise ValueError("TRADE_OUTSIDE_REPLAY_INTERVAL")
        engine = self.execution
        canonical_event = (
            trade.canonical_event
            if trade.canonical_event is not None
            else trade.time_us * EVENT_ORDER_SCALE
        )
        if canonical_event // EVENT_ORDER_SCALE != trade.time_us:
            raise ValueError("CANONICAL_EVENT_TIMESTAMP_MISMATCH")
        if trade.time_us < self.last_us:
            raise ValueError("NONCAUSAL_REPLAY")
        # Advance scheduled strategy decisions using the strict canonical prefix.
        while self._next_clock() <= trade.time_us:
            self._clock(self._next_clock())
        engine.rules = self.rules_at(trade.time_us)
        valid = not any(start <= trade.time_us < end for start, end in self.gaps)
        bid, ask = self.envelope.quote(
            trade.price, engine.rules.tick_size, engine.releasing, trade.buyer_maker
        )
        old_entry = engine.entry_us
        old_full = engine.counts["FULLY_FILLED_CYCLES"]
        old_release = engine.counts["RELEASE_FILLED"]
        # Conserve a shared budget across retries; distinct trade IDs cannot mint
        # liquidity. The positive refresh cadence is a preregistered envelope.
        if trade.time_us >= self.depth_epoch + self.envelope.depth_refresh_us:
            self.depth_remaining = self.envelope.release_depth
            self.depth_epoch = trade.time_us
        engine.book(trade.time_us, trade.trade_id, [(bid, self.depth_remaining)], ask, valid=valid)
        self.depth_remaining = engine.bids[0][1]
        engine.trade(trade)
        if old_entry is None and engine.entry_us is not None:
            self.position_candidate = self.order_candidate
            self.position_candidate_tick = self.order_candidate_tick
            self.decisions.state.candidate = self.position_candidate
            self.decisions.state.candidate_tick_size = self.position_candidate_tick
            self.next_release = engine.entry_us + 3_600_000_000
        if old_entry is not None and engine.entry_us is None:
            self.holds_us.append(trade.time_us - old_entry)
            self.next_release = None
            self.decisions.state.entry_event = None
            self.decisions.state.flat_since = trade.time_us * EVENT_ORDER_SCALE
            if engine.counts["RELEASE_FILLED"] > old_release:
                from .serial_replay import _switch

                _switch(
                    self.decisions.state,
                    self.release_destination,
                    self.release_destination_tick,
                    trade.time_us * EVENT_ORDER_SCALE,
                )
                self.release_destination = None
                self.release_destination_tick = None
            else:
                self.release_destination = None
                self.release_destination_tick = None
                self.decisions.after_ordinary_exit(canonical_event)
            self.position_candidate = None
            self.position_candidate_tick = None
        if engine.counts["FULLY_FILLED_CYCLES"] > old_full:
            from datetime import UTC, datetime

            day = datetime.fromtimestamp(trade.time_us / 1_000_000, UTC).date().isoformat()
            self.full_days[day] += 1
            if D(engine.audit[-1]["net_profit"]) > 0:
                self.net_days[day] += 1
        if trade.time_us >= self.next_decision or (
            self.next_release is not None and trade.time_us >= self.next_release
        ):
            self._clock(trade.time_us)
        self._submit_next(trade.time_us)
        self.last_mark, self.last_us = trade.price, trade.time_us
        self.processed_trades += 1
        with localcontext() as ctx:
            ctx.prec = 128
            equity = engine.cash + engine.reserve + (engine.inventory + engine.dust) * bid
            self.peak_equity = max(self.peak_equity, equity)
            self.max_drawdown = max(
                self.max_drawdown, (self.peak_equity - equity) / self.peak_equity
            )

    def run(self, trades: Iterable[Trade]) -> dict[str, Any]:
        for trade in trades:
            self.step(trade)
        return self.finish()

    def checkpoint(self) -> dict[str, Any]:
        excluded = {"rules_at", "execution", "decisions", "envelope"}
        state = _encode({key: value for key, value in self.__dict__.items() if key not in excluded})
        payload = {
            "state": state,
            "execution": self.execution.checkpoint(),
            "selector": _encode(vars(self.decisions.state)),
            "envelope": _encode(asdict(self.envelope)),
            "parent_hash": self.decisions.runtime.parent.model_hash,
            "release_evaluations": dict(self.decisions.release_evaluations),
        }
        return {"payload": payload, "sha256": canonical_hash(payload)}

    def restore(self, checkpoint: dict[str, Any]) -> None:
        from .serial_replay import _State

        payload = checkpoint["payload"]
        if canonical_hash(payload) != checkpoint["sha256"]:
            raise ValueError("REPLAY_CHECKPOINT_HASH_MISMATCH")
        state = _decode(payload["state"])
        if (
            state["identity"] != self.identity
            or state["start_us"] != self.start_us
            or state["end_us"] != self.end_us
            or payload["parent_hash"] != self.decisions.runtime.parent.model_hash
            or _decode(payload["envelope"]) != asdict(self.envelope)
        ):
            raise ValueError("REPLAY_CHECKPOINT_IDENTITY_MISMATCH")
        self.execution.rules = self.rules_at(state["last_us"])
        self.execution.restore(payload["execution"])
        self.__dict__.update(state)
        self.full_days, self.net_days = Counter(self.full_days), Counter(self.net_days)
        self.decisions.state = _State(**_decode(payload["selector"]))
        self.decisions.release_evaluations = Counter(payload["release_evaluations"])

    def finish(self) -> dict[str, Any]:
        from datetime import UTC, datetime
        from statistics import median

        if self.last_mark is None:
            raise ValueError("NO_REPLAY_TRADES")
        if self.last_us != self.identity.get("expected_last_trade_us", self.end_us - 1):
            raise ValueError("PHYSICAL_CUTOFF_NOT_REACHED")
        if (
            "expected_trade_count" in self.identity
            and self.processed_trades != self.identity["expected_trade_count"]
        ):
            raise ValueError("FULL_INTERVAL_TRADE_COUNT_MISMATCH")
        self.completed = True
        engine = self.execution
        days = (
            datetime.fromtimestamp((self.end_us - 1) / 1_000_000, UTC).date()
            - datetime.fromtimestamp(self.start_us / 1_000_000, UTC).date()
        ).days + 1
        holds = self.holds_us + (
            [self.end_us - engine.entry_us] if engine.entry_us is not None else []
        )
        cycles = engine.counts["FULLY_FILLED_CYCLES"]
        positive = engine.counts["NET_POSITIVE_CYCLES"]
        settlements = engine.settlements
        with localcontext() as ctx:
            ctx.prec = 128
            net = sum((D(row["net_profit"]) for row in settlements), ZERO)
            gross = sum((D(row["gross_pnl"]) for row in settlements), ZERO)
            realized_fees = sum((D(row["realized_fees_quote"]) for row in settlements), ZERO)
            release_loss = sum((D(row["actual_release_loss"]) for row in settlements), ZERO)
            theoretical_loss = sum((D(row["loss_usdt"]) for row in self.release_signals), ZERO)
        buy_orders = [order for order in engine.orders if order.side == "BUY"]
        sell_orders = [
            order for order in engine.orders if order.side == "SELL" and not order.release
        ]

        def rate(numerator: int, denominator: int) -> str | None:
            return str(D(numerator) / denominator) if denominator else None

        return {
            "STRATEGY": "B10_FROZEN",
            "EXECUTION_PROFILE": engine.profile.name,
            "STATUS": "COMPLETED_PARAMETERIZED_EXECUTION_REPLAY",
            "identity": self.identity,
            "HISTORICAL_L2": "UNKNOWN",
            "BOOK_MODEL": "PARAMETERIZED_CADENCED_DEPTH_BUDGET",
            "REFERENCE_PRICE_ALIGNMENT": "INFERRED_TRADE_SIDE_BBO",
            "RATE_LIMIT_MODEL": "PARAMETERIZED_CONSERVATIVE_ACCEPTED_ORDER_THROTTLE",
            "PRICE_PATH_REFERENCE_CYCLES": 3580880,
            "FULLY_FILLED_CYCLES": cycles,
            "NET_POSITIVE_CYCLES": positive,
            "REALITY_RETENTION_RATIO": str(D(cycles) / D(3580880)),
            "ECONOMIC_RETENTION_RATIO": str(D(positive) / D(3580880)),
            "ZERO_CYCLE_DAYS": days - len(self.full_days),
            "ACTIVE_DAYS": len(self.full_days),
            "NET_ZERO_CYCLE_DAYS": days - len(self.net_days),
            "AVG_CYCLES_DAY": str(D(cycles) / days),
            "MEDIAN_CYCLES_DAY": median(
                list(self.full_days.values()) + [0] * (days - len(self.full_days))
            ),
            "NET_PNL_FIXED_100": str(net),
            "GROSS_PNL_FIXED_100": str(gross),
            "REALIZED_FEES_QUOTE": str(realized_fees),
            "EXECUTED_RELEASE_LOSS": str(release_loss),
            "THEORETICAL_RELEASE_LOSS": str(theoretical_loss),
            "BUY_FULL_FILL_RATE": rate(
                sum(order.status == "FILLED" for order in buy_orders), len(buy_orders)
            ),
            "SELL_FULL_FILL_RATE": rate(
                sum(order.status == "FILLED" for order in sell_orders), len(sell_orders)
            ),
            "PARTIAL_FILL_RATE": rate(
                sum(order.had_partial for order in engine.orders), len(engine.orders)
            ),
            "MISSED_BY_LATENCY": engine.counts["MISSED_BY_LATENCY"],
            "MISSED_BY_QUEUE": engine.counts["MISSED_BY_QUEUE"],
            "MISSED_BY_FILTER": engine.counts["ORDER_REJECTION_COUNT"],
            "MISSED_BY_FEE": cycles - positive,
            "NET_EDGE_PER_COMPLETED_CYCLE": str(net / cycles) if cycles else None,
            "RELEASE_SIGNALS": engine.counts["RELEASE_SIGNALS"],
            "RELEASE_FILLED": engine.counts["RELEASE_FILLED"],
            "RELEASE_PARTIAL": engine.counts["RELEASE_PARTIAL"],
            "RELEASES_ACTUAL_GT10BPS_ENTRY_NOTIONAL": engine.counts["RELEASES_ACTUAL_GT10BPS"],
            "RELEASES_GT10BPS_EXECUTED_LOT": engine.counts["RELEASES_GT10BPS_EXECUTED_LOT"],
            "RELEASES_GT10BPS_SIGNAL_BANK": engine.counts["RELEASES_GT10BPS_SIGNAL_BANK"],
            "TOTAL_SLIPPAGE": None,
            "SLIPPAGE_STATUS": (
                "Embedded in proxy execution prices; spread/latency/slippage decomposition UNKNOWN"
            ),
            "TOTAL_FEES": str(engine.fees),
            "RESERVE_INITIAL": "5",
            "RESERVE_FUNDING": str(engine.reserve_funding),
            "RESERVE_CONSUMPTION": str(engine.reserve_consumption),
            "RESERVE_MIN": str(engine.reserve_min),
            "RESERVE_FINAL": str(engine.reserve),
            "RESERVE_DEPLETION_EVENTS": engine.counts["RESERVE_DEPLETION_EVENTS"],
            "RELEASE_BLOCKED_BY_RESERVE": self.decisions.release_evaluations[
                "INSUFFICIENT_RESERVE"
            ],
            "RESERVE_COVERAGE_RATIO": str(engine.reserve_consumption / release_loss)
            if release_loss
            else None,
            "OPERATING_FINAL": str(engine.cash),
            "OPEN_INVENTORY": str(engine.inventory),
            "DUST_BASE": str(engine.dust),
            "DUST_COST_BASIS": str(engine.dust_cost),
            "MAX_HOLD_HOURS": str(D(max(holds, default=0)) / D(3_600_000_000)),
            "LOCK_HOURS_GT24": str(
                sum((D(max(0, hold - 86_400_000_000)) for hold in holds), ZERO) / D(3_600_000_000)
            ),
            "MAX_DRAWDOWN": str(self.max_drawdown),
            "COUNTS": dict(engine.counts),
            "RELEASE_EVALUATIONS": dict(self.decisions.release_evaluations),
            "OPPORTUNITY_LEVEL_FUNNEL": (
                "NOT_RECONSTRUCTED; reference count is not an executable order schedule"
            ),
            "PROCESSED_TRADES": self.processed_trades,
            "VERDICT": "INCONCLUSIVE_EXECUTION_DATA",
            "VERDICT_REASON": (
                "Independent audit and scientific interpretation required; "
                "historical L2 is parameterized."
            ),
        }
