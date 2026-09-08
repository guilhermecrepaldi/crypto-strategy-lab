"""Bounded synthetic fixtures for the identified executable-budget-only delta."""

import json
from decimal import Decimal as D

import pytest
from test_m016_protected_deadline import deadline_replay
from test_observed_l2_execution import replay_book

from crypto_strategy_lab.microstructure.high_uptime_recovery import (
    M016_DEADLINE_POLICY,
    M016_DEADLINE_POLICY_HASH,
    M017_DEADLINE_POLICY,
    M017_DEADLINE_POLICY_HASH,
)
from scripts.run_l2_monthly_samples import STITCHED_DATES, campaign_design_paths


def m017():
    return deadline_replay(model="M017", policy=M017_DEADLINE_POLICY_HASH)


def test_only_identity_and_actual_cap_change_in_policy():
    assert M016_DEADLINE_POLICY_HASH == (
        "62185b396a90bf9c7f43acf4b1a80b6af187b5082df3f5ba728ad100182c37ec"
    )
    changed = {
        k for k in M016_DEADLINE_POLICY if M016_DEADLINE_POLICY[k] != M017_DEADLINE_POLICY[k]
    }
    assert changed == {"model_id", "executable_loss_cap_bps"}
    spec, protocol, review = campaign_design_paths("M017")
    design = json.loads(spec.read_bytes())
    assert design["deadline_policy_hash"] == M017_DEADLINE_POLICY_HASH
    assert design["normal_theoretical_loss_cap_bps"] == "10"
    assert design["normal_release"] == "B10_H1_B10_F2.5"
    assert tuple(design["source_dates"]) == STITCHED_DATES
    assert protocol.exists() and "M017" in str(review)
    assert campaign_design_paths("M016")[0].name == "M016_MODEL_SPEC.json"


@pytest.mark.parametrize(
    "model,policy",
    [
        ("M017", M016_DEADLINE_POLICY_HASH),
        ("M016", M017_DEADLINE_POLICY_HASH),
        ("M017", None),
        ("M015", M017_DEADLINE_POLICY_HASH),
    ],
)
def test_cross_identity_policy_substitution_rejected(model, policy):
    with pytest.raises(ValueError, match="POLICY"):
        deadline_replay(model=model, policy=policy)


def test_observed_fifteen_bps_exit_only_eligible_under_twenty():
    for value, eligible, budget in [(deadline_replay(), False, ".1"), (m017(), True, ".2")]:
        value.receive_book(replay_book(value, 300, 300, 3, bids=[(".9985", "100")]))
        protected = value.engine.protected_exit()
        assert protected["eligible"] is eligible
        # Eligibility never fabricates a fill or changes the balance.
        assert value.engine.inventory == 100 and value.engine.reserve == 10
        if not eligible:
            assert D(protected["loss_cap_budget"]) == D(budget)


def test_same_timer_actual_fill_and_policy_provenance():
    value = m017()
    deadline = value.engine.entry_us + 7_200_000_000
    control = deadline_replay()
    assert value._deadline_prepare_us(value.engine.entry_us) == control._deadline_prepare_us(
        control.engine.entry_us
    )
    value.advance_to(deadline - 1)
    value.receive_book(
        replay_book(
            value, deadline - value.start_us, deadline - value.start_us, 3, bids=[(".9985", "100")]
        )
    )
    assert value.engine.inventory == 0 and value.engine.reserve == D("9.85")
    assert value.engine.counts["HOLD_OVER_2H"] == 0
    signal = next(row for row in value.engine.audit if row["kind"] == "DEADLINE_EXIT_SIGNAL")
    assert signal["policy_hash"] == M017_DEADLINE_POLICY_HASH


def test_floor_and_more_than_twenty_bps_remain_fail_closed():
    for reserve, bid in [(D("2.52"), ".9985"), (D(10), ".997")]:
        value = m017()
        value.engine.reserve = reserve
        value.receive_book(replay_book(value, 300, 300, 3, bids=[(bid, "100")]))
        assert value.engine.protected_exit()["eligible"] is False
        value.advance_to(value.engine.entry_us + 7_200_000_001)
        assert value.engine.inventory == 100 and value.engine.reserve == reserve
        assert value.engine.counts["HOLD_OVER_2H"] == 1


def test_partial_exit_does_not_reset_twenty_bps_lot_budget():
    value = m017()
    deadline = value.engine.entry_us + 7_200_000_000
    value.advance_to(deadline - 1)
    value.receive_book(
        replay_book(
            value, deadline - value.start_us, deadline - value.start_us, 3, bids=[(".9985", "40")]
        )
    )
    assert value.engine.inventory == 60
    value.receive_book(
        replay_book(
            value,
            deadline - value.start_us + 100,
            deadline - value.start_us + 100,
            4,
            bids=[(".9975", "100")],
        )
    )
    assert value.engine.protected_exit()["eligible"] is False  # .06 + .15 > .20
    assert value.engine.inventory == 60
    assert value.engine.counts["HOLD_OVER_2H"] == 1
