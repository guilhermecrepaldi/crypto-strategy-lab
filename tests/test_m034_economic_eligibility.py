from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.economic_eligibility import (
    AdverseSelectionObservation,
    AllocationState,
    BinancePairEvidence,
    BinancePairUniverse,
    CapitalState,
    CausalAdverseSelectionEstimator,
    DatasetRole,
    DatasetRoleRegistry,
    DataState,
    DecisionIntent,
    DecisionReasonCode,
    EconomicCandidate,
    EconomicEligibilityGate,
    EconomicExecutionPolicy,
    EligibilityDecisionLedger,
    EvaluationMode,
    FeeLeg,
    FIFOValueEstimator,
    InventoryExitDecisionEngine,
    InventoryExitRule,
    M034EconomicAllocationEngine,
    M034Policy,
    MarketRegimeSnapshot,
    ReallocationDecisionEngine,
    ThresholdDefinition,
    ThresholdRegistry,
    ThresholdSourceType,
    UnknownCostPolicy,
    VenuePairFeeRegistry,
)
from crypto_strategy_lab.microstructure.multi_stable_ledger import SlotLedger
from crypto_strategy_lab.microstructure.multi_stable_models import PhysicalFill, SlotState
from crypto_strategy_lab.microstructure.multi_stable_queue import (
    CausalCompletionHistory,
    CompletionObservation,
    CompletionProbabilityEstimator,
    ExpectedLockTimeEstimator,
)
from crypto_strategy_lab.microstructure.multi_venue_models import (
    BookKey,
    FeeEvidenceStatus,
    Venue,
    VenueFeeProfile,
)

BINANCE = BookKey(Venue.BINANCE, "USDCUSDT")
KRAKEN = BookKey(Venue.KRAKEN, "USDC/USDT")


def threshold_definitions() -> list[ThresholdDefinition]:
    values = {
        "MIN_COMPLETION_PROBABILITY": ("0.5", "ratio"),
        "MAX_EXPECTED_LOCK_TIME": ("300", "seconds"),
        "RISK_BUFFER": ("1", "bps"),
        "MAX_INVENTORY_EXPOSURE": ("10", "USD"),
        "PEG_DEVIATION_THRESHOLD": ("0.01", "ratio"),
        "MIN_NET_EDGE": ("0.1", "bps"),
        "TAIL_RISK_BOUND": ("1", "USD"),
        "MAX_SPREAD": ("5", "bps"),
        "MIN_DEPTH": ("100", "USD"),
        "MIN_COMPATIBLE_FLOW": ("1", "asset/second"),
    }
    return [
        ThresholdDefinition(
            name=name,
            value=D(value),
            unit=unit,
            source_type=ThresholdSourceType.PROTOCOL_CONSTANT,
            source_reference="M034 synthetic-test fixture",
            derivation_method="deterministic boundary fixture; not an economic parameter",
            calibration_dataset_hash=None,
            effective_from_us=0,
            frozen_at_us=0,
        )
        for name, (value, unit) in values.items()
    ]


def policy() -> M034Policy:
    return M034Policy(
        policy_id="M034_SYNTHETIC_TEST_ONLY",
        provenance="tests/test_m034_economic_eligibility.py",
        thresholds=ThresholdRegistry(threshold_definitions()),
        unknown_cost_policy=UnknownCostPolicy.REJECT,
    )


def execution_policy() -> EconomicExecutionPolicy:
    return EconomicExecutionPolicy(
        frozenset({Venue.BINANCE}),
        "M034_BINANCE_ONLY",
        "test-policy-hash",
        "M034 contract",
    )


def fee_profile(
    *,
    book: BookKey = BINANCE,
    status: FeeEvidenceStatus = FeeEvidenceStatus.PROVEN_HISTORICAL,
    acquired_at_us: int = 200,
) -> VenueFeeProfile:
    return VenueFeeProfile(
        book=book,
        maker_rate=D("0.0001"),
        taker_rate=D("0.0002"),
        fee_asset_semantics="received asset",
        effective_start_us=0,
        effective_end_us=1_000,
        provenance="synthetic test evidence",
        account_tier_assumption="public standard",
        acquired_at_us=acquired_at_us,
        evidence_status=status,
        record_id=f"fee:{book.canonical_id}:{status.value}",
        source_reference="fixture://fee-evidence",
    )


def fee_registry(profile: VenueFeeProfile | None = None) -> VenuePairFeeRegistry:
    registry = VenuePairFeeRegistry()
    registry.add(profile or fee_profile())
    return registry


def gate(registry: VenuePairFeeRegistry | None = None) -> EconomicEligibilityGate:
    return EconomicEligibilityGate(
        execution_policy=execution_policy(),
        policy=policy(),
        fee_registry=registry or fee_registry(),
    )


def candidate(candidate_id: str = "A", **changes: object) -> EconomicCandidate:
    row = EconomicCandidate(
        candidate_id=candidate_id,
        venue=Venue.BINANCE,
        pair=BINANCE,
        side="BUY",
        rank=1,
        column=1,
        route_id="USDT->USDC->USDT",
        inventory_state="FLAT",
        intent=DecisionIntent.NEW_ENTRY,
        priority_class=2,
        decision_currency="USDT",
        decision_time_us=100,
        gross_edge_bps=D("10"),
        execution_cost_bps=D("1"),
        adverse_selection_bps=D("1"),
        completion_probability=D("0.8"),
        expected_lock_seconds=D("60"),
        p95_lock_seconds=D("120"),
        capital_required=D("5"),
        residual_cost_if_incomplete=D("0.0001"),
        tail_risk_cost=D("0.0001"),
        inventory_carry_cost=D("0.0001"),
        fee_legs=(FeeLeg(BINANCE, True), FeeLeg(BINANCE, True)),
        market=MarketRegimeSnapshot(
            observed_at_us=100,
            regime="NORMAL",
            peg_deviation=D("0.001"),
            spread_bps=D("1"),
            depth_usd=D("1000"),
            compatible_flow_per_second=D("10"),
        ),
        data_state=DataState.VALID,
    )
    return replace(row, **changes)


def allocate(rows: list[EconomicCandidate], *, capital: str = "5") -> tuple[object, object]:
    ledger = EligibilityDecisionLedger()
    engine = M034EconomicAllocationEngine(gate=gate(), decision_ledger=ledger)
    result = engine.evaluate_and_allocate(
        rows,
        mode=EvaluationMode.HISTORICAL_REPLAY,
        available_capital=D(capital),
        now_us=100,
    )
    return result, ledger


def test_fee_unproven_is_ineligible_and_authorizes_zero_slots() -> None:
    registry = fee_registry(fee_profile(status=FeeEvidenceStatus.UNPROVEN))
    decision = gate(registry).evaluate(candidate(), mode=EvaluationMode.HISTORICAL_REPLAY)
    assert not decision.eligible and decision.slots_authorized == 0
    assert DecisionReasonCode.FEE_UNPROVEN in decision.decision_reason_codes


def test_gross_edge_not_above_economic_costs_authorizes_zero_slots() -> None:
    decision = gate().evaluate(
        candidate(gross_edge_bps=D("5")), mode=EvaluationMode.HISTORICAL_REPLAY
    )
    assert not decision.eligible and DecisionReasonCode.EDGE_BELOW_MINIMUM in (
        decision.decision_reason_codes
    )


def test_low_completion_probability_authorizes_zero_slots() -> None:
    decision = gate().evaluate(
        candidate(completion_probability=D("0.49")), mode=EvaluationMode.HISTORICAL_REPLAY
    )
    assert DecisionReasonCode.COMPLETION_PROBABILITY_TOO_LOW in decision.decision_reason_codes


def test_excessive_expected_lock_authorizes_zero_slots() -> None:
    decision = gate().evaluate(
        candidate(expected_lock_seconds=D("301")), mode=EvaluationMode.HISTORICAL_REPLAY
    )
    assert DecisionReasonCode.EXPECTED_LOCK_TOO_HIGH in decision.decision_reason_codes


def test_abnormal_peg_blocks_market_and_slots() -> None:
    market = replace(candidate().market, peg_deviation=D("0.02"))
    decision = gate().evaluate(candidate(market=market), mode=EvaluationMode.HISTORICAL_REPLAY)
    assert DecisionReasonCode.PEG_RISK in decision.decision_reason_codes
    assert DecisionReasonCode.MARKET_SAFETY_BLOCK in decision.decision_reason_codes


def test_data_gap_and_invalid_data_fail_closed() -> None:
    market = replace(candidate().market, data_gap=True)
    decision = gate().evaluate(
        candidate(market=market, data_state=DataState.INVALID),
        mode=EvaluationMode.HISTORICAL_REPLAY,
    )
    assert DecisionReasonCode.DATA_GAP in decision.decision_reason_codes
    assert DecisionReasonCode.DATA_INSUFFICIENT in decision.decision_reason_codes


def test_eligible_opportunity_enters_productivity_ranking() -> None:
    result, ledger = allocate([candidate()])
    assert result.state == AllocationState.ALLOCATED
    assert result.selected_candidate_ids == ("A",)
    assert ledger.decisions[0].productivity_score is not None
    assert ledger.decisions[0].slots_authorized == 1


def test_higher_productivity_wins_for_same_priority() -> None:
    slow = candidate("SLOW", expected_lock_seconds=D("120"))
    fast = candidate("FAST", expected_lock_seconds=D("30"))
    result, _ = allocate([slow, fast], capital="5")
    assert result.selected_candidate_ids == ("FAST",)


def test_owned_return_priority_prevents_new_entry_from_taking_capital() -> None:
    owned = candidate(
        "OWNED",
        intent=DecisionIntent.OWNED_RETURN,
        priority_class=1,
        expected_lock_seconds=D("200"),
    )
    new = candidate("NEW", expected_lock_seconds=D("10"))
    result, ledger = allocate([new, owned], capital="5")
    assert result.selected_candidate_ids == ("OWNED",)
    selected = next(row for row in ledger.decisions if row.candidate_id == "OWNED")
    assert selected.decision_reason_codes == (DecisionReasonCode.OWNED_RETURN_PRIORITY,)


def test_fifo_switching_cost_is_outside_opportunity_value() -> None:
    current = FIFOValueEstimator.value(
        probability_of_completion=D("0.8"),
        pnl_if_complete=D("1"),
        residual_cost_if_incomplete=D("0.1"),
    )
    decision = ReallocationDecisionEngine.decide(
        value_new=current + D("0.05"),
        value_current=current,
        lost_fifo_value=D("0.04"),
        cancel_cost=D("0.01"),
        reentry_cost=D("0.01"),
    )
    assert not decision.switch
    assert decision.reason_code == DecisionReasonCode.FIFO_SWITCHING_COST_TOO_HIGH


def test_cancel_request_keeps_capital_reserved_until_ack() -> None:
    ledger = SlotLedger({"USDT": "10"}, marks_usd={"USDT": "1"})
    ledger.create_slot("S", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    ledger.reserve_free("S", "R", asset="USDT", quantity=D("5"), now_us=1)
    ledger.activate("R", now_us=1)
    ledger.request_cancel("R", now_us=2)
    assert ledger.free["USDT"] == D("5")
    assert ledger.slots["S"].state == SlotState.CANCEL_PENDING


def test_cancel_ack_returns_only_then_available_capital() -> None:
    ledger = SlotLedger({"USDT": "10"}, marks_usd={"USDT": "1"})
    ledger.create_slot("S", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    ledger.reserve_free("S", "R", asset="USDT", quantity=D("5"), now_us=1)
    ledger.activate("R", now_us=1)
    ledger.request_cancel("R", now_us=2)
    assert ledger.acknowledge_cancel("R", now_us=3) == D("5")
    assert ledger.free["USDT"] == D("10")


def test_negative_exit_without_preregistered_risk_rule_is_cosmetic_and_rejected() -> None:
    result = InventoryExitDecisionEngine.evaluate(
        authorization_id="X",
        slot_id="S",
        slot_epoch=1,
        quantity=D("5"),
        now_us=5,
        expires_at_us=6,
        expected_hold_loss=D("1"),
        opportunity_cost_of_lock=D("1"),
        tail_risk_increase=D("1"),
        realized_loss_of_exit=D("0.1"),
        rule=None,
    )
    assert not result.allowed and result.authorization is None
    assert result.reason_code == DecisionReasonCode.NEGATIVE_EXIT_NOT_ALLOWED_COSMETIC


def test_negative_exit_risk_rule_requires_true_inequality_and_is_not_a_cycle() -> None:
    rule = InventoryExitRule(
        "PEG-RISK-1",
        "rule-hash",
        0,
        10,
        "synthetic preregistration",
        DecisionReasonCode.PEG_RISK_ESCALATED,
    )
    assessment = InventoryExitDecisionEngine.evaluate(
        authorization_id="REDUCE-1",
        slot_id="S",
        slot_epoch=1,
        quantity=D("5"),
        now_us=5,
        expires_at_us=6,
        expected_hold_loss=D("0.2"),
        opportunity_cost_of_lock=D("0.1"),
        tail_risk_increase=D("0.1"),
        realized_loss_of_exit=D("0.1"),
        rule=rule,
    )
    assert assessment.allowed and assessment.authorization is not None
    ledger = SlotLedger({"USDT": "10", "USDC": "0"}, marks_usd={"USDT": "1", "USDC": "1"})
    ledger.create_slot("S", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    ledger.reserve_free("S", "ENTRY", asset="USDT", quantity=D("5"), now_us=1)
    ledger.activate("ENTRY", now_us=1)
    ledger.apply_fill(
        "ENTRY", PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("4.9"), "USDC", D("0"), 2)
    )
    ledger.reserve_owned("S", "RETURN", asset="USDC", quantity=D("4.9"), now_us=3)
    ledger.activate("RETURN", now_us=3)
    ledger.apply_fill(
        "RETURN",
        PhysicalFill("F2", "USDCUSDT", "USDC", "USDT", D("4.9"), D("4.9"), "USDT", D("0"), 4),
    )
    assert ledger.settle_inventory_reduction(
        "S",
        origin_quantity=D("5"),
        now_us=5,
        reduction_id="REDUCE-1",
        authorization=assessment.authorization,
    ) == D("-0.1")
    assert ledger.turnover_metrics()["COMPLETED_SLOTS"] == 0
    assert ledger.negative_exit_count == 1


def test_kraken_candidate_is_dormant_for_m034_economics() -> None:
    registry = fee_registry(fee_profile(book=KRAKEN))
    row = candidate(
        venue=Venue.KRAKEN,
        pair=KRAKEN,
        fee_legs=(FeeLeg(KRAKEN, True), FeeLeg(KRAKEN, True)),
    )
    decision = gate(registry).evaluate(row, mode=EvaluationMode.HISTORICAL_REPLAY)
    assert not decision.eligible and decision.slots_authorized == 0
    assert DecisionReasonCode.VENUE_DISABLED_FOR_ECONOMIC_EXECUTION in (
        decision.decision_reason_codes
    )


def test_future_observations_cannot_change_completion_lock_or_adverse_decision_at_t() -> None:
    history = CausalCompletionHistory()
    history.add(CompletionObservation("PAST", "CTX", 0, 50, 300, True, D("30")))
    completion = CompletionProbabilityEstimator(
        history, minimum_samples=1, training_cutoff_us=100, horizon_seconds=300
    )
    lock = ExpectedLockTimeEstimator(
        history, minimum_samples=1, training_cutoff_us=100, horizon_seconds=300
    )
    before = (
        completion.estimate(context="CTX", now_us=100, feature_cutoff_us=100),
        lock.estimate(context="CTX", now_us=100, feature_cutoff_us=100),
    )
    history.add(CompletionObservation("FUTURE", "CTX", 101, 200, 300, False, D("999")))
    after = (
        completion.estimate(context="CTX", now_us=100, feature_cutoff_us=100),
        lock.estimate(context="CTX", now_us=100, feature_cutoff_us=100),
    )
    assert before == after
    adverse = CausalAdverseSelectionEstimator(minimum_samples=1, training_cutoff_us=100)
    adverse.add(AdverseSelectionObservation("PAST", "CTX", 1, 2, 50, D("1")))
    first = adverse.estimate(context="CTX", now_us=100, feature_cutoff_us=100)
    adverse.add(AdverseSelectionObservation("FUTURE", "CTX", 101, 150, 200, D("99")))
    assert adverse.estimate(context="CTX", now_us=100, feature_cutoff_us=100) == first


def test_forward_fee_cannot_validate_historical_replay() -> None:
    registry = fee_registry(fee_profile(status=FeeEvidenceStatus.PROVEN_FORWARD, acquired_at_us=50))
    decision = gate(registry).evaluate(candidate(), mode=EvaluationMode.HISTORICAL_REPLAY)
    assert DecisionReasonCode.FEE_UNPROVEN in decision.decision_reason_codes


def test_missing_economic_cost_never_becomes_zero() -> None:
    decision = gate().evaluate(
        candidate(execution_cost_bps=None, adverse_selection_bps=None),
        mode=EvaluationMode.HISTORICAL_REPLAY,
    )
    assert decision.execution_cost_bps is None and decision.adverse_selection_bps is None
    assert DecisionReasonCode.EXECUTION_COST_UNKNOWN in decision.decision_reason_codes
    assert DecisionReasonCode.ADVERSE_SELECTION_UNKNOWN in decision.decision_reason_codes


def test_same_input_state_produces_identical_decision() -> None:
    first = gate().evaluate(candidate(), mode=EvaluationMode.HISTORICAL_REPLAY)
    second = gate().evaluate(candidate(), mode=EvaluationMode.HISTORICAL_REPLAY)
    assert first == second


def test_threshold_without_complete_provenance_fails_validation() -> None:
    with pytest.raises(ValueError, match="THRESHOLD_PROVENANCE_REQUIRED"):
        ThresholdDefinition(
            "X",
            D("1"),
            "bps",
            ThresholdSourceType.PROTOCOL_CONSTANT,
            "",
            "fixture",
            None,
            0,
            0,
        )
    with pytest.raises(ValueError, match="THRESHOLD_SET_INCOMPLETE"):
        ThresholdRegistry(threshold_definitions()[:-1])


def test_threshold_records_share_reproducible_config_hash() -> None:
    first = ThresholdRegistry(threshold_definitions())
    second = ThresholdRegistry(list(reversed(threshold_definitions())))
    assert first.config_hash == second.config_hash
    assert {record.config_hash for record in first.records} == {first.config_hash}


def test_calibration_dataset_cannot_be_reported_as_oos_validation() -> None:
    roles = DatasetRoleRegistry()
    roles.register("dataset-hash", DatasetRole.CALIBRATION)
    with pytest.raises(ValueError, match="CALIBRATION_DATASET_CANNOT_BE_OOS"):
        roles.register("dataset-hash", DatasetRole.VALIDATION_OOS)


def test_no_eligible_candidate_records_idle_and_reason() -> None:
    ledger = EligibilityDecisionLedger()
    engine = M034EconomicAllocationEngine(gate=gate(), decision_ledger=ledger)
    result = engine.evaluate_and_allocate(
        [],
        mode=EvaluationMode.HISTORICAL_REPLAY,
        available_capital=D("5"),
        now_us=100,
    )
    assert result.state == AllocationState.NO_ELIGIBLE_OPPORTUNITY
    assert ledger.capital_states[0].state == CapitalState.IDLE_NO_ELIGIBLE_OPPORTUNITY
    assert ledger.capital_states[0].reason_code == DecisionReasonCode.NO_ELIGIBLE_OPPORTUNITY


def test_every_logged_decision_has_reason_code() -> None:
    result, ledger = allocate([candidate(), candidate("BLOCKED", execution_cost_bps=None)])
    assert result.decisions
    assert all(decision.decision_reason_codes for decision in ledger.decisions)
    assert ledger.metrics()["SLOTS_AUTHORIZED"] == 1


def test_available_binance_pair_is_not_automatically_eligible() -> None:
    universe = BinancePairUniverse(
        [
            BinancePairEvidence(BINANCE, True, False, True, True, True, "evidence"),
            BinancePairEvidence(
                BookKey(Venue.BINANCE, "FDUSDUSDT"), True, True, True, True, True, "evidence"
            ),
        ]
    )
    assert BINANCE in universe.available_books and BINANCE not in universe.eligible_books
