from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from crypto_strategy_lab.domain import (
    Candle,
    ExternalSignalRecord,
    NewsRecord,
    require_utc,
)


class LookAheadError(ValueError):
    """Raised when data after the simulated boundary is requested or supplied."""


class TemporalMarketData:
    def __init__(self, candles: list[Candle]) -> None:
        grouped: dict[str, list[Candle]] = defaultdict(list)
        for candle in candles:
            grouped[candle.symbol].append(candle)
        self._candles = {
            symbol: sorted(values, key=lambda item: item.open_time)
            for symbol, values in grouped.items()
        }

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._candles))

    def visible_candles(
        self,
        symbol: str,
        *,
        simulated_time: datetime,
        available_until: datetime | None = None,
        lookback: timedelta | None = None,
    ) -> list[Candle]:
        simulated_time = require_utc(simulated_time)
        cutoff = require_utc(available_until or simulated_time)
        if cutoff > simulated_time:
            raise LookAheadError("cutoff cannot exceed simulated time")
        lower_bound = cutoff - lookback if lookback else None
        visible: list[Candle] = []
        for candle in self._candles.get(symbol, []):
            if candle.available_at > cutoff:
                continue
            if lower_bound is not None and candle.open_time < lower_bound:
                continue
            visible.append(candle)
        if any(item.available_at > cutoff for item in visible):
            raise LookAheadError("temporal provider exposed future data")
        return visible

    def all_5m(self) -> list[Candle]:
        return sorted(
            (candle for values in self._candles.values() for candle in values),
            key=lambda item: (item.open_time, item.symbol),
        )


class TemporalComplementaryData:
    """Optional CMC/news gate. The simulator never receives records newer than its clock."""

    def __init__(
        self,
        *,
        news: list[NewsRecord] | None = None,
        signals: list[ExternalSignalRecord] | None = None,
    ) -> None:
        self._news = list(news or [])
        self._signals = list(signals or [])

    def visible(self, available_until: datetime) -> dict[str, list[dict[str, object]]]:
        cutoff = require_utc(available_until)
        news = [
            item.model_dump(mode="json")
            for item in self._news
            if require_utc(item.first_seen_at) <= cutoff
        ]
        signals = [
            item.model_dump(mode="json")
            for item in self._signals
            if require_utc(item.available_at) <= cutoff
        ]
        return {"news": news, "external_signals": signals}
