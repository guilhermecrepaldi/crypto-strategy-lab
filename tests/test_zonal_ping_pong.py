import json
import random
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.zonal_ping_pong import ZonalBand, ZonalPingPong

END = 18_000_000_000


def bands():
    result = []
    edges = [D(".9994") + D(index) * D(".0001") for index in range(10)]
    for index in range(9):
        result.append(
            ZonalBand(
                f"Z{index + 1:03d}",
                edges[index],
                edges[index + 1],
                edges[index],
                edges[index + 1],
                D("6") if index < 8 else D("1"),
                D("1"),
            )
        )
    return tuple(result)


ZERO = D("0")


def book(time=1, capture=None, bid=".9998", ask=".9999"):
    return {
        "exchange_time_us": time,
        "exchange_upper_us": time,
        "capture_time_us": time if capture is None else capture,
        "bids": ((D(bid), D("100")),),
        "asks": ((D(ask), D("100")),),
        "known_bid_floor": D(".9994"),
        "known_ask_ceiling": D("1.0003"),
    }


def first_book():
    return book(bid="1.0002", ask="1.0003")


def working_book(time):
    # Keep the desired Z004 BUY below the midpoint, but omit its exact level
    # from displayed depth so the fixture exercises the order itself.
    return book(time, bid=".9996", ask=".9999")


def trade(time, trade_id, price, quantity, buyer_maker, capture=None):
    return {
        "time_us": time,
        "trade_id": trade_id,
        "price": D(price),
        "quantity": D(quantity),
        "buyer_maker": buyer_maker,
        "capture_time_us": time if capture is None else capture,
    }


def engine():
    return ZonalPingPong(bands(), start_us=0, end_us=END, latency_us=1, cancel_latency_us=2)


def test_normalized_label_and_endowment_are_explicit():
    value = engine()
    value.receive_book(first_book())
    value.receive_book(book(2))
    assert "NOT A LIVE-EXECUTABLE RESULT" in value.metrics()["label"]
    assert value.cash + sum((order.reserved_quote for order in value.active_orders), ZERO) == D(
        "100"
    ) - D("49") * D("1.0002")
    assert value.inventory == D("49")
    assert len(value.lots) == 1
    assert len(value.active_sells) == 1
    assert len(value.active_buys) == 4
    assert value.metrics()["window_unsupported"] is True


def test_band_addresses_are_immutable_and_prices_unique():
    value = engine()
    original = tuple(value.bands)
    value.receive_book(first_book())
    value.receive_book(book(2))
    assert tuple(value.bands) == original
    with pytest.raises(ValueError, match="DUPLICATE_IMMUTABLE_BAND_ID"):
        ZonalPingPong((*original, original[0]), start_us=0, end_us=END)
    duplicate = list(original)
    duplicate[1] = ZonalBand(
        "other",
        duplicate[0].price_low,
        D("1.0004"),
        duplicate[0].buy_price,
        D("1.0004"),
        duplicate[1].buy_capacity,
        duplicate[1].sell_capacity,
    )
    with pytest.raises(ValueError, match="DUPLICATE_IMMUTABLE_BUY_PRICE"):
        ZonalPingPong(duplicate, start_us=0, end_us=END)


def test_buy_sell_cycle_requires_full_positive_owned_round_trip():
    value = engine()
    value.receive_book(first_book())
    value.receive_book(working_book(2))
    value.receive_book(working_book(4))
    buy = next(order for order in value.active_buys if order.band_id == "Z004")
    consumed = value.receive_trade(trade(5, 1, buy.price, buy.quantity, True))
    assert consumed == buy.quantity
    value.receive_book(working_book(6))
    value.receive_book(working_book(9))
    sell = next(order for order in value.active_sells if order.band_id == "Z004")
    for lower in value.active_sells:
        if lower.band_id != "Z004" and lower.price < sell.price:
            value.receive_trade(
                trade(10, f"clear-{lower.band_id}", lower.price, lower.quantity, False)
            )
    value.receive_trade(trade(10, 2, sell.price, sell.quantity, False))
    assert value.cycles == 1
    assert value.positive_cycles == 1


def test_endowment_sell_then_owned_buy_counts_one_positive_cycle():
    value = engine()
    value.receive_book(first_book())
    value.receive_book(working_book(2))
    sell = next(order for order in value.active_sells if order.band_id == "Z009")
    value.receive_trade(trade(3, 1, sell.price, sell.quantity, False))
    value.receive_book(book(5, bid="1.0002", ask="1.0003"))
    buy = next(order for order in value.active_buys if order.band_id == "Z009")
    value.receive_book(book(6, bid="1.0002", ask="1.0003"))
    value.receive_trade(trade(7, 2, buy.price - D(".0001"), buy.quantity, True))
    assert value.cycles == 1
    assert value.positive_cycles == 1


def test_partial_fill_does_not_count_cycle_or_release_inventory():
    value = engine()
    value.receive_book(first_book())
    value.receive_book(working_book(2))
    value.receive_book(working_book(4))
    buy = next(order for order in value.active_buys if order.band_id == "Z004")
    value.receive_trade(trade(5, 1, buy.price, D(".5") / buy.price, True))
    assert value.cycles == 0
    assert value._band_state["Z004"] == "BUY_WORKING"


def test_cancel_releases_reserved_quote_exactly_once():
    value = engine()
    value.receive_book(first_book())
    value.receive_book(working_book(2))
    value.receive_book(working_book(4))
    buy = next(order for order in value.active_buys)
    before = value.cash
    value.cancel(buy.order_id, time_us=4)
    value._advance(7)
    after = value.cash
    value.cancel(buy.order_id, time_us=8)
    assert after > before
    assert value.cash == after


def test_same_trade_id_is_global_budgeted_once():
    value = engine()
    value.receive_book(first_book())
    value.receive_book(working_book(2))
    value.receive_book(working_book(4))
    buy = next(order for order in value.active_buys)
    event = trade(5, 1, buy.price, buy.quantity, True)
    first = value.receive_trade(event)
    second = value.receive_trade(event)
    assert first > ZERO
    assert second == ZERO


def test_cutoff_is_exclusive_and_future_event_is_rejected():
    value = engine()
    with pytest.raises(ValueError, match="CUTOFF_EXCLUSIVE"):
        value.receive_book(book(END, END))
    value.receive_book(first_book())
    value.receive_book(book(2))
    with pytest.raises(ValueError, match="CUTOFF_EXCLUSIVE"):
        value.receive_trade(trade(END, 99, D("1"), D("1"), True))
    value.finish(time_us=END)


def test_checkpoint_restore_equivalence():
    value = engine()
    value.receive_book(first_book())
    value.receive_book(book(2))
    checkpoint = value.checkpoint()
    restored = ZonalPingPong.from_checkpoint(
        checkpoint, bands(), start_us=0, end_us=END, latency_us=1, cancel_latency_us=2
    )
    assert restored.metrics() == value.metrics()
    assert restored.checkpoint() == checkpoint


def test_unknown_book_coverage_fails_closed() -> None:
    value = engine()
    raw = first_book()
    raw.pop("known_bid_floor")
    raw.pop("known_ask_ceiling")
    value.receive_book(raw)
    assert value.active_orders == []
    assert any(row["event"] == "COVERAGE_BLOCKED" for row in value.audit)


def test_post_only_is_rechecked_at_actual_activation() -> None:
    value = engine()
    value.receive_book(first_book())
    target = next(order for order in value.active_buys if order.band_id == "Z008")
    assert target.status == "PENDING"
    value.receive_book(book(2, bid="1.0000", ask="1.0001"))
    assert target.status == "REJECTED_POST_ONLY"
    assert target.activation_evaluated_us is None


def test_cancel_pending_remains_fillable_until_cancel_ack() -> None:
    value = engine()
    value.receive_book(first_book())
    value.receive_book(working_book(2))
    value.receive_book(working_book(4))
    target = next(order for order in value.active_buys if order.band_id == "Z004")
    value.cancel(target.order_id, time_us=4)
    assert target.status == "CANCEL_PENDING"
    consumed = value.receive_trade(
        trade(5, 40, target.price - D(".0001"), target.quantity, True)
    )
    assert consumed == target.quantity
    assert target.status == "FILLED"


def test_trade_older_than_latest_book_uncertainty_is_blocked() -> None:
    value = engine()
    value.receive_book(first_book())
    second = working_book(2)
    second["exchange_upper_us"] = 10
    value.receive_book(second)
    value.receive_book({**working_book(4), "exchange_upper_us": 10})
    target = next(order for order in value.active_buys if order.band_id == "Z004")
    assert value.receive_trade(trade(5, 41, target.price, target.quantity, True)) == ZERO
    assert any(row["event"] == "TRADE_BLOCKED_FUTURE_BOOK" for row in value.audit)


def test_fragmented_buy_and_sell_are_one_economic_cycle() -> None:
    value = engine()
    value.receive_book(first_book())
    value.receive_book(working_book(2))
    value.receive_book(working_book(4))
    buy = next(order for order in value.active_buys if order.band_id == "Z004")
    value.receive_trade(trade(5, 50, buy.price - D(".0001"), D(".4"), True))
    value.receive_trade(trade(6, 51, buy.price - D(".0001"), D(".6"), True))
    assert buy.status == "FILLED"
    assert len([lot for lot in value.lots if lot.source_order_id == buy.order_id]) == 2
    value.receive_book(working_book(7))
    value.receive_book(working_book(9))
    sell = next(order for order in value.active_sells if order.band_id == "Z004")
    value.receive_trade(trade(10, 52, sell.price + D(".0001"), D(".4"), False))
    assert value.cycles == 0
    value.receive_trade(trade(11, 53, sell.price + D(".0001"), D(".6"), False))
    assert value.cycles == 1
    assert sum(row["event"] == "CYCLE" for row in value.audit) == 1


def test_trade_through_settles_at_resting_limit_not_print_price() -> None:
    value = engine()
    value.receive_book(first_book())
    value.receive_book(working_book(2))
    value.receive_book(working_book(4))
    buy = next(order for order in value.active_buys if order.band_id == "Z004")
    value.receive_trade(trade(5, 60, buy.price - D(".0002"), D("1"), True))
    value.receive_book(working_book(6))
    value.receive_book(working_book(8))
    sell = next(order for order in value.active_sells if order.band_id == "Z004")
    value.receive_trade(trade(9, 61, sell.price + D(".0010"), D("1"), False))
    assert value.realized_profit == sell.price - buy.price
    fill = next(
        row
        for row in reversed(value.audit)
        if row["event"] == "FILL" and row["order_id"] == sell.order_id
    )
    assert D(fill["price"]) == sell.price


def test_fragmented_endowment_round_trip_counts_once() -> None:
    value = engine()
    value.receive_book(first_book())
    value.receive_book(working_book(2))
    sell = next(order for order in value.active_sells if order.band_id == "Z009")
    cash_before_sale = value.cash
    value.receive_trade(trade(3, 70, sell.price + D(".0001"), D(".4"), False))
    assert value.cash == cash_before_sale
    assert value.metrics()["reentry_escrow"] == "0.40012"
    value.receive_trade(trade(4, 71, sell.price + D(".0001"), D(".6"), False))
    value.receive_book(book(5, bid="1.0002", ask="1.0003"))
    value.receive_book(book(7, bid="1.0002", ask="1.0003"))
    buy = next(order for order in value.active_buys if order.band_id == "Z009")
    value.receive_trade(trade(8, 72, buy.price - D(".0001"), D(".4"), True))
    assert value.cycles == 0
    value.receive_trade(trade(9, 73, buy.price - D(".0001"), D(".6"), True))
    assert value.cycles == 1
    assert D(value.metrics()["roundtrip_profit"]) == D("0.0001")
    assert value.metrics()["reentry_escrow"] == "0"
    assert (
        value.endowment_free_quantity + value.endowment_reserved_quantity
        == value.endowment_initial_quantity
    )
    second_sell = next(order for order in value.active_sells if order.band_id == "Z009")
    value.receive_book(book(10, bid="1.0002", ask="1.0003"))
    value.receive_trade(
        trade(11, 74, second_sell.price + D(".0001"), second_sell.quantity, False)
    )
    second_buy = next(order for order in value.active_buys if order.band_id == "Z009")
    value.receive_book(book(12, bid="1.0002", ask="1.0003"))
    value.receive_trade(
        trade(13, 75, second_buy.price - D(".0001"), second_buy.quantity, True)
    )
    assert value.cycles == 2


def test_checkpoint_binds_frozen_configuration() -> None:
    value = engine()
    value.receive_book(first_book())
    checkpoint = value.checkpoint()
    with pytest.raises(ValueError, match="M020_CHECKPOINT_CONFIG_MISMATCH"):
        ZonalPingPong.from_checkpoint(
            checkpoint,
            bands(),
            start_us=0,
            end_us=END,
            latency_us=2,
            cancel_latency_us=2,
        )


def test_checkpoint_resume_matches_continuous_after_partial_and_cancel_pending() -> None:
    continuous = engine()
    continuous.receive_book(first_book())
    continuous.receive_book(working_book(2))
    continuous.receive_book(working_book(4))
    buy = next(order for order in continuous.active_buys if order.band_id == "Z004")
    continuous.receive_trade(trade(5, 80, buy.price - D(".0001"), D(".4"), True))
    cancellable = next(
        order
        for order in continuous.active_buys
        if order.band_id != "Z004" and order.filled == ZERO
    )
    continuous.cancel(cancellable.order_id, time_us=5)
    checkpoint = continuous.checkpoint()
    restored = ZonalPingPong.from_checkpoint(
        checkpoint, bands(), start_us=0, end_us=END, latency_us=1, cancel_latency_us=2
    )

    def suffix(value: ZonalPingPong) -> None:
        target = next(order for order in value.active_buys if order.band_id == "Z004")
        value.receive_trade(trade(6, 81, target.price - D(".0001"), D(".6"), True))
        value.receive_book(working_book(8))
        value.receive_book(working_book(10))
        sell = next(order for order in value.active_sells if order.band_id == "Z004")
        value.receive_trade(trade(11, 82, sell.price + D(".0001"), D("1"), False))

    suffix(continuous)
    suffix(restored)
    assert restored.metrics() == continuous.metrics()
    assert restored.checkpoint() == continuous.checkpoint()


def test_json_checkpoint_roundtrip_preserves_decimal_filled_and_suffix() -> None:
    value = engine()
    value.receive_book(first_book())
    value.receive_book(working_book(2))
    value.receive_book(working_book(4))
    buy = next(order for order in value.active_buys if order.band_id == "Z004")
    value.receive_trade(trade(5, 180, buy.price - D(".0001"), D(".4"), True))
    persisted = json.loads(json.dumps(value.checkpoint(), default=str))
    restored = ZonalPingPong.from_checkpoint(
        persisted, bands(), start_us=0, end_us=END, latency_us=1, cancel_latency_us=2
    )
    value.receive_book(working_book(7))
    restored.receive_book(working_book(7))
    assert restored.checkpoint() == value.checkpoint()


def test_unfilled_endowment_sells_remain_free_window_quotes() -> None:
    value = engine()
    low = book(1, bid=".9994", ask=".9995")
    value.receive_book(low)
    value.receive_book(book(3, bid=".9998", ask=".9999"))
    value.receive_book(book(6, bid=".9998", ask=".9999"))
    value.receive_book(book(9, bid=".9994", ask=".9995"))
    value.receive_book(book(12, bid=".9994", ask=".9995"))
    unfilled_entry_sells = [
        order
        for order in value.active_sells
        if order.role == "ENTRY" and order.filled == ZERO
    ]
    assert len(unfilled_entry_sells) <= 4
    assert all(
        value._band_state[order.band_id] == "READY_FOR_BUY"
        for order in unfilled_entry_sells
    )


def test_cancel_restores_reserved_lot_at_its_exact_basis_after_rebuy() -> None:
    value = engine()
    value.receive_book(book(1, bid=".9994", ask=".9995"))
    value.receive_book(book(3, bid=".9994", ask=".9995"))
    value.receive_trade(trade(4, 200, ".9996", "2", False))
    value.receive_book(book(6, bid=".9995", ask=".9996"))
    value.receive_trade(trade(7, 201, ".9993", "2", True))
    assert value.cycles == 2
    target = next(order for order in value.active_sells if order.band_id == "Z003")
    value.cancel(target.order_id, time_us=8)
    value._advance(11)
    value.validate_invariants()
    restored = ZonalPingPong.from_checkpoint(
        value.checkpoint(), bands(), start_us=0, end_us=END, latency_us=1, cancel_latency_us=2
    )
    restored.validate_invariants()
    assert restored.checkpoint() == value.checkpoint()


def test_cost_layers_preserve_exact_basis_under_adversarial_sequence() -> None:
    rng = random.Random(0)
    value = engine()
    for index in range(1, 12):
        instant = index * 10
        bid = D(".9993") + D(rng.randrange(10)) * D(".0001")
        value.receive_book(
            {
                "exchange_time_us": instant,
                "exchange_upper_us": instant,
                "capture_time_us": instant,
                "bids": ((bid, D(2)),),
                "asks": ((bid + D(".0001"), D(2)),),
                "known_bid_floor": D(".9993"),
                "known_ask_ceiling": D("1.0004"),
            }
        )
        price = D(".9993") + D(rng.randrange(12)) * D(".0001")
        value.receive_trade(
            trade(
                instant + 3,
                300 + index,
                price,
                rng.randrange(1, 4),
                bool(rng.randrange(2)),
            )
        )
    value.validate_invariants()
    assert value.inventory_cost == value.endowment_cost + sum(
        (lot.remaining_cost for lot in value.lots), ZERO
    )
