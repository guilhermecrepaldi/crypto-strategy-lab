"""One-shot M034 zero-loss development diagnostic on validated Binance events."""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from decimal import Decimal as D
from statistics import median
from typing import Any

from crypto_strategy_lab.microstructure.adaptive_multi_stable_manager import priority_class
from crypto_strategy_lab.microstructure.economic_eligibility import (
    BinancePairEvidence,
    BinancePairUniverse,
    CausalAssetMarkRegistry,
    DataState,
    DecisionIntent,
    EconomicCandidate,
    EconomicEligibilityGate,
    EconomicExecutionPolicy,
    EligibilityDecisionLedger,
    EvaluationMode,
    FeeLeg,
    M034EconomicAllocationEngine,
    M034Policy,
    MarketRegimeSnapshot,
    RuleEvidenceStatus,
    ThresholdDefinition,
    ThresholdRegistry,
    ThresholdSourceType,
    UnknownCostPolicy,
    VenuePairFeeRegistry,
    VenuePairRuleRegistry,
    VenueSymbolRuleRecord,
)
from crypto_strategy_lab.microstructure.multi_stable_ledger import SlotLedger
from crypto_strategy_lab.microstructure.multi_stable_models import (
    ZERO,
    CausalAssetMark,
    InventoryReductionAuthorization,
    PhysicalFill,
)
from crypto_strategy_lab.microstructure.multi_stable_queue import CausalQueueEstimator
from crypto_strategy_lab.microstructure.multi_venue_models import (
    BookKey,
    FeeEvidenceStatus,
    Venue,
    VenueFeeProfile,
    VenueRoute,
    VenueRouteLeg,
    VenueSymbolRule,
)

BPS = D("10000")
BOOK = BookKey(Venue.BINANCE, "USDCUSDT")


def _s(value: D) -> str:
    return format(value, "f")


def _percentile(values: list[D], rank: D) -> D | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int(((D(len(ordered)) - D(1)) * rank).to_integral_value(rounding=ROUND_CEILING))
    return ordered[index]


def zero_loss_economic_pass(
    *,
    cycle_pnls: Iterable[D],
    negative_risk_exits: int,
    final_marked_equity: D,
    initial_equity: D,
) -> bool:
    return (
        all(value >= ZERO for value in cycle_pnls)
        and negative_risk_exits == 0
        and final_marked_equity >= initial_equity
    )


def negative_risk_exit_allowed(
    *,
    peg_deviation: D,
    trigger_deviation: D,
    expected_hold_loss: D,
    opportunity_cost_of_lock: D,
    tail_risk_increase: D,
    realized_loss_of_exit: D,
) -> bool:
    values = (
        expected_hold_loss,
        opportunity_cost_of_lock,
        tail_risk_increase,
        realized_loss_of_exit,
    )
    if any(value < ZERO for value in values):
        raise ValueError("M034_ZERO_LOSS_NEGATIVE_RISK_TERM")
    return (
        abs(peg_deviation) > trigger_deviation
        and realized_loss_of_exit > ZERO
        and expected_hold_loss + opportunity_cost_of_lock + tail_risk_increase
        > realized_loss_of_exit
    )


@dataclass(frozen=True)
class ZeroLossConfig:
    identity: str
    start_us: int
    end_us: int
    initial_bank_usdt: D
    slot_base_usdt: D
    activation_latency_us: int
    cancel_ack_latency_us: int
    tick_size: D
    quantity_step: D
    minimum_quantity: D
    minimum_notional: D
    flow_window_seconds: int
    depth_band_bps: D
    thresholds: tuple[Mapping[str, Any], ...]
    completion_probability: D
    expected_lock_seconds: D
    execution_cost_bps: D
    adverse_selection_bps: D
    taker_contingency_fee_bps: D
    fee_scenarios_bps: tuple[D, ...]
    emergency_exit_peg_deviation: D

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> ZeroLossConfig:
        thresholds = tuple(row["thresholds"])
        config = cls(
            identity=str(row["identity"]),
            start_us=int(row["start_us"]),
            end_us=int(row["end_us"]),
            initial_bank_usdt=D(str(row["initial_bank_usdt"])),
            slot_base_usdt=D(str(row["slot_base_usdt"])),
            activation_latency_us=int(row["activation_latency_us"]),
            cancel_ack_latency_us=int(row["cancel_ack_latency_us"]),
            tick_size=D(str(row["tick_size"])),
            quantity_step=D(str(row["quantity_step"])),
            minimum_quantity=D(str(row["minimum_quantity"])),
            minimum_notional=D(str(row["minimum_notional"])),
            flow_window_seconds=int(row["flow_window_seconds"]),
            depth_band_bps=D(str(row["depth_band_bps"])),
            thresholds=thresholds,
            completion_probability=D(str(row["diagnostic_completion_probability"])),
            expected_lock_seconds=D(str(row["diagnostic_expected_lock_seconds"])),
            execution_cost_bps=D(str(row["diagnostic_execution_cost_bps"])),
            adverse_selection_bps=D(str(row["diagnostic_adverse_selection_bps"])),
            taker_contingency_fee_bps=D(str(row["taker_contingency_fee_bps"])),
            fee_scenarios_bps=tuple(D(str(value)) for value in row["fee_scenarios_bps"]),
            emergency_exit_peg_deviation=D(str(row["emergency_exit_peg_deviation"])),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if (
            self.identity != "M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_V1"
            or self.end_us - self.start_us != 10_800_000_000
            or self.initial_bank_usdt != D("200")
            or self.slot_base_usdt != D("10")
            or self.fee_scenarios_bps != (D(0), D(1), D(2), D(5), D(10))
            or self.execution_cost_bps != D(1)
            or self.adverse_selection_bps != D(1)
            or self.completion_probability != D("0.90")
            or self.expected_lock_seconds != D(300)
            or self.activation_latency_us <= 0
            or self.cancel_ack_latency_us <= 0
        ):
            raise ValueError("M034_ZERO_LOSS_CONFIG_NOT_FROZEN")

    def threshold_registry(self) -> ThresholdRegistry:
        return ThresholdRegistry(
            [
                ThresholdDefinition(
                    name=str(row["name"]),
                    value=D(str(row["value"])),
                    unit=str(row["unit"]),
                    source_type=ThresholdSourceType(str(row["source_type"])),
                    source_reference=str(row["source_reference"]),
                    derivation_method=str(row["derivation_method"]),
                    calibration_dataset_hash=row.get("calibration_dataset_hash"),
                    effective_from_us=int(row["effective_from_us"]),
                    frozen_at_us=int(row["frozen_at_us"]),
                )
                for row in self.thresholds
            ]
        )


@dataclass
class BacktestOrder:
    order_id: str
    slot_id: str
    reservation_id: str
    kind: str
    side: str
    price: D
    quantity: D
    rank: int
    column: int
    entry_price: D
    exit_price: D
    origin_quantity: D
    submitted_at_us: int
    activate_at_us: int
    status: str = "PENDING"
    activation_native_upper_us: int = -1
    filled_quantity: D = ZERO


class M034ZeroLossScenario:
    """One fee scenario sharing the same immutable event sequence with its peers."""

    def __init__(self, config: ZeroLossConfig, *, fee_bps: D) -> None:
        self.config = config
        self.fee_bps = fee_bps
        self.name = f"F{int(fee_bps)}"
        self.ledger = SlotLedger(
            {"USDT": config.initial_bank_usdt, "USDC": ZERO},
            marks_usd={"USDT": D(1), "USDC": D(1)},
        )
        self.queue = CausalQueueEstimator(flow_window_us=config.flow_window_seconds * 1_000_000)
        self.decisions = EligibilityDecisionLedger()
        self.orders: dict[str, BacktestOrder] = {}
        self.cycles: list[dict[str, Any]] = []
        self.negative_cycles: list[dict[str, Any]] = []
        self.rejections: Counter[str] = Counter()
        self.flow: dict[str, deque[tuple[int, D]]] = {
            "BUY": deque(),
            "SELL": deque(),
        }
        self.last_book: dict[str, Any] | None = None
        self.last_book_capture_us = -1
        self.last_event_us = config.start_us
        self.order_sequence = 0
        self.slot_sequence = 0
        self.cycle_sequence = 0
        self.hotline: D | None = None
        self.event_count = 0
        self.trade_count = 0
        self.book_count = 0
        self.trade_quantity_consumed = ZERO
        self.total_fees_usd = ZERO
        self.execution_cost_total = ZERO
        self.adverse_selection_cost_total = ZERO
        self.negative_risk_exits = 0
        self.risk_exit_assessments = 0
        self.locked_integral_usd_us = ZERO
        self.idle_integral_usd_us = ZERO
        self.max_capital_lock_usd = ZERO
        self.checkpoints: list[dict[str, Any]] = []
        self.checkpoint_times = tuple(
            config.start_us + offset * 1_800_000_000 for offset in range(7)
        )
        self._next_checkpoint = 0
        self._record_due_checkpoints(config.start_us)

    @property
    def fee_rate(self) -> D:
        return self.fee_bps / BPS

    @property
    def half_execution_rate(self) -> D:
        return self.config.execution_cost_bps / D(2) / BPS

    @property
    def half_adverse_rate(self) -> D:
        return self.config.adverse_selection_bps / D(2) / BPS

    def _active_orders(self, *, kind: str | None = None) -> list[BacktestOrder]:
        return [
            order
            for order in self.orders.values()
            if order.status in {"PENDING", "ACTIVE", "PARTIAL", "CANCEL_PENDING"}
            and (kind is None or order.kind == kind)
        ]

    def _mark(self) -> D:
        if self.last_book is None:
            return D(1)
        return self.last_book["bids"][0][0]

    def _bucket_values(self) -> tuple[D, D, D]:
        mark = self._mark()
        free = self.ledger.free.get("USDT", ZERO) + self.ledger.free.get("USDC", ZERO) * mark
        reserved = sum(
            (
                reservation.remaining * (D(1) if reservation.asset == "USDT" else mark)
                for reservation in self.ledger.reservations.values()
            ),
            ZERO,
        )
        owned = sum(
            (
                quantity * (D(1) if asset == "USDT" else mark)
                for bucket in self.ledger.owned.values()
                for asset, quantity in bucket.items()
            ),
            ZERO,
        )
        return free, reserved, owned

    def _locked_and_idle(self) -> tuple[D, D]:
        free, reserved, owned = self._bucket_values()
        return reserved + owned, free

    def _advance_clock(self, now_us: int) -> None:
        if now_us < self.last_event_us:
            raise ValueError("M034_ZERO_LOSS_NONCAUSAL_EVENT")
        self._record_due_checkpoints(now_us)
        locked, idle = self._locked_and_idle()
        elapsed = D(now_us - self.last_event_us)
        self.locked_integral_usd_us += locked * elapsed
        self.idle_integral_usd_us += idle * elapsed
        self.max_capital_lock_usd = max(self.max_capital_lock_usd, locked)
        self.last_event_us = now_us

    def _record_due_checkpoints(self, now_us: int) -> None:
        while (
            self._next_checkpoint < len(self.checkpoint_times)
            and self.checkpoint_times[self._next_checkpoint] <= now_us
        ):
            time_us = self.checkpoint_times[self._next_checkpoint]
            self.checkpoints.append(self._checkpoint(time_us))
            self._next_checkpoint += 1

    def _checkpoint(self, time_us: int) -> dict[str, Any]:
        free, reserved, owned = self._bucket_values()
        marked = free + reserved + owned
        realized_pnl = sum(self.ledger.realized_pnl_by_asset.values(), ZERO)
        residual = self._residual_inventory()
        return {
            "SCENARIO": self.name,
            "TIME_US": time_us,
            "REALIZED_EQUITY": _s(self.config.initial_bank_usdt + realized_pnl),
            "MARKED_EQUITY": _s(marked),
            "PHYSICAL_CYCLES": len(self.cycles),
            "FREE_CAPITAL": _s(free),
            "LOCKED_CAPITAL": _s(reserved + owned),
            "RESIDUAL_INVENTORY": residual,
        }

    def _residual_inventory(self) -> dict[str, str]:
        usdc = self.ledger.free.get("USDC", ZERO)
        usdc += sum(
            (r.remaining for r in self.ledger.reservations.values() if r.asset == "USDC"), ZERO
        )
        usdc += sum((bucket.get("USDC", ZERO) for bucket in self.ledger.owned.values()), ZERO)
        return {} if usdc == ZERO else {"USDC": _s(usdc)}

    def receive_book(self, event: Mapping[str, Any]) -> None:
        now_us = int(event["local_us"])
        self._advance_clock(now_us)
        self.event_count += 1
        self.book_count += 1
        bids = tuple((D(str(p)), D(str(q))) for p, q in event["bids"])
        asks = tuple((D(str(p)), D(str(q))) for p, q in event["asks"])
        if not bids or not asks or not event["sequence_validated"]:
            raise ValueError("M034_ZERO_LOSS_INVALID_BOOK")
        self.last_book = {
            "bids": bids,
            "asks": asks,
            "exchange_upper_us": int(event["exchange_upper_us"]),
        }
        self.last_book_capture_us = now_us
        midpoint = (bids[0][0] + asks[0][0]) / D(2)
        next_hotline = (midpoint / self.config.tick_size).to_integral_value(
            rounding=ROUND_HALF_UP
        ) * self.config.tick_size
        if self.hotline is not None and next_hotline != self.hotline:
            self._request_stale_c2_cancels(now_us, next_hotline)
        self.hotline = next_hotline
        self._advance_orders(now_us)
        self._assess_inventory_risk(now_us)
        self._submit_waiting_returns(now_us)
        self._try_allocate_entries(now_us)

    def receive_trade(self, event: Mapping[str, Any]) -> None:
        now_us = int(event["local_us"])
        self._advance_clock(now_us)
        self.event_count += 1
        self.trade_count += 1
        data = event["data"]
        native_us = int(event["exchange_us"])
        price = D(str(data["p"]))
        quantity = D(str(data["q"]))
        side = "BUY" if bool(data["m"]) else "SELL"
        self.flow[side].append((now_us, quantity))
        self._prune_flow(now_us)
        self._advance_orders(now_us)
        if self.last_book is not None and int(self.last_book["exchange_upper_us"]) > native_us:
            return
        eligible_ids = {
            order.order_id
            for order in self._active_orders()
            if order.status in {"ACTIVE", "PARTIAL", "CANCEL_PENDING"}
            and native_us > order.activation_native_upper_us
        }
        fills = self.queue.consume_trade_through(
            event_id=f"{self.name}:{data['t']}",
            book=BOOK.canonical_id,
            side=side,
            trade_price=price,
            quantity=quantity,
            now_us=now_us,
        )
        consumed = ZERO
        for order_id, amount in fills.items():
            if order_id not in eligible_ids:
                raise ValueError("M034_ZERO_LOSS_FILL_BEFORE_NATIVE_ACTIVATION")
            self._apply_fill(self.orders[order_id], amount, now_us, str(data["t"]))
            consumed += amount
        if consumed > quantity:
            raise ValueError("M034_ZERO_LOSS_TRADE_BUDGET_EXCEEDED")
        self.trade_quantity_consumed += consumed

    def _prune_flow(self, now_us: int) -> None:
        cutoff = now_us - self.config.flow_window_seconds * 1_000_000
        for rows in self.flow.values():
            while rows and rows[0][0] < cutoff:
                rows.popleft()

    def _flow_rate(self) -> D:
        rates = []
        window = D(self.config.flow_window_seconds)
        for side in ("BUY", "SELL"):
            rates.append(sum((q for _, q in self.flow[side]), ZERO) / window)
        return min(rates)

    def _market_snapshot(self, now_us: int) -> MarketRegimeSnapshot:
        assert self.last_book is not None
        bid, ask = self.last_book["bids"][0][0], self.last_book["asks"][0][0]
        midpoint = (bid + ask) / D(2)
        spread_bps = (ask - bid) / midpoint * BPS
        band = midpoint * self.config.depth_band_bps / BPS
        depth = sum(
            (price * qty for price, qty in self.last_book["bids"] if price >= midpoint - band),
            ZERO,
        ) + sum(
            (price * qty for price, qty in self.last_book["asks"] if price <= midpoint + band),
            ZERO,
        )
        return MarketRegimeSnapshot(
            observed_at_us=now_us,
            regime="HISTORICAL_PHYSICAL_DEVELOPMENT",
            peg_deviation=midpoint - D(1),
            spread_bps=spread_bps,
            depth_usd=depth,
            compatible_flow_per_second=self._flow_rate(),
            data_gap=False,
        )

    def _gate(self, now_us: int) -> M034EconomicAllocationEngine:
        thresholds = self.config.threshold_registry()
        policy = M034Policy(
            policy_id=f"{self.config.identity}:{self.name}",
            provenance="OWNER_DIAGNOSTIC_ASSUMPTION;DEVELOPMENT_ONLY",
            thresholds=thresholds,
            unknown_cost_policy=UnknownCostPolicy.REJECT,
        )
        fee_registry = VenuePairFeeRegistry()
        fee_registry.add(
            VenueFeeProfile(
                book=BOOK,
                maker_rate=self.fee_rate,
                taker_rate=self.config.taker_contingency_fee_bps / BPS,
                fee_asset_semantics="RECEIVED_ASSET",
                effective_start_us=self.config.start_us,
                effective_end_us=self.config.end_us,
                provenance="OWNER_DIAGNOSTIC_ASSUMPTION;NOT_HISTORICAL_PROOF",
                account_tier_assumption=f"{self.name}_DIAGNOSTIC",
                acquired_at_us=self.config.start_us,
                evidence_status=FeeEvidenceStatus.OWNER_DIAGNOSTIC_ASSUMPTION,
                record_id=f"{self.config.identity}:{self.name}:FEE",
                source_reference="OWNER_FROZEN_FEE_GRID",
            )
        )
        rule = VenueSymbolRule(
            book=BOOK,
            base_asset="USDC",
            quote_asset="USDT",
            tick_size=self.config.tick_size,
            quantity_step=self.config.quantity_step,
            minimum_quantity=self.config.minimum_quantity,
            minimum_notional=self.config.minimum_notional,
            price_precision=8,
            effective_start_us=self.config.start_us,
            effective_end_us=self.config.end_us,
            provenance="OWNER_DIAGNOSTIC_RULE_ASSUMPTION;M026_COMPARABILITY",
        )
        rule_registry = VenuePairRuleRegistry()
        rule_registry.add(
            VenueSymbolRuleRecord(
                rule=rule,
                evidence_status=RuleEvidenceStatus.OWNER_DIAGNOSTIC_ASSUMPTION,
                acquired_at_us=self.config.start_us,
                record_id=f"{self.config.identity}:RULE",
                source_reference="M026_MODEL_SPEC_AND_OBSERVED_2025_PRICE_QUANTUM",
            )
        )
        universe = BinancePairUniverse(
            [
                BinancePairEvidence(
                    book=BOOK,
                    available=True,
                    data_proven=True,
                    rules_proven=True,
                    safety_acceptable=True,
                    liquidity_acceptable=True,
                    temporal_provenance="DEVELOPMENT_DIAGNOSTIC_ASSUMPTION",
                    effective_start_us=self.config.start_us,
                    effective_end_us=self.config.end_us,
                )
            ]
        )
        marks = CausalAssetMarkRegistry()
        marks.add(
            CausalAssetMark(
                base_asset="USDT",
                quote_asset="USD",
                rate=D(1),
                observed_at_us=self.config.start_us,
                effective_until_us=self.config.end_us,
                record_id=f"{self.config.identity}:USDT_USD",
                source_reference="OWNER_200_USD_AS_200_USDT_DIAGNOSTIC",
                provenance="OWNER_DIAGNOSTIC_ASSUMPTION",
            )
        )
        gate = EconomicEligibilityGate(
            execution_policy=EconomicExecutionPolicy(
                economic_venues=frozenset({Venue.BINANCE}),
                policy_id="M034_BINANCE_ONLY",
                policy_hash="M034_BINANCE_ONLY_DEVELOPMENT_V1",
                provenance="OWNER_DIRECTIVE_KRAKEN_RETIRED",
            ),
            policy=policy,
            fee_registry=fee_registry,
            rule_registry=rule_registry,
            pair_universe=universe,
            mark_registry=marks,
        )
        return M034EconomicAllocationEngine(gate=gate, decision_ledger=self.decisions)

    def _candidate(self, *, rank: int, column: int, now_us: int) -> EconomicCandidate | None:
        assert self.hotline is not None
        entry_price = self.hotline - D(rank) * self.config.tick_size
        exit_price = self.hotline + D(rank) * self.config.tick_size
        per_leg_other = (self.half_execution_rate + self.half_adverse_rate) * entry_price
        quantity = (self.config.slot_base_usdt / (entry_price + per_leg_other)).to_integral_value(
            rounding=ROUND_FLOOR
        )
        quantity = (quantity / self.config.quantity_step).to_integral_value(
            rounding=ROUND_FLOOR
        ) * self.config.quantity_step
        if (
            quantity < self.config.minimum_quantity
            or entry_price * quantity < self.config.minimum_notional
        ):
            self.rejections["EXCHANGE_RULE_VIOLATION"] += 1
            return None
        net_base = quantity * (D(1) - self.fee_rate)
        return_quantity = (net_base / self.config.quantity_step).to_integral_value(
            rounding=ROUND_FLOOR
        ) * self.config.quantity_step
        if return_quantity != net_base:
            self.rejections["FEE_DUST_PREVENTS_FULL_RETURN"] += 1
            return None
        entry_cost = entry_price * quantity
        entry_cost += entry_cost * (self.half_execution_rate + self.half_adverse_rate)
        route = VenueRoute(
            route_id=f"USDT-USDC-USDT:{entry_price}:{exit_price}",
            origin_asset="USDT",
            legs=(
                VenueRouteLeg(BOOK, "USDT", "USDC", True),
                VenueRouteLeg(BOOK, "USDC", "USDT", True),
            ),
        )
        return EconomicCandidate(
            candidate_id=f"{self.name}:{now_us}:R{rank}:C{column}",
            venue=Venue.BINANCE,
            pair=BOOK,
            side="BUY",
            rank=rank,
            column=column,
            route_id=route.route_id,
            route=route,
            inventory_state="FLAT",
            intent=DecisionIntent.NEW_ENTRY,
            priority_class=priority_class(
                obligation=False, rank=rank, column=column, old_zero_fill=False
            ),
            decision_currency="USDT",
            decision_time_us=now_us,
            gross_edge_bps=(exit_price / entry_price - D(1)) * BPS,
            execution_cost_bps=self.config.execution_cost_bps,
            adverse_selection_bps=self.config.adverse_selection_bps,
            completion_probability=self.config.completion_probability,
            expected_lock_seconds=self.config.expected_lock_seconds,
            p95_lock_seconds=self.config.expected_lock_seconds,
            capital_required=entry_cost,
            residual_cost_if_incomplete=ZERO,
            tail_risk_cost=ZERO,
            inventory_carry_cost=ZERO,
            fee_legs=(
                FeeLeg(BOOK, True, "USDT", "USDC", "BUY", entry_price, quantity),
                FeeLeg(BOOK, True, "USDC", "USDT", "SELL", exit_price, return_quantity),
            ),
            market=self._market_snapshot(now_us),
            data_state=DataState.VALID,
            account_context=f"{self.name}_DIAGNOSTIC",
        )

    def _potential_exposure(self) -> D:
        mark = self._mark()
        reserved_entry = sum(
            (
                self.ledger.reservations[order.reservation_id].remaining
                for order in self._active_orders(kind="ENTRY")
                if order.reservation_id in self.ledger.reservations
            ),
            ZERO,
        )
        inventory = sum(
            (bucket.get("USDC", ZERO) * mark for bucket in self.ledger.owned.values()), ZERO
        )
        return reserved_entry + inventory

    def _try_allocate_entries(self, now_us: int) -> None:
        if self.last_book is None or self.hotline is None:
            return
        exposure_left = (
            self.config.threshold_registry().value("MAX_INVENTORY_EXPOSURE", unit="USD")
            - self._potential_exposure()
        )
        available = min(self.ledger.free.get("USDT", ZERO), max(exposure_left, ZERO))
        if available < self.config.minimum_notional:
            return
        occupied = {
            (order.side, order.price, order.column) for order in self._active_orders(kind="ENTRY")
        }
        candidates = [
            candidate
            for rank in range(1, 8)
            for column in (1, 2)
            if (candidate := self._candidate(rank=rank, column=column, now_us=now_us)) is not None
            and (candidate.side, candidate.fee_legs[0].price, candidate.column) not in occupied
        ]
        allocation = self._gate(now_us).evaluate_and_allocate(
            candidates,
            mode=EvaluationMode.DEVELOPMENT_DIAGNOSTIC,
            available_capital=available,
            available_capital_currency="USDT",
            now_us=now_us,
        )
        candidate_by_id = {row.candidate_id: row for row in candidates}
        for decision in allocation.decisions:
            if not decision.eligible:
                self.rejections.update(code.value for code in decision.decision_reason_codes)
        for candidate_id in allocation.selected_candidate_ids:
            self._submit_entry(candidate_by_id[candidate_id], now_us)

    def _submit_entry(self, candidate: EconomicCandidate, now_us: int) -> None:
        self.slot_sequence += 1
        self.order_sequence += 1
        slot_id = f"{self.name}:S{self.slot_sequence:06d}"
        order_id = f"{self.name}:O{self.order_sequence:06d}"
        reservation_id = f"{order_id}:RESERVE"
        self.ledger.create_slot(
            slot_id,
            origin_asset="USDT",
            usd_equivalent=candidate.capital_required,
            now_us=now_us,
        )
        self.ledger.reserve_free(
            slot_id,
            reservation_id,
            asset="USDT",
            quantity=candidate.capital_required,
            now_us=now_us,
        )
        order = BacktestOrder(
            order_id=order_id,
            slot_id=slot_id,
            reservation_id=reservation_id,
            kind="ENTRY",
            side="BUY",
            price=candidate.fee_legs[0].price,
            quantity=candidate.fee_legs[0].quantity,
            rank=candidate.rank,
            column=candidate.column,
            entry_price=candidate.fee_legs[0].price,
            exit_price=candidate.fee_legs[1].price,
            origin_quantity=candidate.capital_required,
            submitted_at_us=now_us,
            activate_at_us=now_us + self.config.activation_latency_us,
        )
        self.orders[order_id] = order

    def _advance_orders(self, now_us: int) -> None:
        for order in sorted(self._active_orders(), key=lambda row: row.order_id):
            if order.status == "CANCEL_PENDING":
                reservation = self.ledger.reservations.get(order.reservation_id)
                if (
                    reservation is not None
                    and reservation.cancel_requested_at_us is not None
                    and now_us
                    >= reservation.cancel_requested_at_us + self.config.cancel_ack_latency_us
                ):
                    if order.order_id in self.queue.order_group:
                        self.queue.cancel_ack(order.order_id, now_us=now_us)
                    self.ledger.acknowledge_cancel(order.reservation_id, now_us=now_us)
                    order.status = "CANCELLED"
                continue
            if order.status != "PENDING" or now_us < order.activate_at_us:
                continue
            assert self.last_book is not None
            bid, ask = self.last_book["bids"][0][0], self.last_book["asks"][0][0]
            if (order.side == "BUY" and order.price >= ask) or (
                order.side == "SELL" and order.price <= bid
            ):
                continue
            levels = self.last_book["bids"] if order.side == "BUY" else self.last_book["asks"]
            public = next((qty for price, qty in levels if price == order.price), ZERO)
            self.queue.activate(
                book=BOOK.canonical_id,
                side=order.side,
                price=order.price,
                order_id=order.order_id,
                column=order.column,
                quantity=order.quantity,
                observed_public_queue=public,
                now_us=now_us,
            )
            self.ledger.activate(order.reservation_id, now_us=now_us)
            order.status = "ACTIVE"
            order.activation_native_upper_us = int(self.last_book["exchange_upper_us"])

    def _request_stale_c2_cancels(self, now_us: int, new_hotline: D) -> None:
        for order in self._active_orders(kind="ENTRY"):
            expected = new_hotline - D(order.rank) * self.config.tick_size
            if (
                order.column == 2
                and order.filled_quantity == ZERO
                and order.status in {"PENDING", "ACTIVE"}
                and order.price != expected
            ):
                if order.status == "PENDING":
                    self.ledger.request_cancel(order.reservation_id, now_us=now_us)
                    order.status = "CANCEL_PENDING"
                else:
                    self.ledger.request_cancel(order.reservation_id, now_us=now_us)
                    order.status = "CANCEL_PENDING"

    def _apply_fill(self, order: BacktestOrder, amount: D, now_us: int, trade_id: str) -> None:
        if amount <= ZERO or order.status not in {"ACTIVE", "PARTIAL", "CANCEL_PENDING"}:
            raise ValueError("M034_ZERO_LOSS_INVALID_FILL")
        if order.kind == "ENTRY":
            input_quantity = amount * order.price
            gross_output = amount
            fee = gross_output * self.fee_rate
            fill = PhysicalFill(
                fill_id=f"{self.name}:{trade_id}:{order.order_id}:{order.filled_quantity}",
                symbol="USDCUSDT",
                from_asset="USDT",
                to_asset="USDC",
                input_quantity=input_quantity,
                output_quantity_gross=gross_output,
                fee_asset="USDC",
                fee_quantity=fee,
                time_us=now_us,
            )
            self.ledger.apply_fill(order.reservation_id, fill)
            execution = input_quantity * self.half_execution_rate
            adverse = input_quantity * self.half_adverse_rate
            self.ledger.debit_reserved_cost(
                order.reservation_id,
                quantity=execution,
                cost_kind="EXECUTION_COST_ENTRY",
                now_us=now_us,
            )
            self.ledger.debit_reserved_cost(
                order.reservation_id,
                quantity=adverse,
                cost_kind="ADVERSE_SELECTION_ENTRY",
                now_us=now_us,
            )
            self.total_fees_usd += fee * order.price
            self.execution_cost_total += execution
            self.adverse_selection_cost_total += adverse
        else:
            gross_output = amount * order.price
            fee = gross_output * self.fee_rate
            fill = PhysicalFill(
                fill_id=f"{self.name}:{trade_id}:{order.order_id}:{order.filled_quantity}",
                symbol="USDCUSDT",
                from_asset="USDC",
                to_asset="USDT",
                input_quantity=amount,
                output_quantity_gross=gross_output,
                fee_asset="USDT",
                fee_quantity=fee,
                time_us=now_us,
            )
            self.ledger.apply_fill(order.reservation_id, fill)
            execution = amount * order.entry_price * self.half_execution_rate
            adverse = amount * order.entry_price * self.half_adverse_rate
            self.ledger.debit_owned_cost(
                order.slot_id,
                asset="USDT",
                quantity=execution,
                cost_kind="EXECUTION_COST_RETURN",
                now_us=now_us,
            )
            self.ledger.debit_owned_cost(
                order.slot_id,
                asset="USDT",
                quantity=adverse,
                cost_kind="ADVERSE_SELECTION_RETURN",
                now_us=now_us,
            )
            self.total_fees_usd += fee
            self.execution_cost_total += execution
            self.adverse_selection_cost_total += adverse
        order.filled_quantity += amount
        if order.filled_quantity < order.quantity:
            order.status = "PARTIAL"
            return
        order.status = "FILLED"
        if order.kind == "ENTRY":
            self._submit_waiting_returns(now_us)
        else:
            self._close_cycle(order, now_us)

    def _submit_waiting_returns(self, now_us: int) -> None:
        active_return_slots = {order.slot_id for order in self._active_orders(kind="RETURN")}
        for entry in sorted(self.orders.values(), key=lambda row: row.order_id):
            if entry.kind != "ENTRY" or entry.status != "FILLED":
                continue
            if entry.slot_id in active_return_slots or any(
                row.kind == "RETURN" and row.slot_id == entry.slot_id
                for row in self.orders.values()
            ):
                continue
            owned = self.ledger.owned[entry.slot_id].get("USDC", ZERO)
            quantity = (owned / self.config.quantity_step).to_integral_value(
                rounding=ROUND_FLOOR
            ) * self.config.quantity_step
            if quantity != owned or quantity < self.config.minimum_quantity:
                self.rejections["RESIDUAL_INVENTORY_BELOW_RETURN_STEP"] += 1
                continue
            assert self.last_book is not None
            if entry.exit_price <= self.last_book["bids"][0][0]:
                continue
            self.order_sequence += 1
            order_id = f"{self.name}:O{self.order_sequence:06d}"
            reservation_id = f"{order_id}:RESERVE"
            self.ledger.reserve_owned(
                entry.slot_id,
                reservation_id,
                asset="USDC",
                quantity=quantity,
                now_us=now_us,
            )
            self.orders[order_id] = BacktestOrder(
                order_id=order_id,
                slot_id=entry.slot_id,
                reservation_id=reservation_id,
                kind="RETURN",
                side="SELL",
                price=entry.exit_price,
                quantity=quantity,
                rank=entry.rank,
                column=entry.column,
                entry_price=entry.entry_price,
                exit_price=entry.exit_price,
                origin_quantity=entry.origin_quantity,
                submitted_at_us=now_us,
                activate_at_us=now_us + self.config.activation_latency_us,
            )

    def _assess_inventory_risk(self, now_us: int) -> None:
        if self.last_book is None:
            return
        bid = self.last_book["bids"][0][0]
        ask = self.last_book["asks"][0][0]
        midpoint = (bid + ask) / D(2)
        for slot_id, bucket in sorted(self.ledger.owned.items()):
            return_order = next(
                (row for row in self._active_orders(kind="RETURN") if row.slot_id == slot_id),
                None,
            )
            reserved_quantity = ZERO
            if return_order is not None and return_order.reservation_id in self.ledger.reservations:
                reserved_quantity = self.ledger.reservations[return_order.reservation_id].remaining
            quantity = bucket.get("USDC", ZERO) + reserved_quantity
            slot = self.ledger.slots[slot_id]
            if quantity <= ZERO:
                continue
            entry = next(
                (
                    row
                    for row in self.orders.values()
                    if row.slot_id == slot_id and row.kind == "ENTRY"
                ),
                None,
            )
            if entry is None:
                continue
            self.risk_exit_assessments += 1
            gross_proceeds = ZERO
            remaining = quantity
            for price, depth in self.last_book["bids"]:
                amount = min(remaining, depth)
                gross_proceeds += amount * price
                remaining -= amount
                if remaining == ZERO:
                    break
            if remaining > ZERO:
                self.rejections["RISK_EXIT_DEPTH_INSUFFICIENT"] += 1
                continue
            taker_fee = gross_proceeds * self.config.taker_contingency_fee_bps / BPS
            net_proceeds = gross_proceeds - taker_fee
            loss = max(entry.origin_quantity - net_proceeds, ZERO)
            expected_hold_loss = max(entry.origin_quantity - quantity * bid, ZERO)
            opportunity_cost = ZERO
            tail_increase = quantity * max(
                abs(midpoint - D(1)) - self.config.emergency_exit_peg_deviation,
                ZERO,
            )
            if not negative_risk_exit_allowed(
                peg_deviation=midpoint - D(1),
                trigger_deviation=self.config.emergency_exit_peg_deviation,
                expected_hold_loss=expected_hold_loss,
                opportunity_cost_of_lock=opportunity_cost,
                tail_risk_increase=tail_increase,
                realized_loss_of_exit=loss,
            ):
                self.rejections["NEGATIVE_EXIT_NOT_ALLOWED_COSMETIC"] += 1
                continue
            if return_order is not None:
                if return_order.status != "CANCEL_PENDING":
                    self.ledger.request_cancel(return_order.reservation_id, now_us=now_us)
                    return_order.status = "CANCEL_PENDING"
                    self.rejections["RISK_EXIT_WAITING_FOR_CANCEL_ACK"] += 1
                continue
            if slot.reservation_id is not None:
                raise ValueError("M034_ZERO_LOSS_RISK_EXIT_RESERVATION_NOT_OWNED_RETURN")
            self._execute_negative_risk_exit(
                entry=entry,
                quantity=quantity,
                gross_proceeds=gross_proceeds,
                taker_fee=taker_fee,
                expected_hold_loss=expected_hold_loss,
                opportunity_cost=opportunity_cost,
                tail_increase=tail_increase,
                loss=loss,
                now_us=now_us,
            )

    def _execute_negative_risk_exit(
        self,
        *,
        entry: BacktestOrder,
        quantity: D,
        gross_proceeds: D,
        taker_fee: D,
        expected_hold_loss: D,
        opportunity_cost: D,
        tail_increase: D,
        loss: D,
        now_us: int,
    ) -> None:
        authorization_id = f"{entry.slot_id}:RISK:{now_us}"
        reservation_id = f"{authorization_id}:RESERVE"
        authorization = InventoryReductionAuthorization(
            authorization_id=authorization_id,
            slot_id=entry.slot_id,
            slot_epoch=self.ledger.slots[entry.slot_id].slot_epoch,
            quantity=quantity,
            origin_cost_basis=entry.origin_quantity,
            inventory_asset="USDC",
            origin_asset="USDT",
            exit_reservation_id=reservation_id,
            external_fee_marks=(),
            decided_at_us=now_us,
            expires_at_us=now_us,
            rule_id="M034_OWNER_DIAGNOSTIC_PEG_TAIL_EXIT_V1",
            rule_hash="OWNER_FROZEN_STRICT_HOLD_GT_EXIT_V1",
            reason_code="NEGATIVE_EXIT_RISK_RULE_TRIGGERED",
            trigger_reason_code="PEG_RISK_ESCALATED",
            expected_hold_loss=expected_hold_loss,
            opportunity_cost_of_lock=opportunity_cost,
            tail_risk_increase=tail_increase,
            realized_loss_of_exit=loss,
        )
        self.ledger.register_inventory_reduction_authorization(authorization, now_us=now_us)
        self.ledger.reserve_owned(
            entry.slot_id,
            reservation_id,
            asset="USDC",
            quantity=quantity,
            now_us=now_us,
        )
        self.ledger.activate(reservation_id, now_us=now_us)
        self.ledger.apply_fill(
            reservation_id,
            PhysicalFill(
                fill_id=f"{authorization_id}:FILL",
                symbol="USDCUSDT",
                from_asset="USDC",
                to_asset="USDT",
                input_quantity=quantity,
                output_quantity_gross=gross_proceeds,
                fee_asset="USDT",
                fee_quantity=taker_fee,
                time_us=now_us,
            ),
        )
        self.ledger.settle_inventory_reduction(
            entry.slot_id,
            now_us=now_us,
            reduction_id=authorization_id,
            authorization=authorization,
        )
        entry.status = "RISK_EXITED"
        self.total_fees_usd += taker_fee
        self.negative_risk_exits += 1

    def _close_cycle(self, order: BacktestOrder, now_us: int) -> None:
        residual_non_origin = {
            asset: quantity
            for asset, quantity in self.ledger.owned[order.slot_id].items()
            if asset != "USDT" and quantity != ZERO
        }
        if residual_non_origin:
            self.rejections["RESIDUAL_INVENTORY_PREVENTS_CYCLE_CLOSE"] += 1
            return
        self.cycle_sequence += 1
        cycle_id = f"{self.name}:CYCLE:{self.cycle_sequence:06d}"
        pnl = self.ledger.close_slot(
            order.slot_id,
            origin_quantity=order.origin_quantity,
            now_us=now_us,
            cycle_id=cycle_id,
        )
        if pnl < ZERO:
            raise ValueError("M034_ZERO_LOSS_NEGATIVE_CYCLE_CLOSED")
        entry = next(
            row
            for row in self.orders.values()
            if row.slot_id == order.slot_id and row.kind == "ENTRY"
        )
        entry.status = "CLOSED"
        duration = D(now_us - entry.submitted_at_us) / D(1_000_000)
        gross_pnl = order.quantity * order.exit_price - order.quantity * order.entry_price
        total_cost = entry.origin_quantity - entry.quantity * entry.entry_price
        total_cost += (
            order.quantity * order.entry_price * (self.half_execution_rate + self.half_adverse_rate)
        )
        row = {
            "scenario": self.name,
            "cycle_id": cycle_id,
            "slot_id": order.slot_id,
            "capital_origin": "USDT",
            "route": "USDT->USDC->USDT@BINANCE:USDCUSDT",
            "start_timestamp_us": entry.submitted_at_us,
            "end_timestamp_us": now_us,
            "duration_seconds": _s(duration),
            "capital_used": _s(entry.origin_quantity),
            "cost_basis": _s(entry.origin_quantity),
            "entry_price": _s(entry.entry_price),
            "exit_price": _s(order.exit_price),
            "gross_pnl": _s(gross_pnl),
            "fees": "0",
            "execution_cost": _s(total_cost / D(2)),
            "adverse_selection_cost": _s(total_cost / D(2)),
            "net_pnl": _s(pnl),
            "return_pct": _s(pnl / entry.origin_quantity * D(100)),
            "rank": entry.rank,
            "column": entry.column,
        }
        self.cycles.append(row)
        if pnl < ZERO:
            self.negative_cycles.append(row)
        self._try_allocate_entries(now_us)

    def finish(self) -> dict[str, Any]:
        self._advance_clock(self.config.end_us)
        self._record_due_checkpoints(self.config.end_us)
        free, reserved, owned = self._bucket_values()
        marked_equity = free + reserved + owned
        realized_pnl = sum(self.ledger.realized_pnl_by_asset.values(), ZERO)
        realized_equity = self.config.initial_bank_usdt + realized_pnl
        unrealized_pnl = marked_equity - realized_equity
        cycle_pnls = [D(row["net_pnl"]) for row in self.cycles]
        locks = [D(row["duration_seconds"]) for row in self.cycles]
        for order in self.orders.values():
            if order.kind == "ENTRY" and order.status not in {"CLOSED", "CANCELLED"}:
                locks.append(D(self.config.end_us - order.submitted_at_us) / D(1_000_000))
        duration_us = D(self.config.end_us - self.config.start_us)
        capital_time = self.config.initial_bank_usdt * duration_us
        positive = sum(value > ZERO for value in cycle_pnls)
        zero = sum(value == ZERO for value in cycle_pnls)
        negative = sum(value < ZERO for value in cycle_pnls)
        zero_loss = zero_loss_economic_pass(
            cycle_pnls=cycle_pnls,
            negative_risk_exits=self.negative_risk_exits,
            final_marked_equity=marked_equity,
            initial_equity=self.config.initial_bank_usdt,
        )
        self.ledger.reconcile()
        accounting_residual = marked_equity - (
            self.config.initial_bank_usdt + realized_pnl + unrealized_pnl
        )
        if accounting_residual != ZERO:
            raise ValueError("M034_ZERO_LOSS_ACCOUNTING_IDENTITY_FAILED")
        return {
            "SCENARIO": self.name,
            "FEE_BPS_PER_LEG": _s(self.fee_bps),
            "INITIAL_BANK_USD": _s(self.config.initial_bank_usdt),
            "FINAL_REALIZED_EQUITY_USD": _s(realized_equity),
            "FINAL_MARKED_EQUITY_USD": _s(marked_equity),
            "NET_REALIZED_PNL_USD": _s(realized_pnl),
            "UNREALIZED_PNL_USD": _s(unrealized_pnl),
            "REALIZED_RETURN_PCT": _s(realized_pnl / self.config.initial_bank_usdt * D(100)),
            "MARKED_RETURN_PCT": _s(
                (marked_equity / self.config.initial_bank_usdt - D(1)) * D(100)
            ),
            "PHYSICAL_CYCLES": len(self.cycles),
            "SLOT_EQUIVALENT_CYCLES": len(self.cycles),
            "CYCLES_PER_HOUR": _s(D(len(self.cycles)) / D(3)),
            "POSITIVE_CLOSED_CYCLES": positive,
            "ZERO_PNL_CYCLES": zero,
            "NEGATIVE_CLOSED_CYCLES": negative,
            "NEGATIVE_RISK_EXITS": self.negative_risk_exits,
            "RISK_EXIT_ASSESSMENTS": self.risk_exit_assessments,
            "MIN_CYCLE_NET_PNL": None if not cycle_pnls else _s(min(cycle_pnls)),
            "MEDIAN_CYCLE_NET_PNL": None if not cycle_pnls else _s(D(str(median(cycle_pnls)))),
            "MAX_CYCLE_NET_PNL": None if not cycle_pnls else _s(max(cycle_pnls)),
            "TOTAL_FEES": _s(self.total_fees_usd),
            "EXECUTION_COST_TOTAL": _s(self.execution_cost_total),
            "ADVERSE_SELECTION_COST_TOTAL": _s(self.adverse_selection_cost_total),
            "CAPITAL_UTILIZATION_PCT": _s(self.locked_integral_usd_us / capital_time * D(100)),
            "IDLE_CAPITAL_PCT": _s(self.idle_integral_usd_us / capital_time * D(100)),
            "LOCKED_INVENTORY_PCT": _s(self.locked_integral_usd_us / capital_time * D(100)),
            "MAX_LOCK_SECONDS": None if not locks else _s(max(locks)),
            "P50_LOCK_SECONDS": None if not locks else _s(D(str(median(locks)))),
            "P90_LOCK_SECONDS": None if not locks else _s(_percentile(locks, D("0.90")) or ZERO),
            "P95_LOCK_SECONDS": None if not locks else _s(_percentile(locks, D("0.95")) or ZERO),
            "MAX_CAPITAL_LOCK_USD": _s(self.max_capital_lock_usd),
            "RESIDUAL_INVENTORY": self._residual_inventory(),
            "ZERO_LOSS_ECONOMIC_PASS": zero_loss,
            "REJECTION_REASONS": dict(sorted(self.rejections.items())),
            "EVENT_COUNT": self.event_count,
            "BOOK_COUNT": self.book_count,
            "TRADE_COUNT": self.trade_count,
            "TRADE_QUANTITY_CONSUMED": _s(self.trade_quantity_consumed),
            "ACCOUNTING_IDENTITY_RESIDUAL": _s(accounting_residual),
            "CHECKPOINTS": self.checkpoints,
        }


def run_scenarios(
    config: ZeroLossConfig, events: Iterable[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    scenarios = [M034ZeroLossScenario(config, fee_bps=fee) for fee in config.fee_scenarios_bps]
    for event in events:
        if not (
            config.start_us <= int(event["local_us"]) < config.end_us
            and config.start_us <= int(event["exchange_us"]) < config.end_us
        ):
            raise ValueError("M034_ZERO_LOSS_EVENT_ESCAPED_WINDOW")
        for scenario in scenarios:
            if event["kind"] == "BOOK":
                scenario.receive_book(event)
            elif event["kind"] == "TRADE":
                scenario.receive_trade(event)
            else:
                raise ValueError("M034_ZERO_LOSS_UNKNOWN_EVENT")
    results = [scenario.finish() for scenario in scenarios]
    cycles = [row for scenario in scenarios for row in scenario.cycles]
    checkpoints = [row for scenario in scenarios for row in scenario.checkpoints]
    counts = {(row["EVENT_COUNT"], row["BOOK_COUNT"], row["TRADE_COUNT"]) for row in results}
    if len(counts) != 1:
        raise ValueError("M034_ZERO_LOSS_SCENARIOS_DID_NOT_SHARE_TAPE")
    return results, cycles, checkpoints


__all__ = [
    "M034ZeroLossScenario",
    "ZeroLossConfig",
    "negative_risk_exit_allowed",
    "run_scenarios",
    "zero_loss_economic_pass",
]
