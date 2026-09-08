"""M014 synthetic treasury/bridge tests. No historical market reads."""

import json
from decimal import Decimal as D

import pytest
from test_b10_reality import driver
from test_b10_reality import engine as fixture
from test_high_uptime_recovery import buy, profitable_cycle

from crypto_strategy_lab.microstructure.b10_reality import FrozenB10Decisions
from crypto_strategy_lab.microstructure.high_uptime_recovery import (
    HOUR,
    B10ReserveReplay,
    HighUptimeExecution,
)
from crypto_strategy_lab.microstructure.recovery_reserve import ReserveConfig


def execution():
    base = fixture()
    value = HighUptimeExecution(base.profile, base.rules, b10_owner_reserve=True)
    value.book(0, 1, [(D(".9999"), D(1000))], D("1.0001"))
    return value


def replay():
    base, trades = driver()
    base.decisions.runtime.config = ReserveConfig(D(".02"), 1, D(10), D("2.5"))
    value = B10ReserveReplay(
        base.decisions.runtime,
        base.execution.profile,
        base.rules_at,
        base.envelope,
        start_us=base.start_us,
        end_us=base.start_us + 7 * 24 * HOUR,
        identity={**base.identity, "model_id": "M014", "capital_mode": "COMPOUNDING"},
    )
    return value, trades


def test_owner_compounding_and_exact_funding():
    value = execution()
    profitable_cycle(value)
    assert value.cash == D("100.90") and value.reserve == D("10.10")
    assert value.submit("BUY", D(1), 24).quantity == D("100.90")


def test_absolute_floor_and_exact_release():
    value = execution()
    buy(value)
    protection = value.protected_exit()
    assert protection["price"] == D(".925")
    value.submit("SELL", protection["price"], 12, release=True)
    value.book(23, 3, [(D(".925"), D(100))], D(1))
    assert value.cash == 100 and value.reserve == D("2.5")
    assert value.reserve_consumption == D("7.5")
    assert value.counts["FULLY_FILLED_CYCLES"] == 0


def test_default_bridge_still_rejects_f25_and_explicit_bridge_accepts():
    value, _ = replay()
    with pytest.raises(ValueError, match="B10_FROZEN_CONFIG_MISMATCH"):
        FrozenB10Decisions(value.decisions.runtime, start_event=value.start_us * 4096)
    assert value.engine.reserve == 10 and value.engine.reserve_floor == D("2.5")


def test_weekly_restore_and_no_forced_timeout():
    value, trades = replay()
    for trade in trades[:2]:
        value.step(trade)
    value.advance_to(value.start_us + 24 * HOUR)
    snapshot = json.loads(json.dumps(value.checkpoint()))
    restored, _ = replay()
    restored.restore(snapshot)
    assert restored.checkpoint() == value.checkpoint()
    assert restored.engine.counts["RELEASE_SIGNALS"] == value.engine.counts["RELEASE_SIGNALS"]
    assert restored.metrics()["TOTAL_EQUITY"] == value.metrics()["TOTAL_EQUITY"]
    assert not hasattr(restored, "urgency")


def test_cross_policy_restore_rejected():
    value = execution()
    other = HighUptimeExecution(value.profile, value.rules)
    with pytest.raises(ValueError, match="POLICY_MISMATCH"):
        other.restore(value.checkpoint())


def test_partial_release_retains_realized_claim_and_restores_exactly():
    value = execution()
    buy(value)
    value.submit("SELL", value.protected_exit()["price"], 12, release=True)
    value.book(23, 3, [(D(".99"), D(40))], D(1))
    assert value.inventory == 60 and value.reserve == 10
    assert value.reserve_escrow == D(".4")
    restored = execution()
    restored.restore(json.loads(json.dumps(value.checkpoint())))
    for candidate in (value, restored):
        candidate.book(24, 4, [(D(".99"), D(60))], D(1))
        candidate.submit("SELL", candidate.protected_exit()["price"], 25, release=True)
        candidate.book(36, 5, [(D(".99"), D(60))], D(1))
        assert candidate.inventory == 0 and candidate.cash == 100
        assert candidate.reserve == 9 and candidate.reserve_consumption == 1
    assert restored.checkpoint() == value.checkpoint()


def test_zero_days_excludes_current_partial_day():
    value, _ = replay()
    value.advance_to(value.start_us + 25 * HOUR)
    value.net_days["2026-01-02"] = 1
    assert value.metrics()["ZERO_CYCLE_DAYS"] == 1


def release_replay():
    from datetime import UTC, datetime, timedelta

    from crypto_strategy_lab.microstructure.serial_replay import SerialTape

    value, _ = replay()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    values = [(-100 + i, "1" if i % 2 == 0 else "1.0001") for i in range(20)]
    values.extend((30 + i * 60, ".9998" if i % 2 == 0 else ".9999") for i in range(30))
    values.append((3599, ".9999"))
    tape = SerialTape.from_events(
        [(start + timedelta(seconds=t), D(p)) for t, p in values], tick_size=D(".0001")
    )
    value.decisions.runtime.tape = tape
    value.decisions.runtime.timelines = tape.timelines((1,))
    return value


def test_f25_partial_bridge_exact_original_authority_and_no_mutation():
    import copy

    from test_b10_reality import sell

    value = release_replay()
    ledger = execution()
    buy(ledger)
    ledger.entry_us = value.start_us
    sell(ledger, quantity="45")
    bridge = value.decisions
    boundary = (value.start_us + HOUR) * 4096
    state = copy.deepcopy(bridge.state)
    state.entry_event = value.start_us * 4096
    state.cash, state.inventory, state.inventory_cost = ledger.cash, ledger.inventory, ledger.cost
    reference = copy.copy(bridge.runtime)
    reference.reserve = ledger.reserve
    reference.releases = []
    assert reference(state, boundary)
    before = ledger.checkpoint()
    signal = bridge.release_signal(boundary, ledger)
    assert signal == reference.releases[-1]
    assert D(signal["quantity"]) == 60 and D(signal["loss_usdt"]) == D(".006")
    assert ledger.checkpoint() == before and ledger.reserve == 10


def test_actual_hourly_release_cancel_ioc_and_destination():
    from crypto_strategy_lab.microstructure.b10_reality import Trade

    value = release_replay()
    start = value.start_us
    value.step(Trade(start, 1, D(1), D(1000), True))
    value.step(Trade(start + 11, 2, D(1), D(1000), True))
    assert value.engine.inventory == 100
    value.step(Trade(start + 3_599_000_000, 3, D(".9999"), D(1000), True))
    deadline = start + 11 + HOUR
    value.advance_to(deadline)
    assert value.engine.releasing and value.engine.counts["RELEASE_SIGNALS"] == 1
    assert value.engine.order.cancel_us is not None
    value.advance_to(deadline + 22)
    assert value.engine.order.release
    value.step(Trade(deadline + 33, 4, D(".9999"), D(1000), True))
    assert value.engine.counts["RELEASE_FILLED"] == 1
    assert value.engine.cash == 100
    # Envelope applies .0001 release slippage: actual bid .9998, not trigger .9999.
    assert value.engine.reserve == D("9.98")
    assert value.engine.inventory == 0
    assert value.decisions.state.candidate == (9998, 1)
    assert value.engine.order.side == "BUY" and value.engine.order.price == D(".9998")
