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
    CausalAssetMarkRegistry,
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
    CausalAssetMark,
    InventoryReductionAuthorization,
    PhysicalFill,
    SlotState,
)
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
    VenueRoute,
    VenueRouteLeg,
    VenueSymbolRule,
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


def policy(
    *,
    definitions: list[ThresholdDefinition] | None = None,
    unknown_cost_policy: UnknownCostPolicy = UnknownCostPolicy.REJECT,
) -> M034Policy:
    return M034Policy(
        policy_id="M034_SYNTHETIC_TEST_ONLY",
        provenance="tests/test_m034_economic_eligibility.py",
        thresholds=ThresholdRegistry(definitions or threshold_definitions()),
        unknown_cost_policy=unknown_cost_policy,
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
        fee_asset_semantics="RECEIVED_ASSET",
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


def rule_registry() -> VenuePairRuleRegistry:
    registry = VenuePairRuleRegistry()
    registry.add(
        VenueSymbolRuleRecord(
            rule=VenueSymbolRule(
                book=BINANCE,
                base_asset="USDC",
                quote_asset="USDT",
                tick_size=D("0.0001"),
                quantity_step=D("0.1"),
                minimum_quantity=D("0.1"),
                minimum_notional=D("5"),
                price_precision=4,
                effective_start_us=0,
                effective_end_us=1_000,
                provenance="synthetic historical rule fixture",
            ),
            evidence_status=RuleEvidenceStatus.PROVEN_HISTORICAL,
            acquired_at_us=200,
            record_id="rule:BINANCE:USDCUSDT:historical",
            source_reference="fixture://rule-evidence",
        )
    )
    return registry


def pair_universe(*, eligible: bool = True) -> BinancePairUniverse:
    return BinancePairUniverse(
        [
            BinancePairEvidence(
                BINANCE,
                True,
                eligible,
                eligible,
                eligible,
                eligible,
                "synthetic temporal pair evidence",
                0,
                1_000,
            )
        ]
    )


def mark_registry(*, rate: str = "1", observed_at_us: int = 90) -> CausalAssetMarkRegistry:
    registry = CausalAssetMarkRegistry()
    registry.add(
        CausalAssetMark(
            "USDT",
            "USD",
            D(rate),
            observed_at_us,
            100,
            "mark:USDT:USD:100",
            "fixture://mark",
            "synthetic causal mark",
        )
    )
    return registry


def gate(
    registry: VenuePairFeeRegistry | None = None,
    *,
    active_policy: M034Policy | None = None,
    rules: VenuePairRuleRegistry | None = None,
    universe: BinancePairUniverse | None = None,
    marks: CausalAssetMarkRegistry | None = None,
) -> EconomicEligibilityGate:
    return EconomicEligibilityGate(
        execution_policy=execution_policy(),
        policy=active_policy or policy(),
        fee_registry=registry or fee_registry(),
        rule_registry=rules or rule_registry(),
        pair_universe=universe or pair_universe(),
        mark_registry=marks or mark_registry(),
    )


def candidate(candidate_id: str = "A", **changes: object) -> EconomicCandidate:
    route = VenueRoute(
        "USDT->USDC->USDT",
        "USDT",
        (
            VenueRouteLeg(BINANCE, "USDT", "USDC", True),
            VenueRouteLeg(BINANCE, "USDC", "USDT", True),
        ),
    )
    row = EconomicCandidate(
        candidate_id=candidate_id,
        venue=Venue.BINANCE,
        pair=BINANCE,
        side="BUY",
        rank=1,
        column=1,
        route_id="USDT->USDC->USDT",
        route=route,
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
        fee_legs=(
            FeeLeg(BINANCE, True, "USDT", "USDC", "BUY", D("1.0000"), D("5.0")),
            FeeLeg(BINANCE, True, "USDC", "USDT", "SELL", D("1.0000"), D("5.0")),
        ),
        market=MarketRegimeSnapshot(
            observed_at_us=100,
            regime="NORMAL",
            peg_deviation=D("0.001"),
            spread_bps=D("1"),
            depth_usd=D("1000"),
            compatible_flow_per_second=D("10"),
        ),
        data_state=DataState.VALID,
        account_context="public standard",
    )
    return replace(row, **changes)


def allocate(rows: list[EconomicCandidate], *, capital: str = "5") -> tuple[object, object]:
    ledger = EligibilityDecisionLedger()
    engine = M034EconomicAllocationEngine(gate=gate(), decision_ledger=ledger)
    result = engine.evaluate_and_allocate(
        rows,
        mode=EvaluationMode.HISTORICAL_REPLAY,
        available_capital=D(capital),
        available_capital_currency="USDT",
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
        origin_cost_basis=D("5"),
        inventory_asset="USDC",
        origin_asset="USDT",
        exit_reservation_id="RETURN",
        external_fee_marks=(),
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
        20,
        "synthetic preregistration",
        DecisionReasonCode.PEG_RISK_ESCALATED,
    )
    assessment = InventoryExitDecisionEngine.evaluate(
        authorization_id="REDUCE-1",
        slot_id="S",
        slot_epoch=1,
        quantity=D("4.9"),
        origin_cost_basis=D("5"),
        inventory_asset="USDC",
        origin_asset="USDT",
        exit_reservation_id="RETURN",
        external_fee_marks=(),
        now_us=3,
        expires_at_us=10,
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
    ledger.register_inventory_reduction_authorization(assessment.authorization, now_us=3)
    ledger.reserve_owned("S", "RETURN", asset="USDC", quantity=D("4.9"), now_us=4)
    ledger.activate("RETURN", now_us=4)
    ledger.apply_fill(
        "RETURN",
        PhysicalFill("F2", "USDCUSDT", "USDC", "USDT", D("4.9"), D("4.9"), "USDT", D("0"), 5),
    )
    assert ledger.settle_inventory_reduction(
        "S",
        now_us=6,
        reduction_id="REDUCE-1",
        authorization=assessment.authorization,
    ) == D("-0.1")
    assert ledger.turnover_metrics()["COMPLETED_SLOTS"] == 0
    assert ledger.negative_exit_count == 1


def test_kraken_candidate_is_dormant_for_m034_economics() -> None:
    registry = fee_registry(fee_profile(book=KRAKEN))
    kraken_route = VenueRoute(
        "USDT->USDC->USDT",
        "USDT",
        (
            VenueRouteLeg(KRAKEN, "USDT", "USDC", True),
            VenueRouteLeg(KRAKEN, "USDC", "USDT", True),
        ),
    )
    row = candidate(
        "KRAKEN",
        venue=Venue.KRAKEN,
        pair=KRAKEN,
        route=kraken_route,
        fee_legs=(
            FeeLeg(KRAKEN, True, "USDT", "USDC", "BUY", D("1"), D("5")),
            FeeLeg(KRAKEN, True, "USDC", "USDT", "SELL", D("1"), D("5")),
        ),
    )
    decision = gate(registry).evaluate(row, mode=EvaluationMode.HISTORICAL_REPLAY)
    assert not decision.eligible and decision.slots_authorized == 0
    assert DecisionReasonCode.VENUE_DISABLED_FOR_ECONOMIC_EXECUTION in (
        decision.decision_reason_codes
    )
    ledger = EligibilityDecisionLedger()
    ledger.append(gate().evaluate(candidate("BINANCE"), mode=EvaluationMode.HISTORICAL_REPLAY))
    ledger.append(decision)
    assert ledger.metrics()["ELIGIBILITY_ACCEPT_COUNT"] == 1
    assert ledger.metrics()["ELIGIBILITY_REJECT_COUNT"] == 0
    assert ledger.metrics()["DORMANT_VENUE_DIAGNOSTIC_COUNT"] == 1


def test_future_observations_cannot_change_completion_lock_or_adverse_decision_at_t() -> None:
    history = CausalCompletionHistory()
    history.add(CompletionObservation("PAST", "CTX", 0, 30_000_000, 300, True, D("30")))
    completion = CompletionProbabilityEstimator(
        history, minimum_samples=1, training_cutoff_us=100_000_000, horizon_seconds=300
    )
    lock = ExpectedLockTimeEstimator(
        history, minimum_samples=1, training_cutoff_us=100_000_000, horizon_seconds=300
    )
    before = (
        completion.estimate(context="CTX", now_us=100_000_000, feature_cutoff_us=100_000_000),
        lock.estimate(context="CTX", now_us=100_000_000, feature_cutoff_us=100_000_000),
    )
    history.add(
        CompletionObservation("FUTURE", "CTX", 101_000_000, 401_000_000, 300, False, D("300"))
    )
    after = (
        completion.estimate(context="CTX", now_us=100_000_000, feature_cutoff_us=100_000_000),
        lock.estimate(context="CTX", now_us=100_000_000, feature_cutoff_us=100_000_000),
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
        available_capital_currency="USDT",
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
            BinancePairEvidence(BINANCE, True, False, True, True, True, "evidence", 0, 1_000),
            BinancePairEvidence(
                BookKey(Venue.BINANCE, "FDUSDUSDT"),
                True,
                True,
                True,
                True,
                True,
                "evidence",
                0,
                1_000,
            ),
        ]
    )
    assert BINANCE in universe.available_books and BINANCE not in universe.eligible_books


def test_owned_return_with_negative_productivity_remains_selected() -> None:
    owned = candidate(
        "OWNED",
        intent=DecisionIntent.OWNED_RETURN,
        priority_class=1,
        residual_cost_if_incomplete=D("10"),
    )
    result, ledger = allocate([owned])
    assert result.selected_candidate_ids == ("OWNED",)
    assert ledger.decisions[0].productivity_score is not None
    assert ledger.decisions[0].productivity_score < 0


def test_ineligible_owned_return_reserves_capital_before_new_entry() -> None:
    owned = candidate(
        "OWNED",
        intent=DecisionIntent.OWNED_RETURN,
        priority_class=1,
        expected_lock_seconds=D("301"),
    )
    result, ledger = allocate([owned, candidate("NEW")])
    assert result.selected_candidate_ids == ()
    assert ledger.capital_states[0].state == CapitalState.LOCKED_INVENTORY


def test_owned_return_shortfall_stops_lower_priority_allocation() -> None:
    owned = candidate(
        "OWNED",
        intent=DecisionIntent.OWNED_RETURN,
        priority_class=1,
        capital_required=D("6"),
    )
    new = candidate("NEW")
    result, ledger = allocate([owned, new], capital="5")
    assert result.selected_candidate_ids == ()
    assert ledger.capital_states[0].state == CapitalState.LOCKED_INVENTORY


def test_inventory_reduction_requires_physical_return_to_origin() -> None:
    rule = InventoryExitRule(
        "PEG-RISK-1",
        "rule-hash",
        0,
        20,
        "synthetic preregistration",
        DecisionReasonCode.PEG_RISK_ESCALATED,
    )
    ledger = SlotLedger({"USDT": "10", "USDC": "0"}, marks_usd={"USDT": "1", "USDC": "1"})
    ledger.create_slot("S", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    ledger.reserve_free("S", "ENTRY", asset="USDT", quantity=D("5"), now_us=1)
    ledger.activate("ENTRY", now_us=1)
    ledger.apply_fill(
        "ENTRY",
        PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("5"), "USDC", D("0"), 2),
    )
    assessment = InventoryExitDecisionEngine.evaluate(
        authorization_id="REDUCE-NO-RETURN",
        slot_id="S",
        slot_epoch=1,
        quantity=D("5"),
        origin_cost_basis=D("5"),
        inventory_asset="USDC",
        origin_asset="USDT",
        exit_reservation_id="RETURN",
        external_fee_marks=(),
        now_us=3,
        expires_at_us=10,
        expected_hold_loss=D("6"),
        opportunity_cost_of_lock=D("0"),
        tail_risk_increase=D("0"),
        realized_loss_of_exit=D("5"),
        rule=rule,
    )
    assert assessment.authorization is not None
    ledger.register_inventory_reduction_authorization(assessment.authorization, now_us=3)
    with pytest.raises(ValueError, match="PHYSICAL_EXIT_UNPROVEN"):
        ledger.settle_inventory_reduction(
            "S",
            now_us=4,
            reduction_id="REDUCE-NO-RETURN",
            authorization=assessment.authorization,
        )
    assert ledger.owned["S"]["USDC"] == D("5")
    assert ledger.slots["S"].state != SlotState.CLOSED


def test_inventory_reduction_authorization_cannot_be_retroactive() -> None:
    ledger = SlotLedger({"USDT": "10", "USDC": "0"}, marks_usd={"USDT": "1", "USDC": "1"})
    ledger.create_slot("S", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    ledger.reserve_free("S", "ENTRY", asset="USDT", quantity=D("5"), now_us=1)
    ledger.activate("ENTRY", now_us=1)
    ledger.apply_fill(
        "ENTRY",
        PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("4.9"), "USDC", D("0"), 2),
    )
    ledger.reserve_owned("S", "RETURN", asset="USDC", quantity=D("4.9"), now_us=3)
    ledger.activate("RETURN", now_us=3)
    ledger.apply_fill(
        "RETURN",
        PhysicalFill("F2", "USDCUSDT", "USDC", "USDT", D("4.9"), D("4.9"), "USDT", D("0"), 4),
    )
    authorization = InventoryReductionAuthorization(
        authorization_id="RETRO",
        slot_id="S",
        slot_epoch=1,
        quantity=D("4.9"),
        origin_cost_basis=D("5"),
        inventory_asset="USDC",
        origin_asset="USDT",
        exit_reservation_id="RETURN",
        external_fee_marks=(),
        decided_at_us=5,
        expires_at_us=10,
        rule_id="LATE-RULE",
        rule_hash="late-rule-hash",
        reason_code=DecisionReasonCode.NEGATIVE_EXIT_RISK_RULE_TRIGGERED.value,
        trigger_reason_code=DecisionReasonCode.PEG_RISK_ESCALATED.value,
        expected_hold_loss=D("0.2"),
        opportunity_cost_of_lock=D("0.1"),
        tail_risk_increase=D("0.1"),
        realized_loss_of_exit=D("0.1"),
    )
    with pytest.raises(ValueError, match="INVALID_INVENTORY_REDUCTION_REGISTRATION"):
        ledger.register_inventory_reduction_authorization(authorization, now_us=5)


def test_negative_conservative_cost_bound_is_rejected() -> None:
    definitions = threshold_definitions() + [
        ThresholdDefinition(
            name=name,
            value=D("-100"),
            unit="bps",
            source_type=ThresholdSourceType.SAFETY_BOUND,
            source_reference="synthetic invalid bound",
            derivation_method="adversarial fixture",
            calibration_dataset_hash=None,
            effective_from_us=0,
            frozen_at_us=0,
        )
        for name in (
            "UNKNOWN_EXECUTION_COST_BOUND",
            "UNKNOWN_ADVERSE_SELECTION_BOUND",
        )
    ]
    with pytest.raises(ValueError, match="INVALID_CONSERVATIVE_COST_BOUND"):
        policy(
            definitions=definitions,
            unknown_cost_policy=UnknownCostPolicy.CONSERVATIVE_BOUND,
        )


def test_historical_fee_requires_matching_tier_context() -> None:
    mismatched = replace(fee_profile(), account_tier_assumption="vip9")
    decision = gate(fee_registry(mismatched)).evaluate(
        candidate(), mode=EvaluationMode.HISTORICAL_REPLAY
    )
    assert DecisionReasonCode.FEE_UNPROVEN in decision.decision_reason_codes
    with pytest.raises(ValueError):
        replace(fee_profile(), fee_asset_semantics="")


def test_pair_universe_and_historical_rule_are_admission_gates() -> None:
    unavailable = gate(universe=pair_universe(eligible=False)).evaluate(
        candidate(), mode=EvaluationMode.HISTORICAL_REPLAY
    )
    assert DecisionReasonCode.PAIR_EVIDENCE_UNPROVEN in unavailable.decision_reason_codes
    forward_rules = VenuePairRuleRegistry()
    forward_rules.add(
        replace(
            rule_registry()._records[0],
            evidence_status=RuleEvidenceStatus.PROVEN_FORWARD,
        )
    )
    no_historical_rule = gate(rules=forward_rules).evaluate(
        candidate(), mode=EvaluationMode.HISTORICAL_REPLAY
    )
    assert DecisionReasonCode.EXCHANGE_RULE_UNPROVEN in no_historical_rule.decision_reason_codes


def test_future_effective_threshold_blocks_past_decision() -> None:
    future = [replace(row, effective_from_us=1_000_000) for row in threshold_definitions()]
    decision = gate(active_policy=policy(definitions=future)).evaluate(
        candidate(), mode=EvaluationMode.HISTORICAL_REPLAY
    )
    assert DecisionReasonCode.THRESHOLD_NOT_EFFECTIVE in decision.decision_reason_codes
    assert not decision.eligible


def test_allocation_rejects_mixed_currency_without_causal_conversion() -> None:
    ledger = EligibilityDecisionLedger()
    engine = M034EconomicAllocationEngine(gate=gate(), decision_ledger=ledger)
    with pytest.raises(ValueError, match="ALLOCATION_CURRENCY_MISMATCH"):
        engine.evaluate_and_allocate(
            [candidate(decision_currency="EUR")],
            mode=EvaluationMode.HISTORICAL_REPLAY,
            available_capital=D("5"),
            available_capital_currency="USDT",
            now_us=100,
        )


def test_data_gap_capital_is_blocked_data_not_idle() -> None:
    row = candidate(market=replace(candidate().market, data_gap=True))
    result, ledger = allocate([row])
    assert result.selected_candidate_ids == ()
    assert ledger.capital_states[0].state == CapitalState.BLOCKED_DATA


def test_unknown_estimators_block_capital_as_data_not_idle() -> None:
    row = candidate(
        execution_cost_bps=None,
        adverse_selection_bps=None,
        completion_probability=None,
        expected_lock_seconds=None,
    )
    result, ledger = allocate([row])
    assert result.selected_candidate_ids == ()
    assert ledger.capital_states[0].state == CapitalState.BLOCKED_DATA
    assert ledger.capital_states[0].reason_code == DecisionReasonCode.DATA_INSUFFICIENT


def test_censored_observation_is_not_exact_lock_duration() -> None:
    history = CausalCompletionHistory()
    history.add(CompletionObservation("DONE", "CTX", 0, 30_000_000, 300, True, D("30")))
    history.add(CompletionObservation("CENSORED", "CTX", 0, 300_000_000, 300, False, D("300")))
    estimator = ExpectedLockTimeEstimator(
        history, minimum_samples=1, training_cutoff_us=300_000_000, horizon_seconds=300
    )
    estimate = estimator.estimate(context="CTX", now_us=300_000_000, feature_cutoff_us=300_000_000)
    assert estimate is None
    with pytest.raises(ValueError, match="INVALID_COMPLETION_OBSERVATION"):
        CompletionObservation("IMPOSSIBLE", "CTX", 0, 1, 300, True, D("299"))


def test_ambiguous_fee_is_logged_as_unproven_not_raised() -> None:
    registry = fee_registry()
    registry.add(
        replace(
            fee_profile(),
            maker_rate=D("0.0002"),
            record_id="fee:BINANCE:USDCUSDT:historical:second",
        )
    )
    decision = gate(registry).evaluate(candidate(), mode=EvaluationMode.HISTORICAL_REPLAY)
    assert not decision.eligible
    assert DecisionReasonCode.FEE_UNPROVEN in decision.decision_reason_codes


def test_order_funding_must_cover_the_first_physical_leg() -> None:
    row = candidate()
    oversized_first = replace(row.fee_legs[0], quantity=D("1000"))
    decision = gate().evaluate(
        replace(row, fee_legs=(oversized_first, row.fee_legs[1])),
        mode=EvaluationMode.HISTORICAL_REPLAY,
    )
    assert not decision.eligible
    assert DecisionReasonCode.ORDER_CAPITAL_MISMATCH in decision.decision_reason_codes
    spent_fee = fee_registry(replace(fee_profile(), fee_asset_semantics="SPENT_ASSET"))
    fee_shortfall = gate(spent_fee).evaluate(candidate(), mode=EvaluationMode.HISTORICAL_REPLAY)
    assert DecisionReasonCode.ORDER_CAPITAL_MISMATCH in fee_shortfall.decision_reason_codes


def test_every_route_book_requires_universe_rules_and_fees() -> None:
    usdc_fdusd = BookKey(Venue.BINANCE, "USDCFDUSD")
    fdusd_usdt = BookKey(Venue.BINANCE, "FDUSDUSDT")
    route = VenueRoute(
        "USDT->USDC->FDUSD->USDT",
        "USDT",
        (
            VenueRouteLeg(BINANCE, "USDT", "USDC", True),
            VenueRouteLeg(usdc_fdusd, "USDC", "FDUSD", True),
            VenueRouteLeg(fdusd_usdt, "FDUSD", "USDT", True),
        ),
    )
    row = candidate(
        route_id=route.route_id,
        route=route,
        fee_legs=(
            FeeLeg(BINANCE, True, "USDT", "USDC", "BUY", D("1"), D("5")),
            FeeLeg(usdc_fdusd, True, "USDC", "FDUSD", "SELL", D("1"), D("5")),
            FeeLeg(fdusd_usdt, True, "FDUSD", "USDT", "SELL", D("1"), D("5")),
        ),
    )
    fees = fee_registry()
    fees.add(fee_profile(book=usdc_fdusd))
    fees.add(fee_profile(book=fdusd_usdt))
    decision = gate(fees).evaluate(row, mode=EvaluationMode.HISTORICAL_REPLAY)
    assert not decision.eligible
    assert DecisionReasonCode.PAIR_UNAVAILABLE in decision.decision_reason_codes
    assert DecisionReasonCode.EXCHANGE_RULE_UNPROVEN in decision.decision_reason_codes


def test_currency_mark_requires_temporal_registry_evidence() -> None:
    missing = CausalAssetMarkRegistry()
    decision = gate(marks=missing).evaluate(candidate(), mode=EvaluationMode.HISTORICAL_REPLAY)
    assert DecisionReasonCode.CURRENCY_MARK_UNPROVEN in decision.decision_reason_codes
    with pytest.raises(ValueError, match="INVALID_CAUSAL_ASSET_MARK"):
        CausalAssetMark("USDT", "USD", D("1"), 101, 100, "x", "source", "prov")


def test_external_fee_is_included_in_negative_exit_limit() -> None:
    rule = InventoryExitRule(
        "PEG-RISK-EXT-FEE",
        "rule-hash",
        0,
        20,
        "synthetic preregistration",
        DecisionReasonCode.PEG_RISK_ESCALATED,
    )
    fee_mark = CausalAssetMark(
        "FDUSD", "USDT", D("1"), 3, 10, "mark:FDUSD:USDT", "fixture://mark", "test"
    )
    assessment = InventoryExitDecisionEngine.evaluate(
        authorization_id="EXT-FEE",
        slot_id="S",
        slot_epoch=1,
        quantity=D("5"),
        origin_cost_basis=D("5"),
        inventory_asset="USDC",
        origin_asset="USDT",
        exit_reservation_id="RETURN",
        external_fee_marks=(fee_mark,),
        now_us=3,
        expires_at_us=10,
        expected_hold_loss=D("0.2"),
        opportunity_cost_of_lock=D("0"),
        tail_risk_increase=D("0"),
        realized_loss_of_exit=D("0.1"),
        rule=rule,
    )
    assert assessment.authorization is not None
    ledger = SlotLedger(
        {"USDT": "10", "USDC": "0", "FDUSD": "1"},
        marks_usd={"USDT": "1", "USDC": "1", "FDUSD": "1"},
    )
    ledger.create_slot("S", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    ledger.reserve_free("S", "ENTRY", asset="USDT", quantity=D("5"), now_us=1)
    ledger.activate("ENTRY", now_us=1)
    ledger.apply_fill(
        "ENTRY",
        PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("5"), "USDC", D("0"), 2),
    )
    ledger.register_inventory_reduction_authorization(assessment.authorization, now_us=3)
    ledger.reserve_owned("S", "RETURN", asset="USDC", quantity=D("5"), now_us=4)
    ledger.activate("RETURN", now_us=4)
    ledger.apply_fill(
        "RETURN",
        PhysicalFill(
            "F2",
            "USDCUSDT",
            "USDC",
            "USDT",
            D("5"),
            D("4.9"),
            "FDUSD",
            D("0.5"),
            5,
        ),
    )
    with pytest.raises(ValueError, match="INEQUALITY_NOT_SATISFIED"):
        ledger.settle_inventory_reduction(
            "S", now_us=6, reduction_id="EXT-FEE", authorization=assessment.authorization
        )
    assert ledger.negative_exit_count == 0


def test_spent_asset_fee_counts_toward_authorized_inventory_consumption() -> None:
    rule = InventoryExitRule(
        "PEG-RISK-SPENT-FEE",
        "rule-hash",
        0,
        20,
        "synthetic preregistration",
        DecisionReasonCode.PEG_RISK_ESCALATED,
    )
    assessment = InventoryExitDecisionEngine.evaluate(
        authorization_id="SPENT-FEE",
        slot_id="S",
        slot_epoch=1,
        quantity=D("5"),
        origin_cost_basis=D("5"),
        inventory_asset="USDC",
        origin_asset="USDT",
        exit_reservation_id="RETURN",
        external_fee_marks=(),
        now_us=3,
        expires_at_us=10,
        expected_hold_loss=D("0.3"),
        opportunity_cost_of_lock=D("0"),
        tail_risk_increase=D("0"),
        realized_loss_of_exit=D("0.2"),
        rule=rule,
    )
    assert assessment.authorization is not None
    ledger = SlotLedger({"USDT": "10", "USDC": "0"}, marks_usd={"USDT": "1", "USDC": "1"})
    ledger.create_slot("S", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    ledger.reserve_free("S", "ENTRY", asset="USDT", quantity=D("5"), now_us=1)
    ledger.activate("ENTRY", now_us=1)
    ledger.apply_fill(
        "ENTRY",
        PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("5"), "USDC", D("0"), 2),
    )
    ledger.register_inventory_reduction_authorization(assessment.authorization, now_us=3)
    ledger.reserve_owned("S", "RETURN", asset="USDC", quantity=D("5"), now_us=4)
    ledger.activate("RETURN", now_us=4)
    ledger.apply_fill(
        "RETURN",
        PhysicalFill(
            "F2",
            "USDCUSDT",
            "USDC",
            "USDT",
            D("4.9"),
            D("4.85"),
            "USDC",
            D("0.1"),
            5,
        ),
    )
    pnl = ledger.settle_inventory_reduction(
        "S", now_us=6, reduction_id="SPENT-FEE", authorization=assessment.authorization
    )
    assert pnl == D("-0.15")
    assert ledger.negative_exit_cost == D("0.15")
    assert ledger.negative_exit_count == 1


def test_retired_kraken_obligation_cannot_block_binance_allocation() -> None:
    kraken_route = VenueRoute(
        "USDT->USDC->USDT",
        "USDT",
        (
            VenueRouteLeg(KRAKEN, "USDT", "USDC", True),
            VenueRouteLeg(KRAKEN, "USDC", "USDT", True),
        ),
    )
    retired = candidate(
        "KRAKEN-OWNED",
        venue=Venue.KRAKEN,
        pair=KRAKEN,
        route=kraken_route,
        intent=DecisionIntent.OWNED_RETURN,
        priority_class=1,
        fee_legs=(
            FeeLeg(KRAKEN, True, "USDT", "USDC", "BUY", D("1"), D("5")),
            FeeLeg(KRAKEN, True, "USDC", "USDT", "SELL", D("1"), D("5")),
        ),
    )
    result, ledger = allocate([retired, candidate("BINANCE")])
    assert result.selected_candidate_ids == ("BINANCE",)
    assert all(decision.venue == Venue.BINANCE for decision in ledger.decisions)
    assert all(row.state != CapitalState.LOCKED_INVENTORY for row in ledger.capital_states)
