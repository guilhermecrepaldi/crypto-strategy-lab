import gzip
from array import array
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_strategy_lab.microstructure.hold_risk import (
    DAY_US,
    HOUR_US,
    SCALE,
    EpisodeIndex,
    attach_outcomes,
    candidate_features,
    decision_points,
    qualifies,
    seal_snapshots,
)
from crypto_strategy_lab.microstructure.operator import frozen_m007_strategy
from crypto_strategy_lab.microstructure.serial_replay import (
    USDCUSDT_TICK_CATALOG,
    CandidateTimeline,
    SerialScenarioConfig,
    SerialTape,
    replay_serial_model,
)

D = Decimal


def timeline(lows: list[int], highs: list[int]) -> CandidateTimeline:
    result = CandidateTimeline(100000, 1, array("q", lows), array("q", highs))
    result.build()
    return result


def test_right_censor_does_not_use_future_high() -> None:
    end = 40 * DAY_US * SCALE
    lows = [end - 2 * HOUR_US * SCALE]
    first = EpisodeIndex(timeline(lows, [end + HOUR_US * SCALE]))
    second = EpisodeIndex(timeline(lows, [end + DAY_US * SCALE]))
    a = first.window(end, 24, coverage_start=0)
    assert a == second.window(end, 24, coverage_start=0)
    assert a["completed_entries"] == 0
    assert a["right_censored_entries"] == 1
    assert a["capital_hours_consumed"] == "2"
    assert a["closure"]["1h"]["failures"] == 1
    assert a["closure"]["6h"]["mature_entries"] == 0
    assert not a["closure"]["1h"]["supported"]


def test_same_timestamp_and_horizon_boundary_are_excluded() -> None:
    end = 40 * DAY_US * SCALE
    idx = EpisodeIndex(timeline([end - HOUR_US * SCALE], [end]))
    value = idx.window(end, 24, coverage_start=0)
    assert value["completed_entries"] == 0
    assert value["right_censored_entries"] == 1
    assert value["closure"]["1h"]["mature_entries"] == 0
    with pytest.raises(ValueError, match="STRICT_TIMESTAMP"):
        idx.window(end + 1, 24, coverage_start=0)


def test_fresh_left_boundary_matches_canonical_counts_and_exposure() -> None:
    end = 40 * DAY_US * SCALE
    start = end - DAY_US * SCALE
    lows = [
        start - SCALE,
        start + HOUR_US * SCALE,
        start + 3 * HOUR_US * SCALE,
        end - HOUR_US * SCALE,
    ]
    highs = [start + 2 * HOUR_US * SCALE, start + 4 * HOUR_US * SCALE, end + SCALE]
    source = timeline(lows, highs)
    value = EpisodeIndex(source).window(end, 24, coverage_start=0)
    assert value["completed_entries"] == source.contained_cycles(start, end) == 2
    assert value["capital_hours_consumed"] == "3"
    assert value["right_censored_entries"] == 1


def test_partial_history_and_zero_time_not_security() -> None:
    end = 40 * DAY_US * SCALE
    values = [end - 2 * HOUR_US * SCALE + i * SCALE for i in range(40)]
    source = timeline(values, [value + 1 for value in values])
    result = EpisodeIndex(source).window(end, 24, coverage_start=end - HOUR_US * SCALE)
    assert result["completed_entries"] == 40
    assert result["history"] == "PARTIAL_HISTORY"
    assert result["cycles_per_capital_hour"] is None
    assert not result["closure"]["1h"]["supported"]


def test_window_agrees_with_bruteforce_for_every_prefix() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        (base + timedelta(minutes=i * 17), D("1") if i % 5 in (0, 1, 3) else D("1.00001"))
        for i in range(240)
    ]
    tape = SerialTape.from_events(events, tick_size=D("0.00001"))
    source = tape.timelines((1,))[(100000, 1)]
    idx = EpisodeIndex(source)
    for stop in range(90, 240, 7):
        end = int(tape.events[stop]) // SCALE * SCALE
        start = end - DAY_US * SCALE
        entries, exits = source.cycle_events(start, end)
        last_exit = exits[-1] if exits else start - 1
        pending = next((int(x) for x in source.low_events if last_exit < x < end), None)
        expected_us = sum(b // SCALE - a // SCALE for a, b in zip(entries, exits, strict=True))
        if pending is not None:
            expected_us += end // SCALE - pending // SCALE
        result = idx.window(end, 24, coverage_start=0)
        assert result["completed_entries"] == len(entries)
        assert D(result["capital_hours_consumed"]) == D(expected_us) / HOUR_US
        assert result["right_censored_entries"] == int(pending is not None)


def test_full_candidate_features_are_prefix_invariant() -> None:
    end = 40 * DAY_US * SCALE
    lows = [end - (4 * DAY_US - i * HOUR_US) * SCALE for i in range(80)]
    highs = [x + 60_000_000 * SCALE for x in lows]
    a = candidate_features(EpisodeIndex(timeline(lows, highs)), end, 0, D("0.00001"))
    b = candidate_features(
        EpisodeIndex(timeline([*lows, end], [*highs, end + SCALE])), end, 0, D("0.00001")
    )
    assert a == b
    assert a["risk_status"] == "KNOWN"
    assert not qualifies(a, a)


def test_closure_success_does_not_include_young_completed_entries() -> None:
    end = 40 * DAY_US * SCALE
    low = end - 30 * 60_000_000 * SCALE
    result = EpisodeIndex(timeline([low], [low + SCALE])).window(end, 24, coverage_start=0)
    assert result["completed_entries"] == 1
    assert result["closure"]["1h"]["mature_entries"] == 0
    assert result["closure"]["15m"]["successes"] == 1


def test_sealed_diagnostic_repeatability_and_outcome_join(tmp_path: Path) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        (start + timedelta(minutes=i), D("1") if i % 2 == 0 else D("1.0001"))
        for i in range(-1440, 12)
    ]
    tape = SerialTape.from_events(events, tick_size=D("0.00001"))
    scenario = SerialScenarioConfig(
        tick_size=tape.tick_size,
        historical_tick_catalog_hash=USDCUSDT_TICK_CATALOG.catalog_hash,
        historical_tick_source_url=USDCUSDT_TICK_CATALOG.source_url,
        historical_tick_policy="CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
    )
    result = replay_serial_model(
        tape,
        frozen_m007_strategy(),
        scenario,
        start=start,
        end_exclusive=events[-1][0],
        tick_catalog=USDCUSDT_TICK_CATALOG,
    )
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    points, blocked = decision_points(result)
    assert blocked == result.blocked_reselection_checks
    first = seal_snapshots(result, tape, int(tape.events[0]), a)
    second = seal_snapshots(result, tape, int(tape.events[0]), b)
    assert first["sha256"] == second["sha256"]
    summary = attach_outcomes(result, a, first)
    assert summary["M007_DECISIONS_ANALYZED"] == len(points)
    assert summary["M007_ENTRIES"] == len(result.cycles) + int(result.open_cycle_censored)
    with gzip.open(a / "causal-snapshots.jsonl.gz", "rt") as stream:
        assert "RETROSPECTIVE_DIAGNOSTIC_ONLY" not in stream.read()
    with (a / "causal-snapshots.jsonl.gz").open("ab") as stream:
        stream.write(b"corruption")
    with pytest.raises(ValueError, match="SEAL_MISMATCH"):
        attach_outcomes(result, a, first)
