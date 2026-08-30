from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from crypto_strategy_lab.domain import Candle, canonical_hash, require_utc


class HistoricalUniverseEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    eligible_symbols: list[str]
    evidence: dict[str, str]
    provisional: bool


DEFAULT_STABLECOIN_BASES = frozenset(
    {
        "BUSD",
        "DAI",
        "FDUSD",
        "PAX",
        "TUSD",
        "USDC",
        "USDP",
        "UST",
        "USTC",
    }
)
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")


def static_symbol_exclusion(
    symbol: str, stablecoin_bases: frozenset[str] = DEFAULT_STABLECOIN_BASES
) -> str | None:
    normalized = symbol.upper()
    if not normalized.isascii() or not normalized.isalnum():
        return "unsupported non-ASCII or non-alphanumeric symbol"
    if not normalized.endswith("USDT") or normalized == "USDT":
        return "not a crypto/USDT Spot pair"
    base = normalized.removesuffix("USDT")
    if base in stablecoin_bases:
        return "stablecoin base asset"
    if base.endswith(LEVERAGED_SUFFIXES):
        return "leveraged token"
    return None


class HistoricalRankingEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    rank: int = Field(gt=0)
    symbol: str
    quote_volume_usdt: Decimal
    candle_count: int
    first_open_time: datetime
    last_available_at: datetime


class HistoricalSelectionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    episode_start: datetime
    lookback_start: datetime
    data_cutoff: datetime
    selected_symbols: list[str]
    ranking: list[HistoricalRankingEntry]
    exclusions: dict[str, str]
    criteria: dict[str, object]
    selection_hash: str
    locked_test_accessed: bool = False


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


def select_causal_historical_universe(
    candles: list[Candle],
    *,
    episode_start: datetime,
    lookback: timedelta = timedelta(days=90),
    required_assets: int = 4,
    stablecoin_bases: frozenset[str] = DEFAULT_STABLECOIN_BASES,
) -> HistoricalSelectionResult:
    """Rank only complete, historically existing Spot crypto/USDT pairs before an episode."""
    episode_start = require_utc(episode_start)
    if lookback <= timedelta(0):
        raise ValueError("selection lookback must be positive")
    lookback_start = episode_start - lookback
    cutoff = episode_start - timedelta(microseconds=1)
    grouped: dict[str, list[Candle]] = defaultdict(list)
    for candle in candles:
        if candle.open_time >= episode_start or candle.available_at > cutoff:
            continue
        if candle.open_time >= lookback_start:
            grouped[candle.symbol].append(candle)
    exclusions: dict[str, str] = {}
    candidates: list[tuple[str, Decimal, list[Candle]]] = []
    expected = int(lookback / timedelta(minutes=5))
    for symbol, series in sorted(grouped.items()):
        static_exclusion = static_symbol_exclusion(symbol, stablecoin_bases)
        if static_exclusion:
            exclusions[symbol] = static_exclusion
            continue
        series.sort(key=lambda item: item.open_time)
        if series[0].open_time > lookback_start:
            exclusions[symbol] = "asset did not cover the full pre-episode window"
            continue
        if series[-1].open_time + timedelta(minutes=5) < episode_start:
            exclusions[symbol] = "pair was unavailable before episode start"
            continue
        if len(series) != expected:
            exclusions[symbol] = f"incomplete candles: expected {expected}, got {len(series)}"
            continue
        if any(
            right.open_time != left.open_time + timedelta(minutes=5)
            for left, right in pairwise(series)
        ):
            exclusions[symbol] = "gap or duplicate in selection window"
            continue
        candidates.append(
            (symbol, sum((item.quote_asset_volume for item in series), Decimal("0")), series)
        )
    ordered = sorted(candidates, key=lambda item: (-item[1], item[0]))
    ranking = [
        HistoricalRankingEntry(
            rank=index,
            symbol=symbol,
            quote_volume_usdt=volume,
            candle_count=len(series),
            first_open_time=series[0].open_time,
            last_available_at=series[-1].available_at,
        )
        for index, (symbol, volume, series) in enumerate(ordered, start=1)
    ]
    if len(ranking) < required_assets:
        raise ValueError(
            f"only {len(ranking)} historically complete eligible pairs; need {required_assets}"
        )
    criteria: dict[str, object] = {
        "market": "SPOT",
        "quote_asset": "USDT",
        "ranking_metric": "sum_quote_asset_volume",
        "lookback_seconds": int(lookback.total_seconds()),
        "full_5m_coverage_required": True,
        "stablecoin_bases_excluded": sorted(stablecoin_bases),
        "leveraged_suffixes_excluded": list(LEVERAGED_SUFFIXES),
        "available_at_lte": cutoff,
    }
    selected = [item.symbol for item in ranking[:required_assets]]
    identity = {
        "episode_start": episode_start,
        "lookback_start": lookback_start,
        "cutoff": cutoff,
        "ranking": [item.model_dump(mode="json") for item in ranking],
        "criteria": criteria,
    }
    return HistoricalSelectionResult(
        episode_start=episode_start,
        lookback_start=lookback_start,
        data_cutoff=cutoff,
        selected_symbols=selected,
        ranking=ranking,
        exclusions=exclusions,
        criteria=criteria,
        selection_hash=canonical_hash(identity),
    )
