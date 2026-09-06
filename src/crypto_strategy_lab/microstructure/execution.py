from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from itertools import count
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from crypto_strategy_lab.domain import canonical_hash, require_utc
from crypto_strategy_lab.microstructure.models import (
    BookDeltaEvent,
    BookSnapshotEvent,
    CancelRequest,
    DecisionAudit,
    FeeAsset,
    FeedGapEvent,
    InventoryLedger,
    LiquidityRole,
    MarketEvent,
    MicroFill,
    OrderStatus,
    PassiveOrder,
    QueueModel,
    RiskHaltEvent,
    S0Config,
    Side,
    TradeEvent,
)


class ExecutionIntegrityError(ValueError):
    pass


class MicrostructureRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    strategy_id: str
    dataset_hash: str
    edge_status: Literal["NOT_EVALUATED", "NO_GO", "INCONCLUSIVE", "GO"]
    queue_model: QueueModel
    started_at: datetime
    finished_at: datetime
    book_valid_at_end: bool
    book_invalidations: int
    risk_halt: bool
    risk_halt_reason: str | None
    decisions: tuple[DecisionAudit, ...]
    orders: tuple[PassiveOrder, ...]
    fills: tuple[MicroFill, ...]
    ledger: InventoryLedger
    metrics: dict[str, str | int]


@dataclass(order=True)
class _Scheduled:
    timestamp: datetime
    priority: int
    serial: int
    kind: str = field(compare=False)
    payload: Any = field(compare=False)


class PassiveExecutionSimulator:
    """Deterministic event replay for passive orders; a price touch is never a fill."""

    def __init__(self, config: S0Config) -> None:
        self.config = config
        self._bids: dict[Decimal, Decimal] = {}
        self._asks: dict[Decimal, Decimal] = {}
        self._book_valid = False
        self._strategy_book_valid = False
        self._last_update_id: int | None = None
        self._latest_input_timestamp: datetime | None = None
        self._orders: list[PassiveOrder] = []
        self._fills: list[MicroFill] = []
        self._decisions: list[DecisionAudit] = []
        self._invalidations = 0
        self._risk_halt = False
        self._risk_halt_reason: str | None = None
        self._ledger = InventoryLedger(usdc=config.initial_usdc)
        self._serial = count()
        self._order_number = count(1)
        self._queue: list[_Scheduled] = []
        self._cycles = 0
        self._last_mid: Decimal | None = None

    def run(
        self,
        events: list[MarketEvent],
        *,
        dataset_hash: str,
        cancel_requests: list[CancelRequest] | None = None,
    ) -> MicrostructureRunResult:
        if not events:
            raise ExecutionIntegrityError("event stream is empty")
        self._validate_events(events)
        for event in events:
            self._schedule(event.timestamp, 0, "MARKET", event)
        for request in cancel_requests or []:
            self._schedule(request.requested_at, 1, "CANCEL_REQUEST", request)

        while self._queue:
            item = heapq.heappop(self._queue)
            if item.kind == "MARKET":
                self._on_market(item.payload)
            elif item.kind == "DELIVER_MARKET":
                self._on_market_delivery(item.payload, item.timestamp)
            elif item.kind == "ORDER_ARRIVAL":
                self._on_order_arrival(item.payload)
            elif item.kind == "FILL_NOTICE":
                self._on_fill_notice(item.payload, item.timestamp)
            elif item.kind == "CANCEL_REQUEST":
                self._on_cancel_request(item.payload)
            elif item.kind == "CANCEL_EFFECTIVE":
                self._on_cancel_effective(item.payload, item.timestamp)
            else:  # pragma: no cover - internal invariant
                raise AssertionError(f"unknown scheduled event {item.kind}")

        started_at = min(item.timestamp for item in events)
        finished_at = max(
            [item.timestamp for item in events]
            + [order.exchange_arrival_at for order in self._orders]
            + [fill.timestamp for fill in self._fills]
        )
        self._mark_inventory(finished_at)
        payload = {
            "strategy": self.config.model_dump(mode="json"),
            "dataset_hash": dataset_hash,
        }
        order_count = len(self._orders)
        filled_orders = sum(order.filled_quantity > 0 for order in self._orders)
        gross_pnl = self._ledger.realized_pnl_usdc + self._ledger.fees_usdc
        return MicrostructureRunResult(
            run_id=canonical_hash(payload),
            strategy_id=self.config.strategy_id,
            dataset_hash=dataset_hash,
            edge_status="NOT_EVALUATED",
            queue_model=self.config.queue_model,
            started_at=started_at,
            finished_at=finished_at,
            book_valid_at_end=self._book_valid,
            book_invalidations=self._invalidations,
            risk_halt=self._risk_halt,
            risk_halt_reason=self._risk_halt_reason,
            decisions=tuple(self._decisions),
            orders=tuple(order.model_copy(deep=True) for order in self._orders),
            fills=tuple(self._fills),
            ledger=self._ledger.model_copy(deep=True),
            metrics={
                "order_count": order_count,
                "fill_count": len(self._fills),
                "filled_order_count": filled_orders,
                "fill_ratio": str(
                    Decimal(filled_orders) / Decimal(order_count) if order_count else Decimal("0")
                ),
                "partial_fill_count": sum(
                    order.status == OrderStatus.PARTIALLY_FILLED for order in self._orders
                ),
                "unmatched_fill_quantity": str(self._ledger.fdusd),
                "cycle_count": self._cycles,
                "gross_pnl_usdc": str(gross_pnl),
                "net_pnl_usdc": str(self._ledger.realized_pnl_usdc),
                "fees_usdc": str(self._ledger.fees_usdc),
                "inventory_age_seconds": str(self._ledger.inventory_age_seconds),
                "capital_locked_usdc": str(self._ledger.capital_locked_usdc),
            },
        )

    def _schedule(self, timestamp: datetime, priority: int, kind: str, payload: Any) -> None:
        heapq.heappush(
            self._queue,
            _Scheduled(require_utc(timestamp), priority, next(self._serial), kind, payload),
        )

    @staticmethod
    def _validate_events(events: list[MarketEvent]) -> None:
        identities: set[tuple[datetime, int]] = set()
        prior: tuple[datetime, int] | None = None
        trade_ids: set[int] = set()
        for event in events:
            current = (require_utc(event.timestamp), event.sequence)
            if current in identities:
                raise ExecutionIntegrityError(f"duplicate event identity {current}")
            if prior is not None and current <= prior:
                raise ExecutionIntegrityError(
                    "events must be strictly ordered by timestamp/sequence"
                )
            identities.add(current)
            prior = current
            if isinstance(event, TradeEvent):
                if event.trade_id in trade_ids:
                    raise ExecutionIntegrityError(f"duplicate trade id {event.trade_id}")
                trade_ids.add(event.trade_id)

    def _on_market(self, event: MarketEvent) -> None:
        if isinstance(event, BookSnapshotEvent):
            self._bids = {item.price: item.quantity for item in event.bids if item.quantity > 0}
            self._asks = {item.price: item.quantity for item in event.asks if item.quantity > 0}
            self._last_update_id = event.update_id
            self._book_valid = True
            self._refresh_mid()
        elif isinstance(event, BookDeltaEvent):
            self._apply_delta(event)
        elif isinstance(event, FeedGapEvent):
            self._invalidate_book()
        elif isinstance(event, RiskHaltEvent):
            pass
        elif isinstance(event, TradeEvent):
            self._match_trade(event)
        self._schedule(
            event.timestamp + self.config.latency.market_data,
            2,
            "DELIVER_MARKET",
            event,
        )

    def _apply_delta(self, event: BookDeltaEvent) -> None:
        if not self._book_valid or self._last_update_id is None:
            self._invalidate_book(count_once=True)
            return
        expected = self._last_update_id + 1
        if not (event.first_update_id <= expected <= event.final_update_id):
            self._invalidate_book(count_once=True)
            return
        for level in event.bids:
            self._set_level(self._bids, level.price, level.quantity)
        for level in event.asks:
            self._set_level(self._asks, level.price, level.quantity)
        self._last_update_id = event.final_update_id
        self._refresh_mid()

    @staticmethod
    def _set_level(book: dict[Decimal, Decimal], price: Decimal, quantity: Decimal) -> None:
        if quantity == 0:
            book.pop(price, None)
        else:
            book[price] = quantity

    def _invalidate_book(self, *, count_once: bool = False) -> None:
        if not count_once or self._book_valid:
            self._invalidations += 1
        self._book_valid = False
        self._last_update_id = None

    def _refresh_mid(self) -> None:
        if self._bids and self._asks:
            self._last_mid = (max(self._bids) + min(self._asks)) / Decimal("2")

    def _on_market_delivery(self, event: MarketEvent, delivered_at: datetime) -> None:
        self._latest_input_timestamp = event.timestamp
        if isinstance(event, FeedGapEvent):
            self._strategy_book_valid = False
            return
        if isinstance(event, RiskHaltEvent):
            self._risk_halt = True
            self._risk_halt_reason = event.reason
            return
        if isinstance(event, BookSnapshotEvent):
            self._strategy_book_valid = True
        elif isinstance(event, BookDeltaEvent) and not self._book_valid:
            self._strategy_book_valid = False
        if self._strategy_book_valid and isinstance(event, (BookSnapshotEvent, BookDeltaEvent)):
            decision_at = delivered_at + self.config.latency.decision
            self._consider_s0_order(decision_at, event.timestamp)

    def _consider_s0_order(self, decision_at: datetime, latest_input: datetime) -> None:
        if self._risk_halt or self._has_active(Side.BUY) or self._ledger.fdusd > 0:
            return
        quantity = self._next_buy_quantity()
        if quantity <= 0:
            return
        notional = self.config.lower * quantity
        quote_fee = (
            notional * self.config.fees.maker_rate
            if self.config.fees.buy_fee_asset == FeeAsset.QUOTE
            else Decimal("0")
        )
        if self._ledger.usdc < notional + quote_fee:
            return
        self._decisions.append(
            DecisionAudit(
                action="PLACE_BUY",
                decision_timestamp=decision_at,
                latest_input_timestamp=latest_input,
            )
        )
        self._new_order(
            Side.BUY,
            self.config.lower,
            quantity,
            decision_at,
        )

    def _next_buy_quantity(self) -> Decimal:
        if self.config.quantity_override is not None:
            return self.config.quantity_override
        budget = (
            min(self.config.fixed_lot_usdc, self._ledger.usdc)
            if self.config.lot_mode.value == "FIXED_LOT"
            else self._ledger.usdc
        )
        if self.config.fees.buy_fee_asset == FeeAsset.QUOTE:
            budget /= Decimal("1") + self.config.fees.maker_rate
        raw = budget / self.config.lower
        steps = raw // self.config.step_size
        quantity = steps * self.config.step_size
        if quantity < self.config.min_quantity:
            return Decimal("0")
        if quantity * self.config.lower < self.config.min_notional:
            return Decimal("0")
        return quantity

    def _new_order(
        self,
        side: Side,
        price: Decimal,
        quantity: Decimal,
        decision_at: datetime,
    ) -> PassiveOrder:
        arrival = decision_at + self.config.latency.order_submit
        order = PassiveOrder(
            order_id=f"order-{next(self._order_number):06d}",
            side=side,
            price=price,
            quantity=quantity,
            placed_at=decision_at,
            exchange_arrival_at=arrival,
            queue_ahead=Decimal("0"),
            remaining_quantity=quantity,
        )
        self._orders.append(order)
        self._schedule(arrival, 1, "ORDER_ARRIVAL", order)
        return order

    def _on_order_arrival(self, order: PassiveOrder) -> None:
        if order.status != OrderStatus.PENDING:
            return
        if not self._book_valid or self._would_cross(order):
            order.status = OrderStatus.REJECTED_POST_ONLY
            return
        public_quantity = (
            self._bids.get(order.price, Decimal("0"))
            if order.side == Side.BUY
            else self._asks.get(order.price, Decimal("0"))
        )
        if self.config.queue_model == QueueModel.OPTIMISTIC:
            order.queue_ahead = Decimal("0")
        elif self.config.queue_model == QueueModel.REALISTIC_QUEUE:
            order.queue_ahead = public_quantity
        else:
            order.queue_ahead = public_quantity * self.config.conservative_queue_multiplier
        order.status = OrderStatus.OPEN

    def _would_cross(self, order: PassiveOrder) -> bool:
        if order.side == Side.BUY:
            return bool(self._asks) and order.price >= min(self._asks)
        return bool(self._bids) and order.price <= max(self._bids)

    def _match_trade(self, trade: TradeEvent) -> None:
        passive_side = Side.BUY if trade.buyer_is_maker else Side.SELL
        available = trade.quantity
        matching = [
            order
            for order in self._orders
            if order.side == passive_side
            and order.price == trade.price
            and order.status
            in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCEL_PENDING}
            and order.exchange_arrival_at < trade.timestamp
        ]
        for order in matching:
            consumed = min(order.queue_ahead, available)
            order.queue_ahead -= consumed
            available -= consumed
            if available <= 0:
                break
            fill_quantity = min(order.remaining_quantity, available)
            if fill_quantity > 0:
                fill = self._apply_fill(order, trade.timestamp, fill_quantity)
                available -= fill_quantity
                self._schedule(
                    trade.timestamp + self.config.latency.market_data,
                    2,
                    "FILL_NOTICE",
                    fill,
                )
        book = self._bids if passive_side == Side.BUY else self._asks
        if trade.price in book:
            book[trade.price] = max(Decimal("0"), book[trade.price] - trade.quantity)
            if book[trade.price] == 0:
                del book[trade.price]
            self._refresh_mid()

    def _apply_fill(
        self,
        order: PassiveOrder,
        timestamp: datetime,
        quantity: Decimal,
    ) -> MicroFill:
        cancel_pending = order.status == OrderStatus.CANCEL_PENDING
        rate = self.config.fees.rate(LiquidityRole.MAKER)
        fee_asset = (
            self.config.fees.buy_fee_asset
            if order.side == Side.BUY
            else self.config.fees.sell_fee_asset
        )
        quote_value = quantity * order.price
        fee_amount = quote_value * rate if fee_asset == FeeAsset.QUOTE else quantity * rate
        fee_quote = fee_amount if fee_asset == FeeAsset.QUOTE else fee_amount * order.price
        net_base = (
            quantity - fee_amount
            if order.side == Side.BUY and fee_asset == FeeAsset.BASE
            else quantity
        )

        if order.side == Side.BUY:
            quote_debit = quote_value + (fee_amount if fee_asset == FeeAsset.QUOTE else 0)
            if quote_debit > self._ledger.usdc:
                raise ExecutionIntegrityError("buy fill exceeds available USDC")
            previous_base = self._ledger.fdusd
            previous_cost = self._ledger.average_cost_usdc * previous_base
            self._ledger.usdc -= quote_debit
            self._ledger.fdusd += net_base
            self._ledger.average_cost_usdc = (
                previous_cost + quote_value + fee_quote
            ) / self._ledger.fdusd
            self._ledger.capital_locked_usdc += quote_value + fee_quote
            if self._ledger.inventory_opened_at is None:
                self._ledger.inventory_opened_at = timestamp
        else:
            base_debit = quantity + (fee_amount if fee_asset == FeeAsset.BASE else 0)
            if base_debit > self._ledger.fdusd:
                raise ExecutionIntegrityError("sell fill exceeds available FDUSD")
            quote_credit = quote_value - (fee_amount if fee_asset == FeeAsset.QUOTE else 0)
            cost_released = self._ledger.average_cost_usdc * base_debit
            self._ledger.fdusd -= base_debit
            self._ledger.usdc += quote_credit
            self._ledger.realized_pnl_usdc += quote_credit - cost_released
            self._ledger.capital_locked_usdc = max(
                Decimal("0"), self._ledger.capital_locked_usdc - cost_released
            )
            if self._ledger.fdusd == 0:
                self._ledger.average_cost_usdc = Decimal("0")
                self._ledger.inventory_opened_at = None
                self._ledger.inventory_age_seconds = Decimal("0")
                self._cycles += 1
        self._ledger.fees_usdc += fee_quote

        previous_filled = order.filled_quantity
        order.filled_quantity += quantity
        order.remaining_quantity -= quantity
        order.average_fill_price = (
            (order.average_fill_price * previous_filled) + quote_value
        ) / order.filled_quantity
        order.fees_quote += fee_quote
        if order.remaining_quantity == 0:
            order.status = OrderStatus.FILLED
        elif cancel_pending:
            order.status = OrderStatus.CANCEL_PENDING
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
        fill = MicroFill(
            order_id=order.order_id,
            timestamp=timestamp,
            side=order.side,
            price=order.price,
            gross_quantity=quantity,
            net_base_quantity=net_base,
            quote_value=quote_value,
            fee_amount=fee_amount,
            fee_asset=fee_asset,
            fee_quote_equivalent=fee_quote,
            role=LiquidityRole.MAKER,
            queue_ahead_after=order.queue_ahead,
            completes_order=order.status == OrderStatus.FILLED,
        )
        self._fills.append(fill)
        self._mark_inventory(timestamp)
        return fill

    def _on_fill_notice(self, fill: MicroFill, notice_at: datetime) -> None:
        decision_at = notice_at + self.config.latency.decision
        if fill.side == Side.SELL:
            if not self._risk_halt and fill.completes_order and self._ledger.fdusd == 0:
                self._decisions.append(
                    DecisionAudit(
                        action="ACCOUNT_CYCLE_AND_PLACE_BUY",
                        decision_timestamp=decision_at,
                        latest_input_timestamp=fill.timestamp,
                    )
                )
                quantity = self._next_buy_quantity()
                if quantity > 0:
                    self._new_order(Side.BUY, self.config.lower, quantity, decision_at)
            return
        if not fill.completes_order:
            return
        available = self._ledger.fdusd
        rate = self.config.fees.maker_rate
        sell_quantity = (
            available / (Decimal("1") + rate)
            if self.config.fees.sell_fee_asset == FeeAsset.BASE
            else available
        )
        self._decisions.append(
            DecisionAudit(
                action="PLACE_SELL",
                decision_timestamp=decision_at,
                latest_input_timestamp=fill.timestamp,
            )
        )
        self._new_order(
            Side.SELL,
            self.config.upper,
            sell_quantity,
            decision_at,
        )

    def _on_cancel_request(self, request: CancelRequest) -> None:
        order = next((item for item in self._orders if item.order_id == request.order_id), None)
        if order is None:
            raise ExecutionIntegrityError(f"unknown order {request.order_id}")
        if order.status not in {
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.CANCEL_PENDING,
        }:
            return
        order.cancel_requested_at = request.requested_at
        order.cancel_effective_at = request.requested_at + self.config.latency.cancel
        order.status = OrderStatus.CANCEL_PENDING
        self._schedule(order.cancel_effective_at, 1, "CANCEL_EFFECTIVE", order)

    @staticmethod
    def _on_cancel_effective(order: PassiveOrder, timestamp: datetime) -> None:
        if order.status == OrderStatus.CANCEL_PENDING and order.cancel_effective_at == timestamp:
            order.status = OrderStatus.CANCELED

    def _has_active(self, side: Side) -> bool:
        return any(
            order.side == side
            and order.status
            in {
                OrderStatus.PENDING,
                OrderStatus.OPEN,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.CANCEL_PENDING,
            }
            for order in self._orders
        )

    def _mark_inventory(self, timestamp: datetime) -> None:
        if self._ledger.fdusd > 0 and self._last_mid is not None:
            self._ledger.unrealized_pnl_usdc = self._ledger.fdusd * (
                self._last_mid - self._ledger.average_cost_usdc
            )
            if self._ledger.inventory_opened_at is not None:
                elapsed = require_utc(timestamp) - require_utc(self._ledger.inventory_opened_at)
                self._ledger.inventory_age_seconds = Decimal(str(elapsed.total_seconds()))
        elif self._ledger.fdusd == 0:
            self._ledger.unrealized_pnl_usdc = Decimal("0")


def environment_snapshot() -> dict[str, str]:
    return {
        "python_clock": "UTC",
        "numeric_model": "decimal.Decimal",
        "simulator": "passive-event-driven-v1",
        "generated_at": datetime.now(UTC).isoformat(),
    }
