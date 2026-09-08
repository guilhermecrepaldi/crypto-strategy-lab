"""Observed book evidence for the unchanged M015 ledger; no replay or strategy.

The caller validates raw sequence and canonical trade bindings first. The monthly
driver uses capture-arrival timers and keeps native exchange timestamps for print
eligibility; strategy arrays expose only the received canonical prefix. The engine
also supports a strict exchange-clock diagnostic mode. Every book/trade invokes
the required lifecycle callback, including IOC settlements on book events.
No external account or data access exists here.
"""

from __future__ import annotations

import copy
from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Any, Literal, overload

from crypto_strategy_lab.domain import canonical_hash

from .b10_reality import BookEnvelope, ExecutionProfile, Order, SymbolRules, Trade, _encode
from .high_uptime_recovery import (
    M016_DEADLINE_POLICY_HASH,
    B10ReserveReplay,
    HighUptimeExecution,
)
from .serial_replay import EVENT_ORDER_SCALE, _switch

ZERO = Decimal(0)
Envelope = Literal["CONSERVATIVE_QUEUE", "PRICE_PRIORITY"]
Levels = tuple[tuple[Decimal, Decimal], ...]


def _price_key(price: Decimal) -> str:
    value = format(price, "f")
    return value.rstrip("0").rstrip(".") if "." in value else value


def _money(value: Decimal, *, positive: bool = False) -> None:
    if not isinstance(value, Decimal):
        raise ValueError("DECIMAL_REQUIRED")
    if not value.is_finite() or value < ZERO or (positive and value == ZERO):
        raise ValueError("INVALID_OBSERVED_VALUE")


@dataclass(frozen=True)
class ObservedBookBatch:
    """A complete validated book, not one CSV row or an unvalidated delta.

    Known coverage includes every bid price >= known_bid_floor and every ask
    price <= known_ask_ceiling. Absence outside those regions is unknown.
    capture_order is a global raw-stream ordinal shared with bound trades.
    """

    exchange_time_us: int
    capture_time_us: int
    capture_order: int
    native_update_id: int
    bids: Levels
    asks: Levels
    known_bid_floor: Decimal
    known_ask_ceiling: Decimal
    sequence_validated: bool
    is_snapshot: bool = False
    changes: tuple[tuple[str, Decimal, Decimal], ...] | None = None
    exchange_upper_us: int | None = None
    exchange_precision: str = "EXACT_MICROSECONDS"


class ObservedL2Execution(HighUptimeExecution):
    """Only replace evidence; reuse the canonical accounting and fill methods."""

    def __init__(
        self,
        profile: ExecutionProfile,
        rules: SymbolRules,
        *,
        envelope: Envelope,
        on_transition: Callable[[dict[str, Any]], None],
        clock_mode: Literal["EXCHANGE_STRICT", "CAPTURE_ARRIVAL"] = "EXCHANGE_STRICT",
        deadline_policy_hash: str | None = None,
    ) -> None:
        if envelope not in ("CONSERVATIVE_QUEUE", "PRICE_PRIORITY"):
            raise ValueError("UNREGISTERED_EXECUTION_ENVELOPE")
        if not callable(on_transition):
            raise ValueError("LIFECYCLE_CALLBACK_REQUIRED")
        if clock_mode not in ("EXCHANGE_STRICT", "CAPTURE_ARRIVAL"):
            raise ValueError("UNREGISTERED_CLOCK_MODE")
        super().__init__(
            profile,
            rules,
            b10_owner_reserve=True,
            priority_trade_through=envelope == "PRICE_PRIORITY",
            deadline_policy_hash=deadline_policy_hash,
        )
        self.envelope = envelope
        self.clock_mode = clock_mode
        self.on_transition = on_transition
        self.observed_capture: tuple[int, int] = (-1, -1)
        self.observed_exchange_us = -1
        self.observed_native_update_id = -1
        self.native_book_exchange_us = -1
        self.native_book_exchange_upper_us = -1
        self.last_native_trade: tuple[int, int] | None = None
        self.displayed_bids: Levels = ()
        self.displayed_asks: Levels = ()
        self.known_bid_floor = ZERO
        self.known_ask_ceiling = ZERO
        # String keys make inherited JSON checkpoint encoding exact/reversible.
        self.bid_consumption_debt: dict[str, Decimal] = {}
        self.consumed_bid_prices: dict[str, bool] = {}
        self.activation_observations: list[dict[str, Any]] = []
        self.bid_level_indexes: dict[str, int] = {}
        self.pending_sample_seam = False

    def begin_sample_seam(self, timestamp: int, source_date: str) -> None:
        """Break observation continuity, never financial or order continuity."""
        self.book_valid = False
        self.pending_sample_seam = True
        self.observed_native_update_id = -1
        self._record(
            "SYNTHETIC_SAMPLE_SEAM",
            time_us=timestamp,
            source_date=source_date,
            queue_preserved=True,
            ledger_preserved=True,
        )

    def _check_capture(self, exchange_us: int, capture_us: int, order: int) -> None:
        if any(type(value) is not int or value < 0 for value in (exchange_us, capture_us, order)):
            raise ValueError("INVALID_OBSERVATION_CLOCK")
        previous_time, previous_order = self.observed_capture
        if capture_us < previous_time or order <= previous_order:
            raise ValueError("NONCAUSAL_CAPTURE_ORDER")
        if self.clock_mode == "EXCHANGE_STRICT" and exchange_us < self.observed_exchange_us:
            raise ValueError("UNRESOLVED_TWO_CLOCK_MAPPING")

    def _engine_time(self, exchange_us: int, capture_us: int) -> int:
        return capture_us if self.clock_mode == "CAPTURE_ARRIVAL" else exchange_us

    def _state(self) -> dict[str, Any]:
        order = self.order
        return {
            "entry_us": self.entry_us,
            "inventory": str(self.inventory),
            "cash": str(self.cash),
            "reserve": str(self.reserve),
            "order_id": order.order_id if order is not None else None,
            "order_status": order.status if order is not None else None,
            "ordinary_cycles": self.counts["FULLY_FILLED_CYCLES"],
            "releases": self.counts["RELEASE_FILLED"],
        }

    def _notify(self, cause: str, before: dict[str, Any]) -> None:
        self.on_transition(
            {
                "cause": cause,
                "exchange_time_us": self.observed_exchange_us,
                "engine_time_us": self._engine_time(
                    self.observed_exchange_us, self.observed_capture[0]
                ),
                "capture_time_us": self.observed_capture[0],
                "capture_order": self.observed_capture[1],
                "before": before,
                "after": self._state(),
            }
        )

    def observed_book(self, batch: ObservedBookBatch) -> None:
        self._check_capture(batch.exchange_time_us, batch.capture_time_us, batch.capture_order)
        if batch.sequence_validated is not True:
            raise ValueError("INDEPENDENT_SEQUENCE_VALIDATION_REQUIRED")
        if type(batch.native_update_id) is not int or batch.native_update_id < 0:
            raise ValueError("NATIVE_UPDATE_ID_REQUIRED")
        if batch.exchange_upper_us is not None and (
            type(batch.exchange_upper_us) is not int
            or batch.exchange_upper_us < batch.exchange_time_us
        ):
            raise ValueError("INVALID_BOOK_TIMESTAMP_PRECISION_BOUND")
        if batch.native_update_id < self.observed_native_update_id:
            raise ValueError("NATIVE_UPDATE_REGRESSION")
        if (
            batch.changes is not None
            and not batch.is_snapshot
            and not self.pending_sample_seam
            and self.displayed_bids
            and all(
                side != "bid" or (quantity > 0 and _price_key(price) in self.bid_level_indexes)
                for side, price, quantity in batch.changes
            )
        ):
            self._validated_quantity_update(batch)
            return
        if not batch.bids or not batch.asks:
            raise ValueError("TWO_SIDED_OBSERVED_BOOK_REQUIRED")
        _money(batch.known_bid_floor, positive=True)
        _money(batch.known_ask_ceiling, positive=True)
        for levels, descending in ((batch.bids, True), (batch.asks, False)):
            prices = []
            for price, quantity in levels:
                _money(price, positive=True)
                _money(quantity, positive=True)  # Deleted levels are already absent.
                if price % self.rules.tick_size:
                    raise ValueError("OBSERVED_PRICE_GRID")
                prices.append(price)
            if prices != sorted(set(prices), reverse=descending):
                raise ValueError("UNSORTED_OR_DUPLICATE_OBSERVED_LEVEL")
        if batch.bids[0][0] >= batch.asks[0][0]:
            raise ValueError("CROSSED_OBSERVED_BOOK")
        if batch.native_update_id == self.observed_native_update_id and (
            batch.bids != self.displayed_bids or batch.asks != self.displayed_asks
        ):
            raise ValueError("CHANGED_BOOK_WITHOUT_NATIVE_UPDATE")
        if batch.known_bid_floor > batch.bids[0][0] or (batch.known_ask_ceiling < batch.asks[0][0]):
            raise ValueError("INVALID_KNOWN_COVERAGE")
        before = self._state()
        previous_displayed = dict(self.displayed_bids)
        previous_available = {price: quantity for price, quantity in self.bids}
        self.displayed_bids, self.displayed_asks = batch.bids, batch.asks
        self.known_bid_floor, self.known_ask_ceiling = (
            batch.known_bid_floor,
            batch.known_ask_ceiling,
        )
        self.observed_capture = batch.capture_time_us, batch.capture_order
        self.observed_exchange_us = batch.exchange_time_us
        self.observed_native_update_id = batch.native_update_id
        self.native_book_exchange_us = batch.exchange_time_us
        self.native_book_exchange_upper_us = (
            batch.exchange_upper_us
            if batch.exchange_upper_us is not None
            else batch.exchange_time_us
        )
        with localcontext() as context:
            context.prec = 128
            available = []
            current_prices = {price for price, _ in batch.bids}
            for price in previous_displayed.keys() - current_prices:
                self.bid_consumption_debt[_price_key(price)] = ZERO
                if _price_key(price) in self.consumed_bid_prices:
                    self._record(
                        "OBSERVED_BUDGET_CHANGE",
                        price=str(price),
                        old_displayed=str(previous_displayed[price]),
                        old_available=str(previous_available.get(price, ZERO)),
                        displayed="0",
                        available="0",
                        book_source_id=batch.capture_order,
                    )
            for price, quantity in batch.bids:
                old_quantity = previous_displayed.get(price, ZERO)
                old_available = previous_available.get(price, ZERO)
                budget = (
                    min(quantity, old_available)
                    if self.pending_sample_seam and _price_key(price) in self.bid_consumption_debt
                    else max(ZERO, min(quantity, old_available + quantity - old_quantity))
                )
                available.append((price, budget))
                self.bid_consumption_debt[_price_key(price)] = quantity - budget
                if _price_key(price) in self.consumed_bid_prices and quantity != old_quantity:
                    self._record(
                        "OBSERVED_BUDGET_CHANGE",
                        price=str(price),
                        old_displayed=str(old_quantity),
                        old_available=str(old_available),
                        displayed=str(quantity),
                        available=str(budget),
                        book_source_id=batch.capture_order,
                        seam_clamp=self.pending_sample_seam,
                    )
        if self.pending_sample_seam and self.order is not None:
            self._record(
                "SYNTHETIC_SEAM_ORDER_CARRY",
                order_id=self.order.order_id,
                queue_remaining=str(self.order.queue),
                priority="UNKNOWN_CROSS_SEAM_TIME_PRIORITY",
                crossed=(
                    self.order.price >= batch.asks[0][0]
                    if self.order.side == "BUY"
                    else self.order.price <= batch.bids[0][0]
                ),
            )
        self.pending_sample_seam = False
        self._record(
            "OBSERVED_BOOK",
            time_us=batch.exchange_time_us,
            capture_time_us=batch.capture_time_us,
            capture_order=batch.capture_order,
            native_update_id=batch.native_update_id,
            is_snapshot=batch.is_snapshot,
            exchange_upper_us=self.native_book_exchange_upper_us,
            exchange_precision=batch.exchange_precision,
        )
        # Parent calls our _advance, so activation uses the newly installed book.
        super().book(
            self._engine_time(batch.exchange_time_us, batch.capture_time_us),
            batch.capture_order,
            available,
            batch.asks[0][0],
        )
        self.bid_level_indexes = {_price_key(price): i for i, (price, _) in enumerate(batch.bids)}
        self._notify("BOOK", before)

    def _validated_quantity_update(self, batch: ObservedBookBatch) -> None:
        """Fast path only for already validated native changes on existing bids.

        The campaign runner hashes and validates the entire source before using
        changes. Structural bid changes and snapshots use the full checked path.
        Untouched levels are not rescanned on every 100ms message.
        """
        assert batch.changes is not None
        if not batch.bids or not batch.asks or batch.bids[0][0] >= batch.asks[0][0]:
            raise ValueError("INVALID_VALIDATED_BOOK")
        if batch.native_update_id == self.observed_native_update_id and batch.changes:
            raise ValueError("CHANGED_BOOK_WITHOUT_NATIVE_UPDATE")
        for side, price, quantity in batch.changes:
            if side not in ("bid", "ask"):
                raise ValueError("INVALID_OBSERVED_SIDE")
            _money(price, positive=True)
            _money(quantity)
            if price % self.rules.tick_size:
                raise ValueError("OBSERVED_PRICE_GRID")
        before = self._state()
        with localcontext() as context:
            context.prec = 128
            for side, price, quantity in batch.changes:
                if side != "bid":
                    continue
                key = _price_key(price)
                index = self.bid_level_indexes[key]
                old_quantity = self.displayed_bids[index][1]
                old_available = self.bids[index][1]
                budget = max(ZERO, min(quantity, old_available + quantity - old_quantity))
                if batch.bids[index] != (price, quantity):
                    raise ValueError("VALIDATED_DELTA_FULL_BOOK_MISMATCH")
                self.bids[index][1] = budget
                self.bid_consumption_debt[key] = quantity - budget
                if key in self.consumed_bid_prices and quantity != old_quantity:
                    self._record(
                        "OBSERVED_BUDGET_CHANGE",
                        price=str(price),
                        old_displayed=str(old_quantity),
                        old_available=str(old_available),
                        displayed=str(quantity),
                        available=str(budget),
                        book_source_id=batch.capture_order,
                    )
        self.displayed_bids, self.displayed_asks = batch.bids, batch.asks
        self.known_bid_floor, self.known_ask_ceiling = (
            batch.known_bid_floor,
            batch.known_ask_ceiling,
        )
        self.observed_capture = batch.capture_time_us, batch.capture_order
        self.observed_exchange_us = batch.exchange_time_us
        self.observed_native_update_id = batch.native_update_id
        self.native_book_exchange_us = batch.exchange_time_us
        self.native_book_exchange_upper_us = (
            batch.exchange_upper_us
            if batch.exchange_upper_us is not None
            else batch.exchange_time_us
        )
        self.last_book_us = self._engine_time(batch.exchange_time_us, batch.capture_time_us)
        self.book_id, self.ask, self.book_valid = batch.capture_order, batch.asks[0][0], True
        self._record(
            "OBSERVED_BOOK",
            time_us=batch.exchange_time_us,
            capture_time_us=batch.capture_time_us,
            capture_order=batch.capture_order,
            native_update_id=batch.native_update_id,
            is_snapshot=False,
            exchange_upper_us=self.native_book_exchange_upper_us,
            exchange_precision=batch.exchange_precision,
        )
        self._advance(self.last_book_us)
        self._notify("BOOK", before)

    def observed_trade(self, trade: Trade, *, capture_time_us: int, capture_order: int) -> None:
        """Accept only a caller-reconciled canonical Trade; retain original fields."""
        self._check_capture(trade.time_us, capture_time_us, capture_order)
        _money(trade.price, positive=True)
        _money(trade.quantity, positive=True)
        if trade.price % self.rules.tick_size:
            raise ValueError("TRADE_PRICE_GRID")
        if type(trade.buyer_maker) is not bool or type(trade.trade_id) is not int:
            raise ValueError("INVALID_CANONICAL_TRADE")
        key = trade.time_us, trade.trade_id
        if self.last_native_trade is not None and key <= self.last_native_trade:
            raise ValueError("NONCAUSAL_TRADE")
        before = self._state()
        self.observed_capture = capture_time_us, capture_order
        self.observed_exchange_us = trade.time_us
        self.last_native_trade = key
        if self.clock_mode == "CAPTURE_ARRIVAL":
            mapped = replace(trade, time_us=capture_time_us, canonical_event=None)
            self._record(
                "CANONICAL_TRADE_BINDING",
                trade_id=trade.trade_id,
                exchange_time_us=trade.time_us,
                capture_time_us=capture_time_us,
                canonical_event=trade.canonical_event,
                price=str(trade.price),
                quantity=str(trade.quantity),
                buyer_maker=trade.buyer_maker,
                capture_order=capture_order,
            )
            self._advance(capture_time_us)
            order = self.order
            reason = None
            if self.native_book_exchange_us > trade.time_us:
                reason = "BOOK_NEWER_THAN_NATIVE_TRADE"
            elif self.native_book_exchange_upper_us > trade.time_us:
                reason = "AMBIGUOUS_BOOK_EVENT_PRECISION"
            elif (
                order is not None
                and not order.release
                and trade.time_us
                <= max(order.active_us, self.activation_evaluated_us.get(str(order.order_id), -1))
            ):
                reason = "NATIVE_PRINT_NOT_AFTER_ACTIVATION"
            valid = self.book_valid
            if reason is not None:
                self.book_valid = False
                self.counts[reason] += 1
                self._record("EXECUTION_EVENT_INELIGIBLE", trade_id=trade.trade_id, reason=reason)
            try:
                super().trade(mapped)
            finally:
                self.book_valid = valid
        else:
            super().trade(trade)
        self._notify("TRADE", before)

    def book(self, *args: Any, **kwargs: Any) -> None:
        raise ValueError("USE_OBSERVED_BOOK_WITH_PROVENANCE")

    def trade(self, trade: Trade) -> None:
        raise ValueError("USE_OBSERVED_TRADE_WITH_CAPTURE_BINDING")

    def _advance(self, time_us: int) -> None:
        order = self.order
        pending = order is not None and order.status == "PENDING" and not order.release
        if pending and order is not None and time_us > order.active_us and self.book_valid:
            cancel_effective = order.cancel_us is not None and time_us > order.cancel_us
            known = (
                order.price >= self.known_bid_floor
                if order.side == "BUY"
                else order.price <= self.known_ask_ceiling
            )
            if not known and not cancel_effective:
                order.status = "REJECTED"
                self.counts["ORDER_REJECTION_COUNT"] += 1
                self._record("REJECTION", order_id=order.order_id, reason="UNKNOWN_LEVEL_COVERAGE")
                self.order = None
                return
        super()._advance(time_us)
        if not pending or order is None or self.order is not order or order.status != "ACTIVE":
            return
        levels = self.displayed_bids if order.side == "BUY" else self.displayed_asks
        quantity = dict(levels).get(order.price, ZERO)
        order.queue = quantity
        self.activation_evaluated_us[str(order.order_id)] = time_us
        best = levels[0][0]
        with localcontext() as context:
            context.prec = 128
            depths = {
                f"depth_{ticks}tick": str(
                    sum(
                        (
                            size
                            for price, size in levels
                            if abs(price - best) <= ticks * self.rules.tick_size
                        ),
                        ZERO,
                    )
                )
                for ticks in (1, 2, 5)
            }
        observation = {
            "order_id": order.order_id,
            "side": order.side,
            "time_us": time_us,
            "capture_time_us": self.observed_capture[0],
            "capture_order": self.observed_capture[1],
            "native_update_id": self.observed_native_update_id,
            "best_bid": str(self.displayed_bids[0][0]),
            "best_ask": str(self.displayed_asks[0][0]),
            "limit": str(order.price),
            "displayed_quantity": str(quantity),
            "ahead_estimate": str(quantity),
            "envelope": self.envelope,
            "evidence": "KNOWN_DISPLAYED_AHEAD",
            "priority": "UNKNOWN_TIME_PRIORITY_WITHIN_EXISTING_LEVEL",
            **depths,
        }
        self.activation_observations.append(observation)
        self._record("OBSERVED_QUEUE_ACTIVATION", **observation)

    def _fill(
        self,
        order: Order,
        quantity: Decimal,
        price: Decimal,
        time_us: int,
        source: str,
        source_id: int | None,
    ) -> None:
        budget_before = next((q for p, q in self.bids if p == price), ZERO)
        super()._fill(order, quantity, price, time_us, source, source_id)
        if source == "BOOK":
            with localcontext() as context:
                context.prec = 128
                key = _price_key(price)
                self.consumed_bid_prices[key] = True
                self.bid_consumption_debt[key] = self.bid_consumption_debt.get(key, ZERO) + quantity
            self._record(
                "OBSERVED_DEPTH_CONSUMPTION",
                time_us=time_us,
                price=str(price),
                quantity=str(quantity),
                consumed_debt=str(self.bid_consumption_debt[key]),
                book_source_id=source_id,
                native_update_id=self.observed_native_update_id,
                available_before=str(budget_before),
                available_after=str(budget_before - quantity),
                displayed_quantity=str(dict(self.displayed_bids).get(price, ZERO)),
            )

    def protected_exit(self) -> dict[str, Any]:
        # The visible best may have zero hypothetical budget after an earlier IOC.
        # Preserve observed quotes for maker rejection but use remaining bids for IOC.
        displayed_view = self.bids
        self.bids = [level for level in self.bids if level[1] > ZERO]
        try:
            return super().protected_exit()
        finally:
            self.bids = displayed_view

    def checkpoint(self) -> dict[str, Any]:
        state = _encode(
            {key: value for key, value in self.__dict__.items() if key != "on_transition"}
        )
        return {"state": state, "sha256": canonical_hash(state)}

    def restore(self, checkpoint: dict[str, Any]) -> None:
        if checkpoint["state"].get("envelope") != self.envelope:
            raise ValueError("OBSERVED_ENVELOPE_MISMATCH")
        if checkpoint["state"].get("clock_mode") != self.clock_mode:
            raise ValueError("OBSERVED_CLOCK_MISMATCH")
        callback = self.on_transition
        super().restore(checkpoint)
        self.on_transition = callback


class _AvailableSequence(Sequence[int]):
    """Zero-copy prefix view; paired values (prices/entries) use event/exit keys."""

    def __init__(self, values: Any, events: Any, watermark: Callable[[], int]) -> None:
        self.values, self.events, self.watermark = values, events, watermark

    def __len__(self) -> int:
        return bisect_right(self.events, self.watermark())

    @overload
    def __getitem__(self, index: int) -> int: ...

    @overload
    def __getitem__(self, index: slice) -> list[int]: ...

    def __getitem__(self, index: int | slice) -> int | list[int]:
        length = len(self)
        if isinstance(index, slice):
            return [int(self.values[i]) for i in range(*index.indices(length))]
        if index < 0:
            index += length
        if index < 0 or index >= length:
            raise IndexError(index)
        return int(self.values[index])


class _AvailableTape:
    def __init__(self, tape: Any, watermark: Callable[[], int]) -> None:
        self.tick_size = tape.tick_size
        self.events = _AvailableSequence(tape.events, tape.events, watermark)
        self.price_ticks = _AvailableSequence(tape.price_ticks, tape.events, watermark)
        self.occurrences = {
            price: _AvailableSequence(events, events, watermark)
            for price, events in tape.occurrences.items()
        }
        self._tick_event = tape.observed_tick_evidence_event
        self._watermark = watermark

    @property
    def observed_tick_evidence_event(self) -> int | None:
        value = self._tick_event
        return value if value is not None and value <= self._watermark() else None

    @property
    def last_event(self) -> int:
        return self.events[-1]

    @property
    def last_price_tick(self) -> int:
        return self.price_ticks[-1]


class ObservedL2Replay(B10ReserveReplay):
    """Capture-ordered evidence driver sharing M015 decisions and ledger.

    The caller supplies validated book batches and fully reconciled canonical
    trades in raw capture order. This class never downloads, loads another day,
    reads sealed data or starts a run. No synthetic B10RealityReplay.step is used.
    The original BookEnvelope is constructor provenance only; its quantities and
    quotes do not feed execution. A runner must verify full input coverage first.
    """

    supports_protected_deadline = True

    def __init__(
        self,
        runtime: Any,
        profile: ExecutionProfile,
        rules_at: Callable[[int], SymbolRules],
        frozen_book_envelope: BookEnvelope,
        *,
        start_us: int,
        end_us: int,
        identity: dict[str, Any],
        envelope: Envelope,
    ) -> None:
        duration = end_us - start_us
        if (
            identity.get("model_id") not in ("M015", "M016")
            or duration <= 0
            or duration % (24 * 3_600_000_000)
        ):
            raise ValueError("M015_INDEPENDENT_DAY_REQUIRED")
        self.deadline_enabled = identity.get("model_id") == "M016"
        if self.deadline_enabled and envelope != "PRICE_PRIORITY":
            raise ValueError("M016_FIXED_PRICE_PRIORITY_ENVELOPE_REQUIRED")
        self.deadline_started_entry: int | None = None
        self.deadline_violated_entry: int | None = None
        self.deadline_block_reason: str | None = None
        self.deadline_block_key: tuple[Any, ...] | None = None
        if (
            self.deadline_enabled
            and identity.get("deadline_policy_hash") != M016_DEADLINE_POLICY_HASH
        ):
            raise ValueError("M016_DEADLINE_POLICY_IDENTITY_REQUIRED")
        self.available_canonical_event = start_us * EVENT_ORDER_SCALE - 1
        self._source_tape = runtime.tape

        def watermark() -> int:
            return self.available_canonical_event

        visible = copy.copy(runtime)
        visible.tape = _AvailableTape(runtime.tape, watermark)
        visible.timelines = {
            candidate: replace(
                timeline,
                low_events=_AvailableSequence(timeline.low_events, timeline.low_events, watermark),
                high_events=_AvailableSequence(
                    timeline.high_events, timeline.high_events, watermark
                ),
                cycle_entries=_AvailableSequence(
                    timeline.cycle_entries, timeline.cycle_exits, watermark
                ),
                cycle_exits=_AvailableSequence(
                    timeline.cycle_exits, timeline.cycle_exits, watermark
                ),
            )
            for candidate, timeline in runtime.timelines.items()
        }
        super().__init__(
            visible,
            profile,
            rules_at,
            frozen_book_envelope,
            start_us=start_us,
            end_us=end_us,
            identity=identity,
        )
        self.execution = ObservedL2Execution(
            profile,
            rules_at(start_us),
            envelope=envelope,
            on_transition=self._execution_transition,
            clock_mode="CAPTURE_ARRIVAL",
            deadline_policy_hash=identity.get("deadline_policy_hash"),
        )
        self.last_capture_us = start_us
        self.last_capture_order = -1
        self.execution_envelope = envelope

    def _execution_transition(self, transition: dict[str, Any]) -> None:
        engine = self.engine
        timestamp = int(transition["engine_time_us"])
        before = transition["before"]
        old_entry = before["entry_us"]
        if old_entry is None and engine.entry_us is not None:
            self.position_candidate = self.order_candidate
            self.position_candidate_tick = self.order_candidate_tick
            self.decisions.state.candidate = self.position_candidate
            self.decisions.state.candidate_tick_size = self.position_candidate_tick
            self.next_release = engine.entry_us + 3_600_000_000
        if old_entry is not None and engine.entry_us is None:
            self.holds_us.append(timestamp - int(old_entry))
            self.next_release = None
            self.decisions.state.entry_event = None
            self.decisions.state.flat_since = timestamp * EVENT_ORDER_SCALE
            if self.deadline_enabled and self.deadline_started_entry == old_entry:
                self.decisions.after_ordinary_exit(timestamp * EVENT_ORDER_SCALE)
                engine.needs_reselection = False
            elif engine.counts["RELEASE_FILLED"] > before["releases"]:
                _switch(
                    self.decisions.state,
                    self.release_destination,
                    self.release_destination_tick,
                    timestamp * EVENT_ORDER_SCALE,
                )
            else:
                self.decisions.after_ordinary_exit(timestamp * EVENT_ORDER_SCALE)
            self.release_destination = self.release_destination_tick = None
            self.position_candidate = self.position_candidate_tick = None
            if self.deadline_enabled:
                self.deadline_started_entry = self.deadline_violated_entry = None
                self.deadline_block_reason = None
                self.deadline_block_key = None
        if engine.counts["FULLY_FILLED_CYCLES"] > before["ordinary_cycles"]:
            day = datetime.fromtimestamp(timestamp / 1_000_000, UTC).date().isoformat()
            self.full_days[day] += 1
            if Decimal(engine.settlements[-1]["net_profit"]) > ZERO:
                self.net_days[day] += 1

    def _before_capture(self, timestamp: int, order: int) -> None:
        if self.completed or not self.start_us <= timestamp < self.end_us:
            raise ValueError("CAPTURE_OUTSIDE_AUTHORIZED_DAY")
        if timestamp < self.last_capture_us or order <= self.last_capture_order:
            raise ValueError("NONCAUSAL_CAPTURE_ORDER")
        # The incoming event is absent from all strategy-visible arrays until
        # after these timers AND any settlement-triggered selector invocation.
        while self._next_clock() <= timestamp:
            self._clock(self._next_clock())
        self._integrate(timestamp)
        self.engine.rules = self.rules_at(timestamp)

    def _deadline_prepare_us(self, entry: int) -> int:
        lead = self.engine.profile.cancel_latency_us + 2 * self.engine.profile.latency_us + 2
        if lead >= 7_200_000_000:
            raise ValueError("DEADLINE_LATENCY_EXCEEDS_TWO_HOURS")
        return entry + 7_200_000_000 - lead

    def _next_clock(self) -> int:
        clock = super()._next_clock()
        entry = self.engine.entry_us
        if not self.deadline_enabled or entry is None:
            return clock
        candidates = [clock]
        if self.deadline_started_entry != entry and not self.engine.releasing:
            candidates.append(self._deadline_prepare_us(entry))
        if self.deadline_violated_entry != entry:
            candidates.append(entry + 7_200_000_000 + 1)
        return min(value for value in candidates if value > self.last_clock_us)

    def _clock(self, timestamp: int) -> None:
        engine = self.engine
        entry = engine.entry_us
        evaluations_before = (
            self.decisions.release_evaluations.copy()
            if self.deadline_enabled
            and entry is not None
            and not engine.releasing
            and self.next_release is not None
            and timestamp >= self.next_release
            else None
        )
        if self.deadline_enabled and entry is not None:
            self._integrate(timestamp)
            if self.deadline_violated_entry != entry and timestamp > entry + 7_200_000_000:
                self.deadline_violated_entry = entry
                engine.counts["HOLD_OVER_2H"] += 1
                engine._record(
                    "DEADLINE_VIOLATION",
                    time_us=timestamp,
                    entry_us=entry,
                    deadline_us=entry + 7_200_000_000,
                    inventory=str(engine.inventory),
                )
            if (
                self.deadline_started_entry != entry
                and not engine.releasing
                and timestamp >= self._deadline_prepare_us(entry)
            ):
                self.deadline_started_entry = entry
                self.next_release = None
                self.release_destination = self.position_candidate
                self.release_destination_tick = self.position_candidate_tick
                engine.release_signal_bank = engine.operating_bank
                engine.releasing = True
                engine.counts["DEADLINE_EXIT_SIGNALS"] += 1
                engine._record(
                    "DEADLINE_EXIT_SIGNAL",
                    time_us=timestamp,
                    entry_us=entry,
                    deadline_us=entry + 7_200_000_000,
                    policy_hash=M016_DEADLINE_POLICY_HASH,
                )
                engine.cancel(timestamp)
        super()._clock(timestamp)
        if evaluations_before is not None:
            delta = self.decisions.release_evaluations - evaluations_before
            if delta:
                engine._record(
                    "RELEASE_PREDICATE_EVALUATION",
                    time_us=timestamp,
                    entry_us=entry,
                    evaluations=dict(delta),
                    reserve=str(engine.reserve),
                    operating_bank=str(engine.operating_bank),
                    inventory_cost=str(engine.cost),
                    loss_cap_bps="10",
                    last_observed_bid=str(engine.bids[0][0]) if engine.bids else None,
                )

    def _submit_next(self, timestamp: int) -> None:
        if self.deadline_enabled and self.engine.releasing and self.engine.order is None:
            engine = self.engine
            # Only cache blocked predicates; fresh eligible book epochs still retry.
            # These are exactly the mutable inputs consumed by protected_exit.
            key = (
                engine.book_valid,
                next((tuple(level) for level in engine.bids if level[1] > ZERO), ()),
                engine.reserve,
                engine.inventory,
                engine.cost,
                engine.sold_cost,
                engine.sell_net,
                engine.cash,
                engine.dust_cost,
                engine.rules,
                engine.profile.taker_fee,
            )
            if key == self.deadline_block_key:
                return
            protected = self.engine.protected_exit()
            if not protected["eligible"]:
                self.deadline_block_key = key
                reason = str(protected["reason"])
                self.engine.counts["PROTECTED_EXIT_BLOCKED:" + reason] += 1
                if reason != self.deadline_block_reason:
                    self.engine._record("PROTECTED_EXIT_BLOCKED", time_us=timestamp, **protected)
                    self.deadline_block_reason = reason
                return
            self.deadline_block_key = None
            if self.deadline_block_reason is not None:
                self.engine._record("PROTECTED_EXIT_UNBLOCKED", time_us=timestamp)
                self.deadline_block_reason = None
        super()._submit_next(timestamp)

    def _after_capture(self, timestamp: int, order: int) -> None:
        self._submit_next(timestamp)
        self.last_capture_us, self.last_capture_order = timestamp, order
        self.last_us = timestamp
        with localcontext() as context:
            context.prec = 128
            if self.engine.bids:
                equity = (
                    self.engine.cash
                    + self.engine.reserve
                    + (self.engine.inventory + self.engine.dust) * self.engine.bids[0][0]
                )
                self.peak_equity = max(self.peak_equity, equity)
                self.max_drawdown = max(
                    self.max_drawdown, (self.peak_equity - equity) / self.peak_equity
                )

    def receive_book(self, batch: ObservedBookBatch) -> None:
        self._before_capture(batch.capture_time_us, batch.capture_order)
        self.depth_epoch = batch.native_update_id
        execution = self.execution
        assert isinstance(execution, ObservedL2Execution)
        execution.observed_book(batch)
        self._after_capture(batch.capture_time_us, batch.capture_order)

    def begin_sample_seam(self, timestamp: int, source_date: str) -> None:
        assert isinstance(self.execution, ObservedL2Execution)
        if timestamp > self.last_us:
            self.advance_to(timestamp - 1)
        self.execution.begin_sample_seam(timestamp, source_date)
        self.advance_to(timestamp)

    def receive_trade(self, trade: Trade, *, capture_time_us: int, capture_order: int) -> None:
        event = trade.canonical_event
        if event is None or event // EVENT_ORDER_SCALE != trade.time_us:
            raise ValueError("BOUND_CANONICAL_EVENT_REQUIRED")
        if not self.start_us <= trade.time_us < self.end_us:
            raise ValueError("CANONICAL_TRADE_OUTSIDE_AUTHORIZED_DAY")
        index = bisect_right(self._source_tape.events, self.available_canonical_event)
        if index >= len(self._source_tape.events) or self._source_tape.events[index] != event:
            raise ValueError("CANONICAL_PREFIX_HAS_HOLE_OR_REORDER")
        if (
            Decimal(int(self._source_tape.price_ticks[index])) * self._source_tape.tick_size
            != trade.price
        ):
            raise ValueError("CANONICAL_TAPE_PRICE_MISMATCH")
        self._before_capture(capture_time_us, capture_order)
        execution = self.execution
        assert isinstance(execution, ObservedL2Execution)
        execution.observed_trade(
            trade, capture_time_us=capture_time_us, capture_order=capture_order
        )
        self.available_canonical_event = event
        self.last_mark = trade.price
        self.processed_trades += 1
        self._after_capture(capture_time_us, capture_order)

    def step(self, trade: Trade) -> None:
        raise ValueError("CAPTURE_ORDERED_OBSERVED_EVENTS_REQUIRED")

    def finish(self) -> dict[str, Any]:
        if self.processed_trades != self.identity.get("expected_trade_count"):
            raise ValueError("FULL_DAY_CANONICAL_TRADE_COUNT_MISMATCH")
        self.advance_to(self.end_us)
        self.completed = True
        result = self.metrics()
        result.update(
            {
                "EXECUTION_HYPOTHESIS": self.execution_envelope,
                "EXECUTION_EVIDENCE": "OBSERVED_L2_CONDITIONAL_EXECUTION",
                "CLOCK_MODE": "CAPTURE_ARRIVAL",
                "RUN_STATUS": "COMPLETE",
                "STATUS": "COMPLETE",
                "VERDICT": "COMPLETE_CONDITIONAL_EXECUTION",
                "AVAILABLE_CANONICAL_EVENT": self.available_canonical_event,
            }
        )
        return result

    def checkpoint(self) -> dict[str, Any]:
        raise ValueError("OBSERVED_ORCHESTRATOR_RESUME_NOT_IMPLEMENTED")

    def restore(self, payload: dict[str, Any]) -> None:
        raise ValueError("OBSERVED_ORCHESTRATOR_RESUME_NOT_IMPLEMENTED")
