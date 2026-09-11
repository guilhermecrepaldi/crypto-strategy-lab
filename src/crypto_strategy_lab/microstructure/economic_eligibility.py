"""M034 Binance economic eligibility, valuation and explainable allocation.

This module is the single M034 admission authority.  It composes the reviewed
M032/M033 ledgers, queues, scorers and venue identity without becoming a replay
engine or claiming that missing economic evidence is zero.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, replace
from decimal import ROUND_CEILING
from enum import StrEnum
from hashlib import sha256

from crypto_strategy_lab.microstructure.adaptive_multi_stable_manager import (
    AdaptiveColumnAllocator,
)
from crypto_strategy_lab.microstructure.multi_stable_models import (
    ZERO,
    D,
    InventoryReductionAuthorization,
)
from crypto_strategy_lab.microstructure.multi_stable_routing import (
    EligibleOpportunity,
    PairProductivityScorer,
)
from crypto_strategy_lab.microstructure.multi_venue_models import (
    BookKey,
    FeeEvidenceStatus,
    Venue,
    VenueFeeProfile,
    VenueSymbolRule,
)

BPS = D("10000")


class EvaluationMode(StrEnum):
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    FORWARD = "FORWARD"


class DecisionIntent(StrEnum):
    NEW_ENTRY = "NEW_ENTRY"
    OWNED_RETURN = "OWNED_RETURN"
    INVENTORY_REDUCTION = "INVENTORY_REDUCTION"


class UnknownCostPolicy(StrEnum):
    REJECT = "REJECT"
    CONSERVATIVE_BOUND = "CONSERVATIVE_BOUND"


class SafetyState(StrEnum):
    ACCEPTABLE = "ACCEPTABLE"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class AllocationState(StrEnum):
    ALLOCATED = "ALLOCATED"
    PARTIALLY_ALLOCATED = "PARTIALLY_ALLOCATED"
    NO_ELIGIBLE_OPPORTUNITY = "NO_ELIGIBLE_OPPORTUNITY"


class DataState(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class CapitalState(StrEnum):
    ACTIVE_NEW_ENTRY = "ACTIVE_NEW_ENTRY"
    ACTIVE_OWNED_RETURN = "ACTIVE_OWNED_RETURN"
    LOCKED_INVENTORY = "LOCKED_INVENTORY"
    PENDING_CANCEL_ACK = "PENDING_CANCEL_ACK"
    IDLE_NO_ELIGIBLE_OPPORTUNITY = "IDLE_NO_ELIGIBLE_OPPORTUNITY"
    BLOCKED_DATA = "BLOCKED_DATA"
    BLOCKED_SAFETY = "BLOCKED_SAFETY"


class ThresholdSourceType(StrEnum):
    OWNER_PREREGISTERED = "OWNER_PREREGISTERED"
    EXTERNAL_ECONOMIC_RULE = "EXTERNAL_ECONOMIC_RULE"
    TRAINING_DATA_ESTIMATE = "TRAINING_DATA_ESTIMATE"
    SAFETY_BOUND = "SAFETY_BOUND"
    PROTOCOL_CONSTANT = "PROTOCOL_CONSTANT"


class DatasetRole(StrEnum):
    CALIBRATION = "CALIBRATION"
    VALIDATION_OOS = "VALIDATION_OOS"


class RuleEvidenceStatus(StrEnum):
    PROVEN_HISTORICAL = "PROVEN_HISTORICAL"
    PROVEN_FORWARD = "PROVEN_FORWARD"
    UNPROVEN = "UNPROVEN"


class DecisionReasonCode(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    EDGE_BELOW_MINIMUM = "EDGE_BELOW_MINIMUM"
    FEE_UNPROVEN = "FEE_UNPROVEN"
    EXECUTION_COST_UNKNOWN = "EXECUTION_COST_UNKNOWN"
    ADVERSE_SELECTION_UNKNOWN = "ADVERSE_SELECTION_UNKNOWN"
    ADVERSE_SELECTION_TOO_HIGH = "ADVERSE_SELECTION_TOO_HIGH"
    COMPLETION_PROBABILITY_UNKNOWN = "COMPLETION_PROBABILITY_UNKNOWN"
    COMPLETION_PROBABILITY_TOO_LOW = "COMPLETION_PROBABILITY_TOO_LOW"
    EXPECTED_LOCK_UNKNOWN = "EXPECTED_LOCK_UNKNOWN"
    EXPECTED_LOCK_TOO_HIGH = "EXPECTED_LOCK_TOO_HIGH"
    PEG_RISK = "PEG_RISK"
    ABNORMAL_SPREAD = "ABNORMAL_SPREAD"
    LIQUIDITY_COLLAPSE = "LIQUIDITY_COLLAPSE"
    COMPATIBLE_FLOW_COLLAPSE = "COMPATIBLE_FLOW_COLLAPSE"
    DATA_GAP = "DATA_GAP"
    UNKNOWN_MARKET_STATE = "UNKNOWN_MARKET_STATE"
    VENUE_DISABLED_FOR_ECONOMIC_EXECUTION = "VENUE_DISABLED_FOR_ECONOMIC_EXECUTION"
    CAPITAL_UNAVAILABLE = "CAPITAL_UNAVAILABLE"
    OWNED_RETURN_PRIORITY = "OWNED_RETURN_PRIORITY"
    FIFO_SWITCHING_COST_TOO_HIGH = "FIFO_SWITCHING_COST_TOO_HIGH"
    PRODUCTIVITY_NON_POSITIVE = "PRODUCTIVITY_NON_POSITIVE"
    NO_ELIGIBLE_OPPORTUNITY = "NO_ELIGIBLE_OPPORTUNITY"
    CAPITAL_RESERVED_OWNED_RETURN = "CAPITAL_RESERVED_OWNED_RETURN"
    CAPITAL_LOCKED_INVENTORY = "CAPITAL_LOCKED_INVENTORY"
    CAPITAL_PENDING_CANCEL_ACK = "CAPITAL_PENDING_CANCEL_ACK"
    MARKET_SAFETY_BLOCK = "MARKET_SAFETY_BLOCK"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    PAIR_UNAVAILABLE = "PAIR_UNAVAILABLE"
    PAIR_EVIDENCE_UNPROVEN = "PAIR_EVIDENCE_UNPROVEN"
    EXCHANGE_RULE_UNPROVEN = "EXCHANGE_RULE_UNPROVEN"
    EXCHANGE_RULE_VIOLATION = "EXCHANGE_RULE_VIOLATION"
    THRESHOLD_NOT_EFFECTIVE = "THRESHOLD_NOT_EFFECTIVE"
    TAIL_RISK_TOO_HIGH = "TAIL_RISK_TOO_HIGH"
    INVENTORY_EXPOSURE_TOO_HIGH = "INVENTORY_EXPOSURE_TOO_HIGH"
    NEGATIVE_EXIT_NOT_ALLOWED_COSMETIC = "NEGATIVE_EXIT_NOT_ALLOWED_COSMETIC"
    NEGATIVE_EXIT_RISK_RULE_TRIGGERED = "NEGATIVE_EXIT_RISK_RULE_TRIGGERED"
    INVENTORY_LOCK_EXCEEDED = "INVENTORY_LOCK_EXCEEDED"
    PEG_RISK_ESCALATED = "PEG_RISK_ESCALATED"
    OPPORTUNITY_COST_EXCEEDED = "OPPORTUNITY_COST_EXCEEDED"


@dataclass(frozen=True)
class EconomicExecutionPolicy:
    economic_venues: frozenset[Venue]
    policy_id: str
    policy_hash: str
    provenance: str

    def __post_init__(self) -> None:
        if self.economic_venues != frozenset({Venue.BINANCE}):
            raise ValueError("M034_ECONOMIC_EXECUTION_MUST_BE_BINANCE_ONLY")
        if not self.policy_id or not self.policy_hash or not self.provenance:
            raise ValueError("M034_UNPROVEN_EXECUTION_POLICY")


@dataclass(frozen=True)
class ThresholdDefinition:
    name: str
    value: D
    unit: str
    source_type: ThresholdSourceType
    source_reference: str
    derivation_method: str
    calibration_dataset_hash: str | None
    effective_from_us: int
    frozen_at_us: int

    def __post_init__(self) -> None:
        if (
            not self.name
            or not self.unit
            or not self.source_reference
            or not self.derivation_method
            or self.effective_from_us < 0
            or self.frozen_at_us < 0
            or not self.value.is_finite()
        ):
            raise ValueError("M034_THRESHOLD_PROVENANCE_REQUIRED")
        if self.source_type == ThresholdSourceType.TRAINING_DATA_ESTIMATE and not (
            self.calibration_dataset_hash
        ):
            raise ValueError("M034_CALIBRATION_HASH_REQUIRED")


@dataclass(frozen=True)
class ThresholdRecord:
    definition: ThresholdDefinition
    config_hash: str


class ThresholdRegistry:
    REQUIRED = frozenset(
        {
            "MIN_COMPLETION_PROBABILITY",
            "MAX_EXPECTED_LOCK_TIME",
            "RISK_BUFFER",
            "MAX_INVENTORY_EXPOSURE",
            "PEG_DEVIATION_THRESHOLD",
            "MIN_NET_EDGE",
            "TAIL_RISK_BOUND",
            "MAX_SPREAD",
            "MIN_DEPTH",
            "MIN_COMPATIBLE_FLOW",
        }
    )

    def __init__(self, definitions: list[ThresholdDefinition]) -> None:
        by_name = {row.name: row for row in definitions}
        optional = {"UNKNOWN_EXECUTION_COST_BOUND", "UNKNOWN_ADVERSE_SELECTION_BOUND"}
        if (
            len(by_name) != len(definitions)
            or not self.REQUIRED.issubset(by_name)
            or not set(by_name).issubset(self.REQUIRED | optional)
        ):
            raise ValueError("M034_THRESHOLD_SET_INCOMPLETE_OR_DUPLICATE")
        payload = [
            {
                "name": row.name,
                "value": str(row.value),
                "unit": row.unit,
                "source_type": row.source_type.value,
                "source_reference": row.source_reference,
                "derivation_method": row.derivation_method,
                "calibration_dataset_hash": row.calibration_dataset_hash,
                "effective_from_us": row.effective_from_us,
                "frozen_at_us": row.frozen_at_us,
            }
            for row in sorted(definitions, key=lambda item: item.name)
        ]
        self.config_hash = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.records = tuple(
            ThresholdRecord(row, self.config_hash)
            for row in sorted(definitions, key=lambda item: item.name)
        )
        self._by_name = by_name

    def value(self, name: str, *, unit: str, at_time_us: int | None = None) -> D:
        try:
            row = self._by_name[name]
        except KeyError as exc:
            raise ValueError("M034_THRESHOLD_MISSING") from exc
        if row.unit != unit:
            raise ValueError("M034_THRESHOLD_UNIT_MISMATCH")
        if at_time_us is not None and row.effective_from_us > at_time_us:
            raise ValueError("M034_THRESHOLD_NOT_EFFECTIVE")
        return row.value

    def validate_effective_at(self, time_us: int) -> None:
        if time_us < 0 or any(
            row.effective_from_us > time_us for row in self._by_name.values()
        ):
            raise ValueError("M034_THRESHOLD_NOT_EFFECTIVE")


class DatasetRoleRegistry:
    def __init__(self) -> None:
        self._roles: dict[str, DatasetRole] = {}

    def register(self, dataset_hash: str, role: DatasetRole) -> None:
        if not dataset_hash:
            raise ValueError("M034_DATASET_HASH_REQUIRED")
        previous = self._roles.get(dataset_hash)
        if previous is not None and previous != role:
            raise ValueError("M034_CALIBRATION_DATASET_CANNOT_BE_OOS")
        self._roles[dataset_hash] = role


@dataclass(frozen=True)
class M034Policy:
    policy_id: str
    provenance: str
    thresholds: ThresholdRegistry
    unknown_cost_policy: UnknownCostPolicy

    def __post_init__(self) -> None:
        if not self.policy_id or not self.provenance:
            raise ValueError("M034_POLICY_PROVENANCE_REQUIRED")
        if not ZERO <= self.minimum_completion_probability <= D(1):
            raise ValueError("M034_INVALID_COMPLETION_THRESHOLD")
        nonnegative = (
            self.maximum_expected_lock_seconds,
            self.maximum_peg_deviation,
            self.maximum_spread_bps,
            self.minimum_depth_usd,
            self.minimum_compatible_flow_per_second,
            self.risk_buffer_bps,
            self.maximum_inventory_exposure,
            self.minimum_net_edge_bps,
            self.tail_risk_bound,
        )
        if any(value < ZERO for value in nonnegative) or self.maximum_expected_lock_seconds == ZERO:
            raise ValueError("M034_INVALID_POLICY_THRESHOLD")
        if self.minimum_net_edge_bps <= ZERO:
            raise ValueError("M034_MINIMUM_NET_EDGE_MUST_BE_POSITIVE")
        if self.unknown_cost_policy == UnknownCostPolicy.CONSERVATIVE_BOUND:
            bounds = (
                self.thresholds.value("UNKNOWN_EXECUTION_COST_BOUND", unit="bps"),
                self.thresholds.value("UNKNOWN_ADVERSE_SELECTION_BOUND", unit="bps"),
            )
            if any(value < ZERO or not value.is_finite() for value in bounds):
                raise ValueError("M034_INVALID_CONSERVATIVE_COST_BOUND")

    @property
    def threshold_config_hash(self) -> str:
        return self.thresholds.config_hash

    @property
    def config_hash(self) -> str:
        payload = {
            "policy_id": self.policy_id,
            "provenance": self.provenance,
            "threshold_config_hash": self.threshold_config_hash,
            "unknown_cost_policy": self.unknown_cost_policy.value,
        }
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @property
    def minimum_completion_probability(self) -> D:
        return self.thresholds.value("MIN_COMPLETION_PROBABILITY", unit="ratio")

    @property
    def maximum_expected_lock_seconds(self) -> D:
        return self.thresholds.value("MAX_EXPECTED_LOCK_TIME", unit="seconds")

    @property
    def maximum_peg_deviation(self) -> D:
        return self.thresholds.value("PEG_DEVIATION_THRESHOLD", unit="ratio")

    @property
    def maximum_spread_bps(self) -> D:
        return self.thresholds.value("MAX_SPREAD", unit="bps")

    @property
    def minimum_depth_usd(self) -> D:
        return self.thresholds.value("MIN_DEPTH", unit="USD")

    @property
    def minimum_compatible_flow_per_second(self) -> D:
        return self.thresholds.value("MIN_COMPATIBLE_FLOW", unit="asset/second")

    @property
    def risk_buffer_bps(self) -> D:
        return self.thresholds.value("RISK_BUFFER", unit="bps")

    @property
    def maximum_inventory_exposure(self) -> D:
        return self.thresholds.value("MAX_INVENTORY_EXPOSURE", unit="USD")

    @property
    def minimum_net_edge_bps(self) -> D:
        return self.thresholds.value("MIN_NET_EDGE", unit="bps")

    @property
    def tail_risk_bound(self) -> D:
        return self.thresholds.value("TAIL_RISK_BOUND", unit="USD")

    @property
    def unknown_execution_cost_bound_bps(self) -> D | None:
        if self.unknown_cost_policy == UnknownCostPolicy.REJECT:
            return None
        return self.thresholds.value("UNKNOWN_EXECUTION_COST_BOUND", unit="bps")

    @property
    def unknown_adverse_selection_bound_bps(self) -> D | None:
        if self.unknown_cost_policy == UnknownCostPolicy.REJECT:
            return None
        return self.thresholds.value("UNKNOWN_ADVERSE_SELECTION_BOUND", unit="bps")


class VenuePairFeeRegistry:
    """Temporal, auditable fee evidence keyed by the M033 physical book identity."""

    def __init__(self) -> None:
        self._profiles: list[VenueFeeProfile] = []

    def add(self, profile: VenueFeeProfile) -> None:
        if profile in self._profiles:
            raise ValueError("M034_DUPLICATE_FEE_PROFILE")
        self._profiles.append(profile)

    def resolve(
        self,
        book: BookKey,
        *,
        time_us: int,
        mode: EvaluationMode,
        account_context: str | None,
    ) -> VenueFeeProfile | None:
        candidates = [
            profile
            for profile in self._profiles
            if profile.book == book
            and profile.effective_start_us <= time_us
            and (profile.effective_end_us is None or time_us < profile.effective_end_us)
            and profile.account_tier_assumption == account_context
        ]
        allowed = (
            {FeeEvidenceStatus.PROVEN_HISTORICAL}
            if mode == EvaluationMode.HISTORICAL_REPLAY
            else {FeeEvidenceStatus.PROVEN_FORWARD, FeeEvidenceStatus.ACCOUNT_SPECIFIC}
        )
        candidates = [
            profile
            for profile in candidates
            if profile.evidence_status in allowed
            and profile.acquired_at_us is not None
            and bool(profile.record_id)
            and bool(profile.source_reference)
            and bool(profile.provenance)
            and (mode == EvaluationMode.HISTORICAL_REPLAY or profile.acquired_at_us <= time_us)
        ]
        if len(candidates) > 1:
            return None
        return candidates[0] if candidates else None


@dataclass(frozen=True)
class VenueSymbolRuleRecord:
    rule: VenueSymbolRule
    evidence_status: RuleEvidenceStatus
    acquired_at_us: int
    record_id: str
    source_reference: str

    def __post_init__(self) -> None:
        if (
            self.acquired_at_us < 0
            or not self.record_id
            or not self.source_reference
            or not self.rule.provenance
        ):
            raise ValueError("M034_INVALID_RULE_EVIDENCE")


class VenuePairRuleRegistry:
    """Temporal exchange-rule authority; current rules cannot prove historical orders."""

    def __init__(self) -> None:
        self._records: list[VenueSymbolRuleRecord] = []

    def add(self, record: VenueSymbolRuleRecord) -> None:
        if record in self._records:
            raise ValueError("M034_DUPLICATE_RULE_RECORD")
        self._records.append(record)

    def resolve(
        self, book: BookKey, *, time_us: int, mode: EvaluationMode
    ) -> VenueSymbolRuleRecord | None:
        allowed = (
            {RuleEvidenceStatus.PROVEN_HISTORICAL}
            if mode == EvaluationMode.HISTORICAL_REPLAY
            else {RuleEvidenceStatus.PROVEN_FORWARD}
        )
        matches = [
            row
            for row in self._records
            if row.rule.book == book
            and row.evidence_status in allowed
            and row.rule.effective_start_us <= time_us
            and (row.rule.effective_end_us is None or time_us < row.rule.effective_end_us)
            and (mode == EvaluationMode.HISTORICAL_REPLAY or row.acquired_at_us <= time_us)
        ]
        return matches[0] if len(matches) == 1 else None


@dataclass(frozen=True)
class FeeLeg:
    book: BookKey
    maker: bool


@dataclass(frozen=True)
class MarketRegimeSnapshot:
    observed_at_us: int
    regime: str
    peg_deviation: D | None
    spread_bps: D | None
    depth_usd: D | None
    compatible_flow_per_second: D | None
    data_gap: bool = False

    def __post_init__(self) -> None:
        if (
            self.observed_at_us < 0
            or not self.regime
            or any(
                value is not None and (value < ZERO or not value.is_finite())
                for value in (
                    self.spread_bps,
                    self.depth_usd,
                    self.compatible_flow_per_second,
                )
            )
            or (self.peg_deviation is not None and not self.peg_deviation.is_finite())
        ):
            raise ValueError("M034_INVALID_MARKET_REGIME_SNAPSHOT")


@dataclass(frozen=True)
class MarketRegimeAssessment:
    state: SafetyState
    reason_codes: tuple[DecisionReasonCode, ...]


class MarketRegimeSafetyGate:
    @staticmethod
    def assess(snapshot: MarketRegimeSnapshot, policy: M034Policy) -> MarketRegimeAssessment:
        if snapshot.data_gap:
            return MarketRegimeAssessment(SafetyState.REJECTED, (DecisionReasonCode.DATA_GAP,))
        if any(
            value is None
            for value in (
                snapshot.peg_deviation,
                snapshot.spread_bps,
                snapshot.depth_usd,
                snapshot.compatible_flow_per_second,
            )
        ):
            return MarketRegimeAssessment(
                SafetyState.UNKNOWN, (DecisionReasonCode.UNKNOWN_MARKET_STATE,)
            )
        assert snapshot.peg_deviation is not None
        assert snapshot.spread_bps is not None
        assert snapshot.depth_usd is not None
        assert snapshot.compatible_flow_per_second is not None
        reasons: list[DecisionReasonCode] = []
        if abs(snapshot.peg_deviation) > policy.maximum_peg_deviation:
            reasons.append(DecisionReasonCode.PEG_RISK)
        if snapshot.spread_bps > policy.maximum_spread_bps:
            reasons.append(DecisionReasonCode.ABNORMAL_SPREAD)
        if snapshot.depth_usd < policy.minimum_depth_usd:
            reasons.append(DecisionReasonCode.LIQUIDITY_COLLAPSE)
        if snapshot.compatible_flow_per_second < policy.minimum_compatible_flow_per_second:
            reasons.append(DecisionReasonCode.COMPATIBLE_FLOW_COLLAPSE)
        return MarketRegimeAssessment(
            SafetyState.REJECTED if reasons else SafetyState.ACCEPTABLE,
            tuple(reasons),
        )


@dataclass(frozen=True)
class EconomicCandidate:
    candidate_id: str
    venue: Venue
    pair: BookKey
    side: str
    rank: int
    column: int
    route_id: str
    inventory_state: str
    intent: DecisionIntent
    priority_class: int
    decision_currency: str
    decision_currency_usd_rate: D
    decision_time_us: int
    order_price: D
    order_quantity: D
    gross_edge_bps: D
    execution_cost_bps: D | None
    adverse_selection_bps: D | None
    completion_probability: D | None
    expected_lock_seconds: D | None
    p95_lock_seconds: D | None
    capital_required: D
    residual_cost_if_incomplete: D
    tail_risk_cost: D
    inventory_carry_cost: D
    fee_legs: tuple[FeeLeg, ...]
    market: MarketRegimeSnapshot
    data_state: DataState
    account_context: str | None = None

    def __post_init__(self) -> None:
        if self.pair.venue != self.venue or any(
            leg.book.venue != self.venue for leg in self.fee_legs
        ):
            raise ValueError("M034_CANDIDATE_VENUE_IDENTITY_MISMATCH")
        if (
            self.side not in {"BUY", "SELL"}
            or self.rank not in range(1, 8)
            or self.column not in {1, 2}
        ):
            raise ValueError("M034_INVALID_GEOMETRY_OR_SIDE")
        if self.market.observed_at_us > self.decision_time_us:
            raise ValueError("M034_FUTURE_MARKET_SNAPSHOT")
        if (
            not self.candidate_id
            or not self.route_id
            or not self.inventory_state
            or not self.decision_currency
            or self.decision_time_us < 0
            or self.decision_currency_usd_rate <= ZERO
            or not self.decision_currency_usd_rate.is_finite()
            or self.order_price <= ZERO
            or self.order_quantity <= ZERO
            or self.capital_required <= ZERO
            or self.gross_edge_bps < ZERO
        ):
            raise ValueError("M034_INVALID_CANDIDATE_CAPITAL_OR_EDGE")
        if not self.fee_legs:
            raise ValueError("M034_CANDIDATE_FEE_LEGS_REQUIRED")
        if self.completion_probability is not None and not (
            ZERO <= self.completion_probability <= D(1)
        ):
            raise ValueError("M034_COMPLETION_PROBABILITY_OUT_OF_RANGE")
        if self.expected_lock_seconds is not None and self.expected_lock_seconds <= ZERO:
            raise ValueError("M034_INVALID_EXPECTED_LOCK")
        if self.p95_lock_seconds is not None and self.p95_lock_seconds < ZERO:
            raise ValueError("M034_INVALID_P95_LOCK")
        if any(
            value is not None and value < ZERO
            for value in (self.execution_cost_bps, self.adverse_selection_bps)
        ):
            raise ValueError("M034_NEGATIVE_ECONOMIC_COST")
        if any(
            value < ZERO
            for value in (
                self.residual_cost_if_incomplete,
                self.tail_risk_cost,
                self.inventory_carry_cost,
            )
        ):
            raise ValueError("M034_NEGATIVE_CANDIDATE_COST")
        if self.intent == DecisionIntent.OWNED_RETURN and self.priority_class != 1:
            raise ValueError("M034_OWNED_RETURN_MUST_HAVE_PRIORITY_ONE")
        if self.intent == DecisionIntent.NEW_ENTRY and self.priority_class == 1:
            raise ValueError("M034_NEW_ENTRY_CANNOT_HAVE_OBLIGATION_PRIORITY")


@dataclass(frozen=True)
class EligibilityDecision:
    decision_id: str
    timestamp_us: int
    candidate_id: str
    venue: Venue
    pair: BookKey
    side: str
    rank: int
    column: int
    route_id: str
    intent: DecisionIntent
    decision_currency: str
    decision_currency_usd_rate: D
    gross_edge_bps: D
    known_fees_bps: D | None
    execution_cost_bps: D | None
    adverse_selection_bps: D | None
    risk_buffer_bps: D
    expected_net_edge_bps: D | None
    completion_probability: D | None
    expected_lock_seconds: D | None
    p95_lock_seconds: D | None
    inventory_carry_cost: D
    tail_risk_cost: D
    fee_evidence_status: FeeEvidenceStatus
    market_regime: str
    safety_state: SafetyState
    data_state: DataState
    eligible: bool
    slots_authorized: int
    productivity_score: D | None
    decision_reason_codes: tuple[DecisionReasonCode, ...]
    policy_config_hash: str
    threshold_config_hash: str


class EconomicEligibilityGate:
    def __init__(
        self,
        *,
        execution_policy: EconomicExecutionPolicy,
        policy: M034Policy,
        fee_registry: VenuePairFeeRegistry,
        rule_registry: VenuePairRuleRegistry,
        pair_universe: BinancePairUniverse,
    ) -> None:
        self.execution_policy = execution_policy
        self.policy = policy
        self.fee_registry = fee_registry
        self.rule_registry = rule_registry
        self.pair_universe = pair_universe

    def evaluate(
        self, candidate: EconomicCandidate, *, mode: EvaluationMode
    ) -> EligibilityDecision:
        reasons: list[DecisionReasonCode] = []
        try:
            self.policy.thresholds.validate_effective_at(candidate.decision_time_us)
        except ValueError:
            reasons.append(DecisionReasonCode.THRESHOLD_NOT_EFFECTIVE)
        if candidate.venue not in self.execution_policy.economic_venues:
            reasons.append(DecisionReasonCode.VENUE_DISABLED_FOR_ECONOMIC_EXECUTION)
        if candidate.data_state != DataState.VALID:
            reasons.append(DecisionReasonCode.DATA_INSUFFICIENT)
        pair_evidence = self.pair_universe.resolve(
            candidate.pair, time_us=candidate.decision_time_us
        )
        if pair_evidence is None or not pair_evidence.available:
            reasons.append(DecisionReasonCode.PAIR_UNAVAILABLE)
        elif not pair_evidence.eligible:
            reasons.append(DecisionReasonCode.PAIR_EVIDENCE_UNPROVEN)
        rule_record = self.rule_registry.resolve(
            candidate.pair, time_us=candidate.decision_time_us, mode=mode
        )
        if rule_record is None:
            reasons.append(DecisionReasonCode.EXCHANGE_RULE_UNPROVEN)
        else:
            try:
                rule_record.rule.validate(
                    price=candidate.order_price,
                    quantity=candidate.order_quantity,
                    time_us=candidate.decision_time_us,
                )
                if candidate.decision_currency not in {
                    rule_record.rule.base_asset,
                    rule_record.rule.quote_asset,
                }:
                    raise ValueError("M034_DECISION_CURRENCY_OUTSIDE_BOOK")
            except ValueError:
                reasons.append(DecisionReasonCode.EXCHANGE_RULE_VIOLATION)

        profiles: list[VenueFeeProfile] = []
        for leg in candidate.fee_legs:
            profile = self.fee_registry.resolve(
                leg.book,
                time_us=candidate.decision_time_us,
                mode=mode,
                account_context=candidate.account_context,
            )
            if profile is None:
                reasons.append(DecisionReasonCode.FEE_UNPROVEN)
                break
            profiles.append(profile)
        known_fees_bps = (
            sum(
                (
                    profile.rate(maker=leg.maker, time_us=candidate.decision_time_us) * BPS
                    for profile, leg in zip(profiles, candidate.fee_legs, strict=True)
                ),
                ZERO,
            )
            if len(profiles) == len(candidate.fee_legs)
            else None
        )
        statuses = {profile.evidence_status for profile in profiles}
        if not profiles:
            fee_status = FeeEvidenceStatus.UNPROVEN
        elif FeeEvidenceStatus.ACCOUNT_SPECIFIC in statuses:
            fee_status = FeeEvidenceStatus.ACCOUNT_SPECIFIC
        elif FeeEvidenceStatus.PROVEN_FORWARD in statuses:
            fee_status = FeeEvidenceStatus.PROVEN_FORWARD
        else:
            fee_status = FeeEvidenceStatus.PROVEN_HISTORICAL

        execution_cost = candidate.execution_cost_bps
        adverse_cost = candidate.adverse_selection_bps
        if execution_cost is None:
            if self.policy.unknown_cost_policy == UnknownCostPolicy.CONSERVATIVE_BOUND:
                execution_cost = self.policy.unknown_execution_cost_bound_bps
            else:
                reasons.append(DecisionReasonCode.EXECUTION_COST_UNKNOWN)
        if adverse_cost is None:
            if self.policy.unknown_cost_policy == UnknownCostPolicy.CONSERVATIVE_BOUND:
                adverse_cost = self.policy.unknown_adverse_selection_bound_bps
            else:
                reasons.append(DecisionReasonCode.ADVERSE_SELECTION_UNKNOWN)

        safety = MarketRegimeSafetyGate.assess(candidate.market, self.policy)
        reasons.extend(safety.reason_codes)
        if safety.state != SafetyState.ACCEPTABLE:
            reasons.append(DecisionReasonCode.MARKET_SAFETY_BLOCK)
        if candidate.completion_probability is None:
            reasons.append(DecisionReasonCode.COMPLETION_PROBABILITY_UNKNOWN)
        elif candidate.completion_probability < self.policy.minimum_completion_probability:
            reasons.append(DecisionReasonCode.COMPLETION_PROBABILITY_TOO_LOW)
        if candidate.expected_lock_seconds is None:
            reasons.append(DecisionReasonCode.EXPECTED_LOCK_UNKNOWN)
        elif candidate.expected_lock_seconds > self.policy.maximum_expected_lock_seconds:
            reasons.append(DecisionReasonCode.EXPECTED_LOCK_TOO_HIGH)

        expected_net_edge: D | None = None
        if known_fees_bps is not None and execution_cost is not None and adverse_cost is not None:
            expected_net_edge = (
                candidate.gross_edge_bps
                - known_fees_bps
                - execution_cost
                - adverse_cost
                - self.policy.risk_buffer_bps
            )
            if expected_net_edge < self.policy.minimum_net_edge_bps:
                reasons.append(DecisionReasonCode.EDGE_BELOW_MINIMUM)
        capital_required_usd = (
            candidate.capital_required * candidate.decision_currency_usd_rate
        )
        if capital_required_usd > self.policy.maximum_inventory_exposure:
            reasons.append(DecisionReasonCode.INVENTORY_EXPOSURE_TOO_HIGH)
        if (
            candidate.tail_risk_cost * candidate.decision_currency_usd_rate
            > self.policy.tail_risk_bound
        ):
            reasons.append(DecisionReasonCode.TAIL_RISK_TOO_HIGH)

        reasons = list(dict.fromkeys(reasons))
        eligible = not reasons
        return EligibilityDecision(
            decision_id=f"{candidate.decision_time_us}:{candidate.candidate_id}",
            timestamp_us=candidate.decision_time_us,
            candidate_id=candidate.candidate_id,
            venue=candidate.venue,
            pair=candidate.pair,
            side=candidate.side,
            rank=candidate.rank,
            column=candidate.column,
            route_id=candidate.route_id,
            intent=candidate.intent,
            decision_currency=candidate.decision_currency,
            decision_currency_usd_rate=candidate.decision_currency_usd_rate,
            gross_edge_bps=candidate.gross_edge_bps,
            known_fees_bps=known_fees_bps,
            execution_cost_bps=execution_cost,
            adverse_selection_bps=adverse_cost,
            risk_buffer_bps=self.policy.risk_buffer_bps,
            expected_net_edge_bps=expected_net_edge,
            completion_probability=candidate.completion_probability,
            expected_lock_seconds=candidate.expected_lock_seconds,
            p95_lock_seconds=candidate.p95_lock_seconds,
            inventory_carry_cost=candidate.inventory_carry_cost,
            tail_risk_cost=candidate.tail_risk_cost,
            fee_evidence_status=fee_status,
            market_regime=candidate.market.regime,
            safety_state=safety.state,
            data_state=candidate.data_state,
            eligible=eligible,
            slots_authorized=0,
            productivity_score=None,
            decision_reason_codes=(DecisionReasonCode.ELIGIBLE,) if eligible else tuple(reasons),
            policy_config_hash=self.policy.config_hash,
            threshold_config_hash=self.policy.threshold_config_hash,
        )


class EligibilityDecisionLedger:
    def __init__(self) -> None:
        self.decisions: list[EligibilityDecision] = []
        self._decision_ids: set[str] = set()
        self.capital_states: list[CapitalStateRecord] = []

    def append(self, decision: EligibilityDecision) -> None:
        if not decision.decision_reason_codes:
            raise ValueError("M034_DECISION_REASON_REQUIRED")
        if decision.decision_id in self._decision_ids:
            raise ValueError("M034_DUPLICATE_ELIGIBILITY_DECISION")
        self._decision_ids.add(decision.decision_id)
        self.decisions.append(decision)

    def append_capital_state(self, state: CapitalStateRecord) -> None:
        if self.capital_states and state.timestamp_us < self.capital_states[-1].timestamp_us:
            raise ValueError("M034_NONCAUSAL_CAPITAL_STATE")
        self.capital_states.append(state)

    def metrics(self) -> dict[str, object]:
        reason_counts = Counter(
            reason.value
            for decision in self.decisions
            for reason in decision.decision_reason_codes
            if reason != DecisionReasonCode.ELIGIBLE
        )
        return {
            "ELIGIBILITY_ACCEPT_COUNT": sum(decision.eligible for decision in self.decisions),
            "ELIGIBILITY_REJECT_COUNT": sum(not decision.eligible for decision in self.decisions),
            "SLOTS_AUTHORIZED": sum(decision.slots_authorized for decision in self.decisions),
            "REJECTION_REASONS": dict(sorted(reason_counts.items())),
            "CAPITAL_STATE_EVENTS": len(self.capital_states),
            "IDLE_NO_ELIGIBLE_OPPORTUNITY_EVENTS": sum(
                row.state == CapitalState.IDLE_NO_ELIGIBLE_OPPORTUNITY
                for row in self.capital_states
            ),
        }


@dataclass(frozen=True)
class CapitalStateRecord:
    timestamp_us: int
    state: CapitalState
    capital: D
    currency: str
    reason_code: DecisionReasonCode

    def __post_init__(self) -> None:
        if self.timestamp_us < 0 or self.capital < ZERO or not self.currency:
            raise ValueError("M034_INVALID_CAPITAL_STATE")


@dataclass(frozen=True)
class AllocationResult:
    state: AllocationState
    decisions: tuple[EligibilityDecision, ...]
    selected_candidate_ids: tuple[str, ...]


class M034EconomicAllocationEngine:
    """Small integration seam: gate -> canonical scorer -> canonical allocator -> ledger."""

    def __init__(
        self,
        *,
        gate: EconomicEligibilityGate,
        decision_ledger: EligibilityDecisionLedger,
        scorer: PairProductivityScorer | None = None,
        allocator: AdaptiveColumnAllocator | None = None,
    ) -> None:
        self.gate = gate
        self.decision_ledger = decision_ledger
        self.scorer = scorer or PairProductivityScorer()
        self.allocator = allocator or AdaptiveColumnAllocator(self.scorer)

    def evaluate_and_allocate(
        self,
        candidates: list[EconomicCandidate],
        *,
        mode: EvaluationMode,
        available_capital: D,
        available_capital_currency: str,
        now_us: int,
    ) -> AllocationResult:
        if available_capital < ZERO or not available_capital_currency or now_us < 0:
            raise ValueError("M034_INVALID_AVAILABLE_CAPITAL")
        candidate_ids = [candidate.candidate_id for candidate in candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("M034_DUPLICATE_CANDIDATE_ID")
        if any(candidate.decision_time_us != now_us for candidate in candidates):
            raise ValueError("M034_ALLOCATION_TIME_MISMATCH")
        if any(
            candidate.decision_currency != available_capital_currency
            for candidate in candidates
        ):
            raise ValueError("M034_ALLOCATION_CURRENCY_MISMATCH")
        evaluated = [
            (candidate, self.gate.evaluate(candidate, mode=mode)) for candidate in candidates
        ]
        eligible_opportunities: list[EligibleOpportunity] = []
        candidate_by_id = {candidate.candidate_id: candidate for candidate, _ in evaluated}
        for candidate, decision in evaluated:
            if not decision.eligible:
                continue
            assert decision.expected_net_edge_bps is not None
            assert decision.completion_probability is not None
            assert decision.expected_lock_seconds is not None
            eligible_opportunities.append(
                EligibleOpportunity(
                    candidate_id=candidate.candidate_id,
                    priority_class=candidate.priority_class,
                    conditional_complete_net=(
                        candidate.capital_required * decision.expected_net_edge_bps / BPS
                    ),
                    probability_of_completion=decision.completion_probability,
                    conditional_residual_cost=candidate.residual_cost_if_incomplete,
                    tail_risk_cost=candidate.tail_risk_cost,
                    inventory_carry_cost=candidate.inventory_carry_cost,
                    capital_required=candidate.capital_required,
                    expected_lock_seconds=decision.expected_lock_seconds,
                )
            )
        scores = self.scorer.rank_eligible(eligible_opportunities)
        blocked_owned_capital = sum(
            (
                candidate.capital_required
                for candidate, decision in evaluated
                if candidate.intent == DecisionIntent.OWNED_RETURN and not decision.eligible
            ),
            ZERO,
        )
        allocatable_capital = max(available_capital - blocked_owned_capital, ZERO)
        selected = self.allocator.choose_eligible(
            scores, available_capital=allocatable_capital
        )
        score_by_id = {score.candidate_id: score for score in scores}
        selected_ids = {score.candidate_id for score in selected}
        final: list[EligibilityDecision] = []
        for candidate, decision in evaluated:
            score = score_by_id.get(candidate.candidate_id)
            if score is None:
                final_decision = decision
            elif candidate.candidate_id in selected_ids:
                final_decision = replace(
                    decision,
                    slots_authorized=1,
                    productivity_score=score.productivity,
                    decision_reason_codes=(
                        DecisionReasonCode.OWNED_RETURN_PRIORITY
                        if candidate.intent == DecisionIntent.OWNED_RETURN
                        else DecisionReasonCode.ELIGIBLE,
                    ),
                )
            else:
                reason = (
                    DecisionReasonCode.PRODUCTIVITY_NON_POSITIVE
                    if score.productivity <= ZERO
                    else DecisionReasonCode.CAPITAL_UNAVAILABLE
                )
                final_decision = replace(
                    decision,
                    productivity_score=score.productivity,
                    decision_reason_codes=(reason,),
                )
            self.decision_ledger.append(final_decision)
            final.append(final_decision)
        selected_capital = sum((row.capital_required for row in selected), ZERO)
        for row in selected:
            candidate = candidate_by_id[row.candidate_id]
            self.decision_ledger.append_capital_state(
                CapitalStateRecord(
                    timestamp_us=now_us,
                    state=(
                        CapitalState.ACTIVE_OWNED_RETURN
                        if candidate.intent == DecisionIntent.OWNED_RETURN
                        else CapitalState.ACTIVE_NEW_ENTRY
                    ),
                    capital=row.capital_required,
                    currency=available_capital_currency,
                    reason_code=(
                        DecisionReasonCode.CAPITAL_RESERVED_OWNED_RETURN
                        if candidate.intent == DecisionIntent.OWNED_RETURN
                        else DecisionReasonCode.ELIGIBLE
                    ),
                )
            )
        unclassified_capital = available_capital - selected_capital
        locked_owned = min(blocked_owned_capital, unclassified_capital)
        if locked_owned > ZERO:
            self.decision_ledger.append_capital_state(
                CapitalStateRecord(
                    timestamp_us=now_us,
                    state=CapitalState.LOCKED_INVENTORY,
                    capital=locked_owned,
                    currency=available_capital_currency,
                    reason_code=DecisionReasonCode.CAPITAL_LOCKED_INVENTORY,
                )
            )
            unclassified_capital -= locked_owned
        if unclassified_capital > ZERO:
            reason_sets = [set(decision.decision_reason_codes) for _, decision in evaluated]
            data_reasons = {
                DecisionReasonCode.DATA_GAP,
                DecisionReasonCode.DATA_INSUFFICIENT,
                DecisionReasonCode.FEE_UNPROVEN,
                DecisionReasonCode.PAIR_UNAVAILABLE,
                DecisionReasonCode.PAIR_EVIDENCE_UNPROVEN,
                DecisionReasonCode.EXCHANGE_RULE_UNPROVEN,
                DecisionReasonCode.EXCHANGE_RULE_VIOLATION,
                DecisionReasonCode.THRESHOLD_NOT_EFFECTIVE,
            }
            safety_reasons = {
                DecisionReasonCode.MARKET_SAFETY_BLOCK,
                DecisionReasonCode.PEG_RISK,
                DecisionReasonCode.ABNORMAL_SPREAD,
                DecisionReasonCode.LIQUIDITY_COLLAPSE,
                DecisionReasonCode.COMPATIBLE_FLOW_COLLAPSE,
            }
            if any(reasons & data_reasons for reasons in reason_sets):
                remaining_state = CapitalState.BLOCKED_DATA
                remaining_reason = DecisionReasonCode.DATA_INSUFFICIENT
            elif any(reasons & safety_reasons for reasons in reason_sets):
                remaining_state = CapitalState.BLOCKED_SAFETY
                remaining_reason = DecisionReasonCode.MARKET_SAFETY_BLOCK
            elif any(
                candidate.intent == DecisionIntent.OWNED_RETURN
                and candidate.candidate_id not in selected_ids
                for candidate, _ in evaluated
            ):
                remaining_state = CapitalState.LOCKED_INVENTORY
                remaining_reason = DecisionReasonCode.CAPITAL_LOCKED_INVENTORY
            else:
                remaining_state = CapitalState.IDLE_NO_ELIGIBLE_OPPORTUNITY
                remaining_reason = DecisionReasonCode.NO_ELIGIBLE_OPPORTUNITY
            self.decision_ledger.append_capital_state(
                CapitalStateRecord(
                    timestamp_us=now_us,
                    state=remaining_state,
                    capital=unclassified_capital,
                    currency=available_capital_currency,
                    reason_code=remaining_reason,
                )
            )
        state = (
            AllocationState.NO_ELIGIBLE_OPPORTUNITY
            if not selected
            else (
                AllocationState.ALLOCATED
                if len(selected) == len(candidates)
                else AllocationState.PARTIALLY_ALLOCATED
            )
        )
        return AllocationResult(
            state=state,
            decisions=tuple(final),
            selected_candidate_ids=tuple(
                score.candidate_id for score in selected if score.candidate_id in candidate_by_id
            ),
        )


@dataclass(frozen=True)
class AdverseSelectionObservation:
    observation_id: str
    context: str
    fill_time_us: int
    horizon_end_us: int
    observed_at_us: int
    adverse_selection_bps: D

    def __post_init__(self) -> None:
        if (
            not self.observation_id
            or not self.context
            or self.fill_time_us < 0
            or not self.fill_time_us <= self.horizon_end_us <= self.observed_at_us
            or not self.adverse_selection_bps.is_finite()
        ):
            raise ValueError("M034_NONCAUSAL_ADVERSE_SELECTION_OBSERVATION")


class CausalAdverseSelectionEstimator:
    VERSION = "M034_RESOLVED_PREFIX_P95_V1"

    def __init__(self, *, minimum_samples: int, training_cutoff_us: int) -> None:
        if minimum_samples <= 0 or training_cutoff_us < 0:
            raise ValueError("M034_INVALID_ADVERSE_SELECTION_SAMPLE_MINIMUM")
        self.minimum_samples = minimum_samples
        self.training_cutoff_us = training_cutoff_us
        self.observations: dict[str, AdverseSelectionObservation] = {}

    def add(self, observation: AdverseSelectionObservation) -> None:
        if observation.observation_id in self.observations:
            raise ValueError("M034_DUPLICATE_ADVERSE_SELECTION_OBSERVATION")
        self.observations[observation.observation_id] = observation

    def estimate(
        self, *, context: str, now_us: int, feature_cutoff_us: int
    ) -> AdverseSelectionEstimate | None:
        if (
            now_us < 0
            or feature_cutoff_us < 0
            or self.training_cutoff_us > now_us
            or feature_cutoff_us > now_us
        ):
            raise ValueError("M034_ESTIMATOR_CUTOFF_AFTER_DECISION")
        values = sorted(
            max(ZERO, row.adverse_selection_bps)
            for row in self.observations.values()
            if row.context == context and row.observed_at_us <= min(now_us, self.training_cutoff_us)
        )
        if len(values) < self.minimum_samples:
            return None
        index = int(((D(len(values)) - D(1)) * D("0.95")).to_integral_value(rounding=ROUND_CEILING))
        return AdverseSelectionEstimate(
            adverse_selection_bps=values[index],
            sample_count=len(values),
            training_cutoff_us=self.training_cutoff_us,
            feature_cutoff_us=feature_cutoff_us,
            estimator_version=self.VERSION,
        )


@dataclass(frozen=True)
class AdverseSelectionEstimate:
    adverse_selection_bps: D
    sample_count: int
    training_cutoff_us: int
    feature_cutoff_us: int
    estimator_version: str


class FIFOValueEstimator:
    @staticmethod
    def value(
        *, probability_of_completion: D, pnl_if_complete: D, residual_cost_if_incomplete: D
    ) -> D:
        if not ZERO <= probability_of_completion <= D(1) or any(
            value < ZERO for value in (pnl_if_complete, residual_cost_if_incomplete)
        ):
            raise ValueError("M034_INVALID_FIFO_VALUE_INPUT")
        return (
            probability_of_completion * pnl_if_complete
            - (D(1) - probability_of_completion) * residual_cost_if_incomplete
        )


@dataclass(frozen=True)
class ReallocationDecision:
    switch: bool
    value_improvement: D
    switching_cost: D
    reason_code: DecisionReasonCode


class ReallocationDecisionEngine:
    @staticmethod
    def decide(
        *,
        value_new: D,
        value_current: D,
        lost_fifo_value: D,
        cancel_cost: D,
        reentry_cost: D,
    ) -> ReallocationDecision:
        costs = (lost_fifo_value, cancel_cost, reentry_cost)
        if any(value < ZERO for value in costs):
            raise ValueError("M034_NEGATIVE_SWITCHING_COST")
        improvement = value_new - value_current
        switching = sum(costs, ZERO)
        should_switch = improvement > switching
        return ReallocationDecision(
            switch=should_switch,
            value_improvement=improvement,
            switching_cost=switching,
            reason_code=(
                DecisionReasonCode.ELIGIBLE
                if should_switch
                else DecisionReasonCode.FIFO_SWITCHING_COST_TOO_HIGH
            ),
        )


@dataclass(frozen=True)
class InventoryExitRule:
    rule_id: str
    rule_hash: str
    effective_start_us: int
    effective_end_us: int
    provenance: str
    reason_code: DecisionReasonCode

    def __post_init__(self) -> None:
        if (
            self.reason_code
            not in {
                DecisionReasonCode.INVENTORY_LOCK_EXCEEDED,
                DecisionReasonCode.PEG_RISK_ESCALATED,
                DecisionReasonCode.OPPORTUNITY_COST_EXCEEDED,
            }
            or self.effective_end_us <= self.effective_start_us
            or self.effective_start_us < 0
            or not self.rule_hash
            or not self.provenance
        ):
            raise ValueError("M034_INVALID_INVENTORY_EXIT_RULE")


@dataclass(frozen=True)
class InventoryExitAssessment:
    allowed: bool
    reason_code: DecisionReasonCode
    authorization: InventoryReductionAuthorization | None


class InventoryExitDecisionEngine:
    @staticmethod
    def evaluate(
        *,
        authorization_id: str,
        slot_id: str,
        slot_epoch: int,
        quantity: D,
        origin_cost_basis: D,
        inventory_asset: str,
        origin_asset: str,
        exit_reservation_id: str,
        now_us: int,
        expires_at_us: int,
        expected_hold_loss: D,
        opportunity_cost_of_lock: D,
        tail_risk_increase: D,
        realized_loss_of_exit: D,
        rule: InventoryExitRule | None,
    ) -> InventoryExitAssessment:
        if (
            quantity <= ZERO
            or origin_cost_basis <= ZERO
            or realized_loss_of_exit <= ZERO
            or not inventory_asset
            or not origin_asset
            or inventory_asset == origin_asset
            or not exit_reservation_id
            or expires_at_us < now_us
            or any(
                value < ZERO
                for value in (
                    expected_hold_loss,
                    opportunity_cost_of_lock,
                    tail_risk_increase,
                    realized_loss_of_exit,
                )
            )
        ):
            raise ValueError("M034_INVALID_INVENTORY_EXIT_INPUT")
        if rule is None or not rule.effective_start_us <= now_us < rule.effective_end_us:
            return InventoryExitAssessment(
                False, DecisionReasonCode.NEGATIVE_EXIT_NOT_ALLOWED_COSMETIC, None
            )
        hold_cost = expected_hold_loss + opportunity_cost_of_lock + tail_risk_increase
        if hold_cost <= realized_loss_of_exit:
            return InventoryExitAssessment(
                False, DecisionReasonCode.NEGATIVE_EXIT_NOT_ALLOWED_COSMETIC, None
            )
        if expires_at_us > rule.effective_end_us:
            raise ValueError("M034_INVENTORY_EXIT_AUTHORIZATION_EXCEEDS_RULE_WINDOW")
        authorization = InventoryReductionAuthorization(
            authorization_id=authorization_id,
            slot_id=slot_id,
            slot_epoch=slot_epoch,
            quantity=quantity,
            origin_cost_basis=origin_cost_basis,
            inventory_asset=inventory_asset,
            origin_asset=origin_asset,
            exit_reservation_id=exit_reservation_id,
            decided_at_us=now_us,
            expires_at_us=expires_at_us,
            rule_id=rule.rule_id,
            rule_hash=rule.rule_hash,
            reason_code=DecisionReasonCode.NEGATIVE_EXIT_RISK_RULE_TRIGGERED.value,
            trigger_reason_code=rule.reason_code.value,
            expected_hold_loss=expected_hold_loss,
            opportunity_cost_of_lock=opportunity_cost_of_lock,
            tail_risk_increase=tail_risk_increase,
            realized_loss_of_exit=realized_loss_of_exit,
        )
        return InventoryExitAssessment(
            True, DecisionReasonCode.NEGATIVE_EXIT_RISK_RULE_TRIGGERED, authorization
        )


@dataclass(frozen=True)
class BinancePairEvidence:
    book: BookKey
    available: bool
    data_proven: bool
    rules_proven: bool
    safety_acceptable: bool
    liquidity_acceptable: bool
    temporal_provenance: str
    effective_start_us: int
    effective_end_us: int | None

    def __post_init__(self) -> None:
        if (
            self.book.venue != Venue.BINANCE
            or not self.temporal_provenance
            or self.effective_start_us < 0
            or (
                self.effective_end_us is not None
                and self.effective_end_us <= self.effective_start_us
            )
        ):
            raise ValueError("M034_INVALID_PAIR_EVIDENCE")

    @property
    def eligible(self) -> bool:
        return (
            self.available
            and self.data_proven
            and self.rules_proven
            and self.safety_acceptable
            and self.liquidity_acceptable
        )


class BinancePairUniverse:
    """Book existence is descriptive; only complete evidence makes a book eligible."""

    def __init__(self, evidence: list[BinancePairEvidence]) -> None:
        self.evidence = {row.book: row for row in evidence}
        if len(self.evidence) != len(evidence):
            raise ValueError("M034_DUPLICATE_PAIR_EVIDENCE")
        if any(row.book.venue != Venue.BINANCE for row in evidence):
            raise ValueError("M034_PAIR_UNIVERSE_MUST_BE_BINANCE_ONLY")

    def resolve(self, book: BookKey, *, time_us: int) -> BinancePairEvidence | None:
        row = self.evidence.get(book)
        if row is None or time_us < row.effective_start_us or (
            row.effective_end_us is not None and time_us >= row.effective_end_us
        ):
            return None
        return row

    @property
    def available_books(self) -> tuple[BookKey, ...]:
        return tuple(sorted(book for book, row in self.evidence.items() if row.available))

    @property
    def eligible_books(self) -> tuple[BookKey, ...]:
        return tuple(
            sorted(
                book
                for book, row in self.evidence.items()
                if row.eligible
            )
        )


__all__ = [
    "AdverseSelectionEstimate",
    "AdverseSelectionObservation",
    "AllocationResult",
    "AllocationState",
    "BinancePairEvidence",
    "BinancePairUniverse",
    "CapitalState",
    "CapitalStateRecord",
    "CausalAdverseSelectionEstimator",
    "DataState",
    "DatasetRole",
    "DatasetRoleRegistry",
    "DecisionIntent",
    "DecisionReasonCode",
    "EconomicCandidate",
    "EconomicEligibilityGate",
    "EconomicExecutionPolicy",
    "EligibilityDecision",
    "EligibilityDecisionLedger",
    "EvaluationMode",
    "FIFOValueEstimator",
    "FeeLeg",
    "InventoryExitAssessment",
    "InventoryExitDecisionEngine",
    "InventoryExitRule",
    "M034EconomicAllocationEngine",
    "M034Policy",
    "MarketRegimeAssessment",
    "MarketRegimeSafetyGate",
    "MarketRegimeSnapshot",
    "ReallocationDecision",
    "ReallocationDecisionEngine",
    "RuleEvidenceStatus",
    "SafetyState",
    "ThresholdDefinition",
    "ThresholdRecord",
    "ThresholdRegistry",
    "ThresholdSourceType",
    "UnknownCostPolicy",
    "VenuePairFeeRegistry",
    "VenuePairRuleRegistry",
    "VenueSymbolRuleRecord",
]
