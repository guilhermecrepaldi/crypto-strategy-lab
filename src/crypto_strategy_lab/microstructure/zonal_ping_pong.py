"""Pure M020 fixed-zone ping-pong throughput kernel.

The one-USDT order size is deliberately a normalized, non-executable
structural diagnostic.  This module has no market-data reader and no network
or replay launcher.  A caller supplies causal books and trades.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any

from crypto_strategy_lab.domain import canonical_hash

D = Decimal
ZERO = D("0")
ONE = D("1")
NORMALIZED_CAPITAL = D("100")
NORMALIZED_ORDER_NOTIONAL = D("1")
HISTORICAL_STEP = D("1")
VIRTUAL_STEP = HISTORICAL_STEP
M021_TICK_SIZE = D("0.0001")
M021_BUY_SLOTS = 100
M021_SELL_SLOTS = 100
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
    queue_blocked: D = ZERO
    fill_events: int = 0
    last_fill_us: int | None = None


class ZonalPingPong:
    """Deterministic fixed-band M020 kernel with a five-hour hard cutoff."""

    max_band_limit = MAX_BANDS

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
        max_bands: int = MAX_BANDS,
        allow_duplicate_prices: bool = False,
    ) -> None:
        if max_bands > self.max_band_limit:
            raise ValueError("M021_MAX_BANDS_REQUIRES_DENSE_SUBCLASS")
        materialized = tuple(bands)
        if not materialized or len(materialized) > max_bands:
            raise ValueError("INVALID_BAND_COUNT")
        ids = [band.band_id for band in materialized]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_IMMUTABLE_BAND_ID")
        buy_prices = [band.buy_price for band in materialized]
        sell_prices = [band.sell_price for band in materialized]
        if not allow_duplicate_prices and len(buy_prices) != len(set(buy_prices)):
            raise ValueError("DUPLICATE_IMMUTABLE_BUY_PRICE")
        if not allow_duplicate_prices and len(sell_prices) != len(set(sell_prices)):
            raise ValueError("DUPLICATE_IMMUTABLE_SELL_PRICE")
        if end_us <= start_us or latency_us <= 0 or cancel_latency_us <= 0:
            raise ValueError("INVALID_FIVE_HOUR_WINDOW")
        self.bands = materialized
        self._bands = {band.band_id: band for band in materialized}
        self.start_us, self.end_us = int(start_us), int(end_us)
        self.latency_us, self.cancel_latency_us = latency_us, cancel_latency_us
        self.initial_capital = _dec(initial_capital)
        self.max_bands = int(max_bands)
        self.allow_duplicate_prices = bool(allow_duplicate_prices)
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
        self._max_simultaneous_open_orders = 0
        self._total_fill_events = 0
        self._buy_fill_events = 0
        self._sell_fill_events = 0

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
        return [lot for lot in self.lots if lot.band_id == band_id and lot.remaining > ZERO]

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
                    self._endowment_layers[0][1] if self._endowment_layers else self.endowment_basis
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
        buys = [row for row in free_candidates if row[0] == "BUY" and row[1] not in used][
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
            self._record(
                "INVENTORY_BLOCKED", now, side=side, band_id=band_id, quantity=_s(quantity)
            )
            return
        if side == "BUY":
            funding = self._sell_proceeds[band_id] if role == "EXIT" else self.cash
            if quote > funding:
                self._record(
                    "CAPITAL_BLOCKED",
                    now,
                    side=side,
                    band_id=band_id,
                    required=_s(quote),
                    available=_s(funding),
                )
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
        self._max_simultaneous_open_orders = max(
            self._max_simultaneous_open_orders, len(self.active_orders)
        )
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
        return price >= self._known_bid_floor if side == "BUY" else price <= self._known_ask_ceiling

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
        self._last_native_book_upper_us = int(native if raw_upper is None else raw_upper)
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
        self._total_fill_events += 1
        order.fill_events += 1
        order.last_fill_us = time_us
        if order.side == "BUY":
            self._buy_fill_events += 1
        else:
            self._sell_fill_events += 1
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
                restored_cost = sum((lot.remaining_cost for lot in reentry_lots), ZERO)
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
            [order for order in self.active_orders if order.status in {"ACTIVE", "CANCEL_PENDING"}],
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
                    order.queue_blocked += ahead
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
        if (
            sum((quantity * basis for quantity, basis in self._endowment_layers), ZERO)
            != self.endowment_cost
        ):
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
            "max_simultaneous_open_orders": self._max_simultaneous_open_orders,
            "total_fill_events": self._total_fill_events,
            "buy_fill_events": self._buy_fill_events,
            "sell_fill_events": self._sell_fill_events,
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
                "queue_blocked",
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
            "max_simultaneous_open_orders": self._max_simultaneous_open_orders,
            "total_fill_events": self._total_fill_events,
            "buy_fill_events": self._buy_fill_events,
            "sell_fill_events": self._sell_fill_events,
            "config": self._config(),
        }

    def _config(self) -> dict[str, Any]:
        return {
            "start_us": self.start_us,
            "end_us": self.end_us,
            "latency_us": self.latency_us,
            "cancel_latency_us": self.cancel_latency_us,
            "initial_capital": _s(self.initial_capital),
            "max_bands": self.max_bands,
            "allow_duplicate_prices": self.allow_duplicate_prices,
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
        self._max_simultaneous_open_orders = int(
            state.get("max_simultaneous_open_orders", len(self.active_orders))
        )
        self._total_fill_events = int(state.get("total_fill_events", 0))
        self._buy_fill_events = int(state.get("buy_fill_events", 0))
        self._sell_fill_events = int(state.get("sell_fill_events", 0))
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
                "queue_blocked",
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


class DensePingPongProbe(ZonalPingPong):
    """M021's fixed 100-buy/100-sell normalized mechanics probe.

    The grid is created from the first valid book and never recenters.  This
    subclass deliberately reuses the M020 causal book, queue, ownership and
    trade-budget machinery; it only changes the frozen slot geometry and the
    normalized starting allocation.
    """

    normalized_label = (
        "M021 DENSE 200-SLOT PING-PONG MECHANICS PROBE. "
        "NORMALIZED 1-USDC ORDERS ARE NOT LIVE-EXECUTABLE."
    )
    max_band_limit = M021_BUY_SLOTS + M021_SELL_SLOTS

    def __init__(
        self,
        *,
        start_us: int,
        end_us: int,
        latency_us: int = 1,
        cancel_latency_us: int = 1,
        anchor: D | None = None,
        initial_capital: D | None = None,
    ) -> None:
        anchor_value = None if anchor is None else _dec(anchor)
        provisional = anchor_value or D("1")
        bands = self._make_grid(provisional)
        total_capital = (
            _dec(initial_capital) if initial_capital is not None else D("200") * provisional
        )
        super().__init__(
            bands,
            start_us=start_us,
            end_us=end_us,
            latency_us=latency_us,
            cancel_latency_us=cancel_latency_us,
            initial_capital=total_capital,
            max_bands=M021_BUY_SLOTS + M021_SELL_SLOTS,
            allow_duplicate_prices=True,
        )
        self.grid_anchor = anchor_value
        self.rolling_recenter = False
        self._dense_configured = anchor_value is not None
        self._dense_initial_usdt: D | None = None
        self._dense_initial_usdc = D("100")
        self._dense_first_bid: D | None = None

    @staticmethod
    def _make_grid(anchor: D) -> tuple[ZonalBand, ...]:
        anchor = _dec(anchor)
        if anchor <= D("0.0100"):
            raise ValueError("M021_ANCHOR_TOO_LOW")
        bands: list[ZonalBand] = []
        for index in range(1, M021_BUY_SLOTS + 1):
            entry = anchor - M021_TICK_SIZE * D(index)
            exit_price = entry + M021_TICK_SIZE
            bands.append(
                ZonalBand(
                    f"B{index:03d}",
                    entry,
                    exit_price,
                    entry,
                    exit_price,
                    ONE,
                    ONE,
                )
            )
        for index in range(1, M021_SELL_SLOTS + 1):
            entry = anchor + M021_TICK_SIZE * D(index)
            exit_price = entry - M021_TICK_SIZE
            bands.append(
                ZonalBand(
                    f"S{index:03d}",
                    exit_price,
                    entry,
                    exit_price,
                    entry,
                    ONE,
                    ONE,
                )
            )
        return tuple(bands)

    def _replace_grid(self, anchor: D) -> None:
        self.grid_anchor = _dec(anchor)
        self.bands = self._make_grid(self.grid_anchor)
        self._bands = {band.band_id: band for band in self.bands}
        self._band_state = {band.band_id: "READY_FOR_BUY" for band in self.bands}
        self._sell_proceeds = {band.band_id: ZERO for band in self.bands}
        self._sell_quantity = {band.band_id: ZERO for band in self.bands}
        self._sell_source_order = {band.band_id: None for band in self.bands}
        self._cycles_by_band = {band.band_id: 0 for band in self.bands}

    def initialize_endowment(self, first_bid: D, *, time_us: int | None = None) -> None:
        if self._endowed:
            raise ValueError("ENDOWMENT_ALREADY_INITIALIZED")
        time_us = self.start_us if time_us is None else int(time_us)
        self._check_time(time_us)
        first_bid = _dec(first_bid)
        if first_bid <= ZERO:
            raise ValueError("INVALID_ENDOWMENT_BID")
        quantity = self._dense_initial_usdc
        cost = quantity * first_bid
        self.cash -= cost
        self.inventory += quantity
        self.inventory_cost += cost
        self.endowment_free_quantity = quantity
        self.endowment_basis = first_bid
        self.endowment_cost = cost
        self._endowment_layers.append((quantity, first_bid))
        self.endowment_initial_quantity = quantity
        self._endowed = True
        self._record("ENDOWMENT", time_us, bid=_s(first_bid), quantity=_s(quantity))

    def receive_book(self, book: Any, *, capture_time_us: int | None = None) -> None:
        if not self._dense_configured:
            bids = book.get("bids", ()) if isinstance(book, dict) else getattr(book, "bids", ())
            asks = book.get("asks", ()) if isinstance(book, dict) else getattr(book, "asks", ())
            if not bids or not asks:
                raise ValueError("INCOMPLETE_BOOK")
            bid = _dec(bids[0][0])
            ask = _dec(asks[0][0])
            midpoint = (bid + ask) / D("2")
            anchor = (midpoint / M021_TICK_SIZE).to_integral_value(rounding=ROUND_HALF_UP)
            self._replace_grid(anchor * M021_TICK_SIZE)
            self._dense_initial_usdt = sum(
                (band.buy_price for band in self.bands if band.band_id.startswith("B")),
                ZERO,
            )
            self._dense_first_bid = bid
            self.initial_capital = self._dense_initial_usdt + self._dense_initial_usdc * bid
            self.cash = self.initial_capital
            self._dense_configured = True
        super().receive_book(book, capture_time_us=capture_time_us)

    def _desired(self, now: int, best_bid: D, best_ask: D) -> list[tuple[str, str, D, D]]:
        desired: list[tuple[str, str, D, D]] = []
        for band in self.bands:
            state = self._band_state[band.band_id]
            lots = self._lots_for_band(band.band_id)
            if band.band_id.startswith("B"):
                if (
                    state == "READY_FOR_BUY"
                    and not lots
                    and self._sell_proceeds[band.band_id] == ZERO
                ):
                    desired.append(("BUY", band.band_id, band.buy_price, ONE))
                elif (
                    state == "USDC_INVENTORY"
                    and lots
                    and band.sell_price > max(lot.unit_basis for lot in lots)
                ):
                    desired.append(("SELL", band.band_id, band.sell_price, ONE))
            else:
                if state == "READY_FOR_BUY" and self._sell_proceeds[band.band_id] > ZERO:
                    quantity = self._sell_quantity[band.band_id]
                    if band.buy_price * quantity < self._sell_proceeds[band.band_id]:
                        desired.append(("BUY", band.band_id, band.buy_price, quantity))
                elif (
                    state == "READY_FOR_BUY"
                    and self._sell_proceeds[band.band_id] == ZERO
                    and (not lots or any(lot.reserved > ZERO for lot in lots))
                ):
                    desired.append(("SELL", band.band_id, band.sell_price, ONE))
        return desired

    def metrics(self) -> dict[str, Any]:
        result = super().metrics()
        active_until_us = self.end_us if self._finished else self._last_logical_us
        slots = []
        for band in self.bands:
            orders = [order for order in self.orders if order.band_id == band.band_id]
            filled_quantity = sum((order.filled for order in orders), ZERO)
            fill_events = sum(order.fill_events for order in orders)
            active_time_us = 0
            for order in orders:
                if order.activation_evaluated_us is None or order.status.startswith("REJECTED"):
                    continue
                if order.status == "FILLED" and order.last_fill_us is not None:
                    order_end_us = order.last_fill_us
                elif order.cancel_us is not None and order.status == "CANCELED":
                    order_end_us = order.cancel_us
                else:
                    order_end_us = active_until_us
                active_time_us += max(0, order_end_us - order.activation_evaluated_us)
            slots.append(
                {
                    "slot_id": band.band_id,
                    "initial_side": "BUY" if band.band_id.startswith("B") else "SELL",
                    "price": _s(
                        band.buy_price if band.band_id.startswith("B") else band.sell_price
                    ),
                    "fills": fill_events,
                    "filled_quantity": _s(filled_quantity),
                    "complete_cycles": self._cycles_by_band[band.band_id],
                    "active_time_us": active_time_us,
                    "queue_blocked": _s(sum((order.queue_blocked for order in orders), ZERO)),
                    "open_position_at_cutoff": any(
                        lot.band_id == band.band_id and lot.remaining > ZERO for lot in self.lots
                    )
                    or self._sell_proceeds[band.band_id] > ZERO,
                }
            )
        buckets = {}
        for prefix in ("B", "S"):
            for start in range(1, 101, 10):
                ids = {f"{prefix}{index:03d}" for index in range(start, start + 10)}
                buckets[f"{prefix}{start:03d}_{start + 9:03d}"] = {
                    "fills": sum(slot["fills"] for slot in slots if slot["slot_id"] in ids),
                    "cycles": sum(
                        slot["complete_cycles"] for slot in slots if slot["slot_id"] in ids
                    ),
                }
        buy_bands = [band for band in self.bands if band.band_id.startswith("B")]
        sell_bands = [band for band in self.bands if band.band_id.startswith("S")]
        result.update(
            {
                "model": "M021",
                "period_hours": "5",
                "rolling_recenter": False,
                "grid_anchor": None if self.grid_anchor is None else _s(self.grid_anchor),
                "grid_tick": _s(M021_TICK_SIZE),
                "buy_slot_count": M021_BUY_SLOTS,
                "sell_slot_count": M021_SELL_SLOTS,
                "initial_usdt": (
                    None if self._dense_initial_usdt is None else _s(self._dense_initial_usdt)
                ),
                "initial_usdc": _s(self._dense_initial_usdc),
                "initial_marked_equity": (
                    None
                    if self._dense_initial_usdt is None or self._dense_first_bid is None
                    else _s(
                        self._dense_initial_usdt + self._dense_initial_usdc * self._dense_first_bid
                    )
                ),
                "buy_first_cycles": self._cycles_by_direction["BUY_SELL"],
                "sell_first_cycles": self._cycles_by_direction["SELL_BUY"],
                "total_fills": self._total_fill_events,
                "buy_fills": self._buy_fill_events,
                "sell_fills": self._sell_fill_events,
                "max_simultaneous_open_orders": self._max_simultaneous_open_orders,
                "grid_prices": {
                    "buy_entries": [_s(band.buy_price) for band in buy_bands],
                    "sell_entries": [_s(band.sell_price) for band in sell_bands],
                    "buy_exits": [_s(band.buy_price) for band in sell_bands],
                    "sell_exits": [_s(band.sell_price) for band in buy_bands],
                },
                "slot_report": slots,
                "bucket_report": buckets,
                "order_notional_mode": "NORMALIZED_1_USDC_NON_EXECUTABLE_MECHANICS_PROBE",
            }
        )
        return result

    def _state(self) -> dict[str, Any]:
        state = super()._state()
        state.update(
            {
                "dense_anchor": None if self.grid_anchor is None else _s(self.grid_anchor),
                "dense_configured": self._dense_configured,
                "dense_initial_usdt": (
                    None if self._dense_initial_usdt is None else _s(self._dense_initial_usdt)
                ),
                "dense_first_bid": (
                    None if self._dense_first_bid is None else _s(self._dense_first_bid)
                ),
            }
        )
        return state

    def checkpoint(self) -> dict[str, Any]:
        state = self._state()
        return {
            "schema": "M021_DENSE_PING_PONG_V1",
            "state": state,
            "sha256": canonical_hash(state),
        }

    def restore(self, checkpoint: dict[str, Any]) -> None:
        if checkpoint.get("schema") != "M021_DENSE_PING_PONG_V1":
            raise ValueError("INVALID_M021_CHECKPOINT")
        state = checkpoint.get("state")
        if not isinstance(state, dict) or checkpoint.get("sha256") != canonical_hash(state):
            raise ValueError("M021_CHECKPOINT_HASH_MISMATCH")
        base_checkpoint = {
            "schema": "M020_ZONAL_PING_PONG_V1",
            "state": state,
            "sha256": checkpoint["sha256"],
        }
        super().restore(base_checkpoint)
        self.grid_anchor = None if state.get("dense_anchor") is None else D(state["dense_anchor"])
        self._dense_configured = bool(state.get("dense_configured", True))
        self._dense_initial_usdt = (
            None if state.get("dense_initial_usdt") is None else D(state["dense_initial_usdt"])
        )
        self._dense_first_bid = (
            None if state.get("dense_first_bid") is None else D(state["dense_first_bid"])
        )

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint: dict[str, Any],
        *,
        start_us: int | None = None,
        end_us: int | None = None,
        latency_us: int | None = None,
        cancel_latency_us: int | None = None,
    ) -> DensePingPongProbe:
        state = checkpoint.get("state", {})
        config = state.get("config", {})
        value = cls(
            start_us=config["start_us"] if start_us is None else start_us,
            end_us=config["end_us"] if end_us is None else end_us,
            latency_us=config["latency_us"] if latency_us is None else latency_us,
            cancel_latency_us=(
                config["cancel_latency_us"] if cancel_latency_us is None else cancel_latency_us
            ),
            anchor=None if state.get("dense_anchor") is None else D(state["dense_anchor"]),
            initial_capital=D(config["initial_capital"]),
        )
        value.restore(checkpoint)
        return value


class ManagedDensePingPongProbe(DensePingPongProbe):
    """M022 order manager over the unchanged M021 economic lanes."""

    normalized_label = (
        "M022 DENSE PING-PONG ORDER MANAGER V2. NORMALIZED 1-USDC ORDERS "
        "ARE NOT LIVE-EXECUTABLE."
    )
    MAX_OPEN_ORDERS = 160
    TARGET_FREE_PER_SIDE = 80

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._manager_claims: dict[str, tuple[str, D]] = {}
        self._manager_claim_times: dict[str, int] = {}
        self._manager_claim_source_order_ids: dict[str, int] = {}
        self._manager_lane_profit = {band.band_id: ZERO for band in self.bands}
        self._manager_lane_cycles = {band.band_id: 0 for band in self.bands}
        self._manager_lane_ownership = self._build_lane_ownership()
        self._manager_s_free: dict[str, dict[str, D]] = {
            band.band_id: {"quantity": ZERO, "cost": ZERO}
            for band in self.bands
            if band.band_id.startswith("S")
        }
        self._manager_reservation_lane: str | None = None
        self._manager_return_preemptions = 0
        self._manager_free_canceled_return = 0
        self._manager_free_canceled_float = 0
        self._manager_free_reposted = 0
        self._manager_return_submissions = 0
        self._manager_return_fills = 0
        self._manager_return_wait_us: list[int] = []
        self._manager_return_submission_wait_us: list[int] = []
        self._manager_return_activation_wait_us: list[int] = []
        self._manager_return_submission_claims: set[tuple[str, int, int]] = set()
        self._manager_return_activation_claims: set[tuple[str, int, int]] = set()
        self._manager_return_order_claim_tokens: dict[int, tuple[str, int, int]] = {}
        self._manager_return_completed_order_ids: set[int] = set()
        self._manager_partial_residual_order_ids: set[int] = set()
        self._manager_blocked_free = 0
        self._manager_blocked_owned = 0
        self._manager_reconcile_cap_blocks = 0
        self._manager_last_sample_us: int | None = None
        self._manager_observation_us = 0
        self._manager_weighted_active = ZERO
        self._manager_weighted_parked = ZERO
        self._manager_weighted_distance = ZERO
        self._manager_within5 = ZERO
        self._manager_within10 = ZERO
        self._manager_min_active_after_warmup: int | None = None
        self._manager_repost_lanes: set[str] = set()
        self._manager_repost_reasons: dict[str, str] = {}
        self._manager_return_order_ids: set[int] = set()
        self._manager_cycle_prices: list[D] = []
        self._manager_active_order_time = ZERO
        self._manager_snapshot_mid: D | None = None
        self._manager_snapshot_prices: tuple[D, ...] = ()
        self._manager_snapshot_active_count = 0
        self._manager_snapshot_open_count = 0
        self._manager_snapshot_active_prices: tuple[D, ...] = ()
        self._manager_snapshot_parked_free_count = 0
        self._manager_warmup_started = False

    def _build_lane_ownership(self) -> dict[str, dict[str, str]]:
        return {
            band.band_id: {
                "initial_usdt": _s(band.buy_price if band.band_id.startswith("B") else ZERO),
                "initial_usdc": _s(ONE if band.band_id.startswith("S") else ZERO),
                "profit": _s(self._manager_lane_profit.get(band.band_id, ZERO)),
            }
            for band in self.bands
        }

    def _replace_grid(self, anchor: D) -> None:
        super()._replace_grid(anchor)
        self._manager_lane_ownership = self._build_lane_ownership()

    def _manager_lane_budget(self, lane: str) -> D:
        ownership = self._manager_lane_ownership.get(lane, {})
        return D(ownership.get("initial_usdt", "0")) + self._manager_lane_profit.get(lane, ZERO)

    def _manager_lane_can_fund(self, lane: str, side: str, price: D) -> bool:
        if side == "BUY":
            return self._manager_lane_budget(lane) >= price
        return self._manager_s_free.get(lane, {}).get("quantity", ZERO) >= ONE

    def initialize_endowment(self, first_bid: D, *, time_us: int | None = None) -> None:
        super().initialize_endowment(first_bid, time_us=time_us)
        basis = _dec(first_bid)
        self._manager_s_free = {
            band.band_id: {"quantity": ONE, "cost": basis}
            for band in self.bands
            if band.band_id.startswith("S")
        }

    def _reserve_lot(self, band_id: str, quantity: D) -> list[tuple[str, D]]:
        lane = self._manager_reservation_lane
        if not band_id.startswith("S") or lane != band_id:
            return super()._reserve_lot(band_id, quantity)
        mirror = self._manager_s_free.get(band_id)
        if mirror is None or mirror["quantity"] < quantity:
            return []
        if quantity != ONE:
            return []
        basis = mirror["cost"] / mirror["quantity"]
        remaining = quantity
        allocated_cost = ZERO
        rebuilt: deque[tuple[D, D]] = deque()
        for layer_quantity, layer_basis in self._endowment_layers:
            amount = ZERO
            if remaining > ZERO and layer_basis == basis:
                amount = min(remaining, layer_quantity)
                allocated_cost += amount * layer_basis
                remaining -= amount
                layer_quantity -= amount
            if layer_quantity > ZERO:
                rebuilt.append((layer_quantity, layer_basis))
        if remaining > ZERO:
            raise ValueError("M022_S_LANE_BASIS_LAYER_MISSING")
        self._endowment_layers = rebuilt
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
            unit_basis=basis,
            remaining_cost=allocated_cost,
            entry_us=self._last_logical_us,
            origin="ENDOWMENT_SELL_BUY",
            reserved=quantity,
            source_order_id=None,
        )
        self._next_lot_id += 1
        self.lots.append(lot)
        mirror["quantity"] -= quantity
        mirror["cost"] -= allocated_cost
        return [(lot.lot_id, quantity)]

    def _release(self, order: ZonalOrder) -> None:
        mirror_release: list[tuple[D, D]] = []
        if order.side == "SELL" and order.band_id.startswith("S"):
            for lot_id, amount in order.reserved_lots:
                lot = next((item for item in self.lots if item.lot_id == lot_id), None)
                if lot is not None and lot.origin == "ENDOWMENT_SELL_BUY":
                    mirror_release.append((amount, lot.unit_basis))
        super()._release(order)
        mirror = self._manager_s_free.get(order.band_id)
        if mirror is not None:
            for amount, basis in mirror_release:
                mirror["quantity"] += amount
                mirror["cost"] += amount * basis

    @property
    def manager_lattice(self) -> tuple[D, ...]:
        return tuple(
            sorted(
                {band.buy_price for band in self.bands if band.band_id.startswith("B")}
                | {band.sell_price for band in self.bands if band.band_id.startswith("S")}
            )
        )

    def _manager_active(self) -> list[ZonalOrder]:
        return list(self.active_orders)

    def _manager_owned_returns(self) -> list[tuple[str, str, D, D]]:
        desired: list[tuple[str, str, D, D]] = []
        for band in self.bands:
            state = self._band_state[band.band_id]
            lots = self._lots_for_band(band.band_id)
            if band.band_id.startswith("B"):
                if (
                    state == "USDC_INVENTORY"
                    and lots
                ):
                    claim = self._manager_claims.get(band.band_id)
                    if claim is not None and claim[0] == "SELL":
                        price = claim[1]
                        if price > max(lot.unit_basis for lot in lots):
                            desired.append(("SELL", band.band_id, price, ONE))
            elif state == "READY_FOR_BUY" and self._sell_proceeds[band.band_id] > ZERO:
                quantity = self._sell_quantity[band.band_id]
                claim = self._manager_claims.get(band.band_id)
                if (
                    claim is not None
                    and claim[0] == "BUY"
                    and claim[1] * quantity < self._sell_proceeds[band.band_id]
                ):
                    desired.append(("BUY", band.band_id, claim[1], quantity))
        return desired

    def _manager_free_lanes(self, side: str) -> list[str]:
        prefix = "B" if side == "BUY" else "S"
        occupied = {order.band_id for order in self.active_orders}
        result = []
        for band in self.bands:
            if not band.band_id.startswith(prefix) or band.band_id in occupied:
                continue
            if (
                self._band_state[band.band_id] == "READY_FOR_BUY"
                and not self._lots_for_band(band.band_id)
                and self._sell_proceeds[band.band_id] == ZERO
            ):
                result.append(band.band_id)
        return result

    def _manager_order_crosses(self, side: str, price: D, other: ZonalOrder) -> bool:
        return (side == "BUY" and other.side == "SELL" and price >= other.price) or (
            side == "SELL" and other.side == "BUY" and price <= other.price
        )

    @staticmethod
    def _manager_prices_cross(side: str, price: D, other_side: str, other_price: D) -> bool:
        return (side == "BUY" and other_side == "SELL" and price >= other_price) or (
            side == "SELL" and other_side == "BUY" and price <= other_price
        )

    def _manager_cancel_free(
        self,
        order: ZonalOrder,
        now: int,
        *,
        for_return: bool,
        return_side: str | None = None,
        return_price: D | None = None,
        return_lane: str | None = None,
    ) -> bool:
        if order.role != "ENTRY" or order.filled != ZERO:
            return False
        if order.status not in {"PENDING", "ACTIVE"}:
            return False
        self.cancel(order.order_id, time_us=now)
        if order.status == "CANCEL_PENDING":
            self._manager_repost_lanes.add(order.band_id)
            cancel_kind = "RETURN" if for_return else "FLOAT"
            self._manager_repost_reasons[order.band_id] = cancel_kind
            self._record(
                f"FREE_ORDER_CANCELED_FOR_{cancel_kind}",
                now,
                order_id=order.order_id,
                band_id=order.band_id,
                side=order.side,
                price=_s(order.price),
            )
            if for_return:
                self._manager_return_preemptions += 1
                self._manager_free_canceled_return += 1
                self._manager_blocked_free += 1
                self._record(
                    "RETURN_PREEMPTION",
                    now,
                    free_order_id=order.order_id,
                    return_lane=return_lane,
                    return_side=return_side,
                    return_price=None if return_price is None else _s(return_price),
                    reason="FREE_ENTRY_CONFLICT",
                )
            else:
                self._manager_free_canceled_float += 1
            return True
        return False

    def _manager_return_plan(
        self,
        desired: list[tuple[str, str, D, D]],
        now: int,
    ) -> tuple[list[tuple[str, str, D, D]], set[tuple[str, str]]]:
        active = self._manager_active()
        accepted: list[tuple[str, str, D, D]] = []
        blocked: set[tuple[str, str]] = set()
        ordered = sorted(
            desired,
            key=lambda row: (
                self._manager_claim_times.get(row[1], self.start_us),
                next(
                    (
                        order.activation_evaluated_us
                        if order.activation_evaluated_us is not None
                        else order.active_us
                        for order in self.orders
                        if order.order_id == self._manager_claim_source_order_ids.get(row[1])
                    ),
                    self.start_us,
                ),
                row[1],
                self._manager_claim_source_order_ids.get(row[1], -1),
            ),
        )
        for side, lane, price, quantity in ordered:
            key = (side, lane)
            free_conflicts = [
                order
                for order in active
                if order.band_id != lane
                and self._manager_order_crosses(side, price, order)
                and order.side != side
                and order.role == "ENTRY"
                and order.filled == ZERO
            ]
            owned_conflicts = [
                order
                for order in active
                if order.band_id != lane
                and self._manager_order_crosses(side, price, order)
                and order.side != side
                and order.role == "EXIT"
            ]
            for conflict in sorted(free_conflicts, key=lambda order: order.order_id):
                self._manager_cancel_free(
                    conflict,
                    now,
                    for_return=True,
                    return_side=side,
                    return_price=price,
                    return_lane=lane,
                )
            if owned_conflicts:
                conflict = owned_conflicts[0]
                if self._manager_prices_cross(side, price, conflict.side, conflict.price):
                    self._manager_blocked_owned += 1
                    self._record(
                        "OWNED_RETURN_CONFLICT",
                        now,
                        return_lane=lane,
                        return_side=side,
                        return_price=_s(price),
                        blocking_order_id=(
                            None if conflict.order_id == -1 else conflict.order_id
                        ),
                    )
                    blocked.add(key)
                continue
            if free_conflicts:
                blocked.add(key)
                continue
            accepted_conflicts = [
                row
                for row in accepted
                if self._manager_prices_cross(side, price, row[0], row[2])
            ]
            if accepted_conflicts:
                self._manager_blocked_owned += 1
                blocking = accepted_conflicts[0]
                self._record(
                    "OWNED_RETURN_CONFLICT",
                    now,
                    return_lane=lane,
                    return_side=side,
                    return_price=_s(price),
                    blocking_order_id=None,
                    blocking_lane=blocking[1],
                    blocking_side=blocking[0],
                    blocking_price=_s(blocking[2]),
                )
                blocked.add(key)
                continue
            accepted.append((side, lane, price, quantity))
        return accepted, blocked

    def _manager_free_plan(
        self,
        mid: D,
        return_count: int,
        return_keys: set[tuple[str, str]],
    ) -> list[tuple[str, str, D, D]]:
        capacity = max(0, self.MAX_OPEN_ORDERS - return_count)
        buy_target = min(self.TARGET_FREE_PER_SIDE, (capacity + 1) // 2)
        sell_target = min(self.TARGET_FREE_PER_SIDE, capacity - buy_target)
        claims = tuple(self._manager_claims.values())
        buys = [
            price
            for price in self.manager_lattice
            if price < mid
            and not any(
                side == "SELL" and price >= claim_price
                for side, claim_price in claims
            )
        ]
        sells = [
            price
            for price in self.manager_lattice
            if price > mid
            and not any(
                side == "BUY" and price <= claim_price
                for side, claim_price in claims
            )
        ]
        buys.sort(reverse=True)
        sells.sort()
        result: list[tuple[str, str, D, D]] = []
        active = self._manager_active()
        for side, prices, target in (("BUY", buys, buy_target), ("SELL", sells, sell_target)):
            free_orders = [
                order
                for order in active
                if order.role == "ENTRY" and order.filled == ZERO and order.side == side
            ]
            target_prices = set(prices[:target])
            keep = sorted(
                (
                    order
                    for order in free_orders
                    if order.price in target_prices
                    and (
                        side == "SELL"
                        or self._manager_lane_can_fund(order.band_id, side, order.price)
                    )
                ),
                key=lambda order: (abs(order.price - mid), order.active_us, order.order_id),
            )[:target]
            used_prices = {order.price for order in keep}
            used_lanes = {order.band_id for order in keep}
            result.extend((side, order.band_id, order.price, ONE) for order in keep)
            available_lanes = [
                lane for lane in self._manager_free_lanes(side) if lane not in used_lanes
            ]
            for price in prices[:target]:
                if len(keep) >= target or price in used_prices:
                    continue
                lane = next(
                    (
                        candidate
                        for candidate in available_lanes
                        if self._manager_lane_can_fund(candidate, side, price)
                    ),
                    None,
                )
                if lane is None:
                    continue
                available_lanes.remove(lane)
                result.append((side, lane, price, ONE))
                used_prices.add(price)
                keep.append(
                    ZonalOrder(
                        -1,
                        lane,
                        side,
                        price,
                        ONE,
                        ONE,
                        self._last_logical_us,
                        self._last_logical_us,
                    )
                )
        return result

    def _manager_sample(self, now: int) -> None:
        self._manager_integrate_to(now)
        self._manager_capture_snapshot(now)

    def _manager_parked_free_count(self) -> int:
        occupied = {order.band_id for order in self._manager_active()}
        return sum(
            self._band_state[band.band_id] == "READY_FOR_BUY"
            and not self._lots_for_band(band.band_id)
            and self._sell_proceeds[band.band_id] == ZERO
            and band.band_id not in occupied
            for band in self.bands
        )

    def _manager_integrate_to(self, now: int) -> None:
        """Integrate the state held during the preceding causal interval."""
        if self._manager_last_sample_us is None or self._manager_snapshot_mid is None:
            return
        elapsed = max(0, now - self._manager_last_sample_us)
        if not elapsed:
            return
        open_count = self._manager_snapshot_open_count
        self._manager_observation_us += elapsed
        self._manager_weighted_active += D(open_count) * elapsed
        self._manager_weighted_parked += (
            D(self._manager_snapshot_parked_free_count) * elapsed
        )
        active_prices = self._manager_snapshot_active_prices
        self._manager_active_order_time += D(len(active_prices)) * elapsed
        distances = [
            abs(price - self._manager_snapshot_mid) / M021_TICK_SIZE
            for price in active_prices
        ]
        self._manager_weighted_distance += sum(distances, ZERO) * elapsed
        self._manager_within5 += D(sum(distance <= D("5") for distance in distances)) * elapsed
        self._manager_within10 += D(
            sum(distance <= D("10") for distance in distances)
        ) * elapsed
        if self._manager_warmup_started:
            self._manager_min_active_after_warmup = (
                open_count
                if self._manager_min_active_after_warmup is None
                else min(self._manager_min_active_after_warmup, open_count)
            )
        self._manager_last_sample_us = now

    def _manager_capture_snapshot(self, now: int) -> None:
        if self._last_book is None:
            return
        mid = (self._last_book["bids"][0][0] + self._last_book["asks"][0][0]) / D("2")
        open_orders = self._manager_active()
        active = [
            order
            for order in open_orders
            if order.status == "ACTIVE"
            or (order.status == "CANCEL_PENDING" and order.activation_evaluated_us is not None)
        ]
        self._manager_snapshot_mid = mid
        self._manager_snapshot_prices = tuple(order.price for order in active)
        self._manager_snapshot_active_count = len(open_orders)
        self._manager_snapshot_open_count = len(open_orders)
        self._manager_snapshot_active_prices = tuple(order.price for order in active)
        self._manager_snapshot_parked_free_count = self._manager_parked_free_count()
        if any(order.activation_evaluated_us is not None for order in active):
            self._manager_warmup_started = True
        if self._manager_warmup_started:
            self._manager_min_active_after_warmup = (
                self._manager_snapshot_open_count
                if self._manager_min_active_after_warmup is None
                else min(
                    self._manager_min_active_after_warmup,
                    self._manager_snapshot_open_count,
                )
            )
        self._manager_last_sample_us = now

    @staticmethod
    def _event_logical(event: Any, capture_time_us: int | None, *, trade: bool) -> int:
        if capture_time_us is not None:
            return int(capture_time_us)
        key = "time_us" if trade else "capture_time_us"
        if isinstance(event, dict):
            return int(event.get(key, event.get("exchange_time_us", 0)))
        return int(getattr(event, key, getattr(event, "exchange_time_us", 0)))

    def receive_book(self, book: Any, *, capture_time_us: int | None = None) -> None:
        logical = self._event_logical(book, capture_time_us, trade=False)
        self._check_time(logical)
        self._manager_integrate_to(logical)
        super().receive_book(book, capture_time_us=capture_time_us)

    def receive_trade(self, trade: Any, *, capture_time_us: int | None = None) -> D:
        logical = self._event_logical(trade, capture_time_us, trade=True)
        self._check_time(logical)
        trade_id = str(trade["trade_id"] if isinstance(trade, dict) else trade.trade_id)
        if trade_id not in self.processed_trades:
            self._manager_integrate_to(logical)
        return super().receive_trade(trade, capture_time_us=capture_time_us)

    def _advance(self, now: int) -> None:
        cancel_pending = {
            order.order_id
            for order in self.active_orders
            if order.status == "CANCEL_PENDING"
        }
        activated_before = {
            order.order_id
            for order in self.orders
            if order.activation_evaluated_us is not None
        }
        super()._advance(now)
        for order in self.orders:
            if (
                order.role == "EXIT"
                and order.activation_evaluated_us is not None
                and order.order_id not in activated_before
                and order.order_id in self._manager_return_order_claim_tokens
            ):
                token = self._manager_return_order_claim_tokens[order.order_id]
                if token not in self._manager_return_activation_claims:
                    self._manager_return_activation_claims.add(token)
                    wait_us = max(0, now - token[1])
                    self._manager_return_activation_wait_us.append(wait_us)
                    self._record(
                        "RETURN_ACTIVATED",
                        now,
                        lane=order.band_id,
                        order_id=order.order_id,
                        claim_time_us=token[1],
                        wait_us=wait_us,
                    )
            if (
                order.order_id in cancel_pending
                and order.status == "CANCELED"
                and order.filled > ZERO
                and order.order_id not in self._manager_partial_residual_order_ids
            ):
                self._manager_partial_residual_order_ids.add(order.order_id)
                self._record(
                    "PARTIAL_RESIDUAL_BLOCKED",
                    now,
                    order_id=order.order_id,
                    band_id=order.band_id,
                    side=order.side,
                    filled=_s(order.filled),
                    residual_quantity=_s(order.remaining),
                    reason="BELOW_HISTORICAL_STEP_AFTER_CANCEL_ACK",
                )

    def _reconcile(self, logical: int) -> None:
        if self._last_book is None or not self._endowed:
            return
        mid = (self._last_book["bids"][0][0] + self._last_book["asks"][0][0]) / D("2")
        owned = self._manager_owned_returns()
        accepted_returns, blocked_returns = self._manager_return_plan(owned, logical)
        return_keys = {(side, lane) for side, lane, _, _ in accepted_returns}
        return_keys.update(blocked_returns)
        free = self._manager_free_plan(mid, len(accepted_returns), return_keys)
        desired = accepted_returns + free
        desired_exact = {(side, lane, price) for side, lane, price, _ in desired}
        for order in self.active_orders:
            if order.role != "ENTRY" or order.filled != ZERO:
                continue
            if (order.side, order.band_id, order.price) not in desired_exact:
                self._manager_cancel_free(
                    order,
                    logical,
                    for_return=(order.band_id in {lane for _, lane, _, _ in accepted_returns}),
                )
        existing = {(order.side, order.band_id, order.price): order for order in self.active_orders}
        occupied = {order.band_id for order in self.active_orders}
        for side, lane, price, quantity in desired:
            if (side, lane, price) in existing or lane in occupied:
                continue
            if len(self.active_orders) >= self.MAX_OPEN_ORDERS:
                self._manager_reconcile_cap_blocks += 1
                continue
            self._submit(side, lane, price, quantity, logical)
            if self.orders and self.orders[-1].band_id == lane and self.orders[-1].price == price:
                occupied.add(lane)
        self._window_shortage_events += int(len(self.active_orders) < self.MAX_OPEN_ORDERS)
        self.validate_invariants()
        self._manager_capture_snapshot(logical)

    def _submit(self, side: str, band_id: str, price: D, quantity: D, now: int) -> None:
        if len(self.active_orders) >= self.MAX_OPEN_ORDERS:
            self._manager_reconcile_cap_blocks += 1
            return
        before = len(self.orders)
        self._manager_reservation_lane = band_id if side == "SELL" else None
        try:
            super()._submit(side, band_id, price, quantity, now)
        finally:
            self._manager_reservation_lane = None
        if len(self.orders) == before:
            return
        order = self.orders[-1]
        if order.role == "EXIT":
            self._manager_return_submissions += 1
            self._manager_return_order_ids.add(order.order_id)
            claim = self._manager_claims.get(band_id)
            claim_time = self._manager_claim_times.get(band_id)
            source_order_id = self._manager_claim_source_order_ids.get(band_id, -1)
            claim_token = (
                band_id,
                claim_time if claim_time is not None else now,
                source_order_id,
            )
            self._manager_return_order_claim_tokens[order.order_id] = claim_token
            if claim_token not in self._manager_return_submission_claims:
                self._manager_return_submission_claims.add(claim_token)
                wait_us = max(0, now - claim_token[1])
                self._manager_return_submission_wait_us.append(wait_us)
            else:
                wait_us = None
            self._record(
                "RETURN_SUBMISSION",
                now,
                lane=band_id,
                order_id=order.order_id,
                side=side,
                price=_s(price),
                claim_side=None if claim is None else claim[0],
                claim_price=None if claim is None else _s(claim[1]),
                claim_time_us=claim_time,
                wait_us=wait_us,
            )
        elif band_id in self._manager_repost_lanes:
            self._manager_free_reposted += 1
            self._manager_repost_lanes.discard(band_id)
            self._record(
                "FREE_ORDER_REPOSTED",
                now,
                order_id=order.order_id,
                band_id=band_id,
                side=side,
                price=_s(price),
                reason=self._manager_repost_reasons.pop(band_id, "UNKNOWN"),
            )

    def validate_invariants(self) -> None:
        super().validate_invariants()
        for order in self.active_orders:
            if (
                order.role == "ENTRY"
                and order.filled == ZERO
                and order.side == "BUY"
                and order.price > self._manager_lane_budget(order.band_id)
            ):
                raise ValueError("M022_LANE_BUY_BUDGET_DRIFT")
        for lane, ownership in self._manager_lane_ownership.items():
            if lane.startswith("S") and D(ownership.get("initial_usdc", "0")) != ONE:
                raise ValueError("M022_S_LANE_OWNERSHIP_DRIFT")
        mirror_quantity = sum(
            (value["quantity"] for value in self._manager_s_free.values()), ZERO
        )
        mirror_cost = sum((value["cost"] for value in self._manager_s_free.values()), ZERO)
        if mirror_quantity != self.endowment_free_quantity:
            raise ValueError("M022_S_FREE_QUANTITY_DRIFT")
        if mirror_cost != self.endowment_cost:
            raise ValueError("M022_S_FREE_COST_DRIFT")

    def _fill(self, order: ZonalOrder, quantity: D, time_us: int, *, source_id: str) -> D:
        before_audit = len(self.audit)
        filled = super()._fill(order, quantity, time_us, source_id=source_id)
        if filled <= ZERO:
            return filled
        if (
            order.role == "ENTRY"
            and order.filled > ZERO
            and order.band_id not in self._manager_claims
        ):
            return_side = "SELL" if order.side == "BUY" else "BUY"
            return_price = (
                order.price + M021_TICK_SIZE
                if order.side == "BUY"
                else order.price - M021_TICK_SIZE
            )
            self._manager_claims[order.band_id] = (return_side, return_price)
            self._manager_claim_times[order.band_id] = time_us
            self._manager_claim_source_order_ids[order.band_id] = order.order_id
            self._record(
                "RETURN_PRICE_CLAIM",
                time_us,
                lane=order.band_id,
                source_order_id=order.order_id,
                return_side=return_side,
                return_price=_s(return_price),
                quantity=_s(filled),
            )
        if order.role == "EXIT":
            self._manager_return_fills += 1
            claim = self._manager_claims.get(order.band_id)
            self._record(
                "RETURN_FILL",
                time_us,
                lane=order.band_id,
                order_id=order.order_id,
                side=order.side,
                quantity=_s(filled),
                price=_s(order.price),
                claim_side=None if claim is None else claim[0],
                claim_price=None if claim is None else _s(claim[1]),
                claim_time_us=self._manager_claim_times.get(order.band_id),
                complete=order.status == "FILLED",
            )
            claim_time = self._manager_claim_times.get(order.band_id, time_us)
            if (
                order.status == "FILLED"
                and order.order_id not in self._manager_return_completed_order_ids
            ):
                self._manager_return_completed_order_ids.add(order.order_id)
                self._manager_return_wait_us.append(max(0, time_us - claim_time))
        for row in self.audit[before_audit:]:
            if row.get("event") == "CYCLE":
                lane = row["band_id"]
                self._manager_lane_profit[lane] += D(row["profit"])
                self._manager_lane_cycles[lane] += 1
                cycle_order = next(
                    (
                        item
                        for item in self.orders
                        if item.order_id
                        == int(
                            row.get("entry_sell_order_id", row.get("source_order_id", -1))
                        )
                    ),
                    None,
                )
                if cycle_order is not None:
                    self._manager_cycle_prices.append(cycle_order.price)
                if (
                    cycle_order is not None
                    and lane.startswith("S")
                    and row.get("direction") == "SELL_BUY"
                ):
                    quantity = D(row["quantity"])
                    mirror = self._manager_s_free[lane]
                    mirror["quantity"] += quantity
                    mirror["cost"] += quantity * order.price
                self._manager_claims.pop(lane, None)
                self._manager_claim_times.pop(lane, None)
                self._manager_claim_source_order_ids.pop(lane, None)
        return filled

    @staticmethod
    def _manager_wait_stats(values: list[int]) -> tuple[D | None, D | None, int | None]:
        if not values:
            return None, None, None
        ordered = sorted(values)
        count = len(ordered)
        mean = D(sum(ordered)) / D(count)
        if count % 2:
            median = D(ordered[count // 2])
        else:
            median = D(ordered[count // 2 - 1] + ordered[count // 2]) / D("2")
        p95 = ordered[(count * 95 + 99) // 100 - 1]
        return mean, median, p95

    def metrics(self) -> dict[str, Any]:
        result = super().metrics()
        observation = D(self._manager_observation_us)
        mean_wait, median_wait, p95_wait = self._manager_wait_stats(
            self._manager_return_wait_us
        )
        submission_stats = self._manager_wait_stats(self._manager_return_submission_wait_us)
        activation_stats = self._manager_wait_stats(self._manager_return_activation_wait_us)
        unique_lanes = {order.band_id for order in self.orders}
        now = self._manager_last_sample_us or self._last_logical_us
        censored_ages = sorted(
            max(0, now - claim_time) for claim_time in self._manager_claim_times.values()
        )
        productive = {lane for lane, count in self._manager_lane_cycles.items() if count > 0}
        prices = {_s(order.price) for order in self.orders}
        result.update(
            {
                "model": "M022",
                "order_notional_mode": "NORMALIZED_1_USDC_NON_EXECUTABLE_ORDER_MANAGER_PROBE",
                "max_open_orders": self.MAX_OPEN_ORDERS,
                "return_preemptions": self._manager_return_preemptions,
                "free_orders_canceled_for_return": self._manager_free_canceled_return,
                "free_orders_canceled_for_float": self._manager_free_canceled_float,
                "free_orders_reposted": self._manager_free_reposted,
                "return_submissions": self._manager_return_submissions,
                "return_fills": self._manager_return_fills,
                "return_wait_time_mean": mean_wait,
                "return_wait_time_median": median_wait,
                "return_wait_time_p95": p95_wait,
                "return_completion_wait_time_mean_us": mean_wait,
                "return_completion_wait_time_median_us": median_wait,
                "return_completion_wait_time_p95_us": p95_wait,
                "return_submission_wait_time_mean_us": submission_stats[0],
                "return_submission_wait_time_median_us": submission_stats[1],
                "return_submission_wait_time_p95_us": submission_stats[2],
                "return_activation_wait_time_mean_us": activation_stats[0],
                "return_activation_wait_time_median_us": activation_stats[1],
                "return_activation_wait_time_p95_us": activation_stats[2],
                "censored_return_claim_count": len(censored_ages),
                "censored_return_claim_max_age_us": (
                    censored_ages[-1] if censored_ages else None
                ),
                "return_blocked_by_free_order_count": self._manager_free_canceled_return,
                "return_blocked_by_owned_return_count": self._manager_blocked_owned,
                "return_blocked_free_count": self._manager_blocked_free,
                "manager_blocked_free": self._manager_blocked_free,
                "active_order_time_us": _s(self._manager_active_order_time),
                "partial_residual_blocked_count": len(
                    self._manager_partial_residual_order_ids
                ),
                "partial_residual_blocked_order_ids": sorted(
                    self._manager_partial_residual_order_ids
                ),
                "self_cross_rechecks": sum(
                    row.get("event") == "SELF_CROSS_BLOCKED" for row in self.audit
                ),
                "post_only_rejections": sum(
                    row.get("event") == "REJECTED_POST_ONLY" for row in self.audit
                ),
                "mean_active_open_orders": (
                    None if observation == ZERO else _s(self._manager_weighted_active / observation)
                ),
                "min_active_open_orders_after_warmup": self._manager_min_active_after_warmup,
                "parked_lanes_mean": (
                    None if observation == ZERO else _s(self._manager_weighted_parked / observation)
                ),
                "unique_lanes_used": len(unique_lanes),
                "unique_price_levels_used": len(prices),
                "unique_productive_lanes": len(productive),
                "percent_active_orders_within_5_ticks_of_mid": (
                    None
                    if self._manager_active_order_time == ZERO
                    else _s(
                        self._manager_within5
                        / self._manager_active_order_time
                        * D("100")
                    )
                ),
                "percent_active_orders_within_10_ticks_of_mid": (
                    None
                    if self._manager_active_order_time == ZERO
                    else _s(
                        self._manager_within10
                        / self._manager_active_order_time
                        * D("100")
                    )
                ),
                "time_weighted_distance_from_mid": (
                    None
                    if self._manager_active_order_time == ZERO
                    else _s(self._manager_weighted_distance / self._manager_active_order_time)
                ),
                "lane_profit": {
                    lane: _s(value) for lane, value in self._manager_lane_profit.items()
                },
                "lane_cycles": dict(self._manager_lane_cycles),
                "lane_ownership": {
                    lane: {
                        **ownership,
                        "profit": _s(self._manager_lane_profit.get(lane, ZERO)),
                        **(
                            {
                                "free_usdc": _s(self._manager_s_free[lane]["quantity"]),
                                "free_usdc_cost": _s(self._manager_s_free[lane]["cost"]),
                            }
                            if lane in self._manager_s_free
                            else {}
                        ),
                    }
                    for lane, ownership in self._manager_lane_ownership.items()
                },
                "return_claims": {
                    lane: {"side": side, "price": _s(price)}
                    for lane, (side, price) in self._manager_claims.items()
                },
                "return_blocked_cap_events": self._manager_reconcile_cap_blocks,
                "top_10_lanes_by_cycles": sorted(
                    self._manager_lane_cycles.items(), key=lambda item: (-item[1], item[0])
                )[:10],
                "top_10_price_levels_by_cycles": [
                    {"price": _s(price), "cycles": count}
                    for price, count in sorted(
                        Counter(self._manager_cycle_prices).items(),
                        key=lambda item: (-item[1], item[0]),
                    )[:10]
                ],
            }
        )
        for key in (
            "return_preemptions",
            "free_orders_canceled_for_return",
            "free_orders_canceled_for_float",
            "free_orders_reposted",
            "return_submissions",
            "return_fills",
            "return_wait_time_mean",
            "return_wait_time_median",
            "return_wait_time_p95",
            "return_blocked_by_free_order_count",
            "return_blocked_by_owned_return_count",
            "return_blocked_free_count",
            "manager_blocked_free",
        ):
            result[key.upper()] = result[key]
        for key in (
            "self_cross_rechecks",
            "post_only_rejections",
            "queue_blocked_events",
            "max_simultaneous_open_orders",
            "mean_active_open_orders",
            "min_active_open_orders_after_warmup",
            "parked_lanes_mean",
            "unique_lanes_used",
            "unique_price_levels_used",
            "unique_productive_lanes",
            "time_weighted_distance_from_mid",
        ):
            result[key.upper()] = result[key]
        return result

    def finish(self, *, time_us: int) -> dict[str, Any]:
        if time_us != self.end_us:
            self._check_time(time_us)
        self._manager_integrate_to(time_us)
        return super().finish(time_us=time_us)

    def _state(self) -> dict[str, Any]:
        state = super()._state()
        state.update(
            {
                "manager_claims": {
                    lane: {"side": side, "price": _s(price)}
                    for lane, (side, price) in self._manager_claims.items()
                },
                "manager_claim_times": dict(self._manager_claim_times),
                "manager_claim_source_order_ids": dict(self._manager_claim_source_order_ids),
                "manager_lane_profit": {
                    lane: _s(value) for lane, value in self._manager_lane_profit.items()
                },
                "manager_lane_cycles": dict(self._manager_lane_cycles),
                "manager_cycle_prices": [_s(price) for price in self._manager_cycle_prices],
                "manager_lane_ownership": self._manager_lane_ownership,
                "manager_s_free": {
                    lane: {key: _s(value) for key, value in mirror.items()}
                    for lane, mirror in self._manager_s_free.items()
                },
                "manager_return_preemptions": self._manager_return_preemptions,
                "manager_free_canceled_return": self._manager_free_canceled_return,
                "manager_free_canceled_float": self._manager_free_canceled_float,
                "manager_free_reposted": self._manager_free_reposted,
                "manager_return_submissions": self._manager_return_submissions,
                "manager_return_fills": self._manager_return_fills,
                "manager_return_wait_us": list(self._manager_return_wait_us),
                "manager_return_submission_wait_us": list(
                    self._manager_return_submission_wait_us
                ),
                "manager_return_activation_wait_us": list(
                    self._manager_return_activation_wait_us
                ),
                "manager_return_submission_claims": [
                    list(token) for token in sorted(self._manager_return_submission_claims)
                ],
                "manager_return_activation_claims": [
                    list(token) for token in sorted(self._manager_return_activation_claims)
                ],
                "manager_return_order_claim_tokens": {
                    str(order_id): list(token)
                    for order_id, token in self._manager_return_order_claim_tokens.items()
                },
                "manager_return_completed_order_ids": sorted(
                    self._manager_return_completed_order_ids
                ),
                "manager_partial_residual_order_ids": sorted(
                    self._manager_partial_residual_order_ids
                ),
                "manager_blocked_free": self._manager_blocked_free,
                "manager_blocked_owned": self._manager_blocked_owned,
                "manager_reconcile_cap_blocks": self._manager_reconcile_cap_blocks,
                "manager_last_sample_us": self._manager_last_sample_us,
                "manager_observation_us": self._manager_observation_us,
                "manager_weighted_active": _s(self._manager_weighted_active),
                "manager_weighted_parked": _s(self._manager_weighted_parked),
                "manager_weighted_distance": _s(self._manager_weighted_distance),
                "manager_within5": _s(self._manager_within5),
                "manager_within10": _s(self._manager_within10),
                "manager_min_active_after_warmup": self._manager_min_active_after_warmup,
                "manager_repost_lanes": sorted(self._manager_repost_lanes),
                "manager_repost_reasons": dict(self._manager_repost_reasons),
                "manager_return_order_ids": sorted(self._manager_return_order_ids),
                "manager_active_order_time": _s(self._manager_active_order_time),
                "manager_snapshot_mid": (
                    None if self._manager_snapshot_mid is None else _s(self._manager_snapshot_mid)
                ),
                "manager_snapshot_prices": [_s(price) for price in self._manager_snapshot_prices],
                "manager_snapshot_active_count": self._manager_snapshot_active_count,
                "manager_snapshot_open_count": self._manager_snapshot_open_count,
                "manager_snapshot_active_prices": [
                    _s(price) for price in self._manager_snapshot_active_prices
                ],
                "manager_snapshot_parked_free_count": self._manager_snapshot_parked_free_count,
                "manager_warmup_started": self._manager_warmup_started,
            }
        )
        return state

    def checkpoint(self) -> dict[str, Any]:
        state = self._state()
        return {
            "schema": "M022_MANAGED_DENSE_PING_PONG_V1",
            "state": state,
            "sha256": canonical_hash(state),
        }

    def restore(self, checkpoint: dict[str, Any]) -> None:
        if checkpoint.get("schema") != "M022_MANAGED_DENSE_PING_PONG_V1":
            raise ValueError("INVALID_M022_CHECKPOINT")
        state = checkpoint.get("state")
        if not isinstance(state, dict) or checkpoint.get("sha256") != canonical_hash(state):
            raise ValueError("M022_CHECKPOINT_HASH_MISMATCH")
        super().restore(
            {"schema": "M021_DENSE_PING_PONG_V1", "state": state, "sha256": checkpoint["sha256"]}
        )
        self._manager_claims = {
            lane: (value["side"], D(value["price"]))
            for lane, value in state.get("manager_claims", {}).items()
        }
        self._manager_claim_times = {
            lane: int(value) for lane, value in state.get("manager_claim_times", {}).items()
        }
        self._manager_claim_source_order_ids = {
            lane: int(value)
            for lane, value in state.get("manager_claim_source_order_ids", {}).items()
        }
        self._manager_lane_profit = {
            lane: D(value) for lane, value in state.get("manager_lane_profit", {}).items()
        }
        self._manager_lane_cycles = {
            lane: int(value) for lane, value in state.get("manager_lane_cycles", {}).items()
        }
        self._manager_cycle_prices = [
            D(value) for value in state.get("manager_cycle_prices", [])
        ]
        self._manager_lane_ownership = {
            lane: dict(value)
            for lane, value in state.get(
                "manager_lane_ownership", self._build_lane_ownership()
            ).items()
        }
        raw_s_free = state.get("manager_s_free")
        if raw_s_free is not None:
            self._manager_s_free = {
                lane: {key: D(value) for key, value in mirror.items()}
                for lane, mirror in raw_s_free.items()
            }
        self._manager_return_preemptions = int(state.get("manager_return_preemptions", 0))
        self._manager_free_canceled_return = int(state.get("manager_free_canceled_return", 0))
        self._manager_free_canceled_float = int(state.get("manager_free_canceled_float", 0))
        self._manager_free_reposted = int(state.get("manager_free_reposted", 0))
        self._manager_return_submissions = int(state.get("manager_return_submissions", 0))
        self._manager_return_fills = int(state.get("manager_return_fills", 0))
        self._manager_return_wait_us = [
            int(value) for value in state.get("manager_return_wait_us", [])
        ]
        self._manager_return_submission_wait_us = [
            int(value) for value in state.get("manager_return_submission_wait_us", [])
        ]
        self._manager_return_activation_wait_us = [
            int(value) for value in state.get("manager_return_activation_wait_us", [])
        ]
        self._manager_return_submission_claims = {
            (str(token[0]), int(token[1]), int(token[2]))
            for token in state.get("manager_return_submission_claims", [])
        }
        self._manager_return_activation_claims = {
            (str(token[0]), int(token[1]), int(token[2]))
            for token in state.get("manager_return_activation_claims", [])
        }
        self._manager_return_order_claim_tokens = {
            int(order_id): (str(token[0]), int(token[1]), int(token[2]))
            for order_id, token in state.get("manager_return_order_claim_tokens", {}).items()
        }
        self._manager_return_completed_order_ids = set(
            int(value) for value in state.get("manager_return_completed_order_ids", [])
        )
        self._manager_partial_residual_order_ids = set(
            int(value) for value in state.get("manager_partial_residual_order_ids", [])
        )
        self._manager_blocked_free = int(state.get("manager_blocked_free", 0))
        self._manager_blocked_owned = int(state.get("manager_blocked_owned", 0))
        self._manager_reconcile_cap_blocks = int(state.get("manager_reconcile_cap_blocks", 0))
        self._manager_last_sample_us = state.get("manager_last_sample_us")
        self._manager_observation_us = int(state.get("manager_observation_us", 0))
        self._manager_weighted_active = D(state.get("manager_weighted_active", "0"))
        self._manager_weighted_parked = D(state.get("manager_weighted_parked", "0"))
        self._manager_weighted_distance = D(state.get("manager_weighted_distance", "0"))
        self._manager_within5 = D(state.get("manager_within5", "0"))
        self._manager_within10 = D(state.get("manager_within10", "0"))
        self._manager_min_active_after_warmup = state.get("manager_min_active_after_warmup")
        self._manager_repost_lanes = set(state.get("manager_repost_lanes", []))
        self._manager_repost_reasons = dict(state.get("manager_repost_reasons", {}))
        self._manager_return_order_ids = set(
            int(value) for value in state.get("manager_return_order_ids", [])
        )
        self._manager_active_order_time = D(state.get("manager_active_order_time", "0"))
        self._manager_snapshot_mid = (
            None
            if state.get("manager_snapshot_mid") is None
            else D(state["manager_snapshot_mid"])
        )
        self._manager_snapshot_prices = tuple(
            D(value) for value in state.get("manager_snapshot_prices", [])
        )
        self._manager_snapshot_active_count = int(
            state.get("manager_snapshot_active_count", 0)
        )
        self._manager_snapshot_open_count = int(
            state.get("manager_snapshot_open_count", self._manager_snapshot_active_count)
        )
        self._manager_snapshot_active_prices = tuple(
            D(value)
            for value in state.get(
                "manager_snapshot_active_prices",
                state.get("manager_snapshot_prices", []),
            )
        )
        self._manager_snapshot_parked_free_count = int(
            state.get("manager_snapshot_parked_free_count", 0)
        )
        self._manager_warmup_started = bool(state.get("manager_warmup_started", False))

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint: dict[str, Any],
        *,
        start_us: int | None = None,
        end_us: int | None = None,
        latency_us: int | None = None,
        cancel_latency_us: int | None = None,
    ) -> ManagedDensePingPongProbe:
        state = checkpoint.get("state", {})
        config = state.get("config", {})
        value = cls(
            start_us=config["start_us"] if start_us is None else start_us,
            end_us=config["end_us"] if end_us is None else end_us,
            latency_us=config["latency_us"] if latency_us is None else latency_us,
            cancel_latency_us=(
                config["cancel_latency_us"] if cancel_latency_us is None else cancel_latency_us
            ),
            anchor=None if state.get("dense_anchor") is None else D(state["dense_anchor"]),
            initial_capital=D(config["initial_capital"]),
        )
        value.restore(checkpoint)
        return value


__all__ = [
    "M021_BUY_SLOTS",
    "M021_SELL_SLOTS",
    "M021_TICK_SIZE",
    "MAX_BANDS",
    "MIN_ACTIVE_BUYS",
    "MIN_ACTIVE_SELLS",
    "NORMALIZED_CAPITAL",
    "NORMALIZED_ORDER_NOTIONAL",
    "VIRTUAL_STEP",
    "DensePingPongProbe",
    "ManagedDensePingPongProbe",
    "ZonalBand",
    "ZonalLot",
    "ZonalOrder",
    "ZonalPingPong",
]
