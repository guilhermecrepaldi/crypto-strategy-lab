from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_strategy_lab.decision.providers import DeterministicDecisionProvider
from crypto_strategy_lab.domain import Candle, DecisionResponse


def load_fixture(
    path: Path,
) -> tuple[list[Candle], DeterministicDecisionProvider, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    start = datetime.fromisoformat(payload["start"].replace("Z", "+00:00")).astimezone(UTC)
    candles: list[Candle] = []
    for symbol, raw_prices in payload["symbols"].items():
        prices = [Decimal(value) for value in raw_prices]
        previous = prices[0]
        for index, close in enumerate(prices):
            open_time = start + timedelta(minutes=5 * index)
            high = max(previous, close) * Decimal("1.001")
            low = min(previous, close) * Decimal("0.999")
            close_time = open_time + timedelta(minutes=5) - timedelta(microseconds=1)
            candles.append(
                Candle(
                    symbol=symbol,
                    open_time=open_time,
                    close_time=close_time,
                    available_at=close_time,
                    open=previous,
                    high=high,
                    low=low,
                    close=close,
                    volume=Decimal("10") + index,
                    quote_asset_volume=(Decimal("10") + index) * close,
                    trade_count=100 + index,
                )
            )
            previous = close
    candles.sort(key=lambda item: (item.open_time, item.symbol))
    decisions = [DecisionResponse.model_validate(item) for item in payload["decisions"]]
    return candles, DeterministicDecisionProvider(decisions), payload
