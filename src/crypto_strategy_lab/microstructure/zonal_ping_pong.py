"""Pure M020 fixed-zone ping-pong throughput kernel.

The one-USDT order size is deliberately a normalized, non-executable
structural diagnostic.  This module has no market-data reader and no network
or replay launcher.  A caller supplies causal books and trades.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any

from crypto_strategy_lab.domain import canonical_hash

D = Decimal
ZERO = D("0")
ONE = D("1")
NORMALIZED_CAPITAL = D("100")
NORMALIZED_ORDER_NOTIONAL = D("1")
HISTORICAL_STEP = D("1")
VIRTUAL_STEP = HISTORICAL_STEP
MAX_BANDS = 40
MIN_ACTIVE_BUYS = 4
MIN_ACTIVE_SELLS = 4


def _ceil_step(value: D, step: D = VIRTUAL_STEP) -> D:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _floor_step(value: D, step: D = VIRTUAL_STEP) -> D:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _dec(value: Any) -> D:
    return value if isinstance(value, D) else D(str(value))


def _s(value: D) -> str:
    return str(value)


@dataclass(frozen=True)
class ZonalBand:
    """Immutable physical address and its per-side capacity."""

    band_id: str
    price_low: D
    price_high: D
    buy_price: D
    sell_price: D
    buy_capacity: D
    sell_capacity: D

    def __post_init__(self) -> None:
        if not self.band_id or self.price_low <= ZERO or self.price_high < self.price_low:
            raise ValueError("INVALID_IMMUTABLE_BAND")
        if not self.price_low <= self.buy_price <= self.price_high:
            raise ValueError("BUY_PRICE_OUTSIDE_BAND")
        if not self.price_low <= self.sell_price <= self.price_high:
            raise ValueError("SELL_PRICE_OUTSIDE_BAND")
        if min(self.buy_capacity, self.sell_capacity) < ZERO:
            raise ValueError("NEGATIVE_BAND_CAPACITY")


@dataclass
class ZonalLot:
    lot_id: str
    band_id: str
    quantity: D
    remaining: D
    unit_basis: D
    remaining_cost: D
    entry_us: int
    origin: str
    reserved: D = ZERO
    sold_proceeds: D = ZERO
    sold_quantity: D = ZERO
    source_order_id: int | None = None
    realized_profit: D = ZERO


@dataclass
class ZonalOrder:
    order_id: int
    band_id: str
    side: str
    price: D
    quantity: D
    remaining: D
    submitted_us: int
    active_us: int
    queue: D = ZERO
    reserved_quote: D = ZERO
    reserved_lots: list[tuple[str, D]] = field(default_factory=list)
    status: str = "PENDING"
    filled: D = ZERO
    cancel_us: int | None = None
    submitted_native_us: int = -1
    role: str = "ENTRY"
    activation_evaluated_us: int | None = None
    cycle_recorded: bool = False
    reentry_sale_proceeds: D = ZERO


class ZonalPingPong:
    """Deterministic fixed-band M020 kernel with a five-hour hard cutoff."""

    normalized_label = (
        "THIS 1-USDT ORDER RESULT IS A NORMALIZED STRUCTURAL THROUGHPUT TEST. "
        "IT IS BELOW BINANCE MINIMUM NOTIONAL AND IS NOT A LIVE-EXECUTABLE RESULT."
    )

    def __init__(
        self,
        bands: Iterable[ZonalBand],
        *,
        start_us: int,
        end_us: int,
        latency_us: int = 1,
        cancel_latency_us: int = 1,
        initial_capital: D = NORMALIZED_CAPITAL,
    ) -> None:
        materialized = tuple(bands)
        if not materialized or len(materialized) > MAX_BANDS:
            raise ValueError("INVALID_BAND_COUNT")
        ids = [band.band_id for band in materialized]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_IMMUTABLE_BAND_ID")
        buy_prices = [band.buy_price for band in materialized]
        sell_prices = [band.sell_price for band in materialized]
        if len(buy_prices) != len(set(buy_prices)):
            raise ValueError("DUPLICATE_IMMUTABLE_BUY_PRICE")
        if len(sell_prices) != len(set(sell_prices)):
            raise ValueError("DUPLICATE_IMMUTABLE_SELL_PRICE")
        if end_us <= start_us or latency_us <= 0 or cancel_latency_us <= 0:
            raise ValueError("INVALID_FIVE_HOUR_WINDOW")
        self.bands = materialized
        self._bands = {band.band_id: band for band in materialized}
        self.start_us, self.end_us = int(start_us), int(end_us)
        self.latency_us, self.cancel_latency_us = latency_us, cancel_latency_us
        self.initial_capital = _dec(initial_capital)
        self.cash = self.initial_capital
        self.inventory = ZERO
        self.inventory_cost = ZERO
        self.fees = ZERO
        self.realized_profit = ZERO
        self.cycles = 0
        self.positive_cycles = 0
        self.processed_trades: set[str] = set()
        self.orders: list[ZonalOrder] = []
        self.lots: deque[ZonalLot] = deque()
        self.audit: list[dict[str, Any]] = []
        self._next_order_id = 1
        self._next_lot_id = 1
        self._last_logical_us = start_us
        self._last_native_us = start_us
        self._last_native_book_upper_us = start_us
        self._last_book: Any = None
        self._endowed = False
        self._finished = False
        self.endowment_free_quantity = ZERO
        self.endowment_basis = ZERO
        self.endowment_cost = ZERO
        self._endowment_layers: deque[tuple[D, D]] = deque()
        self.endowment_reserved_quantity = ZERO
        self.endowment_initial_quantity = ZERO
        self._known_bid_floor: D | None = None
        self._known_ask_ceiling: D | None = None
        self._band_state = {band.band_id: "READY_FOR_BUY" for band in materialized}
        self._sell_proceeds = {band.band_id: ZERO for band in materialized}
        self._sell_quantity = {band.band_id: ZERO for band in materialized}
        self._sell_source_order: dict[str, int | None] = {
            band.band_id: None for band in materialized
        }
        self._roundtrip_profit = ZERO
        self._cycles_by_band = {band.band_id: 0 for band in materialized}
        self._cycles_by_direction = {"BUY_SELL": 0, "SELL_BUY": 0}
        self._queue_blocked_events = 0
        self._queue_blocked_quantity = ZERO
        self._exact_fill_quantity = ZERO
        self._trade_through_fill_quantity = ZERO
        self._exact_fill_events = 0
        self._trade_through_fill_events = 0
        self._window_shortage_events = 0

    @property
    def active_orders(self) -> list[ZonalOrder]:
        return [
            order
            for order in self.orders
            if order.status in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
        ]

    @property
    def active_buys(self) -> list[ZonalOrder]:
        return [
            order
            for order in self.active_orders
            if order.side == "BUY" and order.status in {"PENDING", "ACTIVE"}
        ]

    @property
    def active_sells(self) -> list[ZonalOrder]:
        return [
            order
            for order in self.active_orders
            if order.side == "SELL" and order.status in {"PENDING", "ACTIVE"}
        ]

    def _check_time(self, time_us: int) -> None:
        if time_us < self.start_us or time_us >= self.end_us:
            raise ValueError("CUTOFF_EXCLUSIVE")
        if time_us < self._last_logical_us:
            raise ValueError("NONCAUSAL_LOGICAL_TIME")
        self._last_logical_us = time_us

    def _record(self, event: str, time_us: int, **fields: Any) -> None:
        self.audit.append({"event": event, "time_us": time_us, **fields})

    def _lot_for_band(self, band_id: str) -> ZonalLot | None:
        return next(
            (lot for lot in self.lots if lot.band_id == band_id and lot.remaining > ZERO), None
        )

    def _lots_for_band(self, band_id: str) -> list[ZonalLot]:
        return [
            lot
            for lot in self.lots
            if lot.band_id == band_id and lot.remaining > ZERO
        ]

    def initialize_endowment(self, first_bid: D, *, time_us: int | None = None) -> None:
        if self._endowed:
            raise ValueError("ENDOWMENT_ALREADY_INITIALIZED")
        time_us = self.start_us if time_us is None else int(time_us)
        self._check_time(time_us)
        first_bid = _dec(first_bid)
        if first_bid <= ZERO:
            raise ValueError("INVALID_ENDOWMENT_BID")
        quantity = _floor_step(D("50") / first_bid)
        self.cash -= quantity * first_bid
        self.inventory += quantity
        self.inventory_cost += quantity * first_bid
        self.endowment_free_quantity = quantity
        self.endowment_basis = first_bid
        self.endowment_cost = quantity * first_bid
        self._endowment_layers.append((quantity, first_bid))
        self.endowment_initial_quantity = quantity
        self._endowed = True
        self._record("ENDOWMENT", time_us, bid=_s(first_bid), quantity=_s(quantity))

    def _desired(self, now: int, best_bid: D, best_ask: D) -> list[tuple[str, str, D, D]]:
        mark = (best_bid + best_ask) / D(2)
        owned_exits: list[tuple[str, str, D, D]] = []
        free_candidates: list[tuple[str, str, D, D]] = []
        for band in self.bands:
            state = self._band_state[band.band_id]
            lots = self._lots_for_band(band.band_id)
            if (
                state == "READY_FOR_BUY"
                and self._sell_proceeds[band.band_id] > ZERO
                and band.buy_capacity > ZERO
                and band.buy_capacity >= self._sell_quantity[band.band_id]
                and band.buy_price * self._sell_quantity[band.band_id]
                < self._sell_proceeds[band.band_id]
            ):
                quantity = self._sell_quantity[band.band_id]
                owned_exits.append(("BUY", band.band_id, band.buy_price, quantity))
            elif (
                state == "READY_FOR_BUY"
                and self._sell_proceeds[band.band_id] == ZERO
                and band.price_low < mark
                and band.buy_capacity > ZERO
            ):
                quantity = min(band.buy_capacity, NORMALIZED_ORDER_NOTIONAL)
                free_candidates.append(
                    (
                        "BUY",
                        band.band_id,
                        band.buy_price,
                        quantity,
                    )
                )
            if state == "USDC_INVENTORY" and lots:
                available = sum((item.remaining for item in lots), ZERO)
                basis = max((item.unit_basis for item in lots), default=ZERO)
                if available > ZERO and band.price_high > basis:
                    owned_exits.append(
                        (
                            "SELL",
                            band.band_id,
                            band.price_high,
                            min(available, band.sell_capacity, NORMALIZED_ORDER_NOTIONAL),
                        )
                    )
            elif (
                state == "READY_FOR_BUY"
                and self._sell_proceeds[band.band_id] == ZERO
                and band.sell_capacity > ZERO
                and band.price_high > mark
            ):
                available = self.endowment_free_quantity
                basis = (
                    self._endowment_layers[0][1]
                    if self._endowment_layers
                    else self.endowment_basis
                )
                if available > ZERO and band.price_high > basis:
                    free_candidates.append(
                        (
                            "SELL",
                            band.band_id,
                            band.price_high,
                            min(available, band.sell_capacity, NORMALIZED_ORDER_NOTIONAL),
                        )
                    )

        owned_exits.sort(key=lambda row: (row[0], row[1]))
        free_candidates.sort(key=lambda row: (abs(row[2] - mark), row[0], row[1]))
        sells = [row for row in free_candidates if row[0] == "SELL"][:MIN_ACTIVE_SELLS]
        used = {row[1] for row in owned_exits + sells}
        buys = [
            row for row in free_candidates if row[0] == "BUY" and row[1] not in used
        ][
            :MIN_ACTIVE_BUYS
        ]
        return owned_exits + buys + sells

    def _reserve_lot(self, band_id: str, quantity: D) -> list[tuple[str, D]]:
        lots = self._lots_for_band(band_id)
        if lots:
            available = sum((lot.remaining - lot.reserved for lot in lots), ZERO)
            if available < quantity:
                return []
            remaining = quantity
            allocations: list[tuple[str, D]] = []
            for lot in lots:
                amount = min(remaining, lot.remaining - lot.reserved)
                if amount > ZERO:
                    lot.reserved += amount
                    allocations.append((lot.lot_id, amount))
                    remaining -= amount
                if remaining == ZERO:
                    break
            return allocations
        if self.endowment_free_quantity < quantity:
            return []
        remaining = quantity
        allocated_cost = ZERO
        while remaining > ZERO and self._endowment_layers:
            layer_quantity, layer_basis = self._endowment_layers[0]
            amount = min(remaining, layer_quantity)
            allocated_cost += amount * layer_basis
            remaining -= amount
            layer_quantity -= amount
            if layer_quantity == ZERO:
                self._endowment_layers.popleft()
            else:
                self._endowment_layers[0] = (layer_quantity, layer_basis)
        if remaining > ZERO:
            raise ValueError("M020_ENDOWMENT_LAYER_UNDERFLOW")
        self.endowment_free_quantity -= quantity
        self.endowment_cost -= allocated_cost
        self.endowment_basis = (
            self.endowment_cost / self.endowment_free_quantity
            if self.endowment_free_quantity > ZERO
            else ZERO
        )
        self.endowment_reserved_quantity += quantity
        lot = ZonalLot(
            lot_id=f"endowment-{self._next_lot_id}",
            band_id=band_id,
            quantity=quantity,
            remaining=quantity,
            unit_basis=allocated_cost / quantity,
            remaining_cost=allocated_cost,
            entry_us=self._last_logical_us,
            origin="ENDOWMENT_SELL_BUY",
            reserved=quantity,
            source_order_id=None,
        )
        self._next_lot_id += 1
        self.lots.append(lot)
        return [(lot.lot_id, quantity)]

    def _submit(self, side: str, band_id: str, price: D, quantity: D, now: int) -> None:
        if not self._price_covered(side, price):
            self._record("COVERAGE_BLOCKED", now, side=side, band_id=band_id, price=_s(price))
            return
        quantity = _ceil_step(quantity)
        existing_lot = self._lot_for_band(band_id)
        role = (
            "EXIT"
            if (side == "BUY" and self._sell_proceeds[band_id] > ZERO)
            or (side == "SELL" and existing_lot is not None and existing_lot.origin == "BUY_ENTRY")
            else "ENTRY"
        )
        quote = quantity * price if side == "BUY" else ZERO
        allocations = self._reserve_lot(band_id, quantity) if side == "SELL" else []
        if side == "SELL" and not allocations:
            return
        if side == "BUY":
            funding = self._sell_proceeds[band_id] if role == "EXIT" else self.cash
            if quote > funding:
                return
        if side == "BUY" and any(
            order.side == "SELL" and order.price <= price for order in self.active_orders
        ):
            self._record("SELF_CROSS_BLOCKED", now, side=side, band_id=band_id)
            if side == "SELL":
                self._release(
                    ZonalOrder(
                        0,
                        band_id,
                        side,
                        price,
                        quantity,
                        quantity,
                        now,
                        now,
                        reserved_quote=quote,
                        reserved_lots=allocations,
                    )
                )
            return
        if side == "SELL" and any(
            order.side == "BUY" and order.price >= price for order in self.active_orders
        ):
            self._record("SELF_CROSS_BLOCKED", now, side=side, band_id=band_id)
            if side == "SELL":
                self._release(
                    ZonalOrder(
                        0,
                        band_id,
                        side,
                        price,
                        quantity,
                        quantity,
                        now,
                        now,
                        reserved_quote=quote,
                        reserved_lots=allocations,
                    )
                )
            return
        if side == "BUY":
            if role == "EXIT":
                self._sell_proceeds[band_id] -= quote
            else:
                self.cash -= quote
        order = ZonalOrder(
            self._next_order_id,
            band_id,
            side,
            price,
            quantity,
            quantity,
            now,
            now + self.latency_us,
            reserved_quote=quote,
            reserved_lots=allocations,
            submitted_native_us=self._last_native_us,
            role=role,
            reentry_sale_proceeds=(
                self._sell_proceeds[band_id] + quote if role == "EXIT" and side == "BUY" else ZERO
            ),
        )
        self._next_order_id += 1
        self.orders.append(order)
        self._record(
            "SUBMIT",
            now,
            order_id=order.order_id,
            band_id=band_id,
            side=side,
            price=_s(price),
            quantity=_s(quantity),
            role=role,
        )

    def _release(self, order: ZonalOrder) -> None:
        if order.side == "BUY":
            if order.role == "EXIT":
                self._sell_proceeds[order.band_id] += order.reserved_quote
            else:
                self.cash += order.reserved_quote
            order.reserved_quote = ZERO
        else:
            for lot_id, amount in order.reserved_lots:
                lot = next((item for item in self.lots if item.lot_id == lot_id), None)
                if lot is not None:
                    lot.reserved -= amount
                    if lot.origin == "ENDOWMENT_SELL_BUY":
                        previous_free = self.endowment_free_quantity
                        restored_free = previous_free + amount
                        restored_cost = (
                            lot.remaining_cost
                            if amount == lot.remaining
                            else lot.remaining_cost * amount / lot.remaining
                        )
                        self.endowment_cost += restored_cost
                        self._endowment_layers.append((amount, lot.unit_basis))
                        lot.remaining_cost -= restored_cost
                        self.endowment_free_quantity = restored_free
                        self.endowment_basis = self.endowment_cost / restored_free
                        self.endowment_reserved_quantity -= amount
                        lot.remaining -= amount
                        if lot.remaining <= ZERO:
                            self.lots.remove(lot)
                            self._band_state[lot.band_id] = "READY_FOR_BUY"
            order.reserved_lots = []

    def cancel(self, order_id: int, *, time_us: int) -> None:
        self._check_time(time_us)
        order = next((item for item in self.orders if item.order_id == order_id), None)
        if order is None or order.status not in {"PENDING", "ACTIVE"}:
            return
        if order.role == "EXIT" or order.filled > ZERO:
            self._record(
                "CANCEL_BLOCKED_OWNED_SEQUENCE",
                time_us,
                order_id=order_id,
                role=order.role,
                filled=_s(order.filled),
            )
            return
        order.status = "CANCEL_PENDING"
        order.cancel_us = time_us + self.cancel_latency_us
        self._record("CANCEL_REQUEST", time_us, order_id=order_id, effective_us=order.cancel_us)

    def _advance(self, now: int) -> None:
        for order in self.active_orders:
            if (
                order.status == "CANCEL_PENDING"
                and order.cancel_us is not None
                and order.cancel_us <= now
            ):
                self._release(order)
                order.status = "CANCELED"
                self._record("CANCEL_ACK", now, order_id=order.order_id)
            elif (
                order.status == "CANCEL_PENDING"
                and order.activation_evaluated_us is None
                and order.active_us <= now
            ):
                self._evaluate_activation(order, now, keep_cancel_pending=True)
            elif order.status == "PENDING" and order.active_us <= now:
                self._evaluate_activation(order, now)

    def _evaluate_activation(
        self, order: ZonalOrder, now: int, *, keep_cancel_pending: bool = False
    ) -> None:
        if self._last_book is None:
            return
        best_bid = self._last_book["bids"][0][0]
        best_ask = self._last_book["asks"][0][0]
        crosses_public = (order.side == "BUY" and order.price >= best_ask) or (
            order.side == "SELL" and order.price <= best_bid
        )
        crosses_self = (
            order.side == "BUY"
            and any(
                other.order_id != order.order_id
                and other.side == "SELL"
                and other.price <= order.price
                for other in self.active_orders
            )
        ) or (
            order.side == "SELL"
            and any(
                other.order_id != order.order_id
                and other.side == "BUY"
                and other.price >= order.price
                for other in self.active_orders
            )
        )
        covered = self._price_covered(order.side, order.price)
        if crosses_public or crosses_self or not covered:
            self._release(order)
            order.status = (
                "REJECTED_POST_ONLY"
                if crosses_public
                else "REJECTED_SELF_CROSS"
                if crosses_self
                else "REJECTED_UNKNOWN_COVERAGE"
            )
            self._record(
                order.status,
                now,
                order_id=order.order_id,
                best_bid=_s(best_bid),
                best_ask=_s(best_ask),
            )
            return
        order.activation_evaluated_us = now
        order.status = "CANCEL_PENDING" if keep_cancel_pending else "ACTIVE"
        order.queue = self._displayed_depth(order.side, order.price)
        self._record(
            "ACTIVATED",
            now,
            order_id=order.order_id,
            queue=_s(order.queue),
            native_book_upper_us=self._last_native_book_upper_us,
        )

    def _displayed_depth(self, side: str, price: D) -> D:
        if self._last_book is None:
            return ZERO
        levels = self._last_book.get("bids" if side == "BUY" else "asks", ())
        return next((quantity for level, quantity in levels if _dec(level) == price), ZERO)

    def _price_covered(self, side: str, price: D) -> bool:
        if self._known_bid_floor is None or self._known_ask_ceiling is None:
            return False
        return (
            price >= self._known_bid_floor
            if side == "BUY"
            else price <= self._known_ask_ceiling
        )

    def receive_book(self, book: Any, *, capture_time_us: int | None = None) -> None:
        raw_native = (
            book.get("time_us", book.get("exchange_time_us", self.start_us))
            if isinstance(book, dict)
            else getattr(book, "exchange_time_us", self.start_us)
        )
        if raw_native is None:
            raise ValueError("BOOK_NATIVE_TIME_REQUIRED")
        native = int(raw_native)
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
        bids = tuple(
            (_dec(p), _dec(q))
            for p, q in (
                book.get("bids", ()) if isinstance(book, dict) else getattr(book, "bids", ())
            )
        )
        asks = tuple(
            (_dec(p), _dec(q))
            for p, q in (
                book.get("asks", ()) if isinstance(book, dict) else getattr(book, "asks", ())
            )
        )
        if not bids or not asks:
            raise ValueError("INCOMPLETE_BOOK")
        self._last_book = {"bids": bids, "asks": asks}
        self._last_native_us = native
        raw_upper = (
            book.get("exchange_upper_us", native)
            if isinstance(book, dict)
            else getattr(book, "exchange_upper_us", native)
        )
        self._last_native_book_upper_us = int(
            native if raw_upper is None else raw_upper
        )
        raw_floor = (
            book.get("known_bid_floor")
            if isinstance(book, dict)
            else getattr(book, "known_bid_floor", None)
        )
        raw_ceiling = (
            book.get("known_ask_ceiling")
            if isinstance(book, dict)
            else getattr(book, "known_ask_ceiling", None)
        )
        if raw_floor is not None:
            self._known_bid_floor = _dec(raw_floor)
        if raw_ceiling is not None:
            self._known_ask_ceiling = _dec(raw_ceiling)
        self._advance(logical)
        if not self._endowed:
            self.initialize_endowment(bids[0][0], time_us=logical)
        self._reconcile(logical)
        self.validate_invariants()

    def _reconcile(self, logical: int) -> None:
        if self._last_book is None or not self._endowed:
            return
        bids = self._last_book["bids"]
        asks = self._last_book["asks"]
        desired = self._desired(logical, bids[0][0], asks[0][0])
        existing = {(order.side, order.band_id): order for order in self.active_orders}
        occupied_bands = {order.band_id for order in self.active_orders}
        desired_keys = {(side, band) for side, band, _, _ in desired}
        for order in self.active_orders:
            if (
                order.role == "ENTRY"
                and order.filled == ZERO
                and (order.side, order.band_id) not in desired_keys
            ):
                self.cancel(order.order_id, time_us=logical)
        for side, band_id, price, quantity in desired:
            if (side, band_id) not in existing and band_id not in occupied_bands:
                self._submit(side, band_id, price, quantity, logical)
        self._window_shortage_events += int(
            len(self.active_buys) < MIN_ACTIVE_BUYS or len(self.active_sells) < MIN_ACTIVE_SELLS
        )

    def _eligible(self, order: ZonalOrder, trade: Any) -> bool:
        native_time = int(trade["time_us"] if isinstance(trade, dict) else trade.time_us)
        if order.activation_evaluated_us is None or native_time <= max(
            order.active_us, order.activation_evaluated_us
        ):
            return False
        price, buyer_maker = (
            _dec(trade["price"] if isinstance(trade, dict) else trade.price),
            bool(trade["buyer_maker"] if isinstance(trade, dict) else trade.buyer_maker),
        )
        if order.side == "BUY":
            return (price == order.price or price < order.price) and buyer_maker
        return (price == order.price or price > order.price) and not buyer_maker

    def _maybe_settle_buy_order(self, order_id: int, time_us: int) -> None:
        source = next((order for order in self.orders if order.order_id == order_id), None)
        if (
            source is None
            or source.side != "BUY"
            or source.role != "ENTRY"
            or source.status != "FILLED"
            or source.cycle_recorded
        ):
            return
        lots = [
            lot
            for lot in self.lots
            if lot.source_order_id == order_id and lot.origin == "BUY_ENTRY"
        ]
        if not lots or any(lot.remaining > ZERO for lot in lots):
            return
        profit = sum((lot.realized_profit for lot in lots), ZERO)
        if profit <= ZERO:
            return
        source.cycle_recorded = True
        self.cycles += 1
        self.positive_cycles += 1
        self._cycles_by_band[source.band_id] += 1
        self._cycles_by_direction["BUY_SELL"] += 1
        self._band_state[source.band_id] = "READY_FOR_BUY"
        self._record(
            "CYCLE",
            time_us,
            band_id=source.band_id,
            direction="BUY_SELL",
            quantity=_s(source.filled),
            source_order_id=source.order_id,
            profit=_s(profit),
        )

    def _fill(
        self,
        order: ZonalOrder,
        quantity: D,
        time_us: int,
        *,
        source_id: str,
    ) -> D:
        quantity = min(quantity, order.remaining)
        if quantity <= ZERO:
            return ZERO
        fill_profit = ZERO
        affected_source_orders: set[int] = set()
        economic_source_orders: set[int] = set()
        economic_origins: set[str] = set()
        if order.side == "BUY":
            cost = quantity * order.price
            if cost > order.reserved_quote:
                return ZERO
            reentry = order.role == "EXIT"
            # The full quote was moved from the band's escrow into this order
            # at submission. Any positive round-trip remainder stays segregated.
            if reentry and order.quantity * order.price >= order.reentry_sale_proceeds:
                return ZERO
            order.reserved_quote -= cost
            if reentry:
                lot = ZonalLot(
                    lot_id=f"reentry-{self._next_lot_id}",
                    band_id=order.band_id,
                    quantity=quantity,
                    remaining=quantity,
                    unit_basis=order.price,
                    remaining_cost=cost,
                    entry_us=time_us,
                    origin="SELL_BUY_REENTRY",
                    source_order_id=order.order_id,
                )
                self._next_lot_id += 1
                self.lots.append(lot)
                self.inventory += quantity
                self.inventory_cost += cost
                self._band_state[order.band_id] = "BUY_WORKING"
            else:
                lot = ZonalLot(
                    lot_id=f"lot-{self._next_lot_id}",
                    band_id=order.band_id,
                    quantity=quantity,
                    remaining=quantity,
                    unit_basis=order.price,
                    remaining_cost=cost,
                    entry_us=time_us,
                    origin="BUY_ENTRY",
                    source_order_id=order.order_id,
                )
                self._next_lot_id += 1
                self.lots.append(lot)
                self.inventory += quantity
                self.inventory_cost += cost
                self._band_state[order.band_id] = "BUY_WORKING"
        else:
            remaining = quantity
            sold = ZERO
            completed_endowment_quantity = ZERO
            while remaining > ZERO and order.reserved_lots:
                lot_id, allocated = order.reserved_lots[0]
                lot = next(item for item in self.lots if item.lot_id == lot_id)
                amount = min(remaining, allocated, lot.remaining, lot.reserved)
                proceeds = amount * order.price
                cost = lot.remaining_cost if amount == lot.remaining else amount * lot.unit_basis
                if proceeds <= cost:
                    break
                lot.remaining -= amount
                lot.remaining_cost -= cost
                lot.reserved -= amount
                lot.sold_quantity += amount
                lot.sold_proceeds += proceeds
                lot.realized_profit += proceeds - cost
                fill_profit += proceeds - cost
                economic_origins.add(lot.origin)
                if lot.source_order_id is not None:
                    economic_source_orders.add(lot.source_order_id)
                if lot.origin == "ENDOWMENT_SELL_BUY":
                    self._band_state[order.band_id] = "SELL_WORKING"
                    self._sell_proceeds[order.band_id] += proceeds
                    self._sell_quantity[order.band_id] += amount
                else:
                    self.cash += proceeds
                self.inventory -= amount
                self.inventory_cost -= cost
                self.realized_profit += proceeds - cost
                if lot.origin == "ENDOWMENT_SELL_BUY":
                    self.endowment_reserved_quantity -= amount
                allocated -= amount
                remaining -= amount
                sold += amount
                if allocated == ZERO:
                    order.reserved_lots.pop(0)
                else:
                    order.reserved_lots[0] = (lot_id, allocated)
                if lot.remaining == ZERO:
                    if lot.source_order_id is not None and lot.origin == "BUY_ENTRY":
                        affected_source_orders.add(lot.source_order_id)
                    if lot.origin == "ENDOWMENT_SELL_BUY":
                        completed_endowment_quantity += lot.sold_quantity
                    else:
                        # Preserve terminal BUY-entry lots until sequence settlement
                        # so fragmented fills remain one auditable economic cycle.
                        pass
                    if lot.origin == "ENDOWMENT_SELL_BUY":
                        self.lots.remove(lot)
            quantity = sold
            if quantity <= ZERO:
                return ZERO
            if completed_endowment_quantity > ZERO:
                self._band_state[order.band_id] = "READY_FOR_BUY"
                self._sell_source_order[order.band_id] = order.order_id
        order.remaining -= quantity
        order.filled += quantity
        self._record(
            "FILL",
            time_us,
            order_id=order.order_id,
            band_id=order.band_id,
            side=order.side,
            role=order.role,
            price=_s(order.price),
            quantity=_s(quantity),
            source_id=source_id,
            realized_profit=_s(fill_profit),
            economic_source_order_ids=sorted(economic_source_orders),
            economic_origins=sorted(economic_origins),
        )
        for source_order_id in affected_source_orders:
            self._maybe_settle_buy_order(source_order_id, time_us)
        if order.remaining <= ZERO:
            if order.side == "BUY" and order.reserved_quote:
                if order.role == "EXIT":
                    self._sell_proceeds[order.band_id] += order.reserved_quote
                else:
                    self.cash += order.reserved_quote
                order.reserved_quote = ZERO
            if order.side == "BUY" and order.role == "EXIT":
                cycle_profit = self._sell_proceeds[order.band_id]
                if cycle_profit <= ZERO:
                    raise ValueError("M020_NONPOSITIVE_REENTRY_CYCLE")
                self.cycles += 1
                self.positive_cycles += 1
                self._cycles_by_band[order.band_id] += 1
                self._cycles_by_direction["SELL_BUY"] += 1
                reentry_lots = [
                    lot
                    for lot in self.lots
                    if lot.band_id == order.band_id
                    and lot.origin == "SELL_BUY_REENTRY"
                    and lot.source_order_id == order.order_id
                ]
                restored = sum((lot.remaining for lot in reentry_lots), ZERO)
                restored_cost = sum(
                    (lot.remaining_cost for lot in reentry_lots), ZERO
                )
                total_free = self.endowment_free_quantity + restored
                if total_free > ZERO:
                    self.endowment_cost += restored_cost
                    self.endowment_basis = self.endowment_cost / total_free
                self.endowment_free_quantity = total_free
                self._endowment_layers.append((restored, order.price))
                for lot in reentry_lots:
                    self.lots.remove(lot)
                self.cash += cycle_profit
                self._roundtrip_profit += cycle_profit
                self._sell_proceeds[order.band_id] = ZERO
                self._sell_quantity[order.band_id] = ZERO
                entry_sell_order_id = self._sell_source_order[order.band_id]
                self._sell_source_order[order.band_id] = None
                self._band_state[order.band_id] = "READY_FOR_BUY"
                self._record(
                    "CYCLE",
                    time_us,
                    band_id=order.band_id,
                    direction="SELL_BUY",
                    quantity=_s(order.filled),
                    source_order_id=order.order_id,
                    entry_sell_order_id=entry_sell_order_id,
                    profit=_s(cycle_profit),
                )
            elif order.side == "BUY":
                self._band_state[order.band_id] = "USDC_INVENTORY"
            order.status = "FILLED"
            if order.side == "BUY" and order.role == "ENTRY":
                self._maybe_settle_buy_order(order.order_id, time_us)
        return quantity

    def receive_trade(self, trade: Any, *, capture_time_us: int | None = None) -> D:
        native = int(trade["time_us"] if isinstance(trade, dict) else trade.time_us)
        logical = int(capture_time_us if capture_time_us is not None else native)
        self._check_time(logical)
        trade_id = str(trade["trade_id"] if isinstance(trade, dict) else trade.trade_id)
        if trade_id in self.processed_trades:
            return ZERO
        self.processed_trades.add(trade_id)
        self._advance(logical)
        available = _dec(trade["quantity"] if isinstance(trade, dict) else trade.quantity)
        price = _dec(trade["price"] if isinstance(trade, dict) else trade.price)
        if self._last_native_book_upper_us > native:
            self._record(
                "TRADE_BLOCKED_FUTURE_BOOK",
                logical,
                trade_id=trade_id,
                native_time_us=native,
                book_upper_us=self._last_native_book_upper_us,
                original_quantity=_s(available),
                consumed_quantity="0",
                price=_s(price),
                buyer_maker=bool(
                    trade["buyer_maker"] if isinstance(trade, dict) else trade.buyer_maker
                ),
            )
            return ZERO
        orders = sorted(
            [
                order
                for order in self.active_orders
                if order.status in {"ACTIVE", "CANCEL_PENDING"}
            ],
            key=lambda order: (
                (-order.price if order.side == "BUY" else order.price),
                order.active_us,
                order.order_id,
            ),
        )
        consumed = ZERO
        for order in orders:
            if available <= ZERO or not self._eligible(order, trade):
                continue
            if price == order.price and order.queue > ZERO:
                ahead = min(order.queue, available)
                order.queue -= ahead
                available -= ahead
                consumed += ahead
                if ahead > ZERO:
                    self._queue_blocked_events += 1
                    self._queue_blocked_quantity += ahead
                    self._record(
                        "QUEUE_FLOW",
                        logical,
                        order_id=order.order_id,
                        source_id=trade_id,
                        quantity=_s(ahead),
                        queue_after=_s(order.queue),
                    )
                if available <= ZERO:
                    break
            filled = self._fill(order, available, logical, source_id=trade_id)
            available -= filled
            consumed += filled
            if filled > ZERO:
                if price == order.price:
                    self._exact_fill_quantity += filled
                    self._exact_fill_events += 1
                else:
                    self._trade_through_fill_quantity += filled
                    self._trade_through_fill_events += 1
        self._last_native_us = native
        self._record(
            "TRADE",
            logical,
            trade_id=trade_id,
            native_time_us=native,
            price=_s(price),
            buyer_maker=bool(
                trade["buyer_maker"] if isinstance(trade, dict) else trade.buyer_maker
            ),
            original_quantity=_s(
                _dec(trade["quantity"] if isinstance(trade, dict) else trade.quantity)
            ),
            consumed_quantity=_s(consumed),
        )
        self._reconcile(logical)
        self.validate_invariants()
        return consumed

    def validate_invariants(self) -> None:
        """Raise if ownership or fixed-point quantities became inconsistent."""
        quantities = (
            self.cash,
            self.inventory,
            self.inventory_cost,
            self.realized_profit,
            self.endowment_free_quantity,
            self.endowment_reserved_quantity,
            self.endowment_cost,
        )
        if any(value < ZERO for value in quantities):
            raise ValueError("M020_NEGATIVE_OWNERSHIP")
        seen: set[tuple[str, str]] = set()
        for order in self.active_orders:
            key = (order.side, order.band_id)
            if key in seen:
                raise ValueError("M020_DUPLICATE_ACTIVE_SIDE_BAND")
            seen.add(key)
            if min(order.remaining, order.filled, order.reserved_quote) < ZERO:
                raise ValueError("M020_NEGATIVE_ORDER_QUANTITY")
            for _, quantity in order.reserved_lots:
                if quantity < ZERO:
                    raise ValueError("M020_NEGATIVE_LOT_RESERVATION")
        for lot in self.lots:
            if min(lot.remaining, lot.reserved, lot.sold_quantity) < ZERO:
                raise ValueError("M020_NEGATIVE_LOT_QUANTITY")
            if lot.reserved > lot.remaining:
                raise ValueError("M020_LOT_OVERRESERVED")
        if self.endowment_reserved_quantity > self.endowment_initial_quantity:
            raise ValueError("M020_ENDOWMENT_OVERRESERVED")
        if sum((quantity for quantity, _ in self._endowment_layers), ZERO) != (
            self.endowment_free_quantity
        ):
            raise ValueError("M020_ENDOWMENT_LAYER_QUANTITY_DRIFT")
        if sum(
            (quantity * basis for quantity, basis in self._endowment_layers), ZERO
        ) != self.endowment_cost:
            raise ValueError("M020_ENDOWMENT_LAYER_COST_DRIFT")
        reconstructed_inventory = self.endowment_free_quantity + sum(
            (lot.remaining for lot in self.lots), ZERO
        )
        if reconstructed_inventory != self.inventory:
            raise ValueError("M020_INVENTORY_OWNERSHIP_DRIFT")
        reconstructed_cost = self.endowment_cost + sum(
            (lot.remaining_cost for lot in self.lots), ZERO
        )
        if reconstructed_cost != self.inventory_cost:
            raise ValueError("M020_INVENTORY_BASIS_DRIFT")
        active_buys = [order.price for order in self.active_orders if order.side == "BUY"]
        active_sells = [order.price for order in self.active_orders if order.side == "SELL"]
        if active_buys and active_sells and max(active_buys) >= min(active_sells):
            raise ValueError("M020_ACTIVE_SELF_CROSS")
        reserved_quotes = sum((order.reserved_quote for order in self.active_orders), ZERO)
        reserved_reentry = sum(self._sell_proceeds.values(), ZERO)
        ownership = (
            self.cash
            + reserved_quotes
            + reserved_reentry
            + self.inventory_cost
            - self.realized_profit
        )
        if ownership != self.initial_capital:
            raise ValueError("M020_CAPITAL_OWNERSHIP_DRIFT")

    def metrics(self) -> dict[str, Any]:
        mark = ZERO
        if self._last_book and self._last_book["bids"]:
            mark = self._last_book["bids"][0][0]
        reserved_quote = sum((order.reserved_quote for order in self.active_orders), ZERO)
        reserved_reentry = sum(self._sell_proceeds.values(), ZERO)
        usdt = self.cash + reserved_quote + reserved_reentry
        equity = usdt + self.inventory * mark
        buy_count = len(self.active_buys)
        sell_count = len(self.active_sells)
        active_band_ids = {order.band_id for order in self.active_orders}
        active_band_ids.update(lot.band_id for lot in self.lots if lot.remaining > ZERO)
        dormant_band_ids = {
            lot.band_id
            for lot in self.lots
            if lot.remaining > ZERO
            and not any(
                order.band_id == lot.band_id and order.side == "SELL"
                for order in self.active_orders
            )
        }
        return {
            "label": self.normalized_label,
            "period_hours": "5",
            "total_cycles": self.cycles,
            "total_positive_cycles": self.positive_cycles,
            "cycles_per_hour": _s(D(self.cycles) / D("5")),
            "usdt_final": _s(usdt),
            "usdc_final": _s(self.inventory),
            "total_marked_equity": _s(equity),
            "realized_profit": _s(self.realized_profit),
            "roundtrip_profit": _s(self._roundtrip_profit),
            "reentry_escrow": _s(reserved_reentry),
            "unrealized_pnl": _s(self.inventory * mark - self.inventory_cost),
            "active_bands": len(active_band_ids),
            "dormant_bands": len(dormant_band_ids),
            "orders_canceled": sum(order.status == "CANCELED" for order in self.orders),
            "processed_trades": len(self.processed_trades),
            "active_buys": buy_count,
            "active_sells": sell_count,
            "cycles_by_band": dict(self._cycles_by_band),
            "cycles_by_direction": dict(self._cycles_by_direction),
            "queue_blocked_events": self._queue_blocked_events,
            "queue_blocked_quantity": _s(self._queue_blocked_quantity),
            "exact_fill_quantity": _s(self._exact_fill_quantity),
            "trade_through_fill_quantity": _s(self._trade_through_fill_quantity),
            "exact_fill_events": self._exact_fill_events,
            "trade_through_fill_events": self._trade_through_fill_events,
            "window_shortage_events": self._window_shortage_events,
            "band_states": dict(self._band_state),
            "window_unsupported": buy_count < MIN_ACTIVE_BUYS or sell_count < MIN_ACTIVE_SELLS,
            "coverage_status": (
                "WINDOW_UNDERSUPPORTED"
                if buy_count < MIN_ACTIVE_BUYS or sell_count < MIN_ACTIVE_SELLS
                else "TARGET_4_BY_4"
            ),
            "cutoff_exclusive": True,
            "negative_exit_allowed": False,
            "order_notional_mode": "NORMALIZED_1_USDT_NON_EXECUTABLE",
        }

    def finish(self, *, time_us: int) -> dict[str, Any]:
        if time_us != self.end_us:
            self._check_time(time_us)
        self._finished = True
        return self.metrics()

    def _state(self) -> dict[str, Any]:
        orders = []
        for order in self.orders:
            row = dict(order.__dict__)
            for key in (
                "price",
                "quantity",
                "remaining",
                "filled",
                "queue",
                "reserved_quote",
                "reentry_sale_proceeds",
            ):
                row[key] = _s(row[key])
            row["reserved_lots"] = [[key, _s(value)] for key, value in order.reserved_lots]
            orders.append(row)
        lots = []
        for lot in self.lots:
            row = dict(lot.__dict__)
            for key in (
                "quantity",
                "remaining",
                "unit_basis",
                "remaining_cost",
                "reserved",
                "sold_proceeds",
                "sold_quantity",
                "realized_profit",
            ):
                row[key] = _s(row[key])
            lots.append(row)
        return {
            "cash": _s(self.cash),
            "inventory": _s(self.inventory),
            "inventory_cost": _s(self.inventory_cost),
            "realized_profit": _s(self.realized_profit),
            "roundtrip_profit": _s(self._roundtrip_profit),
            "cycles": self.cycles,
            "positive_cycles": self.positive_cycles,
            "processed_trades": sorted(self.processed_trades),
            "band_state": self._band_state,
            "sell_proceeds": {key: _s(value) for key, value in self._sell_proceeds.items()},
            "sell_quantity": {key: _s(value) for key, value in self._sell_quantity.items()},
            "sell_source_order": self._sell_source_order,
            "endowment_free_quantity": _s(self.endowment_free_quantity),
            "endowment_basis": _s(self.endowment_basis),
            "endowment_cost": _s(self.endowment_cost),
            "endowment_layers": [
                [_s(quantity), _s(basis)] for quantity, basis in self._endowment_layers
            ],
            "endowment_reserved_quantity": _s(self.endowment_reserved_quantity),
            "endowed": self._endowed,
            "last_book": self._last_book,
            "orders": orders,
            "lots": lots,
            "next_order_id": self._next_order_id,
            "next_lot_id": self._next_lot_id,
            "logical_us": self._last_logical_us,
            "native_us": self._last_native_us,
            "native_book_upper_us": self._last_native_book_upper_us,
            "finished": self._finished,
            "endowment_initial_quantity": _s(self.endowment_initial_quantity),
            "known_bid_floor": (
                _s(self._known_bid_floor) if self._known_bid_floor is not None else None
            ),
            "known_ask_ceiling": (
                _s(self._known_ask_ceiling) if self._known_ask_ceiling is not None else None
            ),
            "cycles_by_band": dict(self._cycles_by_band),
            "cycles_by_direction": dict(self._cycles_by_direction),
            "queue_blocked_events": self._queue_blocked_events,
            "queue_blocked_quantity": _s(self._queue_blocked_quantity),
            "exact_fill_quantity": _s(self._exact_fill_quantity),
            "trade_through_fill_quantity": _s(self._trade_through_fill_quantity),
            "exact_fill_events": self._exact_fill_events,
            "trade_through_fill_events": self._trade_through_fill_events,
            "window_shortage_events": self._window_shortage_events,
            "config": self._config(),
        }

    def _config(self) -> dict[str, Any]:
        return {
            "start_us": self.start_us,
            "end_us": self.end_us,
            "latency_us": self.latency_us,
            "cancel_latency_us": self.cancel_latency_us,
            "initial_capital": _s(self.initial_capital),
            "bands": [
                {
                    "band_id": band.band_id,
                    "price_low": _s(band.price_low),
                    "price_high": _s(band.price_high),
                    "buy_price": _s(band.buy_price),
                    "sell_price": _s(band.sell_price),
                    "buy_capacity": _s(band.buy_capacity),
                    "sell_capacity": _s(band.sell_capacity),
                }
                for band in self.bands
            ],
        }

    def checkpoint(self) -> dict[str, Any]:
        state = self._state()
        return {
            "schema": "M020_ZONAL_PING_PONG_V1",
            "state": state,
            "sha256": canonical_hash(state),
        }

    def restore(self, checkpoint: dict[str, Any]) -> None:
        if checkpoint.get("schema") != "M020_ZONAL_PING_PONG_V1":
            raise ValueError("INVALID_M020_CHECKPOINT")
        state = checkpoint.get("state")
        if not isinstance(state, dict) or checkpoint.get("sha256") != canonical_hash(state):
            raise ValueError("M020_CHECKPOINT_HASH_MISMATCH")
        if state.get("config") != self._config():
            raise ValueError("M020_CHECKPOINT_CONFIG_MISMATCH")
        self.cash = D(state["cash"])
        self.inventory = D(state["inventory"])
        self.inventory_cost = D(state["inventory_cost"])
        self.realized_profit = D(state["realized_profit"])
        self._roundtrip_profit = D(state["roundtrip_profit"])
        self.cycles, self.positive_cycles = int(state["cycles"]), int(state["positive_cycles"])
        self.processed_trades = set(state["processed_trades"])
        self._band_state = dict(state["band_state"])
        self._sell_proceeds = {key: D(value) for key, value in state["sell_proceeds"].items()}
        self._sell_quantity = {key: D(value) for key, value in state["sell_quantity"].items()}
        self._sell_source_order = {
            key: (None if value is None else int(value))
            for key, value in state["sell_source_order"].items()
        }
        self.endowment_free_quantity = D(state["endowment_free_quantity"])
        self.endowment_basis = D(state["endowment_basis"])
        self.endowment_cost = D(state["endowment_cost"])
        self._endowment_layers = deque(
            (D(quantity), D(basis)) for quantity, basis in state["endowment_layers"]
        )
        self.endowment_reserved_quantity = D(state["endowment_reserved_quantity"])
        self.endowment_initial_quantity = D(state.get("endowment_initial_quantity", "0"))
        self._known_bid_floor = (
            D(state["known_bid_floor"]) if state.get("known_bid_floor") is not None else None
        )
        self._known_ask_ceiling = (
            D(state["known_ask_ceiling"]) if state.get("known_ask_ceiling") is not None else None
        )
        self._cycles_by_band = {
            key: int(value) for key, value in state.get("cycles_by_band", {}).items()
        }
        self._cycles_by_band.update(
            {band.band_id: self._cycles_by_band.get(band.band_id, 0) for band in self.bands}
        )
        self._cycles_by_direction = {
            "BUY_SELL": int(state.get("cycles_by_direction", {}).get("BUY_SELL", 0)),
            "SELL_BUY": int(state.get("cycles_by_direction", {}).get("SELL_BUY", 0)),
        }
        self._queue_blocked_events = int(state.get("queue_blocked_events", 0))
        self._queue_blocked_quantity = D(state.get("queue_blocked_quantity", "0"))
        self._exact_fill_quantity = D(state.get("exact_fill_quantity", "0"))
        self._trade_through_fill_quantity = D(state.get("trade_through_fill_quantity", "0"))
        self._exact_fill_events = int(state.get("exact_fill_events", 0))
        self._trade_through_fill_events = int(state.get("trade_through_fill_events", 0))
        self._window_shortage_events = int(state.get("window_shortage_events", 0))
        self._endowed = bool(state["endowed"])
        self._last_book = state["last_book"]
        if self._last_book is not None:
            self._last_book = {
                "bids": tuple(
                    (D(price), D(quantity)) for price, quantity in self._last_book["bids"]
                ),
                "asks": tuple(
                    (D(price), D(quantity)) for price, quantity in self._last_book["asks"]
                ),
            }
        self.orders = []
        for row in state["orders"]:
            row = dict(row)
            for key in (
                "price",
                "quantity",
                "remaining",
                "filled",
                "queue",
                "reserved_quote",
                "reentry_sale_proceeds",
            ):
                row[key] = D(row[key])
            row["reserved_lots"] = [(key, D(value)) for key, value in row["reserved_lots"]]
            self.orders.append(ZonalOrder(**row))
        self.lots = deque()
        for row in state["lots"]:
            row = dict(row)
            for key in (
                "quantity",
                "remaining",
                "unit_basis",
                "remaining_cost",
                "reserved",
                "sold_proceeds",
                "sold_quantity",
                "realized_profit",
            ):
                row[key] = D(row[key])
            self.lots.append(ZonalLot(**row))
        self._next_order_id = int(state["next_order_id"])
        self._next_lot_id = int(state["next_lot_id"])
        self._last_logical_us = int(state["logical_us"])
        self._last_native_us = int(state["native_us"])
        self._last_native_book_upper_us = int(state["native_book_upper_us"])
        self._finished = bool(state["finished"])

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint: dict[str, Any],
        bands: Iterable[ZonalBand],
        *,
        start_us: int,
        end_us: int,
        **kwargs: Any,
    ) -> ZonalPingPong:
        value = cls(bands, start_us=start_us, end_us=end_us, **kwargs)
        value.restore(checkpoint)
        return value


__all__ = [
    "MAX_BANDS",
    "MIN_ACTIVE_BUYS",
    "MIN_ACTIVE_SELLS",
    "NORMALIZED_CAPITAL",
    "NORMALIZED_ORDER_NOTIONAL",
    "VIRTUAL_STEP",
    "ZonalBand",
    "ZonalLot",
    "ZonalOrder",
    "ZonalPingPong",
]
