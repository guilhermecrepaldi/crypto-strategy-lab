from __future__ import annotations

from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.serial_hot_line import (
    INITIAL_CASH,
    SerialHotLinePingPongProbe,
)


def book(time_us: int, *, bid: str = "1.0000", ask: str = "1.0002") -> dict:
    return {
        "time_us": time_us,
        "bids": [[bid, "0"]],
        "asks": [[ask, "0"]],
        "known_bid_floor": "0.98",
        "known_ask_ceiling": "1.02",
    }


def trade(
    time_us: int, trade_id: str, price: str, *, buyer_maker: bool, quantity: str = "1"
) -> dict:
    return {
        "time_us": time_us,
        "trade_id": trade_id,
        "price": price,
        "quantity": quantity,
        "buyer_maker": buyer_maker,
    }


def active_buy(probe: SerialHotLinePingPongProbe) -> None:
    probe.receive_book(book(1))
    probe.receive_book(book(2))
    assert probe.order is not None
    assert probe.order.status == "ACTIVE"


def complete_cycle(probe: SerialHotLinePingPongProbe) -> None:
    active_buy(probe)
    assert probe.receive_trade(trade(3, "buy-1", "0.9999", buyer_maker=True)) == D("1")
    assert probe.state == "WAIT_SELL"
    probe.receive_book(book(4))
    assert probe.order is not None and probe.order.status == "ACTIVE"
    assert probe.receive_trade(trade(5, "sell-1", "1.0003", buyer_maker=False)) == D("1")


def test_virtual_radar_is_two_persistent_decks_and_one_real_order() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=100)
    assert len(probe.buy_deck) == len(probe.sell_deck) == 100
    assert {card.card_id for card in probe.buy_deck} == {f"B{i:03d}" for i in range(1, 101)}
    assert {card.card_id for card in probe.sell_deck} == {f"S{i:03d}" for i in range(1, 101)}
    assert probe.cash == INITIAL_CASH
    assert probe.buy_deck[0].price == D("1.0019")
    assert probe.sell_deck[0].price == D("1.0021")
    active_buy(probe)
    assert sum(card.status == "ARMED" for card in probe.radar) == 1
    with pytest.raises(ValueError, match="ORDER_CAP"):
        probe._submit("BUY", D("1.0001"), 3)


def test_buy_sell_sequence_is_strict_and_profitable() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=100)
    complete_cycle(probe)
    assert probe.cycles == 1
    assert probe.state == "WAIT_BUY"
    assert probe.inventory == D("0")
    assert probe.cash + (probe.order.reserved_quote if probe.order else D("0")) > INITIAL_CASH
    assert [row["event"] for row in probe.audit if row["event"] in {"LEG_COMPLETE", "CYCLE"}] == [
        "LEG_COMPLETE",
        "CYCLE",
    ]
    assert all(row["side"] in {"BUY", "SELL"} for row in probe.audit if row["event"] == "FILL")


def test_same_event_trade_cannot_fill_pending_order() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=100)
    probe.receive_book(book(1))
    assert probe.receive_trade(trade(1, "same", "0.9999", buyer_maker=True)) == D("0")
    assert probe.buy_fills == 0
    assert probe.order is not None and probe.order.status == "PENDING"


def test_pending_buy_equity_includes_reserved_quote() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=100)
    probe.receive_book(book(1))
    assert probe.order is not None and probe.order.status == "PENDING"
    metrics = probe.metrics()
    assert D(metrics["marked_equity"]) == INITIAL_CASH
    assert D(metrics["cash"]) + D(metrics["reserved_quote"]) == INITIAL_CASH


def test_partial_leg_freezes_until_completion() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=100)
    active_buy(probe)
    order_id = probe.order.order_id
    assert probe.receive_trade(trade(3, "part-1", "0.9999", buyer_maker=True, quantity="0.4")) == D(
        "0.4"
    )
    assert probe.state == "BUY_WORKING"
    probe.receive_book(book(4, bid="0.9990", ask="1.0008"))
    assert probe.order is not None
    assert probe.order.order_id == order_id
    assert probe.order.status == "ACTIVE"
    assert probe.receive_trade(trade(5, "part-2", "0.9989", buyer_maker=True, quantity="0.6")) == D(
        "0.6"
    )
    assert probe.state == "WAIT_SELL"


def test_zero_fill_reprice_waits_for_cancel_ack() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=100, cancel_latency_us=2)
    active_buy(probe)
    old_id = probe.order.order_id
    probe.receive_book(book(3, ask="1.0004"))
    assert probe.order is not None and probe.order.order_id == old_id
    assert probe.order.status == "CANCEL_PENDING"
    probe.receive_book(book(4, ask="1.0004"))
    assert probe.order is not None and probe.order.order_id == old_id
    assert probe.order.status == "CANCEL_PENDING"
    probe.receive_book(book(5, ask="1.0004"))
    assert probe.order is not None
    assert probe.order.status == "PENDING"
    assert probe.order.order_id != old_id
    probe.receive_book(book(6, ask="1.0004"))
    assert probe.order is not None and probe.order.status == "ACTIVE"
    assert probe.cash >= D("0")


def test_cancel_race_records_blocked_partial_residual() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=100)
    active_buy(probe)
    order_id = probe.order.order_id
    probe.cancel(order_id, time_us=3)
    assert probe.receive_trade(trade(3, "race", "0.9999", buyer_maker=True, quantity="0.4")) == D(
        "0.4"
    )
    probe.receive_book(book(4))
    assert probe.order is None
    assert probe.state == "BUY_WORKING"
    assert probe.metrics()["partial_residual_blocked"][0]["residual_quantity"] == "0.6"
    assert any(row["event"] == "PARTIAL_RESIDUAL_BLOCKED" for row in probe.audit)


def test_cancel_pending_order_can_activate_before_cancel_ack() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=100, latency_us=5, cancel_latency_us=10)
    probe.receive_book(book(1))
    probe.receive_book(book(2, ask="1.0004"))
    assert probe.order is not None and probe.order.status == "CANCEL_PENDING"
    probe.receive_book(book(6, ask="1.0004"))
    assert probe.order is not None and probe.order.status == "CANCEL_PENDING"
    assert probe.order.activation_evaluated_us == 6
    assert any(row["event"] == "ACTIVATED" and row["during_cancel"] for row in probe.audit)


def test_invalid_due_activation_during_cancel_is_rejected_not_resurrected() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=100, latency_us=5, cancel_latency_us=10)
    probe.receive_book(book(1))
    old_id = probe.order.order_id
    probe.receive_book(book(2, ask="1.0004"))
    probe.receive_book(book(6, ask="1.0000"))
    rejected = [
        row
        for row in probe.audit
        if row["event"] == "REJECTED_POST_ONLY" and row["order_id"] == old_id
    ]
    assert rejected and rejected[0]["during_cancel"] is True
    assert probe.order is None or probe.order.order_id != old_id


def test_partial_sell_realizes_profit_without_counting_complete_cycle() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=100)
    active_buy(probe)
    probe.receive_trade(trade(3, "1", "0.9999", buyer_maker=True))
    probe.receive_book(book(4))
    assert probe.receive_trade(trade(5, "2", "1.0003", buyer_maker=False, quantity="0.4")) == D(
        "0.4"
    )
    assert probe.cycles == 0
    assert probe.realized_profit > D("0")
    assert probe.order is not None and probe.order.side == "SELL"


def test_rotation_promotes_outer_card_and_preserves_deck_size() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=100)
    active_buy(probe)
    filled_card = probe.order.card_id
    expected_promoted = max(
        (card for card in probe.buy_deck if card.card_id != filled_card),
        key=lambda card: (card.price, card.card_id),
    ).card_id
    filled_price = next(card for card in probe.buy_deck if card.card_id == filled_card).price
    probe.receive_trade(trade(3, "buy", "0.9999", buyer_maker=True))
    rotation = [row for row in probe.audit if row["event"] == "RADAR_ROTATION"][-1]
    assert rotation["filled_card_id"] == filled_card
    assert rotation["promoted_card_id"] == expected_promoted
    assert len(probe.buy_deck) == 100
    assert next(card for card in probe.buy_deck if card.card_id == filled_card).lifecycle == 1
    assert (
        next(card for card in probe.buy_deck if card.card_id == expected_promoted).position
        == rotation["new_position"]
    )
    assert (
        next(card for card in probe.buy_deck if card.card_id == expected_promoted).price
        == filled_price
    )


def test_cancel_does_not_rotate_deck_as_if_an_execution_happened() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=100)
    active_buy(probe)
    before = [(card.card_id, card.price, card.position) for card in probe.buy_deck]
    probe.cancel(probe.order.order_id, time_us=3)
    probe.receive_book(book(4))
    after = [(card.card_id, card.price, card.position) for card in probe.buy_deck]
    assert before == after
    assert not any(row["event"] == "RADAR_ROTATION" for row in probe.audit)


def test_checkpoint_restore_is_prefix_equivalent() -> None:
    left = SerialHotLinePingPongProbe(start_us=0, end_us=100)
    active_buy(left)
    left.receive_trade(trade(3, "buy", "0.9999", buyer_maker=True))
    checkpoint = left.checkpoint()
    right = SerialHotLinePingPongProbe.from_checkpoint(checkpoint, start_us=0, end_us=100)
    left.receive_book(book(4))
    right.receive_book(book(4))
    left.receive_trade(trade(5, "sell", "1.0003", buyer_maker=False))
    right.receive_trade(trade(5, "sell", "1.0003", buyer_maker=False))
    assert left.metrics() == right.metrics()
    assert left.audit == right.audit


def test_checkpoint_binds_window_and_latency_configuration() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=100, latency_us=7, cancel_latency_us=9)
    checkpoint = probe.checkpoint()
    restored = SerialHotLinePingPongProbe.from_checkpoint(checkpoint, start_us=0, end_us=100)
    assert restored.latency_us == 7
    assert restored.cancel_latency_us == 9
    with pytest.raises(ValueError, match="CHECKPOINT_CONFIG_MISMATCH"):
        SerialHotLinePingPongProbe.from_checkpoint(checkpoint, start_us=0, end_us=200)


def test_cutoff_is_exclusive_and_time_is_causal() -> None:
    probe = SerialHotLinePingPongProbe(start_us=0, end_us=10)
    with pytest.raises(ValueError, match="CUTOFF_EXCLUSIVE"):
        probe.receive_book(book(10))
    probe.receive_book(book(1))
    with pytest.raises(ValueError, match="NONCAUSAL_LOGICAL_TIME"):
        probe.receive_trade(trade(0, "old", "0.9999", buyer_maker=True))
