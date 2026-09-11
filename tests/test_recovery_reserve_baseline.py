from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.recovery_reserve_baseline import (
    build_baseline_autopsy,
    write_autopsy_outputs,
)
from crypto_strategy_lab.microstructure.serial_replay import (
    SerialCycle,
    SerialReplayResult,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def _event(timestamp: datetime) -> int:
    return int(timestamp.timestamp() * 1_000_000) * 4096


def _cycle(entry: datetime, exit_: datetime) -> SerialCycle:
    return SerialCycle(
        entry_event=_event(entry),
        exit_event=_event(exit_),
        entry_timestamp=entry,
        exit_timestamp=exit_,
        low=D("1"),
        high=D("1"),
        quantity=D("1"),
        buy_fee_quote=D("0"),
        sell_fee_quote=D("0"),
    )


def _result(
    *,
    cycles: tuple[SerialCycle, ...] = (),
    open_entry: datetime | None = None,
    end: datetime = START + timedelta(days=3),
    daily: dict[date, int] | None = None,
    model_id: str = "M007",
) -> SerialReplayResult:
    return SerialReplayResult.model_construct(
        model_id=model_id,
        start=START,
        end_exclusive=end,
        cycles=cycles,
        release_closures=(),
        open_entry_event=_event(open_entry) if open_entry else None,
        open_entry_timestamp=open_entry,
        daily_cycles=daily
        or {
            START.date(): 0,
            (START + timedelta(days=1)).date(): 1,
            (START + timedelta(days=2)).date(): 0,
        },
    )


def test_zero_days_attribute_only_full_day_coverage_and_censored_hold() -> None:
    result = _result(
        cycles=(
            _cycle(START, START + timedelta(days=1, hours=2)),
            _cycle(START + timedelta(days=1, hours=2), START + timedelta(days=1, hours=12)),
        ),
        open_entry=START + timedelta(days=2),
    )
    payload = build_baseline_autopsy(result)
    rows = {row["date"]: row for row in payload["zero_cycle_day_rows"]}

    assert payload["calendar_day_count"] == 3
    assert rows["2026-01-01"]["causing_position"] == "cycle_000001"
    assert rows["2026-01-03"]["causing_position"] == "open_censored"
    assert payload["top_holds"][0]["duration_hours"] == "26"
    assert payload["top_holds"][0]["lock_hours"] == "2"
    assert any(row["censored"] for row in payload["top_holds"])
    assert payload["top_zero_day_union"]["top1"]["covered_zero_days"] == 1
    assert payload["top_zero_day_union"]["top3"]["covered_zero_days"] == 2


def test_flat_zero_day_is_not_assigned_to_partial_position() -> None:
    result = _result(cycles=(_cycle(START, START + timedelta(hours=12)),))
    payload = build_baseline_autopsy(result)
    rows = {row["date"]: row for row in payload["zero_cycle_day_rows"]}
    assert rows["2026-01-01"]["causing_position"] == "FLAT_NO_COMPLETED_CYCLE"
    assert rows["2026-01-03"]["causing_position"] == "FLAT_NO_COMPLETED_CYCLE"


def test_invalid_model_overlap_and_cutoff_fail_closed() -> None:
    with pytest.raises(ValueError, match="REQUIRES_M007"):
        build_baseline_autopsy(_result(model_id="M010"))
    first = _cycle(START, START + timedelta(days=1))
    second = _cycle(START + timedelta(hours=12), START + timedelta(days=1, hours=1))
    with pytest.raises(ValueError, match="OVERLAPPING"):
        build_baseline_autopsy(_result(cycles=(first, second)))
    after_cutoff = _cycle(START, START + timedelta(days=4))
    with pytest.raises(ValueError, match="OUTSIDE_CUTOFF"):
        build_baseline_autopsy(_result(cycles=(after_cutoff,)))


def test_outputs_are_atomic_projections(tmp_path) -> None:
    payload = build_baseline_autopsy(_result())
    json_path = tmp_path / "out.json"
    csv_path = tmp_path / "out.csv"
    write_autopsy_outputs(payload, json_path, csv_path)
    assert json_path.exists() and csv_path.exists()
    assert "RETROSPECTIVE_DIAGNOSTIC_ONLY" in json_path.read_text(encoding="utf-8")
    assert csv_path.read_text(encoding="utf-8").splitlines()[0].startswith("date,cycles,")
