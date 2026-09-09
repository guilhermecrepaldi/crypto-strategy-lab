"""M023 serial hot-line mechanics probe.

The radar is deliberately virtual.  Only ``order`` participates in exchange
causality, reservation, queue, and fills; the two 100-card decks are a
permutation of reusable price templates.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.zonal_ping_pong import (
    M021_TICK_SIZE,
    ZERO,
    D,
    DensePingPongProbe,
)

ONE = D("1")
INITIAL_CASH = D("1.0019")


def _dec(value: Any) -> D:
    return value if isinstance(value, D) else D(str(value))


def _s(value: D) -> str:
    return str(value)


def _floor_tick(value: D) -> D:
    return (value / M021_TICK_SIZE).to_integral_value(rounding=ROUND_FLOOR) * M021_TICK_SIZE


def _ceil_tick(value: D) -> D:
    return (value / M021_TICK_SIZE).to_integral_value(rounding=ROUND_CEILING) * M021_TICK_SIZE


@dataclass
class HotLineCard:
    card_id: str
    side: str
    price: D
    position: int
    status: str = "FREE"
    lifecycle: int = 0


@dataclass
class HotLineOrder:
    order_id: int
    side: str
    price: D
    quantity: D
    submitted_us: int
    active_us: int
    status: str = "PENDING"
    filled: D = ZERO
    queue: D = ZERO
    reserved_quote: D = ZERO
    activation_evaluated_us: int | None = None
    cancel_us: int | None = None
    card_id: str | None = None
    completed_us: int | None = None
    realized_profit: D = ZERO

    @property
    def remaining(self) -> D:
        return self.quantity - self.filled


class SerialHotLinePingPongProbe:
    """One-order BUY→SELL serial state machine with a virtual 200-card radar."""

    normalized_label = "M023 SERIAL HOT LINE. NORMALIZED 1-USDC NON-EXECUTABLE PROBE."

    def __init__(
        self,
        *,
        start_us: int,
        end_us: int,
        latency_us: int = 1,
        cancel_latency_us: int = 1,
    ) -> None:
        self.start_us = int(start_us)
        self.end_us = int(end_us)
        self.latency_us = int(latency_us)
        self.cancel_latency_us = int(cancel_latency_us)
        self.cash = INITIAL_CASH
        self.inventory = ZERO
        self.inventory_cost = ZERO
        self.realized_profit = ZERO
        self.cycles = 0
        self.buy_fills = 0
        self.sell_fills = 0
        self.order: HotLineOrder | None = None
        self.orders: list[HotLineOrder] = []
        self.state = "WAIT_BUY"
        self._next_order_id = 1
        self._last_logical_us = self.start_us
        self._last_native_us = self.start_us
        self._last_native_book_upper_us = self.start_us
        self._last_book: dict[str, Any] | None = None
        self._processed_trades: set[str] = set()
        self._rejection_context: tuple[Any, ...] | None = None
        self._partial_residual_blocked: list[dict[str, Any]] = []
        self._audit: list[dict[str, Any]] = []
        self._queue_blocked_quantity = ZERO
        self._queue_blocked_events = 0
        self._trade_through_quantity = ZERO
        self._exact_fill_quantity = ZERO
        self._cancel_count = 0
        self._reprice_count = 0
        self._suppressed_retries = 0
        self._submission_count = 0
        self._active_order_time_us = 0
        self._no_order_time_us = 0
        self._last_observation_us = self.start_us
        self._last_trade_price = ZERO
        self._max_open = 0
        self._deck_rotation_count = 0
        self.buy_deck, self.sell_deck = self._make_decks()

    @staticmethod
    def _make_decks() -> tuple[list[HotLineCard], list[HotLineCard]]:
        # M021/M022's published lattice is anchored at the first causal
        # bridged midpoint, 1.0020. The cards inherit those 200 addresses.
        grid = DensePingPongProbe._make_grid(D("1.0020"))
        buys = [
            HotLineCard(f"B{index:03d}", "BUY", band.buy_price, index - 1)
            for index, band in enumerate(grid[:100], 1)
        ]
        sells = [
            HotLineCard(f"S{index:03d}", "SELL", band.sell_price, index - 1)
            for index, band in enumerate(grid[100:], 1)
        ]
        return buys, sells

    @property
    def radar(self) -> tuple[HotLineCard, ...]:
        return tuple(self.buy_deck + self.sell_deck)

    @property
    def audit(self) -> list[dict[str, Any]]:
        return self._audit

    def _record(self, event: str, time_us: int, **fields: Any) -> None:
        self._audit.append({"event": event, "time_us": int(time_us), **fields})

    def _check_time(self, time_us: int) -> None:
        if time_us < self.start_us or time_us >= self.end_us:
            raise ValueError("CUTOFF_EXCLUSIVE")
        if time_us < self._last_logical_us:
            raise ValueError("NONCAUSAL_LOGICAL_TIME")
        self._last_logical_us = time_us

    def _observe(self, now: int) -> None:
        elapsed = max(0, now - self._last_observation_us)
        if self.order is None:
            self._no_order_time_us += elapsed
        else:
            self._active_order_time_us += elapsed
        self._last_observation_us = now

    @staticmethod
    def _field(event: Any, key: str, default: Any = None) -> Any:
        return event.get(key, default) if isinstance(event, dict) else getattr(event, key, default)

    def _context(self, desired: tuple[str, D] | None) -> tuple[Any, ...]:
        if self._last_book is None:
            return (self.state, self.cash, self.inventory, desired)
        return (
            self.state,
            self.cash,
            self.inventory,
            self._last_book["bids"][0][0],
            self._last_book["asks"][0][0],
            self._last_book["known_bid_floor"],
            self._last_book["known_ask_ceiling"],
            desired,
        )

    def _serialized_rejection_context(self) -> list[Any] | None:
        if self._rejection_context is None:
            return None
        values = list(self._rejection_context)
        values[1:7] = [_s(value) for value in values[1:7]]
        if values[7] is not None:
            values[7] = [values[7][0], _s(values[7][1])]
        return values

    @staticmethod
    def _restore_rejection_context(raw: Any) -> tuple[Any, ...] | None:
        if raw is None:
            return None
        values = list(raw)
        values[1:7] = [_dec(value) for value in values[1:7]]
        if values[7] is not None:
            values[7] = (values[7][0], _dec(values[7][1]))
        return tuple(values)

    def _book_mid(self) -> D:
        return (self._last_book["bids"][0][0] + self._last_book["asks"][0][0]) / D("2")

    def _covered(self, side: str, price: D) -> bool:
        if side == "BUY":
            return price >= self._last_book["known_bid_floor"]
        return price <= self._last_book["known_ask_ceiling"]

    def _desired(self) -> tuple[str, D] | None:
        # The target remains meaningful while an order is live: reconciliation
        # compares it with the live order before deciding whether a cancel is
        # required.  A filled leg is handled by ``_reconcile`` and therefore
        # does not submit/reprice from this value.
        if self._last_book is None:
            return None
        bid = self._last_book["bids"][0][0]
        ask = self._last_book["asks"][0][0]
        if self.state == "WAIT_BUY":
            # A live BUY has its quote reserved out of ``cash``.  Include that
            # reservation when recomputing the same target; otherwise merely
            # activating an order makes the available balance look nearly
            # zero and triggers a spurious cancel/re-submit loop.
            available_cash = self.cash
            if self.order is not None and self.order.side == "BUY":
                available_cash += self.order.reserved_quote
            price = min(ask - M021_TICK_SIZE, _floor_tick(available_cash))
            if price > ZERO and price < ask and self._covered("BUY", price):
                return "BUY", price
            return None
        if self.state == "WAIT_SELL" and self.inventory == ONE:
            basis = self.inventory_cost / self.inventory
            price = max(bid + M021_TICK_SIZE, _ceil_tick(basis + M021_TICK_SIZE))
            if price > basis and self._covered("SELL", price):
                return "SELL", price
        return None

    def _free_card(self, side: str, price: D) -> HotLineCard | None:
        deck = self.buy_deck if side == "BUY" else self.sell_deck
        free = [card for card in deck if card.status == "FREE"]
        if not free:
            return None
        if side == "BUY":
            eligible = [card for card in free if card.price <= price]
            return max(eligible or free, key=lambda card: (card.price, card.card_id))
        eligible = [card for card in free if card.price >= price]
        return min(eligible or free, key=lambda card: (card.price, card.card_id))

    def _arm_card(self, side: str, price: D, now: int) -> HotLineCard | None:
        card = self._free_card(side, price)
        if card is None:
            return None
        card.status = "ARMED"
        self._record("RADAR_ARMED", now, card_id=card.card_id, side=side, price=_s(price))
        return card

    def _rotate_card(self, card_id: str | None, side: str, now: int) -> None:
        if card_id is None:
            return
        deck = self.buy_deck if side == "BUY" else self.sell_deck
        executed = next(card for card in deck if card.card_id == card_id)
        executed.status = "FREE"
        executed.lifecycle += 1
        free = [card for card in deck if card.status == "FREE" and card.card_id != executed.card_id]
        if side == "BUY":
            promoted = max(free, key=lambda card: (card.price, card.card_id))
        else:
            promoted = min(free, key=lambda card: (card.price, card.card_id))
        old_position = executed.position
        promoted_old_position = promoted.position
        old_price = executed.price
        promoted_old_price = promoted.price
        promoted.position = old_position
        promoted.price = old_price
        # The promoted card moves into the completed card's hot-line slot;
        # the completed template takes the promoted card's former slot.  This
        # is a permutation (no duplicate virtual positions) while preserving
        # the side-specific price-priority edge selection.
        executed.position = promoted_old_position
        executed.price = promoted_old_price
        promoted.status = "FREE"
        self._deck_rotation_count += 1
        self._record(
            "RADAR_ROTATION",
            now,
            side=side,
            filled_card_id=executed.card_id,
            promoted_card_id=promoted.card_id,
            old_position=promoted_old_position,
            new_position=old_position,
            old_price=_s(promoted_old_price),
            new_price=_s(old_price),
        )

    def _release_card(self, card_id: str | None) -> None:
        """Release an unfilled template without pretending that it traded."""
        if card_id is None:
            return
        card = next(item for item in self.radar if item.card_id == card_id)
        card.status = "FREE"

    def _submit(self, side: str, price: D, now: int) -> None:
        if self.order is not None:
            raise ValueError("M023_ORDER_CAP_EXCEEDED")
        card = self._arm_card(side, price, now)
        if card is None:
            self._record("RADAR_NO_FREE_CARD", now, side=side)
            return
        quote = price if side == "BUY" else ZERO
        if side == "BUY":
            if quote > self.cash:
                card.status = "FREE"
                self._record("CAPITAL_BLOCKED", now, required=_s(quote), available=_s(self.cash))
                return
            self.cash -= quote
        self.order = HotLineOrder(
            self._next_order_id,
            side,
            price,
            ONE,
            now,
            now + self.latency_us,
            reserved_quote=quote,
            card_id=card.card_id,
        )
        self._next_order_id += 1
        self.orders.append(self.order)
        self._submission_count += 1
        self._max_open = max(self._max_open, 1)
        self._record(
            "SUBMIT",
            now,
            order_id=self.order.order_id,
            side=side,
            price=_s(price),
            quantity=_s(ONE),
            card_id=card.card_id,
        )

    def _release_cancel(self, order: HotLineOrder, now: int) -> None:
        if order.side == "BUY" and order.reserved_quote > ZERO:
            self.cash += order.reserved_quote
            order.reserved_quote = ZERO
        if order.filled > ZERO and order.remaining > ZERO:
            row = {
                "order_id": order.order_id,
                "side": order.side,
                "residual_quantity": _s(order.remaining),
                "reason": "BELOW_HISTORICAL_STEP_AFTER_CANCEL_ACK",
            }
            self._partial_residual_blocked.append(row)
            self._record("PARTIAL_RESIDUAL_BLOCKED", now, **row)
        self._release_card(order.card_id)
        order.status = "CANCELED"
        self.order = None
        self._record("CANCEL_ACK", now, order_id=order.order_id)

    def _advance(self, now: int) -> None:
        order = self.order
        if order is None:
            return
        if (
            order.status == "CANCEL_PENDING"
            and order.cancel_us is not None
            and order.cancel_us <= now
        ):
            self._release_cancel(order, now)
            return
        if (
            order.status == "CANCEL_PENDING"
            and order.activation_evaluated_us is None
            and order.active_us <= now
        ):
            bid = self._last_book["bids"][0][0]
            ask = self._last_book["asks"][0][0]
            crosses = (order.side == "BUY" and order.price >= ask) or (
                order.side == "SELL" and order.price <= bid
            )
            if crosses or not self._covered(order.side, order.price):
                order.status = "REJECTED_POST_ONLY" if crosses else "REJECTED_COVERAGE"
                self._rejection_context = self._context((order.side, order.price))
                if order.side == "BUY" and order.reserved_quote > ZERO:
                    self.cash += order.reserved_quote
                    order.reserved_quote = ZERO
                self._release_card(order.card_id)
                self.order = None
                self._record(
                    order.status,
                    now,
                    order_id=order.order_id,
                    during_cancel=True,
                )
                return
            order.activation_evaluated_us = now
            levels = self._last_book["bids"] if order.side == "BUY" else self._last_book["asks"]
            order.queue = next(
                (quantity for price, quantity in levels if price == order.price), ZERO
            )
            self._record(
                "ACTIVATED",
                now,
                order_id=order.order_id,
                queue=_s(order.queue),
                native_book_upper_us=self._last_native_book_upper_us,
                during_cancel=True,
            )
        if order.status == "PENDING" and order.active_us <= now:
            bid = self._last_book["bids"][0][0]
            ask = self._last_book["asks"][0][0]
            crosses = (order.side == "BUY" and order.price >= ask) or (
                order.side == "SELL" and order.price <= bid
            )
            if crosses or not self._covered(order.side, order.price):
                order.status = "REJECTED_POST_ONLY" if crosses else "REJECTED_COVERAGE"
                self._rejection_context = self._context((order.side, order.price))
                if order.side == "BUY" and order.reserved_quote > ZERO:
                    self.cash += order.reserved_quote
                    order.reserved_quote = ZERO
                self._release_card(order.card_id)
                self.order = None
                self._record(order.status, now, order_id=order.order_id)
            else:
                order.status = "ACTIVE"
                order.activation_evaluated_us = now
                levels = self._last_book["bids"] if order.side == "BUY" else self._last_book["asks"]
                order.queue = next(
                    (quantity for price, quantity in levels if price == order.price), ZERO
                )
                self._record(
                    "ACTIVATED",
                    now,
                    order_id=order.order_id,
                    queue=_s(order.queue),
                    native_book_upper_us=self._last_native_book_upper_us,
                    during_cancel=False,
                )

    def _reconcile(self, now: int) -> None:
        desired = self._desired()
        if self.order is not None:
            if self.order.filled > ZERO:
                return
            if self.order.status in {"PENDING", "ACTIVE"} and desired != (
                self.order.side,
                self.order.price,
            ):
                self.order.status = "CANCEL_PENDING"
                self.order.cancel_us = now + self.cancel_latency_us
                self._cancel_count += 1
                self._reprice_count += 1
                self._record(
                    "CANCEL_REQUEST",
                    now,
                    order_id=self.order.order_id,
                    effective_us=self.order.cancel_us,
                )
            return
        if desired is None:
            return
        context = self._context(desired)
        if context == self._rejection_context:
            self._suppressed_retries += 1
            self._record("RETRY_SUPPRESSED", now, side=desired[0], price=_s(desired[1]))
            return
        self._rejection_context = None
        self._submit(desired[0], desired[1], now)

    def receive_book(self, book: Any, *, capture_time_us: int | None = None) -> None:
        native = int(
            self._field(book, "exchange_time_us", self._field(book, "time_us", self.start_us))
        )
        logical = int(
            capture_time_us
            if capture_time_us is not None
            else self._field(book, "capture_time_us", native)
        )
        self._check_time(logical)
        self._observe(logical)
        bids = tuple((_dec(row[0]), _dec(row[1])) for row in self._field(book, "bids", ()))
        asks = tuple((_dec(row[0]), _dec(row[1])) for row in self._field(book, "asks", ()))
        if not bids or not asks:
            raise ValueError("INCOMPLETE_BOOK")
        floor = _dec(self._field(book, "known_bid_floor", bids[-1][0]))
        ceiling = _dec(self._field(book, "known_ask_ceiling", asks[-1][0]))
        self._last_book = {
            "bids": bids,
            "asks": asks,
            "known_bid_floor": floor,
            "known_ask_ceiling": ceiling,
        }
        self._last_native_book_upper_us = int(self._field(book, "exchange_upper_us", native))
        self._advance(logical)
        self._reconcile(logical)
        self._last_native_us = native
        self.validate_invariants()

    def _fill(self, order: HotLineOrder, quantity: D, now: int, trade_id: str) -> D:
        amount = min(quantity, order.remaining)
        if amount <= ZERO:
            return ZERO
        if order.side == "BUY":
            order.reserved_quote -= amount * order.price
            self.inventory += amount
            self.inventory_cost += amount * order.price
            self.state = "BUY_WORKING"
            self.buy_fills += 1
        else:
            basis = self.inventory_cost / self.inventory
            proceeds = amount * order.price
            cost = amount * basis
            if proceeds <= cost:
                return ZERO
            self.inventory -= amount
            self.inventory_cost -= cost
            self.cash += proceeds
            profit = proceeds - cost
            self.realized_profit += profit
            order.realized_profit += profit
            self.state = "SELL_WORKING"
            self.sell_fills += 1
        order.filled += amount
        self._record(
            "FILL",
            now,
            order_id=order.order_id,
            side=order.side,
            price=_s(order.price),
            quantity=_s(amount),
            source_id=trade_id,
        )
        if order.side == "BUY":
            self._exact_fill_quantity += amount if order.price == self._last_trade_price else ZERO
        if order.remaining == ZERO:
            order.completed_us = now
            if order.side == "BUY":
                self.state = "WAIT_SELL"
                self._rotate_card(order.card_id, order.side, now)
            else:
                self.cycles += 1
                self.state = "WAIT_BUY"
                self._rotate_card(order.card_id, order.side, now)
            order.status = "FILLED"
            self.order = None
            self._record(
                "CYCLE" if order.side == "SELL" else "LEG_COMPLETE",
                now,
                side=order.side,
                order_id=order.order_id,
                quantity=_s(order.quantity),
                profit=_s(order.realized_profit),
            )
            if order.side == "BUY" and order.reserved_quote > ZERO:
                self.cash += order.reserved_quote
                order.reserved_quote = ZERO
        return amount

    def receive_trade(self, trade: Any, *, capture_time_us: int | None = None) -> D:
        native = int(self._field(trade, "time_us"))
        logical = int(
            capture_time_us
            if capture_time_us is not None
            else self._field(trade, "capture_time_us", native)
        )
        self._check_time(logical)
        self._observe(logical)
        trade_id = str(self._field(trade, "trade_id"))
        if trade_id in self._processed_trades:
            return ZERO
        self._processed_trades.add(trade_id)
        self._advance(logical)
        price = _dec(self._field(trade, "price"))
        available = _dec(self._field(trade, "quantity"))
        buyer_maker = bool(self._field(trade, "buyer_maker"))
        self._last_trade_price = price
        if self._last_native_book_upper_us > native:
            self._record(
                "TRADE_BLOCKED_FUTURE_BOOK",
                logical,
                trade_id=trade_id,
                native_time_us=native,
                price=_s(price),
                buyer_maker=buyer_maker,
                original_quantity=_s(available),
                consumed_quantity="0",
            )
            return ZERO
        order = self.order
        consumed = ZERO
        if (
            order is not None
            and order.status in {"ACTIVE", "CANCEL_PENDING"}
            and order.activation_evaluated_us is not None
            and native > order.activation_evaluated_us
        ):
            eligible = (order.side == "BUY" and buyer_maker and price <= order.price) or (
                order.side == "SELL" and not buyer_maker and price >= order.price
            )
            if eligible:
                if price == order.price and order.queue > ZERO:
                    ahead = min(order.queue, available)
                    order.queue -= ahead
                    available -= ahead
                    consumed += ahead
                    self._queue_blocked_quantity += ahead
                    if ahead > ZERO:
                        self._queue_blocked_events += 1
                        self._record(
                            "QUEUE_FLOW",
                            logical,
                            order_id=order.order_id,
                            quantity=_s(ahead),
                            queue_after=_s(order.queue),
                            source_id=trade_id,
                        )
                filled = self._fill(order, available, logical, trade_id)
                consumed += filled
                if price != order.price:
                    self._trade_through_quantity += filled
        self._last_native_us = native
        self._record(
            "TRADE",
            logical,
            trade_id=trade_id,
            price=_s(price),
            original_quantity=_s(_dec(self._field(trade, "quantity"))),
            consumed_quantity=_s(consumed),
            native_time_us=native,
            buyer_maker=buyer_maker,
        )
        self._reconcile(logical)
        self.validate_invariants()
        return consumed

    def cancel(self, order_id: int, *, time_us: int) -> None:
        self._check_time(time_us)
        if (
            self.order is None
            or self.order.order_id != order_id
            or self.order.status not in {"PENDING", "ACTIVE"}
        ):
            return
        if self.order.filled > ZERO:
            self._record("CANCEL_BLOCKED_PARTIAL", time_us, order_id=order_id)
            return
        self.order.status = "CANCEL_PENDING"
        self.order.cancel_us = time_us + self.cancel_latency_us
        self._record(
            "CANCEL_REQUEST", time_us, order_id=order_id, effective_us=self.order.cancel_us
        )
        self.validate_invariants()

    def validate_invariants(self) -> None:
        if self.order is not None and self.order.status not in {
            "PENDING",
            "ACTIVE",
            "CANCEL_PENDING",
        }:
            raise ValueError("M023_NONTERMINAL_ORDER_STATUS")
        if (
            self.order is not None
            and self.order.filled > ZERO
            and self.order.side == "BUY"
            and self.state not in {"BUY_WORKING", "WAIT_SELL"}
        ):
            raise ValueError("M023_BUY_SEQUENCE_DRIFT")
        if (
            self.order is not None
            and self.order.filled > ZERO
            and self.order.side == "SELL"
            and self.state != "SELL_WORKING"
        ):
            raise ValueError("M023_SELL_SEQUENCE_DRIFT")
        if len(self.buy_deck) != 100 or len(self.sell_deck) != 100:
            raise ValueError("M023_RADAR_DECK_SIZE")
        if sum(card.status == "ARMED" for card in self.radar) > 1:
            raise ValueError("M023_RADAR_ARMED_CAP")
        for deck, side in ((self.buy_deck, "BUY"), (self.sell_deck, "SELL")):
            if len({card.card_id for card in deck}) != 100 or any(
                card.side != side for card in deck
            ):
                raise ValueError("M023_RADAR_CARD_IDENTITY")
            if len({card.position for card in deck}) != 100:
                raise ValueError("M023_RADAR_POSITION_PERMUTATION")
        if self.inventory < ZERO or self.cash < ZERO:
            raise ValueError("M023_NEGATIVE_OWNERSHIP")
        reserved = self.order.reserved_quote if self.order is not None else ZERO
        if self.cash + self.inventory_cost + reserved != INITIAL_CASH + self.realized_profit:
            raise ValueError("M023_OWNERSHIP_CONSERVATION")

    def metrics(self) -> dict[str, Any]:
        mark = self._last_book["bids"][0][0] if self._last_book else ZERO
        reserved = self.order.reserved_quote if self.order is not None else ZERO
        equity = self.cash + reserved + self.inventory * mark
        open_order = self.order is not None
        waits = {
            side: [
                order.completed_us - order.submitted_us
                for order in self.orders
                if order.side == side and order.completed_us is not None
            ]
            for side in ("BUY", "SELL")
        }

        def wait_metrics(side: str) -> dict[str, str | None]:
            values = waits[side]
            return {
                "mean_seconds": (
                    None if not values else _s(D(sum(values)) / D(len(values)) / D("1000000"))
                ),
                "max_seconds": None if not values else _s(D(max(values)) / D("1000000")),
            }

        return {
            "model": "M023",
            "state": self.state,
            "total_cycles": self.cycles,
            "cycles_per_hour": _s(D(self.cycles) / D("3")),
            "buy_fills": self.buy_fills,
            "sell_fills": self.sell_fills,
            "orders_submitted": self._submission_count,
            "orders_canceled": self._cancel_count,
            "repositions": self._reprice_count,
            "max_open": self._max_open,
            "deck_rotations": self._deck_rotation_count,
            "suppressed_retries": self._suppressed_retries,
            "queue_blocked_events": self._queue_blocked_events,
            "queue_blocked_quantity": _s(self._queue_blocked_quantity),
            "active_order_time_us": self._active_order_time_us,
            "no_order_time_us": self._no_order_time_us,
            "open_order_at_cutoff": open_order,
            "open_state_at_cutoff": self.state,
            "cash": _s(self.cash),
            "reserved_quote": _s(reserved),
            "total_usdt_owned": _s(self.cash + reserved),
            "inventory": _s(self.inventory),
            "inventory_cost": _s(self.inventory_cost),
            "realized_profit": _s(self.realized_profit),
            "unrealized_pnl": _s(self.inventory * mark - self.inventory_cost),
            "marked_equity": _s(equity),
            "radar_size": len(self.radar),
            "buy_deck_size": len(self.buy_deck),
            "sell_deck_size": len(self.sell_deck),
            "partial_residual_blocked": list(self._partial_residual_blocked),
            "buy_wait": wait_metrics("BUY"),
            "sell_wait": wait_metrics("SELL"),
            "mechanism_observed": self.cycles > 0,
        }

    def finish(self, *, time_us: int) -> dict[str, Any]:
        if time_us != self.end_us:
            self._check_time(time_us)
        self._observe(time_us)
        if self.order is not None:
            self._record(
                "CUTOFF_OPEN_ORDER", time_us, order_id=self.order.order_id, state=self.state
            )
        return self.metrics()

    def _state(self) -> dict[str, Any]:
        return {
            "config": {
                "start_us": self.start_us,
                "end_us": self.end_us,
                "latency_us": self.latency_us,
                "cancel_latency_us": self.cancel_latency_us,
            },
            "cash": _s(self.cash),
            "inventory": _s(self.inventory),
            "inventory_cost": _s(self.inventory_cost),
            "realized_profit": _s(self.realized_profit),
            "cycles": self.cycles,
            "buy_fills": self.buy_fills,
            "sell_fills": self.sell_fills,
            "submission_count": self._submission_count,
            "cancel_count": self._cancel_count,
            "reprice_count": self._reprice_count,
            "suppressed_retries": self._suppressed_retries,
            "queue_blocked_quantity": _s(self._queue_blocked_quantity),
            "queue_blocked_events": self._queue_blocked_events,
            "trade_through_quantity": _s(self._trade_through_quantity),
            "exact_fill_quantity": _s(self._exact_fill_quantity),
            "active_order_time_us": self._active_order_time_us,
            "no_order_time_us": self._no_order_time_us,
            "last_observation_us": self._last_observation_us,
            "max_open": self._max_open,
            "deck_rotation_count": self._deck_rotation_count,
            "state": self.state,
            "next_order_id": self._next_order_id,
            "last_logical_us": self._last_logical_us,
            "last_native_us": self._last_native_us,
            "last_native_book_upper_us": self._last_native_book_upper_us,
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
                }
            ),
            "last_trade_price": _s(self._last_trade_price),
            "rejection_context": self._serialized_rejection_context(),
            "processed_trades": sorted(self._processed_trades),
            "orders": [
                {
                    **order.__dict__,
                    "price": _s(order.price),
                    "quantity": _s(order.quantity),
                    "filled": _s(order.filled),
                    "queue": _s(order.queue),
                    "reserved_quote": _s(order.reserved_quote),
                    "realized_profit": _s(order.realized_profit),
                }
                for order in self.orders
            ],
            "order_id": None if self.order is None else self.order.order_id,
            "buy_deck": [card.__dict__ | {"price": _s(card.price)} for card in self.buy_deck],
            "sell_deck": [card.__dict__ | {"price": _s(card.price)} for card in self.sell_deck],
            "audit": self._audit,
            "partial_residual_blocked": self._partial_residual_blocked,
        }

    def checkpoint(self) -> dict[str, Any]:
        state = self._state()
        return {
            "schema": "M023_SERIAL_HOT_LINE_V1",
            "state": state,
            "sha256": canonical_hash(state),
        }

    def restore(self, checkpoint: dict[str, Any]) -> None:
        if checkpoint.get("schema") != "M023_SERIAL_HOT_LINE_V1":
            raise ValueError("INVALID_M023_CHECKPOINT")
        state = checkpoint.get("state")
        if not isinstance(state, dict) or checkpoint.get("sha256") != canonical_hash(state):
            raise ValueError("M023_CHECKPOINT_HASH_MISMATCH")
        expected_config = {
            "start_us": self.start_us,
            "end_us": self.end_us,
            "latency_us": self.latency_us,
            "cancel_latency_us": self.cancel_latency_us,
        }
        if state.get("config") != expected_config:
            raise ValueError("M023_CHECKPOINT_CONFIG_MISMATCH")
        for key in ("cash", "inventory", "inventory_cost", "realized_profit"):
            setattr(self, key, D(state[key]))
        self.cycles = int(state["cycles"])
        self.buy_fills = int(state.get("buy_fills", 0))
        self.sell_fills = int(state.get("sell_fills", 0))
        self._submission_count = int(state.get("submission_count", 0))
        self._cancel_count = int(state.get("cancel_count", 0))
        self._reprice_count = int(state.get("reprice_count", 0))
        self._suppressed_retries = int(state.get("suppressed_retries", 0))
        self._queue_blocked_quantity = D(state.get("queue_blocked_quantity", "0"))
        self._queue_blocked_events = int(state.get("queue_blocked_events", 0))
        self._trade_through_quantity = D(state.get("trade_through_quantity", "0"))
        self._exact_fill_quantity = D(state.get("exact_fill_quantity", "0"))
        self._active_order_time_us = int(state.get("active_order_time_us", 0))
        self._no_order_time_us = int(state.get("no_order_time_us", 0))
        self._last_observation_us = int(state.get("last_observation_us", self.start_us))
        self._max_open = int(state.get("max_open", 0))
        self._deck_rotation_count = int(state.get("deck_rotation_count", 0))
        self.state = state["state"]
        self._next_order_id = int(state["next_order_id"])
        self._last_logical_us = int(state["last_logical_us"])
        self._last_native_us = int(state["last_native_us"])
        self._last_native_book_upper_us = int(state.get("last_native_book_upper_us", self.start_us))
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
            }
        )
        self._last_trade_price = D(state.get("last_trade_price", "0"))
        self._rejection_context = self._restore_rejection_context(state.get("rejection_context"))
        self._processed_trades = set(state["processed_trades"])
        self.orders = []
        for row in state["orders"]:
            row = dict(row)
            for key in (
                "price",
                "quantity",
                "filled",
                "queue",
                "reserved_quote",
                "realized_profit",
            ):
                row[key] = D(row[key])
            self.orders.append(HotLineOrder(**row))
        self.order = next(
            (item for item in self.orders if item.order_id == state["order_id"]), None
        )
        self.buy_deck = [
            HotLineCard(**{**row, "price": D(row["price"])}) for row in state["buy_deck"]
        ]
        self.sell_deck = [
            HotLineCard(**{**row, "price": D(row["price"])}) for row in state["sell_deck"]
        ]
        self._audit = list(state["audit"])
        self._partial_residual_blocked = list(state.get("partial_residual_blocked", []))

    @classmethod
    def from_checkpoint(
        cls, checkpoint: dict[str, Any], *, start_us: int, end_us: int
    ) -> SerialHotLinePingPongProbe:
        state = checkpoint.get("state")
        config = state.get("config") if isinstance(state, dict) else None
        if not isinstance(config, dict) or (
            int(config.get("start_us", -1)) != int(start_us)
            or int(config.get("end_us", -1)) != int(end_us)
        ):
            raise ValueError("M023_CHECKPOINT_CONFIG_MISMATCH")
        value = cls(
            start_us=start_us,
            end_us=end_us,
            latency_us=int(config["latency_us"]),
            cancel_latency_us=int(config["cancel_latency_us"]),
        )
        value.restore(checkpoint)
        return value


__all__ = ["HotLineCard", "HotLineOrder", "SerialHotLinePingPongProbe"]
