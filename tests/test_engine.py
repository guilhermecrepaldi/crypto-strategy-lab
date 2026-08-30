from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from crypto_strategy_lab.data.temporal import TemporalComplementaryData
from crypto_strategy_lab.domain import ExternalSignalRecord, NewsRecord
from crypto_strategy_lab.fixtures import load_fixture
from crypto_strategy_lab.simulation.engine import SimulationEngine


def test_decision_after_close_and_execution_on_next_candle(fixture_bundle) -> None:
    candles, provider, _ = fixture_bundle
    result = SimulationEngine(candles, provider).run()
    first_decision = result.decisions[0]
    first_fill = result.fills[0]
    assert first_decision["available_data_until"] < first_decision["simulated_time"]
    assert first_fill.simulated_time == first_decision["simulated_time"]
    next_candle = next(
        candle
        for candle in candles
        if candle.symbol == first_fill.symbol and candle.open_time == first_fill.simulated_time
    )
    assert first_fill.price > next_candle.open  # buy includes spread and slippage


def test_same_dataset_policy_and_seed_are_deterministic(fixture_path) -> None:
    candles_a, provider_a, _ = load_fixture(fixture_path)
    candles_b, provider_b, _ = load_fixture(fixture_path)
    result_a = SimulationEngine(candles_a, provider_a).run()
    result_b = SimulationEngine(candles_b, provider_b).run()
    assert result_a.run_id == result_b.run_id
    assert result_a.dataset_hash == result_b.dataset_hash
    assert result_a.metrics == result_b.metrics
    assert result_a.fills == result_b.fills


def test_current_complementary_data_cannot_enter_historical_request(fixture_bundle) -> None:
    candles, provider, _ = fixture_bundle
    original = deepcopy(candles)
    future_news = NewsRecord(
        published_at=datetime(2026, 8, 30, tzinfo=UTC),
        first_seen_at=datetime(2026, 8, 30, tzinfo=UTC),
        source="fixture",
        canonical_url="https://example.invalid/future",
        assets=["BTC"],
        category="future",
        content_hash="a" * 64,
        dedup_key="future-news",
    )
    future_signal = ExternalSignalRecord(
        provider="coinmarketcap",
        signal_type="fear_greed",
        observed_at=datetime(2026, 8, 30, tzinfo=UTC),
        available_at=datetime(2026, 8, 30, tzinfo=UTC),
        payload={"value": 99},
    )
    complementary = TemporalComplementaryData(news=[future_news], signals=[future_signal])
    result = SimulationEngine(candles, provider, complementary_data=complementary).run()
    for event in result.decisions:
        context = event["input_payload"]["market_context"]["complementary"]
        assert context == {"news": [], "external_signals": []}
    assert candles == original


def test_engine_fails_explicitly_on_relevant_gap(fixture_bundle) -> None:
    candles, provider, _ = fixture_bundle
    without_one_btc_candle = [
        candle
        for candle in candles
        if not (
            candle.symbol == "BTCUSDT"
            and candle.open_time == datetime(2022, 1, 1, 0, 5, tzinfo=UTC)
        )
    ]
    with pytest.raises(ValueError, match="gap"):
        SimulationEngine(without_one_btc_candle, provider)


def test_required_baseline_metrics_are_emitted(fixture_bundle) -> None:
    candles, provider, _ = fixture_bundle
    metrics = SimulationEngine(candles, provider).run().metrics
    assert {
        "final_equity_usdt",
        "net_return",
        "max_drawdown",
        "fees",
        "slippage",
        "turnover",
        "time_in_usdt_ratio",
        "win_rate",
        "payoff",
        "expectancy",
        "profit_factor",
        "average_exposure",
        "max_exposure_observed",
    } <= metrics.keys()
