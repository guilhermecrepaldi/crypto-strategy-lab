"""Typed economic primitives for the draft M032 multi-stable architecture.

The module contains no replay policy.  It defines physical rules, persistent
slot identity and auditable score/route records used by the independent M032
components.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Final

D = Decimal
ZERO: Final = D("0")
ONE: Final = D("1")


class ColumnRole(StrEnum):
    PERSISTENT_QUEUE = "C1_PERSISTENT_QUEUE"
    OPPORTUNITY = "C2_OPPORTUNITY"


class SlotState(StrEnum):
    FREE = "FREE"
    RESERVED = "RESERVED"
    LIVE = "LIVE"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    RETURN = "RETURN"
    CANCEL_PENDING = "CANCEL_PENDING"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class SymbolRule:
    symbol: str
    base_asset: str
    quote_asset: str
    tick_size: D
    step_size: D
    min_notional: D
    effective_start_us: int
    effective_end_us: int | None
    provenance: str

    def validate_order(self, *, price: D, quantity: D, time_us: int) -> None:
        if time_us < self.effective_start_us or (
            self.effective_end_us is not None and time_us >= self.effective_end_us
        ):
            raise ValueError("M032_SYMBOL_RULE_OUTSIDE_EFFECTIVE_WINDOW")
        if price <= ZERO or quantity <= ZERO:
            raise ValueError("M032_NON_POSITIVE_ORDER")
        if price % self.tick_size != ZERO:
            raise ValueError("M032_TICK_SIZE_VIOLATION")
        if quantity % self.step_size != ZERO:
            raise ValueError("M032_STEP_SIZE_VIOLATION")
        if price * quantity < self.min_notional:
            raise ValueError("M032_MIN_NOTIONAL_VIOLATION")


@dataclass(frozen=True)
class FeeProfile:
    symbol: str
    maker_rate: D
    taker_rate: D
    effective_start_us: int
    effective_end_us: int | None
    provenance: str
    account_specific: bool = False

    def rate(self, *, maker: bool, time_us: int) -> D:
        if time_us < self.effective_start_us or (
            self.effective_end_us is not None and time_us >= self.effective_end_us
        ):
            raise ValueError("M032_FEE_PROFILE_OUTSIDE_EFFECTIVE_WINDOW")
        return self.maker_rate if maker else self.taker_rate


@dataclass(frozen=True)
class StablecoinEvidence:
    asset: str
    adoption_score: D
    peg_stability_score: D
    liquidity_score: D
    reserve_quality_score: D
    binance_operational_score: D
    as_of_us: int
    provenance: tuple[str, ...]

    @property
    def safety_score(self) -> D:
        values = (
            self.adoption_score,
            self.peg_stability_score,
            self.liquidity_score,
            self.reserve_quality_score,
            self.binance_operational_score,
        )
        if any(value < ZERO or value > ONE for value in values):
            raise ValueError("M032_SAFETY_COMPONENT_OUT_OF_RANGE")
        return sum(values, ZERO) / D(len(values))


@dataclass
class EconomicSlot:
    slot_id: str
    slot_epoch: int
    origin_asset: str
    current_asset: str
    initial_usd_equivalent: D
    current_marked_value: D
    created_at_us: int
    state: SlotState = SlotState.FREE
    reserved_value: D = ZERO
    book: str | None = None
    side: str | None = None
    price: D | None = None
    column: int | None = None
    band_rank: int | None = None
    activated_at_us: int | None = None
    queue_age_us: int = 0
    estimated_queue_ahead: D = ZERO
    filled_qty: D = ZERO
    remaining_qty: D = ZERO
    cost_basis: D = ZERO
    route_id: str | None = None
    cycle_id: str | None = None
    capital_lock_started_at_us: int | None = None
    capital_lock_duration_us: int = 0
    realized_pnl: D = ZERO
    marked_pnl: D = ZERO
    reservation_id: str | None = None

    def touch_queue_age(self, now_us: int) -> None:
        if self.activated_at_us is not None:
            self.queue_age_us = max(0, now_us - self.activated_at_us)


@dataclass(frozen=True)
class ScoreBreakdown:
    candidate_id: str
    priority_class: int
    expected_net_pnl: D
    probability_of_completion: D
    capital: D
    expected_lock_seconds: D
    stablecoin_safety: D
    inventory_risk_penalty: D
    lost_fifo_value: D
    score: D


@dataclass(frozen=True)
class RouteLeg:
    symbol: str
    from_asset: str
    to_asset: str
    maker: bool = True


@dataclass(frozen=True)
class RouteCandidate:
    route_id: str
    origin_asset: str
    legs: tuple[RouteLeg, ...]

    def __post_init__(self) -> None:
        if not 2 <= len(self.legs) <= 4:
            raise ValueError("M032_ROUTE_LENGTH_MUST_BE_2_TO_4")
        cursor = self.origin_asset
        visited = {cursor}
        for index, leg in enumerate(self.legs):
            if leg.from_asset != cursor:
                raise ValueError("M032_ROUTE_ASSET_DISCONTINUITY")
            cursor = leg.to_asset
            if index < len(self.legs) - 1 and cursor in visited:
                raise ValueError("M032_ROUTE_REPEATS_ASSET_BEFORE_CLOSE")
            visited.add(cursor)
        if cursor != self.origin_asset:
            raise ValueError("M032_ROUTE_DOES_NOT_CLOSE")


@dataclass
class RouteProgress:
    execution_id: str
    candidate: RouteCandidate
    slot_id: str
    initial_quantity: D
    current_asset: str
    current_quantity: D
    started_at_us: int
    next_leg_index: int = 0
    leg_input_remaining: D = ZERO
    leg_output_accumulated: D = ZERO
    completed_fill_ids: list[str] = field(default_factory=list)
    fees_by_asset: dict[str, D] = field(default_factory=dict)
    external_fee_cost_origin: D = ZERO
    closed_at_us: int | None = None
    realized_pnl_origin: D = ZERO


@dataclass(frozen=True)
class PhysicalFill:
    fill_id: str
    symbol: str
    from_asset: str
    to_asset: str
    input_quantity: D
    output_quantity_gross: D
    fee_asset: str
    fee_quantity: D
    time_us: int

    @property
    def output_quantity_net(self) -> D:
        return self.output_quantity_gross - (
            self.fee_quantity if self.fee_asset == self.to_asset else ZERO
        )


@dataclass(frozen=True)
class InventoryReductionAuthorization:
    authorization_id: str
    slot_id: str
    slot_epoch: int
    quantity: D
    origin_cost_basis: D
    inventory_asset: str
    origin_asset: str
    exit_reservation_id: str
    decided_at_us: int
    expires_at_us: int
    rule_id: str
    rule_hash: str
    reason_code: str
    trigger_reason_code: str
    expected_hold_loss: D
    opportunity_cost_of_lock: D
    tail_risk_increase: D
    realized_loss_of_exit: D

    def __post_init__(self) -> None:
        if (
            not self.authorization_id
            or not self.slot_id
            or not self.rule_id
            or not self.rule_hash
            or not self.reason_code
            or not self.trigger_reason_code
            or not self.inventory_asset
            or not self.origin_asset
            or self.inventory_asset == self.origin_asset
            or not self.exit_reservation_id
            or self.slot_epoch < 1
            or self.quantity <= ZERO
            or self.origin_cost_basis <= ZERO
            or self.decided_at_us < 0
            or self.expires_at_us < self.decided_at_us
        ):
            raise ValueError("M034_INVALID_INVENTORY_REDUCTION_AUTHORIZATION")
        amounts = (
            self.expected_hold_loss,
            self.opportunity_cost_of_lock,
            self.tail_risk_increase,
            self.realized_loss_of_exit,
        )
        if any(value < ZERO for value in amounts):
            raise ValueError("M034_NEGATIVE_INVENTORY_REDUCTION_TERM")
        if self.realized_loss_of_exit <= ZERO:
            raise ValueError("M034_NON_POSITIVE_INVENTORY_REDUCTION_LOSS")


__all__ = [
    "ONE",
    "ZERO",
    "ColumnRole",
    "D",
    "EconomicSlot",
    "FeeProfile",
    "InventoryReductionAuthorization",
    "PhysicalFill",
    "RouteCandidate",
    "RouteLeg",
    "RouteProgress",
    "ScoreBreakdown",
    "SlotState",
    "StablecoinEvidence",
    "SymbolRule",
]
