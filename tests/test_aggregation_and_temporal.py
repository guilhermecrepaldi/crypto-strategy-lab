from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from crypto_strategy_lab.data.aggregation import AggregationError, aggregate_candles
from crypto_strategy_lab.data.binance import DatasetIntegrityError, validate_candle_sequence
from crypto_strategy_lab.data.temporal import LookAheadError, TemporalMarketData
from crypto_strategy_lab.domain import Candle


def test_temporal_provider_blocks_look_ahead(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    provider = TemporalMarketData(candles)
    simulated = datetime(2022, 1, 1, 0, 15, tzinfo=UTC)
    visible = provider.visible_candles(
        "BTCUSDT",
        simulated_time=simulated,
        available_until=simulated - timedelta(microseconds=1),
    )
    assert len(visible) == 3
    assert max(item.available_at for item in visible) < simulated
    with pytest.raises(LookAheadError):
        provider.visible_candles(
            "BTCUSDT",
            simulated_time=simulated,
            available_until=simulated + timedelta(microseconds=1),
        )


def test_aggregation_is_utc_aligned_and_decimal(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    btc = [item for item in candles if item.symbol == "BTCUSDT"]
    aggregated = aggregate_candles(btc, 15)
    first = aggregated[0]
    assert first.open_time == datetime(2022, 1, 1, 0, 0, tzinfo=UTC)
    assert first.open == Decimal("47000")
    assert first.close == Decimal("47200")
    assert first.volume == Decimal("33")
    assert first.timeframe_minutes == 15


def test_incomplete_bucket_is_not_exposed(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    btc = [item for item in candles if item.symbol == "BTCUSDT"][:2]
    assert aggregate_candles(btc, 15) == []


def test_gap_and_duplicate_detection(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    btc = [item for item in candles if item.symbol == "BTCUSDT"]
    gaps = validate_candle_sequence([btc[0], btc[2]])
    assert gaps == [(btc[0].open_time + timedelta(minutes=5), btc[2].open_time)]
    with pytest.raises(DatasetIntegrityError, match="duplicate"):
        validate_candle_sequence([btc[0], btc[0]])


def test_aggregation_rejects_noncanonical_input(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    source = next(item for item in candles if item.symbol == "BTCUSDT")
    invalid = Candle(**{**source.model_dump(), "timeframe_minutes": 15})
    with pytest.raises(AggregationError):
        aggregate_candles([invalid], 15)
