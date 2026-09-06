"""Streaming hourly market descriptors from validated official trade archives."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from crypto_strategy_lab.domain import canonical_hash, require_utc
from crypto_strategy_lab.microstructure.data import HistoryManifest, iter_history


class MarketHour(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: datetime
    end_exclusive: datetime
    trade_records: int
    individual_trades: int
    base_volume: Decimal
    quote_volume: Decimal
    aggressive_buy_base_volume: Decimal
    aggressive_sell_base_volume: Decimal
    open_price: Decimal | None
    high_price: Decimal | None
    low_price: Decimal | None
    close_price: Decimal | None
    distinct_price_levels: int
    price_changes: int
    one_tick_price_changes: int
    absolute_tick_movement: int
    range_ticks: int | None


class MarketHourlyProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "usdcusdt-market-hourly-v1"
    symbol: str
    dataset_hash: str
    start: datetime
    end_exclusive: datetime
    tick_size: Decimal
    profile_hash: str
    hours: tuple[MarketHour, ...]
    unsupported: tuple[str, ...] = (
        "bid_ask_spread",
        "true_mid",
        "book_depth",
        "queue_ahead",
        "fills",
        "partial_fills",
        "executable_capacity",
    )


@dataclass(slots=True)
class _HourAccumulator:
    trade_records: int = 0
    individual_trades: int = 0
    base_volume: Decimal = Decimal("0")
    quote_volume: Decimal = Decimal("0")
    aggressive_buy_base_volume: Decimal = Decimal("0")
    aggressive_sell_base_volume: Decimal = Decimal("0")
    open_price: Decimal = Decimal("0")
    high_price: Decimal = Decimal("0")
    low_price: Decimal = Decimal("0")
    close_price: Decimal = Decimal("0")
    levels: set[Decimal] = field(default_factory=set)
    price_changes: int = 0
    one_tick_price_changes: int = 0
    absolute_tick_movement: int = 0


def build_hourly_market_profile(
    manifest: HistoryManifest,
    *,
    start: datetime,
    end_exclusive: datetime,
    tick_size: Decimal,
) -> MarketHourlyProfile:
    """Aggregate exact observed trades in one streaming pass; empty hours stay explicit."""
    start = require_utc(start)
    end_exclusive = require_utc(end_exclusive)
    if manifest.symbol != "USDCUSDT" or manifest.kind != "trades":
        raise ValueError("market profile accepts only validated USDCUSDT trades")
    if tick_size <= 0 or start >= end_exclusive:
        raise ValueError("invalid market profile interval or tick size")
    raw: dict[datetime, _HourAccumulator] = {}
    for event in iter_history(manifest, start=start, end_exclusive=end_exclusive):
        hour = event.timestamp.replace(minute=0, second=0, microsecond=0)
        bucket = raw.get(hour)
        if bucket is None:
            bucket = _HourAccumulator(
                open_price=event.price,
                high_price=event.price,
                low_price=event.price,
                close_price=event.price,
            )
            raw[hour] = bucket
        previous = bucket.close_price
        scaled = abs(event.price - previous) / tick_size
        if scaled != scaled.to_integral_value():
            raise ValueError(f"price movement is off tick grid at {event.timestamp}")
        movement = int(scaled)
        bucket.trade_records += 1
        bucket.individual_trades += event.individual_trade_count
        bucket.base_volume += event.quantity
        bucket.quote_volume += event.quantity * event.price
        if event.buyer_is_maker:
            bucket.aggressive_sell_base_volume += event.quantity
        else:
            bucket.aggressive_buy_base_volume += event.quantity
        bucket.high_price = max(bucket.high_price, event.price)
        bucket.low_price = min(bucket.low_price, event.price)
        bucket.close_price = event.price
        bucket.levels.add(event.price)
        if movement:
            bucket.price_changes += 1
            bucket.absolute_tick_movement += movement
            if movement == 1:
                bucket.one_tick_price_changes += 1
    hours: list[MarketHour] = []
    cursor = start.replace(minute=0, second=0, microsecond=0)
    while cursor < end_exclusive:
        boundary = min(cursor + timedelta(hours=1), end_exclusive)
        bucket = raw.get(cursor)
        if bucket is None:
            hours.append(
                MarketHour(
                    start=cursor,
                    end_exclusive=boundary,
                    trade_records=0,
                    individual_trades=0,
                    base_volume=Decimal("0"),
                    quote_volume=Decimal("0"),
                    aggressive_buy_base_volume=Decimal("0"),
                    aggressive_sell_base_volume=Decimal("0"),
                    open_price=None,
                    high_price=None,
                    low_price=None,
                    close_price=None,
                    distinct_price_levels=0,
                    price_changes=0,
                    one_tick_price_changes=0,
                    absolute_tick_movement=0,
                    range_ticks=None,
                )
            )
        else:
            high = bucket.high_price
            low = bucket.low_price
            hours.append(
                MarketHour(
                    start=cursor,
                    end_exclusive=boundary,
                    trade_records=bucket.trade_records,
                    individual_trades=bucket.individual_trades,
                    base_volume=bucket.base_volume,
                    quote_volume=bucket.quote_volume,
                    aggressive_buy_base_volume=bucket.aggressive_buy_base_volume,
                    aggressive_sell_base_volume=bucket.aggressive_sell_base_volume,
                    open_price=bucket.open_price,
                    high_price=high,
                    low_price=low,
                    close_price=bucket.close_price,
                    distinct_price_levels=len(bucket.levels),
                    price_changes=bucket.price_changes,
                    one_tick_price_changes=bucket.one_tick_price_changes,
                    absolute_tick_movement=bucket.absolute_tick_movement,
                    range_ticks=int((high - low) / tick_size),
                )
            )
        cursor += timedelta(hours=1)
    identity = {
        "dataset_hash": manifest.dataset_hash,
        "start": start,
        "end_exclusive": end_exclusive,
        "tick_size": tick_size,
        "hours": [item.model_dump(mode="json") for item in hours],
    }
    return MarketHourlyProfile(
        symbol=manifest.symbol,
        dataset_hash=manifest.dataset_hash,
        start=start,
        end_exclusive=end_exclusive,
        tick_size=tick_size,
        profile_hash=canonical_hash(identity),
        hours=tuple(hours),
    )


def write_hourly_market_profile(profile: MarketHourlyProfile, directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "market-hourly.json"
    csv_path = directory / "market-hourly.csv"
    json_path.write_text(profile.model_dump_json(indent=2) + "\n", encoding="utf-8")
    rows = [item.model_dump(mode="json") for item in profile.hours]
    fields = sorted({key for row in rows for key in row})
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest_path = directory / "market-hourly-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": profile.schema_version,
                "dataset_hash": profile.dataset_hash,
                "profile_hash": profile.profile_hash,
                "json": str(json_path),
                "csv": str(csv_path),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"json": json_path, "csv": csv_path, "manifest": manifest_path}


__all__ = [
    "MarketHour",
    "MarketHourlyProfile",
    "build_hourly_market_profile",
    "write_hourly_market_profile",
]
