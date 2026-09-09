"""M024 triangular pre-aged queue mechanics.

This module is an offline, normalized mechanics probe.  It models physical
one-unit orders, shared public queue barriers, and auditable ownership; it does
not create fills, capital, or queue priority that is absent from the observed
events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR
from statistics import median
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.zonal_ping_pong import M021_TICK_SIZE, ZERO, D

ONE = D("1")
INITIAL_LEVELS = 50
INITIAL_DEPTH_ONE_LEVELS = 25
MAX_OPEN_ORDERS = 200


def _dec(value: Any) -> D:
    return value if isinstance(value, D) else D(str(value))


def _s(value: D) -> str:
    return str(value)


def _floor_tick(value: D) -> D:
    return (value / M021_TICK_SIZE).to_integral_value(rounding=ROUND_FLOOR) * M021_TICK_SIZE


def _ceil_tick(value: D) -> D:
    return (value / M021_TICK_SIZE).to_integral_value(rounding=ROUND_CEILING) * M021_TICK_SIZE


@dataclass
class QueueSegment:
    activation_us: int
    public_barrier: D
    order_ids: list[int] = field(default_factory=list)
    public_remaining: D = ZERO
    native_book_upper_us: int = 0


@dataclass
class PriceQueueGroup:
    side: str
    price: D
    public_queue: D = ZERO
    public_remaining: D = ZERO
    segments: list[QueueSegment] = field(default_factory=list)

    @property
    def own_order_ids(self) -> list[int]:
        return [order_id for segment in self.segments for order_id in segment.order_ids]


@dataclass
class QueueOrder:
    order_id: int
    side: str
    price: D
    quantity: D
    submitted_us: int
    active_us: int
    role: str = "ENTRY"
    column: int = 1
    level: int = 1
    direction: str = "BUY_FIRST"
    status: str = "PENDING"
    filled: D = ZERO
    reserved_quote: D = ZERO
    reserved_base: D = ZERO
    activation_evaluated_us: int | None = None
    cancel_us: int | None = None
    queue_wait_start_us: int | None = None
    source_order_id: int | None = None
    lot_ids: list[int] = field(default_factory=list)
    capital_source: str = "OWN"
    queue_ahead_at_activation: D = ZERO
    activation_native_upper_us: int = 0
    cell_id: str | None = None
    asset_basis: D = ZERO

    @property
    def remaining(self) -> D:
        return self.quantity - self.filled


@dataclass
class Lot:
    lot_id: int
    entry_order_id: int
    column: int
    side: str
    quantity: D
    basis: D
    created_us: int
    stage: str = "HOLDING"
    asset_basis: D = ZERO
    closed_quantity: D = ZERO
    restored_cost: D = ZERO


class TriangularPreAgedQueueProbe:
    """Shared public queues with independent physical one-unit columns."""

    normalized_label = "M024 TRIANGULAR PRE-AGED QUEUE. NORMALIZED MECHANICS ONLY."

    def __init__(
        self,
        *,
        start_us: int,
        end_us: int,
        latency_us: int = 1,
        cancel_latency_us: int = 1,
        max_open_orders: int = MAX_OPEN_ORDERS,
    ) -> None:
        if max_open_orders != MAX_OPEN_ORDERS:
            raise ValueError("M024_CAP_MUST_BE_200")
        self.start_us = int(start_us)
        self.end_us = int(end_us)
        self.latency_us = int(latency_us)
        self.cancel_latency_us = int(cancel_latency_us)
        self.max_open_orders = max_open_orders
        self.cash = ZERO
        self.reserved_usdt = ZERO
        self.free_usdc = ZERO
        self.reserved_usdc = ZERO
        self.initial_usdt = ZERO
        self.initial_usdc = ZERO
        self.initial_mark = ZERO
        self.growth_pool = ZERO
        self.realized_pnl = ZERO
        self.realized_disposal_pnl = ZERO
        self.growth_earned = ZERO
        self.unrealized_pnl = ZERO
        self.inventory_qty = ZERO
        self.orders: list[QueueOrder] = []
        self.lots: list[Lot] = []
        self.groups: dict[tuple[str, D], PriceQueueGroup] = {}
        self.audit: list[dict[str, Any]] = []
        self._next_order_id = 1
        self._next_lot_id = 1
        self._processed_trades: set[str] = set()
        self._last_logical_us = self.start_us
        self._last_book: dict[str, Any] | None = None
        self._initialized = False
        self._active_order_time_us = 0
        self._active_capital_time_us = ZERO
        self._last_observation_us = self.start_us
        self._max_open_orders = 0
        self._fill_count = 0
        self._cycles = 0
        self._buy_first_cycles = 0
        self._sell_first_cycles = 0
        self._column_cycle_counts: dict[int, int] = {}
        self._column_waits: dict[int, list[int]] = {}
        self._order_waits: dict[int, list[int]] = {}
        self._preaging_cases: list[dict[str, Any]] = []
        self._deferred_returns: dict[int, int] = {}
        self._growth_cells = 0
        self._initial_depth_two = 25
        self._max_queue_depth = 0
        self._rolling_pending: dict[int, dict[str, Any]] = {}
        self._rolling_ready: list[dict[str, Any]] = []
        self._rolling_cancels = 0
        self._rolling_replacements = 0

    def _record(self, event: str, time_us: int, **fields: Any) -> None:
        self.audit.append({"event": event, "time_us": int(time_us), **fields})

    def _check_time(self, time_us: int) -> None:
        if time_us < self.start_us or time_us >= self.end_us:
            raise ValueError("CUTOFF_EXCLUSIVE")
        if time_us < self._last_logical_us:
            raise ValueError("NONCAUSAL_LOGICAL_TIME")
        self._last_logical_us = time_us

    def _observe(self, now: int) -> None:
        elapsed = max(0, now - self._last_observation_us)
        self._active_order_time_us += elapsed * self.open_order_count
        mark = self._last_book["bids"][0][0] if self._last_book else ZERO
        active_capital = sum(
            (
                order.remaining * order.price
                if order.side == "BUY"
                else order.remaining * mark
            )
            for order in self.active_orders
        )
        self._active_capital_time_us += active_capital * D(elapsed)
        self._last_observation_us = now

    @property
    def open_order_count(self) -> int:
        return sum(order.status in {"PENDING", "ACTIVE", "CANCEL_PENDING"} for order in self.orders)

    @property
    def active_orders(self) -> list[QueueOrder]:
        return [
            order
            for order in self.orders
            if order.status in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
        ]

    def _group(self, side: str, price: D) -> PriceQueueGroup:
        key = (side, price)
        if key not in self.groups:
            self.groups[key] = PriceQueueGroup(side, price)
        return self.groups[key]

    def seed_public_queue(
        self, side: str, price: D | str, public_quantity: D | str, *, activation_us: int = 0
    ) -> PriceQueueGroup:
        """Install one observed public barrier for synthetic queue tests."""
        value = _dec(price)
        quantity = _dec(public_quantity)
        if side not in {"BUY", "SELL"} or quantity < ZERO:
            raise ValueError("M024_INVALID_QUEUE_SEED")
        group = self._group(side, value)
        group.public_queue = quantity
        group.public_remaining = quantity
        if not group.segments:
            group.segments.append(QueueSegment(int(activation_us), quantity, [], quantity))
        else:
            group.segments[0].public_barrier = quantity
            group.segments[0].public_remaining = quantity
        return group

    def seed_capital(self, *, usdt: D | str = ZERO, usdc: D | str = ZERO) -> None:
        """Set an explicit synthetic starting balance before manual queue tests."""
        if self.orders or self._initialized:
            raise ValueError("M024_CAPITAL_SEED_AFTER_ORDERS")
        self.cash = _dec(usdt)
        self.free_usdc = _dec(usdc)
        if self.cash < ZERO or self.free_usdc < ZERO:
            raise ValueError("M024_NEGATIVE_CAPITAL")

    def _locked_sell_proceeds(self, excluded_source_order_id: int | None = None) -> D:
        """USDT proceeds still owned by unresolved SELL-first economic sequences."""
        total = ZERO
        for lot in self.lots:
            if lot.side != "SELL" or lot.entry_order_id == excluded_source_order_id:
                continue
            if lot.stage in {"RESTORED", "RECYCLED"}:
                continue
            has_backed_return = any(
                order.role == "RETURN"
                and order.direction == "SELL_FIRST"
                and order.source_order_id == lot.entry_order_id
                and order.status in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
                for order in self.orders
            )
            if not has_backed_return:
                total += lot.quantity * lot.basis
        return total

    def _reserve_for_order(self, order: QueueOrder) -> None:
        if order.side == "BUY":
            required = order.price * order.quantity
            excluded_source = (
                order.source_order_id
                if order.role == "RETURN" and order.direction == "SELL_FIRST"
                else None
            )
            locked_sell_proceeds = self._locked_sell_proceeds(excluded_source)
            if order.capital_source == "GROWTH":
                if self.growth_pool < required or self.cash - locked_sell_proceeds < required:
                    raise ValueError("M024_GROWTH_INSUFFICIENT")
                self.cash -= required
                self.growth_pool -= required
            elif self.cash - self.growth_pool - locked_sell_proceeds < required:
                raise ValueError("M024_USDT_OWNERSHIP_INSUFFICIENT")
            else:
                self.cash -= required
            self.reserved_usdt += required
            order.reserved_quote = required
        else:
            if self.free_usdc < order.quantity:
                raise ValueError("M024_USDC_OWNERSHIP_INSUFFICIENT")
            self.free_usdc -= order.quantity
            self.reserved_usdc += order.quantity
            order.reserved_base = order.quantity

    def submit_order(
        self,
        side: str,
        price: D | str,
        *,
        quantity: D | str = ONE,
        time_us: int | None = None,
        role: str = "ENTRY",
        column: int = 1,
        level: int = 1,
        direction: str = "BUY_FIRST",
        source_order_id: int | None = None,
        capital_source: str = "OWN",
        activate_immediately: bool = False,
        cell_id: str | None = None,
        asset_basis: D | str = ZERO,
    ) -> QueueOrder:
        now = self.start_us if time_us is None else int(time_us)
        self._check_time(now)
        if side not in {"BUY", "SELL"} or _dec(quantity) != ONE:
            raise ValueError("M024_INVALID_ORDER")
        if side == "SELL" and _dec(asset_basis) > ZERO and _dec(price) <= _dec(asset_basis):
            raise ValueError("M024_NEGATIVE_EXIT_PROHIBITED")
        if self.open_order_count >= self.max_open_orders:
            raise ValueError("M024_OPEN_ORDER_CAP_EXCEEDED")
        order = QueueOrder(
            self._next_order_id,
            side,
            _dec(price),
            _dec(quantity),
            now,
            now if activate_immediately else now + self.latency_us,
            role=role,
            column=int(column),
            level=int(level),
            direction=direction,
            source_order_id=source_order_id,
            capital_source=capital_source,
            cell_id=cell_id or f"CELL:{self._next_order_id}",
            asset_basis=_dec(asset_basis),
        )
        self._reserve_for_order(order)
        self._next_order_id += 1
        self.orders.append(order)
        self._max_open_orders = max(self._max_open_orders, self.open_order_count)
        self._record(
            "SUBMIT",
            now,
            order_id=order.order_id,
            side=side,
            price=_s(order.price),
            quantity=_s(order.quantity),
            role=role,
            column=column,
            level=level,
            direction=direction,
            source_order_id=source_order_id,
            capital_source=capital_source,
            active_us=order.active_us,
            cell_id=order.cell_id,
            asset_basis=_s(order.asset_basis),
        )
        if activate_immediately:
            self._activate(order, now)
        return order

    add_order = submit_order

    def _displayed_queue(self, price: D, side: str) -> D:
        if self._last_book is None:
            return ZERO
        levels = self._last_book["bids"] if side == "BUY" else self._last_book["asks"]
        return next((quantity for level_price, quantity in levels if level_price == price), ZERO)

    def _activate(self, order: QueueOrder, now: int) -> None:
        if order.status != "PENDING":
            return
        order.status = "ACTIVE"
        order.activation_evaluated_us = now
        order.queue_wait_start_us = now
        order.activation_native_upper_us = int(
            (self._last_book or {}).get("exchange_upper_us") or now
        )
        group = self._group(order.side, order.price)
        barrier = self._displayed_queue(order.price, order.side)
        if self._last_book is None and group.segments:
            barrier = group.segments[-1].public_barrier
        if group.segments and group.segments[-1].activation_us == now:
            segment = group.segments[-1]
            if not segment.order_ids:
                segment.public_barrier = barrier
                segment.public_remaining = barrier
                barrier_to_add = ZERO if group.public_queue > ZERO else barrier
            else:
                barrier_to_add = ZERO
        else:
            barrier_to_add = max(ZERO, barrier - group.public_remaining)
            segment = QueueSegment(
                now,
                barrier_to_add,
                [],
                barrier_to_add,
                order.activation_native_upper_us,
            )
            group.segments.append(segment)
        segment.order_ids.append(order.order_id)
        self._max_queue_depth = max(
            self._max_queue_depth,
            len(group.own_order_ids),
        )
        group.public_queue += barrier_to_add
        group.public_remaining += barrier_to_add
        predecessor_quantity = sum(
            item.remaining
            for item in self.orders
            if item.order_id in group.own_order_ids
            and item.order_id != order.order_id
            and item.status in {"ACTIVE", "CANCEL_PENDING"}
        )
        order.queue_ahead_at_activation = group.public_remaining + predecessor_quantity
        self._record(
            "ACTIVATED",
            now,
            order_id=order.order_id,
            side=order.side,
            price=_s(order.price),
            public_queue_ahead=_s(barrier),
            public_barrier_added=_s(barrier_to_add),
            public_remaining=_s(group.public_remaining),
            cohort_activation_us=now,
            queue_ahead_at_activation=_s(order.queue_ahead_at_activation),
            native_book_upper_us=(
                self._last_book.get("exchange_upper_us") if self._last_book else None
            ),
        )

    def _release_reservation(self, order: QueueOrder, remaining: D) -> None:
        if remaining <= ZERO:
            return
        if order.side == "BUY":
            amount = remaining * order.price
            self.reserved_usdt -= amount
            order.reserved_quote -= amount
            if order.capital_source != "GROWTH":
                self.cash += amount
            else:
                self.cash += amount
                self.growth_pool += amount
        else:
            self.reserved_usdc -= remaining
            order.reserved_base -= remaining
            if order.role == "RETURN" and order.direction == "BUY_FIRST":
                self.inventory_qty += remaining
            else:
                self.free_usdc += remaining

    def _advance(self, now: int) -> None:
        for order in list(self.active_orders):
            if (
                order.status == "CANCEL_PENDING"
                and order.cancel_us is not None
                and order.cancel_us <= now
            ):
                remaining = order.remaining
                self._release_reservation(order, remaining)
                self._remove_from_group(order)
                order.status = "CANCELED_PARTIAL" if order.filled > ZERO else "CANCELED"
                self._record("CANCEL_ACK", now, order_id=order.order_id, remaining=_s(remaining))
                replacement = self._rolling_pending.pop(order.order_id, None)
                if order.filled == ZERO:
                    if replacement is not None:
                        self._rolling_ready.append(replacement)
                elif order.role == "ENTRY":
                    lot = next(
                        (item for item in self.lots if item.entry_order_id == order.order_id),
                        None,
                    )
                    if lot is None or lot.quantity != order.filled:
                        raise ValueError("M024_PARTIAL_CANCEL_LOT_MISMATCH")
                    if replacement is not None:
                        self._record(
                            "ROLLING_PARTIAL_CANCEL_ACK",
                            now,
                            order_id=order.order_id,
                            filled_quantity=_s(order.filled),
                            released_quantity=_s(remaining),
                            cell_id=order.cell_id,
                        )
                    lot.stage = (
                        "SUBSTEP_INVENTORY_LOCKED"
                        if order.side == "BUY"
                        else "SUBSTEP_RETURN_DEBT_LOCKED"
                    )
                    self._deferred_returns.pop(order.order_id, None)
                    self._record(
                        "PARTIAL_LOT_SUBSTEP_LOCKED",
                        now,
                        order_id=order.order_id,
                        lot_id=lot.lot_id,
                        side=order.side,
                        quantity=_s(lot.quantity),
                        minimum_order_quantity=_s(ONE),
                        cycle_counted=False,
                    )
                elif order.filled > ZERO:
                    raise ValueError("M024_PARTIAL_RETURN_CANCEL_ACK_UNSUPPORTED")
                continue
            if (
                order.status == "CANCEL_PENDING"
                and order.activation_evaluated_us is None
                and order.active_us <= now
            ):
                reason = self._activation_reason(order)
                if reason is None:
                    order.status = "PENDING"
                    self._activate(order, now)
                    order.status = "CANCEL_PENDING"
                else:
                    self._release_reservation(order, order.remaining)
                    if order.role == "RETURN" and order.source_order_id is not None:
                        if not order.lot_ids:
                            raise ValueError("M024_RETURN_LOT_MISSING")
                        self._deferred_returns[order.source_order_id] = order.lot_ids[0]
                    order.status = reason
                    self._record(reason, now, order_id=order.order_id)
                continue
            if order.status == "PENDING" and order.active_us <= now:
                reason = self._activation_reason(order)
                if reason is None:
                    self._activate(order, now)
                else:
                    self._release_reservation(order, order.remaining)
                    if order.role == "RETURN" and order.source_order_id is not None:
                        if not order.lot_ids:
                            raise ValueError("M024_RETURN_LOT_MISSING")
                        self._deferred_returns[order.source_order_id] = order.lot_ids[0]
                    order.status = reason
                    self._record(reason, now, order_id=order.order_id)
        self._advance_shadow_queues(now)
        self._try_deferred_returns(now)
        self._manage_rolling_window(now)

    def _advance_shadow_queues(self, now: int) -> None:
        for case in self._preaging_cases:
            shadow = case.get("shadow")
            if shadow is None or shadow["status"] != "PENDING":
                continue
            if int(shadow["active_us"]) <= now:
                reason = self._shadow_activation_reason(shadow)
                if reason is not None:
                    shadow["status"] = reason
                    case["status"] = "CENSORED_SHADOW_REJECTED"
                    self._record(
                        "SHADOW_REJECTED",
                        now,
                        c2_order_id=case["c2_order_id"],
                        reason=reason,
                    )
                    continue
                shadow["status"] = "ACTIVE"
                shadow["activation_us"] = now
                shadow["activation_native_upper_us"] = int(
                    (self._last_book or {}).get("exchange_upper_us") or now
                )
                shadow["public_remaining"] = _s(self._displayed_queue(
                    _dec(shadow["price"]), shadow["side"]
                ))
                group = self.groups.get((shadow["side"], _dec(shadow["price"])))
                shadow["own_remaining"] = _s(
                    sum(
                        (
                            order.remaining
                            for order in self.orders
                            if group is not None
                            and order.order_id in group.own_order_ids
                            and order.order_id != case["c2_order_id"]
                            and order.status in {"ACTIVE", "CANCEL_PENDING"}
                        ),
                        ZERO,
                    )
                )
                actual_ahead = self._queue_ahead_for_order(case["c2_order_id"])
                case["c2_queue_ahead_at_shadow_activation"] = (
                    _s(actual_ahead) if actual_ahead is not None else None
                )
                case["preaging_queue_advantage_usdc"] = (
                    _s(
                        _dec(shadow["public_remaining"])
                        + _dec(shadow["own_remaining"])
                        - actual_ahead
                    )
                    if actual_ahead is not None
                    else None
                )
                self._record(
                    "SHADOW_ACTIVATED",
                    now,
                    c2_order_id=case["c2_order_id"],
                    price=shadow["price"],
                    public_queue_ahead=shadow["public_remaining"],
                    own_queue_ahead=shadow["own_remaining"],
                    native_book_upper_us=shadow["activation_native_upper_us"],
                )

    def _feed_shadow_queues(
        self,
        price: D,
        quantity: D,
        buyer_maker: bool,
        now: int,
        native_us: int,
        trade_id: str,
    ) -> None:
        for case in self._preaging_cases:
            shadow = case.get("shadow")
            if shadow is None or shadow["status"] != "ACTIVE":
                continue
            if now <= int(shadow["activation_us"]):
                continue
            if native_us <= max(
                int(shadow["active_us"]),
                int(shadow["activation_us"]),
                int(shadow["activation_native_upper_us"]),
            ):
                continue
            side = shadow["side"]
            eligible = (side == "BUY" and buyer_maker and price <= _dec(shadow["price"])) or (
                side == "SELL" and not buyer_maker and price >= _dec(shadow["price"])
            )
            if not eligible:
                continue
            remaining = quantity
            public_debit = ZERO
            own_debit = ZERO
            fill_debit = ZERO
            if price == _dec(shadow["price"]):
                ahead = min(_dec(shadow["public_remaining"]), remaining)
                shadow["public_remaining"] = _s(_dec(shadow["public_remaining"]) - ahead)
                remaining -= ahead
                public_debit = ahead
            if remaining > ZERO:
                ahead = min(_dec(shadow["own_remaining"]), remaining)
                shadow["own_remaining"] = _s(_dec(shadow["own_remaining"]) - ahead)
                remaining -= ahead
                own_debit = ahead
            if remaining > ZERO:
                unfilled = ONE - _dec(shadow["filled"])
                fill_debit = min(remaining, unfilled)
                shadow["filled"] = _s(_dec(shadow["filled"]) + fill_debit)
            if public_debit + own_debit + fill_debit > ZERO:
                self._record(
                    "SHADOW_TRADE_APPLIED",
                    now,
                    c2_order_id=case["c2_order_id"],
                    source_id=trade_id,
                    native_time_us=native_us,
                    price=_s(price),
                    original_quantity=_s(quantity),
                    public_debit=_s(public_debit),
                    own_debit=_s(own_debit),
                    fill_debit=_s(fill_debit),
                )
            if _dec(shadow["filled"]) >= ONE:
                shadow["status"] = "FILLED"
                shadow["fill_us"] = now
                self._record(
                    "SHADOW_FILL",
                    now,
                    c2_order_id=case["c2_order_id"],
                    price=shadow["price"],
                    source_id=trade_id,
                    native_time_us=native_us,
                )
                self._close_preaging_case(case)

    def _close_preaging_case(self, case: dict[str, Any]) -> None:
        shadow = case.get("shadow")
        if shadow is None:
            return
        if case.get("actual_fill_us") is not None and shadow.get("fill_us") is not None:
            case["benefit_us"] = int(shadow["fill_us"]) - int(case["actual_fill_us"])
            case["status"] = "CLOSED"

    def _queue_ahead_for_order(self, order_id: int) -> D | None:
        """Return causal public plus own quantity ahead of one resting order."""
        order = next((item for item in self.orders if item.order_id == order_id), None)
        if order is None:
            return None
        group = self.groups.get((order.side, order.price))
        if group is None:
            return None
        ahead = ZERO
        for segment in group.segments:
            ahead += segment.public_remaining
            for own_id in segment.order_ids:
                if own_id == order_id:
                    return ahead
                predecessor = next(
                    (item for item in self.orders if item.order_id == own_id), None
                )
                if predecessor is not None:
                    ahead += predecessor.remaining
        return None

    def _shadow_activation_reason(self, shadow: dict[str, Any]) -> str | None:
        if self._last_book is None:
            return "SHADOW_REJECTED_NO_BOOK"
        price = _dec(shadow["price"])
        bid = self._last_book["bids"][0][0]
        ask = self._last_book["asks"][0][0]
        if shadow["side"] == "BUY":
            if price >= ask:
                return "SHADOW_REJECTED_POST_ONLY"
            if price < self._last_book["known_bid_floor"]:
                return "SHADOW_REJECTED_COVERAGE"
            return None
        if price <= bid:
            return "SHADOW_REJECTED_POST_ONLY"
        if price > self._last_book["known_ask_ceiling"]:
            return "SHADOW_REJECTED_COVERAGE"
        return None

    def _activation_reason(self, order: QueueOrder) -> str | None:
        if self._last_book is None:
            return None
        bid = self._last_book["bids"][0][0]
        ask = self._last_book["asks"][0][0]
        if order.side == "BUY":
            if order.price >= ask:
                return "REJECTED_POST_ONLY"
            if any(
                other.order_id != order.order_id
                and other.side == "SELL"
                and other.status in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
                and other.price <= order.price
                for other in self.orders
            ):
                return "REJECTED_SELF_CROSS"
            if order.price < self._last_book["known_bid_floor"]:
                return "REJECTED_COVERAGE"
            return None
        if order.price <= bid:
            return "REJECTED_POST_ONLY"
        if order.asset_basis > ZERO and order.price <= order.asset_basis:
            return "REJECTED_NEGATIVE_EXIT"
        if any(
            other.order_id != order.order_id
            and other.side == "BUY"
            and other.status in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
            and other.price >= order.price
            for other in self.orders
        ):
            return "REJECTED_SELF_CROSS"
        if order.price > self._last_book["known_ask_ceiling"]:
            return "REJECTED_COVERAGE"
        return None

    def cancel(self, order_id: int, *, time_us: int) -> None:
        self._check_time(time_us)
        order = next((item for item in self.orders if item.order_id == order_id), None)
        if order is None or order.status not in {"PENDING", "ACTIVE"}:
            return
        if order.filled > ZERO:
            raise ValueError("M024_PARTIAL_CANCEL_BLOCKED")
        order.status = "CANCEL_PENDING"
        order.cancel_us = time_us + self.cancel_latency_us
        self._record("CANCEL_REQUEST", time_us, order_id=order_id, effective_us=order.cancel_us)

    def fund_growth_cell(
        self,
        side: str,
        price: D | str,
        *,
        time_us: int,
        level: int,
        column: int = 2,
    ) -> QueueOrder:
        if side != "BUY":
            raise ValueError("M024_GROWTH_IS_USDT_ONLY")
        order = self.submit_order(
            side,
            price,
            time_us=time_us,
            role="ENTRY",
            level=level,
            column=column,
            direction="BUY_FIRST",
            capital_source="GROWTH",
            cell_id=f"GROWTH:{side}:L{level:02d}:C{column}",
        )
        self._growth_cells += 1
        self._record(
            "GROWTH_CELL_FUNDED",
            time_us,
            order_id=order.order_id,
            level=level,
            column=column,
            amount=_s(order.price),
        )
        return order

    def _remove_from_group(self, order: QueueOrder) -> None:
        group = self.groups.get((order.side, order.price))
        if group is None:
            return
        for segment in group.segments:
            if order.order_id in segment.order_ids:
                segment.order_ids.remove(order.order_id)

    def _make_lot(self, order: QueueOrder, quantity: D, now: int) -> Lot:
        lot = Lot(
            self._next_lot_id,
            order.order_id,
            order.column,
            order.side,
            quantity,
            order.price,
            now,
            asset_basis=order.asset_basis if order.asset_basis > ZERO else order.price,
        )
        self._next_lot_id += 1
        self.lots.append(lot)
        return lot

    def _entry_lot_for_fill(self, order: QueueOrder, quantity: D, now: int) -> Lot:
        lot = next((item for item in self.lots if item.entry_order_id == order.order_id), None)
        if lot is None:
            lot = self._make_lot(order, quantity, now)
            order.lot_ids.append(lot.lot_id)
        else:
            lot.quantity += quantity
        lot.stage = "PARTIAL_HOLDING" if order.side == "BUY" else "PARTIAL_SOLD"
        return lot

    def _return_target(self, order: QueueOrder) -> tuple[str, D] | None:
        if order.direction == "BUY_FIRST":
            bid = self._last_book["bids"][0][0] if self._last_book else order.price
            return "SELL", max(_ceil_tick(order.price + M021_TICK_SIZE), bid + M021_TICK_SIZE)
        ask = self._last_book["asks"][0][0] if self._last_book else order.price
        return "BUY", min(_floor_tick(order.price - M021_TICK_SIZE), ask - M021_TICK_SIZE)

    def _submit_return(self, source: QueueOrder, now: int, lot: Lot) -> QueueOrder | None:
        side_price = self._return_target(source)
        if side_price is None:
            return None
        side, price = side_price
        conflicts = [
            item
            for item in self.active_orders
            if item.role == "ENTRY"
            and (
                (item.side == side and item.price == price)
                or (side == "BUY" and item.side == "SELL" and item.price <= price)
                or (side == "SELL" and item.side == "BUY" and item.price >= price)
            )
        ]
        if conflicts:
            self._deferred_returns[source.order_id] = lot.lot_id
            cancelable = [item for item in conflicts if item.filled == ZERO]
            for conflict in conflicts:
                if conflict.filled == ZERO and conflict.status != "CANCEL_PENDING":
                    self.cancel(conflict.order_id, time_us=now)
            self._record(
                "RETURN_WAITING_FOR_FREE_CANCEL",
                now,
                source_order_id=source.order_id,
                conflict_order_ids=[item.order_id for item in conflicts],
                cancelable_order_ids=[item.order_id for item in cancelable],
                partial_blocker_order_ids=[
                    item.order_id for item in conflicts if item.filled > ZERO
                ],
            )
            return None
        if self.open_order_count >= self.max_open_orders:
            candidate = self._farthest_youngest_free_entry(side)
            self._deferred_returns[source.order_id] = lot.lot_id
            if candidate is not None:
                self.cancel(candidate.order_id, time_us=now)
                self._record(
                    "RETURN_WAITING_FOR_HEADROOM_CANCEL",
                    now,
                    source_order_id=source.order_id,
                    conflict_order_ids=[candidate.order_id],
                )
            else:
                self._record(
                    "RETURN_DEFERRED",
                    now,
                    source_order_id=source.order_id,
                    reason="M024_NO_CANCELABLE_RETURN_HEADROOM",
                )
            return None
        temporary_base = side == "SELL" and source.direction == "BUY_FIRST"
        try:
            if side == "SELL" and source.direction == "BUY_FIRST":
                # The return sells the exact entry lot.  Reserve that lot in
                # the same ownership ledger as an initial SELL without
                # borrowing from another column's free USDC.
                if self.inventory_qty < lot.quantity:
                    raise ValueError("M024_INVENTORY_LOT_UNAVAILABLE")
                self.inventory_qty -= lot.quantity
                self.free_usdc += lot.quantity
            returned = self.submit_order(
                side,
                price,
                quantity=lot.quantity,
                time_us=now,
                role="RETURN",
                column=source.column,
                level=source.level,
                direction=source.direction,
                source_order_id=source.order_id,
                capital_source="OWN",
                cell_id=source.cell_id,
                asset_basis=lot.asset_basis if side == "SELL" else ZERO,
            )
            returned.lot_ids.append(lot.lot_id)
            self._deferred_returns.pop(source.order_id, None)
            return returned
        except ValueError as exc:
            if temporary_base:
                self.free_usdc -= lot.quantity
                self.inventory_qty += lot.quantity
            self._deferred_returns[source.order_id] = lot.lot_id
            self._record("RETURN_DEFERRED", now, source_order_id=source.order_id, reason=str(exc))
            return None

    def _farthest_youngest_free_entry(self, preferred_side: str | None = None) -> QueueOrder | None:
        if self._last_book is None:
            return None
        bid = self._last_book["bids"][0][0]
        ask = self._last_book["asks"][0][0]
        candidates = [
            order
            for order in self.active_orders
            if order.role == "ENTRY" and order.filled == ZERO and order.status != "CANCEL_PENDING"
        ]
        if preferred_side and any(order.side == preferred_side for order in candidates):
            candidates = [order for order in candidates if order.side == preferred_side]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda order: (
                abs(order.price - (bid if order.side == "BUY" else ask)),
                order.submitted_us,
                order.order_id,
            ),
        )

    def _rolling_prices(self, side: str) -> list[D]:
        if self._last_book is None:
            return []
        anchor = (
            self._last_book["bids"][0][0]
            if side == "BUY"
            else self._last_book["asks"][0][0]
        )
        if side == "BUY":
            return [_floor_tick(anchor - D(rank) * M021_TICK_SIZE) for rank in range(50)]
        return [_ceil_tick(anchor + D(rank) * M021_TICK_SIZE) for rank in range(50)]

    def _manage_rolling_window(self, now: int) -> None:
        """Move only zero-fill free cells after ACK; aged in-window orders stay."""
        if not self._initialized or self._last_book is None:
            return
        for side in ("BUY", "SELL"):
            desired = self._rolling_prices(side)
            desired_set = set(desired)
            active_free = [
                order
                for order in self.active_orders
                if order.side == side and order.role == "ENTRY" and order.filled == ZERO
            ]
            occupied = {order.price for order in active_free}
            missing = [price for price in desired if price not in occupied]

            ready = next(
                (item for item in self._rolling_ready if item["side"] == side), None
            )
            while ready is not None and missing and self.open_order_count < self.max_open_orders:
                price = missing[0]
                if side == "SELL" and ready["asset_basis"] > ZERO:
                    price = max(
                        price,
                        _ceil_tick(ready["asset_basis"] + M021_TICK_SIZE),
                    )
                rank = desired.index(price) + 1
                try:
                    replacement = self.submit_order(
                        side,
                        price,
                        time_us=now,
                        role="ENTRY",
                        column=int(ready["column"]),
                        level=rank,
                        direction="BUY_FIRST" if side == "BUY" else "SELL_FIRST",
                        cell_id=ready["cell_id"],
                        asset_basis=ready["asset_basis"],
                    )
                except ValueError:
                    break
                self._rolling_ready.remove(ready)
                self._rolling_replacements += 1
                self._record(
                    "ROLLING_REPLACEMENT_SUBMITTED",
                    now,
                    order_id=replacement.order_id,
                    replaced_order_id=ready["order_id"],
                    side=side,
                    price=_s(price),
                    level=rank,
                    cell_id=replacement.cell_id,
                )
                occupied.add(price)
                missing = [candidate for candidate in desired if candidate not in occupied]
                ready = next(
                    (item for item in self._rolling_ready if item["side"] == side), None
                )

            deficit = len(missing) - sum(
                item["side"] == side for item in self._rolling_pending.values()
            )
            if deficit <= 0:
                continue
            stale = [
                order
                for order in active_free
                if order.price not in desired_set
                and not (
                    side == "SELL"
                    and order.asset_basis > ZERO
                    and _ceil_tick(order.asset_basis + M021_TICK_SIZE) > max(desired)
                )
                and order.status != "CANCEL_PENDING"
                and order.order_id not in self._rolling_pending
            ]
            anchor = (
                self._last_book["bids"][0][0]
                if side == "BUY"
                else self._last_book["asks"][0][0]
            )
            stale.sort(
                key=lambda order: (
                    abs(order.price - anchor),
                    order.submitted_us,
                    order.order_id,
                ),
                reverse=True,
            )
            for order in stale[:deficit]:
                self._rolling_pending[order.order_id] = {
                    "order_id": order.order_id,
                    "side": side,
                    "column": order.column,
                    "cell_id": order.cell_id,
                    "asset_basis": order.asset_basis,
                }
                self.cancel(order.order_id, time_us=now)
                self._rolling_cancels += 1
                self._record(
                    "ROLLING_CANCEL_REQUESTED",
                    now,
                    order_id=order.order_id,
                    side=side,
                    price=_s(order.price),
                    cell_id=order.cell_id,
                )

    def _try_deferred_returns(self, now: int) -> None:
        pending = sorted(
            self._deferred_returns.items(),
            key=lambda item: next(
                (
                    (lot.created_us, lot.lot_id)
                    for lot in self.lots
                    if lot.lot_id == item[1]
                ),
                (self.end_us, item[1]),
            ),
        )
        for source_id, lot_id in pending:
            source = next((item for item in self.orders if item.order_id == source_id), None)
            lot = next((item for item in self.lots if item.lot_id == lot_id), None)
            if source is not None and lot is not None:
                self._submit_return(source, now, lot)

    def _complete_order(self, order: QueueOrder, now: int) -> None:
        if order.activation_evaluated_us is not None:
            self._order_waits.setdefault(order.column, []).append(
                now - order.activation_evaluated_us
            )
        group = self.groups.get((order.side, order.price))
        if order.role == "ENTRY" and group is not None:
            later = [
                item
                for item in self.orders
                if item.order_id in group.own_order_ids
                and item.order_id != order.order_id
                and item.status in {"ACTIVE", "CANCEL_PENDING"}
            ]
            later.sort(
                key=lambda item: (
                    item.activation_evaluated_us or 0,
                    item.submitted_us,
                    item.order_id,
                )
            )
            seen_c2 = {case["c2_order_id"] for case in self._preaging_cases}
            for aged in later[:1]:
                if aged.order_id in seen_c2:
                    continue
                self._preaging_cases.append(
                    {
                        "c1_order_id": order.order_id,
                        "c2_order_id": aged.order_id,
                        "c1_fill_us": now,
                        "c2_activation_us": aged.activation_evaluated_us,
                        "queue_ahead_at_activation_c1": _s(
                            order.queue_ahead_at_activation
                        ),
                        "queue_ahead_at_activation_c2": _s(
                            aged.queue_ahead_at_activation
                        ),
                        "queue_ahead_at_c1_fill_for_c2": _s(
                            self._queue_ahead_for_order(aged.order_id) or ZERO
                        ),
                        "c2_queue_ahead_at_shadow_activation": None,
                        "preaging_queue_advantage_usdc": None,
                        "actual_fill_us": None,
                        "benefit_us": None,
                        "status": "OPEN",
                        "shadow": {
                            "side": aged.side,
                            "price": _s(aged.price),
                            "quantity": _s(aged.quantity),
                            "submitted_us": now,
                            "active_us": now + self.latency_us,
                            "activation_us": None,
                            "activation_native_upper_us": None,
                            "public_remaining": "0",
                            "own_remaining": "0",
                            "filled": "0",
                            "status": "PENDING",
                            "fill_us": None,
                        },
                    }
                )
        order.status = "FILLED"
        self._remove_from_group(order)
        for case in self._preaging_cases:
            if case["c2_order_id"] == order.order_id:
                case["actual_fill_us"] = now
                self._close_preaging_case(case)
        if order.role == "ENTRY":
            lot = next((item for item in self.lots if item.lot_id in order.lot_ids), None)
            if lot is None or lot.quantity != order.quantity:
                raise ValueError("M024_ENTRY_FILL_LOT_MISMATCH")
            if order.side == "BUY":
                lot.stage = "HOLDING"
            else:
                lot.stage = "SOLD"
            self._submit_return(order, now, lot)
        else:
            lot = next((item for item in self.lots if item.lot_id in order.lot_ids), None)
            if lot is None:
                raise ValueError("M024_RETURN_COMPLETION_LOT_MISSING")
            profit = order.quantity * (order.price - lot.basis)
            if order.direction == "SELL_FIRST":
                profit = order.quantity * (lot.basis - order.price)
                self.reserved_usdt -= order.reserved_quote
                order.reserved_quote = ZERO
                if lot.closed_quantity > ZERO:
                    lot.asset_basis = lot.restored_cost / lot.closed_quantity
                lot.stage = "RESTORED"
            else:
                lot.stage = "CLOSED"
            if profit <= ZERO:
                self._record("NON_POSITIVE_CYCLE_BLOCKED", now, order_id=order.order_id)
                return
            self.realized_pnl += profit
            self.growth_pool += profit
            self.growth_earned += profit
            self._cycles += 1
            self._column_cycle_counts[order.column] = (
                self._column_cycle_counts.get(order.column, 0) + 1
            )
            if order.direction == "BUY_FIRST":
                self._buy_first_cycles += 1
            else:
                self._sell_first_cycles += 1
            wait = now - (order.queue_wait_start_us or now)
            self._column_waits.setdefault(order.column, []).append(wait)
            self._record(
                "CYCLE",
                now,
                order_id=order.order_id,
                direction=order.direction,
                column=order.column,
                profit=_s(profit),
                queue_wait_us=wait,
                lot_id=order.lot_ids[0] if order.lot_ids else None,
                source_order_id=order.source_order_id,
            )
            self._recycle_after_cycle(order, now)
            self._try_profit_funded_growth(now)

    def _recycle_after_cycle(self, order: QueueOrder, now: int) -> None:
        source = next(
            (item for item in self.orders if item.order_id == order.source_order_id),
            None,
        )
        if source is None or self.open_order_count >= self.max_open_orders:
            return
        try:
            if source.direction == "BUY_FIRST":
                prices = self._rolling_prices("BUY") or [source.price]
                price = prices[min(max(source.level, 1), len(prices)) - 1]
                recycled = self.submit_order(
                    "BUY",
                    price,
                    time_us=now,
                    role="ENTRY",
                    column=source.column,
                    level=source.level,
                    direction="BUY_FIRST",
                    cell_id=source.cell_id,
                )
            else:
                lot = next(
                    (item for item in self.lots if item.lot_id in order.lot_ids), None
                )
                prices = self._rolling_prices("SELL") or [source.price]
                price = prices[min(max(source.level, 1), len(prices)) - 1]
                if lot is not None:
                    price = max(
                        price,
                        _ceil_tick(lot.asset_basis + M021_TICK_SIZE),
                    )
                recycled = self.submit_order(
                    "SELL",
                    price,
                    time_us=now,
                    role="ENTRY",
                    column=source.column,
                    level=source.level,
                    direction="SELL_FIRST",
                    cell_id=source.cell_id,
                    asset_basis=lot.asset_basis if lot is not None else order.price,
                )
                if lot is not None:
                    lot.stage = "RECYCLED"
            self._record(
                "PRINCIPAL_RECYCLED",
                now,
                order_id=recycled.order_id,
                source_order_id=order.order_id,
            )
        except ValueError as exc:
            self._record("PRINCIPAL_RECYCLE_DEFERRED", now, reason=str(exc))

    def _try_profit_funded_growth(self, now: int) -> None:
        """Fund one frozen level/side/depth candidate from realized USDT only."""
        if self.open_order_count >= self.max_open_orders:
            return
        for column in range(2, 9):
            for level in range(1, INITIAL_LEVELS + 1):
                for side in ("BUY", "SELL"):
                    if any(
                        order.role == "ENTRY"
                        and order.side == side
                        and order.level == level
                        and order.column == column
                        for order in self.orders
                    ):
                        continue
                    if side == "SELL":
                        self._record(
                            "GROWTH_CELL_BLOCKED_ASSET",
                            now,
                            side=side,
                            level=level,
                            column=column,
                            reason="REALIZED_GROWTH_POOL_IS_USDT_NOT_USDC",
                        )
                        return
                    prices = self._rolling_prices(side)
                    if not prices:
                        return
                    price = prices[level - 1]
                    if self.growth_pool < price or self.cash < price:
                        return
                    self.fund_growth_cell(
                        side,
                        price,
                        time_us=now,
                        level=level,
                        column=column,
                    )
                    return

    def _fill_order(self, order: QueueOrder, quantity: D, now: int, trade_id: str) -> D:
        amount = min(quantity, order.remaining)
        if amount <= ZERO:
            return ZERO
        lot = (
            self._entry_lot_for_fill(order, amount, now)
            if order.role == "ENTRY"
            else next((item for item in self.lots if item.lot_id in order.lot_ids), None)
        )
        if lot is None:
            raise ValueError("M024_RETURN_FILL_LOT_MISSING")
        if (
            order.side == "SELL"
            and order.asset_basis > ZERO
            and order.price <= lot.asset_basis
        ):
            raise ValueError("M024_NEGATIVE_EXIT_FILL_PROHIBITED")
        if order.role == "RETURN":
            lot.closed_quantity += amount
            if order.side == "BUY":
                lot.restored_cost += amount * order.price
                lot.stage = "RESTORING"
            else:
                lot.stage = "CLOSING"
        if order.side == "SELL":
            self.realized_disposal_pnl += amount * (order.price - lot.asset_basis)
        if order.side == "BUY":
            self.reserved_usdt -= amount * order.price
            order.reserved_quote -= amount * order.price
            if order.role == "ENTRY":
                self.inventory_qty += amount
            elif order.direction == "SELL_FIRST":
                self.free_usdc += amount
        else:
            if order.role == "ENTRY":
                self.reserved_usdc -= amount
            else:
                self.reserved_usdc -= amount
            order.reserved_base -= amount
            self.cash += amount * order.price
        order.filled += amount
        self._fill_count += 1
        self._record(
            "FILL",
            now,
            order_id=order.order_id,
            side=order.side,
            price=_s(order.price),
            quantity=_s(amount),
            source_id=trade_id,
            column=order.column,
        )
        if order.remaining == ZERO:
            self._complete_order(order, now)
        return amount

    def _eligible_order(self, order: QueueOrder, native_us: int) -> bool:
        return (
            order.activation_evaluated_us is not None
            and native_us
            > max(
                order.active_us,
                order.activation_evaluated_us,
                order.activation_native_upper_us,
            )
        )

    def _eligible_groups(
        self, price: D, buyer_maker: bool, native_us: int
    ) -> list[PriceQueueGroup]:
        side = "BUY" if buyer_maker else "SELL"
        groups = [
            group
            for group in self.groups.values()
            if group.side == side
            and any(
                order.status in {"ACTIVE", "CANCEL_PENDING"}
                and order.remaining > ZERO
                and self._eligible_order(order, native_us)
                for order in self.orders
                if order.order_id in group.own_order_ids
            )
            and (
                (side == "BUY" and price <= group.price)
                or (side == "SELL" and price >= group.price)
            )
        ]
        return sorted(
            groups,
            key=lambda group: (
                (-group.price, str(group.price))
                if side == "BUY"
                else (group.price, str(group.price))
            ),
        )

    def _consume_group(
        self,
        group: PriceQueueGroup,
        quantity: D,
        now: int,
        native_us: int,
        trade_id: str,
        exact: bool,
    ) -> D:
        remaining = quantity
        consumed = ZERO
        for segment in group.segments:
            if native_us <= max(segment.activation_us, segment.native_book_upper_us):
                continue
            if exact:
                ahead = min(segment.public_remaining, remaining)
                segment.public_remaining -= ahead
                group.public_remaining -= ahead
                remaining -= ahead
                consumed += ahead
                if ahead > ZERO:
                    self._record(
                        "PUBLIC_QUEUE_CONSUMED",
                        now,
                        side=group.side,
                        price=_s(group.price),
                        quantity=_s(ahead),
                        cohort_activation_us=segment.activation_us,
                        source_id=trade_id,
                    )
                if remaining <= ZERO:
                    return consumed
            order_ids = sorted(
                segment.order_ids,
                key=lambda order_id: (
                    next(
                        item.activation_evaluated_us
                        for item in self.orders
                        if item.order_id == order_id
                    )
                    or 0,
                    next(item.submitted_us for item in self.orders if item.order_id == order_id),
                    order_id,
                ),
            )
            for order_id in order_ids:
                order = next(item for item in self.orders if item.order_id == order_id)
                if (
                    order.status not in {"ACTIVE", "CANCEL_PENDING"}
                    or order.remaining <= ZERO
                    or not self._eligible_order(order, native_us)
                ):
                    continue
                amount = self._fill_order(order, remaining, now, trade_id)
                consumed += amount
                remaining -= amount
                if remaining <= ZERO:
                    return consumed
        return consumed

    def receive_book(self, book: Any, *, capture_time_us: int | None = None) -> None:
        native = int(
            book.get("exchange_time_us", book.get("time_us", self.start_us))
            if isinstance(book, dict)
            else getattr(book, "exchange_time_us", getattr(book, "time_us", self.start_us))
        )
        logical = int(
            capture_time_us
            if capture_time_us is not None
            else (
                book.get("capture_time_us", native)
                if isinstance(book, dict)
                else getattr(book, "capture_time_us", native)
            )
        )
        self._check_time(logical)
        self._observe(logical)
        self._last_book = {
            "bids": tuple(
                (_dec(row[0]), _dec(row[1]))
                for row in (book.get("bids", ()) if isinstance(book, dict) else book.bids)
            ),
            "asks": tuple(
                (_dec(row[0]), _dec(row[1]))
                for row in (book.get("asks", ()) if isinstance(book, dict) else book.asks)
            ),
            "known_bid_floor": _dec(
                book.get("known_bid_floor") if isinstance(book, dict) else book.known_bid_floor
            ),
            "known_ask_ceiling": _dec(
                book.get("known_ask_ceiling") if isinstance(book, dict) else book.known_ask_ceiling
            ),
            "exchange_upper_us": (
                book.get("exchange_upper_us")
                if isinstance(book, dict)
                else getattr(book, "exchange_upper_us", None)
            ),
        }
        if not self._last_book["bids"] or not self._last_book["asks"]:
            raise ValueError("INCOMPLETE_BOOK")
        self._advance(logical)
        if not self._initialized:
            self.initialize_triangle(logical)
        self.validate_invariants()

    def initialize_triangle(self, time_us: int) -> None:
        if self._initialized:
            return
        if self._last_book is None:
            raise ValueError("M024_BOOK_REQUIRED_FOR_INITIALIZATION")
        bid = self._last_book["bids"][0][0]
        ask = self._last_book["asks"][0][0]
        buy_prices = [
            _floor_tick(bid - D(index) * M021_TICK_SIZE) for index in range(INITIAL_LEVELS)
        ]
        sell_prices = [
            _ceil_tick(ask + D(index) * M021_TICK_SIZE) for index in range(INITIAL_LEVELS)
        ]
        computed_usdt = sum(
            (
                price
                for price in buy_prices
                for _ in range(2 if buy_prices.index(price) < 25 else 1)
            ),
            ZERO,
        )
        self.initial_usdt = computed_usdt
        self.initial_usdc = D(75)
        self.initial_mark = self.initial_usdt + self.initial_usdc * bid
        self.cash = self.initial_usdt
        self.free_usdc = ZERO
        self._initialized = True
        for index, price in enumerate(buy_prices, 1):
            count = 2 if index <= 25 else 1
            for column in range(1, count + 1):
                self.submit_order(
                    "BUY",
                    price,
                    time_us=time_us,
                    column=column,
                    level=index,
                    direction="BUY_FIRST",
                    cell_id=f"BUY:L{index:02d}:C{column}",
                )
        self.free_usdc = self.initial_usdc
        for index, price in enumerate(sell_prices, 1):
            count = 2 if index <= 25 else 1
            for column in range(1, count + 1):
                self.submit_order(
                    "SELL",
                    price,
                    time_us=time_us,
                    column=column,
                    level=index,
                    direction="SELL_FIRST",
                    cell_id=f"SELL:L{index:02d}:C{column}",
                    asset_basis=bid,
                )
        self._record(
            "TRIANGLE_INITIALIZED",
            time_us,
            initial_usdt=_s(self.initial_usdt),
            initial_usdc=_s(self.initial_usdc),
        )

    def receive_trade(self, trade: Any, *, capture_time_us: int | None = None) -> D:
        native = int(trade.get("time_us") if isinstance(trade, dict) else trade.time_us)
        logical = int(
            capture_time_us
            if capture_time_us is not None
            else (
                trade.get("capture_time_us", native)
                if isinstance(trade, dict)
                else getattr(trade, "capture_time_us", native)
            )
        )
        self._check_time(logical)
        self._observe(logical)
        trade_id = str(trade.get("trade_id") if isinstance(trade, dict) else trade.trade_id)
        if trade_id in self._processed_trades:
            return ZERO
        self._processed_trades.add(trade_id)
        self._advance(logical)
        price = _dec(trade.get("price") if isinstance(trade, dict) else trade.price)
        quantity = _dec(trade.get("quantity") if isinstance(trade, dict) else trade.quantity)
        buyer_maker = bool(
            trade.get("buyer_maker") if isinstance(trade, dict) else trade.buyer_maker
        )
        current_book_upper = int((self._last_book or {}).get("exchange_upper_us") or self.start_us)
        if current_book_upper > native:
            self._record(
                "TRADE",
                logical,
                trade_id=trade_id,
                native_time_us=native,
                buyer_maker=buyer_maker,
                price=_s(price),
                original_quantity=_s(quantity),
                consumed_quantity="0",
                blocked_future_book=True,
                current_book_upper_us=current_book_upper,
            )
            self.validate_invariants()
            return ZERO
        consumed = ZERO
        for group in self._eligible_groups(price, buyer_maker, native):
            left = quantity - consumed
            if left <= ZERO:
                break
            consumed += self._consume_group(
                group, left, logical, native, trade_id, price == group.price
            )
        self._feed_shadow_queues(price, quantity, buyer_maker, logical, native, trade_id)
        self._record(
            "TRADE",
            logical,
            trade_id=trade_id,
            native_time_us=native,
            buyer_maker=buyer_maker,
            price=_s(price),
            original_quantity=_s(quantity),
            consumed_quantity=_s(consumed),
        )
        self.validate_invariants()
        return consumed

    def _percentile(self, values: list[int], rank: float) -> int | None:
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, int((len(ordered) * rank + 0.999999999) - 1)))
        return ordered[index]

    def _marked_inventory(self, mark: D) -> tuple[D, D, D]:
        """Reconstruct held USDC quantity, basis and mark-to-market from owned layers."""
        latest_sell_cells: dict[str, QueueOrder] = {}
        for order in self.orders:
            if order.role == "ENTRY" and order.side == "SELL" and order.cell_id is not None:
                previous = latest_sell_cells.get(order.cell_id)
                if previous is None or order.order_id > previous.order_id:
                    latest_sell_cells[order.cell_id] = order
        quantity = ZERO
        cost = ZERO
        for order in latest_sell_cells.values():
            held = order.remaining
            if held > ZERO:
                quantity += held
                cost += held * order.asset_basis
        order_by_id = {order.order_id: order for order in self.orders}
        for lot in self.lots:
            source = order_by_id[lot.entry_order_id]
            if source.side == "BUY":
                held = lot.quantity - lot.closed_quantity
                if held > ZERO:
                    quantity += held
                    cost += held * lot.asset_basis
            elif lot.stage != "RECYCLED" and lot.closed_quantity > ZERO:
                quantity += lot.closed_quantity
                cost += lot.restored_cost
        return quantity, cost, quantity * mark - cost

    def metrics(self) -> dict[str, Any]:
        mark = self._last_book["bids"][0][0] if self._last_book else ZERO
        final_usdt = self.cash + self.reserved_usdt
        final_usdc = self.free_usdc + self.reserved_usdc + self.inventory_qty
        equity = final_usdt + final_usdc * mark
        marked_inventory_qty, inventory_cost, inventory_unrealized = self._marked_inventory(mark)
        waits = {column: values for column, values in self._order_waits.items()}
        col1 = [wait for column, values in waits.items() if column == 1 for wait in values]
        col2 = [wait for column, values in waits.items() if column == 2 for wait in values]
        all_waits = [wait for values in self._order_waits.values() for wait in values]
        benefits = [
            case["benefit_us"]
            for case in self._preaging_cases
            if case.get("benefit_us") is not None
        ]
        queue_advantages = [
            _dec(case["preaging_queue_advantage_usdc"])
            for case in self._preaging_cases
            if case.get("preaging_queue_advantage_usdc") is not None
        ]
        active_free_groups: dict[tuple[str, D], list[QueueOrder]] = {}
        for order in self.active_orders:
            if order.role == "ENTRY" and order.filled == ZERO:
                active_free_groups.setdefault((order.side, order.price), []).append(order)
        active_depths = [len(rows) for rows in active_free_groups.values()]
        columns = sorted({order.column for order in self.orders})
        column_table = []
        for column in columns:
            column_waits = waits.get(column, [])
            column_table.append(
                {
                    "COLUMN": column,
                    "ORDERS": sum(order.column == column for order in self.orders),
                    "FILLS": sum(
                        row.get("column") == column for row in self.audit if row["event"] == "FILL"
                    ),
                    "CYCLES": self._column_cycle_counts.get(column, 0),
                    "MEDIAN_WAIT_US": median(column_waits) if column_waits else None,
                    "P95_WAIT_US": self._percentile(column_waits, 0.95),
                    "CENSORED_OPEN_ORDERS": sum(
                        order.column == column
                        and order.status in {"ACTIVE", "CANCEL_PENDING"}
                        and order.activation_evaluated_us is not None
                        for order in self.orders
                    ),
                }
            )
        return {
            "MODEL": "M024",
            "PERIOD": "3H",
            "TOTAL_CYCLES": self._cycles,
            "CYCLES_PER_HOUR": _s(D(self._cycles) / D("3")),
            "TARGET_10_PER_HOUR_PASS": self._cycles >= 30,
            "BUY_FIRST_CYCLES": self._buy_first_cycles,
            "SELL_FIRST_CYCLES": self._sell_first_cycles,
            "TOTAL_FILLS": self._fill_count,
            "COLUMN_1_CYCLES": self._column_cycle_counts.get(1, 0),
            "COLUMN_2_CYCLES": self._column_cycle_counts.get(2, 0),
            "COLUMN_1_MEDIAN_QUEUE_WAIT": median(col1) if col1 else None,
            "COLUMN_2_MEDIAN_QUEUE_WAIT": median(col2) if col2 else None,
            "COLUMN_1_P95_QUEUE_WAIT": self._percentile(col1, 0.95),
            "COLUMN_2_P95_QUEUE_WAIT": self._percentile(col2, 0.95),
            "ORDER_QUEUE_WAIT_COUNT": len(all_waits),
            "ORDER_QUEUE_WAIT_MEDIAN_US": median(all_waits) if all_waits else None,
            "ORDER_QUEUE_WAIT_P95_US": self._percentile(all_waits, 0.95),
            "QUEUE_AHEAD_AT_ACTIVATION": {
                str(order.order_id): _s(order.queue_ahead_at_activation)
                for order in self.orders
                if order.activation_evaluated_us is not None
            },
            "QUEUE_AHEAD_AT_ACTIVATION_C1": {
                str(case["c1_order_id"]): case["queue_ahead_at_activation_c1"]
                for case in self._preaging_cases
            },
            "QUEUE_AHEAD_AT_ACTIVATION_C2": {
                str(case["c2_order_id"]): case["queue_ahead_at_activation_c2"]
                for case in self._preaging_cases
            },
            "QUEUE_AHEAD_AT_TIME_C1_FILLED_FOR_C2": {
                str(case["c2_order_id"]): case["queue_ahead_at_c1_fill_for_c2"]
                for case in self._preaging_cases
            },
            "PRE_AGING_CASES": len(self._preaging_cases),
            "PRE_AGING_BENEFIT_OBSERVED": any(value > 0 for value in benefits),
            "PRE_AGING_BENEFIT_MEDIAN_SECONDS": median(benefits) / 1_000_000 if benefits else None,
            "PRE_AGING_BENEFIT_MEAN_SECONDS": (
                sum(benefits) / len(benefits) / 1_000_000 if benefits else None
            ),
            "PRE_AGING_BENEFIT_P95_SECONDS": (
                self._percentile(benefits, 0.95) / 1_000_000 if benefits else None
            ),
            "PRE_AGING_QUEUE_ADVANTAGE_MEAN_USDC": (
                _s(sum(queue_advantages, ZERO) / D(len(queue_advantages)))
                if queue_advantages
                else None
            ),
            "PRE_AGING_QUEUE_ADVANTAGE_MEDIAN_USDC": (
                _s(median(queue_advantages)) if queue_advantages else None
            ),
            "PRE_AGING_BENEFIT_UNAVAILABLE_REASON": None
            if benefits
            else "CENSORED_OR_NO_SHADOW_FILL",
            "PRE_AGING_CASE_ROWS": list(self._preaging_cases),
            "INITIAL_OPEN_ORDERS": 150 if self._initialized else 0,
            "MAX_OPEN_ORDERS": self._max_open_orders,
            "PRODUCTIVE_PRICE_LEVELS": len(
                {(order.side, order.price) for order in self.orders if order.filled > ZERO}
            ),
            "PRODUCTIVE_COLUMNS": len(
                {order.column for order in self.orders if order.filled > ZERO}
            ),
            "GROWTH_POOL_FINAL": _s(self.growth_pool),
            "LOCKED_SELL_PROCEEDS_USDT": _s(self._locked_sell_proceeds()),
            "PARTIAL_SUBSTEP_LOCKED_LOTS": sum(
                lot.stage
                in {"SUBSTEP_INVENTORY_LOCKED", "SUBSTEP_RETURN_DEBT_LOCKED"}
                for lot in self.lots
            ),
            "NEW_QUEUE_CELLS_FUNDED_BY_PROFIT": self._growth_cells,
            "COLUMN_2_COVERAGE_INITIAL": _s(D(25) / D(50)),
            "COLUMN_2_COVERAGE_FINAL": _s(
                D(sum(1 for rows in active_free_groups.values() if len(rows) >= 2))
                / D(len(active_free_groups))
                if active_free_groups
                else ZERO
            ),
            "MAX_QUEUE_DEPTH_REACHED": self._max_queue_depth,
            "DEPTH_1_LEVELS": sum(depth == 1 for depth in active_depths),
            "DEPTH_2_LEVELS": sum(depth == 2 for depth in active_depths),
            "DEPTH_3_PLUS_LEVELS": sum(depth >= 3 for depth in active_depths),
            "RECTANGLE_DEPTH_2_REACHED": all(
                len(rows) >= 2 for rows in active_free_groups.values()
            )
            if active_free_groups
            else False,
            "RECTANGLE_TARGET_DEPTH_8_REACHED": all(
                len(rows) >= 8 for rows in active_free_groups.values()
            )
            if active_free_groups
            else False,
            "INITIAL_USDT": _s(self.initial_usdt),
            "INITIAL_USDC": _s(self.initial_usdc),
            "INITIAL_MARKED_EQUITY": _s(self.initial_mark),
            "FINAL_USDT": _s(final_usdt),
            "FINAL_USDC": _s(final_usdc),
            "FINAL_MARKED_EQUITY": _s(equity),
            "REALIZED_PNL": _s(self.realized_pnl),
            "REALIZED_DISPOSAL_PNL": _s(self.realized_disposal_pnl),
            "COMPLETED_CYCLE_PNL": _s(self.realized_pnl),
            "GROWTH_ELIGIBLE_PNL_CUMULATIVE": _s(self.growth_earned),
            "UNREALIZED_PNL": _s(inventory_unrealized),
            "UNREALIZED_PNL_METHOD": "OWNED_USDC_LAYERS_MARKED_TO_FINAL_BID",
            "INVENTORY_MARKED_QUANTITY": _s(marked_inventory_qty),
            "INVENTORY_COST_BASIS": _s(inventory_cost),
            "TOTAL_EQUITY_CHANGE": _s(equity - self.initial_mark),
            "PNL_IDENTITY_RESIDUAL": _s(
                equity
                - self.initial_mark
                - self.realized_disposal_pnl
                - inventory_unrealized
            ),
            "CYCLES_PER_100_USDT_EQ": _s(
                D(self._cycles) / D("3") * D("100") / self.initial_mark
                if self.initial_mark > ZERO
                else ZERO
            ),
            "CAPITAL_PER_COMPLETE_CYCLE": (
                _s(self.initial_mark / D(self._cycles)) if self._cycles else None
            ),
            "CAPITAL_UTILIZATION": _s(
                self._active_capital_time_us
                / (self.initial_mark * D(self.end_us - self.start_us))
                if self.initial_mark > ZERO
                else ZERO
            ),
            "ACTIVE_CAPITAL_TIME_WEIGHTED": _s(
                self._active_capital_time_us / D(self.end_us - self.start_us)
            ),
            "ACTIVE_CAPITAL_TIME_WEIGHTED_US": self._active_order_time_us,
            "OPEN_ORDER_COUNT": self.open_order_count,
            "GROWTH_CELLS_FUNDED": self._growth_cells,
            "ROLLING_CANCELS": self._rolling_cancels,
            "ORDERS_REPOSITIONED": self._rolling_replacements,
            "COLUMN_TABLE": column_table,
            "AUDIT": self.audit,
            "MAIN_LIMITER": "UNDETERMINED_PENDING_POST_RUN_AUTOPSY",
        }

    def finish(self, *, time_us: int) -> dict[str, Any]:
        if time_us != self.end_us:
            self._check_time(time_us)
        self._observe(time_us)
        for case in self._preaging_cases:
            if case.get("status") == "OPEN":
                case["status"] = "CENSORED_AT_CUTOFF"
        return self.metrics()

    def validate_invariants(self) -> None:
        if self.open_order_count > self.max_open_orders:
            raise ValueError("M024_OPEN_ORDER_CAP_EXCEEDED")
        if (
            self.reserved_usdt < ZERO
            or self.reserved_usdc < ZERO
            or self.cash < ZERO
            or self.free_usdc < ZERO
        ):
            raise ValueError("M024_NEGATIVE_CAPITAL")
        quote_total = sum((order.reserved_quote for order in self.orders), ZERO)
        base_total = sum((order.reserved_base for order in self.orders), ZERO)
        if quote_total != self.reserved_usdt or base_total != self.reserved_usdc:
            raise ValueError("M024_RESERVATION_LEDGER_DRIFT")
        for group in self.groups.values():
            ids = group.own_order_ids
            if len(ids) != len(set(ids)):
                raise ValueError("M024_DUPLICATE_QUEUE_MEMBERSHIP")
            rows = [order for order in self.orders if order.order_id in ids]
            ordered = sorted(
                rows,
                key=lambda order: (
                    order.activation_evaluated_us or 0,
                    order.submitted_us,
                    order.order_id,
                ),
            )
            if [row.order_id for row in rows] != [row.order_id for row in ordered]:
                raise ValueError("M024_OWN_FIFO_DRIFT")
        if self.inventory_qty < ZERO:
            raise ValueError("M024_NEGATIVE_INVENTORY")
        locked_sell_proceeds = self._locked_sell_proceeds()
        if self.growth_pool > self.cash - locked_sell_proceeds:
            raise ValueError("M024_GROWTH_OWNERSHIP_DRIFT")
        if self._initialized and self._last_book is not None:
            mark = self._last_book["bids"][0][0]
            marked_qty, _cost, unrealized = self._marked_inventory(mark)
            physical_qty = self.free_usdc + self.reserved_usdc + self.inventory_qty
            if marked_qty != physical_qty:
                raise ValueError("M024_INVENTORY_LAYER_QUANTITY_DRIFT")
            equity = self.cash + self.reserved_usdt + physical_qty * mark
            if (
                equity
                - self.initial_mark
                - self.realized_disposal_pnl
                - unrealized
                != ZERO
            ):
                raise ValueError("M024_PNL_IDENTITY_DRIFT")

    def _state(self) -> dict[str, Any]:
        def order_row(order: QueueOrder) -> dict[str, Any]:
            return {
                **order.__dict__,
                "price": _s(order.price),
                "quantity": _s(order.quantity),
                "filled": _s(order.filled),
                "reserved_quote": _s(order.reserved_quote),
                "reserved_base": _s(order.reserved_base),
                "asset_basis": _s(order.asset_basis),
            }

        return {
            "cash": _s(self.cash),
            "reserved_usdt": _s(self.reserved_usdt),
            "free_usdc": _s(self.free_usdc),
            "reserved_usdc": _s(self.reserved_usdc),
            "initial_usdt": _s(self.initial_usdt),
            "initial_usdc": _s(self.initial_usdc),
            "initial_mark": _s(self.initial_mark),
            "growth_pool": _s(self.growth_pool),
            "realized_pnl": _s(self.realized_pnl),
            "realized_disposal_pnl": _s(self.realized_disposal_pnl),
            "growth_earned": _s(self.growth_earned),
            "inventory_qty": _s(self.inventory_qty),
            "orders": [order_row(order) for order in self.orders],
            "lots": [
                {
                    **lot.__dict__,
                    "quantity": _s(lot.quantity),
                    "basis": _s(lot.basis),
                    "asset_basis": _s(lot.asset_basis),
                    "closed_quantity": _s(lot.closed_quantity),
                    "restored_cost": _s(lot.restored_cost),
                }
                for lot in self.lots
            ],
            "groups": [
                {
                    "side": group.side,
                    "price": _s(group.price),
                    "public_queue": _s(group.public_queue),
                    "public_remaining": _s(group.public_remaining),
                    "segments": [
                        {**segment.__dict__, "public_barrier": _s(segment.public_barrier)}
                        for segment in group.segments
                    ],
                }
                for group in self.groups.values()
            ],
            "audit": self.audit,
            "processed_trades": sorted(self._processed_trades),
            "next_order_id": self._next_order_id,
            "next_lot_id": self._next_lot_id,
            "last_logical_us": self._last_logical_us,
            "last_observation_us": self._last_observation_us,
            "active_order_time_us": self._active_order_time_us,
            "active_capital_time_us": _s(self._active_capital_time_us),
            "max_open_orders": self._max_open_orders,
            "fill_count": self._fill_count,
            "cycles": self._cycles,
            "buy_first_cycles": self._buy_first_cycles,
            "sell_first_cycles": self._sell_first_cycles,
            "column_cycle_counts": self._column_cycle_counts,
            "column_waits": self._column_waits,
            "order_waits": self._order_waits,
            "growth_cells": self._growth_cells,
            "max_queue_depth": self._max_queue_depth,
            "rolling_pending": {
                str(order_id): {
                    **row,
                    "asset_basis": _s(row["asset_basis"]),
                }
                for order_id, row in self._rolling_pending.items()
            },
            "rolling_ready": [
                {**row, "asset_basis": _s(row["asset_basis"])}
                for row in self._rolling_ready
            ],
            "rolling_cancels": self._rolling_cancels,
            "rolling_replacements": self._rolling_replacements,
            "initialized": self._initialized,
            "preaging_cases": self._preaging_cases,
            "deferred_returns": self._deferred_returns,
            "config": {
                "start_us": self.start_us,
                "end_us": self.end_us,
                "latency_us": self.latency_us,
                "cancel_latency_us": self.cancel_latency_us,
                "max_open_orders": self.max_open_orders,
            },
            "last_book": (
                None
                if self._last_book is None
                else {
                    "bids": [
                        [_s(price), _s(quantity)] for price, quantity in self._last_book["bids"]
                    ],
                    "asks": [
                        [_s(price), _s(quantity)] for price, quantity in self._last_book["asks"]
                    ],
                    "known_bid_floor": _s(self._last_book["known_bid_floor"]),
                    "known_ask_ceiling": _s(self._last_book["known_ask_ceiling"]),
                    "exchange_upper_us": self._last_book.get("exchange_upper_us"),
                }
            ),
        }

    def checkpoint(self) -> dict[str, Any]:
        state = self._state()
        return {
            "schema": "M024_TRIANGULAR_PRE_AGED_QUEUE_V1",
            "state": state,
            "sha256": canonical_hash(state),
        }

    def restore(self, checkpoint: dict[str, Any]) -> None:
        if checkpoint.get("schema") != "M024_TRIANGULAR_PRE_AGED_QUEUE_V1":
            raise ValueError("INVALID_M024_CHECKPOINT")
        state = checkpoint.get("state")
        if not isinstance(state, dict) or checkpoint.get("sha256") != canonical_hash(state):
            raise ValueError("M024_CHECKPOINT_HASH_MISMATCH")
        config = state.get("config", {})
        if (
            int(config.get("start_us", self.start_us)) != self.start_us
            or int(config.get("end_us", self.end_us)) != self.end_us
            or int(config.get("max_open_orders", self.max_open_orders)) != self.max_open_orders
        ):
            raise ValueError("M024_CHECKPOINT_POLICY_MISMATCH")
        for key in (
            "cash",
            "reserved_usdt",
            "free_usdc",
            "reserved_usdc",
            "initial_usdt",
            "initial_usdc",
            "initial_mark",
            "growth_pool",
            "realized_pnl",
            "realized_disposal_pnl",
            "growth_earned",
            "inventory_qty",
        ):
            setattr(self, key, _dec(state[key]))
        self.latency_us = int(config.get("latency_us", self.latency_us))
        self.cancel_latency_us = int(config.get("cancel_latency_us", self.cancel_latency_us))
        self.max_open_orders = int(config.get("max_open_orders", self.max_open_orders))
        self.orders = []
        for row in state["orders"]:
            row = dict(row)
            for key in (
                "price",
                "quantity",
                "filled",
                "reserved_quote",
                "reserved_base",
                "asset_basis",
            ):
                row[key] = _dec(row[key])
            self.orders.append(QueueOrder(**row))
        self.lots = []
        for row in state["lots"]:
            row = dict(row)
            for key in (
                "quantity",
                "basis",
                "asset_basis",
                "closed_quantity",
                "restored_cost",
            ):
                row[key] = _dec(row[key])
            self.lots.append(Lot(**row))
        self.groups = {}
        for row in state["groups"]:
            group = PriceQueueGroup(
                row["side"],
                _dec(row["price"]),
                _dec(row["public_queue"]),
                _dec(row["public_remaining"]),
            )
            group.segments = [
                QueueSegment(
                    int(item["activation_us"]),
                    _dec(item["public_barrier"]),
                    list(item["order_ids"]),
                    _dec(item.get("public_remaining", item["public_barrier"])),
                    int(item.get("native_book_upper_us", 0)),
                )
                for item in row["segments"]
            ]
            self.groups[(group.side, group.price)] = group
        self.audit = list(state["audit"])
        self._processed_trades = set(state["processed_trades"])
        self._next_order_id = int(state["next_order_id"])
        self._next_lot_id = int(state["next_lot_id"])
        self._last_logical_us = int(state["last_logical_us"])
        self._last_observation_us = int(state["last_observation_us"])
        self._active_order_time_us = int(state["active_order_time_us"])
        self._active_capital_time_us = _dec(state.get("active_capital_time_us", "0"))
        self._max_open_orders = int(state["max_open_orders"])
        self._fill_count = int(state["fill_count"])
        self._cycles = int(state["cycles"])
        self._buy_first_cycles = int(state["buy_first_cycles"])
        self._sell_first_cycles = int(state["sell_first_cycles"])
        self._column_cycle_counts = {
            int(k): int(v) for k, v in state["column_cycle_counts"].items()
        }
        self._column_waits = {int(k): list(v) for k, v in state["column_waits"].items()}
        self._order_waits = {int(k): list(v) for k, v in state.get("order_waits", {}).items()}
        self._growth_cells = int(state["growth_cells"])
        self._max_queue_depth = int(state.get("max_queue_depth", 0))
        self._rolling_pending = {
            int(order_id): {**row, "asset_basis": _dec(row.get("asset_basis", "0"))}
            for order_id, row in state.get("rolling_pending", {}).items()
        }
        self._rolling_ready = [
            {**row, "asset_basis": _dec(row.get("asset_basis", "0"))}
            for row in state.get("rolling_ready", [])
        ]
        self._rolling_cancels = int(state.get("rolling_cancels", 0))
        self._rolling_replacements = int(state.get("rolling_replacements", 0))
        self._initialized = bool(state["initialized"])
        self._preaging_cases = list(state.get("preaging_cases", []))
        self._deferred_returns = {
            int(source_id): int(lot_id)
            for source_id, lot_id in state.get("deferred_returns", {}).items()
        }
        raw_book = state.get("last_book")
        self._last_book = (
            None
            if raw_book is None
            else {
                "bids": tuple(
                    (_dec(price), _dec(quantity)) for price, quantity in raw_book["bids"]
                ),
                "asks": tuple(
                    (_dec(price), _dec(quantity)) for price, quantity in raw_book["asks"]
                ),
                "known_bid_floor": _dec(raw_book["known_bid_floor"]),
                "known_ask_ceiling": _dec(raw_book["known_ask_ceiling"]),
                "exchange_upper_us": raw_book.get("exchange_upper_us"),
            }
        )
        self.validate_invariants()

    @classmethod
    def from_checkpoint(
        cls, checkpoint: dict[str, Any], *, start_us: int, end_us: int
    ) -> TriangularPreAgedQueueProbe:
        value = cls(start_us=start_us, end_us=end_us)
        value.restore(checkpoint)
        return value


M024TriangularPreAgedQueue = TriangularPreAgedQueueProbe

__all__ = [
    "Lot",
    "M024TriangularPreAgedQueue",
    "PriceQueueGroup",
    "QueueOrder",
    "QueueSegment",
    "TriangularPreAgedQueueProbe",
]
