"""M012 compounding capital/urgency policy over the unchanged reality kernel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Any, Literal, cast

from crypto_strategy_lab.domain import canonical_hash

from .b10_reality import (
    B10Execution,
    B10RealityReplay,
    BookEnvelope,
    ExecutionProfile,
    Order,
    SymbolRules,
    Trade,
    round_quantity,
)
from .serial_replay import EVENT_ORDER_SCALE, _minutes_to_events, _score, _select, _selection_grid

D = Decimal
ZERO = D(0)
HOUR = 3_600_000_000
POLICY = {
    "model_id": "M012",
    "strategy": "HIGH_UPTIME_DYNAMIC_RECOVERY",
    "capital_mode": "COMPOUNDING",
    "position_sizing": "AVAILABLE_OPERATING_CASH",
    "initial_operating": "100",
    "initial_reserve": "5",
    "profit_funding": "0.05",
    "reserve_target": "0.05",
    "reserve_floor_ratio": "0.001",
    "reserve_floor_absolute": "0.00000001",
    "urgency_hours": [12, 18, 24],
    "withdrawals": False,
}
B10_OWNER_POLICY = {
    "model_id": "M014",
    "capital_mode": "COMPOUNDING",
    "initial_operating": "100",
    "initial_reserve": "10",
    "profit_funding": "0.10",
    "reserve_floor_absolute": "2.5",
    "decisions": "B10_H1_B10_F2.5",
    "forced_timeout": False,
}
M016_DEADLINE_POLICY = {
    "model_id": "M016",
    "parent": "M015",
    "initial_operating": "100",
    "initial_reserve": "10",
    "profit_funding": "0.10",
    "reserve_floor": "2.5",
    "executable_loss_cap_bps": "10",
    "deadline_us": 7_200_000_000,
    "preparation_lead": "CANCEL_LATENCY_PLUS_TWO_ORDER_LATENCIES_PLUS_2US",
    "precedence": "LOSS_CAP_AND_RESERVE_FLOOR_BEFORE_DEADLINE",
    "deadline_action": "LATCH_PROTECTED_EXIT_WITHOUT_OPPORTUNITY_VETO",
    "violation": "INVENTORY_REMAINS_STRICTLY_AFTER_DEADLINE_NO_GRACE",
    "debt_mode": "REPORT_ONLY_NO_FUNDING_STATE_CHANGE",
}
M016_DEADLINE_POLICY_HASH = canonical_hash(M016_DEADLINE_POLICY)
M017_DEADLINE_POLICY = {
    **M016_DEADLINE_POLICY,
    "model_id": "M017",
    "executable_loss_cap_bps": "20",
}
M017_DEADLINE_POLICY_HASH = canonical_hash(M017_DEADLINE_POLICY)
M018_ENTRY_ADMISSION_POLICY = {
    "name": "CAUSAL_PASSIVE_BUY_CAP",
    "new_entry_price": "MIN_SELECTED_LOW_FLOOR_TO_TICK_ASK_MINUS_TICK",
    "exit_target": "PRESERVE_SELECTED_HIGH",
    "partial_entry": "FREEZE_FIRST_FILL_ORDER_LIMIT",
    "active_orders": "NO_BOOK_DRIVEN_CANCEL_OR_REPRICE",
    "unknown_book": "WAIT_FAIL_CLOSED",
}
M018_ENTRY_ADMISSION_POLICY_HASH = canonical_hash(M018_ENTRY_ADMISSION_POLICY)
DEADLINE_POLICY_HASHES = {
    "M016": M016_DEADLINE_POLICY_HASH,
    "M017": M017_DEADLINE_POLICY_HASH,
    "M018": M017_DEADLINE_POLICY_HASH,
}
DEADLINE_POLICIES = {
    M016_DEADLINE_POLICY_HASH: M016_DEADLINE_POLICY,
    M017_DEADLINE_POLICY_HASH: M017_DEADLINE_POLICY,
}


class HighUptimeExecution(B10Execution):
    def __init__(
        self,
        profile: ExecutionProfile,
        rules: SymbolRules,
        *,
        b10_owner_reserve: bool = False,
        priority_trade_through: bool = False,
        deadline_policy_hash: str | None = None,
    ) -> None:
        if deadline_policy_hash is not None and (
            deadline_policy_hash not in DEADLINE_POLICIES or not b10_owner_reserve
        ):
            raise ValueError("M016_DEADLINE_POLICY_IDENTITY_REQUIRED")
        if priority_trade_through and not b10_owner_reserve:
            raise ValueError("PRIORITY_INFERENCE_REQUIRES_OWNER_RESERVE_POLICY")
        super().__init__(profile, rules)
        self.b10_owner_reserve = b10_owner_reserve
        self.priority_trade_through = priority_trade_through
        if deadline_policy_hash is not None:
            self.deadline_policy_hash = deadline_policy_hash
        self.activation_evaluated_us: dict[str, int] = {}
        if b10_owner_reserve:
            self.reserve = self.reserve_min = D(10)
        self.lot_budget = ZERO
        self.reserve_escrow = ZERO
        self.needs_reselection = False
        self.supported_best_level: Decimal | None = None
        self.policy_hash = canonical_hash(B10_OWNER_POLICY if b10_owner_reserve else POLICY)
        if priority_trade_through:
            self.policy_hash = canonical_hash(
                {
                    **B10_OWNER_POLICY,
                    "model_id": "M015",
                    "execution_hypothesis": "PRIORITY_TRADE_THROUGH_CONDITIONAL",
                }
            )
        if deadline_policy_hash is not None:
            self.policy_hash = deadline_policy_hash

    @property
    def operating_bank(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 128
            return self.cash + self.cost + self.dust_cost

    @property
    def reserve_target(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 128
            return self.operating_bank * D("0.05")

    @property
    def reserve_floor(self) -> Decimal:
        if self.b10_owner_reserve:
            return D("2.5")
        with localcontext() as ctx:
            ctx.prec = 128
            return max(D("0.00000001"), self.operating_bank * D("0.001"))

    def protected_exit(self) -> dict[str, Any]:
        with localcontext() as ctx:
            ctx.prec = 128
            if not self.book_valid or not self.bids or self.bids[0][1] <= 0:
                return {"eligible": False, "reason": "NO_LIQUIDITY"}
            quantity = round_quantity(self.inventory, self.rules.step_size)
            if quantity <= 0:
                return {"eligible": False, "reason": "NO_SELLABLE_QUANTITY"}
            restored_bank = self.operating_bank + self.sold_cost - self.sell_net
            guard = max(D("0.00000001"), D("0.001") * max(self.operating_bank, restored_bank))
            if self.b10_owner_reserve:
                guard = D("2.5")
            budget = max(ZERO, self.reserve - guard)
            deadline_budget_details: dict[str, Any] = {}
            if getattr(self, "deadline_policy_hash", None) is not None:
                policy = DEADLINE_POLICIES[self.deadline_policy_hash]
                loss_budget = restored_bank * (D(policy["executable_loss_cap_bps"]) / D(10_000))
                deadline_budget_details = {
                    "loss_cap_budget": str(loss_budget),
                    "reserve_budget": str(budget),
                    "binding_constraint": "LOSS_CAP" if loss_budget <= budget else "RESERVE_FLOOR",
                }
                budget = min(budget, loss_budget)
            cost = self.sold_cost + self.cost * quantity / self.inventory
            minimum = max(
                self.rules.min_price,
                (cost - self.sell_net - budget) / (quantity * (1 - self.profile.taker_fee)),
            )
            price = (minimum / self.rules.tick_size).to_integral_value(
                rounding=ROUND_CEILING
            ) * self.rules.tick_size
            worst = max(
                ZERO, cost - self.sell_net - quantity * price * (1 - self.profile.taker_fee)
            )
            try:
                self.rules.validate("SELL", price, quantity)
            except ValueError as exc:
                return {"eligible": False, "reason": "FILTER_REJECTION", "detail": str(exc)}
            if worst > budget:
                raise ValueError("M012_PROTECTED_PRICE_BUDGET_INVARIANT")
            if self.bids[0][0] < price:
                return {
                    "eligible": False,
                    "reason": (
                        "RELEASE_BLOCKED_BY_LOSS_CAP_OR_FLOOR"
                        if getattr(self, "deadline_policy_hash", None) is not None
                        else "RELEASE_BLOCKED_BY_RESERVE"
                    ),
                    "protected_price": str(price),
                    "floor_guard": str(guard),
                    **deadline_budget_details,
                    **(
                        {"available_budget": str(budget)}
                        if getattr(self, "deadline_policy_hash", None) is not None
                        else {}
                    ),
                }
            return {
                "eligible": True,
                "price": price,
                "quantity": quantity,
                "worst_deficit": worst,
                "floor_guard": guard,
                "available_budget": budget,
            }

    def submit(
        self,
        side: Literal["BUY", "SELL"],
        price: Decimal,
        time_us: int,
        *,
        release: bool = False,
        continuation: bool = False,
    ) -> Order | None:
        if release:
            protected = self.protected_exit()
            if not protected["eligible"]:
                self.counts[protected["reason"]] += 1
                return None
            if price != protected["price"]:
                raise ValueError("M012_RELEASE_MUST_USE_PROTECTED_PRICE")
            order = super().submit(side, price, time_us, release=True)
            if order is not None:
                self.reserve_escrow = protected["worst_deficit"]
                self._record(
                    "RESERVE_ESCROW",
                    time_us=time_us,
                    order_id=order.order_id,
                    amount=str(self.reserve_escrow),
                    floor_guard=str(protected["floor_guard"]),
                    protected_price=str(price),
                )
            return order
        if side == "SELL":
            return super().submit(side, price, time_us)
        if self.order is not None:
            raise ValueError("SERIAL_ORDER_INVARIANT")
        if time_us <= self.last_cancel_ack_us:
            return None
        if not self.book_valid or self.last_book_us > time_us:
            raise ValueError("NO_CAUSAL_BOOK")
        if self.releasing or (self.inventory > 0 and not continuation):
            raise ValueError("SERIAL_LOT_INVARIANT")
        with localcontext() as ctx:
            ctx.prec = 128
            budget = min(self.cash, self.lot_budget - self.buy_cost) if continuation else self.cash
            quantity = round_quantity(budget / price, self.rules.step_size)
            supported = self.supported_best_level
            if supported is not None and quantity > supported:
                self.counts["CAPACITY_LIMIT_REACHED"] += 1
                self._record(
                    "CAPACITY_LIMIT",
                    time_us=time_us,
                    requested_quantity=str(quantity),
                    supported_best_level=str(supported),
                    source="CONDITIONAL_PROFILE_DEPTH",
                )
            try:
                self.rules.validate("BUY", price, quantity)
            except ValueError as exc:
                self.counts["ORDER_REJECTION_COUNT"] += 1
                if quantity > self.rules.max_quantity or price * quantity > self.rules.max_notional:
                    self.counts["CAPACITY_LIMIT_REACHED"] += 1
                self._record(
                    "REJECTION", time_us=time_us, reason=str(exc), requested_budget=str(budget)
                )
                return None
            window = time_us // self.rules.window_us
            self.messages = [t for t in self.messages if t // self.rules.window_us == window]
            if len(self.messages) >= self.rules.orders_per_window:
                self.counts["RATE_LIMIT_REJECTION"] += 1
                return None
            self.messages.append(time_us)
            if not continuation:
                self.lot_budget = budget
            order = Order(
                len(self.orders) + 1,
                side,
                price,
                quantity,
                time_us,
                time_us + self.profile.latency_us,
                self.profile.queue_ahead,
            )
            self.orders.append(order)
            self.order = order
            self._record(
                "SUBMIT",
                **asdict(order),
                capital_mode="COMPOUNDING",
                lot_budget=str(self.lot_budget),
            )
            return order

    def _advance(self, time_us: int) -> None:
        before = self.order
        was_pending = before is not None and before.status == "PENDING"
        super()._advance(time_us)
        if (
            self.priority_trade_through
            and was_pending
            and self.order is before
            and before.status == "ACTIVE"
            and not before.release
        ):
            self.activation_evaluated_us[str(before.order_id)] = time_us
        if before is not None and before.release and self.order is None:
            self.reserve_escrow = (
                max(ZERO, self.sold_cost - self.sell_net) if self.b10_owner_reserve else ZERO
            )

    def trade(self, trade: Trade) -> None:
        # The authority performs causal validation, cancellation and ordinary
        # equality-price queue depletion first. A through print cannot satisfy
        # that equality branch, so its volume is still entirely unspent here.
        super().trade(trade)
        if not self.priority_trade_through:
            return
        order = self.order
        if order is None or order.release or order.status != "ACTIVE" or not self.book_valid:
            return
        activated = self.activation_evaluated_us.get(str(order.order_id))
        if activated is None or activated >= trade.time_us:
            return
        if order.cancel_us is not None and trade.time_us >= order.cancel_us:
            return
        if trade.buyer_maker != (order.side == "BUY"):
            return
        through = trade.price < order.price if order.side == "BUY" else trade.price > order.price
        if not through:
            return
        with localcontext() as ctx:
            ctx.prec = 128
            quantity = min(trade.quantity, order.quantity - order.filled)
            if quantity <= 0:
                return
            self._record(
                "PRICE_THROUGH_PRIORITY_INFERENCE",
                order_id=order.order_id,
                time_us=trade.time_us,
                trade_id=trade.trade_id,
                raw_price=str(trade.price),
                raw_quantity=str(trade.quantity),
                buyer_maker=trade.buyer_maker,
                order_limit=str(order.price),
                queue_before=str(order.queue),
                queue_after="0",
                activation_evaluated_us=activated,
                modeled_active_us=order.active_us,
                own_quantity=str(quantity),
                remaining_raw_quantity=str(trade.quantity - quantity),
                evidence_class="COUNTERFACTUAL_PRICE_PRIORITY_NOT_OBSERVED_QUEUE_CLEARANCE",
            )
            order.queue = ZERO
            self.counts["PRICE_THROUGH_PRIORITY_INFERENCE"] += 1
            self._fill(order, quantity, order.price, trade.time_us, "TRADE_THROUGH", trade.trade_id)

    def _settle(self, time_us: int) -> None:
        if self.inventory >= self.rules.step_size:
            raise ValueError("M012_CANNOT_SETTLE_OPERATIONAL_REMAINDER")
        self.dust += self.inventory
        self.dust_cost += self.cost
        self.inventory = ZERO
        self.cost = ZERO
        profit = self.sell_net - self.sold_cost
        forced = self.release_execution_started
        deficit = max(ZERO, -profit) if forced else ZERO
        funding = max(ZERO, profit) * (D("0.10") if self.b10_owner_reserve else D("0.05"))
        equity_before = self.cash + self.reserve
        if deficit:
            post_cash = self.cash + deficit
            post_floor = max(D("0.00000001"), (post_cash + self.dust_cost) * D("0.001"))
            if self.b10_owner_reserve:
                post_floor = D("2.5")
            if self.reserve - deficit < post_floor or deficit > self.reserve_escrow:
                raise ValueError("M012_REALIZED_DEFICIT_EXCEEDS_PROTECTED_ESCROW")
            self.reserve -= deficit
            self.cash += deficit
            self.reserve_consumption += deficit
        if funding:
            self.reserve += funding
            self.cash -= funding
            self.reserve_funding += funding
        if self.reserve <= 0 or self.reserve < self.reserve_floor:
            raise ValueError("M012_RESERVE_FLOOR_VIOLATION")
        if self.cash + self.reserve != equity_before:
            raise ValueError("M012_TRANSFER_EQUITY_INVARIANT")
        if forced:
            self.counts["RELEASE_FILLED"] += 1
            self.counts["FORCED_NET_POSITIVE_CLOSURES"] += int(profit > 0)
            self.needs_reselection = True
        else:
            self.counts["FULLY_FILLED_CYCLES"] += 1
            self.counts["NET_POSITIVE_CYCLES"] += int(profit > 0)
        self.reserve_min = min(self.reserve_min, self.reserve)
        self._record(
            "SETTLEMENT",
            time_us=time_us,
            net_profit=str(profit),
            release=forced,
            reserve=str(self.reserve),
            cash=str(self.cash),
            dust=str(self.dust),
            dust_cost=str(self.dust_cost),
            sold_cost=str(self.sold_cost),
            gross_pnl=str(profit + self.realized_cycle_fees),
            realized_fees_quote=str(self.realized_cycle_fees),
            actual_release_loss=str(deficit),
            reserve_transfer=str(deficit if forced and deficit else funding),
            reserve_contribution=str(funding),
            reserve_consumption=str(deficit),
            reserve_floor=str(self.reserve_floor),
            lot_budget=str(self.lot_budget),
            capital_mode="COMPOUNDING",
        )
        self.cost = self.buy_cost = self.sell_net = self.sold_cost = ZERO
        self.buy_fee_basis = self.realized_cycle_fees = self.reserve_escrow = ZERO
        self.entry_us = None
        self.releasing = self.release_execution_started = self.buy_complete = False
        self.release_signal_bank = self.release_signal_id = None

    def restore(self, checkpoint: dict[str, Any]) -> None:
        expected_policy = self.policy_hash
        super().restore(checkpoint)
        if self.policy_hash != expected_policy:
            raise ValueError("M012_CHECKPOINT_POLICY_MISMATCH")


class B10ReserveReplay(B10RealityReplay):
    """M014: original F2.5 decisions with OWNER treasury, never M012 urgency."""

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
        gaps: tuple[tuple[int, int], ...] = (),
    ) -> None:
        if (
            identity.get("model_id") not in ("M014", "M015", *DEADLINE_POLICY_HASHES)
            or identity.get("capital_mode") != "COMPOUNDING"
        ):
            raise ValueError("M014_COMPOUNDING_IDENTITY_REQUIRED")
        if identity.get("model_id") == "M018":
            if identity.get("entry_admission_policy_hash") != M018_ENTRY_ADMISSION_POLICY_HASH:
                raise ValueError("M018_ENTRY_ADMISSION_POLICY_IDENTITY_REQUIRED")
        elif identity.get("entry_admission_policy_hash") is not None:
            raise ValueError("ENTRY_ADMISSION_POLICY_REQUIRES_M018")
        if (
            identity.get("model_id") in DEADLINE_POLICY_HASHES
            and identity.get("deadline_policy_hash") != DEADLINE_POLICY_HASHES[identity["model_id"]]
        ):
            raise ValueError("M016_DEADLINE_POLICY_IDENTITY_REQUIRED")
        if identity.get("model_id") in DEADLINE_POLICY_HASHES and not getattr(
            self, "supports_protected_deadline", False
        ):
            raise ValueError("M016_REQUIRES_OBSERVED_DEADLINE_DRIVER")
        if (
            identity.get("model_id") not in DEADLINE_POLICY_HASHES
            and identity.get("deadline_policy_hash") is not None
        ):
            raise ValueError("DEADLINE_POLICY_REQUIRES_M016")
        priority = identity.get("model_id") in ("M015", *DEADLINE_POLICY_HASHES)
        if identity.get("priority_trade_through", False) is not priority:
            raise ValueError("M015_EXPLICIT_PRIORITY_HYPOTHESIS_REQUIRED")
        super().__init__(
            runtime,
            profile,
            rules_at,
            envelope,
            start_us=start_us,
            end_us=end_us,
            identity=identity,
            gaps=gaps,
            decision_reserve_floor=D("2.5"),
        )
        self.execution = HighUptimeExecution(
            profile,
            rules_at(start_us),
            b10_owner_reserve=True,
            priority_trade_through=priority,
            deadline_policy_hash=identity.get("deadline_policy_hash"),
        )
        self.execution.supported_best_level = envelope.release_depth
        self.peak_equity = D(110)
        self.metrics_last_us = start_us
        self.working_order_us = self.holding_us = 0
        self.last_release_epoch: int | None = None

    @property
    def engine(self) -> HighUptimeExecution:
        return cast(HighUptimeExecution, self.execution)

    def _integrate(self, timestamp: int) -> None:
        if timestamp < self.metrics_last_us:
            raise ValueError("M014_NONCAUSAL_METRICS")
        delta = timestamp - self.metrics_last_us
        if self.engine.order is not None:
            self.working_order_us += delta
        if self.engine.entry_us is not None:
            self.holding_us += delta
        self.metrics_last_us = timestamp

    def _clock(self, timestamp: int) -> None:
        self._integrate(timestamp)
        super()._clock(timestamp)

    def _submit_next(self, timestamp: int) -> None:
        if self.engine.releasing:
            if self.engine.order is not None or self.last_release_epoch == self.depth_epoch:
                return
            protected = self.engine.protected_exit()
            if not protected["eligible"]:
                self.engine.counts[protected["reason"]] += 1
                return
            if self.engine.submit("SELL", protected["price"], timestamp, release=True) is not None:
                self.last_release_epoch = self.depth_epoch
            return
        super()._submit_next(timestamp)

    def step(self, trade: Trade) -> None:
        # Timer integration must occur in order, before the incoming trade.
        if self.completed or not self.start_us <= trade.time_us < self.end_us:
            raise ValueError("TRADE_OUTSIDE_REPLAY_INTERVAL")
        if trade.time_us < self.metrics_last_us:
            raise ValueError("M014_NONCAUSAL_TRADE")
        while self._next_clock() <= trade.time_us:
            self._clock(self._next_clock())
        self._integrate(trade.time_us)
        super().step(trade)

    def advance_to(self, timestamp_us: int) -> None:
        if timestamp_us < self.metrics_last_us or timestamp_us > self.end_us:
            raise ValueError("M014_INVALID_TIME_ADVANCE")
        while self._next_clock() <= timestamp_us and self._next_clock() < self.end_us:
            self._clock(self._next_clock())
        self._integrate(timestamp_us)

    def metrics(self, as_of_us: int | None = None) -> dict[str, Any]:
        timestamp = self.metrics_last_us if as_of_us is None else as_of_us
        if timestamp != self.metrics_last_us:
            raise ValueError("M014_METRICS_REQUIRE_ADVANCED_PREFIX")
        engine = self.engine
        with localcontext() as ctx:
            ctx.prec = 128
            bid = engine.bids[0][0] if engine.bids else ZERO
            equity = engine.cash + engine.reserve + (engine.inventory + engine.dust) * bid
            age = timestamp - engine.entry_us if engine.entry_us is not None else 0
            elapsed = timestamp - self.start_us
            closed_days = elapsed // (24 * HOUR)
            cutoff_day = datetime.fromtimestamp(timestamp / 1_000_000, UTC).date().isoformat()
            active_days = sum(
                count > 0 and day < cutoff_day for day, count in self.net_days.items()
            )
            realized_fees = engine.realized_cycle_fees + sum(
                (D(row["realized_fees_quote"]) for row in engine.settlements), ZERO
            )
            realized_net = engine.operating_bank + engine.reserve - D(110)
            return {
                "MODEL_ID": self.identity["model_id"],
                "EXECUTION_HYPOTHESIS": (
                    "PRIORITY_TRADE_THROUGH_CONDITIONAL"
                    if engine.priority_trade_through
                    else "EXACT_PRICE_FIXED_QUEUE_CONDITIONAL"
                ),
                "CAPITAL_MODE": "COMPOUNDING",
                "SIMULATION_TIMESTAMP": datetime.fromtimestamp(
                    timestamp / 1_000_000, UTC
                ).isoformat(),
                "SIMULATION_TIMESTAMP_US": timestamp,
                "PROCESSED_TRADES": self.processed_trades,
                "OPERATING_BANK": str(engine.operating_bank),
                "OPERATING_CASH": str(engine.cash),
                "RESERVE": str(engine.reserve),
                "TOTAL_EQUITY": str(equity),
                "NET_REALIZED_PNL": str(engine.operating_bank + engine.reserve - D(110)),
                "REALIZED_GROSS_PNL": str(realized_net + realized_fees),
                "REALIZED_FEES_QUOTE": str(realized_fees),
                "TOTAL_FEES_QUOTE": str(engine.fees),
                "OPEN_INVENTORY": str(engine.inventory),
                "DUST_BASE": str(engine.dust),
                "DUST_COST_BASIS": str(engine.dust_cost),
                "CURRENT_POSITION_NOTIONAL": str(engine.cost),
                "CYCLE_NOTIONAL": str(engine.lot_budget),
                "FULL_FILL_CYCLES": engine.counts["FULLY_FILLED_CYCLES"],
                "NET_POSITIVE_CYCLES": engine.counts["NET_POSITIVE_CYCLES"],
                "RELEASE_FILLED": engine.counts["RELEASE_FILLED"],
                "RESERVE_FUNDING": str(engine.reserve_funding),
                "RESERVE_CONSUMPTION": str(engine.reserve_consumption),
                "MIN_RESERVE": str(engine.reserve_min),
                "RESERVE_ESCROW": str(engine.reserve_escrow),
                "DAILY_FULL_CYCLES": dict(self.full_days),
                "DAILY_NET_POSITIVE_CYCLES": dict(self.net_days),
                "COMPLETED_UTC_DAYS": closed_days,
                "ZERO_CYCLE_DAYS": max(0, closed_days - active_days),
                "CURRENT_HOLD_HOURS": str(D(age) / HOUR),
                "MAX_HOLD_HOURS": str(D(max([*self.holds_us, age])) / HOUR),
                "HOLDING_HOURS": str(D(self.holding_us) / HOUR),
                "WORKING_ORDER_HOURS": str(D(self.working_order_us) / HOUR),
                "FLAT_HOURS": str(D(elapsed - self.holding_us) / HOUR),
                "MAX_DRAWDOWN_PCT": str(self.max_drawdown * 100),
                "HOLDS_OVER_24H": sum(h >= 24 * HOUR for h in self.holds_us)
                + int(age >= 24 * HOUR),
                "COUNTS": dict(engine.counts),
                "VERDICT": "PENDING",
                "STATUS": "AWAITING_OWNER_APPROVAL" if self.completed else "RUNNING",
                "RUN_STATUS": "COMPLETE" if self.completed else "RUNNING",
                "EXECUTION_EVIDENCE": "CONDITIONAL_PILOT_NOT_HISTORICAL_L2",
            }

    def finish(self) -> dict[str, Any]:
        if self.last_mark is None:
            raise ValueError("NO_REPLAY_TRADES")
        if self.last_us != self.identity.get("expected_last_trade_us", self.end_us - 1):
            raise ValueError("PHYSICAL_CUTOFF_NOT_REACHED")
        if self.processed_trades != self.identity.get(
            "expected_trade_count", self.processed_trades
        ):
            raise ValueError("FULL_INTERVAL_TRADE_COUNT_MISMATCH")
        self.advance_to(self.end_us)
        self.completed = True
        return self.metrics()


class HighUptimeRecoveryReplay(B10RealityReplay):
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
        gaps: tuple[tuple[int, int], ...] = (),
    ) -> None:
        if identity.get("model_id") != "M012" or identity.get("capital_mode") != "COMPOUNDING":
            raise ValueError("M012_COMPOUNDING_IDENTITY_REQUIRED")
        super().__init__(
            runtime,
            profile,
            rules_at,
            envelope,
            start_us=start_us,
            end_us=end_us,
            identity=identity,
            gaps=gaps,
        )
        self.execution = HighUptimeExecution(profile, rules_at(start_us))
        self.execution.supported_best_level = envelope.release_depth
        self.hard_lock_events: list[dict[str, Any]] = []
        self.violated_entries: list[int] = []
        self.urgency = "NORMAL_OPERATION"
        self.last_release_epoch: int | None = None
        self.last_block_reason: str | None = None
        self.below_target_us = self.downtime_us = self.working_order_us = 0
        self.capacity_blocked_us = 0
        self.rebuilding_episodes: list[dict[str, Any]] = []
        self.near_depletion = False
        self.metrics_last_us = start_us
        self.current_canonical_event = start_us * EVENT_ORDER_SCALE

    @property
    def engine(self) -> HighUptimeExecution:
        return cast(HighUptimeExecution, self.execution)

    def _candidate(self, timestamp: int) -> tuple[int, int] | None:
        runtime = self.decisions.runtime
        event = timestamp * EVENT_ORDER_SCALE
        _, distances, multiple = _selection_grid(
            runtime.parent,
            runtime.tick_catalog,
            event,
            runtime.tape.tick_size,
            runtime.tape.observed_tick_evidence_event,
        )
        start = event - _minutes_to_events(runtime.parent.lookback_minutes)
        candidate = _select(
            runtime.timelines,
            runtime.parent,
            start,
            event,
            eligible_distances=distances,
            grid_multiple=multiple,
        )
        if (
            candidate is None
            or _score(candidate, runtime.timelines, runtime.parent, start, event) <= 0
        ):
            return None
        return cast(tuple[int, int], candidate)

    def _enter_release(self, timestamp: int) -> None:
        engine = self.engine
        if not engine.releasing:
            engine.releasing = True
            engine.counts["RELEASE_SIGNALS"] += 1
            self.release_signals.append(
                {
                    "time_us": timestamp,
                    "urgency": self.urgency,
                    "operating_bank": str(engine.operating_bank),
                }
            )
            engine._record(
                "RELEASE_SIGNAL",
                time_us=timestamp,
                urgency=self.urgency,
                operating_bank_before=str(engine.operating_bank),
            )
        if engine.order is not None and not engine.order.release:
            engine.cancel(timestamp)

    def _clock(self, timestamp: int) -> None:
        self._integrate(timestamp)
        engine = self.engine
        self.last_clock_us = timestamp
        self.next_release = None
        engine.rules = self.rules_at(timestamp)
        if any(start <= timestamp < end for start, end in self.gaps):
            engine.book_valid = False
        if engine.order is not None and not engine.order.release:
            engine._advance(timestamp)
        if engine.entry_us is not None:
            age = timestamp - engine.entry_us
            phase = (
                "MANDATORY_UNLOCK"
                if age >= 24 * HOUR
                else "HIGH_RELEASE_URGENCY"
                if age >= 18 * HOUR
                else "EARLY_WARNING"
                if age >= 12 * HOUR
                else "NORMAL_OPERATION"
            )
            if phase != self.urgency:
                self.urgency = phase
                engine._record("URGENCY_TRANSITION", time_us=timestamp, state=phase)
            if age > 24 * HOUR and engine.entry_us not in self.violated_entries:
                self.violated_entries.append(engine.entry_us)
                record = {
                    "entry_us": engine.entry_us,
                    "deadline_us": engine.entry_us + 24 * HOUR,
                    "time_us": timestamp,
                    "cause": self.last_block_reason or "UNRESOLVED_EXECUTION",
                }
                self.hard_lock_events.append(record)
                engine.counts["HARD_LOCK_VIOLATIONS"] += 1
                engine._record("HARD_LOCK_VIOLATION", **record)
            if age >= 18 * HOUR:
                self._enter_release(timestamp)
            elif age >= 12 * HOUR and timestamp >= self.next_decision and not engine.releasing:
                candidate = self._candidate(timestamp)
                if (
                    candidate is not None
                    and candidate != self.position_candidate
                    and engine.protected_exit()["eligible"]
                ):
                    self._enter_release(timestamp)
        if timestamp >= self.next_decision:
            old = self.decisions.state.candidate
            self.decisions.select(timestamp * EVENT_ORDER_SCALE, engine)
            self.next_decision += self.interval
            if (
                engine.order is not None
                and engine.order.side == "BUY"
                and old != self.decisions.state.candidate
            ):
                engine.cancel(timestamp)
        self._submit_next(timestamp)

    def _next_clock(self) -> int:
        self.next_release = None
        clocks = [super()._next_clock()]
        if self.engine.entry_us is not None:
            clocks.extend(self.engine.entry_us + h * HOUR for h in (12, 18, 24))
            if self.engine.entry_us not in self.violated_entries:
                clocks.append(self.engine.entry_us + 24 * HOUR + 1)
        return min(clock for clock in clocks if clock > self.last_clock_us)

    def _submit_next(self, timestamp: int) -> None:
        engine = self.engine
        if engine.order is not None or not engine.book_valid:
            return
        if engine.needs_reselection:
            event = (
                self.current_canonical_event
                if self.current_canonical_event // EVENT_ORDER_SCALE == timestamp
                else timestamp * EVENT_ORDER_SCALE
            )
            self.decisions.after_ordinary_exit(event)
            engine.needs_reselection = False
        if engine.releasing:
            if (
                timestamp <= engine.last_cancel_ack_us
                or self.depth_epoch == self.last_release_epoch
            ):
                return
            self.last_release_epoch = self.depth_epoch
            protected = engine.protected_exit()
            if not protected["eligible"]:
                reason = protected["reason"]
                engine.counts[reason] += 1
                if reason != self.last_block_reason:
                    engine.counts[reason + "_EPISODES"] += 1
                    engine._record("RELEASE_BLOCKED", time_us=timestamp, **protected)
                self.last_block_reason = reason
                return
            self.last_block_reason = None
            engine.submit("SELL", protected["price"], timestamp, release=True)
            return
        super()._submit_next(timestamp)

    def step(self, trade: Trade) -> None:
        self.advance_to(trade.time_us)
        self._integrate(trade.time_us)
        self.current_canonical_event = trade.canonical_event or trade.time_us * EVENT_ORDER_SCALE
        super().step(trade)
        self.next_release = None
        if self.engine.entry_us is None:
            self.urgency = "NORMAL_OPERATION"
        below = self.engine.reserve < self.engine.reserve_target
        open_episode = (
            self.rebuilding_episodes[-1]
            if self.rebuilding_episodes and self.rebuilding_episodes[-1]["end_us"] is None
            else None
        )
        if below and open_episode is None:
            self.rebuilding_episodes.append({"start_us": trade.time_us, "end_us": None})
        elif not below and open_episode is not None:
            open_episode["end_us"] = trade.time_us
        near = self.engine.reserve <= 2 * self.engine.reserve_floor
        if near and not self.near_depletion:
            self.engine.counts["RESERVE_NEAR_DEPLETION_EVENTS"] += 1
        self.near_depletion = near

    def advance_to(self, timestamp_us: int) -> None:
        """Advance causal clocks, never ingest a trade or replenish a book."""
        if timestamp_us < self.metrics_last_us or timestamp_us > self.end_us:
            raise ValueError("M012_INVALID_TIME_ADVANCE")
        while self._next_clock() <= timestamp_us and self._next_clock() < self.end_us:
            self._clock(self._next_clock())
        self._integrate(timestamp_us)

    def _integrate(self, timestamp: int) -> None:
        if timestamp < self.metrics_last_us:
            raise ValueError("M012_NONCAUSAL_METRICS")
        interval = timestamp - self.metrics_last_us
        if self.engine.reserve < self.engine.reserve_target:
            self.below_target_us += interval
        if self.engine.order is not None:
            self.working_order_us += interval
        if self.engine.entry_us is not None:
            self.downtime_us += max(
                0, timestamp - max(self.metrics_last_us, self.engine.entry_us + 12 * HOUR)
            )
        elif not self._can_fund_entry():
            self.downtime_us += interval
            if self._capacity_blocks_entry():
                self.capacity_blocked_us += interval
        self.metrics_last_us = timestamp

    def _can_fund_entry(self) -> bool:
        candidate = self.decisions.state.candidate
        if candidate is None:
            # No selected opportunity is not a capital-insufficiency event.
            return True
        with localcontext() as ctx:
            ctx.prec = 128
            price = D(candidate[0]) * self.decisions.runtime.tape.tick_size
            if price <= 0:
                return False
            quantity = round_quantity(self.engine.cash / price, self.engine.rules.step_size)
            # Price/grid eligibility is not capital insufficiency. The frozen
            # uptime denominator includes only minimum cash and capacity gates.
            return (
                quantity >= self.engine.rules.min_quantity
                and quantity * price >= self.engine.rules.min_notional
                and not self._capacity_blocks_entry()
            )

    def _capacity_blocks_entry(self) -> bool:
        candidate = self.decisions.state.candidate
        if candidate is None:
            return False
        with localcontext() as ctx:
            ctx.prec = 128
            price = D(candidate[0]) * self.decisions.runtime.tape.tick_size
            if price <= 0:
                return False
            quantity = round_quantity(self.engine.cash / price, self.engine.rules.step_size)
            return (
                quantity > self.engine.rules.max_quantity
                or quantity * price > self.engine.rules.max_notional
            )

    def metrics(self, as_of_us: int | None = None) -> dict[str, Any]:
        engine = self.engine
        timestamp = self.metrics_last_us if as_of_us is None else as_of_us
        if timestamp != self.metrics_last_us:
            raise ValueError("M012_METRICS_REQUIRE_ADVANCED_PREFIX")
        elapsed = timestamp - self.start_us
        holds = self.holds_us + (
            [timestamp - engine.entry_us] if engine.entry_us is not None else []
        )
        days = (
            datetime.fromtimestamp(timestamp / 1_000_000, UTC).date()
            - datetime.fromtimestamp(self.start_us / 1_000_000, UTC).date()
        ).days
        day = datetime.fromtimestamp(timestamp / 1_000_000, UTC).date().isoformat()
        active = sum(date < day for date in self.full_days)
        if self.completed and timestamp == self.end_us and timestamp % (24 * HOUR):
            days += 1
            active += int(day in self.full_days)
        with localcontext() as ctx:
            ctx.prec = 128
            net = (
                sum((D(row["net_profit"]) for row in engine.settlements), ZERO)
                + engine.sell_net
                - engine.sold_cost
            )
            realized_fees = (
                sum((D(row["realized_fees_quote"]) for row in engine.settlements), ZERO)
                + engine.realized_cycle_fees
            )
            release_loss = sum((D(row["actual_release_loss"]) for row in engine.settlements), ZERO)
            if release_loss != engine.reserve_consumption:
                raise ValueError("M012_RELEASE_LEDGER_RECONCILIATION")
            mark = engine.bids[0][0] if engine.bids else ZERO
            equity = engine.cash + engine.reserve + (engine.inventory + engine.dust) * mark
            ordered_holds = sorted(self.holds_us)

            def percentile(percent: int) -> str:
                index = max(0, (len(ordered_holds) * percent + 99) // 100 - 1)
                return str(D(ordered_holds[index]) / HOUR) if ordered_holds else "0"

            rebuild = [
                (episode["end_us"] or timestamp) - episode["start_us"]
                for episode in self.rebuilding_episodes
            ]
            releases = [order for order in engine.orders if order.release]
            buys = [order for order in engine.orders if order.side == "BUY"]
            sells = [order for order in engine.orders if order.side == "SELL" and not order.release]

            def outcomes(orders: list[Order]) -> dict[str, int]:
                return {
                    "SUBMITTED": len(orders),
                    "FULL": sum(o.status == "FILLED" for o in orders),
                    "PARTIAL_ONLY": sum(0 < o.filled < o.quantity for o in orders),
                    "NO_FILL": sum(o.filled == 0 for o in orders),
                    "PENDING": sum(o.status in ("PENDING", "ACTIVE") for o in orders),
                }

            return {
                "MODEL_ID": "M012",
                "STRATEGY": POLICY["strategy"],
                "CAPITAL_MODE": "COMPOUNDING",
                "SIMULATION_TIMESTAMP": datetime.fromtimestamp(
                    timestamp / 1_000_000, UTC
                ).isoformat(),
                "OPERATING_BANK": str(engine.operating_bank),
                "OPERATING_CASH": str(engine.cash),
                "RUN_STATUS": "COMPLETE" if self.completed else "RUNNING",
                "PROCESSED_TRADES": self.processed_trades,
                "CYCLE_NOTIONAL": str(
                    engine.lot_budget
                    if engine.entry_us is not None or engine.order
                    else engine.cash
                ),
                "RESERVE": str(engine.reserve),
                "TOTAL_EQUITY": str(equity),
                "CURRENT_POSITION_NOTIONAL": str(engine.cost),
                "CUMULATIVE_NET_PROFIT": str(net),
                "REALIZED_GROSS_PNL": str(net + realized_fees),
                "REALIZED_FEES_QUOTE": str(realized_fees),
                "TOTAL_FEES_QUOTE": str(engine.fees),
                "MAX_DRAWDOWN": str(self.max_drawdown),
                "OPEN_INVENTORY": str(engine.inventory),
                "DUST_BASE": str(engine.dust),
                "DUST_COST_BASIS": str(engine.dust_cost),
                "CUMULATIVE_RESERVE_FUNDING": str(engine.reserve_funding),
                "CUMULATIVE_RELEASE_LOSS": str(release_loss),
                "TARGET_RESERVE_AT_T": str(engine.reserve_target),
                "RESERVE_FLOOR": str(engine.reserve_floor),
                "RESERVE_RATIO": str(engine.reserve / engine.operating_bank)
                if engine.operating_bank
                else None,
                "RESERVE_MIN": str(engine.reserve_min),
                "RESERVE_ESCROW": str(engine.reserve_escrow),
                "TIME_BELOW_5_PERCENT_HOURS": str(D(self.below_target_us) / HOUR),
                "RESERVE_REBUILDING_EPISODES": len(rebuild),
                "RESERVE_REBUILDING_MEAN_HOURS": str(D(sum(rebuild)) / len(rebuild) / HOUR)
                if rebuild
                else "0",
                "RESERVE_REBUILDING_MAX_HOURS": str(D(max(rebuild, default=0)) / HOUR),
                "RESERVE_REBUILDING_OPEN": bool(
                    self.rebuilding_episodes and self.rebuilding_episodes[-1]["end_us"] is None
                ),
                "RESERVE_NEAR_DEPLETION_EVENTS": engine.counts["RESERVE_NEAR_DEPLETION_EVENTS"],
                "FULL_FILL_CYCLES": engine.counts["FULLY_FILLED_CYCLES"],
                "NET_POSITIVE_CYCLES": engine.counts["NET_POSITIVE_CYCLES"],
                "FORCED_NET_POSITIVE_CLOSURES": engine.counts["FORCED_NET_POSITIVE_CLOSURES"],
                "BUY_ORDERS": outcomes(buys),
                "SELL_ORDERS": outcomes(sells),
                "RELEASE_ORDERS": outcomes(releases),
                "RELEASE_SIGNALS": engine.counts["RELEASE_SIGNALS"],
                "RELEASE_FILLED": engine.counts["RELEASE_FILLED"],
                "RELEASE_PARTIAL": engine.counts["RELEASE_PARTIAL"],
                "RELEASE_UNFILLED": engine.counts["RELEASE_UNFILLED"],
                "RELEASE_BLOCKED_BY_RESERVE": engine.counts["RELEASE_BLOCKED_BY_RESERVE"],
                "ACTIVE_DAYS": active,
                "ZERO_DAYS": days - active,
                "CLOSED_UTC_DAYS": days,
                "MAX_HOLD_HOURS": str(D(max(holds, default=0)) / HOUR),
                "HOLD_P50_HOURS": percentile(50),
                "HOLD_P95_HOURS": percentile(95),
                "HOLD_P99_HOURS": percentile(99),
                "HOLD_QUANTILE_METHOD": "NEAREST_RANK_COMPLETED_LOTS_ONLY",
                "OPEN_CENSORED_HOLD_HOURS": str(D(timestamp - engine.entry_us) / HOUR)
                if engine.entry_us is not None
                else None,
                "LOCK_HOURS_GT12": str(sum((D(max(0, h - 12 * HOUR)) for h in holds), ZERO) / HOUR),
                "LOCK_HOURS_GT18": str(sum((D(max(0, h - 18 * HOUR)) for h in holds), ZERO) / HOUR),
                "LOCK_HOURS_GT24": str(sum((D(max(0, h - 24 * HOUR)) for h in holds), ZERO) / HOUR),
                "HARD_LOCK_VIOLATIONS": len(self.hard_lock_events),
                "MOTOR_UPTIME": str(1 - D(self.downtime_us) / elapsed) if elapsed else None,
                "DOWNTIME_HOURS": str(D(self.downtime_us) / HOUR),
                "WORKING_ORDER_HOURS": str(D(self.working_order_us) / HOUR),
                "CAPACITY_LIMIT_REACHED": engine.counts["CAPACITY_LIMIT_REACHED"],
                "CAPACITY_BLOCKED_HOURS": str(D(self.capacity_blocked_us) / HOUR),
                "CAUSAL_CYCLES_PURCHASED": None,
                "CAUSAL_LOCK_AVOIDED": None,
                "COUNTERFACTUAL_STATUS": "UNKNOWN_WITHOUT_MATCHED_CONTROL",
                "COUNTS": dict(engine.counts),
                "VERDICT": "PENDING",
                "NO_OWNER_WITHDRAWALS": True,
            }

    def finish(self) -> dict[str, Any]:
        if self.last_mark is None:
            raise ValueError("NO_REPLAY_TRADES")
        if self.last_us != self.identity.get("expected_last_trade_us", self.end_us - 1):
            raise ValueError("PHYSICAL_CUTOFF_NOT_REACHED")
        if (
            "expected_trade_count" in self.identity
            and self.processed_trades != self.identity["expected_trade_count"]
        ):
            raise ValueError("FULL_INTERVAL_TRADE_COUNT_MISMATCH")
        self.advance_to(self.end_us)
        self.completed = True
        result = self.metrics()
        result["STATUS"] = "COMPLETED_AWAITING_INDEPENDENT_AUDIT"
        return result
