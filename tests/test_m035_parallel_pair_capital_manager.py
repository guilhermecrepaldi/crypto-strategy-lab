from __future__ import annotations

from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.parallel_pair_capital_manager import (
    AllocationCandidate,
    AllocationPriority,
    CapitalState,
    CycleAttributionLedger,
    CycleRecord,
    GlobalCapitalLedger,
    OrderStatus,
    PairEngine,
    ParallelPairCapitalAllocator,
    RiskExitAuthorization,
)


def candidate(
    candidate_id: str,
    pair_id: str,
    amount: str,
    *,
    priority: AllocationPriority = AllocationPriority.NEW_ENTRY,
    productivity: str = "1",
    edge: str = "0.01",
    allow_partial: bool = True,
    existing_capital_id: str | None = None,
) -> AllocationCandidate:
    return AllocationCandidate(
        candidate_id=candidate_id,
        pair_id=pair_id,
        requested_usdt=D(amount),
        priority=priority,
        marginal_productivity=D(productivity),
        fifo_value=D("0.1"),
        expected_lock_seconds=D("60"),
        expected_net_edge=D(edge),
        allow_partial=allow_partial,
        existing_capital_id=existing_capital_id,
    )


def engine(pair_id: str, symbol: str, asset: str) -> PairEngine:
    value = PairEngine(pair_id=pair_id, symbol=symbol, pair_asset=asset, tick_size=D("0.0001"))
    value.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    value.initialize_grid(now_us=0)
    return value


def test_hotline_isolation() -> None:
    pair_a = engine("PAIR_A", "USDCUSDT", "USDC")
    pair_b = engine("PAIR_B", "FDUSDUSDT", "FDUSD")
    b_hotline = pair_b.state.hotline
    b_orders = [(row.order_id, row.price, row.status) for row in pair_b.state.orders.values()]

    pair_a.receive_book(bid=D("1.0002"), ask=D("1.0004"), now_us=1)

    assert pair_a.state.hotline == D("1.0003")
    assert pair_b.state.hotline == b_hotline
    actual_b_orders = [
        (row.order_id, row.price, row.status) for row in pair_b.state.orders.values()
    ]
    assert actual_b_orders == b_orders
    pair_b.receive_book(bid=D("0.9996"), ask=D("0.9998"), now_us=1)
    assert pair_b.state.hotline == D("0.9997")
    assert pair_a.state.hotline == D("1.0003")


def test_grid_follows_hotline_and_c2_waits_for_cancel_ack() -> None:
    pair = engine("PAIR_A", "USDCUSDT", "USDC")
    old_c1 = next(
        row
        for row in pair.state.orders.values()
        if row.side == "BUY" and row.rank == 1 and row.column == 1
    )
    old_c2 = next(
        row
        for row in pair.state.orders.values()
        if row.side == "BUY" and row.rank == 1 and row.column == 2
    )
    pair.receive_book(bid=D("1.0001"), ask=D("1.0003"), now_us=10)

    assert old_c1.status == OrderStatus.ACTIVE
    assert old_c1.price == D("0.9999")
    assert old_c2.status == OrderStatus.CANCEL_PENDING
    assert old_c2.replacement_price == D("1.0001")
    assert old_c2.order_id in pair.queue.order_group

    replacement = pair.acknowledge_grid_cancel(old_c2.order_id, now_us=11)
    assert replacement is not None
    assert old_c2.status == OrderStatus.CANCELLED
    assert old_c2.order_id not in pair.queue.order_group
    assert replacement.price == D("1.0001")
    assert replacement.submitted_at_us == 11


@pytest.mark.parametrize(
    ("bid", "ask", "expected"),
    [
        ("1.0000", "1.0002", "1.0001"),
        ("1.0001", "1.0003", "1.0002"),
        ("0.9998", "1.0000", "0.9999"),
        ("1.0009", "1.0011", "1.0010"),
    ],
)
def test_hotline_accepts_single_multi_and_negative_tick_moves(
    bid: str, ask: str, expected: str
) -> None:
    pair = engine("PAIR_A", "USDCUSDT", "USDC")
    pair.receive_book(bid=D(bid), ask=D(ask), now_us=1)
    assert pair.state.hotline == D(expected)


def test_simultaneous_opportunities_share_one_bank() -> None:
    ledger = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(ledger)
    grants = allocator.allocate(
        [candidate("A70", "PAIR_A", "70"), candidate("B60", "PAIR_B", "60")], now_us=10
    )
    assert {row.pair_id: row.amount_usdt for row in grants} == {
        "PAIR_A": D("70"),
        "PAIR_B": D("60"),
    }
    assert ledger.free_usdt == D("70")
    assert ledger.committed_usdt == D("130")
    assert ledger.marked_equity({}) == D("200")


def test_insufficient_capital_never_commits_250() -> None:
    ledger = GlobalCapitalLedger()
    grants = ParallelPairCapitalAllocator(ledger).allocate(
        [
            candidate("A150", "PAIR_A", "150", productivity="1"),
            candidate("B100", "PAIR_B", "100", productivity="2"),
        ],
        now_us=10,
    )
    assert [(row.candidate_id, row.amount_usdt) for row in grants] == [
        ("B100", D("100")),
        ("A150", D("100")),
    ]
    assert ledger.free_usdt == D("0")
    assert ledger.committed_usdt == D("200")
    assert ledger.committed_usdt <= ledger.marked_equity({})


def test_owned_return_priority_precedes_new_entry() -> None:
    ledger = GlobalCapitalLedger()
    initial = ParallelPairCapitalAllocator(ledger).allocate(
        [candidate("A_INVENTORY", "PAIR_A", "70")], now_us=1
    )[0]
    ledger.record_entry_fill(
        initial.capital_id,
        asset="USDC",
        quantity_net=D("70"),
        causal_mark_usdt=D("1"),
        attributable_cost_usdt=D("0"),
        now_us=2,
    )
    grants = ParallelPairCapitalAllocator(ledger).allocate(
        [
            candidate("NEW_HIGH", "PAIR_B", "150", productivity="100"),
            candidate(
                "RETURN_A",
                "PAIR_A",
                "70",
                priority=AllocationPriority.OWNED_RETURN,
                productivity="0",
                edge="0",
                allow_partial=False,
                existing_capital_id=initial.capital_id,
            ),
        ],
        now_us=3,
    )
    assert [row.candidate_id for row in grants] == ["RETURN_A", "NEW_HIGH"]
    assert [row.amount_usdt for row in grants] == [D("70"), D("130")]
    assert ledger.free_usdt == D("0")
    assert ledger.positions[initial.capital_id].state == CapitalState.RETURN_PAIR_A


def test_returned_capital_is_unavailable_until_physical_settlement() -> None:
    ledger = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(ledger)
    capital_id = allocator.allocate([candidate("A", "PAIR_A", "150")], now_us=1)[0].capital_id
    ledger.record_entry_fill(
        capital_id,
        asset="USDC",
        quantity_net=D("150"),
        causal_mark_usdt=D("1"),
        attributable_cost_usdt=D("0"),
        now_us=2,
    )
    ledger.reserve_owned_return(capital_id, now_us=3)
    before = allocator.allocate([candidate("B", "PAIR_B", "100")], now_us=3)
    assert before[0].amount_usdt == D("50")
    assert ledger.free_usdt == D("0")
    ledger.settle_return(
        capital_id,
        cycle_id="A-CYCLE-1",
        sold_quantity=D("150"),
        net_proceeds_usdt=D("150.01"),
        residual_mark_usdt=D("1"),
        now_us=4,
    )
    after = allocator.allocate([candidate("B2", "PAIR_B", "100")], now_us=5)
    assert after[0].amount_usdt == D("100")


def test_cancel_request_does_not_release_capital_before_ack() -> None:
    ledger = GlobalCapitalLedger()
    capital_id = ParallelPairCapitalAllocator(ledger).allocate(
        [candidate("A", "PAIR_A", "70")], now_us=1
    )[0].capital_id
    ledger.request_cancel(capital_id, now_us=2)
    assert ledger.positions[capital_id].state == CapitalState.CANCEL_PENDING
    assert ledger.free_usdt == D("130")
    assert ledger.owner_of(capital_id) == "PAIR_A"
    assert ledger.acknowledge_cancel(capital_id, now_us=3) == D("70")
    assert ledger.free_usdt == D("200")
    assert ledger.owner_of(capital_id) is None


def test_dust_is_owned_marked_aggregated_and_reusable() -> None:
    ledger = GlobalCapitalLedger()
    capital_id = ParallelPairCapitalAllocator(ledger).allocate(
        [candidate("DUST", "PAIR_A", "9")], now_us=1
    )[0].capital_id
    ledger.record_entry_fill(
        capital_id,
        asset="USDC",
        quantity_net=D("8.9991"),
        causal_mark_usdt=D("1"),
        attributable_cost_usdt=D("0"),
        input_usdt=D("9"),
        now_us=2,
    )
    ledger.reserve_owned_return(capital_id, now_us=3)
    ledger.settle_return(
        capital_id,
        cycle_id="DUST-CYCLE-1",
        sold_quantity=D("8"),
        net_proceeds_usdt=D("8.0016"),
        residual_mark_usdt=D("1"),
        now_us=4,
    )
    assert ledger.dust.quantity("USDC", pair_id="PAIR_A") == D("0.9991")
    assert ledger.dust.marked_value({"USDC": D("1")}) == D("0.9991")
    assert ledger.marked_equity({"USDC": D("1")}) == D("200.0007")
    assert ledger.dust.tradeable_quantity(
        "USDC", step_size=D("0.1"), minimum_quantity=D("0.1"), pair_id="PAIR_A"
    ) == D("0.9")
    aggregated = ledger.reserve_aggregated_dust(
        pair_id="PAIR_A", asset="USDC", quantity=D("0.9"), mark_usdt=D("1"), now_us=5
    )
    assert ledger.positions[aggregated].quantity == D("0.9")
    assert ledger.positions[aggregated].state == CapitalState.RETURN_PAIR_A
    assert ledger.dust.quantity("USDC", pair_id="PAIR_A") == D("0.0991")
    assert ledger.marked_equity({"USDC": D("1")}) == D("200.0007")


def test_positive_aggregate_cannot_hide_negative_cycle() -> None:
    cycles = CycleAttributionLedger()
    cycles.record(
        CycleRecord("A", "PAIR_A", D("10.10"), D("10"), D("0"), D("0"), D("0"))
    )
    cycles.record(
        CycleRecord("B", "PAIR_B", D("9.99"), D("10"), D("0"), D("0"), D("0"))
    )
    assert cycles.aggregate_pnl_usdt == D("0.09")
    assert cycles.negative_closed_cycles == 1
    assert not cycles.zero_loss_cycle_pass
    assert not cycles.zero_loss_economic_pass


def test_two_positive_cycles_pass_zero_loss() -> None:
    cycles = CycleAttributionLedger()
    cycles.record(
        CycleRecord("A", "PAIR_A", D("10.01"), D("10"), D("0"), D("0"), D("0"))
    )
    cycles.record(
        CycleRecord("B", "PAIR_B", D("10.02"), D("10"), D("0"), D("0"), D("0"))
    )
    assert cycles.aggregate_pnl_usdt == D("0.03")
    assert cycles.negative_closed_cycles == 0
    assert cycles.zero_loss_economic_pass


def test_negative_risk_exit_marks_economic_fail() -> None:
    cycles = CycleAttributionLedger()
    cycles.record(
        CycleRecord(
            "RISK",
            "PAIR_A",
            D("9.98"),
            D("10"),
            D("0"),
            D("0"),
            D("0"),
            risk_exit=True,
        )
    )
    assert cycles.negative_risk_exits == 1
    assert not cycles.zero_loss_economic_pass


def test_c1_fifo_value_controls_replacement() -> None:
    pair = engine("PAIR_A", "USDCUSDT", "USDC")
    c1 = next(
        row
        for row in pair.state.orders.values()
        if row.side == "BUY" and row.rank == 1 and row.column == 1
    )
    assert not pair.request_c1_move(
        c1.order_id,
        replacement_price=D("1"),
        new_value=D("1.03"),
        current_value=D("1"),
        lost_fifo_value=D("0.01"),
        cancel_cost=D("0.01"),
        reentry_cost=D("0.01"),
        now_us=1,
    )
    assert c1.status == OrderStatus.ACTIVE
    assert pair.request_c1_move(
        c1.order_id,
        replacement_price=D("1"),
        new_value=D("1.04"),
        current_value=D("1"),
        lost_fifo_value=D("0.01"),
        cancel_cost=D("0.01"),
        reentry_cost=D("0.01"),
        now_us=2,
    )
    assert c1.status == OrderStatus.CANCEL_PENDING


def test_no_self_fill() -> None:
    pair = engine("PAIR_A", "USDCUSDT", "USDC")
    order = next(iter(pair.state.orders.values()))
    with pytest.raises(ValueError, match="M035_SELF_FILL_PROHIBITED"):
        pair.consume_public_trade(
            trade_id=order.order_id,
            side=order.side,
            price=order.price,
            quantity=D("1"),
            now_us=1,
            source="OWN_ORDER",
        )


def test_attributable_cost_survives_same_price_mark_update() -> None:
    ledger = GlobalCapitalLedger()
    capital_id = ParallelPairCapitalAllocator(ledger).allocate(
        [candidate("COST", "PAIR_A", "10")], now_us=1
    )[0].capital_id
    ledger.record_entry_fill(
        capital_id,
        asset="USDC",
        quantity_net=D("10"),
        causal_mark_usdt=D("1"),
        attributable_cost_usdt=D("1"),
        input_usdt=D("10"),
        now_us=2,
    )
    assert ledger.marked_equity({}) == D("199")
    ledger.update_mark(capital_id, mark_usdt=D("1"), now_us=3)
    assert ledger.marked_equity({}) == D("199")


def test_attributable_cost_is_physically_debited_and_survives_settlement() -> None:
    ledger = GlobalCapitalLedger()
    capital_id = ParallelPairCapitalAllocator(ledger).allocate(
        [candidate("COST-CYCLE", "PAIR_A", "10")], now_us=1
    )[0].capital_id
    ledger.record_entry_fill(
        capital_id,
        asset="USDC",
        quantity_net=D("10"),
        causal_mark_usdt=D("1"),
        attributable_cost_usdt=D("1"),
        input_usdt=D("10"),
        now_us=2,
    )
    assert ledger.free_usdt == D("189")
    ledger.reserve_owned_return(capital_id, now_us=3)
    realized = ledger.settle_return(
        capital_id,
        cycle_id="COST-CYCLE",
        sold_quantity=D("10"),
        net_proceeds_usdt=D("11"),
        residual_mark_usdt=D("0"),
        now_us=4,
    )
    assert realized == D("0")
    assert ledger.free_usdt == D("200")
    assert ledger.marked_equity() == D("200")
    assert ledger.cycles.aggregate_pnl_usdt == D("0")
    assert ledger.zero_loss_economic_pass()


def test_partial_racing_fill_preserves_remaining_cancel_reservation() -> None:
    ledger = GlobalCapitalLedger()
    capital_id = ParallelPairCapitalAllocator(ledger).allocate(
        [candidate("PARTIAL", "PAIR_A", "10")], now_us=1
    )[0].capital_id
    ledger.request_cancel(capital_id, now_us=2)
    inventory_id = ledger.record_entry_fill(
        capital_id,
        asset="USDC",
        quantity_net=D("5"),
        causal_mark_usdt=D("1"),
        attributable_cost_usdt=D("0"),
        input_usdt=D("5"),
        now_us=3,
    )
    assert inventory_id != capital_id
    assert ledger.positions[capital_id].state == CapitalState.CANCEL_PENDING
    assert ledger.positions[capital_id].marked_value_usdt == D("5")
    assert ledger.positions[inventory_id].marked_value_usdt == D("5")
    assert ledger.marked_equity({}) == D("200")
    assert ledger.acknowledge_cancel(capital_id, now_us=4) == D("5")
    assert ledger.free_usdt == D("195")
    assert ledger.marked_equity({}) == D("200")


def test_c2_racing_fill_ack_cancels_only_remainder_without_replacement() -> None:
    ledger = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(ledger)
    pair = PairEngine(
        pair_id="PAIR_A",
        symbol="USDCUSDT",
        pair_asset="USDC",
        tick_size=D("0.0001"),
        capital_ledger=ledger,
    )
    pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    pair.initialize_grid(now_us=0)
    c1 = next(
        row
        for row in pair.state.orders.values()
        if row.side == "BUY" and row.rank == 1 and row.column == 1
    )
    c2 = next(
        row
        for row in pair.state.orders.values()
        if row.side == "BUY" and row.rank == 1 and row.column == 2
    )
    grants = allocator.allocate(
        [candidate("C1", "PAIR_A", "0.9999"), candidate("C2", "PAIR_A", "0.9999")],
        now_us=1,
    )
    pair.bind_order_capital(c1.order_id, grants[0].capital_id, now_us=1)
    pair.bind_order_capital(c2.order_id, grants[1].capital_id, now_us=1)
    pair.receive_book(bid=D("1.0001"), ask=D("1.0003"), now_us=10)
    assert c2.status == OrderStatus.CANCEL_PENDING
    fills = pair.consume_public_trade(
        trade_id="RACE",
        side=c2.side,
        price=c2.price,
        quantity=D("1.5"),
        now_us=11,
        source="PUBLIC_TRADE",
    )
    assert fills[c2.order_id] == D("0.5")
    assert pair.acknowledge_grid_cancel(c2.order_id, now_us=12) is None
    assert c2.status == OrderStatus.PARTIAL_FILLED
    assert c2.order_id not in pair.queue.order_group


def test_c2_replacement_uses_latest_hotline_at_ack() -> None:
    pair = engine("PAIR_A", "USDCUSDT", "USDC")
    c2 = next(
        row
        for row in pair.state.orders.values()
        if row.side == "BUY" and row.rank == 1 and row.column == 2
    )
    pair.receive_book(bid=D("1.0002"), ask=D("1.0004"), now_us=10)
    assert c2.replacement_price == D("1.0002")
    pair.receive_book(bid=D("1.0005"), ask=D("1.0007"), now_us=11)
    assert c2.replacement_price == D("1.0005")
    replacement = pair.acknowledge_grid_cancel(c2.order_id, now_us=12)
    assert replacement is not None
    assert replacement.price == D("1.0005")


def test_trade_cannot_precede_latest_pair_book() -> None:
    pair = engine("PAIR_A", "USDCUSDT", "USDC")
    pair.receive_book(bid=D("1.0001"), ask=D("1.0003"), now_us=100)
    order = next(row for row in pair.state.orders.values() if row.status == OrderStatus.ACTIVE)
    with pytest.raises(ValueError, match="M035_NONCAUSAL_PAIR_EVENT"):
        pair.consume_public_trade(
            trade_id="PAST",
            side=order.side,
            price=order.price,
            quantity=D("1"),
            now_us=50,
            source="PUBLIC_TRADE",
        )


def test_unfunded_order_cannot_consume_trade_or_mutate_state() -> None:
    ledger = GlobalCapitalLedger()
    pair = PairEngine(
        pair_id="PAIR_A",
        symbol="USDCUSDT",
        pair_asset="USDC",
        tick_size=D("0.0001"),
        capital_ledger=ledger,
    )
    pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    pair.initialize_grid(now_us=0)
    order = next(iter(pair.state.orders.values()))
    assert order.status == OrderStatus.UNFUNDED
    assert order.order_id not in pair.queue.order_group
    fills = pair.consume_public_trade(
        trade_id="UNFUNDED",
        side=order.side,
        price=order.price,
        quantity=D("1"),
        now_us=1,
        source="PUBLIC_TRADE",
    )
    assert fills == {}
    assert order.status == OrderStatus.UNFUNDED
    assert order.filled_quantity == D("0")
    assert pair.state.inventory_quantity == D("0")
    assert ledger.free_usdt == D("200")


def test_insufficient_funding_is_rejected_before_queue_activation() -> None:
    ledger = GlobalCapitalLedger()
    pair = PairEngine(
        pair_id="PAIR_A",
        symbol="USDCUSDT",
        pair_asset="USDC",
        tick_size=D("0.0001"),
        capital_ledger=ledger,
    )
    pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    pair.initialize_grid(now_us=0)
    order = next(iter(pair.state.orders.values()))
    capital_id = ParallelPairCapitalAllocator(ledger).allocate(
        [candidate("TOO-SMALL", "PAIR_A", "0.5")], now_us=1
    )[0].capital_id
    with pytest.raises(ValueError, match="M035_ORDER_CAPITAL_OWNER_MISMATCH"):
        pair.bind_order_capital(order.order_id, capital_id, now_us=1)
    assert order.status == OrderStatus.UNFUNDED
    assert order.order_id not in pair.queue.order_group
    assert ledger.positions[capital_id].marked_value_usdt == D("0.5")


def test_same_capital_id_cannot_fund_two_orders() -> None:
    ledger = GlobalCapitalLedger()
    pair = PairEngine(
        pair_id="PAIR_A",
        symbol="USDCUSDT",
        pair_asset="USDC",
        tick_size=D("0.0001"),
        capital_ledger=ledger,
    )
    pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    pair.initialize_grid(now_us=0)
    orders = list(pair.state.orders.values())[:2]
    capital_id = ParallelPairCapitalAllocator(ledger).allocate(
        [candidate("ONE-OWNER", "PAIR_A", "1")], now_us=1
    )[0].capital_id
    pair.bind_order_capital(orders[0].order_id, capital_id, now_us=1)
    with pytest.raises(ValueError, match="M035_ORDER_ALREADY_FUNDED"):
        pair.bind_order_capital(orders[1].order_id, capital_id, now_us=1)


def test_engine_cancel_ack_releases_bound_capital_and_replacement_is_unfunded() -> None:
    ledger = GlobalCapitalLedger()
    pair = PairEngine(
        pair_id="PAIR_A",
        symbol="USDCUSDT",
        pair_asset="USDC",
        tick_size=D("0.0001"),
        capital_ledger=ledger,
    )
    pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    pair.initialize_grid(now_us=0)
    c2 = next(
        row
        for row in pair.state.orders.values()
        if row.side == "BUY" and row.rank == 1 and row.column == 2
    )
    capital_id = ParallelPairCapitalAllocator(ledger).allocate(
        [candidate("MOBILE", "PAIR_A", "0.9999")], now_us=1
    )[0].capital_id
    pair.bind_order_capital(c2.order_id, capital_id, now_us=1)
    pair.receive_book(bid=D("1.0001"), ask=D("1.0003"), now_us=2)
    assert ledger.positions[capital_id].state == CapitalState.CANCEL_PENDING
    replacement = pair.acknowledge_grid_cancel(c2.order_id, now_us=3)
    assert replacement is not None
    assert replacement.status == OrderStatus.UNFUNDED
    assert replacement.capital_id is None
    assert capital_id not in ledger.positions
    assert ledger.free_usdt == D("200")


def test_book_marks_open_inventory_and_global_zero_loss_fails() -> None:
    ledger = GlobalCapitalLedger()
    pair = PairEngine(
        pair_id="PAIR_A",
        symbol="USDCUSDT",
        pair_asset="USDC",
        tick_size=D("0.0001"),
        capital_ledger=ledger,
    )
    pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    pair.initialize_grid(now_us=0)
    order = next(iter(pair.state.orders.values()))
    capital_id = ParallelPairCapitalAllocator(ledger).allocate(
        [candidate("MARK", "PAIR_A", "0.9999")], now_us=1
    )[0].capital_id
    pair.bind_order_capital(order.order_id, capital_id, now_us=1)
    pair.consume_public_trade(
        trade_id="BUY",
        side="BUY",
        price=D("0.9999"),
        quantity=D("1"),
        now_us=2,
        source="PUBLIC_TRADE",
    )
    pair.receive_book(bid=D("0.90"), ask=D("0.9002"), now_us=3)
    assert ledger.marked_equity() == D("199.9001")
    assert not ledger.zero_loss_economic_pass()


def test_negative_normal_settlement_is_blocked_and_risk_exit_is_attributed() -> None:
    ledger = GlobalCapitalLedger()
    capital_id = ParallelPairCapitalAllocator(ledger).allocate(
        [candidate("LOSS", "PAIR_A", "10")], now_us=1
    )[0].capital_id
    ledger.record_entry_fill(
        capital_id,
        asset="USDC",
        quantity_net=D("10"),
        causal_mark_usdt=D("1"),
        attributable_cost_usdt=D("0"),
        now_us=2,
    )
    ledger.reserve_owned_return(capital_id, now_us=3)
    with pytest.raises(ValueError, match="M035_NEGATIVE_ORDINARY_CYCLE_PROHIBITED"):
        ledger.settle_return(
            capital_id,
            cycle_id="LOSS",
            sold_quantity=D("10"),
            net_proceeds_usdt=D("9"),
            residual_mark_usdt=D("0"),
            now_us=4,
        )
    assert capital_id in ledger.positions
    assert not ledger.cycles.cycles
    ledger.register_risk_exit_authorization(
        RiskExitAuthorization(
            authorization_id="AUTH-1",
            capital_id=capital_id,
            pair_id="PAIR_A",
            decided_at_us=4,
            expires_at_us=5,
            rule_hash="frozen-rule-hash",
            quantity=D("10"),
            expected_hold_loss_usdt=D("2"),
            opportunity_cost_usdt=D("0"),
            tail_risk_usdt=D("0"),
            loss_if_exit_now_usdt=D("1"),
        ),
        now_us=4,
    )
    ledger.settle_return(
        capital_id,
        cycle_id="RISK-LOSS",
        sold_quantity=D("10"),
        net_proceeds_usdt=D("9"),
        residual_mark_usdt=D("0"),
        now_us=5,
        risk_exit_authorization_id="AUTH-1",
    )
    assert ledger.cycles.negative_closed_cycles == 1
    assert ledger.cycles.negative_risk_exits == 1
    assert not ledger.cycles.zero_loss_economic_pass


def test_duplicate_cycle_rejection_is_atomic_before_any_credit() -> None:
    ledger = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(ledger)
    grants = allocator.allocate(
        [candidate("DUP-A", "PAIR_A", "1"), candidate("DUP-B", "PAIR_A", "1")],
        now_us=1,
    )
    for grant in grants:
        ledger.record_entry_fill(
            grant.capital_id,
            asset="USDC",
            quantity_net=D("1"),
            causal_mark_usdt=D("1"),
            attributable_cost_usdt=D("0"),
            input_usdt=D("1"),
            now_us=2,
        )
    for grant in grants:
        ledger.reserve_owned_return(grant.capital_id, now_us=3)
    ledger.settle_return(
        grants[0].capital_id,
        cycle_id="SAME",
        sold_quantity=D("1"),
        net_proceeds_usdt=D("1.01"),
        residual_mark_usdt=D("0"),
        now_us=4,
    )
    free_before = ledger.free_usdt
    positions_before = {
        key: (row.state, row.quantity, row.marked_value_usdt)
        for key, row in ledger.positions.items()
    }
    audit_before = list(ledger.audit)
    cycles_before = dict(ledger.cycles.cycles)
    with pytest.raises(ValueError, match="M035_INVALID_OR_DUPLICATE_CYCLE"):
        ledger.settle_return(
            grants[1].capital_id,
            cycle_id="SAME",
            sold_quantity=D("1"),
            net_proceeds_usdt=D("1.01"),
            residual_mark_usdt=D("0"),
            now_us=4,
        )
    assert ledger.free_usdt == free_before
    assert {
        key: (row.state, row.quantity, row.marked_value_usdt)
        for key, row in ledger.positions.items()
    } == positions_before
    assert ledger.audit == audit_before
    assert ledger.cycles.cycles == cycles_before


def test_public_fill_updates_order_pair_inventory_and_shared_capital() -> None:
    ledger = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(ledger)
    pair_a = PairEngine(
        pair_id="PAIR_A",
        symbol="USDCUSDT",
        pair_asset="USDC",
        tick_size=D("0.0001"),
        capital_ledger=ledger,
    )
    pair_a.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    pair_a.initialize_grid(now_us=0)
    order = next(
        row
        for row in pair_a.state.orders.values()
        if row.side == "BUY" and row.rank == 1 and row.column == 1
    )
    capital_id = allocator.allocate(
        [candidate("PHYSICAL-A", "PAIR_A", "0.9999")], now_us=1
    )[0].capital_id
    pair_a.bind_order_capital(order.order_id, capital_id, now_us=1)
    fills = pair_a.consume_public_trade(
        trade_id="PUBLIC-A",
        side="BUY",
        price=D("0.9999"),
        quantity=D("1"),
        now_us=2,
        source="PUBLIC_TRADE",
    )
    assert fills == {order.order_id: D("1")}
    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == D("1")
    assert pair_a.state.inventory_quantity == D("1")
    assert order.inventory_capital_ids == [capital_id]
    assert ledger.positions[capital_id].asset == "USDC"
    assert ledger.owner_of(capital_id) == "PAIR_A"
    assert ledger.marked_equity({}) == D("200")


def test_complete_cycle_requires_public_entry_and_return_fills() -> None:
    ledger = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(ledger)
    pair = PairEngine(
        pair_id="PAIR_A",
        symbol="USDCUSDT",
        pair_asset="USDC",
        tick_size=D("0.0001"),
        capital_ledger=ledger,
    )
    pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    pair.initialize_grid(now_us=0)
    entry = next(iter(pair.state.orders.values()))
    capital_id = allocator.allocate(
        [candidate("ROUNDTRIP", "PAIR_A", "0.9999")], now_us=1
    )[0].capital_id
    pair.bind_order_capital(entry.order_id, capital_id, now_us=1)
    pair.consume_public_trade(
        trade_id="ENTRY-PRINT",
        side="BUY",
        price=D("0.9999"),
        quantity=D("1"),
        now_us=2,
        source="PUBLIC_TRADE",
    )
    return_order = pair.submit_owned_return(
        capital_id,
        cycle_id="ROUNDTRIP-1",
        price=D("1.0001"),
        quantity=D("1"),
        now_us=3,
    )
    assert capital_id in ledger.positions
    assert not ledger.cycles.cycles
    pair.consume_public_trade(
        trade_id="RETURN-PRINT",
        side="SELL",
        price=D("1.0001"),
        quantity=D("1"),
        now_us=4,
        source="PUBLIC_TRADE",
    )
    assert return_order.status == OrderStatus.FILLED
    assert pair.state.cycle_history == ["ROUNDTRIP-1"]
    assert pair.state.inventory_quantity == D("0")
    assert ledger.cycles.aggregate_pnl_usdt == D("0.0002")
    assert ledger.free_usdt == D("200.0002")
    assert ledger.zero_loss_economic_pass()


def test_active_return_is_not_repriced_by_hotline_grid_reconciliation() -> None:
    ledger = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(ledger)
    pair = PairEngine(
        pair_id="PAIR_A",
        symbol="USDCUSDT",
        pair_asset="USDC",
        tick_size=D("0.0001"),
        capital_ledger=ledger,
    )
    pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    pair.initialize_grid(now_us=0)
    entry = next(iter(pair.state.orders.values()))
    capital_id = allocator.allocate(
        [candidate("RETURN-STABLE", "PAIR_A", "0.9999")], now_us=1
    )[0].capital_id
    pair.bind_order_capital(entry.order_id, capital_id, now_us=1)
    pair.consume_public_trade(
        trade_id="ENTRY", side="BUY", price=D("0.9999"), quantity=D("1"), now_us=2,
        source="PUBLIC_TRADE",
    )
    return_order = pair.submit_owned_return(
        capital_id, cycle_id="RETURN-STABLE-1", price=D("1.0005"), quantity=D("1"), now_us=3
    )
    pair.receive_book(bid=D("1.0002"), ask=D("1.0004"), now_us=4)
    assert return_order.status == OrderStatus.ACTIVE
    assert return_order.price == D("1.0005")
    assert return_order.order_id in pair.queue.order_group


def test_partial_public_return_updates_ledger_immediately_without_closing_cycle() -> None:
    ledger = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(ledger)
    pair = PairEngine(
        pair_id="PAIR_A", symbol="USDCUSDT", pair_asset="USDC",
        tick_size=D("0.0001"), capital_ledger=ledger,
    )
    pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    pair.initialize_grid(now_us=0)
    entry = next(iter(pair.state.orders.values()))
    capital_id = allocator.allocate(
        [candidate("PARTIAL-RETURN", "PAIR_A", "0.9999")], now_us=1
    )[0].capital_id
    pair.bind_order_capital(entry.order_id, capital_id, now_us=1)
    pair.consume_public_trade(
        trade_id="ENTRY", side="BUY", price=D("0.9999"), quantity=D("1"), now_us=2,
        source="PUBLIC_TRADE",
    )
    return_order = pair.submit_owned_return(
        capital_id, cycle_id="PARTIAL-RETURN-1", price=D("1.0001"), quantity=D("1"), now_us=3
    )
    pair.consume_public_trade(
        trade_id="RETURN-PARTIAL", side="SELL", price=D("1.0001"), quantity=D("0.5"),
        now_us=4, source="PUBLIC_TRADE",
    )
    assert return_order.status == OrderStatus.PARTIAL
    assert ledger.positions[capital_id].quantity == D("0.5")
    assert pair.state.inventory_quantity == D("0.5")
    assert ledger.free_usdt == D("199.50015")
    assert ledger.marked_equity() == D("200.00010")
    assert not ledger.cycles.cycles
    assert not pair.state.cycle_history


def test_negative_return_rejection_is_atomic_before_trade_consumption() -> None:
    ledger = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(ledger)
    pair = PairEngine(
        pair_id="PAIR_A", symbol="USDCUSDT", pair_asset="USDC",
        tick_size=D("0.0001"), capital_ledger=ledger,
    )
    pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    pair.initialize_grid(now_us=0)
    entry = next(iter(pair.state.orders.values()))
    capital_id = allocator.allocate(
        [candidate("ATOMIC-LOSS", "PAIR_A", "0.9999")], now_us=1
    )[0].capital_id
    pair.bind_order_capital(entry.order_id, capital_id, now_us=1)
    pair.consume_public_trade(
        trade_id="ENTRY", side="BUY", price=D("0.9999"), quantity=D("1"), now_us=2,
        source="PUBLIC_TRADE",
    )
    return_order = pair.submit_owned_return(
        capital_id, cycle_id="ATOMIC-LOSS-1", price=D("0.90"), quantity=D("1"), now_us=3
    )
    queue_before = pair.queue.queue_ahead(return_order.order_id)
    with pytest.raises(ValueError, match="M035_NEGATIVE_ORDINARY_CYCLE_PROHIBITED"):
        pair.consume_public_trade(
            trade_id="NEGATIVE", side="SELL", price=D("0.90"), quantity=D("1"), now_us=4,
            source="PUBLIC_TRADE",
        )
    assert return_order.status == OrderStatus.ACTIVE
    assert return_order.filled_quantity == D("0")
    assert pair.queue.queue_ahead(return_order.order_id) == queue_before
    assert "USDCUSDT:NEGATIVE" not in pair.queue.processed_event_ids
    assert ledger.positions[capital_id].quantity == D("1")
    assert pair.state.inventory_quantity == D("1")


def test_two_owned_returns_same_price_use_distinct_fifo_columns() -> None:
    ledger = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(ledger)
    pair = PairEngine(
        pair_id="PAIR_A", symbol="USDCUSDT", pair_asset="USDC",
        tick_size=D("0.0001"), capital_ledger=ledger,
    )
    pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    pair.initialize_grid(now_us=0)
    entries = list(pair.state.orders.values())[:2]
    grants = allocator.allocate(
        [candidate("RET-A", "PAIR_A", "0.9999"), candidate("RET-B", "PAIR_A", "0.9999")],
        now_us=1,
    )
    for order, grant in zip(entries, grants, strict=True):
        pair.bind_order_capital(order.order_id, grant.capital_id, now_us=1)
    pair.consume_public_trade(
        trade_id="TWO-ENTRIES", side="BUY", price=D("0.9999"), quantity=D("2"), now_us=2,
        source="PUBLIC_TRADE",
    )
    first = pair.submit_owned_return(
        grants[0].capital_id, cycle_id="RET-A-1", price=D("1.0001"), quantity=D("1"), now_us=3
    )
    second = pair.submit_owned_return(
        grants[1].capital_id, cycle_id="RET-B-1", price=D("1.0001"), quantity=D("1"), now_us=3
    )
    assert (first.column, second.column) == (1, 2)
    assert ledger.positions[grants[0].capital_id].state == CapitalState.RETURN_PAIR_A
    assert ledger.positions[grants[1].capital_id].state == CapitalState.RETURN_PAIR_A


def test_integrated_fee_dust_survives_return_and_can_be_aggregated() -> None:
    ledger = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(ledger)
    pair = PairEngine(
        pair_id="PAIR_A", symbol="USDCUSDT", pair_asset="USDC",
        tick_size=D("0.0001"), capital_ledger=ledger,
    )
    pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    pair.initialize_grid(now_us=0)
    entry = next(iter(pair.state.orders.values()))
    capital_id = allocator.allocate(
        [candidate("DUST-PATH", "PAIR_A", "0.9999")], now_us=1
    )[0].capital_id
    pair.bind_order_capital(entry.order_id, capital_id, now_us=1)
    pair.consume_public_trade(
        trade_id="DUST-ENTRY", side="BUY", price=D("0.9999"), quantity=D("1"), now_us=2,
        source="PUBLIC_TRADE", fee_rate=D("0.0001"),
    )
    assert ledger.positions[capital_id].quantity == D("0.9999")
    pair.submit_owned_return(
        capital_id, cycle_id="DUST-PATH-1", price=D("1.0001"), quantity=D("0.9"), now_us=3
    )
    pair.consume_public_trade(
        trade_id="DUST-RETURN", side="SELL", price=D("1.0001"), quantity=D("0.9"), now_us=4,
        source="PUBLIC_TRADE",
    )
    assert ledger.dust.quantity("USDC", pair_id="PAIR_A") == D("0.0999")
    assert pair.state.dust_quantity == D("0.0999")
    assert ledger.cycles.negative_closed_cycles == 0
    assert ledger.dust.tradeable_quantity(
        "USDC", step_size=D("0.01"), minimum_quantity=D("0.01"), pair_id="PAIR_A"
    ) == D("0.09")
    aggregated = ledger.reserve_aggregated_dust(
        pair_id="PAIR_A", asset="USDC", quantity=D("0.09"), mark_usdt=D("0.9999"), now_us=5
    )
    assert ledger.positions[aggregated].source_cycles == ("DUST-PATH-1",)
    assert ledger.dust.quantity("USDC", pair_id="PAIR_A") == D("0.0099")


def test_future_book_cannot_change_past_hotline_decision() -> None:
    pair = engine("PAIR_A", "USDCUSDT", "USDC")
    cutoff = 10
    at_cutoff = pair.hotline_at(cutoff)
    pair.receive_book(bid=D("1.0099"), ask=D("1.0101"), now_us=11)
    assert pair.hotline_at(cutoff) == at_cutoff
    with pytest.raises(ValueError, match="M035_NONCAUSAL_PAIR_EVENT"):
        pair.receive_book(bid=D("0.9998"), ask=D("1.0000"), now_us=10)


def test_pair_queues_consume_public_trades_independently() -> None:
    ledger = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(ledger)
    pair_a = PairEngine(
        pair_id="PAIR_A",
        symbol="USDCUSDT",
        pair_asset="USDC",
        tick_size=D("0.0001"),
        capital_ledger=ledger,
    )
    pair_b = PairEngine(
        pair_id="PAIR_B",
        symbol="FDUSDUSDT",
        pair_asset="FDUSD",
        tick_size=D("0.0001"),
        capital_ledger=ledger,
    )
    for pair in (pair_a, pair_b):
        pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
        pair.initialize_grid(now_us=0)
    a_order = next(iter(pair_a.state.orders.values()))
    b_order = next(iter(pair_b.state.orders.values()))
    grants = allocator.allocate(
        [candidate("A", "PAIR_A", "0.9999"), candidate("B", "PAIR_B", "0.9999")],
        now_us=1,
    )
    pair_a.bind_order_capital(a_order.order_id, grants[0].capital_id, now_us=1)
    pair_b.bind_order_capital(b_order.order_id, grants[1].capital_id, now_us=1)
    a_fill = pair_a.consume_public_trade(
        trade_id="T1",
        side=a_order.side,
        price=a_order.price,
        quantity=D("1"),
        now_us=1,
        source="PUBLIC_TRADE",
    )
    b_fill = pair_b.consume_public_trade(
        trade_id="T1",
        side=b_order.side,
        price=b_order.price,
        quantity=D("1"),
        now_us=1,
        source="PUBLIC_TRADE",
    )
    assert a_fill == {a_order.order_id: D("1")}
    assert b_fill == {b_order.order_id: D("1")}


def test_initial_bank_is_exactly_200() -> None:
    assert GlobalCapitalLedger().free_usdt == D("200")
    with pytest.raises(ValueError, match="M035_INITIAL_BANK_MUST_EQUAL_200"):
        GlobalCapitalLedger(D("400"))
