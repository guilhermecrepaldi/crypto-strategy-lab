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
    cancel_requested_at_us: int | None = None
    last_action_time_us: int | None = None


class L3QueueModel:
    """Observable L3 price-time queue, conservative for unresolved timestamp ties."""

    def __init__(self) -> None:
        self.levels: dict[tuple[BookKey, str, D], list[L3QueueEntry]] = {}
        self.order_level: dict[tuple[BookKey, str], tuple[BookKey, str, D]] = {}
        self.processed_events: set[tuple[BookKey, str]] = set()
        self.last_exchange_time: dict[BookKey, int] = {}
        self.gapped_books: set[BookKey] = set()
        self.awaiting_native_state: dict[tuple[BookKey, str], D] = {}
        self.ambiguous_native_removal_levels: set[tuple[BookKey, str, D]] = set()
        self._own_sequence = 1_000_000_000

    def mark_gap(self, book: BookKey) -> None:
        self.gapped_books.add(book)

    def apply_public_event(self, event: L3OrderEvent) -> None:
        identity = (event.book, event.event_id)
        if identity in self.processed_events:
            raise ValueError("M033_DUPLICATE_L3_EVENT")
        self._advance_clock(event.book, event.exchange_time_us)
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
        expected = self.awaiting_native_state.get(order_key)
        if order_key not in self.order_level:
            if event.event_type == L3EventType.DELETE and expected == ZERO:
                del self.awaiting_native_state[order_key]
                return
            raise ValueError("M033_L3_UPDATE_FOR_UNKNOWN_ORDER")
        current_key = self.order_level[order_key]
        if current_key != level_key:
            raise ValueError("M033_L3_NATIVE_UPDATE_CHANGED_PRICE")
        entry = next(row for row in self.levels[level_key] if row.order_id == event.order_id)
        if event.event_type == L3EventType.MODIFY:
            if event.remaining_quantity < ZERO:
                raise ValueError("M033_NEGATIVE_L3_REMAINING_QUANTITY")
            if expected is not None:
                if event.remaining_quantity > expected:
                    raise ValueError("M033_L3_NATIVE_STATE_RESURRECTS_CONSUMED_QUANTITY")
                entry.remaining = event.remaining_quantity
                del self.awaiting_native_state[order_key]
                if event.remaining_quantity < expected:
                    self.ambiguous_native_removal_levels.add(level_key)
                if entry.remaining == ZERO:
                    self.levels[level_key].remove(entry)
                    del self.order_level[order_key]
                return
            if event.remaining_quantity < ZERO or event.remaining_quantity >= entry.remaining:
                raise ValueError("M033_L3_MODIFY_MUST_REDUCE_VISIBLE_QUANTITY")
            entry.remaining = event.remaining_quantity
            self.ambiguous_native_removal_levels.add(level_key)
            return
        self.levels[level_key].remove(entry)
        del self.order_level[order_key]
        self.awaiting_native_state.pop(order_key, None)
        if expected != ZERO:
            self.ambiguous_native_removal_levels.add(level_key)

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
        own_columns = {row.column for row in self.levels.get(level_key, []) if row.is_ours}
        if column in own_columns:
            raise ValueError("M033_DUPLICATE_ACTIVE_COLUMN_AT_PRICE")
        if column == 2 and 1 not in own_columns:
            raise ValueError("M033_C2_REQUIRES_ACTIVE_C1_AT_PRICE")
        self._advance_clock(book, now_us)
        entry = L3QueueEntry(
            order_id,
            quantity,
            now_us,
            self._own_sequence,
            True,
            column,
            last_action_time_us=now_us,
        )
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
        if (
            not entry.is_ours
            or new_quantity <= ZERO
            or entry.cancel_requested_at_us is not None
            or entry.first_fill_time_us is not None
        ):
            raise ValueError("M033_INVALID_OWN_AMEND")
        old_quantity = entry.remaining
        target_price = key[2] if new_price is None else new_price
        loses_priority = target_price != key[2] or new_quantity > old_quantity
        new_key = (book, key[1], target_price)
        if new_key != key and any(
            row.is_ours and row.column == entry.column for row in self.levels.get(new_key, [])
        ):
            raise ValueError("M033_AMEND_WOULD_DUPLICATE_ACTIVE_COLUMN_AT_PRICE")
        self._validate_clock(book, now_us)
        self._advance_clock(book, now_us)
        entry.remaining = new_quantity
        if loses_priority:
            self.levels[key].remove(entry)
            entry.entry_time_us = now_us
            entry.message_sequence = self._own_sequence
            self._own_sequence += 1
            self.levels.setdefault(new_key, []).append(entry)
            self.order_level[(book, order_id)] = new_key
            self._sort_level(new_key)
        entry.last_action_time_us = now_us

    def cancel_request(self, book: BookKey, order_id: str, *, now_us: int) -> None:
        key = self.order_level[(book, order_id)]
        entry = next(row for row in self.levels[key] if row.order_id == order_id)
        if not entry.is_ours or entry.cancel_requested_at_us is not None:
            raise ValueError("M033_INVALID_CANCEL_REQUEST")
        self._advance_clock(book, now_us)
        entry.cancel_requested_at_us = now_us
        entry.last_action_time_us = now_us

    def cancel_ack(self, book: BookKey, order_id: str, *, now_us: int) -> D:
        key = self.order_level[(book, order_id)]
        entry = next(row for row in self.levels[key] if row.order_id == order_id)
        if (
            not entry.is_ours
            or entry.cancel_requested_at_us is None
            or entry.first_fill_time_us is not None
        ):
            raise ValueError("M033_PARTIAL_OR_PUBLIC_NOT_RECLAIMABLE")
        self._advance_clock(book, now_us)
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
        self._advance_clock(book, exchange_time_us)
        self.processed_events.add(identity)
        key = (book, side, price)
        if key in self.ambiguous_native_removal_levels:
            raise ValueError("M033_L3_EXECUTION_ORDERING_AMBIGUOUS_NO_FILL_INFERENCE")
        remaining = quantity
        fills: dict[str, D] = {}
        for entry in list(self.levels.get(key, [])):
            if remaining <= ZERO:
                break
            if entry.is_ours and entry.entry_time_us >= exchange_time_us:
                break
            amount = min(entry.remaining, remaining)
            entry.remaining -= amount
            remaining -= amount
            if entry.is_ours and amount > ZERO:
                fills[entry.order_id] = fills.get(entry.order_id, ZERO) + amount
                if entry.first_fill_time_us is None:
                    entry.first_fill_time_us = exchange_time_us
            if not entry.is_ours and amount > ZERO:
                self.awaiting_native_state[(book, entry.order_id)] = entry.remaining
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

    def _advance_clock(self, book: BookKey, now_us: int) -> None:
        self._validate_clock(book, now_us)
        self.last_exchange_time[book] = now_us

    def _validate_clock(self, book: BookKey, now_us: int) -> None:
        previous = self.last_exchange_time.get(book)
        if previous is not None and now_us < previous:
            raise ValueError("M033_OUT_OF_ORDER_L3_EVENT")


@dataclass(frozen=True)
class L3L2AblationRow:
    order_id: str
    l3_queue_ahead: D
    l2_queue_ahead: D
    difference: D


def compare_l3_to_l2(
    l3: L3QueueModel,
    l2: L2QueueModel,
    *,
    book: BookKey,
    order_id: str,
) -> L3L2AblationRow:
    l3_ahead = l3.queue_ahead(book, order_id)
    l2_ahead = l2.queue_ahead(book, order_id)
    return L3L2AblationRow(order_id, l3_ahead, l2_ahead, l2_ahead - l3_ahead)


class L3ToL2AblationHarness:
    """Two isolated queue states fed from one immutable L3-derived event stream."""

    def __init__(self) -> None:
        self.l3 = L3QueueModel()
        self.l2 = L2QueueModel()

    def apply_public_event(self, event: L3OrderEvent) -> None:
        self.l3.apply_public_event(event)

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
        observed_depth = self.l3.aggregate_l2(book).get((side, price), ZERO)
        self.l3.activate_own(
            book,
            side=side,
            price=price,
            order_id=order_id,
            quantity=quantity,
            column=column,
            now_us=now_us,
        )
        self.l2.activate(
            book,
            side=side,
            price=price,
            order_id=order_id,
            column=column,
            quantity=quantity,
            observed_public_queue=observed_depth,
            now_us=now_us,
        )

    def compare(self, book: BookKey, order_id: str) -> L3L2AblationRow:
        return compare_l3_to_l2(self.l3, self.l2, book=book, order_id=order_id)

    def consume_execution(
        self,
        book: BookKey,
        *,
        event_id: str,
        side: str,
        price: D,
        quantity: D,
        exchange_time_us: int,
    ) -> tuple[dict[str, D], dict[str, D]]:
        l3_fills = self.l3.consume_execution(
            book,
            event_id=event_id,
            side=side,
            price=price,
            quantity=quantity,
            exchange_time_us=exchange_time_us,
        )
        l2_fills = self.l2.consume(
            book,
            event_id=event_id,
            side=side,
            price=price,
            quantity=quantity,
            now_us=exchange_time_us,
        )
        return l3_fills, l2_fills


__all__ = [
    "L2QueueModel",
    "L3L2AblationRow",
    "L3QueueEntry",
    "L3QueueModel",
    "L3ToL2AblationHarness",
    "QueueModel",
    "compare_l3_to_l2",
]
