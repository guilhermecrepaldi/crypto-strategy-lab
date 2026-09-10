"""Physical Binance/Kraken evidence discovery for M033."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from crypto_strategy_lab.microstructure.multi_stable_data import valid_l2_dates


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_tardis_csv(
    path: Path,
    *,
    required: set[str],
    expected_exchange: str | None = None,
    expected_symbol: str | None = None,
    expected_date: str | None = None,
    data_kind: str | None = None,
) -> dict[str, object]:
    if not path.is_file():
        return {"valid": False, "reason": "FILE_MISSING"}
    rows = 0
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    last_exchange_timestamp: int | None = None
    delivery_monotonic = True
    exchange_timestamp_reorders = 0
    structural_errors: set[str] = set()
    snapshot_rows = 0
    snapshot_sides: set[str] = set()
    saw_delta = False
    saw_snapshot = False
    in_snapshot_batch = False
    snapshot_reset_count = 0
    exchange_timestamps_outside_delivery_day = 0
    day_start_us: int | None = None
    day_end_us: int | None = None
    if expected_date is not None:
        start = datetime.fromisoformat(expected_date).replace(tzinfo=UTC)
        day_start_us = int(start.timestamp() * 1_000_000)
        day_end_us = int((start + timedelta(days=1)).timestamp() * 1_000_000)
    with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        fields = set(reader.fieldnames or [])
        if not required.issubset(fields):
            return {
                "valid": False,
                "reason": "REQUIRED_COLUMNS_MISSING",
                "columns": sorted(fields),
            }
        for row in reader:
            try:
                exchange_timestamp = int(row["timestamp"])
                timestamp = int(row.get("local_timestamp") or exchange_timestamp)
                price = Decimal(row["price"])
                amount = Decimal(row["amount"]) if "amount" in row else Decimal("1")
            except (KeyError, ValueError, InvalidOperation):
                structural_errors.add("UNPARSABLE_NUMERIC_FIELD")
                continue
            if expected_exchange is not None and row.get("exchange") != expected_exchange:
                structural_errors.add("WRONG_EXCHANGE")
            if expected_symbol is not None and row.get("symbol") != expected_symbol:
                structural_errors.add("WRONG_SYMBOL")
            if day_start_us is not None and day_end_us is not None:
                if not day_start_us <= timestamp < day_end_us:
                    structural_errors.add("DELIVERY_TIMESTAMP_OUTSIDE_SOURCE_DAY")
                if not day_start_us <= exchange_timestamp < day_end_us:
                    exchange_timestamps_outside_delivery_day += 1
            if price <= 0 or amount < 0 or (data_kind == "trades" and amount <= 0):
                structural_errors.add("INVALID_PRICE_OR_QUANTITY")
            side = row.get("side", "").lower()
            if data_kind == "l2" and side not in {"bid", "ask"}:
                structural_errors.add("INVALID_L2_SIDE")
            if data_kind == "trades" and side not in {"buy", "sell"}:
                structural_errors.add("INVALID_TRADE_SIDE")
            if data_kind == "l2":
                snapshot = row.get("is_snapshot", "").lower()
                if snapshot not in {"true", "false"}:
                    structural_errors.add("INVALID_SNAPSHOT_FLAG")
                elif snapshot == "true":
                    if saw_delta and not in_snapshot_batch:
                        snapshot_reset_count += 1
                    saw_snapshot = True
                    in_snapshot_batch = True
                    snapshot_rows += 1
                    snapshot_sides.add(side)
                    if amount <= 0:
                        structural_errors.add("NON_POSITIVE_SNAPSHOT_QUANTITY")
                else:
                    if not saw_snapshot:
                        structural_errors.add("DELTA_BEFORE_INITIAL_SNAPSHOT")
                    saw_delta = True
                    in_snapshot_batch = False
            if last_timestamp is not None and timestamp < last_timestamp:
                delivery_monotonic = False
            if last_exchange_timestamp is not None and exchange_timestamp < last_exchange_timestamp:
                exchange_timestamp_reorders += 1
            first_timestamp = timestamp if first_timestamp is None else first_timestamp
            last_timestamp = timestamp
            last_exchange_timestamp = exchange_timestamp
            rows += 1
    if data_kind == "l2" and (snapshot_rows == 0 or snapshot_sides != {"bid", "ask"}):
        structural_errors.add("COMPLETE_TWO_SIDED_INITIAL_SNAPSHOT_NOT_PROVEN")
    structurally_valid = rows > 0 and delivery_monotonic and not structural_errors
    return {
        "valid": structurally_valid,
        "validation_class": "INITIAL_SNAPSHOT_AND_TYPED_EVENTS_VALIDATED_CONTINUITY_UNPROVEN"
        if structurally_valid
        else "INVALID",
        "rows": rows,
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
        "delivery_monotonic": delivery_monotonic,
        "exchange_timestamp_reorders": exchange_timestamp_reorders,
        "snapshot_rows": snapshot_rows,
        "snapshot_sides": sorted(snapshot_sides),
        "snapshot_reset_count": snapshot_reset_count,
        "exchange_timestamps_outside_delivery_day": exchange_timestamps_outside_delivery_day,
        "source_sequence_available": False,
        "book_continuity_proven": False,
        "structural_errors": sorted(structural_errors),
        "sha256": sha256(path),
    }


def kraken_valid_dates(root: Path) -> list[dict[str, object]]:
    base = root / "data" / "l2" / "tardis" / "kraken" / "usdc-usdt"
    rows: list[dict[str, object]] = []
    if not base.is_dir():
        return rows
    for day in sorted(path for path in base.iterdir() if path.is_dir()):
        l2 = validate_tardis_csv(
            day / "incremental_book_L2.csv.gz",
            required={
                "exchange",
                "symbol",
                "timestamp",
                "local_timestamp",
                "side",
                "price",
                "amount",
            },
            expected_exchange="kraken",
            expected_symbol="USDC/USDT",
            expected_date=day.name,
            data_kind="l2",
        )
        trades = validate_tardis_csv(
            day / "trades.csv.gz",
            required={"exchange", "symbol", "timestamp", "local_timestamp", "price", "amount"},
            expected_exchange="kraken",
            expected_symbol="USDC/USDT",
            expected_date=day.name,
            data_kind="trades",
        )
        if l2.get("valid") and trades.get("valid"):
            rows.append({"date": day.name, "l2": l2, "trades": trades})
    return rows


def common_date_report(root: Path) -> dict[str, object]:
    binance = valid_l2_dates(root, "USDCUSDT")
    kraken = kraken_valid_dates(root)
    physical = sorted({row["date"] for row in binance} & {row["date"] for row in kraken})
    return {
        "MODEL": "M033_MULTI_VENUE_KRAKEN_L3_VALIDATION_V1",
        "PAIR": "USDC/USDT",
        "BINANCE_NATIVE_SYMBOL": "USDCUSDT",
        "KRAKEN_NATIVE_SYMBOL": "USDC/USDT",
        "BINANCE_VALIDATED_DATES": binance,
        "KRAKEN_VALIDATED_DATES": kraken,
        "STRUCTURAL_FILE_COMMON_DATE_POOL": physical,
        "PHYSICAL_REPLAY_READY_COMMON_DATE_POOL": [],
        "HISTORICAL_FEE_PROVEN_DATES": [],
        "ELIGIBLE_COMMON_DATE_POOL": [],
        "READY_FOR_HISTORICAL_REPLAY": False,
        "BLOCKERS": [
            "KRAKEN_SOURCE_CONTINUITY_NOT_PROVEN",
            "KRAKEN_HISTORICAL_FEE_PROFILE_NOT_PROVEN_FOR_CANDIDATE_DATES",
        ],
    }


def write_report(root: Path, output: Path) -> dict[str, object]:
    payload = common_date_report(root)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


__all__ = [
    "common_date_report",
    "kraken_valid_dates",
    "sha256",
    "validate_tardis_csv",
    "write_report",
]
