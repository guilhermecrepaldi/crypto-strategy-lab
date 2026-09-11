import json
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.zonal_ping_pong import ManagedDensePingPongProbe

END = 18_000_000_000


def book(time: int, *, bid: str = "1.0000", ask: str = "1.0002") -> dict:
    return {
        "exchange_time_us": time,
        "exchange_upper_us": time,
        "capture_time_us": time,
        "bids": ((D(bid), D("1000")),),
        "asks": ((D(ask), D("1000")),),
        "known_bid_floor": D(".98"),
        "known_ask_ceiling": D("1.02"),
    }


def trade(time: int, trade_id: str, price: str, quantity: str, buyer_maker: bool) -> dict:
    return {
        "time_us": time,
        "trade_id": trade_id,
        "price": D(price),
        "quantity": D(quantity),
        "buyer_maker": buyer_maker,
        "capture_time_us": time,
    }


def ready(end: int = END) -> ManagedDensePingPongProbe:
    value = ManagedDensePingPongProbe(start_us=0, end_us=end)
    value.receive_book(book(1))
    value.receive_book(book(2))
    return value


def test_a_to_f_managed_window_and_cap() -> None:
    value = ready()
    assert value.normalized_label.startswith("M022 DENSE PING-PONG ORDER MANAGER V2")
    assert len(value.active_orders) == 160
    assert len(value.active_buys) == 80
    assert len(value.active_sells) == 80
    assert value.metrics()["max_open_orders"] == 160
    assert value.metrics()["parked_lanes_mean"] is not None
    assert value.metrics()["initial_usdt"] == "99.5050"
    ownership = value.metrics()["lane_ownership"]
    assert ownership["B001"]["initial_usdt"] == "1.0000"
    assert ownership["S001"]["initial_usdc"] == "1"
    value.validate_invariants()


def test_g_parked_lanes_reactivate_after_causal_move() -> None:
    value = ready()
    value.receive_book(book(4, bid=".9948", ask=".9950"))
    value.receive_book(book(6, bid=".9948", ask=".9950"))
    parked = max(
        (order for order in value.orders if order.band_id == "B001"),
        key=lambda order: order.order_id,
    )
    assert parked.price == D(".9920")
    assert parked.status == "PENDING"
    value.receive_book(book(8, bid=".9948", ask=".9950"))
    active = next(order for order in value.active_orders if order.band_id == "B001")
    assert active.status == "ACTIVE"
    assert active.price == D(".9920")

    value.receive_book(book(10, bid="1.0050", ask="1.0052"))
    value.receive_book(book(12, bid="1.0050", ask="1.0052"))
    value.receive_book(book(14, bid="1.0050", ask="1.0052"))
    returned = next(order for order in value.active_orders if order.band_id == "B001")
    assert returned.status == "ACTIVE"
    assert returned.price == D("1.0000")


def test_h_new_order_cannot_fill_on_its_creation_event() -> None:
    value = ManagedDensePingPongProbe(start_us=0, end_us=END)
    value.receive_book(book(1))
    before = value.receive_trade(trade(1, "same-event", ".9999", "1", True))
    assert before == D("0")
    assert not any(order.filled > D("0") for order in value.orders)


def test_i_cancel_does_not_release_quote_before_ack() -> None:
    value = ready()
    order = next(order for order in value.active_buys if order.band_id == "B001")
    cash_before = value.cash
    value.cancel(order.order_id, time_us=2)
    assert value.cash == cash_before
    value.receive_book(book(4))
    assert value.cash >= cash_before


def test_j_checkpoint_json_suffix_is_identical() -> None:
    continuous = ready()
    continuous.receive_trade(trade(3, "prefix", ".9999", ".4", True))
    persisted = json.loads(json.dumps(continuous.checkpoint(), default=str))
    restored = ManagedDensePingPongProbe.from_checkpoint(persisted)
    for value in (continuous, restored):
        value.receive_trade(trade(4, "suffix", ".9999", ".6", True))
        value.receive_book(book(5))
    assert restored.metrics() == continuous.metrics()
    assert restored.checkpoint() == continuous.checkpoint()


def test_lane_ownership_mirror_and_claim_at_first_partial_fill() -> None:
    value = ready()
    value.receive_trade(trade(3, "partial", ".9999", ".4", True))
    assert "B001" in value.metrics()["return_claims"]
    assert value.metrics()["return_claims"]["B001"] == {
        "side": "SELL",
        "price": "1.0001",
    }
    assert D(value.metrics()["lane_profit"]["B001"]) == D("0")
    value.validate_invariants()


def test_dynamic_claim_uses_filled_entry_price_not_band_exit() -> None:
    value = ready()
    value.receive_book(book(4, bid=".9948", ask=".9950"))
    value.receive_book(book(6, bid=".9948", ask=".9950"))
    value.receive_book(book(8, bid=".9948", ask=".9950"))
    order = next(order for order in value.active_buys if order.band_id == "B001")
    value._fill(order, D(".25"), 3, source_id="direct-test")
    claim = value.metrics()["return_claims"]["B001"]
    assert claim["price"] == str(order.price + D(".0001"))
    assert claim["price"] != str(value._bands["B001"].sell_price)
    assert any(row["event"] == "RETURN_PRICE_CLAIM" for row in value.audit)


def test_return_preemption_is_real_cancel_ack_and_audited() -> None:
    value = ready()
    accepted, blocked = value._manager_return_plan([("SELL", "B001", D(".9998"), D("1"))], 3)
    assert not accepted
    assert ("SELL", "B001") in blocked
    assert value.metrics()["manager_blocked_free"] >= 2
    assert any(row["event"] == "RETURN_PREEMPTION" for row in value.audit)
    assert sum(row["event"] == "FREE_ORDER_CANCELED_FOR_RETURN" for row in value.audit) >= 2
    value.receive_book(book(4))
    assert not any(
        order.band_id == "B002" and order.status == "CANCEL_PENDING"
        for order in value.active_orders
    )


def test_return_priority_and_no_negative_exit() -> None:
    value = ready()
    value.receive_trade(trade(3, "buy", ".9999", "1", True))
    value.receive_book(book(4))
    value.receive_trade(trade(5, "sell", "1.0002", "1", False))
    assert value.metrics()["return_submissions"] >= 1
    assert value.metrics()["realized_profit"] != "-0.0001"
    assert value.metrics()["negative_exit_allowed"] is False


def test_fragmented_return_wait_is_recorded_once_when_fully_filled() -> None:
    value = ready()
    entry = next(order for order in value.active_buys if order.band_id == "B001")
    entry.queue = D("0")
    value.receive_trade(trade(3, "fragment-entry", ".9999", "1", True))
    value.receive_book(book(4))
    returned = next(
        order for order in value.active_orders if order.band_id == "B001" and order.role == "EXIT"
    )
    returned.queue = D("0")
    value.receive_trade(trade(5, "fragment-a", "1.0001", ".4", False))
    value.receive_trade(trade(6, "fragment-b", "1.0001", ".6", False))
    assert value.metrics()["return_fills"] == 2
    assert value.metrics()["return_wait_time_mean"] == 3
    assert value.metrics()["return_wait_time_median"] == 3
    fills = [row for row in value.audit if row["event"] == "RETURN_FILL"]
    assert [row["complete"] for row in fills] == [False, True]


def test_partial_free_fill_before_cancel_ack_is_blocked_and_not_reused() -> None:
    value = ready()
    order = next(order for order in value.active_buys if order.band_id == "B001")
    value.cancel(order.order_id, time_us=3)
    value._fill(order, D(".4"), 3, source_id="cancel-race")
    value.receive_book(book(4))
    assert order.status == "CANCELED"
    assert value.metrics()["partial_residual_blocked_count"] == 1
    assert not any(
        candidate.band_id == "B001" and candidate.role == "ENTRY"
        for candidate in value.active_orders
    )
    blocked = [row for row in value.audit if row["event"] == "PARTIAL_RESIDUAL_BLOCKED"]
    assert blocked[0]["reason"] == "BELOW_HISTORICAL_STEP_AFTER_CANCEL_ACK"


def test_owned_return_conflict_is_deferred_not_canceled() -> None:
    value = ready()
    value.receive_trade(trade(3, "buy", ".9999", "1", True))
    value.receive_book(book(4))
    value.receive_trade(trade(5, "sell", "1.0002", "1", False))
    owned = [order for order in value.orders if order.role == "EXIT"]
    assert owned
    assert all(order.status != "CANCELED" for order in owned)


def test_two_crossing_exit_obligations_defer_the_later_one() -> None:
    value = ready()
    value._manager_claim_times.update({"S001": 1, "B001": 2})
    accepted, blocked = value._manager_return_plan(
        [
            ("BUY", "S001", D("1.0001"), D("1")),
            ("SELL", "B001", D("1.0001"), D("1")),
        ],
        3,
    )
    assert accepted == [("BUY", "S001", D("1.0001"), D("1"))]
    assert ("SELL", "B001") in blocked
    assert any(row["event"] == "OWNED_RETURN_CONFLICT" for row in value.audit)


def test_owned_return_sort_uses_claim_time_activation_lane_and_source_id() -> None:
    value = ready()
    first = next(order for order in value.orders if order.band_id == "B001")
    second = next(order for order in value.orders if order.band_id == "B002")
    second.activation_evaluated_us = 1
    first.activation_evaluated_us = 2
    value._manager_claim_times.update({"S001": 3, "S002": 3})
    value._manager_claim_source_order_ids.update({"S001": first.order_id, "S002": second.order_id})
    accepted, blocked = value._manager_return_plan(
        [
            ("SELL", "S001", D("1.0001"), D("1")),
            ("SELL", "S002", D("1.0002"), D("1")),
        ],
        3,
    )
    assert not blocked
    assert [row[1] for row in accepted] == ["S002", "S001"]


def test_utilization_uses_open_parked_and_exchange_active_denominators() -> None:
    value = ready(end=100)
    report = value.finish(time_us=100)
    assert report["mean_active_open_orders"] == "160"
    assert report["parked_lanes_mean"] == "40"
    assert report["active_order_time_us"] == "15680"
    assert report["percent_active_orders_within_5_ticks_of_mid"] == "6.2500"
    assert report["time_weighted_distance_from_mid"] == "40.5"


def test_even_wait_median_is_average_of_two_middle_values() -> None:
    value = ready()
    value._manager_return_wait_us[:] = [1, 3]
    assert value.metrics()["return_completion_wait_time_median_us"] == D("2")


def test_never_activated_cancel_pending_is_excluded_from_active_time_metrics() -> None:
    value = ManagedDensePingPongProbe(
        start_us=0,
        end_us=100,
        latency_us=10,
        cancel_latency_us=10,
    )
    value.receive_book(book(1))
    order = next(order for order in value.active_orders if order.band_id == "B001")
    value.cancel(order.order_id, time_us=2)
    value.receive_book(book(3))
    report = value.finish(time_us=5)
    assert order.status == "CANCEL_PENDING"
    assert order.activation_evaluated_us is None
    assert report["mean_active_open_orders"] == "160"
    assert report["active_order_time_us"] == "0"
    assert report["percent_active_orders_within_5_ticks_of_mid"] is None
    assert report["time_weighted_distance_from_mid"] is None


def test_unique_lanes_used_includes_historical_submissions() -> None:
    value = ready()
    value.receive_book(book(4, bid=".9948", ask=".9950"))
    value.receive_book(book(6, bid=".9948", ask=".9950"))
    report = value.metrics()
    assert report["unique_lanes_used"] == len({order.band_id for order in value.orders})


def test_s_lane_return_basis_is_restored_to_the_same_lane() -> None:
    value = ready()
    sell = next(order for order in value.active_sells if order.band_id == "S001")
    sell.queue = D("0")
    value.receive_trade(trade(3, "s-lane", "1.0002", "1", False))
    value.receive_book(book(4))
    value.receive_trade(trade(5, "s-return", "1.0000", "1", True))
    restored = ManagedDensePingPongProbe.from_checkpoint(
        json.loads(json.dumps(value.checkpoint(), default=str))
    )
    assert restored._manager_s_free == value._manager_s_free

    replacement = next(
        order for order in value.active_orders if order.band_id == "S001" and order.side == "SELL"
    )
    value.cancel(replacement.order_id, time_us=6)
    value._check_time(7)
    value._advance(7)
    assert value._manager_s_free["S001"] == {
        "quantity": D("1"),
        "cost": D("1.0001"),
    }
    assert value._manager_s_free["S002"]["quantity"] == D("0")
    assert value.endowment_free_quantity == D("21")
    assert value.endowment_cost == D("21.0001")
    value.validate_invariants()


def test_exact_cutoff_and_reported_manager_metrics() -> None:
    value = ready(end=100)
    with pytest.raises(ValueError, match="CUTOFF_EXCLUSIVE"):
        value.receive_trade(trade(100, "future", ".9999", "1", True))
    report = value.finish(time_us=100)
    for key in (
        "return_preemptions",
        "free_orders_canceled_for_return",
        "free_orders_canceled_for_float",
        "free_orders_reposted",
        "return_submissions",
        "return_fills",
        "mean_active_open_orders",
        "min_active_open_orders_after_warmup",
        "parked_lanes_mean",
        "time_weighted_distance_from_mid",
        "unique_lanes_used",
        "unique_price_levels_used",
        "unique_productive_lanes",
    ):
        assert key in report
