"""Retrospective M007 hold and zero-cycle-day attribution.

This module only describes the already-computed M007 replay.  It does not replay
prices, select a range, or make a release/threshold decision.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from .serial_replay import (
    EVENT_ORDER_SCALE,
    MICROS_PER_SECOND,
    SerialReplayResult,
    _datetime_to_micros,
)

CLASSIFICATION = "RETROSPECTIVE_DIAGNOSTIC_ONLY"
LOCK_RULER = timedelta(hours=24)
CANONICAL_DAY_COUNT = 248
TOP_K = (1, 3, 5, 10, 20)
D = Decimal
MICROS_PER_HOUR = 3_600_000_000
EVENT_UNITS_PER_HOUR = 3600 * MICROS_PER_SECOND * EVENT_ORDER_SCALE


@dataclass(frozen=True)
class _Episode:
    episode_id: str
    entry: datetime
    exit: datetime
    censored: bool
    entry_event: int | None
    exit_event: int

    @property
    def duration(self) -> timedelta:
        return self.exit - self.entry

    @property
    def lock(self) -> timedelta:
        return max(timedelta(0), self.duration - LOCK_RULER)

    @property
    def duration_event_units(self) -> int:
        assert self.entry_event is not None
        return self.exit_event - self.entry_event

    @property
    def lock_event_units(self) -> int:
        return max(0, self.duration_event_units - 24 * EVENT_UNITS_PER_HOUR)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("M007_AUTOPSY_REQUIRES_TIMEZONE_AWARE_UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError("M007_AUTOPSY_REQUIRES_UTC_TIMESTAMPS")
    normalized = value.astimezone(UTC)
    return normalized


def _hours(value: timedelta) -> str:
    return str(D(_microseconds(value)) / D(MICROS_PER_HOUR))


def _event_hours(value: int) -> str:
    return str(D(value) / D(EVENT_UNITS_PER_HOUR))


def _microseconds(value: timedelta) -> int:
    return (
        value.days * 86_400_000_000
        + value.seconds * 1_000_000
        + value.microseconds
    )


def _percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0"
    return str(D(numerator) / D(denominator) * D(100))


def _day_range(start: datetime, end: datetime) -> tuple[date, ...]:
    """Return every UTC calendar date touched by the half-open replay interval."""
    if start >= end:
        raise ValueError("M007_AUTOPSY_INVALID_REPLAY_INTERVAL")
    first = start.date()
    last = (end - timedelta(microseconds=1)).date()
    count = (last - first).days + 1
    return tuple(first + timedelta(days=offset) for offset in range(count))


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _episodes(result: SerialReplayResult) -> tuple[_Episode, ...]:
    if result.release_closures:
        raise ValueError("M007_AUTOPSY_MUST_NOT_CONTAIN_RELEASE_CLOSURES")
    cutoff = _utc(result.end_exclusive)
    episodes: list[_Episode] = []
    for index, cycle in enumerate(result.cycles, start=1):
        entry = _utc(cycle.entry_timestamp)
        exit_ = _utc(cycle.exit_timestamp)
        episodes.append(
            _Episode(
                f"cycle_{index:06d}",
                entry,
                exit_,
                False,
                int(cycle.entry_event),
                int(cycle.exit_event),
            )
        )
    if result.open_entry_event is not None:
        if result.open_entry_timestamp is None:
            raise ValueError("M007_AUTOPSY_OPEN_ENTRY_TIMESTAMP_MISSING")
        episodes.append(
            _Episode(
                "open_censored",
                _utc(result.open_entry_timestamp),
                cutoff,
                True,
                int(result.open_entry_event),
                _datetime_to_micros(cutoff) * EVENT_ORDER_SCALE,
            )
        )
    start = _utc(result.start)
    ordered = sorted(episodes, key=lambda item: (item.entry, item.exit, item.episode_id))
    previous: _Episode | None = None
    for episode in ordered:
        if episode.entry_event is None or episode.entry_event >= episode.exit_event:
            raise ValueError("M007_AUTOPSY_INVALID_EPISODE_INTERVAL")
        if episode.entry < start or episode.exit > cutoff:
            raise ValueError("M007_AUTOPSY_EPISODE_OUTSIDE_CUTOFF")
        if previous is not None and episode.entry_event < previous.exit_event:
            raise ValueError("M007_AUTOPSY_OVERLAPPING_EPISODES")
        previous = episode
    return tuple(ordered)


def _hold_row(episode: _Episode) -> dict[str, Any]:
    return {
        "episode_id": episode.episode_id,
        "entry_timestamp": episode.entry.isoformat(),
        "exit_timestamp": episode.exit.isoformat(),
        "entry_event": episode.entry_event,
        "exit_event": episode.exit_event,
        "censored": episode.censored,
        "duration_hours": _event_hours(episode.duration_event_units),
        "lock_hours": _event_hours(episode.lock_event_units),
    }


def build_baseline_autopsy(result: SerialReplayResult) -> dict[str, Any]:
    """Describe M007 holds and attribute zero-cycle UTC days conservatively."""
    if result.model_id != "M007":
        raise ValueError("M007_AUTOPSY_REQUIRES_M007")
    start = _utc(result.start)
    end = _utc(result.end_exclusive)
    episodes = _episodes(result)
    days = _day_range(start, end)
    daily = {day: int(result.daily_cycles.get(day, 0)) for day in days}
    zero_days = [day for day in days if daily[day] == 0]

    day_rows: list[dict[str, Any]] = []
    covered_by: dict[str, set[date]] = {episode.episode_id: set() for episode in episodes}
    for day in zero_days:
        day_start = max(_midnight(day), start)
        day_end = min(_midnight(day) + timedelta(days=1), end)
        covering = [
            episode
            for episode in episodes
            if episode.entry <= day_start and episode.exit >= day_end
        ]
        if len(covering) > 1:
            raise ValueError("M007_AUTOPSY_OVERLAPPING_DAY_COVERAGE")
        episode = covering[0] if covering else None
        if episode is not None:
            covered_by[episode.episode_id].add(day)
        day_rows.append(
            {
                "date": day.isoformat(),
                "cycles": daily[day],
                "causing_position": episode.episode_id if episode else "FLAT_NO_COMPLETED_CYCLE",
                "causing_episode_id": episode.episode_id if episode else None,
                "causing_duration_hours": (
                    _event_hours(episode.duration_event_units) if episode else None
                ),
                "causing_lock_hours": _event_hours(episode.lock_event_units) if episode else None,
                "causing_censored": episode.censored if episode else None,
                "classification": CLASSIFICATION,
            }
        )

    total_lock = sum(episode.lock_event_units for episode in episodes)
    ranked = sorted(
        episodes,
        key=lambda episode: (
            -episode.duration_event_units,
            episode.entry,
            episode.episode_id,
        ),
    )
    top: dict[str, dict[str, Any]] = {}
    for limit in TOP_K:
        selected = ranked[:limit]
        union_days = (
            set().union(*(covered_by[item.episode_id] for item in selected))
            if selected
            else set()
        )
        selected_lock = sum(item.lock_event_units for item in selected)
        top[f"top{limit}"] = {
            "limit": limit,
            "selected_positions": [item.episode_id for item in selected],
            "covered_zero_days": len(union_days),
            "zero_days_explained": len(union_days),
            "covered_zero_day_percent": _percent(len(union_days), len(zero_days)),
            "zero_days_explained_percent": _percent(len(union_days), len(zero_days)),
            "covered_calendar_day_percent": _percent(len(union_days), len(days)),
            "lock_hours_sum": _event_hours(selected_lock),
            "lock_hours_explained": _event_hours(selected_lock),
            "lock_percent_of_all_holds": _percent(
                selected_lock,
                total_lock,
            ),
            "lock_hours_explained_percent": _percent(
                selected_lock,
                total_lock,
            ),
        }

    return {
        "classification": CLASSIFICATION,
        "model_id": result.model_id,
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "calendar_day_count": len(days),
        "canonical_calendar_day_count": CANONICAL_DAY_COUNT,
        "zero_cycle_days": len(zero_days),
        "zero_cycle_day_percent": _percent(len(zero_days), len(days)),
        "hold_count": len(episodes),
        "top_holds": [_hold_row(episode) for episode in ranked[: max(TOP_K)]],
        "zero_cycle_day_rows": day_rows,
        "top_zero_day_union": top,
        "invariants": {
            "episodes_non_overlapping": True,
            "episodes_within_cutoff": True,
            "final_open_episode_censored_at_cutoff": any(
                episode.censored and episode.exit == end for episode in episodes
            ),
            "release_decisions_made": False,
            "thresholds_applied": False,
        },
    }


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(temporary_name)
        raise


def write_autopsy_outputs(payload: dict[str, Any], json_path: Path, csv_path: Path) -> None:
    """Atomically publish the JSON and zero-day CSV projections."""
    _atomic_write(json_path, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode())
    fields = (
        "date",
        "cycles",
        "causing_position",
        "causing_episode_id",
        "causing_duration_hours",
        "causing_lock_hours",
        "causing_censored",
        "classification",
    )
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(payload["zero_cycle_day_rows"])
    _atomic_write(csv_path, buffer.getvalue().encode())


__all__ = ["build_baseline_autopsy", "write_autopsy_outputs"]
