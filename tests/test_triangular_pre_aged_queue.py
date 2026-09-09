from __future__ import annotations

from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.triangular_pre_aged_queue import (
    TriangularPreAgedQueueProbe,
)


def probe() -> TriangularPreAgedQueueProbe:
    return TriangularPreAgedQueueProbe(start_us=0, end_us=100)


def queue_probe(public: str = "10") -> TriangularPreAgedQueueProbe:
    value = probe()
    value.seed_capital(usdt="10")
    value.seed_public_queue("BUY", "1.0000", public, activation_us=1)
    return value


def buy_trade(time_us: int, trade_id: str, quantity: str) -> dict:
    return {
        "time_us": time_us,
        "trade_id": trade_id,
        "price": "1.0000",
        "quantity": quantity,
        "buyer_maker": True,
    }


def sell_trade(time_us: int, trade_id: str, quantity: str, price: str = "1.0001") -> dict:
    return {
        "time_us": time_us,
        "trade_id": trade_id,
        "price": price,
        "quantity": quantity,
        "buyer_maker": False,
    }


def test_initial_triangle_has_150_orders_and_cap_200() -> None:
    value = probe()
    value.receive_book(
        {
            "time_us": 1,
            "bids": [["1.0019", "100"]],
            "asks": [["1.0020", "100"]],
            "known_bid_floor": "0.98",
            "known_ask_ceiling": "1.02",
        }
    )
    assert value.open_order_count == 150
    assert value.initial_usdc == D("75")
    assert value.initial_mark == D("150.1325")
    assert value.max_open_orders == 200
    value.validate_invariants()


def test_price_queue_group_has_one_public_queue_and_two_own_columns() -> None:
    value = queue_probe()
    first = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True, column=1)
    second = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True, column=2)
    group = value.groups[("BUY", D("1.0000"))]
    assert group.public_queue == D("10")
    assert group.own_order_ids == [first.order_id, second.order_id]
    assert len(group.segments) == 1


def test_volume_one_cannot_fill_two_one_unit_orders() -> None:
    value = queue_probe(public="0")
    first = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    second = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    assert value.receive_trade(buy_trade(2, "t1", "1")) == D("1")
    assert first.status == "FILLED"
    assert second.status == "ACTIVE"
    assert second.filled == D("0")


def test_volume_two_fills_fifo_columns_after_public_queue_zero() -> None:
    value = queue_probe(public="0")
    first = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    second = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    assert value.receive_trade(buy_trade(2, "t1", "2")) == D("2")
    assert first.status == "FILLED"
    assert second.status == "FILLED"
    assert value._fill_count == 2


def test_public_queue_is_consumed_once_before_own_fifo() -> None:
    value = queue_probe(public="10")
    first = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    second = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    assert value.receive_trade(buy_trade(2, "t1", "5")) == D("5")
    assert first.filled == D("0")
    assert value.receive_trade(buy_trade(3, "t2", "5")) == D("5")
    assert first.filled == D("0")
    assert value.receive_trade(buy_trade(4, "t3", "1")) == D("1")
    assert first.status == "FILLED"
    assert second.filled == D("0")
    assert any(row["event"] == "PUBLIC_QUEUE_CONSUMED" for row in value.audit)


def test_later_activation_keeps_a_cohort_public_barrier() -> None:
    value = queue_probe(public="0")
    first = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    second = value.submit_order("BUY", "1.0000", time_us=2, activate_immediately=True)
    group = value.groups[("BUY", D("1.0000"))]
    group.segments[1].public_remaining = D("10")
    group.segments[1].public_barrier = D("10")
    group.public_remaining = D("10")
    assert value.receive_trade(buy_trade(3, "t1", "1")) == D("1")
    assert first.status == "FILLED"
    assert second.status == "ACTIVE"
    assert value.receive_trade(buy_trade(4, "t2", "10")) == D("10")
    assert second.filled == D("0")


def test_later_activation_adds_only_unrepresented_public_depth() -> None:
    value = queue_probe(public="10")
    first = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    group = value.groups[("BUY", D("1.0000"))]
    group.segments[0].public_remaining = D("4")
    group.public_remaining = D("4")
    second = value.submit_order("BUY", "1.0000", time_us=2, activate_immediately=True)
    assert group.segments[-1].public_barrier == D("6")
    assert group.public_remaining == D("10")
    assert first.queue_ahead_at_activation == D("10")
    assert second.queue_ahead_at_activation == D("11")


def test_c1_cancel_benefits_c2_only_after_ack() -> None:
    value = queue_probe(public="0")
    first = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    second = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    value.cancel(first.order_id, time_us=2)
    assert second.status == "ACTIVE"
    assert value.receive_trade(buy_trade(2, "before", "1")) == D("1")
    assert second.filled == D("0")
    assert first.status == "FILLED"
    value.receive_trade(buy_trade(3, "ack", "0"))
    assert value.receive_trade(buy_trade(4, "after", "1")) == D("1")
    assert second.status == "FILLED"


def test_activation_time_beats_order_id_in_fifo() -> None:
    value = queue_probe(public="0")
    early = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    late = value.submit_order("BUY", "1.0000", time_us=2, activate_immediately=True)
    group = value.groups[("BUY", D("1.0000"))]
    assert group.own_order_ids == [early.order_id, late.order_id]
    assert value.receive_trade(buy_trade(3, "t", "1")) == D("1")
    assert early.status == "FILLED"
    assert late.status == "ACTIVE"


def test_trade_id_is_global_and_duplicate_delivery_consumes_zero() -> None:
    value = queue_probe(public="0")
    order = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    assert value.receive_trade(buy_trade(2, "same", "1")) == D("1")
    assert value.receive_trade(buy_trade(3, "same", "1")) == D("0")
    assert order.status == "FILLED"


def test_buy_first_return_is_owned_and_positive_profit_enters_growth() -> None:
    value = queue_probe(public="0")
    entry = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    assert value.receive_trade(buy_trade(2, "buy", "1")) == D("1")
    returned = next(order for order in value.orders if order.role == "RETURN")
    assert returned.side == "SELL"
    assert returned.source_order_id == entry.order_id
    value.receive_trade(sell_trade(4, "activate-return", "0"))
    value.receive_trade(sell_trade(5, "sell", "1"))
    assert value.metrics()["TOTAL_CYCLES"] == 1
    assert value.growth_pool == D("0.0001")


def test_sell_first_return_restores_base_and_never_goes_negative() -> None:
    value = probe()
    value.seed_capital(usdt="0", usdc="1")
    value.submit_order(
        "SELL", "1.0000", time_us=1, activate_immediately=True, direction="SELL_FIRST"
    )
    assert value.receive_trade(sell_trade(2, "sell", "1", price="1.0000")) == D("1")
    returned = next(order for order in value.orders if order.role == "RETURN")
    assert returned.side == "BUY"
    value.receive_trade({**buy_trade(4, "activate-return", "0"), "price": "0.9999"})
    assert value.receive_trade({**buy_trade(5, "buy", "1"), "price": "0.9999"}) == D("1")
    assert value.metrics()["TOTAL_CYCLES"] == 1
    assert value.free_usdc + value.reserved_usdc == D("1")
    assert value.cash >= D("0")


def test_breakeven_return_is_not_a_positive_cycle() -> None:
    value = queue_probe(public="0")
    value.cash = D("250")
    value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    value.receive_trade(buy_trade(2, "buy", "1"))
    returned = next(order for order in value.orders if order.role == "RETURN")
    returned.price = D("1.0000")
    value.receive_trade(sell_trade(3, "sell", "1", price="1.0000"))
    assert value.metrics()["TOTAL_CYCLES"] == 0


def test_growth_funds_exactly_one_cell_and_not_unrealized_pnl() -> None:
    value = queue_probe(public="0")
    value.growth_pool = D("0.0009")
    with pytest.raises(ValueError, match="GROWTH_INSUFFICIENT"):
        value.fund_growth_cell("BUY", "1.0000", time_us=1, level=26)
    value.growth_pool = D("1.0000")
    order = value.fund_growth_cell("BUY", "1.0000", time_us=2, level=26)
    assert order.capital_source == "GROWTH"
    assert value.growth_pool == D("0")
    assert value.metrics()["NEW_QUEUE_CELLS_FUNDED_BY_PROFIT"] == 1


def test_cap_counts_pending_active_and_cancel_pending() -> None:
    value = queue_probe(public="0")
    value.cash = D("250")
    for index in range(200):
        value.submit_order("BUY", D("1") - D(index) / D("10000"), time_us=1)
    assert value.open_order_count == 200
    with pytest.raises(ValueError, match="OPEN_ORDER_CAP"):
        value.submit_order("BUY", "0.9000", time_us=1)


def test_checkpoint_restore_preserves_groups_fifo_and_capital() -> None:
    value = queue_probe(public="0")
    value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    checkpoint = value.checkpoint()
    restored = TriangularPreAgedQueueProbe.from_checkpoint(checkpoint, start_us=0, end_us=100)
    assert restored.metrics()["OPEN_ORDER_COUNT"] == value.metrics()["OPEN_ORDER_COUNT"]
    assert (
        restored.groups[("BUY", D("1.0000"))].own_order_ids
        == value.groups[("BUY", D("1.0000"))].own_order_ids
    )
    assert restored.cash == value.cash


def test_cutoff_is_exclusive() -> None:
    value = probe()
    with pytest.raises(ValueError, match="CUTOFF_EXCLUSIVE"):
        value.receive_trade(buy_trade(100, "late", "1"))


def test_metrics_expose_required_scoreboard_and_limiter() -> None:
    value = queue_probe(public="0")
    value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    metrics = value.metrics()
    for field in (
        "MODEL",
        "PERIOD",
        "TOTAL_CYCLES",
        "TARGET_10_PER_HOUR_PASS",
        "GROWTH_POOL_FINAL",
        "INITIAL_USDT",
        "FINAL_USDT",
        "AUDIT",
        "MAIN_LIMITER",
        "QUEUE_AHEAD_AT_ACTIVATION_C1",
        "QUEUE_AHEAD_AT_ACTIVATION_C2",
        "QUEUE_AHEAD_AT_TIME_C1_FILLED_FOR_C2",
        "PRE_AGING_QUEUE_ADVANTAGE_MEDIAN_USDC",
        "DEPTH_1_LEVELS",
        "DEPTH_2_LEVELS",
        "DEPTH_3_PLUS_LEVELS",
        "RECTANGLE_TARGET_DEPTH_8_REACHED",
    ):
        assert field in metrics


def test_preaging_case_is_recorded_when_c1_fills_before_c2() -> None:
    value = queue_probe(public="0")
    first = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True, column=1)
    second = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True, column=2)
    value.receive_trade(buy_trade(2, "c1", "1"))
    assert value.metrics()["PRE_AGING_CASES"] == 1
    case = value._preaging_cases[0]
    assert case["c1_order_id"] == first.order_id
    assert case["c2_order_id"] == second.order_id
    assert case["queue_ahead_at_activation_c1"] == "0"
    assert case["queue_ahead_at_activation_c2"] == "1"
    assert case["queue_ahead_at_c1_fill_for_c2"] == "0"
    assert case["status"] == "OPEN"


def test_unresolved_preaging_case_is_censored_at_cutoff() -> None:
    value = queue_probe(public="0")
    value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True, column=1)
    value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True, column=2)
    value.receive_trade(buy_trade(2, "c1", "1"))
    metrics = value.finish(time_us=100)
    assert metrics["PRE_AGING_CASE_ROWS"][0]["status"] == "CENSORED_AT_CUTOFF"


def test_shadow_queue_closes_against_actual_c2_without_touching_physical_queue() -> None:
    value = queue_probe(public="0")
    first = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    second = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    value.receive_trade(buy_trade(2, "c1", "1"))
    value._last_book = {
        "bids": ((D("1.0000"), D("0")),),
        "asks": ((D("1.0002"), D("1")),),
        "known_bid_floor": D("0.99"),
        "known_ask_ceiling": D("1.01"),
        "exchange_upper_us": 2,
    }
    assert value.receive_trade(buy_trade(4, "c2", "1")) == D("1")
    assert value.receive_trade(buy_trade(5, "shadow", "1")) == D("0")
    case = next(case for case in value._preaging_cases if case["c2_order_id"] == second.order_id)
    assert case["actual_fill_us"] == 4
    assert case["shadow"]["fill_us"] == 5
    assert case["benefit_us"] == 1
    assert case["status"] == "CLOSED"
    assert first.status == "FILLED"


def test_shadow_partial_prints_accumulate_without_reusing_physical_quantity() -> None:
    value = queue_probe(public="0")
    value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    second = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    value.receive_trade(buy_trade(2, "c1", "1"))
    value._last_book = {
        "bids": ((D("1.0000"), D("0")),),
        "asks": ((D("1.0002"), D("1")),),
        "known_bid_floor": D("0.99"),
        "known_ask_ceiling": D("1.01"),
        "exchange_upper_us": 2,
    }
    value.receive_trade(buy_trade(4, "half-a", "0.5"))
    value.receive_trade(buy_trade(5, "half-b", "0.5"))
    value.receive_trade(buy_trade(6, "half-c", "0.5"))
    case = next(case for case in value._preaging_cases if case["c2_order_id"] == second.order_id)
    assert case["actual_fill_us"] == 5
    assert case["shadow"]["filled"] == "1.0"
    assert case["shadow"]["fill_us"] == 6
    assert case["benefit_us"] == 1
    assert case["status"] == "CLOSED"


def test_return_conflict_waits_for_free_order_cancel_ack() -> None:
    value = queue_probe(public="0")
    value.free_usdc = D("1")
    conflict = value.submit_order("SELL", "1.0001", time_us=1, activate_immediately=True)
    entry = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    value.receive_trade(buy_trade(2, "entry", "1"))
    assert any(row["event"] == "RETURN_WAITING_FOR_FREE_CANCEL" for row in value.audit)
    assert conflict.status == "CANCEL_PENDING"
    value.receive_trade(sell_trade(3, "ack", "0"))
    assert any(
        order.role == "RETURN" and order.source_order_id == entry.order_id for order in value.orders
    )
    assert any(row["event"] == "CANCEL_ACK" for row in value.audit)


def test_rejected_buy_first_return_restores_inventory_exactly_once_and_retries() -> None:
    value = probe()
    value.seed_capital(usdt="10")
    value._last_book = {
        "bids": ((D("0.9999"), D("1")),),
        "asks": ((D("1.0001"), D("1")),),
        "known_bid_floor": D("0.99"),
        "known_ask_ceiling": D("1.01"),
        "exchange_upper_us": 0,
    }
    entry = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    value.receive_trade(buy_trade(2, "entry", "1"))
    first_return = next(order for order in value.orders if order.source_order_id == entry.order_id)
    value._last_book = {
        "bids": ((D("1.0002"), D("1")),),
        "asks": ((D("1.0003"), D("1")),),
        "known_bid_floor": D("0.99"),
        "known_ask_ceiling": D("1.01"),
        "exchange_upper_us": 2,
    }
    value.receive_trade(buy_trade(3, "advance", "0"))
    assert first_return.status == "REJECTED_POST_ONLY"
    assert value.free_usdc + value.inventory_qty + value.reserved_usdc == D("1")
    assert any(
        order.source_order_id == entry.order_id
        and order.order_id != first_return.order_id
        and order.status == "PENDING"
        for order in value.orders
    )
    value.validate_invariants()


def test_partial_free_conflict_defers_owned_return_without_canceling_residual() -> None:
    value = probe()
    value.seed_capital(usdt="10", usdc="1")
    blocker = value.submit_order("SELL", "1.0001", time_us=1, activate_immediately=True)
    value.receive_trade(sell_trade(2, "partial", "0.4"))
    entry = value.submit_order("BUY", "1.0000", time_us=2, activate_immediately=True)
    value.receive_trade(buy_trade(3, "entry", "1"))
    assert blocker.filled == D("0.4")
    assert blocker.status == "ACTIVE"
    assert entry.order_id in value._deferred_returns
    assert any(
        row["event"] == "RETURN_WAITING_FOR_FREE_CANCEL"
        and row["partial_blocker_order_ids"] == [blocker.order_id]
        for row in value.audit
    )


def test_partial_entry_fill_creates_traceable_lot_immediately() -> None:
    value = queue_probe(public="0")
    entry = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    value.receive_trade(buy_trade(2, "partial", "0.4"))
    lot = next(item for item in value.lots if item.entry_order_id == entry.order_id)
    assert lot.quantity == D("0.4")
    assert lot.asset_basis == D("1.0000")
    assert lot.stage == "PARTIAL_HOLDING"
    assert entry.lot_ids == [lot.lot_id]


def test_current_book_native_upper_blocks_older_trade_delivered_later() -> None:
    value = queue_probe(public="0")
    order = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    value._last_book = {
        "bids": ((D("1.0000"), D("1")),),
        "asks": ((D("1.0002"), D("1")),),
        "known_bid_floor": D("0.99"),
        "known_ask_ceiling": D("1.01"),
        "exchange_upper_us": 10,
    }
    assert value.receive_trade(buy_trade(5, "old", "1"), capture_time_us=11) == D("0")
    assert order.filled == D("0")
    assert value.audit[-1]["blocked_future_book"] is True


def test_shadow_rejects_native_print_older_than_its_activation_book() -> None:
    value = queue_probe(public="0")
    value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    second = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    value.receive_trade(buy_trade(2, "c1", "1"))
    value._last_book = {
        "bids": ((D("1.0000"), D("0")),),
        "asks": ((D("1.0002"), D("1")),),
        "known_bid_floor": D("0.99"),
        "known_ask_ceiling": D("1.01"),
        "exchange_upper_us": 30,
    }
    value._advance_shadow_queues(5)
    value._feed_shadow_queues(D("1.0000"), D("2"), True, 6, 4, "old")
    case = next(case for case in value._preaging_cases if case["c2_order_id"] == second.order_id)
    assert case["shadow"]["filled"] == "0"


def test_rolling_window_repositions_only_after_cancel_ack() -> None:
    value = probe()

    def book(time_us: int, bid: str, ask: str) -> dict:
        return {
            "time_us": time_us,
            "exchange_upper_us": time_us,
            "bids": [[bid, "100"]],
            "asks": [[ask, "100"]],
            "known_bid_floor": "0.98",
            "known_ask_ceiling": "1.02",
        }

    value.receive_book(book(1, "1.0019", "1.0020"))
    value.receive_book(book(2, "1.0019", "1.0020"))
    value.receive_book(book(3, "1.0020", "1.0021"))
    assert value._rolling_cancels == 2
    assert value._rolling_replacements == 0
    canceled_ids = set(value._rolling_pending)
    value.receive_book(book(4, "1.0020", "1.0021"))
    # SELL can move immediately; the higher BUY needs real extra USDT and stays ready.
    assert value._rolling_replacements == 1
    assert len(value._rolling_ready) == 1
    assert all(
        next(order for order in value.orders if order.order_id == order_id).status == "CANCELED"
        for order_id in canceled_ids
    )
    assert any(
        row["event"] == "ROLLING_REPLACEMENT_SUBMITTED" for row in value.audit
    )


def test_checkpoint_rejects_different_replay_window() -> None:
    value = queue_probe(public="0")
    checkpoint = value.checkpoint()
    with pytest.raises(ValueError, match="CHECKPOINT_POLICY_MISMATCH"):
        TriangularPreAgedQueueProbe.from_checkpoint(checkpoint, start_us=0, end_us=200)


def test_cancel_pending_order_can_activate_before_later_cancel_ack() -> None:
    value = TriangularPreAgedQueueProbe(
        start_us=0,
        end_us=100,
        latency_us=1,
        cancel_latency_us=3,
    )
    value.seed_capital(usdt="2")
    value._last_book = {
        "bids": ((D("1.0000"), D("0")),),
        "asks": ((D("1.0002"), D("1")),),
        "known_bid_floor": D("0.99"),
        "known_ask_ceiling": D("1.01"),
        "exchange_upper_us": 1,
    }
    order = value.submit_order("BUY", "1.0000", time_us=1)
    value.cancel(order.order_id, time_us=1)
    value.receive_trade(buy_trade(2, "activate", "0"))
    assert order.status == "CANCEL_PENDING"
    assert order.activation_evaluated_us == 2
    assert order.order_id in value.groups[("BUY", D("1.0000"))].own_order_ids


def test_checkpoint_resume_matches_continuous_suffix_after_partial_fifo_fill() -> None:
    continuous = queue_probe(public="0")
    continuous.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True, column=1)
    continuous.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True, column=2)
    continuous.receive_trade(buy_trade(2, "partial", "0.4"))
    restored = TriangularPreAgedQueueProbe.from_checkpoint(
        continuous.checkpoint(), start_us=0, end_us=100
    )
    for engine in (continuous, restored):
        engine.receive_trade(buy_trade(3, "finish-c1", "0.6"))
        engine.receive_trade(buy_trade(4, "fill-c2", "1"))
    assert restored.checkpoint()["sha256"] == continuous.checkpoint()["sha256"]


def test_rolling_cancel_race_routes_partial_lot_without_recreating_full_cell() -> None:
    value = TriangularPreAgedQueueProbe(
        start_us=0,
        end_us=100,
        latency_us=2,
        cancel_latency_us=3,
    )

    def book(time_us: int, bid: str, ask: str) -> None:
        value.receive_book(
            {
                "time_us": time_us,
                "exchange_upper_us": time_us,
                "bids": [[bid, "0"]],
                "asks": [[ask, "0"]],
                "known_bid_floor": "0.98",
                "known_ask_ceiling": "1.02",
            }
        )

    book(10, "1.0019", "1.0020")
    book(20, "1.0019", "1.0020")
    book(30, "1.0021", "1.0022")
    order = next(item for item in value.orders if item.order_id == 76)
    assert order.status == "CANCEL_PENDING"
    value.receive_trade(
        {
            "time_us": 31,
            "trade_id": "race-partial",
            "price": "1.0020",
            "quantity": "0.4",
            "buyer_maker": False,
        }
    )
    book(40, "1.0021", "1.0022")
    assert order.status == "CANCELED_PARTIAL"
    assert not any(
        item.role == "ENTRY"
        and item.cell_id == order.cell_id
        and item.order_id != order.order_id
        for item in value.orders
    )
    assert order.order_id not in value._deferred_returns
    assert not any(item.source_order_id == order.order_id for item in value.orders)
    locked = next(item for item in value.lots if item.entry_order_id == order.order_id)
    assert locked.stage == "SUBSTEP_RETURN_DEBT_LOCKED"
    assert value._locked_sell_proceeds() == D("0.40080")
    assert any(
        row["event"] == "PARTIAL_LOT_SUBSTEP_LOCKED"
        and row["order_id"] == order.order_id
        and row["cycle_counted"] is False
        for row in value.audit
    )
    assert value.metrics()["TOTAL_CYCLES"] == 0
    assert value.free_usdc + value.reserved_usdc + value.inventory_qty == D("74.6")
    value.validate_invariants()


def test_exact_one_usdc_quantity_is_not_relaxed_for_partial_returns() -> None:
    value = probe()
    value.seed_capital(usdt="2")
    with pytest.raises(ValueError, match="M024_INVALID_ORDER"):
        value.submit_order("BUY", "1.0000", quantity="0.4", time_us=1)


def test_partial_sell_proceeds_cannot_fund_an_unrelated_buy() -> None:
    value = probe()
    value.seed_capital(usdc="1")
    value.submit_order(
        "SELL", "1.0000", time_us=1, activate_immediately=True, direction="SELL_FIRST"
    )
    value.receive_trade(sell_trade(2, "partial-sale", "0.4", price="1.0000"))
    assert value.cash == D("0.4")
    assert value._locked_sell_proceeds() == D("0.4")
    with pytest.raises(ValueError, match="M024_USDT_OWNERSHIP_INSUFFICIENT"):
        value.submit_order("BUY", "0.4000", time_us=3)
    value.validate_invariants()


def test_return_conflict_cancel_race_classifies_substep_partial_lot() -> None:
    value = TriangularPreAgedQueueProbe(
        start_us=0,
        end_us=100,
        latency_us=1,
        cancel_latency_us=10,
    )
    value.seed_capital(usdt="1", usdc="1")
    blocker = value.submit_order(
        "SELL", "1.0001", time_us=1, activate_immediately=True, direction="SELL_FIRST"
    )
    entry = value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    value.receive_trade(buy_trade(2, "buy-entry", "1"))
    assert entry.status == "FILLED"
    assert blocker.status == "CANCEL_PENDING"
    value.receive_trade(sell_trade(3, "partial-blocker", "0.4"))
    value.receive_trade(sell_trade(13, "advance-cancel-ack", "0"))
    lot = next(item for item in value.lots if item.entry_order_id == blocker.order_id)
    assert blocker.status == "CANCELED_PARTIAL"
    assert lot.stage == "SUBSTEP_RETURN_DEBT_LOCKED"
    assert value.metrics()["PARTIAL_SUBSTEP_LOCKED_LOTS"] == 1
    assert value.metrics()["TOTAL_CYCLES"] == 0
    assert not any(order.source_order_id == blocker.order_id for order in value.orders)
    value.validate_invariants()


def test_own_recycle_cannot_spend_earmarked_growth_pool() -> None:
    value = probe()
    value.seed_capital(usdt="1.0000")
    value.seed_public_queue("BUY", "1.0000", "0", activation_us=1)
    value._last_book = {
        "bids": ((D("1.0001"), D("0")),),
        "asks": ((D("1.0003"), D("1")),),
        "known_bid_floor": D("0.99"),
        "known_ask_ceiling": D("1.01"),
        "exchange_upper_us": 0,
    }
    value.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    value.receive_trade(buy_trade(2, "entry", "1"))
    returned = next(order for order in value.orders if order.role == "RETURN")
    value.receive_trade(sell_trade(3, "activate-return", "0", price=str(returned.price)))
    value.receive_trade(sell_trade(4, "return", "1", price=str(returned.price)))
    assert value.growth_pool == D("0.0002")
    assert value.cash == D("1.0002")
    assert any(row["event"] == "PRINCIPAL_RECYCLE_DEFERRED" for row in value.audit)
    assert not any(
        order.role == "ENTRY" and order.order_id > returned.order_id for order in value.orders
    )


def test_recycled_sell_never_moves_below_reacquired_usdc_basis() -> None:
    value = probe()
    value.seed_capital(usdc="1")
    entry = value.submit_order(
        "SELL",
        "1.0000",
        time_us=1,
        activate_immediately=True,
        direction="SELL_FIRST",
        asset_basis="0.9998",
    )
    value.receive_trade(sell_trade(2, "sell", "1", price="1.0000"))
    returned = next(order for order in value.orders if order.source_order_id == entry.order_id)
    value.receive_trade(
        {
            "time_us": 3,
            "trade_id": "activate-buyback",
            "price": str(returned.price),
            "quantity": "0",
            "buyer_maker": True,
        }
    )
    value._last_book = {
        "bids": ((D("0.8000"), D("1")),),
        "asks": ((D("0.8001"), D("1")),),
        "known_bid_floor": D("0.79"),
        "known_ask_ceiling": D("1.01"),
        "exchange_upper_us": 2,
    }
    value.receive_trade(
        {
            "time_us": 4,
            "trade_id": "buyback",
            "price": str(returned.price),
            "quantity": "1",
            "buyer_maker": True,
        }
    )
    recycled = max(
        (order for order in value.orders if order.role == "ENTRY"),
        key=lambda order: order.order_id,
    )
    assert recycled.side == "SELL"
    assert recycled.asset_basis == returned.price
    assert recycled.price >= returned.price + D("0.0001")


def test_post_only_and_unknown_coverage_reject_pending_orders() -> None:
    value = queue_probe(public="0")
    value._last_book = {
        "bids": ((D("1.0000"), D("1")),),
        "asks": ((D("1.0002"), D("1")),),
        "known_bid_floor": D("0.9995"),
        "known_ask_ceiling": D("1.0005"),
    }
    crossing = value.submit_order("BUY", "1.0002", time_us=1)
    outside = value.submit_order("BUY", "0.9900", time_us=1)
    value.receive_trade(buy_trade(2, "advance", "0"))
    assert crossing.status == "REJECTED_POST_ONLY"
    assert outside.status == "REJECTED_COVERAGE"
