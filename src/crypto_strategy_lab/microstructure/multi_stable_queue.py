"""Causal PUBLIC -> C1 -> C2 queue state and prefix-only estimators for M032."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import ROUND_CEILING
from statistics import median

from crypto_strategy_lab.microstructure.multi_stable_models import ZERO, D


@dataclass
class OwnQueueOrder:
    order_id: str
    column: int
    quantity: D
    remaining: D
    activated_at_us: int
    activation_sequence: int
    public_barrier_before: D = ZERO
    first_fill_at_us: int | None = None
    filled_at_us: int | None = None


@dataclass
class QueueGroup:
    book: str
    side: str
    price: D
    public_remaining: D
    own_orders: deque[OwnQueueOrder] = field(default_factory=deque)


@dataclass(frozen=True)
class QueueEstimate:
    queue_ahead: D
    compatible_flow_per_second: D
    expected_clear_seconds: D | None
    fill_probability_30s: D
    fill_probability_1m: D
    fill_probability_3m: D
    fill_probability_5m: D


class CausalQueueEstimator:
    """Shared queue accounting; estimates use events observed no later than ``now``."""

    def __init__(self, *, flow_window_us: int = 300_000_000) -> None:
        if flow_window_us <= 0:
            raise ValueError("M032_INVALID_FLOW_WINDOW")
        self.flow_window_us = flow_window_us
        self.groups: dict[tuple[str, str, D], QueueGroup] = {}
        self.order_group: dict[str, tuple[str, str, D]] = {}
        self.processed_event_ids: set[str] = set()
        self.compatible_flow: dict[tuple[str, str, D], deque[tuple[int, D]]] = {}
        self.first_fill_waits_us: dict[tuple[str, str, D], list[int]] = {}
        self.full_fill_waits_us: dict[tuple[str, str, D], list[int]] = {}
        self.last_time_us = -1
        self.next_activation_sequence = 0

    def activate(
        self,
        *,
        book: str,
        side: str,
        price: D,
        order_id: str,
        column: int,
        quantity: D,
        observed_public_queue: D,
        now_us: int,
    ) -> OwnQueueOrder:
        self._causal(now_us)
        if side not in {"BUY", "SELL"} or column not in {1, 2} or quantity <= ZERO:
            raise ValueError("M032_INVALID_QUEUE_ORDER")
        if order_id in self.order_group:
            raise ValueError("M032_DUPLICATE_QUEUE_ORDER")
        key = (book, side, price)
        group = self.groups.get(key)
        if group is None:
            group = QueueGroup(book, side, price, max(ZERO, observed_public_queue))
            self.groups[key] = group
        active_orders = [row for row in group.own_orders if row.remaining > ZERO]
        if not active_orders:
            # A completely new queue epoch has no inherited priority.
            group.public_remaining = max(ZERO, observed_public_queue)
        # Public depth newly observed after an existing own order is represented
        # as a later cohort. It is ahead of the new order, but never jumps ahead
        # of an older surviving own order.
        represented_public = group.public_remaining + sum(
            (row.public_barrier_before for row in active_orders), ZERO
        )
        later_public_cohort = (
            max(ZERO, observed_public_queue - represented_public) if active_orders else ZERO
        )
        if any(row.column == column for row in group.own_orders if row.remaining > ZERO):
            raise ValueError("M032_DUPLICATE_COLUMN_AT_PRICE")
        order = OwnQueueOrder(
            order_id=order_id,
            column=column,
            quantity=quantity,
            remaining=quantity,
            activated_at_us=now_us,
            activation_sequence=self.next_activation_sequence,
            public_barrier_before=later_public_cohort,
        )
        self.next_activation_sequence += 1
        group.own_orders.append(order)
        group.own_orders = deque(
            sorted(
                group.own_orders,
                key=lambda row: (row.activated_at_us, row.activation_sequence),
            )
        )
        self.order_group[order_id] = key
        self._validate_group(group)
        return order

    def cancel_ack(self, order_id: str, *, now_us: int) -> D:
        self._causal(now_us)
        group = self.groups[self.order_group[order_id]]
        order = next(row for row in group.own_orders if row.order_id == order_id)
        if order.remaining != order.quantity:
            raise ValueError("M032_PARTIAL_OR_FILLED_QUEUE_NOT_RECLAIMABLE")
        group.own_orders.remove(order)
        del self.order_group[order_id]
        self._validate_group(group)
        return order.remaining

    def consume_compatible_flow(
        self,
        *,
        event_id: str,
        book: str,
        side: str,
        price: D,
        quantity: D,
        now_us: int,
    ) -> dict[str, D]:
        self._causal(now_us)
        if event_id in self.processed_event_ids:
            raise ValueError("M032_DUPLICATE_TRADE_QUANTITY")
        if quantity < ZERO:
            raise ValueError("M032_NEGATIVE_FLOW")
        self.processed_event_ids.add(event_id)
        key = (book, side, price)
        self.compatible_flow.setdefault(key, deque()).append((now_us, quantity))
        group = self.groups.get(key)
        if group is None:
            return {}
        remaining = quantity
        public = min(remaining, group.public_remaining)
        group.public_remaining -= public
        remaining -= public
        fills: dict[str, D] = {}
        for order in group.own_orders:
            if remaining <= ZERO:
                break
            public = min(remaining, order.public_barrier_before)
            order.public_barrier_before -= public
            remaining -= public
            if remaining <= ZERO:
                break
            amount = min(order.remaining, remaining)
            order.remaining -= amount
            remaining -= amount
            if amount > ZERO:
                fills[order.order_id] = amount
                if order.first_fill_at_us is None:
                    order.first_fill_at_us = now_us
                    self.first_fill_waits_us.setdefault(key, []).append(
                        now_us - order.activated_at_us
                    )
            if order.remaining == ZERO and order.filled_at_us is None:
                order.filled_at_us = now_us
                self.full_fill_waits_us.setdefault(key, []).append(now_us - order.activated_at_us)
        self._validate_group(group)
        return fills

    def queue_ahead(self, order_id: str) -> D:
        group = self.groups[self.order_group[order_id]]
        ahead = group.public_remaining
        for order in group.own_orders:
            ahead += order.public_barrier_before
            if order.order_id == order_id:
                return ahead
            ahead += order.remaining
        raise KeyError(order_id)

    def estimate(self, order_id: str, *, now_us: int) -> QueueEstimate:
        self._causal(now_us)
        key = self.order_group[order_id]
        samples = self.compatible_flow.setdefault(key, deque())
        cutoff = now_us - self.flow_window_us
        while samples and samples[0][0] < cutoff:
            samples.popleft()
        observed = sum((quantity for _, quantity in samples), ZERO)
        if not samples:
            rate = ZERO
        else:
            span_us = max(1, now_us - max(cutoff, samples[0][0]))
            rate = observed / (D(span_us) / D(1_000_000))
        ahead = self.queue_ahead(order_id)
        clear = None if rate <= ZERO else ahead / rate

        def probability(horizon_seconds: int) -> D:
            if clear is None:
                return ZERO
            if clear <= ZERO:
                return D(1)
            return min(D(1), D(horizon_seconds) / clear)

        return QueueEstimate(
            queue_ahead=ahead,
            compatible_flow_per_second=rate,
            expected_clear_seconds=clear,
            fill_probability_30s=probability(30),
            fill_probability_1m=probability(60),
            fill_probability_3m=probability(180),
            fill_probability_5m=probability(300),
        )

    def wait_distribution(self, *, book: str, side: str, price: D) -> dict[str, int | None]:
        first_waits = self.first_fill_waits_us.get((book, side, price), [])
        waits = self.full_fill_waits_us.get((book, side, price), [])
        return {
            "MEDIAN_TIME_TO_FIRST_FILL_US": int(median(first_waits)) if first_waits else None,
            "MEDIAN_TIME_TO_FULL_FILL_US": int(median(waits)) if waits else None,
            "P90_TIME_TO_FULL_FILL_US": self._percentile(waits, D("0.90")),
            "P95_TIME_TO_FULL_FILL_US": self._percentile(waits, D("0.95")),
        }

    def _causal(self, now_us: int) -> None:
        if now_us < self.last_time_us:
            raise ValueError("M032_FUTURE_OR_REORDERED_QUEUE_EVENT")
        self.last_time_us = now_us

    @staticmethod
    def _percentile(values: list[int], rank: D) -> int | None:
        if not values:
            return None
        ordered = sorted(values)
        index = int(((D(len(ordered)) - D(1)) * rank).to_integral_value(rounding=ROUND_CEILING))
        return ordered[index]

    @staticmethod
    def _validate_group(group: QueueGroup) -> None:
        active = [row for row in group.own_orders if row.remaining > ZERO]
        if len(active) > 2:
            raise ValueError("M032_MAX_TWO_COLUMNS_PER_PRICE")
        ordered = sorted(
            active,
            key=lambda row: (row.activated_at_us, row.activation_sequence),
        )
        if active != ordered:
            raise ValueError("M032_OWN_FIFO_ORDER_DRIFT")
        if len({row.column for row in active}) != len(active):
            raise ValueError("M032_DUPLICATE_ACTIVE_COLUMN")
        if group.public_remaining < ZERO or any(row.remaining < ZERO for row in active):
            raise ValueError("M032_NEGATIVE_QUEUE")


__all__ = ["CausalQueueEstimator", "OwnQueueOrder", "QueueEstimate", "QueueGroup"]
