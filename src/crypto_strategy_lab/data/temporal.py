from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import pairwise

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
        self._available_times = {
            symbol: [item.available_at for item in values]
            for symbol, values in self._candles.items()
        }
        self._available_monotonic = {
            symbol: all(left.available_at <= right.available_at for left, right in pairwise(values))
            for symbol, values in self._candles.items()
        }
        self._open_times = {
            symbol: [item.open_time for item in values] for symbol, values in self._candles.items()
        }
        self._by_open_time: dict[datetime, dict[str, Candle]] = defaultdict(dict)
        for symbol, values in self._candles.items():
            for candle in values:
                self._by_open_time[candle.open_time][symbol] = candle

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
        values = self._candles.get(symbol, [])
        if self._available_monotonic.get(symbol, True):
            upper = bisect_right(self._available_times.get(symbol, []), cutoff)
            lower = (
                bisect_left(self._open_times.get(symbol, []), lower_bound, hi=upper)
                if lower_bound is not None
                else 0
            )
            visible = values[lower:upper]
        else:
            visible = [
                candle
                for candle in values
                if candle.available_at <= cutoff
                and (lower_bound is None or candle.open_time >= lower_bound)
            ]
        if any(item.available_at > cutoff for item in visible):
            raise LookAheadError("temporal provider exposed future data")
        return visible

    def all_5m(self) -> list[Candle]:
        return sorted(
            (candle for values in self._candles.values() for candle in values),
            key=lambda item: (item.open_time, item.symbol),
        )

    def prices_at(self, open_time: datetime, *, field: str) -> dict[str, Decimal]:
        if field not in {"open", "close"}:
            raise ValueError("price field must be open or close")
        candles = self._by_open_time.get(require_utc(open_time), {})
        return {symbol: getattr(candle, field) for symbol, candle in candles.items()}


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
