from __future__ import annotations

from datetime import UTC, datetime

from crypto_strategy_lab.data.universe import (
    FixtureHistoricalUniverseProvider,
    select_top_four_by_historical_volume,
)


def test_universe_selection_uses_only_historical_eligible_volume(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    provider = FixtureHistoricalUniverseProvider(
        ["ADAUSDT", "BNBUSDT", "BTCUSDT", "ETHUSDT"], "CI fixture"
    )
    evidence = provider.eligible_at(datetime(2022, 1, 1, tzinfo=UTC))
    assert evidence.provisional is True
    ranking = select_top_four_by_historical_volume(
        candles,
        eligible_symbols=set(evidence.eligible_symbols),
        start=datetime(2022, 1, 1, tzinfo=UTC),
        end=datetime(2022, 1, 2, tzinfo=UTC),
    )
    assert len(ranking) == 4
    assert ranking[0][0] == "BTCUSDT"
