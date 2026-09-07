from array import array
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from crypto_strategy_lab.microstructure.capital_release import (
    _datetime_to_micros,
    _exact_recovery_cycles,
    _first_cycle_q90,
    _fixed_100_transform,
    _fixed_position_values,
    _kaplan_meier,
    _rounded_quantity,
    _same_band_survival,
    kaplan_meier_q90,
    kaplan_meier_rmst,
)
from crypto_strategy_lab.microstructure.serial_replay import EVENT_ORDER_SCALE, CandidateTimeline


def _event(timestamp: datetime) -> int:
    return _datetime_to_micros(timestamp) * EVENT_ORDER_SCALE


def test_kaplan_meier_rmst_groups_ties_and_censoring() -> None:
    result = kaplan_meier_rmst([1, 2, 3], [True, False, True], Decimal("4"))
    assert abs(result - Decimal(7) / 3) < Decimal("1e-24")


def test_kaplan_meier_preserves_bounds_when_horizon_is_not_supported() -> None:
    result = _kaplan_meier([10, 20], [True, False], Decimal("100"))
    assert result.rmst is None
    assert result.identified is False
    assert result.lower_bound == Decimal("15")
    assert result.upper_bound == Decimal("55")


def test_kaplan_meier_q90_returns_unknown_without_tail_event() -> None:
    assert kaplan_meier_q90([1, 2, 3], [True, True, False], Decimal("10")) is None
    assert kaplan_meier_q90([1, 1, 1, 2], [True, True, True, True], Decimal("10")) == Decimal(2)


def test_fixed_100_uses_its_own_canonical_rounding_and_cash_basis() -> None:
    quantity = _rounded_quantity(Decimal("100"), Decimal("0.99998"), Decimal("0"))
    assert quantity == Decimal("100.00")
    destination_quantity, delta = _fixed_100_transform(
        Decimal("0.99998"), Decimal("1.00008"), Decimal("0"), Decimal("0")
    )
    assert destination_quantity == Decimal("100.00")
    assert delta == Decimal("0.0100000")
    assert (
        _exact_recovery_cycles(
            Decimal("99.50"),
            Decimal("100"),
            Decimal("0.99998"),
            Decimal("1.00008"),
            Decimal("0"),
            Decimal("0"),
        )
        == 51
    )
    quantity, residual, release, target = _fixed_position_values(
        Decimal("0.99998"),
        Decimal("1.00008"),
        Decimal("0.99988"),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
    )
    assert quantity == Decimal("100.00")
    assert residual == Decimal("0.0020000")
    assert release == Decimal("99.9900000")
    assert target == Decimal("100.0100000")


def test_same_band_uses_truncated_prefix_and_censors_focal_once() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    checkpoint = datetime(2025, 4, 1, tzinfo=UTC)
    lows = array("q")
    highs = array("q")
    for day in range(30):
        entry_time = start + timedelta(days=day)
        lows.append(_event(entry_time))
        highs.append(_event(entry_time + timedelta(hours=1)))
    focal_entry = _event(datetime(2025, 2, 1, tzinfo=UTC))
    lows.append(focal_entry)
    timeline_a = CandidateTimeline(
        1,
        1,
        lows,
        array("q", [*highs, _event(checkpoint + timedelta(days=1))]),
    )
    timeline_b = CandidateTimeline(
        1,
        1,
        lows,
        array("q", [*highs, _event(checkpoint + timedelta(days=100))]),
    )
    timeline_a.build()
    timeline_b.build()
    result_a = _same_band_survival((1, 1), _event(checkpoint), focal_entry, 60, timeline_a)
    result_b = _same_band_survival((1, 1), _event(checkpoint), focal_entry, 60, timeline_b)
    assert result_a["focal_included_as_right_censored"] is True
    assert result_a["risk_set"] == 31
    assert result_a["rmst24_seconds"] == result_b["rmst24_seconds"]
    assert result_a["followup_24h_count"] == result_b["followup_24h_count"]
    assert result_a["future_exit_values_read"] is False


def test_first_cycle_q90_is_unchanged_when_only_future_events_change() -> None:
    checkpoint = datetime(2026, 2, 1, tzinfo=UTC)
    lows = array("q")
    highs = array("q")
    for hour in range(30 * 24):
        low = _event(checkpoint - timedelta(hours=30 * 24 - hour) + timedelta(minutes=5))
        lows.append(low)
        highs.append(low + 60 * EVENT_ORDER_SCALE * 1_000_000)
    future_low = _event(checkpoint + timedelta(hours=1))
    timeline_a = CandidateTimeline(
        1,
        1,
        array("q", [*lows, future_low]),
        array("q", [*highs, _event(checkpoint + timedelta(hours=2))]),
    )
    timeline_b = CandidateTimeline(
        1,
        1,
        array("q", [*lows, future_low]),
        array("q", [*highs, _event(checkpoint + timedelta(days=10))]),
    )
    timeline_a.build()
    timeline_b.build()
    result_a = _first_cycle_q90((1, 1), _event(checkpoint), {(1, 1): timeline_a})
    result_b = _first_cycle_q90((1, 1), _event(checkpoint), {(1, 1): timeline_b})
    assert result_a == result_b
    assert result_a["support"] is True
    assert result_a["q90_seconds"] == "360"
    assert result_a["future_event_values_read"] is False
