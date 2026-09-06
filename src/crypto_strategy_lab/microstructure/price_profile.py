from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from crypto_strategy_lab.domain import require_utc

ArchiveKind = Literal["trades", "aggTrades"]
ProfilePeriod = Literal["DAY", "WEEK", "MONTH", "QUARTER", "YEAR", "ALL"]


class ProfileTrade(Protocol):
    @property
    def timestamp(self) -> datetime: ...

    @property
    def price(self) -> Decimal: ...

    @property
    def quantity(self) -> Decimal: ...

    @property
    def individual_trade_count(self) -> int: ...


class PriceProfileRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    source_kind: ArchiveKind
    period_type: ProfilePeriod
    period: str
    price: Decimal
    trade_count: int
    aggtrade_count: int | None
    visit_count: int
    base_volume: Decimal
    quote_volume: Decimal
    active_seconds: int
    active_minutes: int
    active_hours: int
    active_days: int
    first_seen: datetime
    last_seen: datetime


class MarketPeriodSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    source_kind: ArchiveKind
    period_type: ProfilePeriod
    period: str
    start: datetime
    end: datetime
    total_trade_count: int
    total_aggtrade_count: int | None
    total_base_volume: Decimal
    total_quote_volume: Decimal
    price_mode: Decimal
    price_median: Decimal
    base_volume_weighted_mean: Decimal
    minimum_price: Decimal
    maximum_price: Decimal
    price_range: Decimal
    active_seconds: int
    active_minutes: int
    active_hours: int
    active_days: int
    trades_per_active_second: Decimal
    first_price: Decimal
    last_price: Decimal


@dataclass
class _DailyStats:
    trade_count: int = 0
    aggtrade_count: int = 0
    visit_count: int = 0
    base_volume: Decimal = Decimal("0")
    quote_volume: Decimal = Decimal("0")
    second_bits: int = 0
    minute_bits: int = 0
    hour_bits: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None


def build_price_profiles(
    events: Iterable[ProfileTrade],
    *,
    symbol: str,
    source_kind: ArchiveKind,
) -> tuple[tuple[PriceProfileRow, ...], tuple[MarketPeriodSummary, ...]]:
    """Build exact fixed-price profiles without retaining individual events in memory."""
    normalized_symbol = symbol.strip().upper()
    daily_rows, daily_summaries = _daily_profiles(
        events,
        symbol=normalized_symbol,
        source_kind=source_kind,
    )
    all_rows = list(daily_rows)
    all_summaries = list(daily_summaries)
    for period_type in ("WEEK", "MONTH", "QUARTER", "YEAR", "ALL"):
        rows, summaries = _aggregate_daily(
            daily_rows,
            daily_summaries,
            period_type=period_type,
        )
        all_rows.extend(rows)
        all_summaries.extend(summaries)
    return tuple(all_rows), tuple(all_summaries)


def write_price_profile_reports(
    rows: tuple[PriceProfileRow, ...],
    summaries: tuple[MarketPeriodSummary, ...],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "profiles": output_dir / "price-profiles.csv",
        "summaries_csv": output_dir / "market-period-summaries.csv",
        "summaries_json": output_dir / "market-period-summaries.json",
    }
    _write_models_csv(paths["profiles"], rows)
    _write_models_csv(paths["summaries_csv"], summaries)
    paths["summaries_json"].write_text(
        json.dumps(
            [item.model_dump(mode="json") for item in summaries],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return paths


def _write_models_csv(path: Path, rows: tuple[BaseModel, ...]) -> None:
    if not rows:
        raise ValueError("cannot write an empty profile report")
    serialized = [item.model_dump(mode="json") for item in rows]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(serialized[0]))
        writer.writeheader()
        writer.writerows(serialized)


def _daily_profiles(
    events: Iterable[ProfileTrade],
    *,
    symbol: str,
    source_kind: ArchiveKind,
) -> tuple[tuple[PriceProfileRow, ...], tuple[MarketPeriodSummary, ...]]:
    rows: list[PriceProfileRow] = []
    summaries: list[MarketPeriodSummary] = []
    current_day: date | None = None
    by_price: dict[Decimal, _DailyStats] = {}
    previous_price: Decimal | None = None
    market_seconds = market_minutes = market_hours = 0
    first_price: Decimal | None = None
    last_price: Decimal | None = None

    def flush() -> None:
        nonlocal by_price, market_seconds, market_minutes, market_hours
        if current_day is None or first_price is None or last_price is None:
            return
        period_rows = tuple(
            _daily_row(symbol, source_kind, current_day, price, stats)
            for price, stats in sorted(by_price.items())
        )
        rows.extend(period_rows)
        summaries.append(
            _summary(
                period_rows,
                symbol=symbol,
                source_kind=source_kind,
                period_type="DAY",
                period=current_day.isoformat(),
                active_seconds=market_seconds.bit_count(),
                active_minutes=market_minutes.bit_count(),
                active_hours=market_hours.bit_count(),
                active_days=1,
                first_price=first_price,
                last_price=last_price,
            )
        )
        by_price = {}
        market_seconds = market_minutes = market_hours = 0

    previous_timestamp: datetime | None = None
    for event in events:
        timestamp = require_utc(event.timestamp)
        if previous_timestamp is not None and timestamp < previous_timestamp:
            raise ValueError("profile events must be chronological")
        if event.quantity <= 0 or event.price <= 0 or event.individual_trade_count <= 0:
            raise ValueError("profile events require positive price, quantity and trade count")
        event_day = timestamp.date()
        if current_day is not None and event_day != current_day:
            flush()
            previous_price = None
            first_price = None
        current_day = event_day
        if first_price is None:
            first_price = event.price
        last_price = event.price
        stats = by_price.setdefault(event.price, _DailyStats())
        stats.trade_count += 1 if source_kind == "trades" else event.individual_trade_count
        stats.aggtrade_count += 1
        if event.price != previous_price:
            stats.visit_count += 1
        stats.base_volume += event.quantity
        stats.quote_volume += event.quantity * event.price
        second = timestamp.hour * 3_600 + timestamp.minute * 60 + timestamp.second
        minute = timestamp.hour * 60 + timestamp.minute
        stats.second_bits |= 1 << second
        stats.minute_bits |= 1 << minute
        stats.hour_bits |= 1 << timestamp.hour
        stats.first_seen = stats.first_seen or timestamp
        stats.last_seen = timestamp
        market_seconds |= 1 << second
        market_minutes |= 1 << minute
        market_hours |= 1 << timestamp.hour
        previous_price = event.price
        previous_timestamp = timestamp
    flush()
    if not rows:
        raise ValueError("cannot profile an empty event stream")
    return tuple(rows), tuple(summaries)


def _daily_row(
    symbol: str,
    source_kind: ArchiveKind,
    day: date,
    price: Decimal,
    stats: _DailyStats,
) -> PriceProfileRow:
    if stats.first_seen is None or stats.last_seen is None:  # pragma: no cover - internal guard
        raise ValueError("daily price statistics have no timestamps")
    return PriceProfileRow(
        symbol=symbol,
        source_kind=source_kind,
        period_type="DAY",
        period=day.isoformat(),
        price=price,
        trade_count=stats.trade_count,
        aggtrade_count=stats.aggtrade_count if source_kind == "aggTrades" else None,
        visit_count=stats.visit_count,
        base_volume=stats.base_volume,
        quote_volume=stats.quote_volume,
        active_seconds=stats.second_bits.bit_count(),
        active_minutes=stats.minute_bits.bit_count(),
        active_hours=stats.hour_bits.bit_count(),
        active_days=1,
        first_seen=stats.first_seen,
        last_seen=stats.last_seen,
    )


def _aggregate_daily(
    daily_rows: tuple[PriceProfileRow, ...],
    daily_summaries: tuple[MarketPeriodSummary, ...],
    *,
    period_type: Literal["WEEK", "MONTH", "QUARTER", "YEAR", "ALL"],
) -> tuple[tuple[PriceProfileRow, ...], tuple[MarketPeriodSummary, ...]]:
    summary_by_day = {item.start.date(): item for item in daily_summaries}
    rows_by_period: dict[str, list[PriceProfileRow]] = defaultdict(list)
    for row in daily_rows:
        rows_by_period[_period_key(date.fromisoformat(row.period), period_type)].append(row)
    result_rows: list[PriceProfileRow] = []
    result_summaries: list[MarketPeriodSummary] = []
    for period, source_rows in sorted(rows_by_period.items()):
        days = sorted({date.fromisoformat(item.period) for item in source_rows})
        grouped: dict[Decimal, list[PriceProfileRow]] = defaultdict(list)
        for row in source_rows:
            grouped[row.price].append(row)
        period_rows = tuple(
            _aggregate_price(
                price,
                items,
                period=period,
                period_type=period_type,
                daily_summaries=summary_by_day,
            )
            for price, items in sorted(grouped.items())
        )
        result_rows.extend(period_rows)
        first_summary = summary_by_day[days[0]]
        last_summary = summary_by_day[days[-1]]
        result_summaries.append(
            _summary(
                period_rows,
                symbol=first_summary.symbol,
                source_kind=first_summary.source_kind,
                period_type=period_type,
                period=period,
                active_seconds=sum(summary_by_day[day].active_seconds for day in days),
                active_minutes=sum(summary_by_day[day].active_minutes for day in days),
                active_hours=sum(summary_by_day[day].active_hours for day in days),
                active_days=len(days),
                first_price=first_summary.first_price,
                last_price=last_summary.last_price,
            )
        )
    return tuple(result_rows), tuple(result_summaries)


def _aggregate_price(
    price: Decimal,
    rows: list[PriceProfileRow],
    *,
    period: str,
    period_type: ProfilePeriod,
    daily_summaries: dict[date, MarketPeriodSummary],
) -> PriceProfileRow:
    ordered = sorted(rows, key=lambda item: item.first_seen)
    visits = sum(item.visit_count for item in ordered)
    for prior, current in pairwise(ordered):
        prior_day = prior.first_seen.date()
        current_day = current.first_seen.date()
        if (
            current_day == prior_day + timedelta(days=1)
            and daily_summaries[prior_day].last_price == price
            and daily_summaries[current_day].first_price == price
        ):
            visits -= 1
    return PriceProfileRow(
        symbol=ordered[0].symbol,
        source_kind=ordered[0].source_kind,
        period_type=period_type,
        period=period,
        price=price,
        trade_count=sum(item.trade_count for item in ordered),
        aggtrade_count=(
            sum(item.aggtrade_count or 0 for item in ordered)
            if ordered[0].aggtrade_count is not None
            else None
        ),
        visit_count=visits,
        base_volume=sum((item.base_volume for item in ordered), Decimal("0")),
        quote_volume=sum((item.quote_volume for item in ordered), Decimal("0")),
        active_seconds=sum(item.active_seconds for item in ordered),
        active_minutes=sum(item.active_minutes for item in ordered),
        active_hours=sum(item.active_hours for item in ordered),
        active_days=len(ordered),
        first_seen=ordered[0].first_seen,
        last_seen=ordered[-1].last_seen,
    )


def _summary(
    rows: tuple[PriceProfileRow, ...],
    *,
    symbol: str,
    source_kind: ArchiveKind,
    period_type: ProfilePeriod,
    period: str,
    active_seconds: int,
    active_minutes: int,
    active_hours: int,
    active_days: int,
    first_price: Decimal,
    last_price: Decimal,
) -> MarketPeriodSummary:
    if not rows or active_seconds <= 0:
        raise ValueError("market summary requires active rows")
    total_trades = sum(item.trade_count for item in rows)
    total_base = sum((item.base_volume for item in rows), Decimal("0"))
    total_quote = sum((item.quote_volume for item in rows), Decimal("0"))
    ordered = sorted(rows, key=lambda item: item.price)
    halfway = (total_trades + 1) // 2
    cumulative = 0
    median_price = ordered[-1].price
    for row in ordered:
        cumulative += row.trade_count
        if cumulative >= halfway:
            median_price = row.price
            break
    mode = min(rows, key=lambda item: (-item.trade_count, item.price)).price
    return MarketPeriodSummary(
        symbol=symbol,
        source_kind=source_kind,
        period_type=period_type,
        period=period,
        start=min(item.first_seen for item in rows),
        end=max(item.last_seen for item in rows),
        total_trade_count=total_trades,
        total_aggtrade_count=(
            sum(item.aggtrade_count or 0 for item in rows)
            if rows[0].aggtrade_count is not None
            else None
        ),
        total_base_volume=total_base,
        total_quote_volume=total_quote,
        price_mode=mode,
        price_median=median_price,
        base_volume_weighted_mean=total_quote / total_base,
        minimum_price=ordered[0].price,
        maximum_price=ordered[-1].price,
        price_range=ordered[-1].price - ordered[0].price,
        active_seconds=active_seconds,
        active_minutes=active_minutes,
        active_hours=active_hours,
        active_days=active_days,
        trades_per_active_second=Decimal(total_trades) / Decimal(active_seconds),
        first_price=first_price,
        last_price=last_price,
    )


def _period_key(day: date, period_type: ProfilePeriod) -> str:
    if period_type == "WEEK":
        iso = day.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if period_type == "MONTH":
        return day.strftime("%Y-%m")
    if period_type == "QUARTER":
        return f"{day.year}-Q{(day.month - 1) // 3 + 1}"
    if period_type == "YEAR":
        return str(day.year)
    if period_type == "ALL":
        return "ALL"
    return day.isoformat()
