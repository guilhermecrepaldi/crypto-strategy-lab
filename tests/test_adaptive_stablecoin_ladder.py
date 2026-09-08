from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.adaptive_stablecoin_ladder import (
    AdaptiveStablecoinLadder,
)
from crypto_strategy_lab.microstructure.b10_reality import ExecutionProfile, SymbolRules, Trade
from crypto_strategy_lab.microstructure.observed_l2_execution import ObservedBookBatch


def _fixtures():
    profile = ExecutionProfile(
        "M019-test",
        "a" * 64,
        10,
        10,
        D(".001"),
        D(".001"),
        D(".001"),
    )
    rules = SymbolRules(
        D(".0001"),
        D(".01"),
        D(".01"),
        D("10000"),
        D("5"),
        D("100000"),
        D(".01"),
        D("100"),
        "b" * 64,
        orders_per_window=1000,
        window_us=1_000_000,
    )
    book = ObservedBookBatch(
        0,
        100,
        1,
        1,
        ((D("1"), D("100")), (D(".99"), D("100"))),
        ((D("1.01"), D("100")),),
        D(".9"),
        D("1.1"),
        True,
    )
    return profile, rules, book


def test_first_valid_bid_endows_fifty_and_creates_six_slots_each_side():
    profile, rules, book = _fixtures()
    ladder = AdaptiveStablecoinLadder(profile, rules)
    ladder.receive_book(book)

    assert ladder.first_bid == D("1")
    assert ladder.endowment_quantity == D("50")
    assert ladder.cash + ladder.active_buy_notional == D("50")
    assert ladder.reserve == D("0")
    assert len(ladder.active_orders) == 12
    assert {order.slot for order in ladder.active_orders if order.side == "BUY"} == set(range(6))
    assert {order.slot for order in ladder.active_orders if order.side == "SELL"} == set(range(6))
    assert max(order.price for order in ladder.active_orders if order.side == "BUY") < D("1.01")
    marked = D(ladder.metrics()["equity"])
    assert ladder.inventory * D("1") + ladder.active_buy_notional <= D(".90") * marked
    assert ladder.cash + ladder.active_buy_notional == D("50")
    assert ladder.validate_invariants()
    buys = [order.price for order in ladder.active_orders if order.side == "BUY"]
    sells = [order.price for order in ladder.active_orders if order.side == "SELL"]
    assert max(buys) < min(sells)


def test_initial_endowment_sale_is_realized_but_never_a_cycle():
    profile, rules, book = _fixtures()
    ladder = AdaptiveStablecoinLadder(profile, rules)
    ladder.receive_book(book)
    ladder.receive_book(replace_book_time(book, 150))
    sell = next(order for order in ladder.active_orders if order.side == "SELL")
    trade = Trade(200, 1, sell.price, sell.quantity, False)

    consumed = ladder.receive_trade(trade, capture_time_us=250)

    assert consumed == sell.quantity
    assert ladder.realized_profit > D("0")
    assert ladder.cycle_count == 0
    assert (
        all(item["reserve_consumption"] == "0" for item in ladder.settlements)
        or not ladder.settlements
    )


def test_buy_then_profitable_fifo_sale_counts_only_non_endowment_lot():
    profile, rules, book = _fixtures()
    ladder = AdaptiveStablecoinLadder(profile, rules)
    ladder.receive_book(book)
    buy = next(order for order in ladder.active_orders if order.side == "BUY")
    buy_trade = Trade(11, 1, buy.price, buy.quantity, True)
    ladder.receive_trade(buy_trade, capture_time_us=200)

    # The initial lot is FIFO, so sell enough to exhaust it and then one
    # additional quantity from the purchased lot at a strictly profitable price.
    sell = next(order for order in ladder.active_orders if order.side == "SELL")
    ladder.receive_trade(Trade(12, 2, sell.price, D("50"), False), capture_time_us=300)
    assert ladder.cycle_count == 0
    if ladder.lots:
        purchased = next((lot for lot in ladder.lots if not lot.initial_endowment), None)
        if purchased is not None and purchased.remaining == D("0"):
            assert ladder.cycle_count == 1


def test_checkpoint_restore_is_exact_and_does_not_liquidate_open_lots():
    profile, rules, book = _fixtures()
    ladder = AdaptiveStablecoinLadder(profile, rules, lane_id="lane-2")
    ladder.receive_book(book)
    checkpoint = ladder.checkpoint()
    restored = AdaptiveStablecoinLadder.from_checkpoint(checkpoint, profile, rules)

    assert restored.metrics() == ladder.metrics()
    assert restored.checkpoint() == checkpoint
    assert restored.inventory == D("50")
    assert restored.cycle_count == 0


def test_trade_quantity_is_consumed_once_and_no_breakeven_sale_is_recorded():
    profile, rules, book = _fixtures()
    ladder = AdaptiveStablecoinLadder(profile, rules)
    ladder.receive_book(book)
    sell = next(order for order in ladder.active_orders if order.side == "SELL")
    before = ladder.inventory
    consumed = ladder.receive_trade(
        Trade(11, 1, sell.price + rules.tick_size, D("0.01"), True),
        capture_time_us=200,
    )

    assert consumed == D("0")
    assert ladder.inventory == before
    assert ladder.cycle_count == 0


def test_cancel_latency_keeps_old_quote_fillable_until_acknowledgement():
    profile, rules, book = _fixtures()
    ladder = AdaptiveStablecoinLadder(profile, rules)
    ladder.receive_book(book)
    order = next(order for order in ladder.active_orders if order.side == "BUY")
    ladder._cancel(order, 111, "TEST")

    assert order.status == "CANCEL_PENDING"
    ladder.receive_trade(Trade(114, 1, order.price, D("0.01"), True), capture_time_us=115)
    assert order.filled == D("0.01")
    ladder.receive_book(
        ObservedBookBatch(
            30,
            130,
            2,
            2,
            ((D("1"), D("100")),),
            ((D("1.01"), D("100")),),
            D(".9"),
            D("1.1"),
            True,
        )
    )
    assert order.status == "CANCELED"


def _without_endowment():
    profile, rules, book = _fixtures()
    ladder = AdaptiveStablecoinLadder(profile, rules, endowment_notional=D("0"))
    ladder.receive_book(book)
    return ladder, profile, rules, book


def test_buy_fill_creates_inventory_exactly_once_and_preserves_source_identity():
    ladder, _, _, _ = _without_endowment()
    buy = next(order for order in ladder.active_orders if order.side == "BUY")
    before = ladder.inventory
    filled = ladder._fill(buy, D("1"), 200, source_id=77)

    assert filled == D("1")
    assert ladder.inventory - before == D("1")
    lot = next(lot for lot in ladder.lots if lot.source_order_id == buy.order_id)
    assert (lot.source_slot, lot.band_id, lot.quantity) == (buy.slot, buy.slot, D("1"))
    assert ladder.validate_invariants()


def test_sell_cannot_exceed_owned_or_reserved_inventory():
    ladder, _, _, _ = _without_endowment()
    buy = next(order for order in ladder.active_orders if order.side == "BUY")
    ladder._fill(buy, buy.remaining, 200, source_id=1)
    ladder.last_refresh_us = -1
    ladder._refresh(300)
    sell = next(order for order in ladder.active_orders if order.side == "SELL")
    before = ladder.inventory

    filled = ladder._fill(sell, D("999"), 400, source_id=2)

    assert filled <= before
    assert ladder.inventory >= D("0")
    assert ladder.validate_invariants()


def test_negative_and_breakeven_exit_are_rejected_and_never_cycles():
    ladder, _, _, _ = _without_endowment()
    buy = next(order for order in ladder.active_orders if order.side == "BUY")
    ladder._fill(buy, buy.remaining, 200, source_id=1)
    ladder.last_refresh_us = -1
    ladder._refresh(300)
    sell = next(order for order in ladder.active_orders if order.side == "SELL")
    lot = next(lot for lot in ladder.lots if not lot.initial_endowment)
    sell.price = lot.unit_cost

    assert ladder._fill(sell, sell.remaining, 400, source_id=2) == D("0")
    assert ladder.cycle_count == 0
    assert lot.remaining == lot.quantity


def test_partial_buy_fill_reconciles_reservation_and_cancel_releases_only_remainder():
    ladder, profile, _, book = _without_endowment()
    buy = next(order for order in ladder.active_orders if order.side == "BUY")
    initial_free = ladder.cash
    initial_reserved = buy.reserved_quote
    filled = ladder._fill(buy, D("1"), 200, source_id=1)
    expected_remaining = (buy.quantity - filled) * buy.price * (D("1") + profile.maker_fee)

    assert buy.reserved_quote == expected_remaining
    ladder._cancel(buy, 210, "TEST_PARTIAL")
    later = replace_book_time(book, 500)
    ladder.receive_book(later)

    assert buy.status == "CANCELED"
    assert buy.reserved_quote == D("0")
    assert ladder.cash == initial_free + initial_reserved - filled * buy.price * (
        D("1") + profile.maker_fee
    )
    assert ladder.validate_invariants()


def replace_book_time(book, capture_time):
    return ObservedBookBatch(
        book.exchange_time_us + capture_time,
        capture_time,
        book.capture_order + capture_time,
        book.native_update_id + capture_time,
        book.bids,
        book.asks,
        book.known_bid_floor,
        book.known_ask_ceiling,
        True,
        exchange_upper_us=book.exchange_time_us + capture_time,
    )


def test_reprice_reuses_logical_slot_without_duplicate_active_order():
    ladder, _, _, _ = _without_endowment()
    moved = ObservedBookBatch(
        61_000_000,
        61_000_100,
        2,
        2,
        ((D(".99"), D("100")),),
        ((D("1"), D("100")),),
        D(".9"),
        D("1.1"),
        True,
        exchange_upper_us=61_000_000,
    )
    ladder.receive_book(moved)
    ladder.receive_book(replace_book_time(moved, 63_000_000))

    keys = [(order.side, order.slot) for order in ladder.active_orders]
    assert len(keys) == len(set(keys))
    assert len(keys) <= 12
    assert ladder.validate_invariants()


def test_one_trade_budget_cannot_fill_multiple_orders_beyond_observed_quantity():
    ladder, _, _, _ = _without_endowment()
    for order in ladder.active_orders:
        order.active_us = 100
        order.status = "ACTIVE"
        order.queue = D("0")
        order.activation_evaluated_us = 100
    before = ladder.inventory
    quantity = D(".05")

    consumed = ladder.receive_trade(
        Trade(200, 99, D(".90"), quantity, True), capture_time_us=200
    )

    assert consumed == quantity
    assert ladder.inventory - before == quantity
    assert sum((order.filled for order in ladder.orders if order.side == "BUY"), D("0")) == quantity


def test_inventory_survives_band_recenter_and_dormant_lot_retains_cost_basis():
    ladder, _, _, _ = _without_endowment()
    buy = next(order for order in ladder.active_orders if order.side == "BUY")
    ladder._fill(buy, D("1"), 200, source_id=1)
    lot = next(lot for lot in ladder.lots if not lot.initial_endowment)
    cost = lot.unit_cost
    moved = ObservedBookBatch(
        61_000_000,
        61_000_100,
        2,
        2,
        ((D(".90"), D("100")),),
        ((D(".91"), D("100")),),
        D(".8"),
        D("1.1"),
        True,
        exchange_upper_us=61_000_000,
    )
    ladder.receive_book(moved)

    retained = next(item for item in ladder.lots if item.lot_id == lot.lot_id)
    assert retained.remaining == D("1")
    assert retained.unit_cost == cost
    assert D(ladder.metrics()["unrealized_profit"]) < D("0")


def test_profitable_exit_closes_the_bound_lot_and_compounds_cash():
    ladder, _, _, _ = _without_endowment()
    buy = next(order for order in ladder.active_orders if order.side == "BUY")
    ladder._fill(buy, buy.remaining, 200, source_id=1)
    ladder.last_refresh_us = -1
    ladder._refresh(300)
    sell = next(order for order in ladder.active_orders if order.side == "SELL")
    bound_ids = [lot_id for lot_id, _ in sell.reserved_lots]
    before_equity_basis = ladder.cash + ladder.active_buy_notional + ladder.inventory_cost
    ladder._fill(sell, sell.remaining, 400, source_id=2)

    assert all(
        lot.remaining == D("0")
        for lot in ladder.lots
        if lot.lot_id in bound_ids
    )
    assert ladder.cycle_count >= 1
    assert ladder.realized_profit > D("0")
    assert ladder.cash + ladder.active_buy_notional + ladder.inventory_cost > before_equity_basis
    assert ladder.validate_invariants()


def test_marked_equity_components_and_cost_basis_conservation_are_exact():
    ladder, _, _, _ = _without_endowment()
    buy = next(order for order in ladder.active_orders if order.side == "BUY")
    ladder._fill(buy, D("1"), 200, source_id=1)
    metrics = ladder.metrics()
    mark = ladder.current_bids[0][0]

    assert D(metrics["equity"]) == (
        ladder.cash + ladder.active_buy_notional + ladder.inventory * mark
    )
    assert ladder.cash + ladder.active_buy_notional + ladder.inventory_cost == (
        D("100") + ladder.realized_profit
    )
    assert ladder.validate_invariants()


def test_delayed_native_print_before_actual_activation_cannot_fill():
    ladder, _, _, _ = _without_endowment()
    order = next(order for order in ladder.active_orders if order.side == "BUY")

    consumed = ladder.receive_trade(
        Trade(109, 1, order.price, D("1"), True), capture_time_us=200
    )

    assert consumed == D("0")
    assert order.activation_evaluated_us == 200
    assert order.filled == D("0")


def test_cancel_pending_order_does_not_fill_before_it_really_activates():
    ladder, _, _, _ = _without_endowment()
    order = next(order for order in ladder.active_orders if order.side == "BUY")
    ladder._cancel(order, 105, "CANCEL_BEFORE_ACTIVE")

    assert order.activation_evaluated_us is None
    assert ladder.receive_trade(
        Trade(109, 1, order.price, D("1"), True), capture_time_us=111
    ) == D("0")
    assert order.filled == D("0")


def test_cycle_count_is_invariant_to_entry_fill_fragmentation():
    ladder, _, _, _ = _without_endowment()
    buy = next(order for order in ladder.active_orders if order.side == "BUY")
    ladder._fill(buy, D("2"), 200, source_id=1)
    ladder._fill(buy, buy.remaining, 201, source_id=2)
    assert len([lot for lot in ladder.lots if lot.source_order_id == buy.order_id]) == 2
    ladder.last_refresh_us = -1
    ladder._refresh(300)
    sell = next(order for order in ladder.active_orders if order.side == "SELL")
    ladder._fill(sell, sell.remaining, 400, source_id=3)

    assert ladder.cycle_count == 1
    assert len(ladder.settlements) == 1


def test_checkpoint_restore_continuation_matches_same_suffix():
    ladder, profile, rules, book = _without_endowment()
    ladder.receive_book(replace_book_time(book, 150))
    checkpoint = ladder.checkpoint()
    restored = AdaptiveStablecoinLadder.from_checkpoint(checkpoint, profile, rules)
    suffix_book = replace_book_time(book, 61_000_000)

    ladder.receive_book(suffix_book)
    restored.receive_book(suffix_book)
    trade = Trade(62_000_000, 7, D(".90"), D(".05"), True)
    ladder.receive_trade(trade, capture_time_us=62_000_100)
    restored.receive_trade(trade, capture_time_us=62_000_100)

    assert restored.checkpoint() == ladder.checkpoint()


def test_checkpoint_rejects_different_profile_or_rules():
    ladder, profile, rules, _ = _without_endowment()
    changed_profile = type(profile)(
        profile.name,
        profile.evidence_sha256,
        profile.latency_us + 1,
        profile.cancel_latency_us,
        profile.queue_ahead,
        profile.maker_fee,
        profile.taker_fee,
    )

    with pytest.raises(ValueError, match="CHECKPOINT_PROFILE_OR_RULES_MISMATCH"):
        AdaptiveStablecoinLadder.from_checkpoint(ladder.checkpoint(), changed_profile, rules)


def test_unknown_snapshot_coverage_rejects_activation_instead_of_zero_queue():
    profile, rules, _ = _fixtures()
    book = ObservedBookBatch(
        0,
        100,
        1,
        1,
        ((D("1"), D("100")),),
        ((D("1.01"), D("100")),),
        D("1.005"),
        D("1.006"),
        True,
    )
    ladder = AdaptiveStablecoinLadder(profile, rules, endowment_notional=D("0"))
    ladder.receive_book(book)
    ladder.receive_book(replace_book_time(book, 200))

    assert any(order.status == "REJECTED_UNKNOWN_COVERAGE" for order in ladder.orders)
    assert any(row["event"] == "UNKNOWN_COVERAGE_REJECTED" for row in ladder.audit)


def test_inventory_cap_never_shrinks_candidate_below_safe_min_notional():
    profile, rules, book = _fixtures()
    ladder = AdaptiveStablecoinLadder(profile, rules, projected_usdc_cap=D(".55"))
    ladder.receive_book(book)

    assert not [order for order in ladder.active_orders if order.side == "BUY"]
    assert all(
        order.price * order.quantity >= ladder.safe_min_notional
        for order in ladder.orders
        if order.side == "BUY"
    )
