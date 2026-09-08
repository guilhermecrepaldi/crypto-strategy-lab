"""Synthetic evidence adapter tests; no historical economics or network."""

import json
from dataclasses import replace
from decimal import Decimal as D

import pytest
from test_b10_reality import engine as base_fixture

from crypto_strategy_lab.microstructure.b10_reality import Trade
from crypto_strategy_lab.microstructure.observed_l2_execution import (
    ObservedBookBatch,
    ObservedL2Execution,
    ObservedL2Replay,
)


def batch(time=0, order=1, *, bids=None, asks=None, **kwargs):
    return ObservedBookBatch(
        exchange_time_us=time,
        capture_time_us=time + 100,
        capture_order=order,
        native_update_id=order,
        bids=tuple((D(p), D(q)) for p, q in (bids or [("1", "5"), (".99", "100")])),
        asks=tuple((D(p), D(q)) for p, q in (asks or [("1.01", "7")])),
        known_bid_floor=D(".9"),
        known_ask_ceiling=D("1.1"),
        sequence_validated=True,
        **kwargs,
    )


def engine(envelope="CONSERVATIVE_QUEUE"):
    base = base_fixture()
    transitions = []
    value = ObservedL2Execution(
        base.profile, base.rules, envelope=envelope, on_transition=transitions.append
    )
    value.observed_book(batch())
    return value, transitions


def trade(value, time, quantity, *, price="1", buyer=True, order=None):
    value.observed_trade(
        Trade(time, time, D(price), D(quantity), buyer),
        capture_time_us=time + 100,
        capture_order=time if order is None else order,
    )


def test_activation_seeds_current_observed_quantity_not_submission_or_proxy():
    value, _ = engine()
    value.submit("BUY", D(1), 0)
    value.observed_book(batch(11, 2, bids=[("1", "20"), (".99", "100")]))
    assert value.order.queue == 20
    trade(value, 12, "25")
    assert value.inventory == 5
    assert len(value.activation_observations) == 1
    assert value.activation_observations[0]["ahead_estimate"] == "20"
    assert value.activation_observations[0]["depth_1tick"] == "20"


def test_known_empty_level_zero_queue_and_unknown_level_rejected():
    value, _ = engine()
    value.submit("BUY", D("1.0001"), 0)
    trade(value, 11, "10", price="1.0001")
    assert value.inventory == 10 and value.activation_observations[0]["ahead_estimate"] == "0"
    other, _ = engine()
    other.submit("BUY", D(".8"), 0)
    trade(other, 11, "100", price=".8")
    assert other.inventory == 0 and other.orders[0].status == "REJECTED"
    assert other.audit[-1]["reason"] == "UNKNOWN_LEVEL_COVERAGE"


def test_depth_change_does_not_double_count_trade_depletion_or_reset_queue():
    value, _ = engine()
    value.submit("BUY", D(1), 0)
    trade(value, 11, "2")
    assert value.order.queue == 3
    value.observed_book(batch(12, 12, bids=[("1", "3"), (".99", "100")]))
    assert value.order.queue == 3
    value.observed_book(batch(13, 13, bids=[("1", "40"), (".99", "100")]))
    assert value.order.queue == 3
    trade(value, 14, "4")
    assert value.inventory == 1


@pytest.mark.parametrize(
    "side,limit,through,buyer",
    [
        ("BUY", "1", ".9999", True),
        ("SELL", "1.01", "1.0101", False),
    ],
)
def test_priority_gate_uses_previous_activation_own_limit_and_quantity(side, limit, through, buyer):
    value, _ = engine("PRICE_PRIORITY")
    if side == "SELL":
        value.submit("BUY", D(1), 0)
        trade(value, 11, "105")
        start = 12
    else:
        start = 0
    value.submit(side, D(limit), start)
    trade(value, start + 11, "2", price=through, buyer=buyer)
    assert value.order.filled == 0  # Activation observed by this print is too late.
    trade(value, start + 12, "2", price=through, buyer=buyer)
    assert value.order.filled == 2 and value.order.queue == 0
    fills = [row for row in value.audit if row["kind"] == "FILL"]
    assert D(fills[-1]["price"]) == D(limit)
    assert value.counts["PRICE_THROUGH_PRIORITY_INFERENCE"] == 1


def test_conservative_does_not_use_through_and_wrong_aggressor_does_not_fill():
    value, _ = engine()
    value.submit("BUY", D(1), 0)
    trade(value, 11, "100", buyer=False)
    trade(value, 12, "100", price=".9999")
    assert value.inventory == 0 and value.order.queue == 5


def buy(value):
    value.submit("BUY", D(1), 0)
    trade(value, 11, "105")
    assert value.inventory == 100


def test_ioc_book_settlement_callback_and_exact_owner_accounting():
    value, changes = engine()
    buy(value)
    value.submit("SELL", value.protected_exit()["price"], 12, release=True)
    value.observed_book(batch(23, 23, bids=[(".99", "100")], asks=[("1", "100")]))
    assert value.inventory == 0 and value.cash == 100 and value.reserve == 9
    assert value.bid_consumption_debt["0.99"] == 100
    assert changes[-1]["cause"] == "BOOK"
    assert changes[-1]["before"]["inventory"] == "100"
    assert changes[-1]["after"]["releases"] == 1


def test_partial_ioc_budget_survives_snapshot_and_other_level_updates():
    value, _ = engine()
    buy(value)
    value.submit("SELL", value.protected_exit()["price"], 12, release=True)
    value.observed_book(batch(23, 23, bids=[(".99", "40")], asks=[("1", "100")]))
    assert value.inventory == 60
    value.observed_book(batch(24, 24, bids=[(".9900", "40")], is_snapshot=True))
    assert value.bids[0][1] == 0 and not value.protected_exit()["eligible"]
    value.observed_book(batch(25, 25, bids=[(".99", "40"), (".98", "5")]))
    assert value.bids[0][1] == 0
    value.submit("SELL", value.protected_exit()["price"], 26, release=True)
    value.observed_book(batch(37, 37, bids=[(".99", "40"), (".98", "5")]))
    assert value.inventory == 55  # Only newly observed lower-level depth is available.
    assert value.bid_consumption_debt["0.99"] == D(40)
    assert value.bid_consumption_debt["0.98"] == D(5)


def test_price_representation_and_new_positive_depth_do_not_fabricate_budget():
    value, _ = engine()
    buy(value)
    value.submit("SELL", value.protected_exit()["price"], 12, release=True)
    value.observed_book(batch(23, 23, bids=[(".99", "40")]))
    value.observed_book(batch(24, 24, bids=[(".9900", "50")], is_snapshot=True))
    assert value.bids[0][1] == 10


def test_observed_deletion_and_replenishment_restore_only_new_depth():
    value, _ = engine()
    buy(value)
    value.submit("SELL", value.protected_exit()["price"], 12, release=True)
    value.observed_book(batch(23, 23, bids=[(".99", "40")]))
    value.observed_book(batch(24, 24, bids=[(".99", "20")]))
    value.observed_book(batch(25, 25, bids=[(".99", "30")]))
    assert value.bids[0][1] == 10
    value.observed_book(batch(26, 26, bids=[(".98", "1")]))
    value.observed_book(batch(27, 27, bids=[(".99", "40"), (".98", "1")]))
    assert value.bids[0][1] == 40


def test_checkpoint_restores_debt_queue_and_binds_envelope():
    value, _ = engine()
    buy(value)
    value.submit("SELL", value.protected_exit()["price"], 12, release=True)
    value.observed_book(batch(23, 23, bids=[(".99", "40")]))
    snapshot = json.loads(json.dumps(value.checkpoint()))
    restored, callbacks = engine()
    restored.restore(snapshot)
    assert restored.checkpoint() == snapshot
    restored.observed_book(batch(24, 24, bids=[(".99", "40")]))
    assert restored.bids[0][1] == 0 and callbacks[-1]["cause"] == "BOOK"
    other, _ = engine("PRICE_PRIORITY")
    with pytest.raises(ValueError, match="ENVELOPE"):
        other.restore(snapshot)


@pytest.mark.parametrize(
    "bad,reason",
    [
        (replace(batch(1, 2), sequence_validated=False), "SEQUENCE"),
        (replace(batch(1, 2), bids=((D(1), 1.0),)), "DECIMAL"),
        (replace(batch(1, 2), bids=((D("1.01"), D(1)),)), "CROSSED"),
    ],
)
def test_invalid_book_rejected_before_mutation(bad, reason):
    value, _ = engine()
    before = value.checkpoint()
    with pytest.raises(ValueError, match=reason):
        value.observed_book(bad)
    assert value.checkpoint() == before


def test_capture_regression_exchange_regression_and_raw_bypass_fail_closed():
    value, _ = engine()
    value.observed_book(batch(20, 2))
    with pytest.raises(ValueError, match="TWO_CLOCK"):
        value.observed_trade(Trade(19, 19, D(1), D(1), True), capture_time_us=121, capture_order=3)
    with pytest.raises(ValueError, match="CAPTURE"):
        value.observed_book(replace(batch(21, 3), capture_time_us=119))
    with pytest.raises(ValueError, match="CAPTURE_BINDING"):
        value.trade(Trade(21, 21, D(1), D(1), True))
    with pytest.raises(ValueError, match="PROVENANCE"):
        value.book(21, 21, [(D(1), D(1))], D("1.01"))


def test_profitable_cycle_uses_existing_ten_percent_funding():
    value, changes = engine()
    buy(value)
    value.submit("SELL", D("1.01"), 12)
    trade(value, 23, "107", price="1.01", buyer=False)
    assert value.cash == D("100.90") and value.reserve == D("10.10")
    assert value.counts["FULLY_FILLED_CYCLES"] == 1
    assert changes[-1]["cause"] == "TRADE" and changes[-1]["after"]["ordinary_cycles"] == 1


def test_duplicate_native_id_cannot_supply_changed_depth():
    value, _ = engine()
    before = value.checkpoint()
    changed = replace(batch(1, 2, bids=[("1", "500")]), native_update_id=1)
    with pytest.raises(ValueError, match="WITHOUT_NATIVE_UPDATE"):
        value.observed_book(changed)
    assert value.checkpoint() == before


def test_sample_seam_preserves_active_queue_and_blocks_print_before_snapshot():
    value, _ = engine()
    value.submit("BUY", D(1), 0)
    trade(value, 11, "2")
    order = value.order
    queue = order.queue
    value.begin_sample_seam(12, "2025-02-01")
    trade(value, 13, "1000")
    assert value.order is order and order.queue == queue and value.inventory == 0
    value.observed_book(replace(batch(14, 14, bids=[("1", "500")]), is_snapshot=True))
    assert order.queue == queue and value.order is order


def test_sample_seam_pending_order_waits_for_new_snapshot():
    value, _ = engine()
    value.submit("BUY", D(1), 0)
    value.begin_sample_seam(1, "2025-02-01")
    trade(value, 11, "1000")
    assert value.order.status == "PENDING" and value.inventory == 0
    value.observed_book(replace(batch(12, 12), is_snapshot=True))
    assert value.order.status == "ACTIVE"


def test_sample_seam_never_treats_cross_gap_increase_as_replenishment():
    value, _ = engine()
    original = value.bids[0][1]
    value.bids[0][1] = D(1)
    value.bid_consumption_debt["1"] = original - D(1)
    value.begin_sample_seam(1, "2025-02-01")
    value.observed_book(replace(batch(2, 2, bids=[("1", "500")]), is_snapshot=True))
    assert value.bids[0][1] == 1
    value.observed_book(batch(3, 3, bids=[("1", "510")]))
    assert value.bids[0][1] == 11


def test_replacement_reseeds_queue_but_partial_order_retains_it():
    value, _ = engine()
    value.submit("BUY", D(1), 0)
    trade(value, 11, "2")
    value.cancel(12)
    trade(value, 23, "1")
    assert value.order is None
    value.observed_book(batch(34, 34, bids=[("1", "9")]))
    value.submit("BUY", D(1), 34)
    trade(value, 45, "10")
    assert value.inventory == 1 and value.order.queue == 0
    value.observed_book(batch(46, 46, bids=[("1", "200")]))
    trade(value, 47, "1")
    assert value.inventory == 2 and len(value.activation_observations) == 2
    assert value.activation_observations[-1]["ahead_estimate"] == "9"


def replay_fixture(*, cold_start=False):
    from datetime import UTC, datetime, timedelta

    from test_b10_reality import driver

    from crypto_strategy_lab.microstructure.recovery_reserve import ReserveConfig
    from crypto_strategy_lab.microstructure.serial_replay import EVENT_ORDER_SCALE, SerialTape

    old, _ = driver()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    history = (
        []
        if cold_start
        else [
            (start + timedelta(seconds=-20 + i), D("1") if i % 2 == 0 else D("1.0001"))
            for i in range(20)
        ]
    )
    current = [(120, "1", True), (220, "1", True), (320, "1.0001", False)]
    history.extend((start + timedelta(microseconds=t), D(p)) for t, p, _ in current)
    tape = SerialTape.from_events(history, tick_size=D(".0001"))
    runtime = old.decisions.runtime
    runtime.config = ReserveConfig(D(".02"), 1, D(10), D("2.5"))
    runtime.tape = tape
    runtime.timelines = tape.timelines((1,))
    replay = ObservedL2Replay(
        runtime,
        old.execution.profile,
        old.rules_at,
        old.envelope,
        start_us=old.start_us,
        end_us=old.start_us + 24 * 3_600_000_000,
        identity={
            **old.identity,
            "model_id": "M015",
            "capital_mode": "COMPOUNDING",
            "priority_trade_through": True,
            "expected_trade_count": 3,
        },
        envelope="CONSERVATIVE_QUEUE",
    )
    trades = [
        Trade(old.start_us + t, i + 1, D(p), D(107), buyer, (old.start_us + t) * EVENT_ORDER_SCALE)
        for i, (t, p, buyer) in enumerate(current)
    ]
    return replay, trades


def replay_book(replay, native_time, capture_time, order, *, bids=None):
    start = replay.start_us
    return replace(
        batch(start + native_time, order, bids=bids, asks=[("1.0001", "7")]),
        capture_time_us=start + capture_time,
    )


def test_capture_replay_accepts_interleaved_exchange_clock_and_bounds_execution():
    value, trades = replay_fixture()
    value.receive_book(replay_book(value, 0, 100, 1))
    value.receive_book(replay_book(value, 190, 190, 2))
    value.receive_trade(trades[0], capture_time_us=value.start_us + 200, capture_order=3)
    assert value.engine.inventory == 0
    assert value.engine.counts["BOOK_NEWER_THAN_NATIVE_TRADE"] == 1
    value.receive_trade(trades[1], capture_time_us=value.start_us + 300, capture_order=4)
    assert value.engine.inventory == 100
    value.receive_trade(trades[2], capture_time_us=value.start_us + 400, capture_order=5)
    assert value.engine.counts["FULLY_FILLED_CYCLES"] == 1
    assert value.engine.cash == D("100.009") and value.engine.reserve == D("10.001")
    result = value.finish()
    assert result["RUN_STATUS"] == "COMPLETE"
    assert result["CLOCK_MODE"] == "CAPTURE_ARRIVAL"
    assert result["NET_POSITIVE_CYCLES"] == 1


def test_available_prefix_hides_future_tape_prices_cycles_and_current_fill_print():
    value, trades = replay_fixture(cold_start=True)
    tape = value.decisions.runtime.tape
    assert len(tape.events) == 0 and value.decisions.state.candidate is None
    for timeline in value.decisions.runtime.timelines.values():
        assert len(timeline.low_events) == 0
        assert len(timeline.high_events) == 0
        assert len(timeline.cycle_exits) == 0
    value.receive_book(replay_book(value, 0, 100, 1))
    value.receive_trade(trades[0], capture_time_us=value.start_us + 200, capture_order=2)
    assert len(tape.events) == 1 and tape.last_event == trades[0].canonical_event
    assert all(not timeline.cycle_exits for timeline in value.decisions.runtime.timelines.values())
    with pytest.raises(ValueError, match="PREFIX_HAS_HOLE"):
        value.receive_trade(trades[2], capture_time_us=value.start_us + 400, capture_order=3)


def test_capture_clock_does_not_fill_print_that_happened_before_activation():
    value, trades = replay_fixture()
    value.receive_book(replay_book(value, 0, 150, 1))
    value.receive_trade(trades[0], capture_time_us=value.start_us + 200, capture_order=2)
    assert value.engine.inventory == 0
    assert value.engine.counts["NATIVE_PRINT_NOT_AFTER_ACTIVATION"] == 1


@pytest.mark.parametrize("uncertain", [False, True])
def test_book_exchange_precision_interval_is_not_silently_exact(uncertain):
    value, trades = replay_fixture()
    book = replay_book(value, 0, 100, 1)
    value.receive_book(
        replace(
            book,
            exchange_upper_us=book.exchange_time_us + (999 if uncertain else 0),
            exchange_precision="MILLISECONDS" if uncertain else "EXACT_MICROSECONDS",
        )
    )
    value.receive_trade(trades[0], capture_time_us=value.start_us + 200, capture_order=2)
    assert value.engine.inventory == (0 if uncertain else 100)
    assert value.engine.counts["AMBIGUOUS_BOOK_EVENT_PRECISION"] == int(uncertain)


def test_replay_book_ioc_settlement_updates_lifecycle_without_synthetic_step():
    value, trades = replay_fixture()
    value.receive_book(replay_book(value, 0, 100, 1))
    value.receive_trade(trades[0], capture_time_us=value.start_us + 200, capture_order=2)
    assert value.engine.inventory == 100
    value.engine.releasing = True
    value.engine.cancel(value.start_us + 201)
    value.advance_to(value.start_us + 223)
    value.release_destination = (9999, 1)
    value.release_destination_tick = D(".0001")
    assert value.engine.order.release
    value.receive_book(replay_book(value, 300, 300, 3, bids=[(".9999", "100")]))
    assert value.engine.counts["RELEASE_FILLED"] == 1
    assert value.next_release is None and value.position_candidate is None
    assert value.decisions.state.candidate == (9999, 1)
    assert len(value.holds_us) == 1
    with pytest.raises(ValueError, match="CAPTURE_ORDERED"):
        value.step(trades[1])
