from __future__ import annotations

from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.adaptive_multi_stable_manager import (
    AdaptiveCapitalOrderManager,
    AdaptiveColumnAllocator,
    PegGuard,
    StablecoinUniverse,
    column_role,
    priority_class,
    zone_for_rank,
)
from crypto_strategy_lab.microstructure.multi_stable_ledger import SlotLedger
from crypto_strategy_lab.microstructure.multi_stable_models import (
    ColumnRole,
    FeeProfile,
    PhysicalFill,
    RouteCandidate,
    RouteLeg,
    SlotState,
    StablecoinEvidence,
    SymbolRule,
)
from crypto_strategy_lab.microstructure.multi_stable_queue import CausalQueueEstimator
from crypto_strategy_lab.microstructure.multi_stable_routing import (
    CycleManager,
    MarginalOpportunity,
    PairProductivityScorer,
    RouteEnumerator,
    RouteScorer,
)


def ledger() -> SlotLedger:
    return SlotLedger(
        {"USDT": "100", "USDC": "50", "FDUSD": "25", "USDP": "25"},
        marks_usd={"USDT": "1", "USDC": "1", "FDUSD": "1", "USDP": "1"},
    )


def slot_ledger() -> tuple[SlotLedger, str]:
    value = ledger()
    value.create_slot("S1", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    value.reserve_free("S1", "R1", asset="USDT", quantity=D("5"), now_us=1)
    value.activate("R1", now_us=1)
    return value, "S1"


def evidence(asset: str, score: str = "1") -> StablecoinEvidence:
    value = D(score)
    return StablecoinEvidence(asset, value, value, value, value, value, 0, ("source",))


def rule() -> SymbolRule:
    return SymbolRule("USDCUSDT", "USDC", "USDT", D("0.0001"), D("1"), D("5"), 0, None, "test")


def two_asset_route() -> RouteCandidate:
    return RouteCandidate(
        "USDT->USDC->USDT",
        "USDT",
        (
            RouteLeg("USDCUSDT", "USDT", "USDC"),
            RouteLeg("USDCUSDT", "USDC", "USDT"),
        ),
    )


def test_max_bankroll_is_200_and_capital_never_duplicates() -> None:
    value = ledger()
    assert value.initial_equity == D("200")
    value.create_slot("S1", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    value.reserve_free("S1", "R1", asset="USDT", quantity=D("5"), now_us=1)
    assert value.asset_totals()["USDT"] == D("100")
    value.reconcile()
    with pytest.raises(ValueError, match="MAX_BANKROLL"):
        SlotLedger({"USDT": "201"}, marks_usd={"USDT": "1"})


def test_one_reservation_belongs_to_one_slot() -> None:
    value, _ = slot_ledger()
    value.create_slot("S2", origin_asset="USDT", usd_equivalent=D("5"), now_us=1)
    with pytest.raises(ValueError, match="RESERVATION_ALREADY_OWNED"):
        value.reserve_free("S2", "R1", asset="USDT", quantity=D("5"), now_us=2)
    with pytest.raises(ValueError, match="RESERVATION_ALREADY_OWNED"):
        value.reserve_free("S1", "R2", asset="USDT", quantity=D("5"), now_us=2)


def test_zero_fill_capital_releases_only_after_cancel_ack() -> None:
    value, _ = slot_ledger()
    assert value.free["USDT"] == D("95")
    value.request_cancel("R1", now_us=2)
    assert value.free["USDT"] == D("95")
    assert value.slots["S1"].state == SlotState.CANCEL_PENDING
    assert value.acknowledge_cancel("R1", now_us=3) == D("5")
    assert value.free["USDT"] == D("100")


def test_partial_and_filled_reservations_are_not_reclaimable() -> None:
    value, _ = slot_ledger()
    value.apply_fill(
        "R1",
        PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("2"), D("2"), "USDC", D("0"), 2),
    )
    with pytest.raises(ValueError, match="NOT_RECLAIMABLE"):
        value.request_cancel("R1", now_us=3)


def test_duplicate_fill_is_hard_failure() -> None:
    value, _ = slot_ledger()
    fill = PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("2"), D("2"), "USDC", D("0"), 2)
    value.apply_fill("R1", fill)
    with pytest.raises(ValueError, match="DUPLICATE_FILL"):
        value.apply_fill("R1", fill)


def test_invalid_fill_and_unfunded_fee_are_atomic() -> None:
    value, _ = slot_ledger()
    before = (
        value.asset_totals(),
        value.reservations["R1"].remaining,
        value.slots["S1"].filled_qty,
    )
    with pytest.raises(ValueError, match="FILL_EXCEEDS"):
        value.apply_fill(
            "R1",
            PhysicalFill(
                "NEG",
                "USDCUSDT",
                "USDT",
                "USDC",
                D("-1"),
                D("100"),
                "USDC",
                D("0"),
                2,
            ),
        )
    assert (
        value.asset_totals(),
        value.reservations["R1"].remaining,
        value.slots["S1"].filled_qty,
    ) == before
    with pytest.raises(ValueError, match="FEE_EXCEEDS"):
        value.apply_fill(
            "R1",
            PhysicalFill(
                "FEE",
                "USDCUSDT",
                "USDT",
                "USDC",
                D("5"),
                D("5"),
                "USDT",
                D("0.1"),
                2,
            ),
        )
    assert (
        value.asset_totals(),
        value.reservations["R1"].remaining,
        value.slots["S1"].filled_qty,
    ) == before


def test_cancel_fill_race_preserves_owned_fill_and_releases_only_residual() -> None:
    value, _ = slot_ledger()
    value.request_cancel("R1", now_us=2)
    value.apply_fill(
        "R1",
        PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("2"), D("2"), "USDC", D("0"), 3),
    )
    assert value.free["USDT"] == D("95")
    assert value.owned["S1"]["USDC"] == D("2")
    assert value.acknowledge_cancel("R1", now_us=4) == D("3")
    assert value.free["USDT"] == D("98")
    assert value.owned["S1"]["USDC"] == D("2")
    assert value.slots["S1"].state == SlotState.FILLED


def test_ack_before_request_and_activate_after_cancel_are_rejected() -> None:
    value, _ = slot_ledger()
    value.request_cancel("R1", now_us=20)
    with pytest.raises(ValueError, match="NONCAUSAL_LEDGER_EVENT"):
        value.acknowledge_cancel("R1", now_us=10)
    with pytest.raises(ValueError, match="INVALID_ACTIVATION"):
        value.activate("R1", now_us=21)


def test_cancel_pending_without_prior_activation_cannot_fill() -> None:
    value = ledger()
    value.create_slot("S1", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    value.reserve_free("S1", "R1", asset="USDT", quantity=D("5"), now_us=1)
    value.request_cancel("R1", now_us=2)
    with pytest.raises(ValueError, match="FILL_BEFORE_ACTIVATION"):
        value.apply_fill(
            "R1",
            PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("1"), D("1"), "USDC", D("0"), 3),
        )


def test_marked_pnl_does_not_become_realized_pnl() -> None:
    value, _ = slot_ledger()
    value.apply_fill(
        "R1",
        PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("5.1"), "USDC", D("0"), 2),
    )
    assert (
        value.marked_equity({"USDT": D("1"), "USDC": D("0.99"), "FDUSD": D("1"), "USDP": D("1")})
        != value.initial_equity
    )
    assert value.realized_pnl_by_asset["USDT"] == 0


def test_negative_realized_exit_is_prohibited() -> None:
    value, _ = slot_ledger()
    value.apply_fill(
        "R1",
        PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("4.9"), "USDC", D("0"), 2),
    )
    value.owned["S1"]["USDT"] = D("4.9")
    value.owned["S1"]["USDC"] = D("0")
    value._asset_totals["USDC"] -= D("4.9")
    value._asset_totals["USDT"] += D("4.9")
    with pytest.raises(ValueError, match="NEGATIVE_REALIZED"):
        value.close_slot("S1", origin_quantity=D("5"), now_us=3, cycle_id="C1")


def test_fee_is_debited_from_received_asset() -> None:
    value, _ = slot_ledger()
    value.apply_fill(
        "R1",
        PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("5.1"), "USDC", D("0.1"), 2),
    )
    assert value.owned["S1"]["USDC"] == D("5.0")
    assert value.asset_totals()["USDC"] == D("55.0")


def test_symbol_rules_enforce_tick_step_and_min_notional() -> None:
    current = rule()
    current.validate_order(price=D("1.0000"), quantity=D("5"), time_us=1)
    for price, quantity, message in (
        (D("1.00001"), D("5"), "TICK"),
        (D("1.0000"), D("5.5"), "STEP"),
        (D("1.0000"), D("4"), "MIN_NOTIONAL"),
    ):
        with pytest.raises(ValueError, match=message):
            current.validate_order(price=price, quantity=quantity, time_us=1)


def test_fee_profile_is_time_bounded() -> None:
    profile = FeeProfile("USDCUSDT", D("0.001"), D("0.002"), 10, 20, "test")
    assert profile.rate(maker=True, time_us=10) == D("0.001")
    with pytest.raises(ValueError, match="OUTSIDE"):
        profile.rate(maker=True, time_us=20)


def test_geometry_is_seven_ranks_and_two_columns() -> None:
    assert [zone_for_rank(rank) for rank in range(1, 8)] == [
        "HOT",
        "HOT",
        "HOT",
        "MID",
        "MID",
        "FAR",
        "FAR",
    ]
    assert column_role(1) == ColumnRole.PERSISTENT_QUEUE
    assert column_role(2) == ColumnRole.OPPORTUNITY
    with pytest.raises(ValueError):
        column_role(3)


def test_priority_class_separates_obligation_and_score() -> None:
    assert priority_class(obligation=True, rank=7, column=2, old_zero_fill=False) == 1
    assert priority_class(obligation=False, rank=1, column=1, old_zero_fill=False) == 2
    assert priority_class(obligation=False, rank=7, column=2, old_zero_fill=False) == 7
    assert priority_class(obligation=False, rank=1, column=1, old_zero_fill=True) == 8


def test_c2_is_behind_c1_and_does_not_copy_public_queue() -> None:
    queue = CausalQueueEstimator()
    queue.activate(
        book="USDCUSDT",
        side="BUY",
        price=D("1"),
        order_id="C1",
        column=1,
        quantity=D("1"),
        observed_public_queue=D("10"),
        now_us=1,
    )
    queue.activate(
        book="USDCUSDT",
        side="BUY",
        price=D("1"),
        order_id="C2",
        column=2,
        quantity=D("1"),
        observed_public_queue=D("10"),
        now_us=2,
    )
    assert queue.queue_ahead("C1") == D("10")
    assert queue.queue_ahead("C2") == D("11")


def test_same_trade_quantity_is_consumed_once_public_then_c1_then_c2() -> None:
    queue = CausalQueueEstimator()
    queue.activate(
        book="B",
        side="BUY",
        price=D("1"),
        order_id="C1",
        column=1,
        quantity=D("1"),
        observed_public_queue=D("2"),
        now_us=1,
    )
    queue.activate(
        book="B",
        side="BUY",
        price=D("1"),
        order_id="C2",
        column=2,
        quantity=D("1"),
        observed_public_queue=D("2"),
        now_us=2,
    )
    assert queue.consume_compatible_flow(
        event_id="T1", book="B", side="BUY", price=D("1"), quantity=D("3"), now_us=3
    ) == {"C1": D("1")}
    with pytest.raises(ValueError, match="DUPLICATE_TRADE"):
        queue.consume_compatible_flow(
            event_id="T1", book="B", side="BUY", price=D("1"), quantity=D("3"), now_us=3
        )
    assert queue.queue_ahead("C2") == 0


def test_partial_c1_blocks_c2() -> None:
    queue = CausalQueueEstimator()
    queue.activate(
        book="B",
        side="SELL",
        price=D("1"),
        order_id="C1",
        column=1,
        quantity=D("2"),
        observed_public_queue=D("0"),
        now_us=1,
    )
    queue.activate(
        book="B",
        side="SELL",
        price=D("1"),
        order_id="C2",
        column=2,
        quantity=D("1"),
        observed_public_queue=D("0"),
        now_us=2,
    )
    fills = queue.consume_compatible_flow(
        event_id="T1", book="B", side="SELL", price=D("1"), quantity=D("1"), now_us=3
    )
    assert fills == {"C1": D("1")}
    assert queue.queue_ahead("C2") == D("1")
    assert queue.wait_distribution(book="B", side="SELL", price=D("1")) == {
        "MEDIAN_TIME_TO_FIRST_FILL_US": 2,
        "MEDIAN_TIME_TO_FULL_FILL_US": None,
        "P90_TIME_TO_FULL_FILL_US": None,
        "P95_TIME_TO_FULL_FILL_US": None,
    }


def test_replacement_order_is_younger_and_cannot_inherit_priority() -> None:
    queue = CausalQueueEstimator()
    original = queue.activate(
        book="B",
        side="BUY",
        price=D("1"),
        order_id="ORIGINAL",
        column=1,
        quantity=D("1"),
        observed_public_queue=D("1"),
        now_us=1,
    )
    queue.cancel_ack("ORIGINAL", now_us=2)
    replacement = queue.activate(
        book="B",
        side="BUY",
        price=D("1.0001"),
        order_id="REPLACEMENT",
        column=1,
        quantity=D("2"),
        observed_public_queue=D("3"),
        now_us=3,
    )
    assert replacement.activated_at_us > original.activated_at_us
    assert queue.queue_ahead("REPLACEMENT") == D("3")


def test_same_price_replacement_gets_new_public_queue_epoch() -> None:
    queue = CausalQueueEstimator()
    queue.activate(
        book="B",
        side="BUY",
        price=D("1"),
        order_id="OLD",
        column=1,
        quantity=D("1"),
        observed_public_queue=D("0"),
        now_us=1,
    )
    queue.cancel_ack("OLD", now_us=2)
    queue.activate(
        book="B",
        side="BUY",
        price=D("1"),
        order_id="NEW",
        column=1,
        quantity=D("1"),
        observed_public_queue=D("100"),
        now_us=3,
    )
    assert queue.queue_ahead("NEW") == D("100")


def test_causal_queue_score_rejects_future_reordering() -> None:
    queue = CausalQueueEstimator()
    queue.activate(
        book="B",
        side="BUY",
        price=D("1"),
        order_id="C1",
        column=1,
        quantity=D("1"),
        observed_public_queue=D("1"),
        now_us=5,
    )
    with pytest.raises(ValueError, match="FUTURE_OR_REORDERED"):
        queue.estimate("C1", now_us=4)


def test_queue_probabilities_use_prefix_flow_only() -> None:
    queue = CausalQueueEstimator(flow_window_us=60_000_000)
    queue.activate(
        book="B",
        side="BUY",
        price=D("1"),
        order_id="C1",
        column=1,
        quantity=D("1"),
        observed_public_queue=D("60"),
        now_us=0,
    )
    queue.consume_compatible_flow(
        event_id="T1", book="B", side="BUY", price=D("1"), quantity=D("30"), now_us=30_000_000
    )
    estimate = queue.estimate("C1", now_us=60_000_000)
    assert estimate.queue_ahead == D("30")
    assert estimate.fill_probability_30s == D("1")


def test_hotline_multi_tick_jump_reconciles_once_without_reset() -> None:
    value = ledger()
    universe = StablecoinUniverse([evidence("USDT"), evidence("USDC")], minimum_safety=D("0.5"))
    manager = AdaptiveCapitalOrderManager(
        ledger=value,
        rules={"USDCUSDT": rule()},
        universe=universe,
        peg_guard=PegGuard(D("0.02"), D("0.001"), D("100")),
    )
    first = manager.update_hotline("USDCUSDT", midpoint=D("1.0000"), now_us=1)
    assert first.reconciliations == 1
    moved = manager.update_hotline("USDCUSDT", midpoint=D("1.0005"), now_us=2)
    assert moved.crossed_ticks == 5
    assert moved.reconciliations == 2


def test_cell_configuration_requires_hotline_rank_safety_and_free_unique_slot() -> None:
    value = ledger()
    value.create_slot("S1", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    value.create_slot("S2", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    universe = StablecoinUniverse([evidence("USDT"), evidence("USDC")], minimum_safety=D("0.5"))
    manager = AdaptiveCapitalOrderManager(
        ledger=value,
        rules={"USDCUSDT": rule()},
        universe=universe,
        peg_guard=PegGuard(D("0.02"), D("0.001"), D("100")),
    )
    manager.update_hotline("USDCUSDT", midpoint=D("1"), now_us=1)
    kwargs = {
        "symbol": "USDCUSDT",
        "side": "BUY",
        "price": D("0.9999"),
        "rank": 1,
        "column": 1,
        "quantity": D("6"),
        "now_us": 1,
        "peg_deviation": D("0"),
        "spread": D("0.0001"),
        "depth_usd": D("200"),
        "data_gap": False,
    }
    manager.configure_slot_cell("S1", **kwargs)
    with pytest.raises(ValueError, match="DUPLICATE_PHYSICAL_CELL"):
        manager.configure_slot_cell("S2", **kwargs)
    value.reserve_free("S1", "R1", asset="USDT", quantity=D("5"), now_us=2)
    with pytest.raises(ValueError, match="ACTIVE_SLOT_CELL_IMMUTABLE"):
        manager.configure_slot_cell("S1", **{**kwargs, "now_us": 2})


def test_aged_c1_is_preserved_unless_reallocation_value_wins() -> None:
    value = ledger()
    value.create_slot("S1", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    value.slots["S1"].column = 1
    universe = StablecoinUniverse([evidence("USDT"), evidence("USDC")], minimum_safety=D("0.5"))
    manager = AdaptiveCapitalOrderManager(
        ledger=value,
        rules={"USDCUSDT": rule()},
        universe=universe,
        peg_guard=PegGuard(D("0.02"), D("0.001"), D("100")),
    )
    assert (
        manager.reclaimable(
            "S1",
            alternative_score=D("1"),
            queue_position_value=D("2"),
            reason="BETTER_ROUTE_AVAILABLE",
            now_us=1,
        )
        is False
    )
    assert (
        manager.reclaimable(
            "S1",
            alternative_score=D("3"),
            queue_position_value=D("2"),
            reason="BETTER_ROUTE_AVAILABLE",
            now_us=2,
        )
        is True
    )


def test_partial_slot_is_never_manager_reclaimable() -> None:
    value = ledger()
    value.create_slot("S1", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    value.slots["S1"].state = SlotState.PARTIAL
    value.slots["S1"].filled_qty = D("1")
    universe = StablecoinUniverse([evidence("USDT"), evidence("USDC")], minimum_safety=D("0.5"))
    manager = AdaptiveCapitalOrderManager(
        ledger=value,
        rules={"USDCUSDT": rule()},
        universe=universe,
        peg_guard=PegGuard(D("0.02"), D("0.001"), D("100")),
    )
    assert (
        manager.reclaimable(
            "S1",
            alternative_score=D("9"),
            queue_position_value=D("0"),
            reason="BETTER_ROUTE_AVAILABLE",
            now_us=1,
        )
        is False
    )


def test_depeg_guard_blocks_new_entry() -> None:
    guard = PegGuard(D("0.01"), D("0.001"), D("100"))
    assert guard.allows_entry(
        peg_deviation=D("0.005"), spread=D("0.0001"), depth_usd=D("200"), data_gap=False
    )
    assert not guard.allows_entry(
        peg_deviation=D("0.02"), spread=D("0.0001"), depth_usd=D("200"), data_gap=False
    )
    assert not guard.allows_entry(
        peg_deviation=D("0"), spread=D("0.0001"), depth_usd=D("200"), data_gap=True
    )


def test_safety_score_is_eligibility_not_column_count() -> None:
    universe = StablecoinUniverse(
        [evidence("USDT", "1"), evidence("USDC", "0.4")], minimum_safety=D("0.5")
    )
    assert universe.eligible_assets == ("USDT",)


def test_marginal_score_is_explainable_and_capital_time_normalized() -> None:
    row = MarginalOpportunity("A", 2, D("0.01"), D("0.5"), D("5"), D("10"), D("0.9"))
    score = PairProductivityScorer.score(row)
    assert score.score == D("0.00009")
    assert score.expected_net_pnl == D("0.01")


def test_allocator_respects_priority_then_score_and_real_capital() -> None:
    rows = [
        MarginalOpportunity("C2", 3, D("1"), D("1"), D("5"), D("1"), D("1")),
        MarginalOpportunity("C1", 2, D("0.1"), D("1"), D("5"), D("1"), D("1")),
    ]
    chosen = AdaptiveColumnAllocator().choose(rows, available_capital=D("5"))
    assert [row.candidate_id for row in chosen] == ["C1"]


def test_allocator_funds_obligation_even_with_negative_score_and_stops_on_shortfall() -> None:
    obligation = MarginalOpportunity(
        "RETURN",
        1,
        D("0.01"),
        D("1"),
        D("5"),
        D("1"),
        D("1"),
        inventory_risk_penalty=D("0.02"),
    )
    entry = MarginalOpportunity("ENTRY", 2, D("1"), D("1"), D("1"), D("1"), D("1"))
    assert [
        row.candidate_id
        for row in AdaptiveColumnAllocator().choose([entry, obligation], available_capital=D("5"))
    ] == ["RETURN"]
    assert AdaptiveColumnAllocator().choose([entry, obligation], available_capital=D("4")) == []


def test_negative_expected_exit_is_not_scored() -> None:
    with pytest.raises(ValueError, match="NEGATIVE_EXPECTED_EXIT"):
        PairProductivityScorer.score(
            MarginalOpportunity("LOSS", 1, D("-0.01"), D("1"), D("5"), D("1"), D("1"))
        )


def test_route_2_asset_closes_only_after_second_physical_fill() -> None:
    manager = CycleManager(ledger())
    value = manager.ledger
    value.create_slot("S1", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    manager.start(two_asset_route(), execution_id="E1", slot_id="S1", quantity=D("5"), now_us=1)
    value.reserve_free("S1", "R1", asset="USDT", quantity=D("5"), now_us=1)
    value.activate("R1", now_us=1)
    first = PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("5.01"), "USDC", D("0"), 2)
    second = PhysicalFill("F2", "USDCUSDT", "USDC", "USDT", D("5.01"), D("5.02"), "USDT", D("0"), 3)
    assert manager.record_fill("E1", "R1", first) is False
    assert manager.closed_cycles == []
    value.reserve_owned("S1", "R2", asset="USDC", quantity=D("5.01"), now_us=2)
    value.activate("R2", now_us=2)
    assert manager.record_fill("E1", "R2", second) is True
    assert value.free["USDT"] == D("100.02")


def test_route_leg_aggregates_physical_partial_fragments() -> None:
    value = ledger()
    value.create_slot("S1", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    manager = CycleManager(value)
    manager.start(two_asset_route(), execution_id="E1", slot_id="S1", quantity=D("5"), now_us=1)
    value.reserve_free("S1", "R1", asset="USDT", quantity=D("5"), now_us=1)
    value.activate("R1", now_us=1)
    first_fragment = PhysicalFill(
        "F1", "USDCUSDT", "USDT", "USDC", D("2"), D("2.01"), "USDC", D("0"), 2
    )
    second_fragment = PhysicalFill(
        "F2", "USDCUSDT", "USDT", "USDC", D("3"), D("3.01"), "USDC", D("0"), 3
    )
    assert manager.record_fill("E1", "R1", first_fragment) is False
    assert manager.routes["E1"].next_leg_index == 0
    assert manager.record_fill("E1", "R1", second_fragment) is False
    assert manager.routes["E1"].next_leg_index == 1
    assert manager.routes["E1"].current_quantity == D("5.02")


def test_third_asset_fee_reduces_cycle_pnl_and_negative_return_is_atomic() -> None:
    value = SlotLedger(
        {"USDT": "100", "USDC": "50", "FDUSD": "1"},
        marks_usd={"USDT": "1", "USDC": "1", "FDUSD": "1"},
    )
    value.create_slot("S1", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    manager = CycleManager(value)
    manager.start(two_asset_route(), execution_id="E1", slot_id="S1", quantity=D("5"), now_us=1)
    value.reserve_free("S1", "R1", asset="USDT", quantity=D("5"), now_us=1)
    value.activate("R1", now_us=1)
    manager.record_fill(
        "E1",
        "R1",
        PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("5"), "FDUSD", D("0.01"), 2),
    )
    value.reserve_owned("S1", "R2", asset="USDC", quantity=D("5"), now_us=2)
    value.activate("R2", now_us=2)
    before = (value.asset_totals(), value.reservations["R2"].remaining)
    with pytest.raises(ValueError, match="NEGATIVE_RETURN_FILL_NOT_ADMITTED"):
        manager.record_fill(
            "E1",
            "R2",
            PhysicalFill("F2", "USDCUSDT", "USDC", "USDT", D("5"), D("5"), "USDT", D("0"), 3),
        )
    assert (value.asset_totals(), value.reservations["R2"].remaining) == before


def test_third_asset_fee_is_included_in_positive_realized_cycle_pnl() -> None:
    value = SlotLedger(
        {"USDT": "100", "USDC": "50", "FDUSD": "1"},
        marks_usd={"USDT": "1", "USDC": "1", "FDUSD": "1"},
    )
    value.create_slot("S1", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    manager = CycleManager(value)
    manager.start(two_asset_route(), execution_id="E1", slot_id="S1", quantity=D("5"), now_us=1)
    value.reserve_free("S1", "R1", asset="USDT", quantity=D("5"), now_us=1)
    value.activate("R1", now_us=1)
    manager.record_fill(
        "E1",
        "R1",
        PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("5"), "FDUSD", D("0.01"), 2),
    )
    value.reserve_owned("S1", "R2", asset="USDC", quantity=D("5"), now_us=2)
    value.activate("R2", now_us=2)
    assert manager.record_fill(
        "E1",
        "R2",
        PhysicalFill("F2", "USDCUSDT", "USDC", "USDT", D("5"), D("5.02"), "USDT", D("0"), 3),
    )
    assert manager.routes["E1"].realized_pnl_origin == D("0.01")
    assert value.realized_pnl_by_asset["USDT"] == D("0.01")


def test_input_asset_fee_consumes_leg_without_double_deduction() -> None:
    value = ledger()
    value.create_slot("S1", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    manager = CycleManager(value)
    manager.start(two_asset_route(), execution_id="E1", slot_id="S1", quantity=D("5"), now_us=1)
    value.reserve_free("S1", "R1", asset="USDT", quantity=D("5"), now_us=1)
    value.activate("R1", now_us=1)
    manager.record_fill(
        "E1",
        "R1",
        PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("5"), "USDC", D("0"), 2),
    )
    value.reserve_owned("S1", "R2", asset="USDC", quantity=D("5"), now_us=2)
    value.activate("R2", now_us=2)
    assert manager.record_fill(
        "E1",
        "R2",
        PhysicalFill("F2", "USDCUSDT", "USDC", "USDT", D("4.9"), D("5.2"), "USDC", D("0.1"), 3),
    )
    assert manager.routes["E1"].leg_input_remaining == 0
    assert manager.routes["E1"].realized_pnl_origin == D("0.2")
    assert value.realized_pnl_by_asset["USDT"] == D("0.2")
    value.reconcile()


@pytest.mark.parametrize(
    ("assets", "legs"),
    [
        (("USDT", "USDC", "FDUSD", "USDT"), 3),
        (("USDT", "USDC", "FDUSD", "USDP", "USDT"), 4),
    ],
)
def test_route_3_and_4_asset_close_correctly(assets: tuple[str, ...], legs: int) -> None:
    candidate = RouteCandidate(
        "->".join(assets),
        assets[0],
        tuple(RouteLeg(f"B{index}", assets[index], assets[index + 1]) for index in range(legs)),
    )
    value = ledger()
    value.create_slot("S1", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    manager = CycleManager(value)
    manager.start(candidate, execution_id="E1", slot_id="S1", quantity=D("5"), now_us=1)
    quantity = D("5")
    for index, leg in enumerate(candidate.legs):
        reservation_id = f"R{index}"
        if index == 0:
            value.reserve_free(
                "S1", reservation_id, asset=leg.from_asset, quantity=quantity, now_us=1
            )
        else:
            value.reserve_owned(
                "S1", reservation_id, asset=leg.from_asset, quantity=quantity, now_us=index + 1
            )
        value.activate(reservation_id, now_us=index + 1)
        is_last = index == legs - 1
        output = quantity + D("0.01") if is_last else quantity
        closed = manager.record_fill(
            "E1",
            reservation_id,
            PhysicalFill(
                f"F{index}",
                leg.symbol,
                leg.from_asset,
                leg.to_asset,
                quantity,
                output,
                leg.to_asset,
                D("0"),
                index + 2,
            ),
        )
        assert closed is is_last
        quantity = output
    assert manager.closed_cycles == ["E1"]


def test_route_enumerator_never_repeats_middle_asset() -> None:
    assets = {"USDT", "USDC", "FDUSD"}
    markets = {(a, b): "".join((a, b)) for a in assets for b in assets if a != b}
    routes = RouteEnumerator(markets).enumerate("USDT", assets)
    assert {len(route.legs) for route in routes} == {2, 3}
    assert all(len({leg.from_asset for leg in route.legs}) == len(route.legs) for route in routes)


def test_route_incomplete_never_counts_as_realized_cycle() -> None:
    value = ledger()
    value.create_slot("S1", origin_asset="USDT", usd_equivalent=D("5"), now_us=0)
    manager = CycleManager(value)
    route = two_asset_route()
    manager.start(route, execution_id="E1", slot_id="S1", quantity=D("5"), now_us=1)
    value.reserve_free("S1", "R1", asset="USDT", quantity=D("5"), now_us=1)
    value.activate("R1", now_us=1)
    manager.record_fill(
        "E1",
        "R1",
        PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("5"), "USDC", D("0"), 2),
    )
    assert manager.closed_cycles == []


def test_same_capital_cannot_fund_two_incompatible_legs() -> None:
    value, _ = slot_ledger()
    with pytest.raises(ValueError, match="RESERVATION_ALREADY_OWNED"):
        value.reserve_free("S1", "R2", asset="USDT", quantity=D("1"), now_us=2)


def test_route_scorer_penalizes_slow_route() -> None:
    route = two_asset_route()
    fast = RouteScorer.score(
        route,
        leg_wait_seconds=(D("1"), D("1")),
        leg_completion_probabilities=(D("1"), D("1")),
        expected_net_pnl=D("0.01"),
        capital=D("5"),
    )
    slow = RouteScorer.score(
        route,
        leg_wait_seconds=(D("10"), D("10")),
        leg_completion_probabilities=(D("1"), D("1")),
        expected_net_pnl=D("0.01"),
        capital=D("5"),
    )
    assert fast.route_score > slow.route_score


def test_physical_cycle_is_not_slot_equivalent_cycle() -> None:
    physical_cycles = 1
    slot_equivalent_cycles = 4
    assert physical_cycles != slot_equivalent_cycles


def test_turnover_median_and_p95_use_only_closed_slots() -> None:
    value = ledger()
    value.turnover_us.extend([10, 20, 30])
    metrics = value.turnover_metrics()
    assert metrics["MEDIAN_SLOT_TURNOVER_US"] == 20
    assert metrics["P95_SLOT_TURNOVER_US"] == 30


def test_same_inputs_are_reproducible() -> None:
    def run() -> tuple[dict[str, D], dict[str, D]]:
        value, _ = slot_ledger()
        value.apply_fill(
            "R1", PhysicalFill("F1", "USDCUSDT", "USDT", "USDC", D("5"), D("5"), "USDC", D("0"), 2)
        )
        return value.asset_totals(), value.owned["S1"]

    assert run() == run()
