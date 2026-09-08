"""Validate authorized independent L2 days; never execute economic strategy.

Reads one immutable manifest snapshot. Derived validation caches are separate
from source manifests and original market files. Run only after publication.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import tempfile
import zipfile
from collections import Counter
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from crypto_strategy_lab.microstructure.serial_replay import USDCUSDT_TICK_CATALOG
from crypto_strategy_lab.microstructure.tardis_l2 import (
    _local_microseconds,
    bind_csv_reconstructed_native,
    iter_csv_rows,
    native_exchange_microseconds,
    validate_csv_rows,
    validate_raw_lines,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("data/manifests/usdcusdt-tardis-free-l2.json")
TRADE_MANIFEST = Path("data/manifests/usdcusdt-trades-2025-2026.json")
TRADE_MANIFEST_SHA256 = "553550be53b657c9523bda59d905b1b987f7f86310db838ca0e47dd625a4359d"
OUTPUT = Path("reports/usdcusdt/L2-monthly-sample-validation.json")
AUTHORIZED_DATES = tuple(
    f"{year}-{month:02d}-01"
    for year in (2025, 2026)
    for month in range(1, 13 if year == 2025 else 10)
)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validator_identity(root: Path = ROOT) -> dict[str, str]:
    paths = (
        "scripts/validate_tardis_l2_samples.py",
        "src/crypto_strategy_lab/microstructure/tardis_l2.py",
        "src/crypto_strategy_lab/microstructure/serial_replay.py",
    )
    return {
        path: hashlib.sha256((root / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for path in paths
    }


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="validation-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def day_start_us(day: str) -> int:
    if day not in AUTHORIZED_DATES:
        raise ValueError("date outside OWNER monthly sample scope")
    delta = datetime.fromisoformat(day).replace(tzinfo=UTC) - EPOCH
    return delta.days * 86_400_000_000


def checked_path(root: Path, relative: str, day: str, *, raw: bool = False) -> Path:
    path = (root / relative).resolve()
    expected = (root / "data/l2/tardis/binance/usdcusdt" / day).resolve()
    if not path.is_relative_to(expected):
        raise ValueError("L2 source path escapes authorized day")
    if raw and path.parent != expected / "raw":
        raise ValueError("raw slice outside canonical raw directory")
    return path


def validate_slice_metadata(day: str, entry: dict[str, Any]) -> None:
    offset = entry["offset"]
    if type(offset) is not int or offset not in range(0, 1440, 10):
        raise ValueError("invalid raw slice offset")
    if entry.get("http_status") != 200 or entry.get("status") not in {
        "AVAILABLE",
        "ORIGINAL_PRESENT",
    }:
        raise ValueError("raw slice unavailable or HTTP failed")
    headers = {key.lower(): str(value) for key, value in entry["response_headers"].items()}
    if headers.get("x-slice-size") != "10":
        raise ValueError("native slice size is not verified ten minutes")
    url = urlparse(entry["source_url"])
    params = parse_qs(url.query)
    if (
        url.scheme != "https"
        or url.netloc != "api.tardis.dev"
        or url.path != "/v1/data-feeds/binance"
    ):
        raise ValueError("unexpected raw source")
    for key, value in (
        ("from", day),
        ("offset", str(offset)),
        ("sliceSize", "10"),
        ("compression", "gzip"),
    ):
        if params.get(key) != [value]:
            raise ValueError(f"wrong native source {key}")
    filters = json.loads(params["filters"][0])
    expected = {"depth", "depthSnapshot", "trade"}
    if len(filters) != 3 or {item["channel"] for item in filters} != expected:
        raise ValueError("unexpected native channel set")
    if any(item["symbols"] != ["usdcusdt"] for item in filters):
        raise ValueError("unexpected native symbol filter")
    expected_name = f"binance/{day.replace('-', '/')}/{offset // 60:02d}/{offset % 60:02d}"
    if headers.get("x-name") != expected_name:
        raise ValueError("native response slice identity mismatch")


def raw_lines(root: Path, day: str, slices: list[dict[str, Any]]) -> Iterator[str]:
    """Offset order is slice identity; each file's capture order is untouched."""
    start = day_start_us(day)
    for entry in sorted(slices, key=lambda item: item["offset"]):
        begin = start + entry["offset"] * 60_000_000
        with gzip.open(checked_path(root, entry["local_path"], day, raw=True), "rt") as stream:
            for line in stream:
                if line.strip():
                    local = _local_microseconds(line.split(" ", 1)[0])
                    if not begin <= local < begin + 600_000_000:
                        raise ValueError("native record outside its ten-minute capture slice")
                yield line


def trade_timestamp_matches(canonical_us: int, native_value: int) -> bool:
    native_exchange_microseconds(native_value)  # type/range guard
    return (
        canonical_us == native_value
        if native_value >= 100_000_000_000_000
        else canonical_us // 1000 == native_value
    )


def reconcile_trades(
    root: Path,
    day: str,
    archive: dict[str, Any],
    lines: Iterable[str],
) -> dict[str, Any]:
    """Match capture feed to pinned same-day official IDs; no adjacent archive reads."""
    path = (root / archive["local_path"]).resolve()
    expected = (
        root / "data/raw/binance-microstructure/USDCUSDT/trades" / f"USDCUSDT-trades-{day}.zip"
    ).resolve()
    if path != expected or archive.get("utc_date") != day:
        raise ValueError("canonical trade archive date/path mismatch")
    if archive.get("integrity_status") != "VALID" or archive.get("symbol") != "USDCUSDT":
        raise ValueError("canonical trade archive not valid USDCUSDT")
    if path.stat().st_size != archive["size_bytes"] or file_sha256(path) != archive["sha256"]:
        raise ValueError("canonical trade archive bytes/hash mismatch")
    counts: Counter[str] = Counter()
    canonical: dict[int, tuple[Decimal, Decimal, int, bool]] = {}
    start = day_start_us(day)
    previous_id = previous_time = None
    first_time = last_time = None
    with zipfile.ZipFile(path) as zipped:
        if len(zipped.namelist()) != 1:
            raise ValueError("unexpected canonical ZIP members")
        with zipped.open(zipped.namelist()[0]) as member:
            for row in csv.reader(io.TextIOWrapper(member, encoding="utf-8")):
                trade_id, price, quantity = int(row[0]), Decimal(row[1]), Decimal(row[2])
                moment, maker = int(row[4]), row[5]
                if maker not in {"True", "False", "true", "false"}:
                    raise ValueError("invalid canonical maker flag")
                if not start <= moment < start + 86_400_000_000:
                    raise ValueError("canonical trade timestamp outside day")
                if not price.is_finite() or not quantity.is_finite() or price <= 0 or quantity <= 0:
                    raise ValueError("invalid canonical price or quantity")
                if previous_id is not None and trade_id != previous_id + 1:
                    counts["canonical_id_discontinuities"] += 1
                if previous_time is not None and moment < previous_time:
                    counts["canonical_time_regressions"] += 1
                if not USDCUSDT_TICK_CATALOG.is_price_compatible(
                    EPOCH + timedelta(microseconds=moment), price
                ):
                    counts["canonical_off_grid"] += 1
                if trade_id in canonical:
                    counts["canonical_duplicate_ids"] += 1
                canonical[trade_id] = (price, quantity, moment, maker.lower() == "true")
                previous_id, previous_time = trade_id, moment
                if first_time is None:
                    first_time = moment
                last_time = moment
    counts["canonical_trades"] = len(canonical)
    if len(canonical) != archive["record_count"]:
        raise ValueError("canonical record count mismatch")
    if canonical and (
        min(canonical) != archive["first_trade_id"] or max(canonical) != archive["last_trade_id"]
    ):
        raise ValueError("canonical first/last ID mismatch")
    matched: set[int] = set()
    native_ids: set[int] = set()
    previous_native_time = previous_native_id = None
    for line in lines:
        if not line.strip():
            continue
        _, encoded = line.split(" ", 1)
        payload = json.loads(encoded)
        event = payload["data"]
        if event.get("e") != "trade":
            continue
        counts["native_trades"] += 1
        trade_id, native_time = event["t"], event["T"]
        if type(trade_id) is not int or type(event["m"]) is not bool:
            raise ValueError("invalid native trade fields")
        timestamp = native_exchange_microseconds(native_time)
        counts[
            "native_microsecond_timestamps"
            if native_time >= 100_000_000_000_000
            else "native_millisecond_timestamps"
        ] += 1
        if trade_id in native_ids:
            counts["native_duplicate_ids"] += 1
        native_ids.add(trade_id)
        if previous_native_time is not None and timestamp < previous_native_time:
            counts["native_trade_time_regressions"] += 1
        if previous_native_id is not None and trade_id < previous_native_id:
            counts["native_trade_id_regressions"] += 1
        previous_native_time, previous_native_id = timestamp, trade_id
        source = canonical.get(trade_id)
        if source is None:
            counts[
                "native_outside_exchange_day"
                if not start <= timestamp < start + 86_400_000_000
                else "native_unknown_interior_ids"
            ] += 1
            continue
        price, quantity, moment, source_maker = source
        if (
            Decimal(event["p"]) != price
            or Decimal(event["q"]) != quantity
            or event["m"] != source_maker
            or not trade_timestamp_matches(moment, native_time)
        ):
            counts["trade_field_mismatches"] += 1
            continue
        matched.add(trade_id)
    counts["matched_trades"] = len(matched)
    if matched:
        low, high = min(matched), max(matched)
        for trade_id in canonical.keys() - matched:
            counts[
                "missing_prefix"
                if trade_id < low
                else "missing_suffix"
                if trade_id > high
                else "missing_interior"
            ] += 1
    else:
        counts["missing_unclassified"] = len(canonical)
    invalid = any(
        counts[key]
        for key in (
            "canonical_id_discontinuities",
            "canonical_time_regressions",
            "canonical_off_grid",
            "canonical_duplicate_ids",
            "native_duplicate_ids",
            "native_trade_time_regressions",
            "native_trade_id_regressions",
            "native_unknown_interior_ids",
            "trade_field_mismatches",
            "missing_interior",
            "missing_unclassified",
        )
    )
    # Edge losses are reported separately; caller must compare startup/suffix
    # availability to activation coverage before claiming an executable day.
    gate = (
        "FAIL"
        if invalid
        else "UNKNOWN"
        if counts["missing_prefix"] or counts["missing_suffix"]
        else "PASS"
    )
    return {
        "trade_binding_gate": gate,
        "counts": dict(counts),
        "canonical_archive_sha256": archive["sha256"],
        "first_canonical_timestamp": first_time,
        "last_canonical_timestamp": last_time,
        "timestamp_comparison": "EXACT_AT_NATIVE_REPORTED_PRECISION",
        "first_matched_id": min(matched) if matched else None,
        "last_matched_id": max(matched) if matched else None,
    }


def validate_day(
    entry: dict[str, Any],
    trade_manifest: dict[str, Any],
    *,
    root: Path = ROOT,
    csv_only: bool = False,
    use_cache: bool = True,
) -> dict[str, Any]:
    day = entry["date"]
    day_start_us(day)
    result: dict[str, Any] = {"date": day, "L2_DAY_VALID": None, "errors": []}
    if entry.get("status") not in {"AVAILABLE", "ORIGINAL_PRESENT"}:
        return {**result, "status": "UNAVAILABLE"}
    try:
        expected_url = (
            "https://datasets.tardis.dev/v1/binance/incremental_book_L2/"
            f"{day.replace('-', '/')}/USDCUSDT.csv.gz"
        )
        if entry.get("source_url") != expected_url or entry.get("http_status") != 200:
            raise ValueError("CSV source URL or HTTP status mismatch")
        csv_path = checked_path(root, entry["local_path"], day)
        if csv_path.stat().st_size != entry["bytes"] or file_sha256(csv_path) != entry["sha256"]:
            raise ValueError("CSV source bytes/hash mismatch")
        slices = entry.get("raw_slices", [])
        identities = []
        archive_sha = None
        if not csv_only:
            archives = [item for item in trade_manifest["archives"] if item["utc_date"] == day]
            if len(archives) != 1:
                raise ValueError("canonical same-day trade archive is not unique")
            archive = archives[0]
            trade_path = (root / archive["local_path"]).resolve()
            expected_trade_path = (
                root
                / "data/raw/binance-microstructure/USDCUSDT/trades"
                / f"USDCUSDT-trades-{day}.zip"
            ).resolve()
            if trade_path != expected_trade_path:
                raise ValueError("canonical trade archive path mismatch")
            archive_sha = file_sha256(trade_path)
            if (
                trade_path.stat().st_size != archive["size_bytes"]
                or archive_sha != archive["sha256"]
            ):
                raise ValueError("canonical archive changed before validation/cache lookup")
            for source in slices:
                validate_slice_metadata(day, source)
                path = checked_path(root, source["local_path"], day, raw=True)
                if path.stat().st_size != source["bytes"] or file_sha256(path) != source["sha256"]:
                    raise ValueError("native source bytes/hash mismatch")
                identities.append({"offset": source["offset"], "sha256": source["sha256"]})
        source_binding = {
            "csv_sha256": entry["sha256"],
            "raw_slices": sorted(identities, key=lambda item: item["offset"]),
            "validator_lf_sha256": validator_identity(root),
            "canonical_trade_manifest_sha256": TRADE_MANIFEST_SHA256,
            "canonical_archive_sha256": archive_sha,
            "csv_only": csv_only,
            "date": day,
        }
        cache_key = hashlib.sha256(json.dumps(source_binding, sort_keys=True).encode()).hexdigest()
        cache_path = csv_path.parent / ("validation-csv.json" if csv_only else "validation.json")
        if use_cache and cache_path.exists():
            cached: dict[str, Any] = json.loads(cache_path.read_text())
            if cached.get("cache_key") == cache_key:
                return cached
        result.update(
            input_binding=source_binding,
            input_sha256=cache_key,
            cache_key=cache_key,
        )
        grid: Counter[str] = Counter()
        start = day_start_us(day)

        def checked_csv() -> Iterator[dict[str, str]]:
            for row in iter_csv_rows(csv_path):
                local, exchange = int(row["local_timestamp"]), int(row["timestamp"])
                if not start <= local < start + 86_400_000_000:
                    grid["capture_outside_day"] += 1
                if not start <= exchange < start + 86_400_000_000:
                    grid["exchange_outside_day"] += 1
                if not USDCUSDT_TICK_CATALOG.is_price_compatible(
                    EPOCH + timedelta(microseconds=exchange), Decimal(row["price"])
                ):
                    grid["off_grid"] += 1
                yield row

        csv_result = validate_csv_rows(checked_csv())
        csv_result.pop("final_book", None)
        if csv_result["counts"].get("rows") != entry["rows"]:
            raise ValueError("CSV parsed row count differs from acquisition manifest")
        for observed, expected in (
            ("first_local_timestamp", "first_timestamp"),
            ("last_local_timestamp", "last_timestamp"),
        ):
            if csv_result[observed] != int(entry[expected]):
                raise ValueError("CSV capture endpoints differ from acquisition manifest")
        result.update(
            csv=csv_result,
            CSV_ROWS=csv_result["counts"].get("rows", 0),
            grid={"counts": dict(grid), "catalog_sha256": USDCUSDT_TICK_CATALOG.catalog_hash},
        )
        if (
            not csv_result["observable_invariants_pass"]
            or grid["off_grid"]
            or grid["capture_outside_day"]
        ):
            result["L2_DAY_VALID"] = False
        if csv_only:
            result["status"] = "CSV_ONLY_NO_EXECUTION_GATE"
        elif len(slices) != 144 or {item["offset"] for item in slices} != set(range(0, 1440, 10)):
            result["status"] = "RAW_COVERAGE_INCOMPLETE"
            result["raw_slices_available"] = len(slices)
        else:
            raw_result = validate_raw_lines(raw_lines(root, day, slices))
            raw_result.pop("final_book", None)
            result["raw"] = raw_result
            result["coverage"] = {
                "gate": "PASS",
                "verified_ten_minute_slices": 144,
                "initial_unavailable_microseconds": csv_result["first_local_timestamp"] - start,
                "startup_policy": "FLAT_NO_ORDERS_BEFORE_BRIDGED_SNAPSHOT",
                "quiet_intervals_are_not_inferred_gaps": True,
            }
            result["binding"] = bind_csv_reconstructed_native(
                iter_csv_rows(csv_path), raw_lines(root, day, slices)
            )
            result["trades"] = reconcile_trades(
                root, day, archives[0], raw_lines(root, day, slices)
            )
            result["TRADES"] = result["trades"]["counts"].get("canonical_trades", 0)
            gates = (
                raw_result["sequence_gate"],
                result["binding"]["normalized_binding_gate"],
                result["trades"]["trade_binding_gate"],
            )
            if "FAIL" in gates or raw_result["L2_DAY_VALID"] is False:
                result["L2_DAY_VALID"] = False
            elif all(gate == "PASS" for gate in gates) and result["L2_DAY_VALID"] is not False:
                result["L2_DAY_VALID"] = True
            result["status"] = (
                "VALIDATED" if result["L2_DAY_VALID"] is True else "BLOCKED_BY_DATA_GATES"
            )
        atomic_json(cache_path, result)
    except (
        OSError,
        EOFError,
        ArithmeticError,
        ValueError,
        KeyError,
        TypeError,
        zipfile.BadZipFile,
    ) as exc:
        result["L2_DAY_VALID"] = False
        result["status"] = "VALIDATION_ERROR"
        result["errors"].append(str(exc))
    return result


def validate_work(task: tuple[dict[str, Any], dict[str, Any], bool, bool]) -> dict[str, Any]:
    """Picklable CPU worker; identical validation authority in serial and parallel."""
    entry, trade_manifest, csv_only, use_cache = task
    result = validate_day(entry, trade_manifest, csv_only=csv_only, use_cache=use_cache)
    print(
        json.dumps(
            {
                "date": entry["date"],
                "status": result["status"],
                "L2_DAY_VALID": result["L2_DAY_VALID"],
            }
        ),
        flush=True,
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-only", action="store_true")
    parser.add_argument("--dates", nargs="+", choices=AUTHORIZED_DATES)
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    manifest_bytes = (ROOT / MANIFEST).read_bytes()
    manifest = json.loads(manifest_bytes)
    trade_bytes = (ROOT / TRADE_MANIFEST).read_bytes()
    if hashlib.sha256(trade_bytes).hexdigest() != TRADE_MANIFEST_SHA256:
        raise ValueError("canonical trade manifest differs from OWNER-pinned source")
    if manifest["canonical_trade_manifest_sha256"] != TRADE_MANIFEST_SHA256:
        raise ValueError("L2 manifest binds another canonical trade source")
    trade_manifest = json.loads(trade_bytes)
    selected = set(args.dates or AUTHORIZED_DATES)
    entries = [entry for entry in manifest["dates"] if entry["date"] in selected]
    if len(entries) != len(selected) or len({item["date"] for item in entries}) != len(selected):
        raise ValueError("manifest lacks unique authorized selected days")

    tasks = [(entry, trade_manifest, args.csv_only, not args.no_cache) for entry in entries]
    if args.workers == 1:
        days = [validate_work(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            days = list(executor.map(validate_work, tasks))
    output = {
        "schema": "usdcusdt-l2-monthly-validation-v1",
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "CSV_ONLY" if args.csv_only else "ALL_DATA_GATES",
        "days": sorted(days, key=lambda item: item["date"]),
    }
    atomic_json(ROOT / OUTPUT, output)


if __name__ == "__main__":
    main()
