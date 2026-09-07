"""Synthetic execution semantics fixtures, not Binance calibration/results."""

from dataclasses import replace
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.b10_reality import (
    B10Execution,
    B10RealityReplay,
    BookEnvelope,
    ExecutionProfile,
    SymbolRules,
    Trade,
    round_quantity,
)


def engine(fee="0", *, reserve=None):
    profile = ExecutionProfile("SYNTHETIC_FIXTURE_ONLY", "a" * 64, 10, 10, D(5), D(fee), D(fee))
    rules = SymbolRules(
        D("0.0001"),
        D("0.01"),
        D("0.01"),
        D(10000),
        D(5),
        D(100000),
        D("0.01"),
        D(100),
        "b" * 64,
        orders_per_window=1000,
        window_us=1000000,
    )
    value = B10Execution(profile, rules)
    value.book(0, 1, [(D("0.9999"), D(1000))], D("1.0001"))
    if reserve is not None:
        value.reserve = D(reserve)
    return value


def trade(value, time=11, quantity="105", price="1", buyer=True):
    value.trade(Trade(time, time, D(price), D(quantity), buyer))


def buy(value):
    value.submit("BUY", D(1), 0)
    trade(value)


def sell(value, *, quantity="105"):
    value.submit("SELL", D("1.001"), 12)
    trade(value, 23, quantity, "1.001", False)


def test_touch_wrong_aggressor_latency_queue_partial_full():
    value = engine()
    value.submit("BUY", D(1), 0)
    trade(value, 10)  # Equal timestamp activation is not usable.
    assert value.inventory == 0
    trade(value, 11, buyer=False)
    assert value.inventory == 0
    trade(value, 12, "5")
    assert value.inventory == 0
    trade(value, 13, "30")
    assert value.inventory == 30
    with pytest.raises(ValueError, match="SERIAL_ORDER"):
        value.submit("SELL", D("1.001"), 14)
    trade(value, 14, "70")
    assert value.inventory == 100
    assert value.buy_complete
    assert value.counts["MISSED_BY_LATENCY"] == 1
    assert value.counts["MISSED_BY_QUEUE"] == 1


def test_partial_sell_not_cycle_then_net_skim():
    value = engine()
    buy(value)
    sell(value, quantity="45")
    assert value.counts["FULLY_FILLED_CYCLES"] == 0
    assert value.inventory == 60
    trade(value, 24, "60", "1.001", False)
    assert value.counts["FULLY_FILLED_CYCLES"] == 1
    assert value.reserve_funding == D("0.002")
    assert value.cash + value.reserve == D("105.100")


def test_cancel_race_fills_no_second_lot():
    value = engine()
    value.submit("BUY", D(1), 0)
    value.cancel(11)
    trade(value, 15, "35")
    assert value.inventory == 30
    trade(value, 22, "100")
    assert value.inventory == 30
    assert value.order is None
    with pytest.raises(ValueError, match="SERIAL_LOT"):
        value.submit("BUY", D(1), 33)
    with pytest.raises(ValueError, match="BUY_NOT_FULL"):
        value.submit("SELL", D("1.001"), 33)


def test_step_and_notional_rejection():
    assert round_quantity(D("100.999"), D(1)) == 100
    value = engine()
    value.cash = D(4)
    assert value.submit("BUY", D(1), 0) is None
    assert value.counts["ORDER_REJECTION_COUNT"] == 1


def test_fee_wipes_edge_and_dust_not_reused():
    value = engine("0.001")
    buy(value)
    sell(value)
    assert value.counts["FULLY_FILLED_CYCLES"] == 1
    assert value.counts["NET_POSITIVE_CYCLES"] == 0
    assert value.reserve_funding == 0
    assert value.cash < 100


def test_positive_profit_skim_is_net_not_gross():
    value = engine("0.0001")
    buy(value)
    sell(value)
    settlement = value.audit[-1]
    assert value.reserve_funding == D(settlement["net_profit"]) * D("0.02")
    assert value.reserve_funding < D("0.002")


def test_partial_release_waits_actual_settlement_and_gt10bps():
    value = engine()
    buy(value)
    value.submit("SELL", D("0.99"), 12, release=True)
    value.book(23, 2, [(D("0.9988"), D(40))], D("1.0001"))
    assert value.inventory == 60
    assert value.reserve == 5
    assert value.counts["RELEASE_PARTIAL"] == 1
    value.submit("SELL", D("0.99"), 24, release=True)
    value.book(35, 3, [(D("0.9987"), D(60))], D("1.0001"))
    assert value.inventory == 0
    assert value.counts["RELEASES_ACTUAL_GT10BPS"] == 1
    assert value.reserve_consumption == D("0.126")
    assert value.cash == 100
    assert value.cash + value.reserve == D("104.874")


def test_depletion_does_not_create_money():
    value = engine(reserve="0.01")
    buy(value)
    value.submit("SELL", D("0.99"), 12, release=True)
    value.book(23, 2, [(D("0.9988"), D(1000))], D("1.0001"))
    assert value.reserve == 0
    assert value.cash == D("99.89")
    assert value.counts["RESERVE_DEPLETION_EVENTS"] == 1


def test_gap_requires_new_book_and_duplicate_trade_rejected():
    value = engine()
    value.submit("BUY", D(1), 0)
    value.gap()
    trade(value, 11)
    assert value.inventory == 0
    value.book(12, 2, [(D("0.9999"), D(1000))], D("1.0001"))
    trade(value, 13)
    assert value.inventory == 100
    with pytest.raises(ValueError, match="NONCAUSAL_TRADE"):
        trade(value, 13)


def test_restart_determinism_and_corrupt_checkpoint():
    value = engine()
    value.submit("BUY", D(1), 0)
    trade(value, 11, "35")
    checkpoint = value.checkpoint()
    restarted = engine()
    restarted.restore(checkpoint)
    for item in (value, restarted):
        trade(item, 12, "70")
        sell(item)
    assert restarted.checkpoint() == value.checkpoint()
    checkpoint["state"]["cash"] = D(999)
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        restarted.restore(checkpoint)


def test_limit_maker_cross_reject_and_profile_fail_closed():
    value = engine()
    value.submit("BUY", D("1.0001"), 0)
    trade(value, price="1.0001")
    assert value.inventory == 0
    assert value.orders[0].status == "REJECTED"
    with pytest.raises(ValueError, match="ZERO_LATENCY"):
        replace(value.profile, latency_us=0)


def test_dynamic_filter_and_rate_limit():
    value = engine()
    value.rules = replace(value.rules, buy_bounds=(D("0.99"), D("0.999")))
    assert value.submit("BUY", D(1), 0) is None
    value.rules = replace(value.rules, buy_bounds=None, orders_per_window=1)
    value.submit("BUY", D(1), 0)
    value.cancel(1)
    trade(value, 12, buyer=False)
    assert value.submit("BUY", D(1), 23) is None
    assert value.counts["RATE_LIMIT_REJECTION"] == 1


def driver():
    from datetime import UTC, datetime, timedelta

    from crypto_strategy_lab.microstructure.recovery_reserve import (
        RecoveryReserveRuntime,
        ReserveConfig,
    )
    from crypto_strategy_lab.microstructure.serial_replay import (
        SerialModelConfig,
        SerialScenarioConfig,
        SerialStrategy,
        SerialTape,
    )

    start = datetime(2026, 1, 1, tzinfo=UTC)
    tape = SerialTape.from_events(
        [
            (start + timedelta(seconds=-20 + i), D("1") if i % 2 == 0 else D("1.0001"))
            for i in range(20)
        ],
        tick_size=D("0.0001"),
    )
    parent = SerialModelConfig(
        model_id="M007",
        parent_model_id=None,
        strategy=SerialStrategy.ALWAYS_BEST,
        lookback_minutes=1440,
        decision_interval_minutes=1,
    )
    runtime = RecoveryReserveRuntime(
        ReserveConfig(D("0.02"), 1, D(10)),
        parent,
        SerialScenarioConfig(tick_size=tape.tick_size),
        tape,
        tape.timelines((1,)),
        None,
    )
    fixture = engine()
    start_us = int(start.timestamp()) * 1_000_000
    result = B10RealityReplay(
        runtime,
        fixture.profile,
        lambda _: fixture.rules,
        BookEnvelope("c" * 64, D("0.00001"), D("0.0001"), D(1000), D("0.01"), 1000),
        start_us=start_us,
        end_us=start_us + 41,
        identity={"published_config_sha": "fixture", "data_manifest_sha256": "fixture"},
    )
    return result, [
        Trade(start_us + t, i, D(p), D(1000), m)
        for i, (t, p, m) in enumerate([(0, "1", True), (20, "1", True), (40, "1.0001", False)])
    ]


def test_full_driver_uses_canonical_selection_and_json_restart():
    import json

    original, trades = driver()
    original.step(trades[0])
    assert original.order_candidate == (10000, 1)
    original.step(trades[1])
    recovered, _ = driver()
    recovered.restore(json.loads(json.dumps(original.checkpoint())))
    original.step(trades[2])
    recovered.step(trades[2])
    assert original.finish() == recovered.finish()
    assert recovered.execution.counts["FULLY_FILLED_CYCLES"] == 1
    assert recovered.execution.reserve_funding == D("0.0002")


def test_driver_refuses_truncated_stream():
    replay, trades = driver()
    with pytest.raises(ValueError, match="PHYSICAL_CUTOFF"):
        replay.run(trades[:1])


def test_partial_sell_allocates_remaining_cost():
    value = engine()
    buy(value)
    sell(value, quantity="45")
    assert value.cost == 60


def test_unsold_dust_is_not_realized_loss_or_reserve_deficit():
    value = engine("0.00011")
    buy(value)
    value.submit("SELL", D("0.99"), 12, release=True)
    value.book(23, 2, [(D("0.9988"), D(1000))], D("1.0001"))
    row = value.audit[-1]
    assert value.dust == D("0.00900")
    assert value.dust_cost > 0
    assert D(row["sold_cost"]) + value.dust_cost == D(100)
    assert value.reserve_consumption == D(row["net_profit"]).copy_abs()
    assert value.cash < D(100)  # Unsold basis was never covered by the reserve.


def test_normal_sell_winning_cancel_race_is_not_aggressive_release():
    value = engine()
    buy(value)
    value.submit("SELL", D("1.001"), 12)
    value.releasing = True  # Release signal; cancellation still in flight.
    value.cancel(23)
    trade(value, 24, "105", "1.001", False)
    assert value.counts["FULLY_FILLED_CYCLES"] == 1
    assert value.counts["RELEASE_FILLED"] == 0
    assert value.reserve_funding == D("0.002")


def test_release_bridge_matches_original_authority_without_mutation():
    import copy
    from datetime import UTC, datetime, timedelta

    from crypto_strategy_lab.microstructure.b10_reality import FrozenB10Decisions
    from crypto_strategy_lab.microstructure.recovery_reserve import (
        RecoveryReserveRuntime,
        ReserveConfig,
    )
    from crypto_strategy_lab.microstructure.serial_replay import (
        EVENT_ORDER_SCALE,
        SerialModelConfig,
        SerialScenarioConfig,
        SerialStrategy,
        SerialTape,
    )

    start = datetime(2026, 1, 1, tzinfo=UTC)
    values = [(-100 + i, "1" if i % 2 == 0 else "1.0001") for i in range(20)]
    values.extend((30 + i * 60, "0.9998" if i % 2 == 0 else "0.9999") for i in range(30))
    values.append((3599, "0.9999"))
    tape = SerialTape.from_events(
        [(start + timedelta(seconds=t), D(p)) for t, p in values], tick_size=D("0.0001")
    )
    parent = SerialModelConfig(
        model_id="M007",
        parent_model_id=None,
        strategy=SerialStrategy.ALWAYS_BEST,
        lookback_minutes=1440,
        decision_interval_minutes=1,
    )
    runtime = RecoveryReserveRuntime(
        ReserveConfig(D("0.02"), 1, D(10)),
        parent,
        SerialScenarioConfig(tick_size=tape.tick_size),
        tape,
        tape.timelines((1,)),
        None,
    )
    start_us = int(start.timestamp()) * 1_000_000
    bridge = FrozenB10Decisions(runtime, start_event=start_us * EVENT_ORDER_SCALE)
    value = engine()
    buy(value)
    value.entry_us = start_us
    # Already sold forty units; only sixty units' basis can enter release eligibility.
    sell(value, quantity="45")
    boundary = (start_us + 3_600_000_000) * EVENT_ORDER_SCALE
    state = copy.deepcopy(bridge.state)
    state.entry_event = start_us * EVENT_ORDER_SCALE
    state.cash, state.inventory, state.inventory_cost = value.cash, value.inventory, value.cost
    reference_runtime = copy.copy(runtime)
    assert reference_runtime(state, boundary)
    expected = reference_runtime.releases[-1]
    runtime.releases = []
    signal = bridge.release_signal(boundary, value)
    assert signal == expected
    assert D(signal["quantity"]) == 60
    assert D(signal["loss_usdt"]) == D("0.0060")
    assert value.inventory == 60
    assert value.reserve == 5
    assert bridge.state.candidate == (10000, 1)


def test_same_timestamp_canonical_exit_ordinal_is_preserved(monkeypatch):
    replay, trades = driver()
    replay.step(trades[0])
    replay.step(trades[1])
    called = []
    monkeypatch.setattr(replay.decisions, "after_ordinary_exit", called.append)
    from crypto_strategy_lab.microstructure.serial_replay import EVENT_ORDER_SCALE

    final = replace(trades[2], canonical_event=trades[2].time_us * EVENT_ORDER_SCALE + 7)
    replay.step(final)
    assert called == [final.canonical_event]


def test_audit_journal_durable_prefix_restart_and_corruption(tmp_path):
    import runpy

    journal_type = runpy.run_path("scripts/run_b10_reality.py")["AuditJournal"]
    path = tmp_path / "execution-audit.jsonl"
    value = engine()
    buy(value)
    journal = journal_type(path)
    journal.drain(value)
    saved = journal.durable()
    assert not value.audit
    value._record("UNCOMMITTED_SUFFIX", marker=1)
    journal.drain(value)
    journal.durable()
    journal.close()
    assert path.stat().st_size > saved["bytes"]
    recovered = journal_type(path, saved)
    assert recovered.durable() == saved
    recovered.close()
    assert path.stat().st_size == saved["bytes"]
    with pytest.raises(ValueError, match="PREFIX_HASH"):
        journal_type(path, {**saved, "sha256": "0" * 64})


def test_driver_order_activation_timer_does_not_require_next_trade():
    replay, trades = driver()
    replay.step(trades[0])
    activation = replay.execution.order.active_us + 1
    replay._clock(activation)
    assert replay.execution.order.status == "ACTIVE"
    assert replay.execution.order.filled == 0


def test_clock_uses_transition_rules_without_intervening_trade():
    replay, trades = driver()
    replay.step(trades[0])
    activation = replay.execution.order.active_us + 1
    old_rules = replay.execution.rules
    new_rules = replace(old_rules, min_notional=D(101))
    replay.rules_at = lambda timestamp: new_rules if timestamp >= activation else old_rules
    replay._clock(activation)
    assert replay.execution.orders[0].status == "REJECTED"
    assert replay.execution.rules == new_rules
