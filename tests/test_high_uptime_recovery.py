"""M012 synthetic policy invariants; no economic result or calibration."""

import json
from dataclasses import replace
from decimal import Decimal as D
from decimal import localcontext

import pytest
from test_b10_reality import driver as kernel_driver
from test_b10_reality import engine as kernel_fixture

from crypto_strategy_lab.microstructure.b10_reality import Trade
from crypto_strategy_lab.microstructure.high_uptime_recovery import (
    HOUR,
    HighUptimeExecution,
    HighUptimeRecoveryReplay,
)


def engine(fee="0"):
    fixture = kernel_fixture(fee)
    result = HighUptimeExecution(fixture.profile, fixture.rules)
    result.book(0, 1, [(D("0.9999"), D(1000))], D("1.0001"))
    return result


def buy(value, quantity="105"):
    value.submit("BUY", D(1), 0)
    value.trade(Trade(11, 2, D(1), D(quantity), True))


def profitable_cycle(value, price="1.01"):
    buy(value)
    value.submit("SELL", D(price), 12)
    value.trade(Trade(23, 3, D(price), D(200), False))


def replay():
    source, trades = kernel_driver()
    result = HighUptimeRecoveryReplay(
        source.decisions.runtime,
        source.execution.profile,
        source.rules_at,
        source.envelope,
        start_us=source.start_us,
        end_us=source.start_us + 26 * HOUR,
        identity={**source.identity, "model_id": "M012", "capital_mode": "COMPOUNDING"},
    )
    return result, trades


def test_compounding_profit_one_and_no_withdrawal():
    value = engine()
    profitable_cycle(value)
    assert value.cash == D("100.95")
    assert value.reserve == D("5.05")
    assert value.cash + value.reserve == 106
    assert value.reserve_target == D("5.0475")
    order = value.submit("BUY", D(1), 24)
    assert order.quantity == D("100.95")
    assert value.lot_budget == D("100.95")
    assert value.counts["FULLY_FILLED_CYCLES"] == 1


def test_partial_entry_keeps_budget_and_first_fill_anchor():
    value = engine()
    buy(value, "35")
    assert value.inventory == 30 and value.entry_us == 11
    value.cancel(12)
    value._advance(23)
    continuation = value.submit("BUY", D(1), 33, continuation=True)
    assert continuation.quantity == 70
    value.trade(Trade(44, 4, D(1), D(75), True))
    assert value.inventory == 100 and value.buy_cost == 100 and value.entry_us == 11


def test_forced_exact_loss_reserve_transfer_and_floor():
    value = engine()
    buy(value)
    protection = value.protected_exit()
    assert protection["price"] == D("0.951")
    value.submit("SELL", protection["price"], 12, release=True)
    value.book(23, 3, [(D("0.99"), D(100))], D("1.0001"))
    assert value.cash == 100 and value.reserve == 4
    assert value.cash + value.reserve == 104
    assert value.reserve_consumption == 1
    assert value.counts["FULLY_FILLED_CYCLES"] == 0
    assert value.counts["RELEASE_FILLED"] == 1
    assert value.reserve_escrow == 0


def test_forced_positive_funds_without_ordinary_count():
    value = engine()
    buy(value)
    value.submit("SELL", value.protected_exit()["price"], 12, release=True)
    value.book(23, 3, [(D("1.01"), D(100))], D("1.02"))
    assert value.cash == D("100.95") and value.reserve == D("5.05")
    assert value.counts["FORCED_NET_POSITIVE_CLOSURES"] == 1
    assert value.counts["FULLY_FILLED_CYCLES"] == 0


def test_partial_release_guard_restores_bank_floor():
    value = engine()
    buy(value)
    value.submit("SELL", value.protected_exit()["price"], 12, release=True)
    value.book(23, 3, [(D("0.99"), D(40))], D("1.0001"))
    assert value.inventory == 60 and value.reserve == 5 and value.reserve_escrow == 0
    protection = value.protected_exit()
    assert not protection["eligible"]  # Shared book was consumed.
    value.book(24, 4, [(D("0.99"), D(60))], D("1.0001"))
    protection = value.protected_exit()
    assert protection["floor_guard"] == D("0.1")
    value.submit("SELL", protection["price"], 25, release=True)
    value.book(36, 5, [(D("0.99"), D(60))], D("1.0001"))
    assert value.reserve == 4 and value.cash == 100


def test_fee_dust_remains_asset_not_realized_loss():
    value = engine("0.00001")
    profitable_cycle(value)
    assert value.inventory == 0 and value.dust > 0 and value.dust_cost > 0
    row = value.settlements[-1]
    with localcontext() as ctx:
        ctx.prec = 128
        assert value.operating_bank == value.cash + value.dust_cost
        assert D(row["net_profit"]) == D("1.01") * D("99.99") * (1 - D("0.00001")) - D(
            row["sold_cost"]
        )
    assert value.reserve_consumption == 0


def test_filter_capacity_is_explicit_not_fixed100():
    value = engine()
    value.cash = D(20000)
    assert value.submit("BUY", D(1), 0) is None
    assert value.counts["CAPACITY_LIMIT_REACHED"] > 0
    assert value.cash == 20000 and value.reserve == 5


def test_protected_exit_below_floor_and_stranded_min_notional():
    value = engine()
    buy(value)
    value.book(12, 3, [(D("0.9"), D(100))], D(1))
    assert value.protected_exit()["reason"] == "RELEASE_BLOCKED_BY_RESERVE"
    value.inventory, value.cost = D(1), D(1)
    assert value.protected_exit()["reason"] == "FILTER_REJECTION"
    assert value.entry_us == 11


def test_timer_prefix_hard_lock_no_fabricated_fill_or_count():
    value, _ = replay()
    fixture = engine()
    buy(fixture)
    value.execution = fixture
    value.engine.entry_us = value.start_us
    value.position_candidate = (10000, 1)
    value.engine.book(value.start_us, 4, [(D("0.9"), D(100))], D(1))
    old_last, count = value.last_us, value.processed_trades
    value.advance_to(value.start_us + 18 * HOUR)
    assert value.engine.releasing and value.engine.inventory == 100
    value.advance_to(value.start_us + 24 * HOUR)
    assert value.urgency == "MANDATORY_UNLOCK" and not value.hard_lock_events
    value.advance_to(value.start_us + 24 * HOUR + 1)
    assert len(value.hard_lock_events) == 1
    assert value.last_us == old_last and value.processed_trades == count
    assert value.engine.inventory == 100 and value.engine.reserve == 5
    assert D(value.metrics()["LOCK_HOURS_GT24"]) > 0


def test_driver_json_restart_and_timer_only_metrics():
    value, trades = replay()
    value.step(trades[0])
    value.advance_to(trades[1].time_us)
    restored, _ = replay()
    restored.restore(json.loads(json.dumps(value.checkpoint())))
    for trade in trades[1:]:
        value.step(trade)
        restored.step(trade)
    assert value.checkpoint() == restored.checkpoint()
    assert value.metrics() == restored.metrics()
    with pytest.raises(ValueError, match="PHYSICAL_CUTOFF"):
        value.finish()


def test_initial_metrics_and_wrong_capital_identity():
    value, _ = replay()
    assert value.metrics()["TOTAL_EQUITY"] == "105"
    assert value.metrics()["RUN_STATUS"] == "RUNNING"
    source, _ = kernel_driver()
    with pytest.raises(ValueError, match="COMPOUNDING"):
        HighUptimeRecoveryReplay(
            source.decisions.runtime,
            source.execution.profile,
            source.rules_at,
            source.envelope,
            start_us=source.start_us,
            end_us=source.end_us,
            identity={"model_id": "M012"},
        )


def test_partial_sell_prefix_realized_profit_and_restored_floor():
    value, _ = replay()
    value.execution = engine()
    buy(value.engine)
    value.engine.submit("SELL", D("1.01"), 12)
    value.engine.trade(Trade(23, 3, D("1.01"), D(45), False))
    assert value.metrics()["CUMULATIVE_NET_PROFIT"] == "0.40"
    assert value.engine.reserve == 5  # Funding waits for completed lot.
    assert value.engine.cost == 60


def test_early_warning_requires_different_positive_candidate(monkeypatch):
    value, _ = replay()
    value.execution = engine()
    buy(value.engine)
    value.engine.entry_us = value.start_us
    value.position_candidate = (10000, 1)
    monkeypatch.setattr(value, "_candidate", lambda _: (10000, 1))
    value.advance_to(value.start_us + 12 * HOUR)
    assert value.urgency == "EARLY_WARNING" and not value.engine.releasing
    monkeypatch.setattr(value, "_candidate", lambda _: (9999, 1))
    value.advance_to(value.start_us + 12 * HOUR + 60_000_000)
    assert value.engine.releasing
    assert value.engine.reserve == 5 and value.engine.inventory == 100


def test_cancel_partial_buy_at18_never_resets_age():
    value, _ = replay()
    value.execution = engine()
    buy(value.engine, "35")
    value.engine.entry_us = value.start_us
    value.position_candidate = (10000, 1)
    deadline = value.start_us + 18 * HOUR
    value.advance_to(deadline)
    assert value.engine.order.cancel_us == deadline + 10
    assert value.engine.order.side == "BUY" and value.engine.inventory == 30
    value.advance_to(deadline + 21)
    assert value.engine.order is None or value.engine.order.release
    assert value.engine.entry_us == value.start_us
    assert value.engine.buy_cost == 30


def test_same_depth_epoch_no_ioc_retry_and_timer_integral():
    value, _ = replay()
    value.execution = engine()
    buy(value.engine)
    value.engine.entry_us = value.start_us
    value.position_candidate = (10000, 1)
    value.engine.releasing = True
    value._submit_next(value.start_us)
    assert value.engine.order.release
    value.engine.book(value.start_us + 11, 7, [(D("0.99"), D(40))], D(1))
    attempts = len(value.engine.orders)
    value._submit_next(value.start_us + 12)
    assert len(value.engine.orders) == attempts
    value.depth_epoch += 1000
    value.engine.book(value.start_us + 13, 8, [(D("0.99"), D(60))], D(1))
    value._submit_next(value.start_us + 13)
    assert len(value.engine.orders) == attempts + 1


def test_clock_filter_transition_without_trade():
    value, trades = replay()
    value.step(trades[0])
    changed = replace(value.engine.rules, tick_size=D("0.001"))
    value.rules_at = lambda _: changed
    value.advance_to(trades[0].time_us + 11)
    assert value.engine.rules == changed
    assert value.processed_trades == 1


def test_complete_includes_partial_final_calendar_day():
    value, trades = replay()
    value.end_us = value.start_us + 26 * HOUR
    value.identity["expected_last_trade_us"] = value.end_us - 1
    value.identity["expected_trade_count"] = 2
    value.step(trades[0])
    value.step(Trade(value.end_us - 1, 77, D(1), D(1), False))
    result = value.finish()
    assert result["CLOSED_UTC_DAYS"] == 2
    assert result["RUN_STATUS"] == "COMPLETE"
    assert result["PROCESSED_TRADES"] == 2


def test_escrow_cannot_cover_more_than_floor_budget():
    value = engine()
    buy(value)
    value.reserve = D("0.1")
    value.book(12, 3, [(D("0.99"), D(100))], D(1))
    assert value.protected_exit()["reason"] == "RELEASE_BLOCKED_BY_RESERVE"
    assert value.reserve == D("0.1")


def test_working_time_integrates_cancel_effective_boundary():
    value, trades = replay()
    value.step(trades[0])
    value.engine.cancel(value.start_us + 1)
    value.advance_to(value.start_us + 15)
    assert value.working_order_us == 12
    assert value.engine.order is None


def test_production_driver_forced_exit_reselects_and_reenters_compounded_bank():
    value, trades = replay()
    for trade in trades:
        value.step(trade)
    assert value.engine.counts["FULLY_FILLED_CYCLES"] == 1
    value.step(Trade(value.start_us + 60, 4, D(1), D(1000), True))
    assert value.engine.entry_us == value.start_us + 60
    deadline = value.engine.entry_us + 18 * HOUR
    value.step(Trade(deadline + 100, 5, D("0.99"), D(1000), True))
    assert value.engine.counts["RELEASE_FILLED"] == 1
    assert value.engine.inventory == 0
    assert not value.engine.needs_reselection
    assert value.engine.orders[-1].side == "BUY"
    assert value.engine.lot_budget == D("100.0095")
    assert value.decisions.state.candidate == (10000, 1)
    assert value.holds_us[-1] == 18 * HOUR + 100
    # Fixture envelope subtracts 0.0001 release slippage from 0.99.
    assert value.engine.reserve == D("3.9905")


def test_capacity_downtime_and_completed_only_hold_quantiles():
    value, _ = replay()
    value.engine.cash = D(20000)
    value.holds_us = [HOUR]
    value.advance_to(value.start_us + HOUR)
    assert value.metrics()["CAPACITY_BLOCKED_HOURS"] == "1"
    value.engine.entry_us = value.start_us
    value.advance_to(value.start_us + 2 * HOUR)
    metrics = value.metrics()
    assert metrics["HOLD_P99_HOURS"] == "1"
    assert metrics["OPEN_CENSORED_HOLD_HOURS"] == "2"


def test_supported_capacity_not_consumed_depth():
    value = engine()
    value.supported_best_level = D(1000)
    value.book(0, 9, [(D("0.9999"), D(1))], D("1.0001"))
    assert value.submit("BUY", D(1), 0) is not None
    assert value.counts["CAPACITY_LIMIT_REACHED"] == 0


def test_price_filter_ineligibility_is_not_capital_downtime():
    value, _ = replay()
    invalid_price_rules = replace(value.engine.rules, min_price=D("1.01"))
    value.rules_at = lambda _: invalid_price_rules
    value.engine.rules = invalid_price_rules
    assert value._can_fund_entry()
    value.advance_to(value.start_us + HOUR)
    assert value.metrics()["DOWNTIME_HOURS"] == "0"
