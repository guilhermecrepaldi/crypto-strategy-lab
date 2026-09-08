"""M015 counterfactual matching semantics, synthetic data only."""

import json
from decimal import Decimal as D

import pytest
from test_b10_reality import engine as fixture
from test_b10_reserve_weekly import replay

from crypto_strategy_lab.microstructure.b10_reality import Trade
from crypto_strategy_lab.microstructure.high_uptime_recovery import (
    B10ReserveReplay,
    HighUptimeExecution,
)


def engine(enabled=True):
    base = fixture()
    value = HighUptimeExecution(
        base.profile, base.rules, b10_owner_reserve=True, priority_trade_through=enabled
    )
    value.book(0, 1, [(D(".9999"), D(1000))], D("1.0001"))
    value.submit("BUY", D(1), 0)
    return value


def test_through_quantity_capped_at_own_limit_and_restorable_partial():
    value = engine()
    value._advance(11)
    value.trade(Trade(12, 2, D(".9998"), D(30), True))
    assert value.inventory == 30 and value.cash == 70 and value.order.queue == 0
    assert value.audit[-1]["source"] == "TRADE_THROUGH"
    assert value.audit[-1]["price"] == "1"
    restored = engine()
    restored.restore(json.loads(json.dumps(value.checkpoint())))
    for candidate in (value, restored):
        candidate.trade(Trade(13, 3, D(".9998"), D(200), True))
        assert candidate.inventory == 100 and candidate.cash == 0
    assert value.checkpoint() == restored.checkpoint()


@pytest.mark.parametrize("when", [10, 11])
def test_pending_or_same_activation_timestamp_cannot_infer(when):
    value = engine()
    value.trade(Trade(when, 2, D(".9998"), D(1000), True))
    assert value.inventory == 0 and value.order.queue == 5


def test_crossing_at_admission_is_rejected_not_rescued():
    value = engine()
    value.book(11, 2, [(D(".9998"), D(1000))], D(".9999"))
    value.trade(Trade(12, 3, D(".9998"), D(1000), True))
    assert value.order is None and value.inventory == 0
    assert value.orders[0].status == "REJECTED"


def test_wrong_aggressor_equal_price_and_default_keep_existing_queue():
    value = engine()
    value._advance(11)
    value.trade(Trade(12, 2, D(".9998"), D(1000), False))
    assert value.inventory == 0 and value.order.queue == 5
    value.trade(Trade(13, 3, D(1), D(4), True))
    assert value.inventory == 0 and value.order.queue == 1
    old = engine(False)
    old._advance(11)
    old.trade(Trade(12, 2, D(".9998"), D(1000), True))
    assert old.inventory == 0 and old.order.queue == 5


def test_cancel_race_before_effective_allowed_but_at_and_after_not():
    for timestamp, filled in ((19, 10), (20, 0), (21, 0)):
        value = engine()
        value._advance(11)
        value.cancel(10)
        value.trade(Trade(timestamp, 2, D(".9998"), D(10), True))
        assert value.inventory == filled


def test_sell_through_pays_limit_not_better_print_price():
    value = engine()
    value._advance(11)
    value.trade(Trade(12, 2, D(".9998"), D(1000), True))
    value.submit("SELL", D("1.0001"), 13)
    value._advance(24)
    value.trade(Trade(25, 3, D("1.0002"), D(1000), False))
    assert value.cash == D("100.009") and value.reserve == D("10.001")
    assert value.counts["NET_POSITIVE_CYCLES"] == 1
    assert value.settlements[-1]["net_profit"] == "0.0100"


def test_identity_and_cross_policy_restore_fail_closed():
    base, _ = replay()
    args = (base.decisions.runtime, base.engine.profile, base.rules_at, base.envelope)
    kwargs = dict(start_us=base.start_us, end_us=base.end_us)
    with pytest.raises(ValueError, match="EXPLICIT_PRIORITY"):
        B10ReserveReplay(*args, **kwargs, identity={**base.identity, "model_id": "M015"})
    value = B10ReserveReplay(
        *args,
        **kwargs,
        identity={**base.identity, "model_id": "M015", "priority_trade_through": True},
    )
    assert value.metrics()["MODEL_ID"] == "M015"
    with pytest.raises(ValueError, match="POLICY_MISMATCH"):
        engine(False).restore(engine().checkpoint())


def test_duplicate_raw_print_cannot_fill_twice():
    value = engine()
    value._advance(11)
    raw = Trade(12, 2, D(".9998"), D(20), True)
    value.trade(raw)
    with pytest.raises(ValueError, match="NONCAUSAL_TRADE"):
        value.trade(raw)
    assert value.inventory == 20


def test_production_replay_through_fill_and_full_checkpoint_continuity():
    base, _ = replay()
    identity = {**base.identity, "model_id": "M015", "priority_trade_through": True}
    args = (base.decisions.runtime, base.engine.profile, base.rules_at, base.envelope)
    kwargs = dict(start_us=base.start_us, end_us=base.end_us, identity=identity)
    value = B10ReserveReplay(*args, **kwargs)
    start = value.start_us
    value.step(Trade(start, 1, D(1), D(100), True))
    value.step(Trade(start + 12, 2, D(".9999"), D(30), True))
    assert value.engine.inventory == 30 and value.position_candidate == (10000, 1)
    restored = B10ReserveReplay(*args, **kwargs)
    restored.restore(json.loads(json.dumps(value.checkpoint())))
    for candidate in (value, restored):
        candidate.step(Trade(start + 13, 3, D(".9999"), D(100), True))
        assert candidate.engine.inventory == 100 and candidate.engine.order.side == "SELL"
    assert value.checkpoint() == restored.checkpoint()


def test_release_never_uses_priority_inference():
    value = engine()
    value._advance(11)
    value.trade(Trade(12, 2, D(".9998"), D(1000), True))
    before = value.counts["PRICE_THROUGH_PRIORITY_INFERENCE"]
    value.submit("SELL", value.protected_exit()["price"], 13, release=True)
    value.trade(Trade(25, 3, D(1), D(1000), False))
    assert value.counts["PRICE_THROUGH_PRIORITY_INFERENCE"] == before
    assert all(
        row["source"] != "TRADE_THROUGH"
        for row in value.audit
        if row["kind"] == "FILL" and row["release"]
    )
