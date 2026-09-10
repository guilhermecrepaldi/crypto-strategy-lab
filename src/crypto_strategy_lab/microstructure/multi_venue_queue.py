"""Venue-isolated L2 and observable-order L3 queue models for M033."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crypto_strategy_lab.microstructure.multi_stable_queue import CausalQueueEstimator
from crypto_strategy_lab.microstructure.multi_venue_models import (
    ZERO,
    BookKey,
    D,
    L3EventType,
    L3OrderEvent,
)


class QueueModel(Protocol):
    def queue_ahead(self, book: BookKey, order_id: str) -> D: ...


class L2QueueModel:
    """Namespace the unchanged conservative M032 L2 estimator by physical book."""

    def __init__(self) -> None:
        self.models: dict[BookKey, CausalQueueEstimator] = {}

    def _model(self, book: BookKey) -> CausalQueueEstimator:
        return self.models.setdefault(book, CausalQueueEstimator())

    def activate(
        self,
        book: BookKey,
        *,
        side: str,
        price: D,
        order_id: str,
        column: int,
        quantity: D,
        observed_public_queue: D,
        now_us: int,
    ) -> None:
        self._model(book).activate(
            book=book.canonical_id,
            side=side,
            price=price,
            order_id=order_id,
            column=column,
            quantity=quantity,
            observed_public_queue=observed_public_queue,
            now_us=now_us,
        )

    def queue_ahead(self, book: BookKey, order_id: str) -> D:
        return self._model(book).queue_ahead(order_id)

    def consume(
        self,
        book: BookKey,
        *,
        event_id: str,
        side: str,
        price: D,
        quantity: D,
        now_us: int,
    ) -> dict[str, D]:
        return self._model(book).consume_compatible_flow(
            event_id=event_id,
            book=book.canonical_id,
            side=side,
            price=price,
            quantity=quantity,
            now_us=now_us,
        )


@dataclass
class L3QueueEntry:
    order_id: str
    remaining: D
    entry_time_us: int
    message_sequence: int
    is_ours: bool
    column: int | None = None
    first_fill_time_us: int | None = None


class L3QueueModel:
    """Observable L3 price-time queue, conservative for unresolved timestamp ties."""

    def __init__(self) -> None:
        self.levels: dict[tuple[BookKey, str, D], list[L3QueueEntry]] = {}
        self.order_level: dict[tuple[BookKey, str], tuple[BookKey, str, D]] = {}
        self.processed_events: set[tuple[BookKey, str]] = set()
        self.last_exchange_time: dict[BookKey, int] = {}
        self.gapped_books: set[BookKey] = set()
        self._own_sequence = 1_000_000_000

    def mark_gap(self, book: BookKey) -> None:
        self.gapped_books.add(book)

    def apply_public_event(self, event: L3OrderEvent) -> None:
        identity = (event.book, event.event_id)
        if identity in self.processed_events:
            raise ValueError("M033_DUPLICATE_L3_EVENT")
        previous = self.last_exchange_time.get(event.book)
        if previous is not None and event.exchange_time_us < previous:
            raise ValueError("M033_OUT_OF_ORDER_L3_EVENT")
        self.last_exchange_time[event.book] = event.exchange_time_us
        self.processed_events.add(identity)
        order_key = (event.book, event.order_id)
        level_key = (event.book, event.side, event.price)
        if event.event_type == L3EventType.ADD:
            if order_key in self.order_level or event.remaining_quantity <= ZERO:
                raise ValueError("M033_DUPLICATE_OR_EMPTY_L3_ADD")
            entry = L3QueueEntry(
                event.order_id,
                event.remaining_quantity,
                event.order_entry_time_us,
                event.message_sequence,
                False,
            )
            self.levels.setdefault(level_key, []).append(entry)
            self.order_level[order_key] = level_key
            self._sort_level(level_key)
            return
        if order_key not in self.order_level:
            raise ValueError("M033_L3_UPDATE_FOR_UNKNOWN_ORDER")
        current_key = self.order_level[order_key]
        if current_key != level_key:
            raise ValueError("M033_L3_NATIVE_UPDATE_CHANGED_PRICE")
        entry = next(row for row in self.levels[level_key] if row.order_id == event.order_id)
        if event.event_type == L3EventType.MODIFY:
            if event.remaining_quantity < ZERO or event.remaining_quantity >= entry.remaining:
                raise ValueError("M033_L3_MODIFY_MUST_REDUCE_VISIBLE_QUANTITY")
            entry.remaining = event.remaining_quantity
            return
        self.levels[level_key].remove(entry)
        del self.order_level[order_key]

    def activate_own(
        self,
        book: BookKey,
        *,
        side: str,
        price: D,
        order_id: str,
        quantity: D,
        column: int,
        now_us: int,
    ) -> None:
        if self.gapped_books and book in self.gapped_books:
            raise ValueError("M033_L3_BOOK_GAPPED")
        if column not in {1, 2} or quantity <= ZERO:
            raise ValueError("M033_INVALID_OWN_L3_ORDER")
        order_key = (book, order_id)
        if order_key in self.order_level:
            raise ValueError("M033_DUPLICATE_OWN_L3_ORDER")
        level_key = (book, side, price)
        entry = L3QueueEntry(order_id, quantity, now_us, self._own_sequence, True, column)
        self._own_sequence += 1
        self.levels.setdefault(level_key, []).append(entry)
        self.order_level[order_key] = level_key
        self._sort_level(level_key)

    def amend_own(
        self,
        book: BookKey,
        order_id: str,
        *,
        new_quantity: D,
        now_us: int,
        new_price: D | None = None,
    ) -> None:
        key = self.order_level[(book, order_id)]
        entry = next(row for row in self.levels[key] if row.order_id == order_id)
        if not entry.is_ours or new_quantity <= ZERO:
            raise ValueError("M033_INVALID_OWN_AMEND")
        old_quantity = entry.remaining
        target_price = key[2] if new_price is None else new_price
        loses_priority = target_price != key[2] or new_quantity > old_quantity
        entry.remaining = new_quantity
        if loses_priority:
            self.levels[key].remove(entry)
            new_key = (book, key[1], target_price)
            entry.entry_time_us = now_us
            entry.message_sequence = self._own_sequence
            self._own_sequence += 1
            self.levels.setdefault(new_key, []).append(entry)
            self.order_level[(book, order_id)] = new_key
            self._sort_level(new_key)

    def cancel_ack(self, book: BookKey, order_id: str) -> D:
        key = self.order_level[(book, order_id)]
        entry = next(row for row in self.levels[key] if row.order_id == order_id)
        if not entry.is_ours or entry.first_fill_time_us is not None:
            raise ValueError("M033_PARTIAL_OR_PUBLIC_NOT_RECLAIMABLE")
        self.levels[key].remove(entry)
        del self.order_level[(book, order_id)]
        return entry.remaining

    def queue_ahead(self, book: BookKey, order_id: str) -> D:
        key = self.order_level[(book, order_id)]
        ahead = ZERO
        for entry in self.levels[key]:
            if entry.order_id == order_id:
                return ahead
            ahead += entry.remaining
        raise KeyError(order_id)

    def public_orders_ahead(self, book: BookKey, order_id: str) -> int:
        key = self.order_level[(book, order_id)]
        count = 0
        for entry in self.levels[key]:
            if entry.order_id == order_id:
                return count
            count += int(not entry.is_ours)
        raise KeyError(order_id)

    def consume_execution(
        self,
        book: BookKey,
        *,
        event_id: str,
        side: str,
        price: D,
        quantity: D,
        exchange_time_us: int,
    ) -> dict[str, D]:
        identity = (book, event_id)
        if identity in self.processed_events:
            raise ValueError("M033_DUPLICATE_L3_EVENT")
        if book in self.gapped_books:
            raise ValueError("M033_L3_BOOK_GAPPED")
        previous = self.last_exchange_time.get(book)
        if previous is not None and exchange_time_us < previous:
            raise ValueError("M033_OUT_OF_ORDER_L3_EVENT")
        self.last_exchange_time[book] = exchange_time_us
        self.processed_events.add(identity)
        key = (book, side, price)
        remaining = quantity
        fills: dict[str, D] = {}
        for entry in list(self.levels.get(key, [])):
            if remaining <= ZERO:
                break
            amount = min(entry.remaining, remaining)
            entry.remaining -= amount
            remaining -= amount
            if entry.is_ours and amount > ZERO:
                fills[entry.order_id] = fills.get(entry.order_id, ZERO) + amount
                if entry.first_fill_time_us is None:
                    entry.first_fill_time_us = exchange_time_us
            if entry.remaining == ZERO:
                self.levels[key].remove(entry)
                del self.order_level[(book, entry.order_id)]
        return fills

    def aggregate_l2(self, book: BookKey) -> dict[tuple[str, D], D]:
        result: dict[tuple[str, D], D] = {}
        for (current_book, side, price), entries in self.levels.items():
            if current_book != book:
                continue
            public = sum((row.remaining for row in entries if not row.is_ours), ZERO)
            if public > ZERO:
                result[(side, price)] = public
        return result

    def _sort_level(self, key: tuple[BookKey, str, D]) -> None:
        # Public orders at unresolved identical timestamps precede our simulated
        # order. Within the native public cohort, recorder order is deterministic
        # but is not promoted as proven exchange priority.
        self.levels[key].sort(
            key=lambda row: (row.entry_time_us, 1 if row.is_ours else 0, row.message_sequence)
        )


@dataclass(frozen=True)
class L3L2AblationRow:
    order_id: str
    l3_queue_ahead: D
    l2_queue_ahead: D
    difference: D


def compare_l3_to_l2(
    l3: L3QueueModel,
    *,
    book: BookKey,
    order_id: str,
    side: str,
    price: D,
) -> L3L2AblationRow:
    l3_ahead = l3.queue_ahead(book, order_id)
    l2_depth = l3.aggregate_l2(book).get((side, price), ZERO)
    return L3L2AblationRow(order_id, l3_ahead, l2_depth, l2_depth - l3_ahead)


__all__ = [
    "L2QueueModel",
    "L3L2AblationRow",
    "L3QueueEntry",
    "L3QueueModel",
    "QueueModel",
    "compare_l3_to_l2",
]
