"""M013 shared-liquidity coordinator; B10/M012 remain immutable ancestors.

One event budget, one external FIFO front block per occupied price level, and
one treasury own the responsibilities which cannot be replicated per queue.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Any

from crypto_strategy_lab.domain import canonical_hash

from .b10_reality import (
    B10Execution,
    BookEnvelope,
    ExecutionProfile,
    Order,
    SymbolRules,
    Trade,
    _decode,
    _encode,
    round_quantity,
)
from .high_uptime_recovery import HOUR, HighUptimeExecution
from .serial_replay import EVENT_ORDER_SCALE, _selection_grid

D = Decimal
ZERO = D(0)
DAY = 24 * HOUR


class QueueExecution(HighUptimeExecution):
    """Reuse sizing, latency/cancel lifecycle and Decimal fill accounting only."""

    def __init__(self, owner: ContinuousMultiQueueReplay, queue_id: int) -> None:
        super().__init__(owner.profile, owner.rules_at(owner.start_us))
        self.owner, self.queue_id = owner, queue_id
        self.policy_hash = owner.spec_hash
        self.cash = self.reserve = self.reserve_min = ZERO
        self.candidate: tuple[int, int] | None = None
        self.candidate_tick: Decimal | None = None
        self.last_release_epoch: int | None = None
        self.urgency = "NORMAL"
        self.hard_violation = False
        self.range_eligible = False
        self.cancel_retry_us: int | None = None
        self.ack_cash_hold = ZERO
        self.supported_best_level = owner.envelope.release_depth
        self.holds: list[int] = []

    def _record(self, kind: str, **values: Any) -> None:
        if kind == "SUBMIT":
            self.owner.order_sequence += 1
            assert self.order is not None
            self.order.order_id = self.owner.order_sequence
            values["order_id"] = self.order.order_id
        record = {"kind": kind, "queue_id": self.queue_id, **values}
        self.owner.audit.append(record)
        if kind == "SETTLEMENT":
            self.settlements.append(record)

    def submit(
        self,
        side: Any,
        price: Decimal,
        time_us: int,
        *,
        release: bool = False,
        continuation: bool = False,
    ) -> Order | None:
        # Accepted submission throttle belongs to the pair, never four accounts.
        crossing = [
            q
            for q in self.owner.queues
            if q is not self
            and q.order is not None
            and q.order.side != side
            and (price >= q.order.price if side == "BUY" else price <= q.order.price)
        ]
        if crossing:
            if release:
                for other in crossing:
                    other.cancel(time_us)
            self.counts["SELF_CROSS_DEFERRED"] += 1
            self._record("SELF_CROSS_DEFERRED", time_us=time_us, side=side, price=str(price))
            return None
        self.messages = list(self.owner.messages)
        protected = self.protected_exit() if release else None
        if release:
            if not protected["eligible"]:
                self.counts[protected["reason"]] += 1
                return None
            if protected["price"] != price:
                raise ValueError("M013_UNPROTECTED_RELEASE")
            order = B10Execution.submit(self, side, price, time_us, release=True)
            if order is not None:
                self.reserve_escrow = protected["worst_deficit"]
                self.owner.claims[self.queue_id] = self.reserve_escrow
                self._record(
                    "RESERVE_ESCROW",
                    time_us=time_us,
                    order_id=order.order_id,
                    amount=str(self.reserve_escrow),
                    price=str(price),
                )
        else:
            order = super().submit(side, price, time_us, continuation=continuation)
        self.owner.messages = list(self.messages)
        return order

    def cancel(self, time_us: int) -> None:
        if self.order is None or self.order.cancel_us is not None:
            self.cancel_retry_us = None
            return
        window = time_us // self.rules.window_us
        self.owner.messages = [
            t for t in self.owner.messages if t // self.rules.window_us == window
        ]
        if len(self.owner.messages) >= self.rules.orders_per_window:
            self.cancel_retry_us = (window + 1) * self.rules.window_us
            self.counts["CANCEL_RATE_LIMIT_DEFERRED"] += 1
            return
        self.owner.messages.append(time_us)
        self.cancel_retry_us = None
        B10Execution.cancel(self, time_us)

    def protected_exit(self) -> dict[str, Any]:
        return self.owner.protected_exit(self)

    def _advance(self, time_us: int) -> None:
        before = self.order
        B10Execution._advance(self, time_us)
        if before is not None and before.side == "BUY" and before.status == "CANCELED":
            self.ack_cash_hold = (before.quantity - before.filled) * before.price
        if time_us > self.last_cancel_ack_us:
            self.ack_cash_hold = ZERO
        if before is not None and before.release and self.order is None:
            # Executed but unsettled deficit remains a treasury liability.
            pending = max(ZERO, self.sold_cost - self.sell_net) if self.queue_id != 4 else ZERO
            self.reserve_escrow = pending
            self.owner.claims[self.queue_id] = pending

    def _settle(self, time_us: int) -> None:
        self.owner.settle(self, time_us)

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
            reserve_before = self.owner.reserve
            active_pnl = ZERO
            if self.queue_id == 4 and order.side == "SELL":
                fee = self.profile.taker_fee if order.release else self.profile.maker_fee
                active_pnl = quantity * price * (1 - fee) - self.cost * quantity / self.inventory
            B10Execution._fill(self, order, quantity, price, time_us, source, source_id)
            self.owner.reserve_min = min(self.owner.reserve_min, self.owner.reserve)
            if active_pnl < 0:
                self.owner.recoveries.append(
                    {
                        "time_us": time_us,
                        "queue_id": 4,
                        "scope": "PHYSICAL_PARTIAL_MARKED_REALIZATION_NOT_SETTLED_FUNDING",
                        "loss": str(-active_pnl),
                        "reserve_before": str(reserve_before),
                        "reserve_after": str(self.owner.reserve),
                        "recovered_us": None,
                    }
                )
                self._record(
                    "ACTIVE_RESERVE_CONSUMPTION",
                    time_us=time_us,
                    loss=str(-active_pnl),
                    reserve_before=str(reserve_before),
                    reserve_after=str(self.owner.reserve),
                )

    def checkpoint(self) -> dict[str, Any]:
        state = _encode({k: v for k, v in vars(self).items() if k != "owner"})
        return {"state": state, "sha256": canonical_hash(state)}

    def restore(self, checkpoint: dict[str, Any]) -> None:
        if canonical_hash(checkpoint["state"]) != checkpoint["sha256"]:
            raise ValueError("M013_QUEUE_CHECKPOINT_HASH")
        state = _decode(checkpoint["state"])
        if (
            state["queue_id"] != self.queue_id
            or state["profile"] != self.profile
            or state["policy_hash"] != self.owner.spec_hash
        ):
            raise ValueError("M013_QUEUE_CHECKPOINT_IDENTITY")
        self.__dict__.update(state)
        self.counts = Counter(self.counts)
        if self.order is not None:
            self.order = next(
                order for order in self.orders if order.order_id == self.order.order_id
            )


class ContinuousMultiQueueReplay:
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
        spec: dict[str, Any],
        gaps: tuple[tuple[int, int], ...] = (),
    ) -> None:
        if identity.get("model_id") != "M013" or identity.get("capital_mode") != "COMPOUNDING":
            raise ValueError("M013_COMPOUNDING_IDENTITY_REQUIRED")
        if start_us >= end_us or spec.get("model_id") != "M013":
            raise ValueError("M013_SPEC_OR_INTERVAL")
        self.runtime, self.profile, self.rules_at, self.envelope = (
            runtime,
            profile,
            rules_at,
            envelope,
        )
        self.start_us, self.end_us, self.identity, self.spec = start_us, end_us, identity, spec
        self.spec_hash = canonical_hash(spec)
        self.gaps = gaps
        self.audit: list[dict[str, Any]] = []
        self.messages: list[int] = []
        self.order_sequence = 0
        self.core = D(10)
        self.pool = D(100)
        self.claims = {i: ZERO for i in range(1, 5)}
        self.queues = [QueueExecution(self, i) for i in range(1, 5)]
        self.levels: dict[str, dict[str, Any]] = {}
        self.last_us = start_us - 1
        self.last_trade_id: int | None = None
        self.last_clock_us = start_us - 1
        self.metrics_last_us = start_us
        self.next_decision = start_us
        self.processed_trades = 0
        self.completed = False
        self.depth_epoch = start_us - envelope.depth_refresh_us
        self.depth_remaining = ZERO
        self.bid = self.ask = ZERO
        self.book_valid = False
        self.book_id: int | None = None
        self.reserve_min = D(10)
        self.funding = self.active_profit = self.consumption = ZERO
        self.active_losses = ZERO
        self.net_realized = self.realized_fees = ZERO
        self.peak_equity = D(110)
        self.max_drawdown = ZERO
        self.counts: Counter[str] = Counter()
        self.full_days: Counter[str] = Counter()
        self.full_stop_by_day: dict[str, int] = {}
        self.full_stop_us = 0
        self.was_full_stop = False
        self.productive_capital_us = self.total_capital_us = ZERO
        self.deployable_capital_us = ZERO
        self.locked_capital_us = self.idle_capital_us = ZERO
        self.reserve_active_capital_us = self.core_idle_capital_us = ZERO
        self.recoveries: list[dict[str, Any]] = []
        self.hard_locks: list[dict[str, Any]] = []
        self.last_ranked: list[dict[str, Any]] = []
        self.last_event = start_us * EVENT_ORDER_SCALE

    @property
    def operating(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 128
            return self.pool + sum((q.cash + q.cost + q.dust_cost for q in self.queues[:3]), ZERO)

    @property
    def reserve(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 128
            q = self.queues[3]
            return self.core + q.cash + q.cost + q.dust_cost

    @property
    def active_committed(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 128
            q = self.queues[3]
            pending = (
                (q.order.quantity - q.order.filled) * q.order.price
                if q.order is not None and q.order.side == "BUY"
                else ZERO
            )
            return q.cost + q.dust_cost + max(pending, q.ack_cash_hold)

    @property
    def floor_guard(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 128
            restored = self.operating + sum(
                (max(ZERO, q.sold_cost - q.sell_net) for q in self.queues[:3]), ZERO
            )
            return max(D("0.00000001"), D("0.001") * restored)

    def _invariants(self) -> None:
        with localcontext() as ctx:
            ctx.prec = 128
            if self.core < 0 or self.pool < 0 or any(q.cash < 0 for q in self.queues):
                self.counts["ACCOUNTING_VIOLATIONS"] += 1
                raise ValueError("M013_NEGATIVE_CASH")
            escrow = sum(self.claims.values(), ZERO)
            if self.reserve <= 0 or self.core - escrow < self.floor_guard:
                self.counts["CORE_RESERVE_VIOLATIONS"] += 1
                self.counts["RESERVE_DEPLETION_EVENTS"] += int(self.reserve <= 0)
                raise ValueError("M013_CORE_SURVIVAL_INVARIANT")
            if self.reserve - escrow < 2 * self.active_committed:
                self.counts["CORE_RESERVE_VIOLATIONS"] += 1
                raise ValueError("M013_ACTIVE_HALF_INVARIANT")

    def _return_active_cash(self) -> None:
        q = self.queues[3]
        pending = (
            (q.order.quantity - q.order.filled) * q.order.price
            if q.order is not None and q.order.side == "BUY"
            else ZERO
        )
        free = max(ZERO, q.cash - max(pending, q.ack_cash_hold))
        q.cash -= free
        self.core += free

    def protected_exit(self, queue: QueueExecution) -> dict[str, Any]:
        with localcontext() as ctx:
            ctx.prec = 128
            if not queue.book_valid or not queue.bids or queue.bids[0][1] <= 0:
                return {"eligible": False, "reason": "NO_LIQUIDITY"}
            q = round_quantity(queue.inventory, queue.rules.step_size)
            if q <= 0:
                return {"eligible": False, "reason": "NO_SELLABLE_QUANTITY"}
            other = sum((v for k, v in self.claims.items() if k != queue.queue_id), ZERO)
            budget = max(
                ZERO,
                min(
                    self.core - other - self.floor_guard,
                    self.reserve - 2 * self.active_committed - other,
                ),
            )
            if queue.queue_id == 4:
                guard = self.operating + sum(
                    (max(ZERO, q.sold_cost - q.sell_net) for q in self.queues[:3]), ZERO
                )
                budget = min(budget, D("0.001") * guard)
            else:
                age = self.last_clock_us - queue.entry_us if queue.entry_us is not None else 0
                fraction = D(1) if age >= 18 * HOUR else D("0.5") if age >= 12 * HOUR else D("0.25")
                ratio = (
                    min(D(1), self.reserve / self.operating / D("0.10")) if self.operating else ZERO
                )
                budget *= fraction * ratio
            cost = queue.sold_cost + queue.cost * q / queue.inventory
            minimum = max(
                queue.rules.min_price,
                (cost - queue.sell_net - budget) / (q * (1 - self.profile.taker_fee)),
            )
            price = (minimum / queue.rules.tick_size).to_integral_value(
                rounding=ROUND_CEILING
            ) * queue.rules.tick_size
            worst = max(ZERO, cost - queue.sell_net - q * price * (1 - self.profile.taker_fee))
            try:
                queue.rules.validate("SELL", price, q)
            except ValueError as exc:
                return {"eligible": False, "reason": "FILTER_REJECTION", "detail": str(exc)}
            if price > queue.bids[0][0] or worst > budget:
                return {"eligible": False, "reason": "RELEASE_BLOCKED_BY_RESERVE"}
            return {
                "eligible": True,
                "price": price,
                "quantity": q,
                "worst_deficit": worst,
                "budget": budget,
                "floor_guard": self.floor_guard,
            }

    def settle(self, queue: QueueExecution, timestamp: int) -> None:
        with localcontext() as ctx:
            ctx.prec = 128
            if queue.inventory >= queue.rules.step_size:
                raise ValueError("M013_OPERATIONAL_REMAINDER_CANNOT_SETTLE")
            queue.dust += queue.inventory
            queue.dust_cost += queue.cost
            queue.inventory = queue.cost = ZERO
            profit = queue.sell_net - queue.sold_cost
            forced = queue.release_execution_started
            loss = max(ZERO, -profit) if forced else ZERO
            contribution = max(ZERO, profit) * D("0.10") if queue.queue_id != 4 else ZERO
            reserve_before = self.reserve
            if queue.queue_id != 4:
                if loss > self.claims[queue.queue_id]:
                    self.counts["OPERATING_RESTORATION_VIOLATIONS"] += 1
                    raise ValueError("M013_RELEASE_ESCROW_EXCEEDED")
                self.core -= loss
                queue.cash += loss
                self.core += contribution
                queue.cash -= contribution
                self.funding += contribution
            else:
                self.active_profit += max(ZERO, profit)
                self.active_losses += max(ZERO, -profit)
            self.consumption += loss if queue.queue_id != 4 else ZERO
            self.net_realized += profit
            self.realized_fees += queue.realized_cycle_fees
            self.claims[queue.queue_id] = ZERO
            self._return_active_cash()
            queue.counts["RELEASE_FILLED" if forced else "FULLY_FILLED_CYCLES"] += 1
            queue.counts["NET_POSITIVE_CYCLES"] += int(profit > 0 and not forced)
            queue.counts["FORCED_NET_POSITIVE_CLOSURES"] += int(profit > 0 and forced)
            self.counts["CYCLES"] += 1
            self.counts["NET_POSITIVE_CYCLES"] += int(profit > 0)
            day = datetime.fromtimestamp(timestamp / 1_000_000, UTC).date().isoformat()
            if queue.queue_id != 4 and not forced:
                self.full_days[day] += 1
            if queue.entry_us is not None:
                queue.holds.append(timestamp - queue.entry_us)
            if loss and queue.queue_id != 4:
                self.recoveries.append(
                    {
                        "time_us": timestamp,
                        "queue_id": queue.queue_id,
                        "loss": str(loss),
                        "reserve_before": str(reserve_before),
                        "reserve_after": str(self.reserve),
                        "recovered_us": None,
                    }
                )
            queue._record(
                "SETTLEMENT",
                time_us=timestamp,
                release=forced,
                net_profit=str(profit),
                sold_cost=str(queue.sold_cost),
                gross_pnl=str(profit + queue.realized_cycle_fees),
                realized_fees_quote=str(queue.realized_cycle_fees),
                reserve_funding=str(contribution),
                actual_release_loss=str(loss),
                reserve_before=str(reserve_before),
                reserve_after=str(self.reserve),
                cash=str(queue.cash),
                dust=str(queue.dust),
                dust_cost=str(queue.dust_cost),
                core=str(self.core),
                active_committed=str(self.active_committed),
            )
            queue.buy_cost = queue.sell_net = queue.sold_cost = ZERO
            queue.buy_fee_basis = queue.realized_cycle_fees = queue.reserve_escrow = ZERO
            queue.entry_us = None
            queue.releasing = queue.release_execution_started = queue.buy_complete = False
            queue.candidate = None
            queue.hard_violation = False
            queue.urgency = "NORMAL"
            self._invariants()
            self.reserve_min = min(self.reserve_min, self.reserve)

    def ranked(self, timestamp: int) -> list[dict[str, Any]]:
        event = timestamp * EVENT_ORDER_SCALE
        tick, distances, multiple = _selection_grid(
            self.runtime.parent,
            self.runtime.tick_catalog,
            event,
            self.runtime.tape.tick_size,
            self.runtime.tape.observed_tick_evidence_event,
        )
        rows = []
        rules = self.rules_at(timestamp)
        with localcontext() as ctx:
            ctx.prec = 128
            for candidate, timeline in self.runtime.timelines.items():
                low, distance = candidate
                if (distances is not None and distance not in distances) or (
                    multiple is not None and (low % multiple or (low + distance) % multiple)
                ):
                    continue
                c1 = timeline.contained_cycles(event - HOUR * EVENT_ORDER_SCALE, event)
                c24 = timeline.contained_cycles(event - DAY * EVENT_ORDER_SCALE, event)
                edge = D(low + distance) / D(low) * (1 - self.profile.maker_fee) ** 2 - 1
                low_price, high_price = (
                    D(low) * self.runtime.tape.tick_size,
                    D(low + distance) * self.runtime.tape.tick_size,
                )
                if (
                    low_price < rules.min_price
                    or high_price > rules.max_price
                    or low_price % rules.tick_size
                    or high_price % rules.tick_size
                ):
                    continue
                if c1 < 1 or c24 < 1 or edge <= 0:
                    continue
                rows.append(
                    {
                        "candidate": candidate,
                        "score": D(min(c24, 24 * c1)) * edge,
                        "c1": c1,
                        "tick": tick,
                    }
                )
        return sorted(rows, key=lambda r: (-r["score"], r["candidate"][0], sum(r["candidate"])))

    @staticmethod
    def _disjoint(candidate: tuple[int, int], occupied: list[tuple[int, int]]) -> bool:
        low, dist = candidate
        return all(low > sum(other) or low + dist < other[0] for other in occupied)

    def _allocate(self, timestamp: int) -> None:
        rows = self.ranked(timestamp)
        self.last_ranked = rows
        for q in self.queues:
            q.range_eligible = any(
                row["candidate"] == q.candidate and (q.queue_id != 4 or row["c1"] >= 2)
                for row in rows
            )
        free = [
            q
            for q in self.queues[:3]
            if q.entry_us is None and q.order is None and timestamp > q.last_cancel_ack_us
        ]
        occupied = [
            q.candidate
            for q in self.queues
            if q.candidate is not None and (q.entry_us is not None or q.order is not None)
        ]
        for queue in free:
            self.pool += queue.cash
            queue.cash = ZERO
            queue.candidate = None
        selected = []
        for row in rows:
            if self._disjoint(row["candidate"], occupied):
                selected.append(row)
                occupied.append(row["candidate"])
                if len(selected) == len(free):
                    break
        if not free:
            selected = []
        with localcontext() as ctx:
            ctx.prec = 128
            while selected:
                total = sum((r["score"] for r in selected), ZERO)
                valid = []
                for row in selected:
                    price = D(row["candidate"][0]) * self.runtime.tape.tick_size
                    share = self.pool * row["score"] / total
                    quantity = round_quantity(share / price, self.rules_at(timestamp).step_size)
                    rules = self.rules_at(timestamp)
                    if quantity >= rules.min_quantity and quantity * price >= rules.min_notional:
                        valid.append(row)
                if len(valid) == len(selected):
                    break
                selected = valid
            original_pool = self.pool
            total = sum((r["score"] for r in selected), ZERO)
            for index, (queue, row) in enumerate(zip(free, selected, strict=False)):
                share = (
                    self.pool
                    if index == len(selected) - 1
                    else original_pool * row["score"] / total
                )
                self.pool -= share
                queue.cash = share
                queue.candidate, queue.candidate_tick = row["candidate"], row["tick"]
                queue.range_eligible = True
                queue._record(
                    "ALLOCATION",
                    time_us=timestamp,
                    capital=str(share),
                    candidate=row["candidate"],
                    score=str(row["score"]),
                )
            q4 = self.queues[3]
            if q4.entry_us is None and q4.order is None and timestamp > q4.last_cancel_ack_us:
                self._return_active_cash()
                q4.candidate = None
                recovery = any(q.releasing for q in self.queues[:3])
                if not recovery:
                    occupied = [q.candidate for q in self.queues[:3] if q.candidate is not None]
                    row = next(
                        (
                            r
                            for r in rows
                            if r["c1"] >= 2 and self._disjoint(r["candidate"], occupied)
                        ),
                        None,
                    )
                    budget = max(
                        ZERO,
                        min(
                            (
                                self.reserve
                                - sum(self.claims.values(), ZERO)
                                - D("0.05") * self.operating
                            )
                            / 2
                            - q4.dust_cost,
                            self.core - sum(self.claims.values(), ZERO) - self.floor_guard,
                        ),
                    )
                    if row is not None:
                        price = D(row["candidate"][0]) * self.runtime.tape.tick_size
                        quantity = round_quantity(budget / price, q4.rules.step_size)
                        if (
                            quantity >= q4.rules.min_quantity
                            and quantity * price >= q4.rules.min_notional
                        ):
                            q4.cash = budget
                            self.core -= budget
                            q4.candidate, q4.candidate_tick = row["candidate"], row["tick"]
                            q4.range_eligible = True
                            q4._record(
                                "ALLOCATION",
                                time_us=timestamp,
                                capital=str(budget),
                                candidate=row["candidate"],
                            )

    def _begin_release(self, queue: QueueExecution, timestamp: int) -> None:
        if not queue.releasing:
            queue.releasing = True
            queue.counts["RELEASE_SIGNALS"] += 1
            queue._record(
                "RELEASE_SIGNAL",
                time_us=timestamp,
                urgency=queue.urgency,
                reserve=str(self.reserve),
                operating=str(self.operating),
            )
        if queue.order is not None and not queue.order.release:
            queue.cancel(timestamp)

    def _clock(self, timestamp: int) -> None:
        self._integrate(timestamp)
        self.last_clock_us = timestamp
        decision = timestamp >= self.next_decision
        if decision:
            ranked = self.ranked(timestamp)
            for q in self.queues:
                eligible = {row["candidate"] for row in ranked if q.queue_id != 4 or row["c1"] >= 2}
                if (
                    q.order is not None
                    and q.order.side == "BUY"
                    and not q.order.filled
                    and q.candidate not in eligible
                ):
                    q.cancel(timestamp)
        for queue in self.queues:
            queue.rules = self.rules_at(timestamp)
            if timestamp > queue.last_cancel_ack_us:
                queue.ack_cash_hold = ZERO
            if queue.cancel_retry_us is not None and timestamp >= queue.cancel_retry_us:
                queue.cancel(timestamp)
            if any(a <= timestamp < b for a, b in self.gaps):
                queue.book_valid = False
            if queue.order is not None and not queue.order.release:
                queue._advance(timestamp)
            if queue.entry_us is None:
                continue
            age = timestamp - queue.entry_us
            limit = (6 if queue.queue_id == 4 else 24) * HOUR
            if age >= limit and not queue.hard_violation:
                queue.hard_violation = True
                record = {
                    "queue_id": queue.queue_id,
                    "entry_us": queue.entry_us,
                    "time_us": timestamp,
                }
                self.hard_locks.append(record)
                queue._record("HARD_LOCK_VIOLATION", time_us=timestamp, entry_us=queue.entry_us)
            if queue.queue_id == 4:
                queue.urgency = "MANDATORY" if age >= 3 * HOUR else "NORMAL"
                if age >= 3 * HOUR:
                    self._begin_release(queue, timestamp)
            else:
                queue.urgency = (
                    "MANDATORY"
                    if age >= 18 * HOUR
                    else "HIGH"
                    if age >= 12 * HOUR
                    else "ELIGIBLE"
                    if age >= 6 * HOUR
                    else "WATCH"
                    if age >= 3 * HOUR
                    else "NORMAL"
                )
                if age >= 12 * HOUR:
                    self._begin_release(queue, timestamp)
                elif age >= 6 * HOUR and decision and not queue.releasing:
                    ranked = self.ranked(timestamp)
                    own_score = next(
                        (r["score"] for r in ranked if r["candidate"] == queue.candidate), ZERO
                    )
                    others = [
                        q.candidate
                        for q in self.queues
                        if q is not queue and q.candidate is not None
                    ]
                    if (
                        any(
                            r["candidate"] != queue.candidate
                            and r["score"] > own_score
                            and self._disjoint(r["candidate"], others)
                            for r in ranked
                        )
                        and queue.protected_exit()["eligible"]
                    ):
                        self._begin_release(queue, timestamp)
        if any(q.releasing for q in self.queues[:3]):
            q4 = self.queues[3]
            if q4.order is not None and q4.order.side == "BUY":
                q4.cancel(timestamp)
        self._clean_levels()
        self._return_active_cash()
        if decision:
            self._allocate(timestamp)
            self.next_decision = timestamp + 60_000_000
        self._submit_next(timestamp)

    def _next_clock(self) -> int:
        clocks = [self.next_decision]
        for q in self.queues:
            if q.cancel_retry_us is not None:
                clocks.append(q.cancel_retry_us)
            if q.order is not None:
                if q.order.status == "PENDING" and not q.order.release:
                    clocks.append(q.order.active_us + 1)
                if q.order.cancel_us is not None:
                    clocks.append(q.order.cancel_us + 1)
            clocks.append(q.last_cancel_ack_us + 1)
            if q.entry_us is not None:
                clocks.extend(
                    q.entry_us + h * HOUR
                    for h in ((3, 6) if q.queue_id == 4 else (3, 6, 12, 18, 24))
                )
                if not q.hard_violation:
                    clocks.append(q.entry_us + (6 if q.queue_id == 4 else 24) * HOUR)
        return min(t for t in clocks if t > self.last_clock_us)

    def _submit_next(self, timestamp: int) -> None:
        for q in sorted(
            self.queues, key=lambda q: (q.queue_id == 4, q.entry_us or timestamp, q.queue_id)
        ):
            if q.order is not None or not q.book_valid or timestamp <= q.last_cancel_ack_us:
                continue
            if q.releasing:
                if q.last_release_epoch == self.depth_epoch:
                    continue
                q.last_release_epoch = self.depth_epoch
                protected = q.protected_exit()
                if protected["eligible"]:
                    q.submit("SELL", protected["price"], timestamp, release=True)
                else:
                    q.counts[protected["reason"]] += 1
                    q._record("RELEASE_BLOCKED", time_us=timestamp, **protected)
            elif q.candidate is not None:
                if (
                    q.queue_id == 4
                    and not q.buy_complete
                    and any(other.releasing for other in self.queues[:3])
                ):
                    continue
                low, dist = q.candidate
                if q.entry_us is None:
                    # A canceled obsolete zero-fill entry must remain flat until
                    # the next causal allocation. Existing inventory still exits.
                    if not q.range_eligible:
                        continue
                    q.submit("BUY", D(low) * self.runtime.tape.tick_size, timestamp)
                elif q.buy_complete:
                    q.submit("SELL", D(low + dist) * self.runtime.tape.tick_size, timestamp)
                else:
                    q.submit(
                        "BUY", D(low) * self.runtime.tape.tick_size, timestamp, continuation=True
                    )
        self._return_active_cash()

    def _clean_levels(self) -> None:
        live = {
            q.order.order_id: q
            for q in self.queues
            if q.order is not None and q.order.status == "ACTIVE" and not q.order.release
        }
        for key in list(self.levels):
            self.levels[key]["orders"] = [oid for oid in self.levels[key]["orders"] if oid in live]
            if not self.levels[key]["orders"]:
                del self.levels[key]
        known = {oid for level in self.levels.values() for oid in level["orders"]}
        for oid, q in sorted(live.items(), key=lambda item: (item[1].order.active_us, item[0])):
            if oid not in known:
                key = q.order.side + ":" + str(q.order.price.normalize())
                if key not in self.levels:
                    self.levels[key] = {
                        "side": q.order.side,
                        "price": q.order.price,
                        "external": self.profile.queue_ahead,
                        "orders": [],
                    }
                self.levels[key]["orders"].append(oid)

    def _match_passive(self, trade: Trade, remaining: Decimal) -> Decimal:
        self._clean_levels()
        side = "BUY" if trade.buyer_maker else "SELL"
        # Exact-price compatibility preserves the ancestor's execution domain.
        levels = [
            level
            for level in self.levels.values()
            if level["side"] == side and level["price"] == trade.price
        ]
        for level in levels:
            before = remaining
            external = min(remaining, level["external"])
            level["external"] -= external
            remaining -= external
            for oid in list(level["orders"]):
                q = next(
                    (q for q in self.queues if q.order is not None and q.order.order_id == oid),
                    None,
                )
                if q is None or remaining <= 0:
                    continue
                order = q.order
                quantity = min(remaining, order.quantity - order.filled)
                q._fill(order, quantity, order.price, trade.time_us, "TRADE", trade.trade_id)
                remaining -= quantity
            self.audit.append(
                {
                    "kind": "SHARED_QUEUE_FLOW",
                    "time_us": trade.time_us,
                    "trade_id": trade.trade_id,
                    "side": side,
                    "price": str(trade.price),
                    "event_budget_before": str(before),
                    "external_burn": str(external),
                    "event_budget_after": str(remaining),
                    "external_remaining": str(level["external"]),
                }
            )
        self._clean_levels()
        return remaining

    def step(self, trade: Trade) -> None:
        if self.completed or not self.start_us <= trade.time_us < self.end_us:
            raise ValueError("M013_TRADE_OUTSIDE_STAGE")
        if trade.time_us < self.last_us or (
            self.last_trade_id is not None and trade.trade_id <= self.last_trade_id
        ):
            self.counts["FUTURE_LEAKAGE_EVENTS"] += 1
            raise ValueError("M013_NONCAUSAL_TRADE")
        if trade.quantity <= 0 or trade.price <= 0:
            raise ValueError("INVALID_TRADE")
        self.advance_to(trade.time_us)
        with localcontext() as ctx:
            ctx.prec = 128
            while self._next_clock() <= trade.time_us:
                self._clock(self._next_clock())
            self.last_event = trade.canonical_event or trade.time_us * EVENT_ORDER_SCALE
            if self.last_event // EVENT_ORDER_SCALE != trade.time_us:
                self.counts["FUTURE_LEAKAGE_EVENTS"] += 1
                raise ValueError("CANONICAL_EVENT_TIMESTAMP_MISMATCH")
            rules = self.rules_at(trade.time_us)
            self.book_valid = not any(a <= trade.time_us < b for a, b in self.gaps)
            self.bid, self.ask = self.envelope.quote(
                trade.price, rules.tick_size, False, trade.buyer_maker
            )
            release_bid, _ = self.envelope.quote(
                trade.price, rules.tick_size, True, trade.buyer_maker
            )
            self.book_id = trade.trade_id
            if trade.time_us >= self.depth_epoch + self.envelope.depth_refresh_us:
                self.depth_epoch, self.depth_remaining = trade.time_us, self.envelope.release_depth
            remaining = trade.quantity
            priority = sorted(
                self.queues,
                key=lambda q: (
                    not (q.order and q.order.release),
                    q.queue_id == 4,
                    q.entry_us or trade.time_us,
                    q.queue_id,
                ),
            )
            for q in priority:
                q.rules = rules
                depth = (
                    min(self.depth_remaining, remaining)
                    if q.order and q.order.release
                    else self.depth_remaining
                )
                before = depth
                price = release_bid if q.order and q.order.release else self.bid
                q.book(
                    trade.time_us, trade.trade_id, [(price, depth)], self.ask, valid=self.book_valid
                )
                consumed = before - q.bids[0][1]
                self.depth_remaining -= consumed
                remaining -= consumed
            if self.book_valid:
                remaining = self._match_passive(trade, remaining)
            if remaining < 0:
                self.counts["LIQUIDITY_DUPLICATION_EVENTS"] += 1
                raise ValueError("M013_SHARED_EVENT_OVERCONSUMPTION")
            self._return_active_cash()
            # New capital allocation waits for the frozen 60-second clock.
            self._submit_next(trade.time_us)
            self._invariants()
            self.reserve_min = min(self.reserve_min, self.reserve)
            for recovery in self.recoveries:
                if recovery["recovered_us"] is None and self.reserve >= D(
                    recovery["reserve_before"]
                ):
                    recovery["recovered_us"] = trade.time_us
            equity = self._equity()
            self.peak_equity = max(self.peak_equity, equity)
            self.max_drawdown = max(
                self.max_drawdown, (self.peak_equity - equity) / self.peak_equity
            )
            self.last_us, self.last_trade_id = trade.time_us, trade.trade_id
            self.processed_trades += 1

    def advance_to(self, timestamp_us: int) -> None:
        if timestamp_us < self.metrics_last_us or timestamp_us > self.end_us:
            raise ValueError("M013_NONCAUSAL_CLOCK")
        while self._next_clock() <= timestamp_us and self._next_clock() < self.end_us:
            with localcontext() as ctx:
                ctx.prec = 128
                self._clock(self._next_clock())
        self._integrate(timestamp_us)

    def _productive(self, q: QueueExecution) -> bool:
        if not q.range_eligible or q.releasing or not q.book_valid:
            return False
        if q.order is not None and q.order.status not in ("ACTIVE", "PENDING"):
            return False
        if q.entry_us is not None:
            age = self.metrics_last_us - q.entry_us
            if age >= (3 if q.queue_id == 4 else 6) * HOUR:
                return False
            return q.order is not None and q.order.cancel_us is None
        if q.order is not None:
            return q.book_valid and q.order.cancel_us is None
        if q.candidate is None or q.cash <= 0 or not q.book_valid:
            return False
        price = D(q.candidate[0]) * self.runtime.tape.tick_size
        quantity = round_quantity(q.cash / price, q.rules.step_size)
        try:
            q.rules.validate("BUY", price, quantity)
        except ValueError:
            return False
        return True

    def _integrate(self, timestamp: int) -> None:
        if timestamp < self.metrics_last_us:
            raise ValueError("M013_NONCAUSAL_INTEGRAL")
        delta = timestamp - self.metrics_last_us
        with localcontext() as ctx:
            ctx.prec = 128
            productive = [q for q in self.queues if self._productive(q)]
            capital = sum((q.cash + q.cost for q in productive), ZERO)
            total = self.operating + self.reserve
            locked = sum(
                (q.cost for q in self.queues if q.entry_us is not None and q not in productive),
                ZERO,
            )
            self.productive_capital_us += capital * delta
            self.total_capital_us += total * delta
            self.deployable_capital_us += (self.operating + self.active_committed) * delta
            self.locked_capital_us += locked * delta
            self.idle_capital_us += (total - capital - locked) * delta
            self.reserve_active_capital_us += self.active_committed * delta
            self.core_idle_capital_us += self.core * delta
            stopped = not productive
            if stopped:
                self.full_stop_us += delta
                cursor = self.metrics_last_us
                while cursor < timestamp:
                    next_day = min(timestamp, (cursor // DAY + 1) * DAY)
                    day = datetime.fromtimestamp(cursor / 1_000_000, UTC).date().isoformat()
                    self.full_stop_by_day[day] = (
                        self.full_stop_by_day.get(day, 0) + next_day - cursor
                    )
                    cursor = next_day
                if delta and not self.was_full_stop:
                    self.counts["FULL_STOP_EVENTS"] += 1
            self.was_full_stop = stopped
        self.metrics_last_us = timestamp

    def _equity(self) -> Decimal:
        return (
            self.pool
            + self.core
            + sum((q.cash + (q.inventory + q.dust) * self.bid for q in self.queues), ZERO)
        )

    def metrics(self, as_of_us: int | None = None) -> dict[str, Any]:
        timestamp = self.metrics_last_us if as_of_us is None else as_of_us
        if timestamp != self.metrics_last_us:
            raise ValueError("M013_METRICS_REQUIRE_ADVANCED_PREFIX")
        with localcontext() as ctx:
            ctx.prec = 128
            duration = timestamp - self.start_us
            days = duration // DAY
            operating_holds = [h for q in self.queues[:3] for h in q.holds]
            operating_holds += [
                timestamp - q.entry_us for q in self.queues[:3] if q.entry_us is not None
            ]
            net = self.net_realized + sum((q.sell_net - q.sold_cost for q in self.queues), ZERO)
            active = sum(self._productive(q) for q in self.queues[:3])
            contributions = self.funding + self.active_profit
            conservative_loss = self.consumption + self.active_losses
            active_holds = self.queues[3].holds + (
                [timestamp - self.queues[3].entry_us] if self.queues[3].entry_us is not None else []
            )
            result = {
                "MODEL_ID": "M013",
                "STRATEGY": "CONTINUOUS_MULTI_QUEUE_RECOVERY",
                "CAPITAL_MODE": "COMPOUNDING",
                "RUN_STATUS": "COMPLETE" if self.completed else "RUNNING",
                "SIMULATION_TIMESTAMP": datetime.fromtimestamp(
                    timestamp / 1_000_000, UTC
                ).isoformat(),
                "PROCESSED_TRADES": self.processed_trades,
                "OPERATING_CAPITAL": str(self.operating),
                "OPERATING_BANK": str(self.operating),
                "RECOVERY_RESERVE": str(self.reserve),
                "RESERVE_RATIO": str(self.reserve / self.operating) if self.operating else None,
                "RESERVE_REGIME": (
                    "RESERVE_REBUILDING"
                    if self.reserve < D("0.10") * self.operating
                    else "RESERVE_PROTECTED"
                    if self.reserve < D("0.15") * self.operating
                    else "RESERVE_GROWING"
                    if self.reserve < D("0.20") * self.operating
                    else "RESERVE_STRONG"
                    if self.reserve < D("0.30") * self.operating
                    else "RESERVE_EXPANSION_READY"
                ),
                "CORE_RESERVE": str(self.core),
                "ACTIVE_RESERVE_CAPITAL": str(self.active_committed),
                "TOTAL_EQUITY": str(self._equity()),
                "TOTAL_PROFIT": str(self._equity() - D(110)),
                "NET_REALIZED_PNL": str(net),
                "OPERATING_QUEUES_ACTIVE": active,
                "RESERVE_QUEUE_ACTIVE": self._productive(self.queues[3]),
                "CYCLES": self.counts["CYCLES"],
                "NET_POSITIVE_CYCLES": self.counts["NET_POSITIVE_CYCLES"],
                "MOTOR_UPTIME": str(1 - D(self.full_stop_us) / duration) if duration else None,
                "CAPITAL_WEIGHTED_UPTIME": str(self.productive_capital_us / self.total_capital_us)
                if self.total_capital_us
                else None,
                "DEPLOYABLE_CAPITAL_WEIGHTED_UPTIME": str(
                    self.productive_capital_us / self.deployable_capital_us
                )
                if self.deployable_capital_us
                else None,
                "FULL_STOP_HOURS": str(D(self.full_stop_us) / HOUR),
                "FULL_STOP_EVENTS": self.counts["FULL_STOP_EVENTS"],
                "FULL_STOP_DAYS": sum(value >= DAY for value in self.full_stop_by_day.values()),
                "ZERO_CYCLE_DAYS": days
                - sum(
                    day < datetime.fromtimestamp(timestamp / 1_000_000, UTC).date().isoformat()
                    for day in self.full_days
                ),
                "MAX_HOLD": str(D(max(operating_holds, default=0)) / HOUR),
                "MAX_OPERATING_HOLD_HOURS": str(D(max(operating_holds, default=0)) / HOUR),
                "MAX_ACTIVE_RESERVE_HOLD_HOURS": str(D(max(active_holds, default=0)) / HOUR),
                "LOCK_HOURS_GT24": str(
                    sum((D(max(0, h - DAY)) for h in operating_holds), ZERO) / HOUR
                ),
                "HARD_LOCK_VIOLATIONS": len(self.hard_locks),
                "RESERVE_MIN": str(self.reserve_min),
                "RELEASE_COUNT": sum(q.counts["RELEASE_FILLED"] for q in self.queues),
                "TOTAL_RELEASE_LOSS": str(self.consumption),
                "RESERVE_CONTRIBUTIONS": str(self.funding),
                "ACTIVE_RESERVE_PROFIT": str(self.active_profit),
                "RESERVE_CONSUMPTION": str(self.consumption),
                "RESERVE_SELF_SUSTAINABILITY_RATIO": str(contributions / conservative_loss)
                if conservative_loss
                else None,
                "OWNER_RELEASE_ONLY_SUSTAINABILITY_RATIO": str(contributions / self.consumption)
                if self.consumption
                else None,
                "ACTIVE_RESERVE_LOSSES": str(self.active_losses),
                "ACTIVE_RESERVE_NET_PNL": str(self.active_profit - self.active_losses),
                "ACTIVE_RESERVE_PENDING_REALIZED_NET_PNL": str(
                    self.queues[3].sell_net - self.queues[3].sold_cost
                ),
                "CORE_RESERVE_VIOLATIONS": self.counts["CORE_RESERVE_VIOLATIONS"],
                "ACCOUNTING_VIOLATIONS": self.counts["ACCOUNTING_VIOLATIONS"],
                "FUTURE_LEAKAGE_EVENTS": self.counts["FUTURE_LEAKAGE_EVENTS"],
                "LIQUIDITY_DUPLICATION_EVENTS": self.counts["LIQUIDITY_DUPLICATION_EVENTS"],
                "OPERATING_RESTORATION_VIOLATIONS": self.counts["OPERATING_RESTORATION_VIOLATIONS"],
                "RESERVE_DEPLETION_EVENTS": self.counts["RESERVE_DEPLETION_EVENTS"],
                "CAPACITY_PRESSURE_EVENTS": sum(
                    q.counts["CAPACITY_LIMIT_REACHED"] for q in self.queues
                ),
                "PRODUCTIVE_CAPITAL_HOURS": str(self.productive_capital_us / HOUR),
                "LOCKED_CAPITAL_HOURS": str(self.locked_capital_us / HOUR),
                "IDLE_CAPITAL_HOURS": str(self.idle_capital_us / HOUR),
                "RESERVE_ACTIVE_HOURS": str(self.reserve_active_capital_us / HOUR),
                "CORE_RESERVE_IDLE_HOURS": str(self.core_idle_capital_us / HOUR),
                "MAX_DRAWDOWN": str(self.max_drawdown),
                "VERDICT": "PENDING_INDEPENDENT_AUDIT",
                "QUEUES": [
                    {
                        "queue_id": q.queue_id,
                        "cash": str(q.cash),
                        "capital": str(q.cash + q.cost + q.dust_cost),
                        "inventory": str(q.inventory),
                        "dust": str(q.dust),
                        "counts": dict(q.counts),
                        "candidate": q.candidate,
                        "entry_us": q.entry_us,
                    }
                    for q in self.queues
                ],
            }
            completed_recovery = sorted(
                r["recovered_us"] - r["time_us"]
                for r in self.recoveries
                if r["recovered_us"] is not None
            )
            completed_hold = sorted(h for q in self.queues for h in q.holds)

            def percentile(values: list[int], percent: int) -> str | None:
                if not values:
                    return None
                return str(D(values[max(0, (len(values) * percent + 99) // 100 - 1)]) / HOUR)

            result.update(
                {
                    "CALENDAR_DAYS_PROCESSED": duration // DAY,
                    "CALENDAR_DAYS_TOTAL": (self.end_us - self.start_us + DAY - 1) // DAY,
                    "PROGRESS_PERCENT": str(D(duration) / (self.end_us - self.start_us) * 100),
                    "INITIAL_EQUITY": "110",
                    "ORDINARY_OPERATING_CYCLES": sum(
                        q.counts["FULLY_FILLED_CYCLES"] for q in self.queues[:3]
                    ),
                    "ACTIVE_RESERVE_CYCLES": self.queues[3].counts["FULLY_FILLED_CYCLES"],
                    "FULL_STOP_MINUTES": str(D(self.full_stop_us) / 60_000_000),
                    "P50_RESERVE_RECOVERY_TIME_HOURS": percentile(completed_recovery, 50),
                    "P90_RESERVE_RECOVERY_TIME_HOURS": percentile(completed_recovery, 90),
                    "P99_RESERVE_RECOVERY_TIME_HOURS": percentile(completed_recovery, 99),
                    "MAX_RESERVE_RECOVERY_TIME_HOURS": str(D(max(completed_recovery)) / HOUR)
                    if completed_recovery
                    else None,
                    "RESERVE_RECOVERY_OPEN_EPISODES": sum(
                        r["recovered_us"] is None for r in self.recoveries
                    ),
                    "RESERVE_RECOVERY_SCOPE": (
                        "OPERATING_SETTLED_CONSUMPTION_AND_Q4_PHYSICAL_LOSS_DELTAS"
                    ),
                    "HOLD_P50_HOURS": percentile(completed_hold, 50),
                    "HOLD_P90_HOURS": percentile(completed_hold, 90),
                    "HOLD_P99_HOURS": percentile(completed_hold, 99),
                    "REALIZED_FEES_QUOTE": str(
                        self.realized_fees + sum((q.realized_cycle_fees for q in self.queues), ZERO)
                    ),
                    "TOTAL_FEES_QUOTE": str(sum((q.fees for q in self.queues), ZERO)),
                    "RESERVE_NET_CHANGE": str(self.reserve - D(10)),
                    "RESERVE_ESCROW": str(sum(self.claims.values(), ZERO)),
                    "EXECUTION_EVIDENCE_CLASS": (
                        "CONDITIONAL_PILOT_PARAMETERIZED_FLOW_REFRESH_NOT_HISTORICAL_L2"
                    ),
                    "GLOBAL_THROTTLE_MODEL": (
                        "ACCEPTED_SUBMISSIONS_AND_CANCEL_REQUESTS; LOCAL_REJECTS_NOT_SENT"
                    ),
                    **{
                        f"Q{q.queue_id}_CAPITAL": str(q.cash + q.cost + q.dust_cost)
                        for q in self.queues
                    },
                }
            )
            return result

    def checkpoint(self) -> dict[str, Any]:
        excluded = {"runtime", "profile", "rules_at", "envelope", "queues", "audit"}
        state = _encode({k: v for k, v in vars(self).items() if k not in excluded})
        payload = {
            "state": state,
            "queues": [q.checkpoint() for q in self.queues],
            "profile": _encode(asdict(self.profile)),
            "envelope": _encode(asdict(self.envelope)),
        }
        return {"payload": payload, "sha256": canonical_hash(payload)}

    def restore(self, checkpoint: dict[str, Any]) -> None:
        payload = checkpoint["payload"]
        if canonical_hash(payload) != checkpoint["sha256"]:
            raise ValueError("M013_CHECKPOINT_HASH")
        state = _decode(payload["state"])
        if (
            state["identity"] != self.identity
            or state["spec_hash"] != self.spec_hash
            or state["end_us"] != self.end_us
        ):
            raise ValueError("M013_CHECKPOINT_IDENTITY")
        if _decode(payload["profile"]) != asdict(self.profile) or _decode(
            payload["envelope"]
        ) != asdict(self.envelope):
            raise ValueError("M013_CHECKPOINT_EXECUTION_PROFILE")
        self.__dict__.update(state)
        self.counts, self.full_days = Counter(self.counts), Counter(self.full_days)
        self.claims = {int(k): v for k, v in self.claims.items()}
        for q, saved in zip(self.queues, payload["queues"], strict=True):
            q.restore(saved)
        self._invariants()

    def finish(self) -> dict[str, Any]:
        if self.last_us != self.identity.get("expected_last_trade_us", self.end_us - 1):
            raise ValueError("PHYSICAL_CUTOFF_NOT_REACHED")
        if self.processed_trades != self.identity.get(
            "expected_trade_count", self.processed_trades
        ):
            raise ValueError("FULL_INTERVAL_TRADE_COUNT_MISMATCH")
        self.advance_to(self.end_us)
        self.completed = True
        return self.metrics()

    def extend_to(
        self,
        end_us: int,
        identity: dict[str, Any],
        stage1_decision: str,
        audit_sha256: str,
        *,
        runtime: Any | None = None,
    ) -> None:
        if not self.completed or stage1_decision != "PASS_TO_EXTENSION" or len(audit_sha256) != 64:
            raise ValueError("M013_EXTENSION_GATE_CLOSED")
        mutable = {
            "expected_last_trade_us",
            "expected_trade_count",
            "stage",
            "stage_data_manifest_sha256",
            "end_exclusive",
            "extension_tape_hash",
        }
        if (
            {k: v for k, v in identity.items() if k not in mutable}
            != {k: v for k, v in self.identity.items() if k not in mutable}
        ) or end_us <= self.end_us:
            raise ValueError("M013_EXTENSION_IDENTITY_CHANGED")
        self.audit.append(
            {"kind": "STAGE_EXTENSION", "time_us": self.end_us, "audit_sha256": audit_sha256}
        )
        if runtime is not None:
            if (
                runtime.parent.model_hash != self.runtime.parent.model_hash
                or runtime.tape.tick_size != self.runtime.tape.tick_size
            ):
                raise ValueError("M013_EXTENSION_RUNTIME_STRATEGY_CHANGED")
            self.runtime = runtime
        self.end_us, self.identity, self.completed = end_us, identity, False
