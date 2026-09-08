from datetime import UTC, datetime
from decimal import Decimal

from crypto_strategy_lab.microstructure.price_occupancy import narrowest_interval


def test_narrowest_interval_uses_time_not_print_count() -> None:
    result = narrowest_interval({100: 7, 101: 1, 102: 2}, Decimal("0.80"))
    assert result["low_ticks"] == 100
    assert result["high_ticks"] == 101
    assert result["covered_duration_us"] == 8


def test_narrowest_interval_tie_prefers_more_mass_then_lower_low() -> None:
    result = narrowest_interval({100: 4, 101: 2, 102: 4}, Decimal("0.40"))
    assert result["low_ticks"] == 100
    assert result["high_ticks"] == 100


def test_calendar_boundary_is_timezone_explicit() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    assert int((end - start).total_seconds()) == 365 * 86_400
