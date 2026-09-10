from __future__ import annotations

from copy import deepcopy
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.b10_reality import Trade
from crypto_strategy_lab.microstructure.micro_hot_reallocation import (
    MicroHotReallocationProbe,
    validate_micro_offset_for_tick,
)
from scripts.audit_micro_hot_reallocation import independent_micro_hot_audit


def book(time_us: int, bid: str = "0.99999", ask: str = "1.00000") -> dict:
    return {
        "time_us": time_us,
        "exchange_upper_us": time_us,
        "bids": [[bid, "1000"]],
        "asks": [[ask, "1000"]],
        "known_bid_floor": "0.98",
        "known_ask_ceiling": "1.02",
    }


def probe(scenario: str = "TREATMENT", *, cancel_latency_us: int = 0):
    value = MicroHotReallocationProbe(
        scenario=scenario,
        start_us=0,
        end_us=10_000_000,
        latency_us=0,
        cancel_latency_us=cancel_latency_us,
    )
    value.receive_book(book(1))
    return value


def test_fine_tick_accepts_micro_and_coarse_tick_blocks_it() -> None:
    validate_micro_offset_for_tick("0.00001")
    with pytest.raises(ValueError, match="BLOCKED_FINE_TICK"):
        validate_micro_offset_for_tick("0.0001")


def test_geometry_reallocates_exactly_two_slots_per_side() -> None:
    control, treatment = probe("CONTROL"), probe("TREATMENT")
    assert control.open_order_count == treatment.open_order_count == 60
    assert sum(control._order_meta[o.order_id]["slot_count"] for o in control.orders) == 140
    assert sum(treatment._order_meta[o.order_id]["slot_count"] for o in treatment.orders) == 140
    for side in ("BUY", "SELL"):
        cfar = [o for o in control.orders if o.side == side and o.level in {14, 15}]
        micro = [
            o
            for o in treatment.orders
            if o.side == side and treatment._order_meta[o.order_id]["origin_zone"] == "MICRO"
        ]
        assert len(cfar) == len(micro) == 2
        assert sum(control._order_meta[o.order_id]["slot_count"] for o in cfar) == 2
        assert [(o.column, treatment._order_meta[o.order_id]["slot_count"]) for o in micro] == [
            (1, 1),
            (2, 1),
        ]


def test_micro_prices_are_half_coarse_tick_on_correct_sides() -> None:
    value = probe()
    micro = [o for o in value.orders if value._order_meta[o.order_id]["origin_zone"] == "MICRO"]
    assert {o.price for o in micro if o.side == "BUY"} == {D("0.99995")}
    assert {o.price for o in micro if o.side == "SELL"} == {D("1.00005")}
    assert all(o.price % D("0.00001") == 0 for o in value.orders)


def test_micro_same_price_fifo_is_segmented_c1_before_c2() -> None:
    value = probe()
    value._advance(2)
    group = value.groups[("BUY", D("0.99995"))]
    own = [order_id for segment in group.segments for order_id in segment.order_ids]
    micro = [
        o.order_id
        for o in value.orders
        if o.side == "BUY" and value._order_meta[o.order_id]["origin_zone"] == "MICRO"
    ]
    assert own[:2] == micro


def test_partial_c1_stays_ahead_of_c2() -> None:
    value = probe()
    value._advance(2)
    c1, c2 = [
        o
        for o in value.orders
        if o.side == "BUY" and value._order_meta[o.order_id]["origin_zone"] == "MICRO"
    ]
    value._fill_order(c1, D("0.5"), 3, "partial")
    _public, own = value._queue_components(c2)
    assert own == D("0.5")
    assert c1.remaining == D("0.5")


def test_hotline_move_cancels_old_zero_fill_micro_through_ack() -> None:
    value = probe(cancel_latency_us=10)
    value._advance(2)
    old = next(o for o in value.orders if o.side == "BUY" and o.price == D("0.99995"))
    value.receive_book(book(3, "1.00009", "1.00010"))
    assert old.status == "CANCEL_PENDING"
    assert old.reserved_quote > 0
    value._advance(13)
    assert old.status == "CANCELED"
    assert old.reserved_quote == 0


def test_filled_old_micro_is_not_economically_canceled() -> None:
    value = probe()
    value._advance(2)
    old = next(
        o for o in value.orders if o.side == "BUY" and o.price == D("0.99995") and o.column == 1
    )
    value._fill_order(old, old.quantity, 3, "entry")
    value.receive_book(book(4, "1.00009", "1.00010"))
    assert old.status == "FILLED"
    assert any(o.source_order_id == old.order_id for o in value.orders)


def test_control_has_far14_15_and_treatment_does_not() -> None:
    control, treatment = probe("CONTROL"), probe("TREATMENT")
    assert {(o.side, o.level) for o in control.orders if o.level in {14, 15}} == {
        ("BUY", 14),
        ("BUY", 15),
        ("SELL", 14),
        ("SELL", 15),
    }
    assert not [o for o in treatment.orders if o.level in {14, 15}]


@pytest.mark.parametrize("scenario", ["CONTROL", "TREATMENT"])
def test_checkpoint_roundtrip_preserves_scenario_and_micro_state(scenario: str) -> None:
    value = probe(scenario)
    value._micro_unique_trade_ids.add("diagnostic")
    checkpoint = value.checkpoint()
    restored = MicroHotReallocationProbe.from_checkpoint(checkpoint, start_us=0, end_us=10_000_000)
    assert restored.checkpoint() == checkpoint
    assert restored.metrics() == value.metrics()


def test_capital_match_is_below_owner_tolerance() -> None:
    control, treatment = probe("CONTROL"), probe("TREATMENT")
    error = abs(treatment.initial_mark - control.initial_mark) / control.initial_mark * 100
    assert error <= D("0.01")


def test_independent_audit_rejects_tampered_micro_metrics() -> None:
    value = probe("TREATMENT")
    metrics = value.finish(time_us=10_000_000)
    terminal = value.checkpoint()
    for key in ("MICRO_HOT_PHYSICAL_CYCLES", "MICRO_C1_CYCLES", "MICRO_UNIQUE_PRICE_TOUCHES"):
        tampered = deepcopy(metrics)
        tampered[key] = 999
        with pytest.raises(ValueError, match="M027_AUDIT"):
            independent_micro_hot_audit(value.audit, terminal, tampered, {}, scenario="TREATMENT")


def test_independent_audit_reconstructs_and_rejects_false_micro_touch() -> None:
    value = probe("TREATMENT")
    value._advance(2)
    trade = Trade(3, 1, D("1.00050"), D("1"), False)
    value.receive_trade(trade, capture_time_us=3)
    value._micro_unique_trade_ids.add("1")
    value._record(
        "MICRO_UNIQUE_PRICE_TOUCH",
        3,
        trade_id="1",
        price="1.00050",
        hotline="1.00000",
    )
    metrics = value.finish(time_us=10_000_000)
    terminal = value.checkpoint()
    with pytest.raises(ValueError, match="MICRO_TOUCH_SET"):
        independent_micro_hot_audit(
            value.audit, terminal, metrics, {1: trade}, scenario="TREATMENT"
        )
