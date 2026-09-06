from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from crypto_strategy_lab.domain import require_utc


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class QueueModel(StrEnum):
    OPTIMISTIC = "OPTIMISTIC"
    REALISTIC_QUEUE = "REALISTIC_QUEUE"
    CONSERVATIVE_QUEUE = "CONSERVATIVE_QUEUE"


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELED = "CANCELED"
    REJECTED_POST_ONLY = "REJECTED_POST_ONLY"
    EXPIRED = "EXPIRED"


class LiquidityRole(StrEnum):
    MAKER = "MAKER"
    TAKER = "TAKER"


class FeeAsset(StrEnum):
    BASE = "BASE"
    QUOTE = "QUOTE"


class LotMode(StrEnum):
    FIXED = "FIXED_LOT"
    COMPOUNDING = "COMPOUNDING_LOT"


class LatencyConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    market_data_ms: int = Field(default=0, ge=0)
    decision_ms: int = Field(default=0, ge=0)
    order_submit_ms: int = Field(default=0, ge=0)
    cancel_ms: int = Field(default=0, ge=0)

    @property
    def market_data(self) -> timedelta:
        return timedelta(milliseconds=self.market_data_ms)

    @property
    def decision(self) -> timedelta:
        return timedelta(milliseconds=self.decision_ms)

    @property
    def order_submit(self) -> timedelta:
        return timedelta(milliseconds=self.order_submit_ms)

    @property
    def cancel(self) -> timedelta:
        return timedelta(milliseconds=self.cancel_ms)


class FeeModel(BaseModel):
    """Explicit fee assumptions; never infers a temporary exchange promotion."""

    model_config = ConfigDict(frozen=True)

    maker_rate: Decimal = Field(default=Decimal("0"), ge=0)
    taker_rate: Decimal = Field(default=Decimal("0"), ge=0)
    buy_fee_asset: FeeAsset = FeeAsset.QUOTE
    sell_fee_asset: FeeAsset = FeeAsset.QUOTE
    source: str = "EXPLICIT_SCENARIO_NOT_ACCOUNT_VERIFIED"

    def rate(self, role: LiquidityRole) -> Decimal:
        return self.maker_rate if role == LiquidityRole.MAKER else self.taker_rate

    def one_tick_net_quote(
        self,
        *,
        lower: Decimal,
        upper: Decimal,
        quantity: Decimal,
        buy_role: LiquidityRole,
        sell_role: LiquidityRole,
    ) -> Decimal:
        buy_rate = self.rate(buy_role)
        sell_rate = self.rate(sell_role)
        return quantity * (upper * (Decimal("1") - sell_rate)) - quantity * (
            lower * (Decimal("1") + buy_rate)
        )


class PriceLevel(BaseModel):
    model_config = ConfigDict(frozen=True)

    price: Decimal = Field(gt=0)
    quantity: Decimal = Field(ge=0)


class BookSnapshotEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    sequence: int = Field(ge=0)
    update_id: int = Field(ge=0)
    bids: tuple[PriceLevel, ...]
    asks: tuple[PriceLevel, ...]

    @model_validator(mode="after")
    def validate_snapshot(self) -> BookSnapshotEvent:
        require_utc(self.timestamp)
        if not self.bids or not self.asks:
            raise ValueError("snapshot requires at least one bid and ask")
        if max(item.price for item in self.bids) >= min(item.price for item in self.asks):
            raise ValueError("snapshot book is crossed")
        return self


class BookDeltaEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    sequence: int = Field(ge=0)
    first_update_id: int = Field(ge=0)
    final_update_id: int = Field(ge=0)
    bids: tuple[PriceLevel, ...] = ()
    asks: tuple[PriceLevel, ...] = ()

    @model_validator(mode="after")
    def validate_delta(self) -> BookDeltaEvent:
        require_utc(self.timestamp)
        if self.first_update_id > self.final_update_id:
            raise ValueError("first_update_id cannot exceed final_update_id")
        return self


class FeedGapEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    sequence: int = Field(ge=0)
    reason: str

    @model_validator(mode="after")
    def validate_gap(self) -> FeedGapEvent:
        require_utc(self.timestamp)
        return self


class RiskHaltEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    sequence: int = Field(ge=0)
    reason: str
    evidence: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_halt(self) -> RiskHaltEvent:
        require_utc(self.timestamp)
        if not self.reason.strip() or not self.evidence:
            raise ValueError("RISK_HALT requires a reason and explicit evidence")
        return self


class TradeEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    trade_id: int = Field(ge=0)
    timestamp: datetime
    sequence: int = Field(ge=0)
    price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    buyer_is_maker: bool

    @model_validator(mode="after")
    def validate_trade(self) -> TradeEvent:
        require_utc(self.timestamp)
        return self


MarketEvent = BookSnapshotEvent | BookDeltaEvent | FeedGapEvent | RiskHaltEvent | TradeEvent


class CancelRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str
    requested_at: datetime

    @model_validator(mode="after")
    def validate_request(self) -> CancelRequest:
        require_utc(self.requested_at)
        return self


class DecisionAudit(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: str
    decision_timestamp: datetime
    latest_input_timestamp: datetime

    @model_validator(mode="after")
    def reject_lookahead(self) -> DecisionAudit:
        decision = require_utc(self.decision_timestamp)
        latest = require_utc(self.latest_input_timestamp)
        if latest > decision:
            raise ValueError("latest_input_timestamp cannot exceed decision_timestamp")
        return self


class PassiveOrder(BaseModel):
    order_id: str
    side: Side
    price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    placed_at: datetime
    exchange_arrival_at: datetime
    queue_ahead: Decimal = Field(ge=0)
    filled_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    remaining_quantity: Decimal = Field(ge=0)
    average_fill_price: Decimal = Field(default=Decimal("0"), ge=0)
    maker_or_taker: LiquidityRole = LiquidityRole.MAKER
    fees_quote: Decimal = Field(default=Decimal("0"), ge=0)
    cancel_requested_at: datetime | None = None
    cancel_effective_at: datetime | None = None
    status: OrderStatus = OrderStatus.PENDING


class MicroFill(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str
    timestamp: datetime
    side: Side
    price: Decimal
    gross_quantity: Decimal
    net_base_quantity: Decimal
    quote_value: Decimal
    fee_amount: Decimal
    fee_asset: FeeAsset
    fee_quote_equivalent: Decimal
    role: LiquidityRole
    queue_ahead_after: Decimal
    completes_order: bool


class InventoryLedger(BaseModel):
    usdc: Decimal
    fdusd: Decimal = Decimal("0")
    average_cost_usdc: Decimal = Decimal("0")
    realized_pnl_usdc: Decimal = Decimal("0")
    unrealized_pnl_usdc: Decimal = Decimal("0")
    fees_usdc: Decimal = Decimal("0")
    capital_locked_usdc: Decimal = Decimal("0")
    inventory_opened_at: datetime | None = None
    inventory_age_seconds: Decimal = Decimal("0")


class S0Config(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str = "S0_FROZEN_LEVELS-v1"
    symbol: str = "FDUSDUSDC"
    lower: Decimal = Decimal("0.9988")
    upper: Decimal = Decimal("0.9989")
    quantity_override: Decimal | None = Field(default=None, gt=0)
    initial_usdc: Decimal = Field(default=Decimal("1000"), gt=0)
    lot_mode: LotMode = LotMode.COMPOUNDING
    fixed_lot_usdc: Decimal = Field(default=Decimal("1000"), gt=0)
    step_size: Decimal = Field(default=Decimal("0.01"), gt=0)
    min_quantity: Decimal = Field(default=Decimal("0.01"), gt=0)
    min_notional: Decimal = Field(default=Decimal("5"), gt=0)
    queue_model: QueueModel = QueueModel.REALISTIC_QUEUE
    conservative_queue_multiplier: Decimal = Field(default=Decimal("2"), ge=1)
    latency: LatencyConfig = LatencyConfig()
    fees: FeeModel = FeeModel()

    @model_validator(mode="after")
    def validate_levels(self) -> S0Config:
        if self.upper <= self.lower:
            raise ValueError("upper must exceed lower")
        return self
