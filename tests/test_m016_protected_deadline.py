"""Finite synthetic M016 deadline fixtures; no historical data or economics."""

import copy
from dataclasses import replace
from decimal import Decimal as D

import pytest
from test_observed_l2_execution import replay_book, replay_fixture

from crypto_strategy_lab.microstructure.high_uptime_recovery import M016_DEADLINE_POLICY_HASH
from crypto_strategy_lab.microstructure.observed_l2_execution import ObservedL2Replay


def deadline_replay(*, model="M016", policy=M016_DEADLINE_POLICY_HASH, partial_buy=False):
    base, trades = replay_fixture()
    runtime = copy.copy(base.decisions.runtime)
    runtime.tape = base._source_tape
    runtime.timelines = runtime.tape.timelines((1,))
    identity = {**base.identity, "model_id": model}
    if policy is not None:
        identity["deadline_policy_hash"] = policy
    value = ObservedL2Replay(
        runtime,
        base.engine.profile,
        base.rules_at,
        base.envelope,
        start_us=base.start_us,
        end_us=base.end_us,
        identity=identity,
        envelope="PRICE_PRIORITY",
    )
    # Isolate the new emergency branch from the unchanged H1 opportunity rule.
    value.decisions.release_signal = lambda event, engine: None
    value.receive_book(replay_book(value, 0, 100, 1))
    trade = replace(trades[0], quantity=D(35)) if partial_buy else trades[0]
    value.receive_trade(trade, capture_time_us=value.start_us + 200, capture_order=2)
    assert value.engine.inventory == (30 if partial_buy else 100)
    return value


@pytest.mark.parametrize(
    "model,policy", [("M016", None), ("M016", "wrong"), ("M015", M016_DEADLINE_POLICY_HASH)]
)
def test_deadline_identity_is_explicit_not_disguised_m015(model, policy):
    with pytest.raises(ValueError, match="POLICY"):
        deadline_replay(model=model, policy=policy)


def test_m015_has_no_new_timeout_or_policy_state():
    value = deadline_replay(model="M015", policy=None)
    value.advance_to(value.engine.entry_us + 7_200_000_001)
    assert not value.engine.releasing
    assert not hasattr(value.engine, "deadline_policy_hash")
    assert value.engine.counts["HOLD_OVER_2H"] == 0


def test_deadline_cancels_with_response_and_entry_latency_then_fills_at_exact_limit():
    value = deadline_replay()
    entry = value.engine.entry_us
    deadline = entry + 7_200_000_000
    prepare = value._deadline_prepare_us(entry)
    value.advance_to(prepare)
    assert value.engine.releasing
    assert value.engine.order.cancel_us == prepare + value.engine.profile.cancel_latency_us
    assert value.engine.counts["DEADLINE_EXIT_SIGNALS"] == 1
    value.advance_to(deadline - 1)
    assert value.engine.order.release and value.engine.order.active_us == deadline - 1
    value.receive_book(
        replay_book(
            value, deadline - value.start_us, deadline - value.start_us, 3, bids=[(".9999", "100")]
        )
    )
    assert value.engine.inventory == 0 and value.engine.counts["RELEASE_FILLED"] == 1
    assert value.engine.reserve == D("9.99")
    assert value.engine.counts["HOLD_OVER_2H"] == 0
    assert value.position_candidate is None


def test_ten_bps_cap_blocks_deadline_without_fake_liquidation_and_logs_violation_once():
    value = deadline_replay()
    entry = value.engine.entry_us
    prepare, deadline = value._deadline_prepare_us(entry), entry + 7_200_000_000
    value.receive_book(
        replay_book(
            value,
            prepare - value.start_us - 1,
            prepare - value.start_us - 1,
            3,
            bids=[(".998", "100")],
        )
    )
    value.advance_to(deadline + 1)
    assert value.engine.inventory == 100 and value.engine.reserve == 10
    assert value.engine.order is None and value.engine.releasing
    assert value.engine.counts["HOLD_OVER_2H"] == 1
    assert value.engine.counts["PROTECTED_EXIT_BLOCKED:RELEASE_BLOCKED_BY_LOSS_CAP_OR_FLOOR"] > 0
    value.advance_to(deadline + 100)
    assert value.engine.counts["HOLD_OVER_2H"] == 1


def test_snapshot_gap_cannot_guarantee_two_hour_flatness():
    value = deadline_replay()
    entry = value.engine.entry_us
    value.begin_sample_seam(value._deadline_prepare_us(entry), "synthetic-gap")
    value.advance_to(entry + 7_200_000_001)
    assert value.engine.inventory == 100 and value.engine.counts["HOLD_OVER_2H"] == 1
    assert value.engine.counts["PROTECTED_EXIT_BLOCKED:NO_LIQUIDITY"] > 0


def test_reserve_floor_has_precedence_over_deadline():
    value = deadline_replay()
    value.engine.reserve = D("2.52")
    value.receive_book(replay_book(value, 300, 300, 3, bids=[(".9995", "100")]))
    protected = value.engine.protected_exit()
    assert protected["eligible"] is False
    assert D(protected["available_budget"]) == D(".02")
    value.advance_to(value.engine.entry_us + 7_200_000_001)
    assert value.engine.inventory == 100 and value.engine.reserve == D("2.52")


def test_hourly_rejected_predicate_is_persisted_before_deadline():
    value = deadline_replay()

    def reject(event, engine):
        value.decisions.release_evaluations["TOTAL"] += 1
        value.decisions.release_evaluations["LOSS_CAP"] += 1
        return None

    value.decisions.release_signal = reject
    value.advance_to(value.engine.entry_us + 3_600_000_000)
    rows = [row for row in value.engine.audit if row["kind"] == "RELEASE_PREDICATE_EVALUATION"]
    assert len(rows) == 1 and rows[0]["evaluations"] == {"TOTAL": 1, "LOSS_CAP": 1}


def test_unchanged_blocked_predicate_is_not_recomputed_per_event():
    value = deadline_replay()
    deadline = value.engine.entry_us + 7_200_000_000
    value.receive_book(replay_book(value, 300, 300, 3, bids=[(".998", "100")]))
    value.advance_to(deadline + 1)
    key = "PROTECTED_EXIT_BLOCKED:RELEASE_BLOCKED_BY_LOSS_CAP_OR_FLOOR"
    count = value.engine.counts[key]
    value._submit_next(deadline + 2)
    value._submit_next(deadline + 3)
    assert value.engine.counts[key] == count
    value.engine.cash += D(".0001")
    value._submit_next(deadline + 4)
    assert value.engine.counts[key] == count + 1


def test_lower_bid_replenishment_invalidates_blocked_cache_when_best_is_consumed():
    value = deadline_replay()
    deadline = value.engine.entry_us + 7_200_000_000
    value.advance_to(deadline - 1)
    # Preserve the external levels while exhausting their hypothetical budgets.
    value.engine.order = None
    value.engine.bids = [[D(".9999"), D(0)], [D(".9998"), D(0)]]
    value._submit_next(deadline)
    assert value.engine.order is None and value.deadline_block_reason == "NO_LIQUIDITY"
    value.engine.bids[1][1] = D(100)
    value.depth_epoch += 1
    assert value.engine.protected_exit()["eligible"] is True
    value._submit_next(deadline + 1)
    assert value.engine.order is not None and value.engine.order.release
    assert value.deadline_block_key is None


def test_deadline_cancels_partial_buy_and_sells_only_actual_inventory():
    value = deadline_replay(partial_buy=True)
    entry = value.engine.entry_us
    deadline = entry + 7_200_000_000
    assert not value.engine.buy_complete and value.engine.order.side == "BUY"
    value.advance_to(value._deadline_prepare_us(entry))
    assert value.engine.order.side == "BUY" and value.engine.order.cancel_us is not None
    value.advance_to(deadline - 1)
    assert value.engine.order.release and value.engine.order.quantity == 30
    value.receive_book(
        replay_book(
            value, deadline - value.start_us, deadline - value.start_us, 3, bids=[(".9999", "100")]
        )
    )
    assert value.engine.inventory == 0 and value.engine.reserve == D("9.997")
    assert value.engine.counts["NET_POSITIVE_CYCLES"] == 0


def test_deadline_does_not_restart_cancel_already_in_transit():
    value = deadline_replay()
    prepare = value._deadline_prepare_us(value.engine.entry_us)
    value.advance_to(prepare - 5)
    value.engine.cancel(prepare - 5)
    cancel_us = value.engine.order.cancel_us
    count = value.engine.counts["CANCEL_REQUEST_COUNT"]
    value.advance_to(prepare)
    assert value.engine.order.cancel_us == cancel_us
    assert value.engine.counts["CANCEL_REQUEST_COUNT"] == count


def test_partial_deadline_ioc_keeps_aggregate_loss_budget_and_actual_violation():
    value = deadline_replay()
    deadline = value.engine.entry_us + 7_200_000_000
    value.advance_to(deadline - 1)
    value.receive_book(
        replay_book(
            value, deadline - value.start_us, deadline - value.start_us, 3, bids=[(".9995", "40")]
        )
    )
    assert value.engine.inventory == 60
    value.advance_to(deadline + 1)
    assert value.engine.counts["HOLD_OVER_2H"] == 1
    value.receive_book(
        replay_book(
            value,
            deadline - value.start_us + 100,
            deadline - value.start_us + 100,
            4,
            bids=[(".9995", "100")],
        )
    )
    value.receive_book(
        replay_book(
            value,
            deadline - value.start_us + 120,
            deadline - value.start_us + 120,
            5,
            bids=[(".9995", "100")],
        )
    )
    assert value.engine.inventory == 0 and value.engine.reserve == D("9.95")
    assert value.engine.reserve_consumption == D(".05")
    assert value.engine.counts["HOLD_OVER_2H"] == 1
