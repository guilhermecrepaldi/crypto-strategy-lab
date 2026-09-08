"""M013 synthetic coordination fixtures, never economic evidence."""

import json
from dataclasses import replace
from decimal import Decimal as D
from decimal import localcontext
from pathlib import Path

import pytest
from test_b10_reality import driver as ancestor_driver

from crypto_strategy_lab.microstructure.b10_reality import Trade
from crypto_strategy_lab.microstructure.continuous_multi_queue import (
    HOUR,
    ContinuousMultiQueueReplay,
)


def replay():
    old, trades = ancestor_driver()
    spec = json.loads(Path("docs/microstructure/M013_MODEL_SPEC.json").read_text())
    value = ContinuousMultiQueueReplay(
        old.decisions.runtime,
        old.execution.profile,
        old.rules_at,
        old.envelope,
        start_us=old.start_us,
        end_us=old.start_us + 25 * HOUR,
        identity={"model_id": "M013", "capital_mode": "COMPOUNDING", "model_hash": "fixture"},
        spec=spec,
    )
    return value, trades


def fund(value, index, cash):
    q = value.queues[index - 1]
    amount = D(cash)
    if index == 4:
        value.core -= amount
    else:
        value.pool -= amount
    q.cash = amount
    q.candidate = (10000, 1)
    q.range_eligible = True
    q.book(0, index, [(D("0.9999"), D(1000))], D("1.0001"))
    return q


def buy(value, q, quantity="1000"):
    q.submit("BUY", D(1), 0)
    q.book(11, 10 + q.queue_id, [(D("0.9999"), D(1000))], D("1.0001"))
    value._match_passive(Trade(11, 11, D(1), D(quantity), True), D(quantity))


def test_obsolete_buy_stays_flat_after_cancel_ack_across_decisions(monkeypatch):
    value, _ = replay()
    q = fund(value, 1, "100")
    q.submit("BUY", D(1), 0)
    monkeypatch.setattr(value, "ranked", lambda _: [])
    start = value.start_us
    q.book(start - 1, 100, [(D("0.9999"), D(1000))], D("1.0001"))
    assert q.order.status == "ACTIVE" and q.book_valid
    value._clock(start)
    assert q.order is not None and q.order.cancel_us is not None
    ack = q.order.cancel_us
    value._clock(ack)
    assert q.order is not None
    value._clock(ack + 1)
    assert q.order is None
    assert not q.range_eligible
    assert q.cash == 100 and value.pool == 0
    value._clock(q.last_cancel_ack_us)
    assert q.order is None
    value._clock(q.last_cancel_ack_us + 1)
    assert q.order is None
    value._clock(start + 60_000_000)
    value._clock(start + 120_000_000)
    assert q.order is None and q.candidate is None
    assert value.pool == 100
    assert value.order_sequence == 1


def test_cancelled_obsolete_buy_reselects_fresh_range_after_checkpoint(monkeypatch):
    value, _ = replay()
    q = fund(value, 1, "100")
    q.range_eligible = False
    q.last_cancel_ack_us = value.start_us
    value.next_decision = value.start_us + 60_000_000
    restored, _ = replay()
    restored.restore(json.loads(json.dumps(value.checkpoint())))
    rows = [{"candidate": (9998, 1), "score": D(1), "c1": 1, "tick": D("0.0001")}]
    monkeypatch.setattr(ContinuousMultiQueueReplay, "ranked", lambda self, _: rows)
    for run in (value, restored):
        run._submit_next(run.start_us)
        assert run.queues[0].order is None
        run._submit_next(run.start_us + 1)
        assert run.queues[0].order is None
        run._clock(run.next_decision)
        assert run.queues[0].candidate == (9998, 1)
        assert run.queues[0].order.price == D("0.9998")
    assert value.checkpoint() == restored.checkpoint()


def test_ineligible_range_does_not_block_existing_inventory_exit():
    value, _ = replay()
    q = fund(value, 1, "100")
    buy(value, q)
    assert q.buy_complete and q.order is None
    q.range_eligible = False
    value._submit_next(12)
    assert q.order is not None and q.order.side == "SELL"


def test_initial_100_operating_10_reserve_no_forced_fourth_queue():
    value, trades = replay()
    value.step(trades[0])
    assert value.operating == 100 and value.reserve == 10
    assert value.metrics()["TOTAL_EQUITY"] == "110"
    assert value.queues[3].order is None and value.queues[3].cash == 0


def test_ten_percent_funding_ninety_percent_compounding():
    value, _ = replay()
    q = fund(value, 1, "100")
    buy(value, q)
    q.submit("SELL", D("1.01"), 12)
    q.book(23, 21, [(D(1), D(1000))], D("1.02"))
    value._match_passive(Trade(23, 23, D("1.01"), D(105), False), D(105))
    assert q.cash == D("100.9") and value.reserve == D("10.1")
    assert value.funding == D("0.1") and value.operating == D("100.9")
    assert q.submit("BUY", D(1), 24).quantity == D("100.9")


def test_one_external_queue_own_fifo_and_independent_ledgers():
    value, _ = replay()
    first, second = fund(value, 1, "50"), fund(value, 2, "50")
    for q in (first, second):
        q.submit("BUY", D(1), 0)
        q.book(11, 20 + q.queue_id, [(D("0.9999"), D(1000))], D("1.0001"))
    remaining = value._match_passive(Trade(11, 50, D(1), D(65), True), D(65))
    assert remaining == 0
    assert first.inventory == 50 and second.inventory == 10
    assert first.cost == 50 and second.cost == 10
    assert len(value.levels) == 1
    value._match_passive(Trade(12, 51, D(1), D(40), True), D(40))
    assert second.inventory == 50
    assert value.operating == 100 and value.reserve == 10
    assert not value.levels


def test_active_profit_stays_in_reserve_and_half_limit():
    value, _ = replay()
    q = fund(value, 4, "5")
    buy(value, q)
    assert value.active_committed == 5 and value.core == 5
    value._invariants()
    q.submit("SELL", D("1.01"), 12)
    q.book(23, 21, [(D(1), D(1000))], D("1.02"))
    value._match_passive(Trade(23, 23, D("1.01"), D(10), False), D(10))
    assert value.operating == 100
    assert value.reserve == D("10.05") and value.core == D("10.05")
    assert q.cash == 0 and value.active_profit == D("0.05")


def test_active_half_blocks_operating_release_budget():
    value, _ = replay()
    active = fund(value, 4, "5")
    buy(value, active)
    op = fund(value, 1, "100")
    buy(value, op)
    value.last_clock_us = 18 * HOUR + 11
    op.book(24, 25, [(D("0.99"), D(1000))], D(1))
    assert op.protected_exit()["reason"] == "RELEASE_BLOCKED_BY_RESERVE"
    assert value.reserve == 10


def test_exact_operating_loss_coverage_and_pending_claim():
    value, _ = replay()
    q = fund(value, 1, "100")
    buy(value, q)
    value.last_clock_us = 18 * HOUR + 11
    protected = q.protected_exit()
    q.submit("SELL", protected["price"], 12, release=True)
    q.book(23, 30, [(D("0.99"), D(40))], D(1))
    assert q.inventory == 60
    assert value.claims[1] == D("0.4") and value.reserve == 10
    q.book(24, 31, [(D("0.99"), D(60))], D(1))
    q.submit("SELL", q.protected_exit()["price"], 25, release=True)
    q.book(36, 32, [(D("0.99"), D(60))], D(1))
    assert q.cash == 100 and value.reserve == 9
    assert value.consumption == 1 and value.claims[1] == 0
    assert value.operating == 100


def test_global_throttle_not_four_independent_limits():
    value, _ = replay()
    first, second = fund(value, 1, "50"), fund(value, 2, "50")
    first.rules = replace(first.rules, orders_per_window=1)
    second.rules = first.rules
    assert first.submit("BUY", D(1), 0) is not None
    assert second.submit("BUY", D(1), 0) is None
    assert second.counts["RATE_LIMIT_REJECTION"] == 1


def test_self_cross_is_deferred_never_self_fill():
    value, _ = replay()
    first, second = fund(value, 1, "50"), fund(value, 2, "50")
    buy(value, first)
    first.submit("SELL", D("1.001"), 12)
    assert second.submit("BUY", D("1.001"), 12) is None
    assert second.counts["SELF_CROSS_DEFERRED"] == 1


def test_stage_boundary_checkpoint_preserves_orders_and_continuation():
    value, trades = replay()
    value.end_us = value.start_us + 21
    value.identity.update(
        expected_last_trade_us=trades[1].time_us, expected_trade_count=2, stage="STAGE_1"
    )
    for trade in trades[:2]:
        value.step(trade)
    value.finish()
    before = value.queues[0].inventory
    checkpoint = json.loads(json.dumps(value.checkpoint()))
    restored, _ = replay()
    restored.end_us, restored.identity = value.end_us, dict(value.identity)
    restored.restore(checkpoint)
    identity = {
        **value.identity,
        "stage": "STAGE_2",
        "expected_last_trade_us": trades[2].time_us,
        "expected_trade_count": 3,
    }
    for run in (value, restored):
        run.extend_to(
            trades[2].time_us + 1, identity, "PASS_TO_EXTENSION", "a" * 64, runtime=run.runtime
        )
        assert run.queues[0].inventory == before
        run.step(trades[2])
    assert value.finish() == restored.finish()
    assert value.checkpoint() == restored.checkpoint()


def test_extension_fail_closed_without_audit_pass():
    value, _ = replay()
    with pytest.raises(ValueError, match="GATE_CLOSED"):
        value.extend_to(value.end_us + 1, value.identity, "FAIL", "a" * 64)


def test_allocation_proportional_distinct_and_minimum_drop(monkeypatch):
    value, _ = replay()
    rows = [
        {"candidate": (10000 + i * 2, 1), "score": D(score), "c1": 3, "tick": D("0.0001")}
        for i, score in enumerate((5, 3, 2, 1))
    ]
    monkeypatch.setattr(value, "ranked", lambda _: rows)
    value._allocate(value.start_us)
    assert [q.cash for q in value.queues[:3]] == [50, 30, 20]
    assert [q.candidate for q in value.queues[:3]] == [(10000, 1), (10002, 1), (10004, 1)]
    assert value.queues[3].cash == 0


def test_capital_time_partition_and_full_stop_metric():
    value, _ = replay()
    value.advance_to(value.start_us + HOUR)
    result = value.metrics()
    assert result["FULL_STOP_HOURS"] == "1"
    assert result["MOTOR_UPTIME"] == "0"
    with localcontext() as ctx:
        ctx.prec = 128
        assert (
            value.productive_capital_us + value.locked_capital_us + value.idle_capital_us
            == value.total_capital_us
        )


def test_active_cancel_cash_stays_committed_until_ack():
    value, _ = replay()
    q = fund(value, 4, "5")
    q.submit("BUY", D(1), 0)
    q.cancel(1)
    q._advance(12)
    value._return_active_cash()
    assert q.cash == 5 and value.core == 5 and value.active_committed == 5
    q._advance(22)
    value._return_active_cash()
    assert q.cash == 0 and value.core == 10 and value.active_committed == 0


def test_shared_ioc_depth_and_raw_event_cap_across_operating_queues():
    value, _ = replay()
    first, second = fund(value, 1, "50"), fund(value, 2, "50")
    buy(value, first)
    buy(value, second)
    for q in (first, second):
        q.entry_us = value.start_us - 18 * HOUR
    value.last_clock_us = value.start_us - 1
    for q in (first, second):
        q.submit("SELL", q.protected_exit()["price"], 12, release=True)
    value.step(Trade(value.start_us, 55, D("0.99"), D(60), True))
    assert first.inventory == 0 and second.inventory == 40
    fills = [
        row for row in value.audit if row["kind"] == "FILL" and row["time_us"] == value.start_us
    ]
    assert sum(D(row["quantity"]) for row in fills) == 60
    assert value.depth_remaining == value.envelope.release_depth - 60


def test_partial_live_order_checkpoint_relinks_global_order_identity():
    value, _ = replay()
    first, second = fund(value, 1, "50"), fund(value, 2, "50")
    for q in (first, second):
        q.submit("BUY", D(1), 0)
        q.book(11, 20 + q.queue_id, [(D("0.9999"), D(1000))], D("1.0001"))
    value._match_passive(Trade(11, 50, D(1), D(65), True), D(65))
    restored, _ = replay()
    restored.restore(json.loads(json.dumps(value.checkpoint())))
    for run in (value, restored):
        run._match_passive(Trade(12, 51, D(1), D(40), True), D(40))
    assert value.checkpoint() == restored.checkpoint()


def test_hard_lock_at24hours_without_timer_fill():
    value, _ = replay()
    q = fund(value, 1, "100")
    buy(value, q)
    q.entry_us = value.start_us
    value.advance_to(value.start_us + 24 * HOUR)
    assert len(value.hard_locks) == 1
    assert value.hard_locks[0]["time_us"] == value.start_us + 24 * HOUR
    assert q.inventory == 100


def test_exclusive_stage_end_defers_boundary_timer_until_extension():
    value, _ = replay()
    q = fund(value, 1, "100")
    buy(value, q)
    q.entry_us = value.start_us
    value.end_us = value.start_us + 24 * HOUR
    value.advance_to(value.end_us)
    assert not value.hard_locks
    value.completed = True
    value.extend_to(value.end_us + HOUR, value.identity, "PASS_TO_EXTENSION", "a" * 64)
    value.advance_to(value.metrics_last_us)
    assert len(value.hard_locks) == 1
    assert q.inventory == 100


def test_cancel_rate_limit_uses_pair_budget_and_has_retry_clock():
    value, _ = replay()
    q = fund(value, 1, "100")
    q.rules = replace(q.rules, orders_per_window=1)
    q.submit("BUY", D(1), 0)
    q.cancel(1)
    assert q.order.cancel_us is None
    assert q.cancel_retry_us == q.rules.window_us
    q.cancel(q.cancel_retry_us)
    assert q.order.cancel_us is not None


def test_active_partial_loss_not_completed_funding_and_physical_minimum():
    value, _ = replay()
    value.core = D(50)
    value.reserve_min = D(50)
    q = fund(value, 4, "20")
    buy(value, q)
    q.book(12, 29, [(D("0.997"), D(100))], D(1))
    q.submit("SELL", q.protected_exit()["price"], 13, release=True)
    q.book(24, 30, [(D("0.997"), D(10))], D(1))
    assert q.inventory == 10
    assert value.active_losses == 0 and value.active_profit == 0
    assert value.reserve_min == D("49.97")
    assert value.recoveries[-1]["reserve_before"] == "50"
    assert value.recoveries[-1]["time_us"] == 24


def test_all_four_queues_share_ioc_passive_event_and_restart_partial():
    value, _ = replay()
    value.core = value.reserve_min = D(50)
    queues = [
        fund(value, 1, "40"),
        fund(value, 2, "30"),
        fund(value, 3, "30"),
        fund(value, 4, "20"),
    ]
    for q in queues:
        buy(value, q)
        q.entry_us = value.start_us - (12 if q.queue_id < 3 else 1) * HOUR
    value.last_clock_us = value.start_us - 1
    for q in queues[:2]:
        protected = q.protected_exit()
        assert protected["eligible"]
        q.submit("SELL", protected["price"], 12, release=True)
    for q in queues[2:]:
        q.book(24, 30 + q.queue_id, [(D("0.98"), D(1000))], D(1))
        q.submit("SELL", D("0.99"), 25)
    event = Trade(value.start_us, 55, D("0.99"), D(110), False)
    value.step(event)
    fills = [
        row for row in value.audit if row["kind"] == "FILL" and row["time_us"] == event.time_us
    ]
    assert [row["queue_id"] for row in fills] == [1, 2, 3, 4]
    assert [D(row["quantity"]) for row in fills] == [40, 30, 30, 5]
    assert sum(D(row["quantity"]) for row in fills) == 105  # Five consumed once by external front.
    assert value.depth_remaining == value.envelope.release_depth - 70
    assert queues[3].inventory == 15 and queues[3].order.filled == 5
    assert value.active_losses == 0  # Q4 completed-lot funding remains unsettled.
    restored, _ = replay()
    restored.restore(json.loads(json.dumps(value.checkpoint())))
    next_event = Trade(value.start_us + 1, 56, D("0.99"), D(15), False)
    for run in (value, restored):
        run.step(next_event)
    assert value.checkpoint() == restored.checkpoint()
    assert value.queues[3].inventory == 0
    assert value.active_losses == D("0.2")
