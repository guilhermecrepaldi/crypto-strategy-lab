"""Physical Binance/Kraken evidence discovery for M033."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

from crypto_strategy_lab.microstructure.multi_stable_data import valid_l2_dates


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_tardis_csv(path: Path, *, required: set[str]) -> dict[str, object]:
    if not path.is_file():
        return {"valid": False, "reason": "FILE_MISSING"}
    rows = 0
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    last_exchange_timestamp: int | None = None
    delivery_monotonic = True
    exchange_timestamp_reorders = 0
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
            exchange_timestamp = int(row["timestamp"])
            timestamp = int(row.get("local_timestamp") or exchange_timestamp)
            if last_timestamp is not None and timestamp < last_timestamp:
                delivery_monotonic = False
            if last_exchange_timestamp is not None and exchange_timestamp < last_exchange_timestamp:
                exchange_timestamp_reorders += 1
            first_timestamp = timestamp if first_timestamp is None else first_timestamp
            last_timestamp = timestamp
            last_exchange_timestamp = exchange_timestamp
            rows += 1
    return {
        "valid": rows > 0 and delivery_monotonic,
        "rows": rows,
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
        "delivery_monotonic": delivery_monotonic,
        "exchange_timestamp_reorders": exchange_timestamp_reorders,
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
        )
        trades = validate_tardis_csv(
            day / "trades.csv.gz",
            required={"exchange", "symbol", "timestamp", "local_timestamp", "price", "amount"},
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
        "PHYSICAL_L2_TRADES_COMMON_DATE_POOL": physical,
        "HISTORICAL_FEE_PROVEN_DATES": [],
        "ELIGIBLE_COMMON_DATE_POOL": [],
        "READY_FOR_HISTORICAL_REPLAY": False,
        "BLOCKER": "KRAKEN_HISTORICAL_FEE_PROFILE_NOT_PROVEN_FOR_CANDIDATE_DATES",
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
