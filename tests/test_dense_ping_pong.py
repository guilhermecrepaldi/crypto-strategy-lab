import json
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.zonal_ping_pong import DensePingPongProbe

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


def ready(end: int = END) -> DensePingPongProbe:
    value = DensePingPongProbe(start_us=0, end_us=end)
    value.receive_book(book(1))
    value.receive_book(book(2))
    return value


def test_dense_funds_all_200_slots_without_injection() -> None:
    value = ready()
    metrics = value.metrics()
    assert len(value.active_buys) == 100
    assert len(value.active_sells) == 100
    assert metrics["max_simultaneous_open_orders"] == 200
    assert metrics["initial_usdt"] == "99.5050"
    assert metrics["initial_usdc"] == "100"
    assert D(metrics["initial_marked_equity"]) == D("199.5050")
    value.validate_invariants()


def test_dense_anchor_excludes_entries_but_allows_first_exits_at_anchor() -> None:
    value = ready()
    anchor = D(value.metrics()["grid_anchor"])
    assert all(
        order.price != anchor
        for order in value.active_buys + value.active_sells
        if order.band_id in {"B001", "S001"}
    )
    assert value._bands["B001"].sell_price == anchor
    assert value._bands["S001"].buy_price == anchor


def test_dense_buy_first_and_sell_first_cycles_are_positive() -> None:
    value = ready()
    value.receive_trade(trade(3, "b-buy", ".9999", "1", True))
    value.receive_book(book(4))
    value.receive_trade(trade(5, "b-sell", "1.0002", "1", False))
    value.receive_trade(trade(6, "s-sell", "1.0003", "1", False))
    value.receive_book(book(7))
    value.receive_trade(trade(8, "s-buy", "1.0000", "1", True))
    metrics = value.metrics()
    assert metrics["total_cycles"] == 2
    assert metrics["buy_first_cycles"] == 1
    assert metrics["sell_first_cycles"] == 1
    assert D(metrics["realized_profit"]) > D("0")


def test_dense_partial_entry_waits_for_full_quantity() -> None:
    value = ready()
    value.receive_trade(trade(3, "partial", ".9999", ".4", True))
    assert value.cycles == 0
    assert value._band_state["B001"] == "BUY_WORKING"
    entry = next(order for order in value.orders if order.band_id == "B001" and order.side == "BUY")
    assert entry.status == "ACTIVE"
    value.receive_trade(trade(4, "rest", ".9999", ".6", True))
    assert entry.status == "FILLED"
    assert value.cycles == 0


def test_dense_slot_fills_are_events_and_active_time_is_accumulated() -> None:
    value = ready(end=10)
    value.receive_trade(trade(3, "partial", ".9999", ".4", True))
    value.receive_trade(trade(4, "rest", ".9999", ".6", True))
    value.receive_book(book(5))
    value.finish(time_us=10)
    slot = next(row for row in value.metrics()["slot_report"] if row["slot_id"] == "B001")
    assert slot["fills"] == 2
    assert slot["filled_quantity"] == "1.0"
    assert slot["active_time_us"] == 7
    assert slot["open_position_at_cutoff"] is True


def test_dense_post_only_rechecks_at_activation() -> None:
    value = DensePingPongProbe(start_us=0, end_us=END)
    value.receive_book(book(1))
    value.receive_book(book(2, bid=".9999", ask=".99995"))
    assert any(row["event"] == "REJECTED_POST_ONLY" for row in value.audit)


def test_dense_trade_print_is_consumed_once_by_best_price() -> None:
    value = ready()
    consumed = value.receive_trade(trade(3, "one-print", ".9999", "1", True))
    assert consumed == D("1")
    assert next(order for order in value.orders if order.band_id == "B001").filled == D("1")
    assert next(order for order in value.orders if order.band_id == "B002").filled == D("0")
    assert value.receive_trade(trade(3, "one-print", ".9999", "1", True)) == D("0")


def test_dense_checkpoint_json_suffix_is_equivalent() -> None:
    continuous = ready()
    continuous.receive_trade(trade(3, "prefix", ".9999", ".4", True))
    persisted = json.loads(json.dumps(continuous.checkpoint(), default=str))
    restored = DensePingPongProbe.from_checkpoint(persisted)
    for value in (continuous, restored):
        value.receive_trade(trade(4, "suffix", ".9999", ".6", True))
        value.receive_book(book(5))
    assert restored.metrics() == continuous.metrics()
    assert restored.checkpoint() == continuous.checkpoint()


def test_dense_cutoff_is_exclusive_but_finish_is_exact() -> None:
    value = ready(end=100)
    with pytest.raises(ValueError, match="CUTOFF_EXCLUSIVE"):
        value.receive_trade(trade(100, "future", ".9999", "1", True))
    value.finish(time_us=100)
