"""Physical two-pair M035 development backtest with one global capital ledger."""

from __future__ import annotations

import hashlib
from collections import Counter, deque
from collections.abc import Iterable, Mapping
from copy import copy, deepcopy
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from decimal import Decimal as D
from statistics import median
from typing import Any

from crypto_strategy_lab.microstructure.multi_stable_queue import CausalQueueEstimator
from crypto_strategy_lab.microstructure.parallel_pair_capital_manager import (
    AllocationCandidate,
    AllocationPriority,
    GlobalCapitalLedger,
    ParallelPairCapitalAllocator,
)

ZERO = D(0)
BPS = D(10_000)


def _s(value: D) -> str:
    return format(value, "f")


def _percentile(values: list[D], rank: D) -> D | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int(((D(len(ordered)) - 1) * rank).to_integral_value(rounding=ROUND_CEILING))
    return ordered[index]


def _id_set_evidence(values: set[str]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "first": None if not ordered else ordered[0],
        "last": None if not ordered else ordered[-1],
        "sha256": hashlib.sha256("\n".join(ordered).encode()).hexdigest(),
    }


@dataclass(frozen=True)
class M035BacktestConfig:
    identity: str
    start_us: int
    end_us: int
    initial_bank_usdt: D = D("200")
    order_quantity: D = D("10")
    tick_size: D = D("0.0001")
    quantity_step: D = D("1")
    minimum_quantity: D = D("1")
    minimum_notional: D = D("5")
    activation_latency_us: int = 1_179_525
    cancel_ack_latency_us: int = 1_179_525
    execution_cost_bps: D = D("1")
    adverse_selection_bps: D = D("1")
    risk_buffer_bps: D = D("2")
    minimum_net_edge_bps: D = D("1")
    maximum_spread_bps: D = D("5")
    minimum_depth_usd: D = D("1000")
    minimum_flow_per_second: D = D("10")
    flow_window_seconds: int = 60
    maximum_book_age_us: int = 2_000_000
    emergency_peg_deviation: D = D("0.0025")
    taker_fee_bps: D = D("10")

    def validate(self) -> None:
        if (
            self.identity != "M035_200USD_3H_PARALLEL_DEVELOPMENT_BACKTEST_V1"
            or self.end_us - self.start_us != 10_800_000_000
            or self.initial_bank_usdt != D(200)
            or self.order_quantity != D(10)
            or self.tick_size <= ZERO
            or self.quantity_step <= ZERO
            or self.minimum_notional <= ZERO
            or self.activation_latency_us <= 0
            or self.cancel_ack_latency_us <= 0
        ):
            raise ValueError("M035_ECONOMIC_CONFIG_NOT_FROZEN")


class M035BacktestExecutionError(RuntimeError):
    """Failure carrying the complete auditable prefix for every fee scenario."""

    def __init__(
        self,
        cause: BaseException,
        *,
        mode: str,
        event_index: int,
        event: Mapping[str, Any] | None,
        evidence: list[dict[str, Any]],
    ) -> None:
        super().__init__(str(cause))
        self.cause_type = type(cause).__name__
        self.mode = mode
        self.event_index = event_index
        self.event = None if event is None else dict(event)
        self.evidence = evidence


@dataclass
class EconomicOrder:
    order_id: str
    pair_id: str
    symbol: str
    asset: str
    kind: str
    side: str
    rank: int
    column: int
    price: D
    quantity: D
    capital_id: str
    submitted_at_us: int
    activate_at_us: int
    entry_price: D
    exit_price: D
    status: str = "PENDING"
    filled_quantity: D = ZERO
    activation_exchange_upper_us: int = -1
    cancel_requested_at_us: int | None = None
    inventory_capital_ids: list[str] = field(default_factory=list)
    cycle_id: str | None = None
    fees_usdt: D = ZERO
    execution_cost_usdt: D = ZERO
    adverse_selection_usdt: D = ZERO
    source_entry_order_id: str | None = None
    source_inventory_quantity: D = ZERO


class M035EconomicPairEngine:
    """Pair-local book, hotline, FIFO, orders, flow, inventory and cycles."""

    def __init__(
        self,
        *,
        pair_id: str,
        symbol: str,
        asset: str,
        config: M035BacktestConfig,
        ledger: GlobalCapitalLedger,
        fee_bps: D,
    ) -> None:
        self.pair_id = pair_id
        self.symbol = symbol
        self.asset = asset
        self.config = config
        self.ledger = ledger
        self.fee_bps = fee_bps
        self.fee_rate = fee_bps / BPS
        self.queue = CausalQueueEstimator(flow_window_us=config.flow_window_seconds * 1_000_000)
        self.orders: dict[str, EconomicOrder] = {}
        self.last_book: Mapping[str, Any] | None = None
        self.last_book_us = -1
        self.hotline: D | None = None
        self.hotline_history: list[tuple[int, D]] = []
        self.hotline_rows: list[dict[str, Any]] = []
        self.flow: dict[str, deque[tuple[int, D]]] = {"BUY": deque(), "SELL": deque()}
        self.rejections: Counter[str] = Counter()
        self.order_sequence = 0
        self.cycle_sequence = 0
        self.trade_count = 0
        self.book_count = 0
        self.trade_quantity_consumed = ZERO
        self.total_fees_usdt = ZERO
        self.total_execution_cost_usdt = ZERO
        self.total_adverse_selection_usdt = ZERO
        self.cycle_rows: list[dict[str, Any]] = []
        self.lock_seconds: list[D] = []

    @property
    def half_execution_rate(self) -> D:
        return self.config.execution_cost_bps / BPS / 2

    @property
    def half_adverse_rate(self) -> D:
        return self.config.adverse_selection_bps / BPS / 2

    def _prune_flow(self, now_us: int) -> None:
        cutoff = now_us - self.config.flow_window_seconds * 1_000_000
        for rows in self.flow.values():
            while rows and rows[0][0] < cutoff:
                rows.popleft()

    def flow_rate(self, now_us: int) -> D:
        self._prune_flow(now_us)
        window = D(self.config.flow_window_seconds)
        return min(sum((q for _, q in self.flow[side]), ZERO) / window for side in self.flow)

    def receive_book(self, event: Mapping[str, Any], *, now_us: int) -> None:
        bids = tuple((D(str(p)), D(str(q))) for p, q in event["bids"])
        asks = tuple((D(str(p)), D(str(q))) for p, q in event["asks"])
        known_bid_floor = D(str(event.get("known_bid_floor")))
        known_ask_ceiling = D(str(event.get("known_ask_ceiling")))
        if (
            not bids
            or not asks
            or not event["sequence_validated"]
            or asks[0][0] <= bids[0][0]
            or known_bid_floor > bids[0][0]
            or known_ask_ceiling < asks[0][0]
        ):
            raise ValueError("M035_INVALID_PHYSICAL_BOOK")
        midpoint = (bids[0][0] + asks[0][0]) / 2
        if abs(midpoint - 1) > self.config.emergency_peg_deviation:
            raise ValueError("M035_RISK_TRIGGER_FAIL_CLOSED_NO_UNREGISTERED_EXIT")
        next_hotline = (midpoint / self.config.tick_size).to_integral_value(
            rounding=ROUND_HALF_UP
        ) * self.config.tick_size
        old_hotline = self.hotline
        affected: list[str] = []
        if old_hotline is not None and next_hotline != old_hotline:
            affected = self._request_c2_cancels(now_us=now_us, new_hotline=next_hotline)
        self.hotline = next_hotline
        if not self.hotline_history or self.hotline_history[-1][1] != next_hotline:
            self.hotline_history.append((now_us, next_hotline))
            self.hotline_rows.append(
                {
                    "TIME_US": now_us,
                    "PAIR_ID": self.pair_id,
                    "SYMBOL": self.symbol,
                    "OLD_HOTLINE": None if old_hotline is None else _s(old_hotline),
                    "NEW_HOTLINE": _s(next_hotline),
                    "REASON": "INITIAL_BOOK" if old_hotline is None else "MIDPOINT_TICK_CHANGE",
                    "AFFECTED_C2_ORDER_IDS": affected,
                }
            )
        self.last_book = event
        self.last_book_us = now_us
        self.book_count += 1
        self.ledger.update_asset_mark(self.asset, mark_usdt=bids[0][0], now_us=now_us)
        self.advance_orders(now_us=now_us)
        self._submit_waiting_returns(now_us=now_us)
        self._submit_tradeable_dust_return(now_us=now_us)

    def receive_trade(self, event: Mapping[str, Any], *, now_us: int) -> None:
        self.trade_count += 1
        data = event["data"]
        price, quantity = D(str(data["p"])), D(str(data["q"]))
        side = "BUY" if bool(data["m"]) else "SELL"
        self.flow[side].append((now_us, quantity))
        self._prune_flow(now_us)
        self.advance_orders(now_us=now_us)
        if self.last_book is None or int(self.last_book["exchange_upper_us"]) >= int(
            event["exchange_us"]
        ):
            return
        eligible = {
            row.order_id
            for row in self.orders.values()
            if row.status in {"ACTIVE", "PARTIAL", "CANCEL_PENDING"}
            and int(event["exchange_us"]) > row.activation_exchange_upper_us
        }
        queue_after = deepcopy(self.queue)
        fills = queue_after.consume_trade_through(
            event_id=f"{self.symbol}:{data['t']}",
            book=self.symbol,
            side=side,
            trade_price=price,
            quantity=quantity,
            now_us=now_us,
        )
        consumed = sum(fills.values(), ZERO)
        if consumed > quantity:
            raise ValueError("M035_PAIR_TRADE_BUDGET_EXCEEDED")
        if any(order_id not in eligible for order_id in fills):
            raise ValueError("M035_FILL_BEFORE_NATIVE_ACTIVATION")
        if fills:
            probe = copy(self)
            probe.queue = queue_after
            probe.ledger = deepcopy(self.ledger)
            probe.orders = deepcopy(self.orders)
            probe.rejections = self.rejections.copy()
            probe.cycle_rows = deepcopy(self.cycle_rows)
            probe.lock_seconds = list(self.lock_seconds)
            for order_id, amount in fills.items():
                probe._apply_fill(probe.orders[order_id], amount, now_us=now_us)
            self.queue = probe.queue
            self.ledger.__dict__.clear()
            self.ledger.__dict__.update(probe.ledger.__dict__)
            self.orders = probe.orders
            self.rejections = probe.rejections
            self.cycle_rows = probe.cycle_rows
            self.lock_seconds = probe.lock_seconds
            self.order_sequence = probe.order_sequence
            self.cycle_sequence = probe.cycle_sequence
            self.total_fees_usdt = probe.total_fees_usdt
            self.total_execution_cost_usdt = probe.total_execution_cost_usdt
            self.total_adverse_selection_usdt = probe.total_adverse_selection_usdt
        else:
            self.queue = queue_after
        self.trade_quantity_consumed += consumed

    def _public_queue(self, side: str, price: D) -> D:
        assert self.last_book is not None
        levels = self.last_book["bids"] if side == "BUY" else self.last_book["asks"]
        return next((D(str(q)) for p, q in levels if D(str(p)) == price), ZERO)

    def _price_has_causal_book_coverage(self, side: str, price: D) -> bool:
        if self.last_book is None:
            return False
        if side == "BUY":
            return price >= D(str(self.last_book["known_bid_floor"]))
        return price <= D(str(self.last_book["known_ask_ceiling"]))

    def advance_orders(self, *, now_us: int) -> None:
        for order in sorted(self.orders.values(), key=lambda row: row.order_id):
            if order.status == "CANCEL_PENDING":
                assert order.cancel_requested_at_us is not None
                if now_us < order.cancel_requested_at_us + self.config.cancel_ack_latency_us:
                    continue
                if order.order_id in self.queue.order_group:
                    if order.filled_quantity:
                        self.queue.cancel_ack_after_racing_fill(order.order_id, now_us=now_us)
                    else:
                        self.queue.cancel_ack(order.order_id, now_us=now_us)
                position = self.ledger.positions.get(order.capital_id)
                if position is not None and position.asset == "USDT":
                    self.ledger.acknowledge_cancel(order.capital_id, now_us=now_us)
                order.status = "PARTIAL_CANCELLED" if order.filled_quantity else "CANCELLED"
                if order.status == "PARTIAL_CANCELLED":
                    self._submit_return(order, now_us=now_us)
                continue
            if order.status != "PENDING" or now_us < order.activate_at_us:
                continue
            if (
                self.last_book is None
                or int(self.last_book["exchange_upper_us"]) < order.activate_at_us
                or not self._price_has_causal_book_coverage(order.side, order.price)
            ):
                continue
            bid = D(str(self.last_book["bids"][0][0]))
            ask = D(str(self.last_book["asks"][0][0]))
            if (order.side == "BUY" and order.price >= ask) or (
                order.side == "SELL" and order.price <= bid
            ):
                continue
            self.queue.activate(
                book=self.symbol,
                side=order.side,
                price=order.price,
                order_id=order.order_id,
                column=order.column,
                quantity=order.quantity,
                observed_public_queue=self._public_queue(order.side, order.price),
                now_us=now_us,
            )
            order.status = "ACTIVE"
            order.activation_exchange_upper_us = max(
                int(self.last_book["exchange_upper_us"]), order.activate_at_us
            )

    def _request_c2_cancels(self, *, now_us: int, new_hotline: D) -> list[str]:
        affected: list[str] = []
        for order in self.orders.values():
            if (
                order.kind == "ENTRY"
                and order.column == 2
                and order.status in {"PENDING", "ACTIVE", "PARTIAL"}
                and order.price != new_hotline - D(order.rank) * self.config.tick_size
            ):
                self.ledger.request_cancel(order.capital_id, now_us=now_us)
                order.status = "CANCEL_PENDING"
                order.cancel_requested_at_us = now_us
                affected.append(order.order_id)
        return affected

    def candidates(self, *, now_us: int) -> list[tuple[AllocationCandidate, dict[str, Any]]]:
        if (
            self.last_book is None
            or self.hotline is None
            or now_us - self.last_book_us > self.config.maximum_book_age_us
        ):
            return []
        bid, ask = D(str(self.last_book["bids"][0][0])), D(str(self.last_book["asks"][0][0]))
        midpoint = (bid + ask) / 2
        spread_bps = (ask - bid) / midpoint * BPS
        depth = sum(
            D(str(p)) * D(str(q)) for p, q in (*self.last_book["bids"], *self.last_book["asks"])
        )
        if (
            spread_bps > self.config.maximum_spread_bps
            or depth < self.config.minimum_depth_usd
            or self.flow_rate(now_us) < self.config.minimum_flow_per_second
        ):
            return []
        occupied = {
            (row.rank, row.column)
            for row in self.orders.values()
            if row.kind == "ENTRY"
            and row.status in {"PENDING", "ACTIVE", "PARTIAL", "CANCEL_PENDING"}
        }
        occupied_prices = {
            (row.price, row.column)
            for row in self.orders.values()
            if row.kind == "ENTRY"
            and row.status in {"PENDING", "ACTIVE", "PARTIAL", "CANCEL_PENDING"}
        }
        rows: list[tuple[AllocationCandidate, dict[str, Any]]] = []
        for rank in range(1, 8):
            for column in (1, 2):
                entry = self.hotline - D(rank) * self.config.tick_size
                exit_price = self.hotline + D(rank) * self.config.tick_size
                if (rank, column) in occupied or (entry, column) in occupied_prices:
                    continue
                if not self._price_has_causal_book_coverage("BUY", entry) or not (
                    self._price_has_causal_book_coverage("SELL", exit_price)
                ):
                    self.rejections["PRICE_OUTSIDE_CAUSAL_BOOK_COVERAGE"] += 1
                    continue
                quantity = self.config.order_quantity
                input_usdt = entry * quantity
                if (
                    quantity < self.config.minimum_quantity
                    or input_usdt < self.config.minimum_notional
                ):
                    continue
                net_asset = quantity * (1 - self.fee_rate)
                return_quantity = (net_asset / self.config.quantity_step).to_integral_value(
                    rounding=ROUND_FLOOR
                ) * self.config.quantity_step
                if return_quantity < self.config.minimum_quantity:
                    continue
                net_proceeds = return_quantity * exit_price * (1 - self.fee_rate)
                proportional_basis = input_usdt * return_quantity / net_asset
                external = (
                    input_usdt
                    * (self.config.execution_cost_bps + self.config.adverse_selection_bps)
                    / BPS
                )
                expected_net = net_proceeds - proportional_basis - external
                decision_edge_bps = expected_net / input_usdt * BPS - self.config.risk_buffer_bps
                if decision_edge_bps < self.config.minimum_net_edge_bps:
                    self.rejections["INSUFFICIENT_EXPECTED_NET_EDGE"] += 1
                    continue
                metadata = {
                    "entry_price": entry,
                    "exit_price": exit_price,
                    "quantity": quantity,
                    "expected_external_cost": external,
                    "expected_entry_external_cost": input_usdt
                    * (self.half_execution_rate + self.half_adverse_rate),
                }
                candidate = AllocationCandidate(
                    candidate_id=f"{self.pair_id}:{now_us}:R{rank}:C{column}",
                    pair_id=self.pair_id,
                    requested_usdt=input_usdt,
                    priority=AllocationPriority.NEW_ENTRY,
                    marginal_productivity=expected_net / (input_usdt * D(300)),
                    fifo_value=ZERO,
                    expected_lock_seconds=D(300),
                    expected_net_edge=expected_net,
                    allow_partial=False,
                )
                rows.append((candidate, metadata))
        return rows

    def submit_entry(
        self,
        candidate: AllocationCandidate,
        metadata: Mapping[str, Any],
        capital_id: str,
        *,
        now_us: int,
    ) -> None:
        self.order_sequence += 1
        order = EconomicOrder(
            order_id=f"{self.pair_id}:O:{self.order_sequence:06d}",
            pair_id=self.pair_id,
            symbol=self.symbol,
            asset=self.asset,
            kind="ENTRY",
            side="BUY",
            rank=int(candidate.candidate_id.split(":R")[1].split(":")[0]),
            column=int(candidate.candidate_id.rsplit("C", 1)[1]),
            price=D(metadata["entry_price"]),
            quantity=D(metadata["quantity"]),
            capital_id=capital_id,
            submitted_at_us=now_us,
            activate_at_us=now_us + self.config.activation_latency_us,
            entry_price=D(metadata["entry_price"]),
            exit_price=D(metadata["exit_price"]),
        )
        self.orders[order.order_id] = order

    def _apply_fill(self, order: EconomicOrder, amount: D, *, now_us: int) -> None:
        cancel_pending = order.status == "CANCEL_PENDING"
        if order.kind == "ENTRY":
            input_usdt = amount * order.price
            fee_asset = amount * self.fee_rate
            execution = input_usdt * self.half_execution_rate
            adverse = input_usdt * self.half_adverse_rate
            inventory_id = self.ledger.record_entry_fill(
                order.capital_id,
                asset=self.asset,
                quantity_net=amount - fee_asset,
                causal_mark_usdt=self.ledger.asset_marks_usdt[self.asset],
                attributable_cost_usdt=execution + adverse,
                input_usdt=input_usdt,
                now_us=now_us,
            )
            order.inventory_capital_ids.append(inventory_id)
            order.fees_usdt += fee_asset * order.price
            self.total_fees_usdt += fee_asset * order.price
        else:
            proceeds_gross = amount * order.price
            fee_usdt = proceeds_gross * self.fee_rate
            execution = amount * order.entry_price * self.half_execution_rate
            adverse = amount * order.entry_price * self.half_adverse_rate
            complete = order.filled_quantity + amount == order.quantity
            position = self.ledger.positions[order.capital_id]
            self.ledger.settle_return(
                order.capital_id,
                cycle_id=order.cycle_id or "",
                sold_quantity=amount,
                net_proceeds_usdt=proceeds_gross - fee_usdt - execution - adverse,
                residual_mark_usdt=(
                    self.ledger.asset_marks_usdt[self.asset]
                    if complete and position.quantity > amount
                    else ZERO
                ),
                now_us=now_us,
                return_order_complete=complete,
            )
            order.fees_usdt += fee_usdt
            self.total_fees_usdt += fee_usdt
        self.total_execution_cost_usdt += execution
        self.total_adverse_selection_usdt += adverse
        order.execution_cost_usdt += execution
        order.adverse_selection_usdt += adverse
        order.filled_quantity += amount
        if order.filled_quantity < order.quantity:
            order.status = "CANCEL_PENDING" if cancel_pending else "PARTIAL"
            return
        order.status = "CANCEL_PENDING" if cancel_pending else "FILLED"
        if order.status != "FILLED":
            return
        if order.kind == "ENTRY":
            self._submit_return(order, now_us=now_us)
        else:
            order.status = "CLOSED"
            self._record_cycle(order, now_us=now_us)

    def _submit_waiting_returns(self, *, now_us: int) -> None:
        for order in sorted(self.orders.values(), key=lambda row: row.order_id):
            if order.kind == "ENTRY" and order.status in {"FILLED", "PARTIAL_CANCELLED"}:
                self._submit_return(order, now_us=now_us)

    def _submit_tradeable_dust_return(self, *, now_us: int) -> None:
        if (
            self.last_book is None
            or self.hotline is None
            or any(
                row.kind == "DUST_RETURN"
                and row.status in {"PENDING", "ACTIVE", "PARTIAL", "CANCEL_PENDING"}
                for row in self.orders.values()
            )
        ):
            return
        quantity = self.ledger.dust.tradeable_quantity(
            self.asset,
            step_size=self.config.quantity_step,
            minimum_quantity=self.config.minimum_quantity,
            pair_id=self.pair_id,
        )
        if quantity == ZERO:
            return
        preview = self.ledger.dust.preview_consumption(
            self.asset, quantity=quantity, pair_id=self.pair_id, now_us=now_us
        )
        unit_cost = preview.cost_basis_usdt / quantity
        return_cost = quantity * unit_cost * (self.half_execution_rate + self.half_adverse_rate)
        required_price = (preview.cost_basis_usdt + return_cost) / (quantity * (1 - self.fee_rate))
        required_price = (required_price / self.config.tick_size).to_integral_value(
            rounding=ROUND_CEILING
        ) * self.config.tick_size
        price = max(required_price, self.hotline + self.config.tick_size)
        if price > self.hotline + D(7) * self.config.tick_size:
            self.rejections["DUST_RETURN_OUTSIDE_FROZEN_GRID"] += 1
            return
        if quantity * price < self.config.minimum_notional:
            self.rejections["DUST_RETURN_BELOW_EXCHANGE_MINIMUM"] += 1
            return
        if not self._price_has_causal_book_coverage("SELL", price):
            self.rejections["DUST_RETURN_OUTSIDE_CAUSAL_BOOK_COVERAGE"] += 1
            return
        occupied = {
            row.column
            for row in self.orders.values()
            if row.kind in {"RETURN", "DUST_RETURN"}
            and row.price == price
            and row.status in {"PENDING", "ACTIVE", "PARTIAL", "CANCEL_PENDING"}
        }
        column = next((value for value in (1, 2) if value not in occupied), None)
        if column is None:
            self.rejections["DUST_RETURN_QUEUE_FULL"] += 1
            return
        capital_id = self.ledger.reserve_aggregated_dust(
            pair_id=self.pair_id,
            asset=self.asset,
            quantity=quantity,
            mark_usdt=self.ledger.asset_marks_usdt[self.asset],
            now_us=now_us,
        )
        self.order_sequence += 1
        self.cycle_sequence += 1
        self.orders[f"{self.pair_id}:O:{self.order_sequence:06d}"] = EconomicOrder(
            order_id=f"{self.pair_id}:O:{self.order_sequence:06d}",
            pair_id=self.pair_id,
            symbol=self.symbol,
            asset=self.asset,
            kind="DUST_RETURN",
            side="SELL",
            rank=int((price - self.hotline) / self.config.tick_size),
            column=column,
            price=price,
            quantity=quantity,
            capital_id=capital_id,
            submitted_at_us=now_us,
            activate_at_us=now_us + self.config.activation_latency_us,
            entry_price=unit_cost,
            exit_price=price,
            cycle_id=f"{self.pair_id}:DUST:CYCLE:{self.cycle_sequence:06d}",
            source_inventory_quantity=quantity,
        )

    def _submit_return(self, entry: EconomicOrder, *, now_us: int) -> None:
        if not entry.inventory_capital_ids or any(
            row.kind == "RETURN" and row.source_entry_order_id == entry.order_id
            for row in self.orders.values()
        ):
            return
        if len(entry.inventory_capital_ids) == 1:
            capital_id = entry.inventory_capital_ids[0]
        else:
            capital_id = self.ledger.consolidate_inventory(
                entry.inventory_capital_ids,
                pair_id=self.pair_id,
                asset=self.asset,
                now_us=now_us,
            )
            entry.inventory_capital_ids = [capital_id]
        position = self.ledger.positions[capital_id]
        quantity = (position.quantity / self.config.quantity_step).to_integral_value(
            rounding=ROUND_FLOOR
        ) * self.config.quantity_step
        if (
            quantity < self.config.minimum_quantity
            or quantity * entry.exit_price < self.config.minimum_notional
        ):
            self.rejections["RETURN_BELOW_EXCHANGE_MINIMUM"] += 1
            self.ledger.move_untradeable_inventory_to_dust(
                capital_id,
                now_us=now_us,
                reason="RETURN_BELOW_EXCHANGE_MINIMUM",
            )
            entry.inventory_capital_ids = []
            entry.status = "DUSTED"
            return
        if not self._price_has_causal_book_coverage("SELL", entry.exit_price):
            self.rejections["RETURN_OUTSIDE_CAUSAL_BOOK_COVERAGE"] += 1
            return
        occupied = {
            row.column
            for row in self.orders.values()
            if row.kind in {"RETURN", "DUST_RETURN"}
            and row.price == entry.exit_price
            and row.status in {"PENDING", "ACTIVE", "PARTIAL", "CANCEL_PENDING"}
        }
        available = next((column for column in (1, 2) if column not in occupied), None)
        if available is None:
            self.rejections["RETURN_QUEUE_FULL"] += 1
            return
        self.ledger.reserve_owned_return(capital_id, now_us=now_us)
        self.order_sequence += 1
        self.cycle_sequence += 1
        cycle_id = f"{self.pair_id}:CYCLE:{self.cycle_sequence:06d}"
        order = EconomicOrder(
            order_id=f"{self.pair_id}:O:{self.order_sequence:06d}",
            pair_id=self.pair_id,
            symbol=self.symbol,
            asset=self.asset,
            kind="RETURN",
            side="SELL",
            rank=entry.rank,
            column=available,
            price=entry.exit_price,
            quantity=quantity,
            capital_id=capital_id,
            submitted_at_us=entry.submitted_at_us,
            activate_at_us=now_us + self.config.activation_latency_us,
            entry_price=entry.entry_price,
            exit_price=entry.exit_price,
            cycle_id=cycle_id,
            fees_usdt=entry.fees_usdt,
            execution_cost_usdt=entry.execution_cost_usdt,
            adverse_selection_usdt=entry.adverse_selection_usdt,
            source_entry_order_id=entry.order_id,
            source_inventory_quantity=position.quantity,
        )
        self.orders[order.order_id] = order
        entry.status = "RETURN_SUBMITTED"

    def _record_cycle(self, order: EconomicOrder, *, now_us: int) -> None:
        assert order.cycle_id is not None
        record = self.ledger.cycles.cycles[order.cycle_id]
        duration = D(now_us - order.submitted_at_us) / 1_000_000
        self.lock_seconds.append(duration)
        gross_proceeds = order.quantity * order.exit_price
        if order.kind == "RETURN":
            gross_entry_quantity = order.quantity / (1 - self.fee_rate)
            cost_basis_ex_fee = order.quantity * order.entry_price
            entry_fee = (gross_entry_quantity - order.quantity) * order.entry_price
            entry_execution = gross_entry_quantity * order.entry_price * self.half_execution_rate
            entry_adverse = gross_entry_quantity * order.entry_price * self.half_adverse_rate
            counted_physical_cycle = True
            cycle_type = "SIMPLE_TWO_LEG"
        else:
            cost_basis_ex_fee = record.original_cost_basis_usdt
            entry_fee = ZERO
            entry_execution = ZERO
            entry_adverse = ZERO
            counted_physical_cycle = False
            cycle_type = "AGGREGATED_DUST_RETURN"
        return_fee = gross_proceeds * self.fee_rate
        return_execution = order.quantity * order.entry_price * self.half_execution_rate
        return_adverse = order.quantity * order.entry_price * self.half_adverse_rate
        fees = entry_fee + return_fee
        execution = entry_execution + return_execution
        adverse = entry_adverse + return_adverse
        recomputed_net = gross_proceeds - cost_basis_ex_fee - fees - execution - adverse
        attribution_residual = recomputed_net - record.net_pnl_usdt
        if abs(attribution_residual) > D("1e-24"):
            raise ValueError("M035_CYCLE_COST_ATTRIBUTION_MISMATCH")
        residual = next(
            (row for row in self.ledger.dust.lots if row.capital_id == order.capital_id),
            None,
        )
        self.cycle_rows.append(
            {
                "cycle_id": order.cycle_id,
                "cycle_type": cycle_type,
                "counted_physical_cycle": counted_physical_cycle,
                "pair_id": self.pair_id,
                "route": (
                    f"USDT->{self.asset}->USDT@BINANCE:{self.symbol}"
                    if counted_physical_cycle
                    else f"AGGREGATED_{self.asset}_DUST->USDT@BINANCE:{self.symbol}"
                ),
                "start_timestamp_us": order.submitted_at_us,
                "end_timestamp_us": now_us,
                "duration_seconds": _s(duration),
                "capital_used": _s(cost_basis_ex_fee + entry_fee),
                "entry_price": _s(order.entry_price),
                "exit_price": _s(order.exit_price),
                "gross_proceeds": _s(gross_proceeds),
                "gross_pnl": _s(gross_proceeds - cost_basis_ex_fee),
                "cost_basis_ex_received_asset_fee": _s(cost_basis_ex_fee),
                "ledger_cost_basis_including_received_asset_fee": _s(
                    record.original_cost_basis_usdt
                ),
                "entry_fee_value": _s(entry_fee),
                "return_fee_value": _s(return_fee),
                "fees": _s(fees),
                "execution_cost": _s(execution),
                "adverse_selection_cost": _s(adverse),
                "net_pnl": _s(record.net_pnl_usdt),
                "cost_attribution_residual": _s(attribution_residual),
                "return_pct": _s(record.net_pnl_usdt / record.original_cost_basis_usdt * 100),
                "residual_dust_quantity": "0" if residual is None else _s(residual.quantity),
                "residual_dust_cost_basis": (
                    "0" if residual is None else _s(residual.cost_basis_usdt)
                ),
            }
        )


class M035EconomicScenario:
    """One fee/mode counterfactual; parallel mode still has exactly one bank."""

    def __init__(self, config: M035BacktestConfig, *, fee_bps: D, parallel: bool) -> None:
        config.validate()
        self.config = config
        self.fee_bps = fee_bps
        self.parallel = parallel
        self.mode = "PARALLEL_TWO_PAIR" if parallel else "SINGLE_PAIR"
        self.name = f"F{int(fee_bps)}"
        self.ledger = GlobalCapitalLedger(config.initial_bank_usdt)
        self.allocator = ParallelPairCapitalAllocator(self.ledger)
        self.engines = {
            "USDCUSDT": M035EconomicPairEngine(
                pair_id="PAIR_A",
                symbol="USDCUSDT",
                asset="USDC",
                config=config,
                ledger=self.ledger,
                fee_bps=fee_bps,
            )
        }
        if parallel:
            self.engines["FDUSDUSDT"] = M035EconomicPairEngine(
                pair_id="PAIR_B",
                symbol="FDUSDUSDT",
                asset="FDUSD",
                config=config,
                ledger=self.ledger,
                fee_bps=fee_bps,
            )
        self.last_event_us = config.start_us
        self.locked_integral = ZERO
        self.idle_integral = ZERO
        self.pair_integral = {"PAIR_A": ZERO, "PAIR_B": ZERO}
        self.max_committed = ZERO
        self.max_abs_conservation_residual = ZERO
        self.event_count = 0
        self.checkpoint_times = tuple(
            config.start_us + offset * 1_800_000_000 for offset in range(7)
        )
        self._next_checkpoint = 0
        self.checkpoints: list[dict[str, Any]] = []
        self.capital_timeline: list[dict[str, Any]] = []
        self._last_capital_signature: tuple[str, ...] | None = None
        self._record_due_checkpoints(config.start_us)
        self._record_capital_state(config.start_us)

    def _committed(self) -> D:
        return self.ledger.committed_usdt + self.ledger.dust.marked_value(
            self.ledger.asset_marks_usdt
        )

    def _pair_committed(self, pair_id: str) -> D:
        positions = sum(
            (
                row.marked_value_usdt
                for row in self.ledger.positions.values()
                if row.pair_id == pair_id
            ),
            ZERO,
        )
        dust = sum(
            (
                row.quantity * self.ledger.asset_marks_usdt[row.asset]
                for row in self.ledger.dust.lots
                if row.pair_id == pair_id
            ),
            ZERO,
        )
        return positions + dust

    def _accumulate(self, until_us: int) -> None:
        elapsed = D(until_us - self.last_event_us)
        committed = self._committed()
        marked = self.ledger.marked_equity()
        residual = marked - self.ledger.free_usdt - committed
        self.max_abs_conservation_residual = max(self.max_abs_conservation_residual, abs(residual))
        if committed > marked or residual != ZERO:
            raise ValueError("M035_EVENT_TIME_CAPITAL_INVARIANT_FAILED")
        self.locked_integral += committed * elapsed
        self.idle_integral += self.ledger.free_usdt * elapsed
        for pair_id in self.pair_integral:
            self.pair_integral[pair_id] += self._pair_committed(pair_id) * elapsed
        self.max_committed = max(self.max_committed, committed)
        self.last_event_us = until_us

    def _residual_inventory(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for asset in ("USDC", "FDUSD"):
            quantity = sum(
                (row.quantity for row in self.ledger.positions.values() if row.asset == asset),
                ZERO,
            ) + self.ledger.dust.quantity(asset)
            if quantity > ZERO:
                result[asset] = _s(quantity)
        return result

    def _capital_buckets(self, pair_id: str) -> tuple[D, D, D, D]:
        reserved = inventory = returning = ZERO
        for row in self.ledger.positions.values():
            if row.pair_id != pair_id:
                continue
            if row.asset == "USDT":
                reserved += row.marked_value_usdt
            elif row.state.value.startswith("RETURN_"):
                returning += row.marked_value_usdt
            else:
                inventory += row.marked_value_usdt
        dust = sum(
            (
                row.quantity * self.ledger.asset_marks_usdt[row.asset]
                for row in self.ledger.dust.lots
                if row.pair_id == pair_id
            ),
            ZERO,
        )
        return reserved, inventory, returning, dust

    def _record_capital_state(self, now_us: int) -> None:
        a = self._capital_buckets("PAIR_A")
        b = self._capital_buckets("PAIR_B")
        marked = self.ledger.marked_equity()
        buckets = (self.ledger.free_usdt, *a, *b, marked)
        signature = tuple(_s(value) for value in buckets)
        if signature == self._last_capital_signature:
            return
        residual = marked - sum(buckets[:-1], ZERO)
        self.max_abs_conservation_residual = max(self.max_abs_conservation_residual, abs(residual))
        if residual != ZERO:
            raise ValueError("M035_CAPITAL_TIMELINE_CONSERVATION_FAILED")
        self.capital_timeline.append(
            {
                "SCENARIO": self.name,
                "MODE": self.mode,
                "TIME_US": now_us,
                "FREE_USDT": signature[0],
                "PAIR_A_RESERVED": signature[1],
                "PAIR_A_INVENTORY": signature[2],
                "PAIR_A_RETURN": signature[3],
                "PAIR_A_DUST": signature[4],
                "PAIR_B_RESERVED": signature[5],
                "PAIR_B_INVENTORY": signature[6],
                "PAIR_B_RETURN": signature[7],
                "PAIR_B_DUST": signature[8],
                "TOTAL_MARKED_EQUITY": signature[9],
                "GLOBAL_CAPITAL_CONSERVATION_RESIDUAL": _s(residual),
            }
        )
        self._last_capital_signature = signature

    def _checkpoint(self, time_us: int) -> dict[str, Any]:
        pair_cycles = {
            engine.pair_id: sum(row["counted_physical_cycle"] for row in engine.cycle_rows)
            for engine in self.engines.values()
        }
        cycles = sum(pair_cycles.values())
        return {
            "SCENARIO": self.name,
            "MODE": self.mode,
            "TIME_US": time_us,
            "REALIZED_EQUITY": _s(self.config.initial_bank_usdt + self.ledger.realized_pnl_usdt),
            "MARKED_EQUITY": _s(self.ledger.marked_equity()),
            "PHYSICAL_CYCLES": cycles,
            "FREE_CAPITAL": _s(self.ledger.free_usdt),
            "LOCKED_CAPITAL": _s(self._committed()),
            "PAIR_A_CAPITAL": _s(self._pair_committed("PAIR_A")),
            "PAIR_B_CAPITAL": _s(self._pair_committed("PAIR_B")),
            "PAIR_A_CYCLES": pair_cycles.get("PAIR_A", 0),
            "PAIR_B_CYCLES": pair_cycles.get("PAIR_B", 0),
            "RESIDUAL_INVENTORY": self._residual_inventory(),
        }

    def _record_due_checkpoints(self, now_us: int) -> None:
        while (
            self._next_checkpoint < len(self.checkpoint_times)
            and self.checkpoint_times[self._next_checkpoint] <= now_us
        ):
            checkpoint_us = self.checkpoint_times[self._next_checkpoint]
            if checkpoint_us > self.last_event_us:
                self._accumulate(checkpoint_us)
            self.checkpoints.append(self._checkpoint(checkpoint_us))
            self._next_checkpoint += 1

    def _advance(self, now_us: int) -> None:
        if now_us < self.last_event_us:
            raise ValueError("M035_NONCAUSAL_MERGED_EVENT")
        self._record_due_checkpoints(now_us)
        if now_us > self.last_event_us:
            self._accumulate(now_us)

    def receive(self, event: Mapping[str, Any]) -> None:
        now_us = int(event["local_us"])
        if now_us < self.config.start_us or now_us >= self.config.end_us:
            raise ValueError("M035_EVENT_OUTSIDE_FROZEN_WINDOW")
        self._advance(now_us)
        self.event_count += 1
        engine = self.engines.get(str(event["symbol"]))
        if engine is None:
            return
        if event["kind"] == "BOOK":
            engine.receive_book(event, now_us=now_us)
            self._allocate(now_us)
        elif event["kind"] == "TRADE":
            engine.receive_trade(event, now_us=now_us)
        else:
            raise ValueError("M035_UNKNOWN_EVENT_KIND")
        self.ledger.reconcile()
        self._record_capital_state(now_us)

    def _allocate(self, now_us: int) -> None:
        offered = [
            (candidate, metadata, engine)
            for engine in self.engines.values()
            for candidate, metadata in engine.candidates(now_us=now_us)
        ]
        if not offered:
            return
        by_id = {
            candidate.candidate_id: (candidate, metadata, engine)
            for candidate, metadata, engine in offered
        }
        ranked = sorted(
            (candidate for candidate, _, _ in offered),
            key=ParallelPairCapitalAllocator._ranking,
        )
        selected: list[AllocationCandidate] = []
        budget = self.ledger.free_usdt - self._outstanding_entry_cost_buffer()
        for candidate in ranked:
            metadata = by_id[candidate.candidate_id][1]
            required_buffer = D(metadata["expected_external_cost"])
            if candidate.requested_usdt + required_buffer <= budget:
                selected.append(candidate)
                budget -= candidate.requested_usdt + required_buffer
        grants = self.allocator.allocate(selected, now_us=now_us)
        for grant in grants:
            candidate, metadata, engine = by_id[grant.candidate_id]
            engine.submit_entry(candidate, metadata, grant.capital_id, now_us=now_us)

    def _outstanding_entry_cost_buffer(self) -> D:
        return sum(
            (
                (order.quantity - order.filled_quantity)
                * order.price
                * (engine.half_execution_rate + engine.half_adverse_rate)
                for engine in self.engines.values()
                for order in engine.orders.values()
                if order.kind == "ENTRY"
                and order.status in {"PENDING", "ACTIVE", "PARTIAL", "CANCEL_PENDING"}
            ),
            ZERO,
        )

    def _pair_marked_pnl(self, pair_id: str) -> D:
        realized = sum(
            (
                row.net_pnl_usdt
                for row in self.ledger.cycles.cycles.values()
                if row.pair_id == pair_id
            ),
            ZERO,
        )
        open_pnl = ZERO
        for position in self.ledger.positions.values():
            if position.pair_id != pair_id:
                continue
            open_pnl += (
                position.returned_proceeds_usdt
                + position.marked_value_usdt
                - position.returned_cost_basis_usdt
                - position.cost_basis_usdt
                - position.returned_attributable_costs_usdt
                - position.attributable_costs_usdt
            )
        dust_pnl = sum(
            (
                lot.quantity * self.ledger.asset_marks_usdt[lot.asset] - lot.cost_basis_usdt
                for lot in self.ledger.dust.lots
                if lot.pair_id == pair_id
            ),
            ZERO,
        )
        return realized + open_pnl + dust_pnl

    def evidence_snapshot(self) -> dict[str, Any]:
        """Preserve sufficient state to reconcile a successful or failed physical prefix."""
        return {
            "scenario": self.name,
            "mode": self.mode,
            "last_event_us": self.last_event_us,
            "event_count": self.event_count,
            "ledger": {
                "free_usdt": _s(self.ledger.free_usdt),
                "realized_pnl_usdt": _s(self.ledger.realized_pnl_usdt),
                "external_costs_usdt": _s(self.ledger.external_costs_usdt),
                "asset_marks_usdt": {
                    asset: _s(value) for asset, value in self.ledger.asset_marks_usdt.items()
                },
                "positions": [
                    {
                        "capital_id": row.capital_id,
                        "pair_id": row.pair_id,
                        "state": row.state.value,
                        "cost_basis_usdt": _s(row.cost_basis_usdt),
                        "marked_value_usdt": _s(row.marked_value_usdt),
                        "asset": row.asset,
                        "quantity": _s(row.quantity),
                        "created_at_us": row.created_at_us,
                        "source_candidate_id": row.source_candidate_id,
                        "source_capital_ids": row.source_capital_ids,
                        "source_cycles": row.source_cycles,
                        "attributable_costs_usdt": _s(row.attributable_costs_usdt),
                        "returned_proceeds_usdt": _s(row.returned_proceeds_usdt),
                        "returned_quantity": _s(row.returned_quantity),
                        "returned_cost_basis_usdt": _s(row.returned_cost_basis_usdt),
                        "returned_attributable_costs_usdt": _s(
                            row.returned_attributable_costs_usdt
                        ),
                        "pending_cycle_id": row.pending_cycle_id,
                        "cancel_requested_at_us": row.cancel_requested_at_us,
                    }
                    for row in self.ledger.positions.values()
                ],
                "dust": [
                    {
                        "capital_id": row.capital_id,
                        "pair_id": row.pair_id,
                        "asset": row.asset,
                        "quantity": _s(row.quantity),
                        "cost_basis_usdt": _s(row.cost_basis_usdt),
                        "source_cycles": row.source_cycles,
                        "created_at_us": row.created_at_us,
                    }
                    for row in self.ledger.dust.lots
                ],
                "cycles": [
                    {
                        "cycle_id": row.cycle_id,
                        "pair_id": row.pair_id,
                        "proceeds_usdt": _s(row.proceeds_usdt),
                        "original_cost_basis_usdt": _s(row.original_cost_basis_usdt),
                        "attributable_costs_usdt": _s(row.attributable_costs_usdt),
                        "net_pnl_usdt": _s(row.net_pnl_usdt),
                        "risk_exit": row.risk_exit,
                    }
                    for row in self.ledger.cycles.cycles.values()
                ],
                "audit": self.ledger.audit,
            },
            "pair_engines": {
                engine.symbol: {
                    "pair_id": engine.pair_id,
                    "hotline": None if engine.hotline is None else _s(engine.hotline),
                    "hotline_rows": engine.hotline_rows,
                    "orders": [
                        {
                            "order_id": row.order_id,
                            "kind": row.kind,
                            "side": row.side,
                            "rank": row.rank,
                            "column": row.column,
                            "price": _s(row.price),
                            "quantity": _s(row.quantity),
                            "filled_quantity": _s(row.filled_quantity),
                            "capital_id": row.capital_id,
                            "status": row.status,
                            "submitted_at_us": row.submitted_at_us,
                            "activate_at_us": row.activate_at_us,
                            "activation_exchange_upper_us": row.activation_exchange_upper_us,
                            "cancel_requested_at_us": row.cancel_requested_at_us,
                            "cycle_id": row.cycle_id,
                            "source_entry_order_id": row.source_entry_order_id,
                        }
                        for row in engine.orders.values()
                    ],
                    "queue": {
                        "groups": [
                            {
                                "book": group.book,
                                "side": group.side,
                                "price": _s(group.price),
                                "public_remaining": _s(group.public_remaining),
                                "own_orders": [
                                    {
                                        "order_id": row.order_id,
                                        "column": row.column,
                                        "quantity": _s(row.quantity),
                                        "remaining": _s(row.remaining),
                                        "activated_at_us": row.activated_at_us,
                                        "activation_sequence": row.activation_sequence,
                                        "public_barrier_before": _s(row.public_barrier_before),
                                        "first_fill_at_us": row.first_fill_at_us,
                                        "filled_at_us": row.filled_at_us,
                                    }
                                    for row in group.own_orders
                                ],
                            }
                            for group in engine.queue.groups.values()
                        ],
                        "processed_event_ids": _id_set_evidence(engine.queue.processed_event_ids),
                        "last_time_us": engine.queue.last_time_us,
                    },
                    "rejections": dict(sorted(engine.rejections.items())),
                }
                for engine in self.engines.values()
            },
            "capital_timeline": self.capital_timeline,
            "checkpoints": self.checkpoints,
        }

    def finish(self) -> dict[str, Any]:
        self._advance(self.config.end_us)
        marked = self.ledger.marked_equity()
        realized = self.ledger.realized_pnl_usdt
        cycles = sorted(
            (row for engine in self.engines.values() for row in engine.cycle_rows),
            key=lambda row: (row["end_timestamp_us"], row["cycle_id"]),
        )
        physical_cycles = [row for row in cycles if row["counted_physical_cycle"]]
        cycle_pnls = [row.net_pnl_usdt for row in self.ledger.cycles.cycles.values()]
        locks = [value for engine in self.engines.values() for value in engine.lock_seconds]
        for engine in self.engines.values():
            locks.extend(
                D(self.config.end_us - row.submitted_at_us) / 1_000_000
                for row in engine.orders.values()
                if (
                    row.kind == "ENTRY"
                    and row.status not in {"CANCELLED", "CLOSED", "RETURN_SUBMITTED"}
                )
                or (
                    row.kind in {"RETURN", "DUST_RETURN"}
                    and row.status in {"PENDING", "ACTIVE", "PARTIAL", "CANCEL_PENDING"}
                )
            )
        observed = self.locked_integral + self.idle_integral
        dust = {
            asset: _s(self.ledger.dust.quantity(asset))
            for asset in ("USDC", "FDUSD")
            if self.ledger.dust.quantity(asset) > ZERO
        }
        pair_cycles = {
            pair_id: sum(row["pair_id"] == pair_id for row in physical_cycles)
            for pair_id in ("PAIR_A", "PAIR_B")
        }
        pair_pnl = {pair_id: _s(self._pair_marked_pnl(pair_id)) for pair_id in ("PAIR_A", "PAIR_B")}
        pair_pnl_total = sum((D(value) for value in pair_pnl.values()), ZERO)
        bucket_total = (
            self.ledger.free_usdt
            + sum((row.marked_value_usdt for row in self.ledger.positions.values()), ZERO)
            + self.ledger.dust.marked_value(self.ledger.asset_marks_usdt)
        )
        accounting_residual = marked - bucket_total
        pair_pnl_residual = pair_pnl_total - (marked - self.config.initial_bank_usdt)
        if (
            accounting_residual != ZERO
            or self.max_abs_conservation_residual != ZERO
            or abs(pair_pnl_residual) > D("1e-24")
        ):
            raise ValueError("M035_GLOBAL_CAPITAL_AUDIT_FAILED")
        return {
            "SCENARIO": self.name,
            "MODE": self.mode,
            "FEE_BPS_PER_LEG": _s(self.fee_bps),
            "INITIAL_EQUITY": _s(self.config.initial_bank_usdt),
            "FINAL_REALIZED_EQUITY": _s(self.config.initial_bank_usdt + realized),
            "FINAL_MARKED_EQUITY": _s(marked),
            "REALIZED_PNL_USD": _s(realized),
            "MARKED_PNL_USD": _s(marked - self.config.initial_bank_usdt),
            "UNREALIZED_PNL_USD": _s(marked - self.config.initial_bank_usdt - realized),
            "REALIZED_RETURN_PCT": _s(realized / self.config.initial_bank_usdt * 100),
            "MARKED_RETURN_PCT": _s((marked / self.config.initial_bank_usdt - 1) * 100),
            "PHYSICAL_CYCLES": len(physical_cycles),
            "SLOT_EQUIVALENT_CYCLES": len(physical_cycles),
            "CYCLES_PER_HOUR": _s(D(len(physical_cycles)) / 3),
            "DUST_RETURN_SETTLEMENTS": len(cycles) - len(physical_cycles),
            "NEGATIVE_CLOSED_CYCLES": sum(value < ZERO for value in cycle_pnls),
            "ZERO_PNL_CYCLES": sum(value == ZERO for value in cycle_pnls),
            "POSITIVE_CLOSED_CYCLES": sum(value > ZERO for value in cycle_pnls),
            "NEGATIVE_RISK_EXITS": self.ledger.cycles.negative_risk_exits,
            "MIN_CYCLE_NET_PNL": None if not cycle_pnls else _s(min(cycle_pnls)),
            "MEDIAN_CYCLE_NET_PNL": (None if not cycle_pnls else _s(D(str(median(cycle_pnls))))),
            "MAX_CYCLE_NET_PNL": None if not cycle_pnls else _s(max(cycle_pnls)),
            "TOTAL_FEES": _s(
                sum((engine.total_fees_usdt for engine in self.engines.values()), ZERO)
            ),
            "EXECUTION_COST_TOTAL": _s(
                sum(
                    (engine.total_execution_cost_usdt for engine in self.engines.values()),
                    ZERO,
                )
            ),
            "ADVERSE_SELECTION_COST_TOTAL": _s(
                sum(
                    (engine.total_adverse_selection_usdt for engine in self.engines.values()),
                    ZERO,
                )
            ),
            "CAPITAL_UTILIZATION_PCT": _s(self.locked_integral / observed * 100),
            "IDLE_CAPITAL_PCT": _s(self.idle_integral / observed * 100),
            "NET_PNL_PER_CAPITAL_HOUR": _s((marked - self.config.initial_bank_usdt) / 600),
            "DUST_BY_ASSET": dust,
            "RESIDUAL_INVENTORY": self._residual_inventory(),
            "PAIR_A_CYCLES": pair_cycles["PAIR_A"],
            "PAIR_B_CYCLES": pair_cycles["PAIR_B"],
            "PAIR_A_PNL": pair_pnl["PAIR_A"],
            "PAIR_B_PNL": pair_pnl["PAIR_B"],
            "PAIR_A_CAPITAL_TIME_USD_HOURS": _s(self.pair_integral["PAIR_A"] / 3_600_000_000),
            "PAIR_B_CAPITAL_TIME_USD_HOURS": _s(self.pair_integral["PAIR_B"] / 3_600_000_000),
            "P50_LOCK": None if not locks else _s(D(str(median(locks)))),
            "P90_LOCK": None if not locks else _s(_percentile(locks, D("0.90")) or ZERO),
            "P95_LOCK": None if not locks else _s(_percentile(locks, D("0.95")) or ZERO),
            "MAX_SIMULTANEOUS_CAPITAL": _s(self.max_committed),
            "GLOBAL_CAPITAL_CONSERVATION_RESIDUAL": _s(accounting_residual),
            "MAX_ABS_CAPITAL_CONSERVATION_RESIDUAL": _s(self.max_abs_conservation_residual),
            "PAIR_PNL_RECONCILIATION_RESIDUAL": _s(pair_pnl_residual),
            "PAIR_PNL_RECONCILIATION_TOLERANCE": "1e-24",
            "TOTAL_COMMITTED_NEVER_EXCEEDED_EQUITY": True,
            "UNIQUE_CAPITAL_OWNERSHIP": True,
            "ZERO_LOSS_CYCLE_PASS": self.ledger.cycles.zero_loss_cycle_pass,
            "ZERO_LOSS_ECONOMIC_PASS": self.ledger.zero_loss_economic_pass(),
            "EVENT_COUNT": self.event_count,
            "PAIR_COUNTS": {
                engine.symbol: {
                    "books": engine.book_count,
                    "trades": engine.trade_count,
                    "trade_quantity_consumed": _s(engine.trade_quantity_consumed),
                }
                for engine in self.engines.values()
            },
            "REJECTIONS": {
                engine.symbol: dict(sorted(engine.rejections.items()))
                for engine in self.engines.values()
            },
            "CYCLES": cycles,
            "CHECKPOINTS": self.checkpoints,
            "CAPITAL_TIMELINE": self.capital_timeline,
            "PAIR_TIMELINES": {
                engine.pair_id: engine.hotline_rows for engine in self.engines.values()
            },
            "EVIDENCE": self.evidence_snapshot(),
        }


def run_mode(
    config: M035BacktestConfig,
    *,
    events: Iterable[Mapping[str, Any]],
    fees: Iterable[D],
    parallel: bool,
) -> list[dict[str, Any]]:
    scenarios = [M035EconomicScenario(config, fee_bps=fee, parallel=parallel) for fee in fees]
    event_index = 0
    event: Mapping[str, Any] | None = None
    try:
        for index, event in enumerate(events, 1):
            event_index = index
            if not (
                config.start_us <= int(event["local_us"]) < config.end_us
                and config.start_us <= int(event["exchange_us"]) < config.end_us
            ):
                raise ValueError("M035_EVENT_ESCAPED_FROZEN_WINDOW")
            for scenario in scenarios:
                scenario.receive(event)
        return [scenario.finish() for scenario in scenarios]
    except BaseException as error:
        raise M035BacktestExecutionError(
            error,
            mode="PARALLEL_TWO_PAIR" if parallel else "SINGLE_PAIR",
            event_index=event_index,
            event=event,
            evidence=[scenario.evidence_snapshot() for scenario in scenarios],
        ) from error


__all__ = [
    "M035BacktestConfig",
    "M035BacktestExecutionError",
    "M035EconomicPairEngine",
    "M035EconomicScenario",
    "run_mode",
]
