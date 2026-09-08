"""Pure, deterministic M019 adaptive stablecoin ladder mechanics.

This module is an execution kernel only.  It does not read market data, place
orders, infer missing book levels, or choose a strategy configuration.  A
runner/coordinator supplies validated book batches and trades and may use the
checkpoint representation to bind the kernel to an evidence manifest.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any

from crypto_strategy_lab.domain import canonical_hash

D = Decimal
ZERO = D("0")
ONE = D("1")
INITIAL_CAPITAL = D("100")
ENDOWMENT_NOTIONAL = D("50")
PROJECTED_USDC_CAP = D(".90")
SLOT_COUNT = 6
REFRESH_US = 60_000_000
ONE_HOUR_US = 3_600_000_000


def _floor_step(value: D, step: D) -> D:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _ceil_step(value: D, step: D) -> D:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _ceil_tick(value: D, tick: D) -> D:
    return _ceil_step(value, tick)


def _str_decimal(value: D) -> str:
    return str(value)


@dataclass
class LadderLot:
    lot_id: str
    quantity: D
    remaining: D
    unit_cost: D
    entry_us: int
    initial_endowment: bool = False
    realized_profit: D = ZERO
    sold_quantity: D = ZERO
    reserved: D = ZERO
    band_id: int = 0
    source_slot: int | None = None
    source_order_id: int | None = None
    closed_us: int | None = None


@dataclass
class LadderOrder:
    order_id: int
    slot: int
    side: str
    price: D
    quantity: D
    remaining: D
    submitted_us: int
    active_us: int
    queue: D
    reserved_quote: D = ZERO
    reserved_lots: list[tuple[str, D]] = field(default_factory=list)
    submitted_native_us: int = -1
    status: str = "PENDING"
    filled: D = ZERO
    had_partial: bool = False
    cancel_us: int | None = None
    activation_evaluated_us: int | None = None
    cycle_recorded: bool = False


def _book_levels(book: Any, name: str) -> tuple[tuple[D, D], ...]:
    return tuple((D(price), D(quantity)) for price, quantity in getattr(book, name, ()))


class AdaptiveStablecoinLadder:
    """One deterministic ladder lane.

    The lane intentionally keeps accounting separate from a replay
    coordinator.  A coordinator can ask :meth:`receive_trade` for consumed
    quantity in deterministic lane order and decrement the trade globally.
    """

    def __init__(
        self,
        profile: Any,
        rules: Any,
        *,
        lane_id: str = "lane-0",
        candidate: str = "M019",
        initial_capital: D = INITIAL_CAPITAL,
        endowment_notional: D = ENDOWMENT_NOTIONAL,
        projected_usdc_cap: D = PROJECTED_USDC_CAP,
    ) -> None:
        if not isinstance(initial_capital, D) or initial_capital <= ZERO:
            raise ValueError("INITIAL_CAPITAL_REQUIRED")
        if not isinstance(endowment_notional, D) or endowment_notional < ZERO:
            raise ValueError("INVALID_ENDOWMENT")
        if projected_usdc_cap <= ZERO or projected_usdc_cap > ONE:
            raise ValueError("INVALID_PROJECTED_USDC_CAP")
        self.profile = profile
        self.rules = rules
        self.lane_id = str(lane_id)
        self.candidate = str(candidate)
        self.initial_capital = initial_capital
        self.endowment_notional = endowment_notional
        self.projected_usdc_cap = projected_usdc_cap
        self.cash = initial_capital
        self.reserve = ZERO
        self.inventory = ZERO
        self.inventory_cost = ZERO
        self.fees = ZERO
        self.realized_sales = ZERO
        self.realized_profit = ZERO
        self.cycle_count = 0
        self.processed_trades = 0
        self.first_bid: D | None = None
        self.endowment_quantity = ZERO
        self.endowed = False
        self.last_book_us = -1
        self.last_native_book_us = -1
        self.last_native_book_upper_us = -1
        self.last_logical_us = -1
        self.last_refresh_us = -1
        self.current_bids: tuple[tuple[D, D], ...] = ()
        self.current_asks: tuple[tuple[D, D], ...] = ()
        self.known_bid_floor: D | None = None
        self.known_ask_ceiling: D | None = None
        self.orders: list[LadderOrder] = []
        self._open_orders: dict[int, LadderOrder] = {}
        self.lots: deque[LadderLot] = deque()
        self.audit: list[dict[str, Any]] = []
        self.settlements: list[dict[str, Any]] = []
        self._next_order_id = 1
        self._next_lot_id = 1
        self._submission_times: list[int] = []
        self._cancel_times: list[int] = []
        self._finished = False
        self._finished_us: int | None = None
        self._current_native_us = -1

    @property
    def tick_size(self) -> D:
        return D(self.rules.tick_size)

    @property
    def step_size(self) -> D:
        return D(self.rules.step_size)

    @property
    def safe_min_notional(self) -> D:
        return max(D("6"), D("1.2") * D(self.rules.min_notional))

    @property
    def active_orders(self) -> list[LadderOrder]:
        return list(self._open_orders.values())

    @property
    def active_buy_notional(self) -> D:
        return sum(
            (order.reserved_quote for order in self.active_orders if order.side == "BUY"),
            ZERO,
        )

    @property
    def reserved_sell_quantity(self) -> D:
        return sum((lot.reserved for lot in self.lots), ZERO)

    def _marked_equity(self, mark: D | None = None) -> D:
        mark = mark if mark is not None else (self._best_bid() or self.first_bid or ZERO)
        return self.cash + self.active_buy_notional + self.reserve + self.inventory * mark

    def _record(self, event: str, time_us: int, **fields: Any) -> None:
        self.audit.append({"event": event, "time_us": int(time_us), **fields})

    def _config_hash(self) -> str:
        return canonical_hash(
            {
                "profile": vars(self.profile),
                "rules": vars(self.rules),
            }
        )

    def _valid_price(self, price: D) -> bool:
        return (
            D(self.rules.min_price) <= price <= D(self.rules.max_price)
            and price % self.tick_size == ZERO
        )

    def _valid_quantity(self, price: D, quantity: D) -> bool:
        if quantity <= ZERO or quantity % self.step_size:
            return False
        if quantity < D(self.rules.min_quantity) or quantity > D(self.rules.max_quantity):
            return False
        return D(self.rules.min_notional) <= price * quantity <= D(self.rules.max_notional)

    def _rate_limit_available(self, times: list[int], now: int) -> bool:
        window = int(getattr(self.rules, "window_us", 0))
        limit = int(getattr(self.rules, "orders_per_window", 0))
        if window <= 0 or limit <= 0:
            return True
        times[:] = [value for value in times if now - value < window]
        return len(times) < limit

    def _best_bid(self) -> D | None:
        return self.current_bids[0][0] if self.current_bids else None

    def _best_ask(self) -> D | None:
        return self.current_asks[0][0] if self.current_asks else None

    def _displayed_quantity(self, side: str, price: D) -> D:
        levels = self.current_bids if side == "BUY" else self.current_asks
        for level_price, quantity in levels:
            if level_price == price:
                return quantity
        return ZERO

    def _would_self_cross(self, side: str, price: D, exclude_order_id: int | None = None) -> bool:
        for other in self.active_orders:
            if other.order_id == exclude_order_id or other.side == side:
                continue
            if side == "BUY" and price >= other.price:
                return True
            if side == "SELL" and price <= other.price:
                return True
        return False

    def _endow(self, bid: D, time_us: int) -> None:
        if self.endowed:
            return
        quantity = _floor_step(self.endowment_notional / bid, self.step_size)
        if quantity < D(self.rules.min_quantity) or not self._valid_quantity(bid, quantity):
            quantity = ZERO
        self.first_bid = bid
        self.endowment_quantity = quantity
        self.cash -= quantity * bid
        if quantity:
            band_quantity = _floor_step(quantity / D(SLOT_COUNT), self.step_size)
            remaining = quantity
            for band in range(SLOT_COUNT):
                if remaining <= ZERO:
                    break
                amount = band_quantity if band < SLOT_COUNT - 1 else remaining
                lot = LadderLot(
                        lot_id=f"{self.lane_id}:endowment-{band}",
                        quantity=amount,
                        remaining=amount,
                        unit_cost=bid,
                        entry_us=time_us,
                        initial_endowment=True,
                        band_id=band,
                        source_slot=band,
                    )
                self.lots.append(lot)
                self._record(
                    "LOT_CREATED",
                    time_us,
                    lot_id=lot.lot_id,
                    quantity=_str_decimal(amount),
                    unit_cost=_str_decimal(bid),
                    band_id=band,
                    source_order_id=None,
                    initial_endowment=True,
                )
                remaining -= amount
            self.inventory += quantity
            self.inventory_cost += quantity * bid
        self.endowed = True
        self._record(
            "ENDOWMENT",
            time_us,
            bid=_str_decimal(bid),
            quantity=_str_decimal(quantity),
            cash=_str_decimal(self.cash),
        )

    def _ladder_prices(self, mid: D) -> tuple[list[D], list[D]]:
        center_floor = (mid / self.tick_size).to_integral_value(rounding=ROUND_FLOOR)
        center_ceil = (mid / self.tick_size).to_integral_value(rounding=ROUND_CEILING)
        buys = [(center_floor - i) * self.tick_size for i in range(SLOT_COUNT)]
        sells = [(center_ceil + i) * self.tick_size for i in range(SLOT_COUNT)]
        return buys, sells

    def _break_even_exit(self, lot: LadderLot) -> D:
        fee = D(getattr(self.profile, "maker_fee", ZERO))
        gross = lot.unit_cost / (ONE - fee) if fee < ONE else lot.unit_cost
        return _ceil_tick(gross, self.tick_size) + self.tick_size

    def _desired_orders(self) -> dict[tuple[str, int], tuple[D, D]]:
        bid, ask = self._best_bid(), self._best_ask()
        if bid is None or ask is None:
            return {}
        mid = (bid + ask) / D(2)
        buy_prices, sell_prices = self._ladder_prices(mid)
        desired: dict[tuple[str, int], tuple[D, D]] = {}
        active_by_key = {(order.side, order.slot): order for order in self.active_orders}
        fee_rate = D(getattr(self.profile, "maker_fee", ZERO))
        projected_inventory_mark = self.inventory * bid + sum(
            (
                order.remaining * bid
                for order in self.active_orders
                if order.side == "BUY"
            ),
            ZERO,
        )
        projected_equity = self._marked_equity(bid) + sum(
            (
                order.remaining * (bid - order.price * (ONE + fee_rate))
                for order in self.active_orders
                if order.side == "BUY"
            ),
            ZERO,
        )
        for slot, price in enumerate(buy_prices):
            if not self._valid_price(price) or price >= ask:
                continue
            existing = active_by_key.get(("BUY", slot))
            if existing is not None:
                desired[("BUY", slot)] = (price, existing.remaining)
                continue
            quantity = _ceil_step(self.safe_min_notional / price, self.step_size)
            affordable = self.cash
            quantity = min(
                quantity,
                _floor_step(affordable / (price * (ONE + fee_rate)), self.step_size),
            )
            candidate_inventory_mark = projected_inventory_mark + quantity * bid
            candidate_equity = projected_equity + quantity * (
                bid - price * (ONE + fee_rate)
            )
            if (
                self._valid_quantity(price, quantity)
                and price * quantity >= self.safe_min_notional
                and candidate_equity > ZERO
                and candidate_inventory_mark <= self.projected_usdc_cap * candidate_equity
            ):
                desired[("BUY", slot)] = (price, quantity)
                projected_inventory_mark = candidate_inventory_mark
                projected_equity = candidate_equity

        for slot, ladder_price in enumerate(sell_prices):
            existing = active_by_key.get(("SELL", slot))
            if existing is not None:
                desired[("SELL", slot)] = (existing.price, existing.remaining)
                continue
            if not self._valid_price(ladder_price) or ladder_price <= bid:
                continue
            price = ladder_price
            band_lots = [
                lot
                for lot in self.lots
                if lot.band_id == slot and lot.remaining - lot.reserved > ZERO
            ]
            if not band_lots:
                continue
            selected_lots: list[LadderLot] = []
            selected_quantity = ZERO
            for lot in band_lots:
                selected_lots.append(lot)
                selected_quantity += lot.remaining - lot.reserved
                price = max(price, self._break_even_exit(lot))
                if selected_quantity * price >= self.safe_min_notional:
                    break
            own_buys = [
                order.price for order in self.active_orders if order.side == "BUY"
            ] + [
                desired_price
                for (desired_side, _), (desired_price, _) in desired.items()
                if desired_side == "BUY"
            ]
            if own_buys:
                price = max(price, max(own_buys) + self.tick_size)
            if not self._valid_price(price) or price <= bid:
                continue
            quantity = _floor_step(selected_quantity, self.step_size)
            if self._valid_quantity(price, quantity) and price * quantity >= self.safe_min_notional:
                desired[("SELL", slot)] = (price, quantity)
        return desired

    def _cancel(self, order: LadderOrder, now: int, reason: str) -> None:
        if order.status not in {"PENDING", "ACTIVE"}:
            return
        if not self._rate_limit_available(self._cancel_times, now):
            return
        if order.status == "PENDING" and order.active_us <= now:
            self._evaluate_activation(order, now)
            if order.status != "ACTIVE":
                return
        order.status = "CANCEL_PENDING"
        order.cancel_us = now + int(getattr(self.profile, "cancel_latency_us", 1))
        self._cancel_times.append(now)
        self._record("CANCEL", now, order_id=order.order_id, reason=reason)

    def _reserve_sell_lots(self, quantity: D, slot: int) -> list[tuple[str, D]]:
        """Bind a SELL order to FIFO lots before it can become active."""
        remaining = quantity
        allocations: list[tuple[str, D]] = []
        for lot in self.lots:
            if lot.band_id != slot:
                continue
            available = lot.remaining - lot.reserved
            if available <= ZERO:
                continue
            amount = min(remaining, available)
            if amount <= ZERO:
                continue
            lot.reserved += amount
            allocations.append((lot.lot_id, amount))
            remaining -= amount
            if remaining <= ZERO:
                break
        if remaining > ZERO:
            for lot_id, amount in allocations:
                lot = next(item for item in self.lots if item.lot_id == lot_id)
                lot.reserved -= amount
            return []
        return allocations

    def _release_order_reservations(self, order: LadderOrder) -> None:
        if order.side == "BUY":
            self.cash += order.reserved_quote
            order.reserved_quote = ZERO
            return
        for lot_id, amount in order.reserved_lots:
            lot = next((item for item in self.lots if item.lot_id == lot_id), None)
            if lot is not None:
                lot.reserved -= amount
        order.reserved_lots = []

    def _submit(self, side: str, slot: int, price: D, quantity: D, now: int) -> None:
        if not self._rate_limit_available(self._submission_times, now):
            self._record("SUBMIT_REJECTED", now, side=side, slot=slot, reason="RATE_LIMIT")
            return
        if side == "BUY" and self._best_ask() is not None and price >= self._best_ask():
            return
        if side == "SELL" and self._best_bid() is not None and price <= self._best_bid():
            return
        if self._would_self_cross(side, price):
            self._record("SELF_CROSS_BLOCKED", now, side=side, slot=slot, price=str(price))
            return
        fee_rate = D(getattr(self.profile, "maker_fee", ZERO))
        reserved_quote = quantity * price * (ONE + fee_rate) if side == "BUY" else ZERO
        if side == "BUY":
            if reserved_quote > self.cash:
                return
            self.cash -= reserved_quote
        allocations = self._reserve_sell_lots(quantity, slot) if side == "SELL" else []
        if side == "SELL" and not allocations:
            return
        order = LadderOrder(
            order_id=self._next_order_id,
            slot=slot,
            side=side,
            price=price,
            quantity=quantity,
            remaining=quantity,
            submitted_us=now,
            active_us=now + int(getattr(self.profile, "latency_us", 1)),
            queue=ZERO,
            reserved_quote=reserved_quote,
            reserved_lots=allocations,
            submitted_native_us=self._current_native_us,
        )
        self._next_order_id += 1
        self.orders.append(order)
        self._open_orders[order.order_id] = order
        self._submission_times.append(now)
        self._record(
            "SUBMIT",
            now,
            order_id=order.order_id,
            slot=slot,
            side=side,
            price=_str_decimal(price),
            quantity=_str_decimal(quantity),
            active_us=order.active_us,
            queue=_str_decimal(order.queue),
            reserved_quote=_str_decimal(order.reserved_quote),
            reserved_lots=[
                [lot_id, _str_decimal(amount)] for lot_id, amount in order.reserved_lots
            ],
        )

    def _refresh(self, now: int) -> None:
        if self.last_refresh_us >= 0 and now - self.last_refresh_us < REFRESH_US:
            return
        desired = self._desired_orders()
        by_slot = {(order.side, order.slot): order for order in self.active_orders}
        for key, order in list(by_slot.items()):
            target = desired.get(key)
            if target is None:
                self._cancel(order, now, "DESIRED_SLOT_GONE")
                continue
            target_price, target_quantity = target
            if order.side == "BUY" and abs(order.price - target_price) >= D(2) * self.tick_size:
                self._cancel(order, now, "REPRICE_TWO_TICKS")
            elif target_quantity < order.remaining and key[0] == "SELL":
                self._cancel(order, now, "OWNERSHIP_REDUCED")
        active_keys = {(order.side, order.slot) for order in self.active_orders}
        for (side, slot), (price, quantity) in desired.items():
            if (side, slot) not in active_keys:
                self._submit(side, slot, price, quantity, now)
        self.last_refresh_us = now

    def receive_book(self, book: Any) -> None:
        native_time = int(getattr(book, "exchange_time_us", getattr(book, "time_us", 0)))
        native_upper_value = getattr(book, "exchange_upper_us", None)
        native_upper = native_time if native_upper_value is None else int(native_upper_value)
        logical_time = int(getattr(book, "capture_time_us", native_time))
        if logical_time < self.last_logical_us:
            raise ValueError("NONCAUSAL_BOOK_TIME")
        bids, asks = _book_levels(book, "bids"), _book_levels(book, "asks")
        if not bids:
            return
        self.current_bids, self.current_asks = bids, asks
        self.known_bid_floor = D(book.known_bid_floor)
        self.known_ask_ceiling = D(book.known_ask_ceiling)
        self.last_book_us = logical_time
        self.last_logical_us = logical_time
        self.last_native_book_us = native_time
        self.last_native_book_upper_us = native_upper
        self._current_native_us = native_time
        if not self.endowed:
            self._endow(bids[0][0], logical_time)
        self._activate_pending(logical_time)
        self._refresh(logical_time)

    def _activate_pending(self, now: int) -> None:
        for order in self.active_orders:
            if order.status == "CANCEL_PENDING":
                if order.cancel_us is not None and order.cancel_us <= now:
                    released_quote = order.reserved_quote
                    released_base = sum((amount for _, amount in order.reserved_lots), ZERO)
                    self._release_order_reservations(order)
                    order.status = "CANCELED"
                    self._open_orders.pop(order.order_id, None)
                    self._record(
                        "CANCEL_ACK",
                        now,
                        order_id=order.order_id,
                        released_quote=_str_decimal(released_quote),
                        released_base=_str_decimal(released_base),
                    )
                    if order.side == "BUY":
                        self._maybe_settle_buy_order(order, now)
                    continue
                if order.activation_evaluated_us is None and order.active_us <= now:
                    self._evaluate_activation(order, now, keep_cancel_pending=True)
                continue
            if order.status == "PENDING" and order.active_us <= now:
                self._evaluate_activation(order, now)

    def _evaluate_activation(
        self, order: LadderOrder, now: int, *, keep_cancel_pending: bool = False
    ) -> None:
        bid, ask = self._best_bid(), self._best_ask()
        crosses_public = (order.side == "BUY" and ask is not None and order.price >= ask) or (
            order.side == "SELL" and bid is not None and order.price <= bid
        )
        crosses_self = self._would_self_cross(order.side, order.price, order.order_id)
        known = (
            self.known_bid_floor is not None
            and self.known_ask_ceiling is not None
            and (
                order.price >= self.known_bid_floor
                if order.side == "BUY"
                else order.price <= self.known_ask_ceiling
            )
        )
        if crosses_public or crosses_self or not known:
            released_quote = order.reserved_quote
            released_base = sum((amount for _, amount in order.reserved_lots), ZERO)
            self._release_order_reservations(order)
            order.status = (
                "REJECTED_POST_ONLY"
                if crosses_public
                else "REJECTED_SELF_CROSS"
                if crosses_self
                else "REJECTED_UNKNOWN_COVERAGE"
            )
            self._open_orders.pop(order.order_id, None)
            self._record(
                "POST_ONLY_REJECTED"
                if crosses_public
                else "SELF_CROSS_REJECTED"
                if crosses_self
                else "UNKNOWN_COVERAGE_REJECTED",
                now,
                order_id=order.order_id,
                side=order.side,
                price=_str_decimal(order.price),
                best_bid=None if bid is None else _str_decimal(bid),
                best_ask=None if ask is None else _str_decimal(ask),
                known_bid_floor=(
                    None
                    if self.known_bid_floor is None
                    else _str_decimal(self.known_bid_floor)
                ),
                known_ask_ceiling=(
                    None
                    if self.known_ask_ceiling is None
                    else _str_decimal(self.known_ask_ceiling)
                ),
                released_quote=_str_decimal(released_quote),
                released_base=_str_decimal(released_base),
            )
            return
        order.activation_evaluated_us = now
        order.status = "CANCEL_PENDING" if keep_cancel_pending else "ACTIVE"
        order.queue = self._displayed_quantity(order.side, order.price)
        self._record(
            "ACTIVATED",
            now,
            order_id=order.order_id,
            queue=_str_decimal(order.queue),
            side=order.side,
            price=_str_decimal(order.price),
            best_bid=None if bid is None else _str_decimal(bid),
            best_ask=None if ask is None else _str_decimal(ask),
            known_bid_floor=_str_decimal(self.known_bid_floor),
            known_ask_ceiling=_str_decimal(self.known_ask_ceiling),
            native_book_upper_us=self.last_native_book_upper_us,
        )

    def _eligible(self, order: LadderOrder, trade: Any) -> bool:
        if order.activation_evaluated_us is None:
            return False
        if int(trade.time_us) <= max(order.active_us, order.activation_evaluated_us):
            return False
        price, buyer_maker = D(trade.price), bool(trade.buyer_maker)
        if order.side == "BUY":
            # A resting BUY is hit by an aggressive seller: the observed
            # buyer is the resting maker (the B10 convention).
            return (price == order.price or price < order.price) and buyer_maker
        # A resting SELL is hit by an aggressive buyer.
        return (price == order.price or price > order.price) and not buyer_maker

    def _sell_from_lots(self, order: LadderOrder, quantity: D, time_us: int) -> D:
        remaining = quantity
        sold = ZERO
        fee_rate = D(getattr(self.profile, "maker_fee", ZERO))
        allocations = list(order.reserved_lots)
        affected_buy_orders: set[int] = set()
        while remaining > ZERO and allocations:
            lot_id, allocated = allocations[0]
            lot = next((item for item in self.lots if item.lot_id == lot_id), None)
            if lot is None:
                break
            if order.price <= lot.unit_cost / (ONE - fee_rate):
                break
            amount = min(remaining, allocated, lot.remaining, lot.reserved)
            gross = amount * order.price
            fee = gross * fee_rate
            cost = amount * lot.unit_cost
            profit = gross - fee - cost
            if profit <= ZERO:
                break
            lot.remaining -= amount
            lot.reserved -= amount
            lot.sold_quantity += amount
            lot.realized_profit += profit
            if lot.source_order_id is not None and not lot.initial_endowment:
                affected_buy_orders.add(lot.source_order_id)
            self.inventory -= amount
            self.inventory_cost -= cost
            self.cash += gross - fee
            self.fees += fee
            self.realized_sales += gross - fee
            self.realized_profit += profit
            self._record(
                "LOT_SOLD",
                time_us,
                lot_id=lot.lot_id,
                source_order_id=lot.source_order_id,
                sell_order_id=order.order_id,
                quantity=_str_decimal(amount),
                gross=_str_decimal(gross),
                fee=_str_decimal(fee),
                cost=_str_decimal(cost),
                profit=_str_decimal(profit),
                remaining=_str_decimal(lot.remaining),
                initial_endowment=lot.initial_endowment,
            )
            sold += amount
            remaining -= amount
            allocated -= amount
            if allocated == ZERO:
                allocations.pop(0)
            else:
                allocations[0] = (lot_id, allocated)
            if lot.remaining == ZERO:
                lot.closed_us = time_us
                # Closed lots remain in the immutable economic lineage.  Their
                # remaining quantity is zero, so they cannot be reserved again.
        order.reserved_lots = allocations
        for source_order_id in affected_buy_orders:
            source_order = next(
                item for item in self.orders if item.order_id == source_order_id
            )
            self._maybe_settle_buy_order(source_order, time_us)
        return sold

    def _maybe_settle_buy_order(self, order: LadderOrder, time_us: int) -> None:
        """Count one cycle per terminal BUY order, independent of fill fragmentation."""
        if order.side != "BUY" or order.cycle_recorded:
            return
        if order.status not in {"FILLED", "CANCELED"}:
            return
        lots = [
            lot
            for lot in self.lots
            if not lot.initial_endowment and lot.source_order_id == order.order_id
        ]
        if not lots or any(lot.remaining > ZERO for lot in lots):
            return
        profit = sum((lot.realized_profit for lot in lots), ZERO)
        if profit <= ZERO:
            return
        order.cycle_recorded = True
        self.cycle_count += 1
        settlement = {
            "time_us": time_us,
            "release": False,
            "net_profit": _str_decimal(profit),
            "reserve_consumption": "0",
            "cycle": True,
            "lot_ids": [lot.lot_id for lot in lots],
            "band_id": order.slot,
            "source_slot": order.slot,
            "source_order_id": order.order_id,
            "entry_quantity": _str_decimal(sum((lot.quantity for lot in lots), ZERO)),
        }
        self.settlements.append(settlement)
        self._record(
            "CYCLE_SETTLED",
            time_us,
            **{key: value for key, value in settlement.items() if key != "time_us"},
        )

    def _fill(
        self,
        order: LadderOrder,
        quantity: D,
        time_us: int,
        *,
        source_id: int | None = None,
        source: str = "TRADE",
    ) -> D:
        quantity = min(quantity, order.remaining)
        if quantity <= ZERO:
            return ZERO
        fee_rate = D(getattr(self.profile, "maker_fee", ZERO))
        if order.side == "BUY":
            gross = quantity * order.price
            fee = gross * fee_rate
            if gross + fee > order.reserved_quote:
                quantity = _floor_step(
                    order.reserved_quote / (order.price * (ONE + fee_rate)), self.step_size
                )
                gross, fee = quantity * order.price, quantity * order.price * fee_rate
            if quantity <= ZERO:
                return ZERO
            order.reserved_quote -= gross + fee
            self.fees += fee
            lot = LadderLot(
                lot_id=f"{self.lane_id}:lot-{self._next_lot_id}",
                quantity=quantity,
                remaining=quantity,
                unit_cost=(gross + fee) / quantity,
                entry_us=time_us,
                band_id=order.slot,
                source_slot=order.slot,
                source_order_id=order.order_id,
            )
            self._next_lot_id += 1
            self.lots.append(lot)
            self._record(
                "LOT_CREATED",
                time_us,
                lot_id=lot.lot_id,
                quantity=_str_decimal(quantity),
                unit_cost=_str_decimal(lot.unit_cost),
                band_id=lot.band_id,
                source_order_id=order.order_id,
                initial_endowment=False,
            )
            self.inventory += quantity
            self.inventory_cost += gross + fee
        else:
            quantity = self._sell_from_lots(order, quantity, time_us)
            if quantity <= ZERO:
                return ZERO
        order.remaining -= quantity
        order.filled += quantity
        order.had_partial = order.had_partial or order.remaining > ZERO
        if order.remaining == ZERO:
            if order.side == "BUY" and order.reserved_quote:
                self.cash += order.reserved_quote
                order.reserved_quote = ZERO
            order.status = "FILLED"
            self._open_orders.pop(order.order_id, None)
            if order.side == "BUY":
                self._maybe_settle_buy_order(order, time_us)
        self._record(
            "FILL",
            time_us,
            order_id=order.order_id,
            side=order.side,
            price=_str_decimal(order.price),
            quantity=_str_decimal(quantity),
            source=source,
            source_id=source_id,
            remaining_after=_str_decimal(order.remaining),
            status_after=order.status,
        )
        return quantity

    def receive_trade(
        self,
        trade: Any,
        *,
        capture_time_us: int | None = None,
        capture_order: int | None = None,
    ) -> D:
        native_time = int(trade.time_us)
        time_us = int(capture_time_us if capture_time_us is not None else native_time)
        if time_us < self.last_logical_us:
            raise ValueError("NONCAUSAL_CAPTURE_ORDER")
        self.last_logical_us = time_us
        self._activate_pending(time_us)
        available = D(trade.quantity)
        consumed = ZERO
        queue_consumed = ZERO
        fill_consumed = ZERO
        if self.last_native_book_upper_us > native_time:
            self.processed_trades += 1
            self._record(
                "TRADE_BLOCKED_FUTURE_BOOK",
                time_us,
                trade_id=getattr(trade, "trade_id", None),
                native_time_us=native_time,
                book_upper_us=self.last_native_book_upper_us,
                original_quantity=_str_decimal(D(trade.quantity)),
                consumed_quantity="0",
                remaining_quantity=_str_decimal(D(trade.quantity)),
                capture_time_us=capture_time_us,
                capture_order=capture_order,
            )
            return ZERO
        for order in sorted(self.active_orders, key=lambda item: (item.active_us, item.order_id)):
            if (
                available <= ZERO
                or order.status not in {"ACTIVE", "CANCEL_PENDING"}
                or not self._eligible(order, trade)
            ):
                continue
            exact = D(trade.price) == order.price
            if exact and order.queue > ZERO:
                queue_before = order.queue
                ahead = min(order.queue, available)
                order.queue -= ahead
                available -= ahead
                consumed += ahead
                queue_consumed += ahead
                self._record(
                    "QUEUE_FLOW",
                    time_us,
                    order_id=order.order_id,
                    trade_id=getattr(trade, "trade_id", None),
                    queue_before=_str_decimal(queue_before),
                    queue_after=_str_decimal(order.queue),
                    quantity=_str_decimal(ahead),
                )
                if available <= ZERO:
                    break
            filled = self._fill(
                order,
                available,
                time_us,
                source_id=getattr(trade, "trade_id", None),
                source="TRADE" if exact else "TRADE_THROUGH",
            )
            available -= filled
            consumed += filled
            fill_consumed += filled
        self.processed_trades += 1
        self._record(
            "TRADE",
            time_us,
            trade_id=getattr(trade, "trade_id", None),
            original_quantity=_str_decimal(D(trade.quantity)),
            consumed_quantity=_str_decimal(consumed),
            queue_consumed_quantity=_str_decimal(queue_consumed),
            fill_consumed_quantity=_str_decimal(fill_consumed),
            remaining_quantity=_str_decimal(available),
            capture_time_us=capture_time_us,
            capture_order=capture_order,
            native_time_us=native_time,
        )
        return consumed

    def begin_sample_seam(self, timestamp: int, source_date: str) -> None:
        self._record("SYNTHETIC_SAMPLE_SEAM", timestamp, source_date=source_date)

    def _state(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "candidate": self.candidate,
            "config_sha256": self._config_hash(),
            "initial_capital": _str_decimal(self.initial_capital),
            "endowment_notional": _str_decimal(self.endowment_notional),
            "projected_usdc_cap": _str_decimal(self.projected_usdc_cap),
            "cash": _str_decimal(self.cash),
            "reserve": _str_decimal(self.reserve),
            "inventory": _str_decimal(self.inventory),
            "inventory_cost": _str_decimal(self.inventory_cost),
            "fees": _str_decimal(self.fees),
            "realized_sales": _str_decimal(self.realized_sales),
            "realized_profit": _str_decimal(self.realized_profit),
            "cycle_count": self.cycle_count,
            "processed_trades": self.processed_trades,
            "first_bid": None if self.first_bid is None else _str_decimal(self.first_bid),
            "endowment_quantity": _str_decimal(self.endowment_quantity),
            "endowed": self.endowed,
            "last_book_us": self.last_book_us,
            "last_native_book_us": self.last_native_book_us,
            "last_native_book_upper_us": self.last_native_book_upper_us,
            "last_logical_us": self.last_logical_us,
            "last_refresh_us": self.last_refresh_us,
            "current_native_us": self._current_native_us,
            "current_bids": [[_str_decimal(p), _str_decimal(q)] for p, q in self.current_bids],
            "current_asks": [[_str_decimal(p), _str_decimal(q)] for p, q in self.current_asks],
            "known_bid_floor": (
                None if self.known_bid_floor is None else _str_decimal(self.known_bid_floor)
            ),
            "known_ask_ceiling": (
                None if self.known_ask_ceiling is None else _str_decimal(self.known_ask_ceiling)
            ),
            "orders": [
                {
                    "order_id": o.order_id,
                    "slot": o.slot,
                    "side": o.side,
                    "price": _str_decimal(o.price),
                    "quantity": _str_decimal(o.quantity),
                    "remaining": _str_decimal(o.remaining),
                    "submitted_us": o.submitted_us,
                    "active_us": o.active_us,
                    "queue": _str_decimal(o.queue),
                    "reserved_quote": _str_decimal(o.reserved_quote),
                    "reserved_lots": [
                        [lot_id, _str_decimal(amount)] for lot_id, amount in o.reserved_lots
                    ],
                    "submitted_native_us": o.submitted_native_us,
                    "status": o.status,
                    "filled": _str_decimal(o.filled),
                    "had_partial": o.had_partial,
                    "cancel_us": o.cancel_us,
                    "activation_evaluated_us": o.activation_evaluated_us,
                    "cycle_recorded": o.cycle_recorded,
                }
                for o in self.orders
            ],
            "lots": [
                {
                    "lot_id": lot.lot_id,
                    "quantity": _str_decimal(lot.quantity),
                    "remaining": _str_decimal(lot.remaining),
                    "unit_cost": _str_decimal(lot.unit_cost),
                    "entry_us": lot.entry_us,
                    "initial_endowment": lot.initial_endowment,
                    "realized_profit": _str_decimal(lot.realized_profit),
                    "sold_quantity": _str_decimal(lot.sold_quantity),
                    "reserved": _str_decimal(lot.reserved),
                    "band_id": lot.band_id,
                    "source_slot": lot.source_slot,
                    "source_order_id": lot.source_order_id,
                    "closed_us": lot.closed_us,
                }
                for lot in self.lots
            ],
            "next_order_id": self._next_order_id,
            "next_lot_id": self._next_lot_id,
            "audit": self.audit,
            "settlements": self.settlements,
            "submission_times": self._submission_times,
            "cancel_times": self._cancel_times,
            "finished": self._finished,
            "finished_us": self._finished_us,
        }

    def checkpoint(self) -> dict[str, Any]:
        state = self._state()
        return {
            "schema": "M019_ADAPTIVE_STABLECOIN_LADDER_V1",
            "state": state,
            "sha256": canonical_hash(state),
        }

    def restore(self, checkpoint: dict[str, Any]) -> None:
        if checkpoint.get("schema") != "M019_ADAPTIVE_STABLECOIN_LADDER_V1":
            raise ValueError("INVALID_LADDER_CHECKPOINT")
        state = checkpoint.get("state")
        if not isinstance(state, dict) or checkpoint.get("sha256") != canonical_hash(state):
            raise ValueError("CHECKPOINT_HASH_MISMATCH")
        if state.get("config_sha256") != self._config_hash():
            raise ValueError("CHECKPOINT_PROFILE_OR_RULES_MISMATCH")
        self.lane_id = str(state["lane_id"])
        self.candidate = str(state["candidate"])
        self.initial_capital = D(state["initial_capital"])
        self.endowment_notional = D(state["endowment_notional"])
        self.projected_usdc_cap = D(state["projected_usdc_cap"])
        decimal_fields = (
            "cash",
            "reserve",
            "inventory",
            "inventory_cost",
            "fees",
            "realized_sales",
            "realized_profit",
            "endowment_quantity",
        )
        for name in decimal_fields:
            setattr(self, name, D(state[name]))
        integer_fields = (
            "cycle_count",
            "processed_trades",
            "last_book_us",
            "last_native_book_us",
            "last_native_book_upper_us",
            "last_logical_us",
            "last_refresh_us",
            "current_native_us",
            "next_order_id",
            "next_lot_id",
        )
        for name in integer_fields:
            internal = name.startswith("next_") or name == "current_native_us"
            setattr(self, f"_{name}" if internal else name, int(state[name]))
        self.first_bid = None if state["first_bid"] is None else D(state["first_bid"])
        self.endowed = bool(state["endowed"])
        self.current_bids = tuple((D(p), D(q)) for p, q in state["current_bids"])
        self.current_asks = tuple((D(p), D(q)) for p, q in state["current_asks"])
        self.known_bid_floor = (
            None if state["known_bid_floor"] is None else D(state["known_bid_floor"])
        )
        self.known_ask_ceiling = (
            None if state["known_ask_ceiling"] is None else D(state["known_ask_ceiling"])
        )
        decimal_order_fields = {
            "price",
            "quantity",
            "remaining",
            "queue",
            "filled",
            "reserved_quote",
        }
        self.orders = []
        for row in state["orders"]:
            values = {
                key: D(value) if key in decimal_order_fields else value
                for key, value in row.items()
            }
            values["reserved_lots"] = [
                (str(lot_id), D(amount)) for lot_id, amount in row.get("reserved_lots", [])
            ]
            self.orders.append(LadderOrder(**values))
        self._open_orders = {
            order.order_id: order
            for order in self.orders
            if order.status in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
        }
        decimal_lot_fields = {
            "quantity",
            "remaining",
            "unit_cost",
            "realized_profit",
            "sold_quantity",
            "reserved",
        }
        self.lots = deque(
            LadderLot(
                **{
                    key: D(value) if key in decimal_lot_fields else value
                    for key, value in row.items()
                }
            )
            for row in state["lots"]
        )
        self.audit = list(state["audit"])
        self.settlements = list(state["settlements"])
        self._submission_times = [int(value) for value in state.get("submission_times", [])]
        self._cancel_times = [int(value) for value in state.get("cancel_times", [])]
        self._finished = bool(state.get("finished", False))
        self._finished_us = (
            None if state.get("finished_us") is None else int(state["finished_us"])
        )

    @classmethod
    def from_checkpoint(
        cls, checkpoint: dict[str, Any], profile: Any, rules: Any
    ) -> AdaptiveStablecoinLadder:
        state = checkpoint.get("state", {})
        value = cls(
            profile,
            rules,
            lane_id=str(state.get("lane_id", "lane-0")),
            candidate=str(state.get("candidate", "M019")),
        )
        value.restore(checkpoint)
        return value

    def finish(self, end_us: int | None = None) -> dict[str, Any]:
        self._finished = True
        self._finished_us = self.last_logical_us if end_us is None else int(end_us)
        return self.metrics()

    def capital_state(self) -> dict[str, str]:
        """Return the explicit free/reserved/inventory capital buckets."""
        mark = self._best_bid() or self.first_bid or ZERO
        return {
            "free_usdt": _str_decimal(self.cash),
            "reserve_usdt": _str_decimal(self.reserve),
            "active_buy_usdt": _str_decimal(self.active_buy_notional),
            "reserved_sell_usdc": _str_decimal(self.reserved_sell_quantity),
            "inventory_usdc": _str_decimal(self.inventory),
            "inventory_cost_usdt": _str_decimal(self.inventory_cost),
            "marked_equity_usdt": _str_decimal(
                self.cash + self.active_buy_notional + self.reserve + self.inventory * mark
            ),
        }

    def validate_invariants(self) -> bool:
        """Check conservation and slot uniqueness without changing state."""
        if min(self.cash, self.reserve, self.inventory, self.inventory_cost) < ZERO:
            raise ValueError("NEGATIVE_CAPITAL_STATE")
        lot_inventory = sum((lot.remaining for lot in self.lots), ZERO)
        if lot_inventory != self.inventory:
            raise ValueError("INVENTORY_LOT_RECONCILIATION")
        active_keys = [(order.side, order.slot) for order in self.active_orders]
        if any(self._open_orders.get(order.order_id) is not order for order in self.active_orders):
            raise ValueError("OPEN_ORDER_INDEX_RECONCILIATION")
        if len(active_keys) != len(set(active_keys)):
            raise ValueError("DUPLICATE_ACTIVE_SLOT")
        if len(self.active_orders) > SLOT_COUNT * 2:
            raise ValueError("ACTIVE_SLOT_LIMIT")
        order_lot_reservations: dict[str, D] = {}
        fee_rate = D(getattr(self.profile, "maker_fee", ZERO))
        for order in self.active_orders:
            if order.side == "BUY":
                expected = order.remaining * order.price * (ONE + fee_rate)
                if order.reserved_quote != expected:
                    raise ValueError("BUY_RESERVATION_RECONCILIATION")
            else:
                if order.reserved_quote != ZERO:
                    raise ValueError("SELL_HAS_QUOTE_RESERVATION")
                if sum((amount for _, amount in order.reserved_lots), ZERO) != order.remaining:
                    raise ValueError("SELL_RESERVATION_RECONCILIATION")
                for lot_id, amount in order.reserved_lots:
                    order_lot_reservations[lot_id] = (
                        order_lot_reservations.get(lot_id, ZERO) + amount
                    )
        for lot in self.lots:
            if lot.reserved < ZERO or lot.reserved > lot.remaining:
                raise ValueError("INVALID_LOT_RESERVATION")
            if order_lot_reservations.get(lot.lot_id, ZERO) != lot.reserved:
                raise ValueError("LOT_RESERVATION_RECONCILIATION")
        cost_basis_total = self.cash + self.active_buy_notional + self.inventory_cost
        if cost_basis_total != self.initial_capital + self.realized_profit:
            raise ValueError("CAPITAL_CONSERVATION")
        return True

    def metrics(self) -> dict[str, Any]:
        mark = self._best_bid() or self.first_bid or ZERO
        equity = self.cash + self.active_buy_notional + self.reserve + self.inventory * mark
        unrealized = self.inventory * mark - self.inventory_cost
        observation_end = (
            self._finished_us if self._finished_us is not None else self.last_logical_us
        )
        all_holds = [
            D((lot.closed_us if lot.closed_us is not None else observation_end) - lot.entry_us)
            / D("3600000000")
            for lot in self.lots
            if observation_end >= lot.entry_us
        ]
        return {
            "candidate": self.candidate,
            "lane_id": self.lane_id,
            "initial_capital": _str_decimal(self.initial_capital),
            "cash": _str_decimal(self.cash),
            "reserve": _str_decimal(self.reserve),
            "inventory": _str_decimal(self.inventory),
            "equity": _str_decimal(equity),
            "fees": _str_decimal(self.fees),
            "realized_sales": _str_decimal(self.realized_sales),
            "realized_profit": _str_decimal(self.realized_profit),
            "unrealized_profit": _str_decimal(unrealized),
            "cycle_count": self.cycle_count,
            "processed_trades": self.processed_trades,
            "active_orders": len(self.active_orders),
            "active_buy_notional": _str_decimal(self.active_buy_notional),
            "safe_min_notional": _str_decimal(self.safe_min_notional),
            "max_hold_hours": _str_decimal(max(all_holds, default=ZERO)),
            "hold_gt_1h": sum(hours > 1 for hours in all_holds),
            "one_hour_metrics_only": True,
            "cutoff_liquidation": False,
            "capital_state": self.capital_state(),
        }


__all__ = [
    "ENDOWMENT_NOTIONAL",
    "INITIAL_CAPITAL",
    "ONE_HOUR_US",
    "PROJECTED_USDC_CAP",
    "REFRESH_US",
    "SLOT_COUNT",
    "AdaptiveStablecoinLadder",
    "LadderLot",
    "LadderOrder",
]
