from __future__ import annotations

import gzip
from pathlib import Path

from crypto_strategy_lab.microstructure.multi_venue_data import validate_tardis_csv


def write_csv(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as output:
        output.write(text)


def test_tardis_l2_validation_requires_physical_columns_and_monotonic_time(tmp_path) -> None:
    path = tmp_path / "l2.csv.gz"
    write_csv(
        path,
        "exchange,symbol,timestamp,local_timestamp,is_snapshot,side,price,amount\n"
        "kraken,USDC-USDT,1,2,true,bid,1,5\n"
        "kraken,USDC-USDT,2,3,false,ask,1.0001,4\n",
    )
    result = validate_tardis_csv(
        path,
        required={"exchange", "symbol", "timestamp", "local_timestamp", "side", "price", "amount"},
    )
    assert result["valid"] is True
    assert result["rows"] == 2


def test_tardis_validation_rejects_reordered_events(tmp_path) -> None:
    path = tmp_path / "l2.csv.gz"
    write_csv(path, "timestamp,price\n2,1\n1,1\n")
    result = validate_tardis_csv(path, required={"timestamp", "price"})
    assert result["valid"] is False
    assert result["delivery_monotonic"] is False


def test_exchange_timestamp_reorder_is_recorded_but_delivery_order_remains_valid(tmp_path) -> None:
    path = tmp_path / "l2.csv.gz"
    write_csv(
        path,
        "timestamp,local_timestamp,price\n2,10,1\n1,11,1\n",
    )
    result = validate_tardis_csv(path, required={"timestamp", "local_timestamp", "price"})
    assert result["valid"] is True
    assert result["exchange_timestamp_reorders"] == 1


def test_tardis_validation_rejects_missing_columns(tmp_path) -> None:
    path = tmp_path / "l2.csv.gz"
    write_csv(path, "timestamp\n1\n")
    result = validate_tardis_csv(path, required={"timestamp", "price"})
    assert result["valid"] is False
    assert result["reason"] == "REQUIRED_COLUMNS_MISSING"
