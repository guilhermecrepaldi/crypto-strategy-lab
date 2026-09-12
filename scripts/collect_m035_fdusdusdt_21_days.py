"""Acquire the frozen 21-day FDUSDUSDT evidence set for M035.

L2 originals come from Tardis' Binance ``incremental_book_L2`` archive.
Individual trades come from Binance Vision and retain Binance's adjacent checksum.
This module performs acquisition and validation only; it cannot run a replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from collect_tardis_l2_samples import _download_one, source_url, validate_gzip

from crypto_strategy_lab.microstructure.data import download_archive, manifest_from_archive

SYMBOL = "FDUSDUSDT"
IDENTITY = "M035_FDUSDUSDT_21_DAY_EVIDENCE_V1"
DATES = tuple(
    date(year, month, 1)
    for year, months in ((2025, range(1, 13)), (2026, range(1, 10)))
    for month in months
)
L2_ROOT = Path("data/l2/tardis/binance/fdusdusdt")
TRADES_ROOT = Path("data/raw/binance-microstructure/FDUSDUSDT/trades")
MANIFEST = Path("reports/m035/M035_FDUSDUSDT_21_DAY_DATA_REPORT.json")
BINANCE_TRADES_BASE = "https://data.binance.vision/data/spot/daily/trades"


def trade_url(day: date) -> str:
    filename = f"{SYMBOL}-trades-{day.isoformat()}.zip"
    return f"{BINANCE_TRADES_BASE}/{SYMBOL}/{filename}"


def _paths(day: date) -> tuple[Path, Path]:
    l2 = L2_ROOT / day.isoformat() / "incremental_book_L2.csv.gz"
    trades = TRADES_ROOT / day.isoformat() / f"{SYMBOL}-trades-{day.isoformat()}.zip"
    return l2, trades


def _validate_trade_binding(path: Path, day: date) -> None:
    checksum_path = path.with_name(path.name + ".CHECKSUM")
    if not checksum_path.exists():
        raise ValueError("OFFICIAL_CHECKSUM_SIDECAR_REQUIRED")
    match = re.search(r"\b([0-9a-f]{64})\b", checksum_path.read_text(encoding="ascii"), re.I)
    if match is None:
        raise ValueError("INVALID_OFFICIAL_CHECKSUM_SIDECAR")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != match.group(1).lower():
        raise ValueError("OFFICIAL_CHECKSUM_BINDING_MISMATCH")
    expected_member = f"{SYMBOL}-trades-{day.isoformat()}.csv"
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if not name.endswith("/")]
    if members != [expected_member]:
        raise ValueError("OFFICIAL_ARCHIVE_MEMBER_BINDING_MISMATCH")


def _one_day(
    day: date,
    *,
    download: bool,
    timeout: float,
    prior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    l2_path, trades_path = _paths(day)
    result: dict[str, Any] = {"date": day.isoformat()}
    try:
        if l2_path.exists():
            prior_l2 = (prior or {}).get("l2", {})
            expected_url = source_url(day, SYMBOL)
            if (
                prior_l2.get("status") != "AVAILABLE"
                or prior_l2.get("source_url") != expected_url
                or prior_l2.get("local_path") != l2_path.as_posix()
                or not prior_l2.get("sha256")
            ):
                raise ValueError("L2_ORPHAN_OR_UNBOUND_ORIGINAL")
            checked = validate_gzip(l2_path, day, SYMBOL)
            if checked["sha256"] != prior_l2["sha256"]:
                raise ValueError("L2_MANIFEST_HASH_MISMATCH")
            l2 = {**prior_l2, **checked, "status": "AVAILABLE", "reused": True}
        elif download:
            l2 = _download_one(day, L2_ROOT, timeout, SYMBOL)
        else:
            l2 = {"status": "UNAVAILABLE", "source_url": source_url(day, SYMBOL)}
    except Exception as exc:  # preserve every per-source failure in the manifest
        l2 = {"status": "INVALID", "source_url": source_url(day, SYMBOL), "error": str(exc)}
    result["l2"] = l2

    try:
        url = trade_url(day)
        if not trades_path.exists() and not download:
            trades: dict[str, Any] = {"status": "UNAVAILABLE", "source_url": url}
        else:
            if download:
                download_archive(url, trades_path)
            _validate_trade_binding(trades_path, day)
            manifest = manifest_from_archive(
                trades_path,
                origin=url,
                period=day.isoformat(),
                symbol=SYMBOL,
                kind="trades",
            )
            trades = {
                "status": "AVAILABLE" if manifest.integrity_status == "VALID" else "INVALID",
                "source_url": url,
                **manifest.model_dump(mode="json"),
            }
    except Exception as exc:  # preserve every per-source failure in the manifest
        trades = {"status": "INVALID", "source_url": trade_url(day), "error": str(exc)}
    result["individual_trades"] = trades
    result["day_status"] = (
        "AVAILABLE"
        if l2.get("status") == "AVAILABLE" and trades.get("status") == "AVAILABLE"
        else "INVALID_OR_UNAVAILABLE"
    )
    return result


def build_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(results, key=lambda item: item["date"])
    available = sum(item["day_status"] == "AVAILABLE" for item in ordered)
    return {
        "schema_version": "m035-fdusdusdt-21-day-evidence-v1",
        "identity": IDENTITY,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "symbol": SYMBOL,
        "venue": "BINANCE_SPOT",
        "requested_days": len(DATES),
        "available_days": available,
        "all_21_available": available == len(DATES),
        "selection_policy": {
            "days": "FROZEN_FIRST_DAY_OF_EACH_MONTH_2025_01_THROUGH_2026_09",
            "three_hour_window": "NOT_SELECTED; MUST_BE_RANDOMLY_DRAWN_AND_PREREGISTERED_LATER",
            "pnl_based_selection": False,
        },
        "provenance": {
            "mode": "MIXED_EXPLICIT",
            "l2": "TARDIS_INCREMENTAL_BOOK_L2_ARCHIVE_OF_BINANCE_SPOT",
            "individual_trades": "BINANCE_VISION_OFFICIAL_SPOT_TRADES_ARCHIVE",
            "candles_as_fills": False,
            "aggtrades_as_individual_trades": False,
            "silent_source_mixing": False,
        },
        "scope": "DATA_ACQUISITION_AND_VALIDATION_ONLY_NO_REPLAY",
        "limitations": [
            "Tardis normalized incremental_book_L2 does not itself prove native Binance "
            "U/u sequence continuity.",
            "A later replay gate must align L2 and individual-trade coverage before drawing "
            "the 3-hour window.",
        ],
        "days": ordered,
    }


def merge_checkpoint(
    preserved: dict[str, dict[str, Any]], completed: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Return a monotonic checkpoint without dropping not-yet-revalidated provenance."""
    return {**preserved, str(completed["date"]): completed}


def write_report(report: dict[str, Any]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(MANIFEST)


def collect(
    *, download: bool = True, concurrency: int = 3, timeout: float = 120.0
) -> dict[str, Any]:
    if concurrency < 1 or concurrency > 3:
        raise ValueError("concurrency must be between 1 and 3")
    prior_by_date: dict[str, dict[str, Any]] = {}
    if MANIFEST.exists():
        prior_report = json.loads(MANIFEST.read_text(encoding="utf-8"))
        if prior_report.get("identity") != IDENTITY or prior_report.get("symbol") != SYMBOL:
            raise ValueError("EXISTING_MANIFEST_IDENTITY_MISMATCH")
        prior_by_date = {item["date"]: item for item in prior_report.get("days", [])}
    results_by_date = {
        key: {**item, "verified_in_current_run": False}
        for key, item in prior_by_date.items()
    }
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(
                _one_day,
                day,
                download=download,
                timeout=timeout,
                prior=prior_by_date.get(day.isoformat()),
            ): day
            for day in DATES
        }
        for future in as_completed(futures):
            completed = future.result()
            completed["verified_in_current_run"] = True
            results_by_date = merge_checkpoint(results_by_date, completed)
            write_report(build_report(list(results_by_date.values())))
    report = build_report(list(results_by_date.values()))
    write_report(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="validate local originals only")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    report = collect(
        download=not args.offline,
        concurrency=args.concurrency,
        timeout=args.timeout,
    )
    print(
        json.dumps({key: report[key] for key in ("identity", "available_days", "all_21_available")})
    )
    if not report["all_21_available"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
