"""Venue-explicit primitives for M033.

M032 remains immutable.  These types move physical identity from ``symbol`` to
``venue + native symbol`` without changing the inherited economic policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

D = Decimal
ZERO = D("0")


class Venue(StrEnum):
    BINANCE = "BINANCE"
    KRAKEN = "KRAKEN"


@dataclass(frozen=True, order=True)
class BookKey:
    venue: Venue
    symbol: str

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.strip():
            raise ValueError("M033_INVALID_NATIVE_SYMBOL")

    @property
    def canonical_id(self) -> str:
        return f"{self.venue.value}:{self.symbol}"


@dataclass(frozen=True)
class VenueSymbolRule:
    book: BookKey
    base_asset: str
    quote_asset: str
    tick_size: D
    quantity_step: D
    minimum_quantity: D
    minimum_notional: D
    price_precision: int
    effective_start_us: int
    effective_end_us: int | None
    provenance: str

    def validate(self, *, price: D, quantity: D, time_us: int) -> None:
        if time_us < self.effective_start_us or (
            self.effective_end_us is not None and time_us >= self.effective_end_us
        ):
            raise ValueError("M033_RULE_OUTSIDE_EFFECTIVE_WINDOW")
        if price <= ZERO or quantity <= ZERO:
            raise ValueError("M033_NON_POSITIVE_ORDER")
        if price % self.tick_size != ZERO:
            raise ValueError("M033_TICK_SIZE_VIOLATION")
        if quantity % self.quantity_step != ZERO:
            raise ValueError("M033_QUANTITY_STEP_VIOLATION")
        if quantity < self.minimum_quantity:
            raise ValueError("M033_MINIMUM_QUANTITY_VIOLATION")
        if price * quantity < self.minimum_notional:
            raise ValueError("M033_MINIMUM_NOTIONAL_VIOLATION")


@dataclass(frozen=True)
class VenueFeeProfile:
    book: BookKey
    maker_rate: D
    taker_rate: D
    fee_asset_semantics: str
    effective_start_us: int
    effective_end_us: int | None
    provenance: str
    account_tier_assumption: str

    def rate(self, *, maker: bool, time_us: int) -> D:
        if time_us < self.effective_start_us or (
            self.effective_end_us is not None and time_us >= self.effective_end_us
        ):
            raise ValueError("M033_FEE_OUTSIDE_EFFECTIVE_WINDOW")
        return self.maker_rate if maker else self.taker_rate


@dataclass(frozen=True)
class VenueOrderSemantics:
    """Exchange-physical order behavior, never an economic-policy shortcut."""

    venue: Venue
    post_only_mechanism: str
    cancel_releases_on_ack_only: bool
    quantity_decrease_priority: str
    quantity_increase_priority: str
    price_change_priority: str
    chained_unacknowledged_actions: str
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class VenueLatencyProfile:
    """Frozen latency inputs; unknown values stay unknown rather than becoming zero."""

    venue: Venue
    market_data_latency_us: int | None
    order_submit_latency_us: int | None
    order_ack_latency_us: int | None
    cancel_latency_us: int | None
    cancel_ack_latency_us: int | None
    provenance: str

    def __post_init__(self) -> None:
        values = (
            self.market_data_latency_us,
            self.order_submit_latency_us,
            self.order_ack_latency_us,
            self.cancel_latency_us,
            self.cancel_ack_latency_us,
        )
        if any(value is not None and value < 0 for value in values):
            raise ValueError("M033_NEGATIVE_LATENCY")


@dataclass(frozen=True)
class AssetSafetyEvidence:
    asset: str
    adoption_score: D
    peg_stability_score: D
    reserve_quality_score: D
    global_liquidity_score: D
    as_of_us: int
    provenance: tuple[str, ...]

    @property
    def safety_score(self) -> D:
        values = (
            self.adoption_score,
            self.peg_stability_score,
            self.reserve_quality_score,
            self.global_liquidity_score,
        )
        if any(value < ZERO or value > D(1) for value in values):
            raise ValueError("M033_ASSET_SAFETY_COMPONENT_OUT_OF_RANGE")
        return sum(values, ZERO) / D(len(values))


@dataclass(frozen=True)
class VenueOperationalEvidence:
    venue: Venue
    asset: str
    trading_status: str
    market_available: bool
    operational_quality_score: D
    as_of_us: int
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if not ZERO <= self.operational_quality_score <= D(1):
            raise ValueError("M033_VENUE_OPERATIONAL_SCORE_OUT_OF_RANGE")


@dataclass(frozen=True)
class CanonicalLevel:
    price: D
    quantity: D


@dataclass(frozen=True)
class CanonicalBookSnapshot:
    book: BookKey
    bids: tuple[CanonicalLevel, ...]
    asks: tuple[CanonicalLevel, ...]
    exchange_time_us: int
    local_capture_time_us: int
    update_id: str


@dataclass(frozen=True)
class CanonicalBookDelta:
    book: BookKey
    side: str
    price: D
    quantity: D
    exchange_time_us: int
    local_capture_time_us: int
    update_id: str


@dataclass(frozen=True)
class CanonicalTrade:
    book: BookKey
    trade_id: str
    price: D
    quantity: D
    aggressor_side: str | None
    exchange_time_us: int
    local_capture_time_us: int


class L3EventType(StrEnum):
    ADD = "ADD"
    MODIFY = "MODIFY"
    DELETE = "DELETE"


@dataclass(frozen=True)
class L3OrderEvent:
    book: BookKey
    event_id: str
    event_type: L3EventType
    side: str
    price: D
    order_id: str
    remaining_quantity: D
    order_entry_time_us: int
    exchange_time_us: int
    local_capture_time_us: int
    message_sequence: int


@dataclass(frozen=True)
class VenueRouteLeg:
    book: BookKey
    from_asset: str
    to_asset: str
    maker: bool = True


@dataclass(frozen=True)
class VenueRoute:
    route_id: str
    origin_asset: str
    legs: tuple[VenueRouteLeg, ...]

    def __post_init__(self) -> None:
        if not 2 <= len(self.legs) <= 4:
            raise ValueError("M033_ROUTE_LENGTH_MUST_BE_2_TO_4")
        venues = {leg.book.venue for leg in self.legs}
        if len(venues) != 1:
            raise ValueError("M033_CROSS_VENUE_ROUTE_PROHIBITED")
        cursor = self.origin_asset
        for leg in self.legs:
            if leg.from_asset != cursor:
                raise ValueError("M033_ROUTE_ASSET_DISCONTINUITY")
            cursor = leg.to_asset
        if cursor != self.origin_asset:
            raise ValueError("M033_ROUTE_DOES_NOT_CLOSE")

    @property
    def venue(self) -> Venue:
        return self.legs[0].book.venue


@dataclass(frozen=True)
class VenuePhysicalFill:
    venue: Venue
    fill_id: str
    book: BookKey
    from_asset: str
    to_asset: str
    input_quantity: D
    output_quantity_gross: D
    fee_asset: str
    fee_quantity: D
    time_us: int

    def __post_init__(self) -> None:
        if self.venue != self.book.venue:
            raise ValueError("M033_FILL_BOOK_VENUE_MISMATCH")


__all__ = [
    "ZERO",
    "AssetSafetyEvidence",
    "BookKey",
    "CanonicalBookDelta",
    "CanonicalBookSnapshot",
    "CanonicalLevel",
    "CanonicalTrade",
    "D",
    "L3EventType",
    "L3OrderEvent",
    "Venue",
    "VenueFeeProfile",
    "VenueLatencyProfile",
    "VenueOperationalEvidence",
    "VenueOrderSemantics",
    "VenuePhysicalFill",
    "VenueRoute",
    "VenueRouteLeg",
    "VenueSymbolRule",
]
