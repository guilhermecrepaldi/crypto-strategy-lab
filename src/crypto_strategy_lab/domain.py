from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

FIVE_MINUTES = timedelta(minutes=5)


def require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class Candle(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    open_time: datetime
    close_time: datetime
    available_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_asset_volume: Decimal
    trade_count: int = Field(ge=0)
    timeframe_minutes: int = Field(default=5, gt=0)

    @model_validator(mode="after")
    def validate_candle(self) -> Candle:
        for field in ("open_time", "close_time", "available_at"):
            require_utc(getattr(self, field))
        if self.open_time >= self.close_time:
            raise ValueError("open_time must precede close_time")
        if self.available_at < self.close_time:
            raise ValueError("available_at cannot precede close_time")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("OHLC bounds are inconsistent")
        if min(self.low, self.volume, self.quote_asset_volume) < 0:
            raise ValueError("market values cannot be negative")
        return self


class Action(StrEnum):
    HOLD = "HOLD"
    BUY_FROM_USDT = "BUY_FROM_USDT"
    SELL_TO_USDT = "SELL_TO_USDT"
    ROTATE_ASSET = "ROTATE_ASSET"


class DecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Action = Action.HOLD
    from_symbol: str | None = None
    to_symbol: str | None = None
    allocation_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    confidence: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    observed_patterns: list[str] = Field(default_factory=list)
    reasoning_summary: str = ""
    invalidating_conditions: list[str] = Field(default_factory=list)
    expected_edge_after_costs: Decimal | None = None

    @model_validator(mode="after")
    def validate_action(self) -> DecisionResponse:
        if self.action == Action.BUY_FROM_USDT and not self.to_symbol:
            raise ValueError("BUY_FROM_USDT requires to_symbol")
        if self.action == Action.SELL_TO_USDT and not self.from_symbol:
            raise ValueError("SELL_TO_USDT requires from_symbol")
        if self.action == Action.ROTATE_ASSET and (
            not self.from_symbol or not self.to_symbol or self.from_symbol == self.to_symbol
        ):
            raise ValueError("ROTATE_ASSET requires distinct from_symbol and to_symbol")
        return self

    @classmethod
    def hold(cls, reason: str) -> DecisionResponse:
        return cls(action=Action.HOLD, reasoning_summary=reason)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    simulated_time: datetime
    available_data_until: datetime
    portfolio: dict[str, Any]
    market_context: dict[str, Any]
    adaptive_memory: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_temporal_boundary(self) -> DecisionRequest:
        require_utc(self.simulated_time)
        require_utc(self.available_data_until)
        if self.available_data_until >= self.simulated_time:
            raise ValueError("available_data_until must precede simulated_time")
        return self


class Fill(BaseModel):
    model_config = ConfigDict(frozen=True)

    simulated_time: datetime
    symbol: str
    side: str
    price: Decimal
    quantity: Decimal
    quote_value: Decimal
    fee: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    realized_pnl: Decimal = Decimal("0")


class PortfolioState(BaseModel):
    usdt: Decimal
    asset_symbol: str | None = None
    asset_quantity: Decimal = Decimal("0")
    average_cost: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    peak_equity: Decimal
    max_drawdown: Decimal = Decimal("0")


class StrategyPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class SafetyPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_exposure: Decimal = Field(default=Decimal("0.75"), ge=0, le=1)
    reserve_ratio: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)
    long_only: bool = True
    single_asset: bool = True
    temporal_integrity_mutable_by_ai: bool = False


class NewsRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    published_at: datetime
    first_seen_at: datetime
    source: str
    canonical_url: str
    assets: list[str] = Field(default_factory=list)
    category: str
    relevance: Decimal | None = None
    novelty: Decimal | None = None
    quality: Decimal | None = None
    sentiment: Decimal | None = None
    content_hash: str
    dedup_key: str


class ExternalSignalRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    signal_type: str
    observed_at: datetime
    available_at: datetime
    payload: dict[str, Any]
