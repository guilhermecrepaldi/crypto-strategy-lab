"""Derived release diagnostics; never imported by the recovery decision runtime."""

from __future__ import annotations

import copy
from bisect import bisect_right
from decimal import Decimal
from typing import Any

from .serial_replay import EVENT_ORDER_SCALE, SerialReplayResult, _datetime_to_micros

HOUR = 3600 * 1_000_000 * EVENT_ORDER_SCALE
CLASSIFICATION = "RETROSPECTIVE_DIAGNOSTIC_ONLY"


def release_autopsy(
    result: SerialReplayResult,
    releases: list[dict[str, Any]],
    replenishments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return new rows with horizon-matched fixed-24h lock contrasts.

    Overlapping release horizons must never be added to form aggregate lock avoided.
    This contrast is mechanically nonnegative for valid serial episodes: resetting
    position age can only reduce excess-24h time within the original HIGH horizon.
    It therefore does not establish economic usefulness or identified causality.
    """
    cutoff = _datetime_to_micros(result.end_exclusive) * EVENT_ORDER_SCALE
    episodes = [
        (int(c.entry_event), int(c.exit_event)) for c in (*result.cycles, *result.release_closures)
    ]
    if result.open_entry_event is not None:
        episodes.append((int(result.open_entry_event), cutoff))
    episodes.sort()
    previous_end: int | None = None
    starts: list[int] = []
    ends: list[int] = []
    prefix = [0]
    for entry, exit_event in episodes:
        if exit_event < entry or exit_event > cutoff:
            raise ValueError("AUTOPSY_INVALID_EPISODE")
        if previous_end is not None and entry < previous_end:
            raise ValueError("AUTOPSY_NONSERIAL_OVERLAPPING_EPISODES")
        previous_end = exit_event
        lock_start = entry + 24 * HOUR
        if exit_event > lock_start:
            starts.append(lock_start)
            ends.append(exit_event)
            prefix.append(prefix[-1] + exit_event - lock_start)

    def cumulative(event: int) -> int:
        index = bisect_right(ends, event)
        total = prefix[index]
        if index < len(starts) and starts[index] < event:
            total += event - starts[index]
        return total

    def hours(duration: int) -> str:
        return str(Decimal(duration) / Decimal(HOUR))

    targets = {int(row["event"]): row for row in replenishments}
    if len(targets) != len(replenishments):
        raise ValueError("AUTOPSY_DUPLICATE_REPLENISHMENT")
    closures = {int(c.exit_event): int(c.entry_event) for c in result.release_closures}
    rows = copy.deepcopy(releases)
    for row in rows:
        release, entry = int(row["event"]), int(row["entry_event"])
        if closures.get(release) != entry:
            raise ValueError("AUTOPSY_RELEASE_CLOSURE_MISMATCH")
        diagnostic = row["retrospective"]
        returned = diagnostic["original_high_return_event"]
        horizon = cutoff if returned is None else int(returned)
        if not entry <= release <= horizon <= cutoff:
            raise ValueError("AUTOPSY_INVALID_RETROSPECTIVE_HORIZON")
        original = max(0, horizon - max(release, entry + 24 * HOUR))
        actual = cumulative(horizon) - cumulative(release)
        contrast = original - actual
        if contrast < 0:
            raise ValueError("AUTOPSY_SERIAL_LOCK_CONTRAST_INVARIANT")
        target = targets.get(release)
        if target is None:
            raise ValueError("AUTOPSY_MISSING_REPLENISHMENT_RECORD")
        row["release_lock_diagnostic"] = {
            "classification": CLASSIFICATION,
            "horizon_event": horizon,
            "right_censored": returned is None,
            "original_counterfactual_lock_hours": hours(original),
            "actual_post_release_lock_hours": hours(actual),
            "lock_hours_avoided": hours(contrast),
            "ruler_hours": 24,
            "aggregation": "DO_NOT_SUM_OVERLAPPING_RELEASE_HORIZONS",
            "causal_attribution": "NOT_IDENTIFIED; AGE_RESET_CONTRAST_IS_MECHANICALLY_NONNEGATIVE",
            "censoring": "TRUNCATED_AT_CANONICAL_CUTOFF; NO_FUTURE_AVOIDANCE_CLAIM",
        }
        row["lock_hours_avoided"] = hours(contrast)
        row["reserve_replenishment_time_seconds"] = target["time_to_replenish_seconds"]
        row["reserve_replenishment_cycles"] = target["cycles_to_replenish"]
        row["reserve_replenishment_right_censored"] = target["time_to_replenish_seconds"] is None
    return rows
