from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from crypto_strategy_lab.domain import Candle, require_utc


class HistoricalUniverseEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    eligible_symbols: list[str]
    evidence: dict[str, str]
    provisional: bool


class HistoricalUniverseProvider(Protocol):
    def eligible_at(self, effective_at: datetime) -> HistoricalUniverseEvidence: ...


class FixtureHistoricalUniverseProvider:
    """Explicitly provisional provider used only by the deterministic vertical slice."""

    def __init__(self, symbols: list[str], reason: str) -> None:
        self._symbols = symbols
        self._reason = reason

    def eligible_at(self, effective_at: datetime) -> HistoricalUniverseEvidence:
        require_utc(effective_at)
        return HistoricalUniverseEvidence(
            eligible_symbols=self._symbols,
            evidence={"fixture": self._reason},
            provisional=True,
        )


def select_top_four_by_historical_volume(
    candles: list[Candle],
    *,
    eligible_symbols: set[str],
    start: datetime,
    end: datetime,
) -> list[tuple[str, Decimal]]:
    start = require_utc(start)
    end = require_utc(end)
    if start >= end:
        raise ValueError("selection interval must be non-empty")
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for candle in candles:
        if candle.symbol not in eligible_symbols:
            continue
        if start <= candle.open_time < end and candle.available_at < end:
            totals[candle.symbol] += candle.quote_asset_volume
    return sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:4]
