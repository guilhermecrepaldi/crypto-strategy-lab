from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from crypto_strategy_lab.domain import Candle


class AggregationError(ValueError):
    pass


def _bucket_start(value: datetime, minutes: int) -> datetime:
    epoch_minutes = int(value.astimezone(UTC).timestamp()) // 60
    bucket_minutes = epoch_minutes - (epoch_minutes % minutes)
    return datetime.fromtimestamp(bucket_minutes * 60, tz=UTC)


def aggregate_candles(candles: list[Candle], timeframe_minutes: int) -> list[Candle]:
    if timeframe_minutes not in {15, 30, 60}:
        raise AggregationError("supported aggregates are 15m, 30m and 60m")
    expected = timeframe_minutes // 5
    grouped: dict[tuple[str, datetime], list[Candle]] = defaultdict(list)
    for candle in candles:
        if candle.timeframe_minutes != 5:
            raise AggregationError("only canonical 5m candles may be aggregated")
        grouped[(candle.symbol, _bucket_start(candle.open_time, timeframe_minutes))].append(candle)

    results: list[Candle] = []
    for (symbol, bucket), members in sorted(grouped.items()):
        members.sort(key=lambda item: item.open_time)
        if len(members) != expected:
            continue
        expected_times = [bucket + timedelta(minutes=5 * index) for index in range(expected)]
        if [member.open_time for member in members] != expected_times:
            raise AggregationError(f"gap or duplicate in {symbol} bucket {bucket.isoformat()}")
        results.append(
            Candle(
                symbol=symbol,
                open_time=bucket,
                close_time=members[-1].close_time,
                available_at=members[-1].available_at,
                open=members[0].open,
                high=max(member.high for member in members),
                low=min(member.low for member in members),
                close=members[-1].close,
                volume=sum((member.volume for member in members), Decimal("0")),
                quote_asset_volume=sum(
                    (member.quote_asset_volume for member in members), Decimal("0")
                ),
                trade_count=sum(member.trade_count for member in members),
                timeframe_minutes=timeframe_minutes,
            )
        )
    return results
