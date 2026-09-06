from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_strategy_lab.microstructure.price_profile import (
    build_price_profiles,
    write_price_profile_reports,
)


@dataclass(frozen=True)
class Event:
    timestamp: datetime
    price: Decimal
    quantity: Decimal = Decimal("1")
    individual_trade_count: int = 1


START = datetime(2026, 1, 1, tzinfo=UTC)


def test_exact_profiles_and_temporal_rollups_preserve_visits() -> None:
    events = [
        Event(START, Decimal("0.9999")),
        Event(START + timedelta(milliseconds=10), Decimal("0.9999")),
        Event(START + timedelta(seconds=1), Decimal("1.0000"), Decimal("2")),
        Event(START + timedelta(days=1), Decimal("1.0000"), Decimal("3")),
        Event(START + timedelta(days=1, seconds=1), Decimal("0.9999")),
    ]

    profiles, summaries = build_price_profiles(events, symbol="usdcusdt", source_kind="trades")

    days = [item for item in summaries if item.period_type == "DAY"]
    whole = next(item for item in summaries if item.period_type == "ALL")
    whole_10000 = next(
        item for item in profiles if item.period_type == "ALL" and item.price == Decimal("1.0000")
    )
    assert len(days) == 2
    assert whole.symbol == "USDCUSDT"
    assert whole.total_trade_count == 5
    assert whole.total_base_volume == Decimal("8")
    assert whole.price_mode == Decimal("0.9999")
    assert whole.minimum_price == Decimal("0.9999")
    assert whole.maximum_price == Decimal("1.0000")
    assert whole.active_seconds == 4
    assert whole.active_days == 2
    assert whole_10000.visit_count == 1
    assert whole_10000.active_days == 2
    assert whole_10000.aggtrade_count is None


def test_aggtrade_profile_retains_aggregate_and_individual_counts() -> None:
    events = [
        Event(START, Decimal("1.0000"), individual_trade_count=3),
        Event(START + timedelta(seconds=1), Decimal("1.0000"), individual_trade_count=2),
    ]

    profiles, summaries = build_price_profiles(
        events,
        symbol="USDCUSDT",
        source_kind="aggTrades",
    )

    day = next(item for item in profiles if item.period_type == "DAY")
    summary = next(item for item in summaries if item.period_type == "DAY")
    assert day.trade_count == 5
    assert day.aggtrade_count == 2
    assert summary.total_trade_count == 5
    assert summary.total_aggtrade_count == 2


def test_profile_rejects_out_of_order_or_invalid_events() -> None:
    with pytest.raises(ValueError, match="chronological"):
        build_price_profiles(
            [
                Event(START + timedelta(seconds=1), Decimal("1")),
                Event(START, Decimal("1")),
            ],
            symbol="USDCUSDT",
            source_kind="trades",
        )
    with pytest.raises(ValueError, match="positive"):
        build_price_profiles(
            [Event(START, Decimal("1"), individual_trade_count=0)],
            symbol="USDCUSDT",
            source_kind="trades",
        )


def test_profile_reports_are_deterministic_and_complete(tmp_path: Path) -> None:
    profiles, summaries = build_price_profiles(
        [Event(START, Decimal("1"))],
        symbol="USDCUSDT",
        source_kind="trades",
    )

    paths = write_price_profile_reports(profiles, summaries, tmp_path)
    before = {name: path.read_bytes() for name, path in paths.items()}
    repeated = write_price_profile_reports(profiles, summaries, tmp_path)

    assert {name: path.read_bytes() for name, path in repeated.items()} == before
    assert paths["profiles"].read_text(encoding="utf-8").splitlines()[0].startswith("symbol,")
    assert '"period_type": "ALL"' in paths["summaries_json"].read_text(encoding="utf-8")
