"""Synthetic admission-only fixtures; no campaign data or economic replay."""

import copy
import json
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pytest
from test_observed_l2_execution import replay_book, replay_fixture

from crypto_strategy_lab.microstructure.high_uptime_recovery import (
    M017_DEADLINE_POLICY_HASH,
    M018_ENTRY_ADMISSION_POLICY_HASH,
)
from crypto_strategy_lab.microstructure.observed_l2_execution import ObservedL2Replay


def admission_replay(
    model="M018", entry_policy=M018_ENTRY_ADMISSION_POLICY_HASH, fill_price=None, price_tick=".0001"
):
    base, trades = replay_fixture()
    runtime = copy.copy(base.decisions.runtime)
    runtime.tape = base._source_tape
    if fill_price is not None:
        prices = runtime.tape.price_ticks[:]
        index = next(
            i for i, event in enumerate(runtime.tape.events) if event == trades[0].canonical_event
        )
        prices[index] = int(D(fill_price) / runtime.tape.tick_size)
        runtime.tape = replace(runtime.tape, price_ticks=prices)
    runtime.timelines = runtime.tape.timelines((1,))
    identity = {
        **base.identity,
        "model_id": model,
        "deadline_policy_hash": M017_DEADLINE_POLICY_HASH,
        "entry_admission_policy_hash": entry_policy,
    }
    value = ObservedL2Replay(
        runtime,
        base.engine.profile,
        lambda timestamp: replace(base.rules_at(timestamp), tick_size=D(price_tick)),
        base.envelope,
        start_us=base.start_us,
        end_us=base.end_us,
        identity=identity,
        envelope="PRICE_PRIORITY",
    )
    return value, trades


def book(value, timestamp=100, order=1, ask=".9999", bid=".9998"):
    return replace(
        replay_book(value, timestamp, timestamp, order, bids=[(bid, "5")]),
        asks=((D(ask), D(7)),),
    )


@pytest.mark.parametrize(
    "model,policy", [("M018", None), ("M018", "bad"), ("M017", M018_ENTRY_ADMISSION_POLICY_HASH)]
)
def test_identity_cannot_silently_enable_admission(model, policy):
    with pytest.raises(ValueError, match="ADMISSION_POLICY"):
        admission_replay(model, policy)


def test_spec_binds_distinct_admission_and_unchanged_deadline():
    spec = json.loads(Path("docs/microstructure/M018_MODEL_SPEC.json").read_bytes())
    assert spec["entry_admission_policy_hash"] == M018_ENTRY_ADMISSION_POLICY_HASH
    assert spec["deadline_policy_hash"] == M017_DEADLINE_POLICY_HASH
    assert spec["initial_stage_days"] == 1 and spec["max_stage_days"] == 3


def test_crossing_low_is_capped_without_fill_or_candidate_rewrite():
    value, _ = admission_replay()
    candidate = value.decisions.state.candidate
    value.receive_book(book(value))
    assert value.engine.order.price == D(".9998")
    assert value.decisions.state.candidate == candidate
    assert value.order_candidate == candidate
    assert value.engine.inventory == 0 and value.engine.order.status == "PENDING"
    row = next(r for r in value.engine.audit if r["kind"] == "PASSIVE_ENTRY_ADMISSION")
    assert row["reason"] == "SELECTED_LOW_NOT_PASSIVE_AT_SUBMISSION"
    assert row["selected_low"] == "1.0000" and D(row["selected_high"]) == D("1.0001")
    assert row["policy_hash"] == M018_ENTRY_ADMISSION_POLICY_HASH


def test_already_passive_low_unchanged():
    value, _ = admission_replay()
    value.receive_book(book(value, ask="1.0002", bid="1.0001"))
    assert value.engine.order.price == D(1)
    assert value.engine.counts["PASSIVE_ENTRY_ADJUSTED"] == 0


def test_trade_triggered_admission_keeps_effective_book_provenance():
    value, trades = admission_replay()
    candidate = value.decisions.state.candidate
    value.decisions.state.candidate = None
    observed_book = replace(book(value), exchange_time_us=value.start_us + 90)
    value.receive_book(observed_book)
    assert value.engine.order is None
    value.decisions.state.candidate = candidate
    value.receive_trade(trades[0], capture_time_us=value.start_us + 300, capture_order=2)
    row = next(r for r in value.engine.audit if r["kind"] == "PASSIVE_ENTRY_ADMISSION")
    assert value.engine.observed_capture == (value.start_us + 300, 2)
    assert row["time_us"] == value.start_us + 300
    assert row["book_capture_order"] == observed_book.capture_order == 1
    assert row["book_capture_time_us"] == observed_book.capture_time_us == value.start_us + 100
    assert row["native_update_id"] == observed_book.native_update_id
    assert value.engine.order.price == D(".9998")
    assert value.engine.order.status == "PENDING" and value.engine.inventory == 0


@pytest.mark.parametrize(
    "tick,ask,expected", [(".0001", ".9999", ".9998"), (".00001", ".99999", ".99998")]
)
def test_passive_cap_respects_source_day_tick(tick, ask, expected):
    value, _ = admission_replay(price_tick=tick)
    value.receive_book(book(value, ask=ask, bid=expected))
    assert value.engine.order.price == D(expected)
    assert value.engine.order.price % D(tick) == 0


def test_missing_book_or_unknown_admitted_region_waits():
    value, _ = admission_replay()
    value._submit_next(value.start_us)
    assert value.engine.order is None
    value.receive_book(
        replace(book(value, ask="1.0002", bid="1.0001"), known_bid_floor=D("1.0001"))
    )
    assert value.engine.order is None and value.engine.inventory == 0


def test_activation_may_still_reject_and_zero_fill_retry_uses_new_book():
    value, _ = admission_replay()
    value.receive_book(book(value))
    first = value.engine.order
    value.receive_book(book(value, 101, 2, ask=".9998", bid=".9997"))
    value.advance_to(first.active_us + 1)
    assert first.status == "REJECTED" and first.filled == 0
    assert value.engine.order.price == D(".9997")
    assert value.engine.order.order_id != first.order_id


def test_active_order_is_not_repriced_on_book_changes():
    value, _ = admission_replay()
    value.receive_book(book(value))
    order = value.engine.order
    value.advance_to(order.active_us + 1)
    queue = order.queue
    value.receive_book(book(value, 150, 2, ask=".9998", bid=".9997"))
    assert value.engine.order is order and order.status == "ACTIVE"
    assert order.price == D(".9998") and order.queue == queue and order.cancel_us is None


def test_partial_entry_continuation_freezes_price_and_checkpoint():
    value, trades = admission_replay(fill_price=".9998")
    value.receive_book(book(value))
    value.receive_trade(
        replace(trades[0], price=D(".9998"), quantity=D(35)),
        capture_time_us=value.start_us + 300,
        capture_order=2,
    )
    assert value.engine.inventory == 30 and value.engine.passive_entry_price == D(".9998")
    original = value.engine.order
    value.engine.cancel(value.start_us + 310)
    value.receive_book(book(value, 315, 3, ask=".9997", bid=".9996"))
    value.advance_to(value.start_us + 340)
    assert original.status == "CANCELED"
    assert value.engine.order.price == D(".9998")  # no lower-price averaging
    checkpoint = value.engine.checkpoint()
    restored, _ = admission_replay()
    restored.engine.restore(checkpoint)
    assert restored.engine.passive_entry_price == D(".9998")


def test_completed_buy_preserves_original_sell_high():
    value, trades = admission_replay(fill_price=".9998")
    value.receive_book(book(value))
    value.receive_trade(
        replace(trades[0], price=D(".9998"), quantity=D(200)),
        capture_time_us=value.start_us + 300,
        capture_order=2,
    )
    assert value.engine.buy_complete
    assert value.engine.order.side == "SELL" and value.engine.order.price == D("1.0001")
