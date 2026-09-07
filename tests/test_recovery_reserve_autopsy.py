import copy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from crypto_strategy_lab.microstructure.recovery_reserve_autopsy import HOUR, release_autopsy
from crypto_strategy_lab.microstructure.serial_replay import SerialCycle, SerialReplayResult

START = datetime(2026, 1, 1, tzinfo=UTC)
BASE = int(START.timestamp()) * (HOUR // 3600)


def event(hour):
    return BASE + hour * HOUR


def cycle(entry, exit_event):
    return SerialCycle.model_construct(entry_event=event(entry), exit_event=event(exit_event))


def result(*, cycles=(), releases=((0, 30),), open_entry=None, cutoff=100):
    return SerialReplayResult.model_construct(
        cycles=tuple(cycle(*c) for c in cycles),
        release_closures=tuple(cycle(*c) for c in releases),
        open_entry_event=event(open_entry) if open_entry is not None else None,
        end_exclusive=START + timedelta(hours=cutoff),
    )


def rows(*, release=30, entry=0, returned=90):
    return [
        {
            "event": event(release),
            "entry_event": event(entry),
            "retrospective": {
                "original_high_return_event": event(returned) if returned is not None else None,
                "right_censored": returned is None,
            },
        }
    ]


def targets(*release_hours):
    return [
        {"event": event(h), "time_to_replenish_seconds": "3600", "cycles_to_replenish": 3}
        for h in release_hours
    ]


def test_positive_contrast_and_input_immutability():
    replay = result(cycles=((30, 80),))
    releases, replenishments = rows(), targets(30)
    original = copy.deepcopy((releases, replenishments))
    out = release_autopsy(replay, releases, replenishments)
    diagnostic = out[0]["release_lock_diagnostic"]
    assert Decimal(diagnostic["original_counterfactual_lock_hours"]) == 60
    assert Decimal(diagnostic["actual_post_release_lock_hours"]) == 26
    assert Decimal(out[0]["lock_hours_avoided"]) == 34
    assert out[0]["reserve_replenishment_time_seconds"] == "3600"
    assert out[0]["reserve_replenishment_cycles"] == 3
    assert (releases, replenishments) == original


def test_censored_horizon_and_open_episode_are_truncated_at_cutoff():
    out = release_autopsy(result(open_entry=30), rows(returned=None), targets(30))
    diagnostic = out[0]["release_lock_diagnostic"]
    assert diagnostic["right_censored"] is True
    assert Decimal(diagnostic["original_counterfactual_lock_hours"]) == 70
    assert Decimal(diagnostic["actual_post_release_lock_hours"]) == 46
    assert Decimal(out[0]["lock_hours_avoided"]) == 24


def test_overlapping_horizons_never_produce_an_aggregate():
    replay = result(releases=((0, 30), (30, 60)), cycles=((60, 100),))
    out = release_autopsy(replay, rows() + rows(entry=30, release=60), targets(30, 60))
    assert len(out) == 2
    for row in out:
        assert row["release_lock_diagnostic"]["aggregation"].startswith("DO_NOT_SUM")
        assert "NOT_IDENTIFIED" in row["release_lock_diagnostic"]["causal_attribution"]


def test_negative_contrast_requires_invalid_overlapping_inventory_and_is_rejected():
    # This would add 90h actual lock to the 60h old-HIGH window, but violates one lot.
    replay = result(cycles=((0, 100),))
    with pytest.raises(ValueError, match="NONSERIAL_OVERLAPPING"):
        release_autopsy(replay, rows(), targets(30))


def test_zero_horizon_and_unreplenished_target():
    target = targets(30)
    target[0]["time_to_replenish_seconds"] = None
    target[0]["cycles_to_replenish"] = None
    out = release_autopsy(result(), rows(returned=30), target)
    assert Decimal(out[0]["lock_hours_avoided"]) == 0
    assert out[0]["reserve_replenishment_right_censored"] is True


def test_future_high_outside_cutoff_is_rejected():
    with pytest.raises(ValueError, match="INVALID_RETROSPECTIVE_HORIZON"):
        release_autopsy(result(), rows(returned=101), targets(30))
