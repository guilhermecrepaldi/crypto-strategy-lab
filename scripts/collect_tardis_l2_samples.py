"""Acquire and validate the public first-of-month Tardis L2 samples.

This module deliberately contains no replay or execution logic.  Downloads are
streamed to unique ``.part`` files and originals are never replaced.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import subprocess
import tempfile
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

EXPECTED_SCHEMA = [
    "exchange",
    "symbol",
    "timestamp",
    "local_timestamp",
    "is_snapshot",
    "side",
    "price",
    "amount",
]
BASE_URL = "https://datasets.tardis.dev/v1/binance/incremental_book_L2"
START = date(2025, 1, 1)
END = date(2026, 9, 5)
AUDITED_MANIFEST = Path("data/manifests/usdcusdt-trades-2025-2026.json")
AUDITED_SHA = "553550be53b657c9523bda59d905b1b987f7f86310db838ca0e47dd625a4359d"
MANIFEST = Path("data/manifests/usdcusdt-tardis-free-l2.json")
ROOT = Path("data/l2/tardis/binance/usdcusdt")
RAW_ROOT = ROOT / "raw"
RAW_API = "https://api.tardis.dev/v1/data-feeds/binance"
RAW_CHANNELS = ("depth", "depthSnapshot", "trade")


def candidate_dates(audited_manifest: Path = AUDITED_MANIFEST) -> list[date]:
    """Return exactly the audited first day of each month in the allowed horizon."""
    original = audited_manifest.read_bytes()
    if hashlib.sha256(original).hexdigest() != AUDITED_SHA:
        raise ValueError("CANONICAL_MANIFEST_HASH_MISMATCH")
    payload = json.loads(original)
    if payload.get("symbol") != "USDCUSDT" or payload.get("integrity_status") != "VALID":
        raise ValueError("audited USDCUSDT trades manifest is not VALID")
    result: list[date] = []
    cursor = date(2025, 1, 1)
    while cursor <= date(2026, 9, 1):
        if cursor.isoformat() >= payload.get(
            "requested_start", "0000-00-00"
        ) and cursor.isoformat() <= payload.get("requested_end", "9999-99-99"):
            result.append(cursor)
        cursor = date(
            cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1
        )
    available = {
        item["utc_date"] for item in payload["archives"] if item["integrity_status"] == "VALID"
    }
    if len(result) != 21 or any(day.isoformat() not in available for day in result):
        raise ValueError("EXACT_21_AUDITED_CANDIDATES_REQUIRED")
    return result


def source_url(day: date, symbol: str = "USDCUSDT") -> str:
    return f"{BASE_URL}/{day:%Y/%m/%d}/{symbol.upper()}.csv.gz"


def _timestamp(value: str) -> datetime:
    text = value.strip()
    try:
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            number = int(text)
            if number < 10**14:
                raise ValueError("microsecond timestamp required")
            return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=number)
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except (ValueError, OverflowError, OSError) as exc:
        raise ValueError(f"invalid timestamp: {value!r}") from exc


def validate_gzip(
    path: Path, expected_date: date, expected_symbol: str = "USDCUSDT"
) -> dict[str, object]:
    """Read all compressed bytes (thereby checking CRC/trailer) and validate rows."""
    digest = hashlib.sha256()
    rows = 0
    first: str | None = None
    last: str | None = None
    exchange_first = exchange_last = None
    previous_local = None
    regressions = exchange_outside = 0
    with path.open("rb") as raw:
        for chunk in iter(lambda: raw.read(1024 * 1024), b""):
            digest.update(chunk)
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != EXPECTED_SCHEMA:
                raise ValueError(f"schema mismatch: {reader.fieldnames!r}")
            for row in reader:
                if set(row) != set(EXPECTED_SCHEMA) or any(value is None for value in row.values()):
                    raise ValueError("malformed CSV row")
                if (
                    row["exchange"].strip().lower() != "binance"
                    or row["symbol"].strip().upper() != expected_symbol.upper()
                ):
                    raise ValueError("unexpected exchange or symbol")
                if row["side"].strip().lower() not in {"bid", "ask"}:
                    raise ValueError("side must be bid or ask")
                price, amount = Decimal(row["price"]), Decimal(row["amount"])
                if not price.is_finite() or price <= 0:
                    raise ValueError("price must be finite and positive")
                if not amount.is_finite() or amount < 0:
                    raise ValueError("amount must be finite and non-negative")
                if row["is_snapshot"].strip().lower() not in {"true", "false", "0", "1"}:
                    raise ValueError("is_snapshot must be boolean")
                timestamp = _timestamp(row["timestamp"])
                local_timestamp = _timestamp(row["local_timestamp"])
                if local_timestamp.date() != expected_date:
                    raise ValueError("row is outside candidate capture day scope")
                exchange_outside += timestamp.date() != expected_date
                regressions += previous_local is not None and local_timestamp < previous_local
                previous_local = local_timestamp
                exchange_first = exchange_first or row["timestamp"]
                exchange_last = row["timestamp"]
                stamp = row["local_timestamp"].strip()
                first = first or stamp
                last = stamp
                rows += 1
    except (OSError, EOFError, gzip.BadGzipFile, csv.Error, ValueError):
        raise
    return {
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "rows": rows,
        "first_timestamp": first,
        "last_timestamp": last,
        "first_exchange_timestamp": exchange_first,
        "last_exchange_timestamp": exchange_last,
        "capture_time_regressions": regressions,
        "exchange_rows_outside_capture_day": exchange_outside,
        "capture_order": "PRESERVED_NOT_SORTED",
        "gzip_integrity": "PASS",
        "schema": EXPECTED_SCHEMA,
        "l2_day_valid": False,
    }


def _download_one(
    day: date, root: Path, timeout: float, symbol: str = "USDCUSDT"
) -> dict[str, object]:
    url = source_url(day, symbol)
    destination = root / day.isoformat() / "incremental_book_L2.csv.gz"
    destination.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if destination.exists():
        raise FileExistsError(f"orphan original exists; refusing overwrite: {destination}")
    part = destination.with_name(
        f"{destination.name}.{os.getpid()}.{next(tempfile._get_candidate_names())}.part"
    )
    status: dict[str, object] = {
        "date": day.isoformat(),
        "source_url": url,
        "download_timestamp": now,
        "status": "UNAVAILABLE",
        "local_path": destination.as_posix(),
    }
    try:
        request = Request(url, headers={"User-Agent": "crypto-strategy-lab/tardis-l2"})
        with urlopen(request, timeout=timeout) as response, part.open("wb") as output:
            status["http_status"] = response.status
            status["content_length"] = response.headers.get("Content-Length")
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                output.write(chunk)
        status["bytes"] = part.stat().st_size
        with part.open("rb") as original:
            status["sha256"] = hashlib.file_digest(original, "sha256").hexdigest()
        if (
            status["content_length"] is not None
            and int(status["content_length"]) != status["bytes"]
        ):
            raise ValueError("HTTP_CONTENT_LENGTH_MISMATCH")
        # Windows rename fails if the final original appeared meanwhile; never replace.
        part.rename(destination)
        checked = validate_gzip(destination, day, symbol)
        status.update(checked, status="AVAILABLE")
    except HTTPError as exc:
        status.update(http_status=exc.code, error=str(exc))
    except (URLError, TimeoutError, OSError, ValueError, EOFError, gzip.BadGzipFile) as exc:
        status.update(status="INVALID", error=str(exc))
    finally:
        if part.exists() and status.get("status") == "AVAILABLE":
            part.unlink()
    return status


def collect(
    *,
    dates: Iterable[date] | None = None,
    root: Path = ROOT,
    manifest_path: Path = MANIFEST,
    timeout: float = 30.0,
    concurrency: int = 3,
    download: bool = True,
) -> dict[str, object]:
    authorized = candidate_dates()
    days = list(authorized if dates is None else dates)
    if not days or len(set(days)) != len(days) or any(day not in authorized for day in days):
        raise ValueError("ONLY_AUTHORIZED_MONTHLY_CANDIDATES_ALLOWED")
    if concurrency < 1 or concurrency > 3:
        raise ValueError("concurrency must be between 1 and 3")
    prior: dict[str, dict[str, object]] = {}
    if manifest_path.exists():
        prior = {
            str(item["date"]): item
            for item in json.loads(manifest_path.read_text(encoding="utf-8")).get("dates", [])
        }
    results: dict[str, dict[str, object]] = {}
    for day in days:
        key = day.isoformat()
        path = root / key / "incremental_book_L2.csv.gz"
        if path.exists() and key in prior and prior[key].get("sha256"):
            try:
                checked = validate_gzip(path, day)
                if checked["sha256"] != prior[key]["sha256"]:
                    raise ValueError("existing original hash differs from manifest")
                results[key] = {**prior[key], **checked, "status": "AVAILABLE", "reused": True}
                continue
            except (OSError, ValueError, EOFError, gzip.BadGzipFile) as exc:
                results[key] = {
                    "date": key,
                    "source_url": source_url(day),
                    "status": "INVALID",
                    "error": str(exc),
                    "local_path": path.as_posix(),
                }
                continue
        if path.exists():
            results[key] = {
                "date": key,
                "source_url": source_url(day),
                "status": "INVALID",
                "error": "orphan original has unknown provenance; refusing overwrite",
                "local_path": path.as_posix(),
            }
    pending = [day for day in days if day.isoformat() not in results]
    if not download:
        for day in pending:
            key = day.isoformat()
            results[key] = {
                "date": key,
                "source_url": source_url(day),
                "status": "UNAVAILABLE",
                "error": "offline inspection: original not present",
            }
        _write_manifest(manifest_path, results, days)
        return {
            "schema_version": "tardis-free-l2-v1",
            "symbol": "USDCUSDT",
            "source": "Tardis",
            "dates": [results[d.isoformat()] for d in days],
        }
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_download_one, day, root, timeout): day for day in pending}
        for future in as_completed(futures):
            item = future.result()
            results[str(item["date"])] = item
            _write_manifest(manifest_path, results, days)
    _write_manifest(manifest_path, results, days)
    return {
        "schema_version": "tardis-free-l2-v1",
        "symbol": "USDCUSDT",
        "source": "Tardis",
        "canonical_trade_manifest_sha256": AUDITED_SHA,
        "dates": [results[d.isoformat()] for d in days],
    }


def _write_manifest(path: Path, results: dict[str, dict[str, object]], days: list[date]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "tardis-free-l2-v1",
        "symbol": "USDCUSDT",
        "source": "Tardis",
        "canonical_trade_manifest_sha256": AUDITED_SHA,
        "dates": [results[d.isoformat()] for d in days if d.isoformat() in results],
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _raw_url(day: date, offset: int) -> str:
    filters = json.dumps(
        [{"channel": channel, "symbols": ["usdcusdt"]} for channel in RAW_CHANNELS],
        separators=(",", ":"),
    )
    query = urlencode(
        {
            "from": day.isoformat(),
            "offset": offset,
            "sliceSize": 10,
            "compression": "gzip",
            "filters": filters,
        },
        quote_via=quote,
    )
    return f"{RAW_API}?{query}"


def _retry_delay(response: object, attempt: int) -> float:
    headers = getattr(response, "headers", {})
    try:
        value = min(float(headers.get("Retry-After", "0")), 60.0)
    except (TypeError, ValueError):
        value = 0.0
    return value if value else min(2.0**attempt, 60.0)


def _raw_slice(
    day: date,
    offset: int,
    root: Path,
    timeout: float,
    prior: dict[str, object] | None = None,
    revalidate_orphans: bool = False,
) -> dict[str, object]:
    if not START <= day <= END or day.day != 1:
        raise ValueError("ONLY_AUTHORIZED_MONTHLY_CANDIDATES_ALLOWED")
    if offset < 0 or offset >= 1440 or offset % 10:
        raise ValueError("RAW_OFFSET_MUST_BE_0_TO_1430_STEP_10")
    url = _raw_url(day, offset)
    directory = root / day.isoformat() / "raw"
    directory.mkdir(parents=True, exist_ok=True)
    stem = directory / f"{offset:04d}.ndjson"
    existing = next(
        (candidate for candidate in (stem.with_suffix(".ndjson.gz"), stem) if candidate.exists()),
        None,
    )
    if existing is not None:
        with existing.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        sidecar = existing.with_name(existing.name + ".meta.json")
        metadata = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
        trusted = next(
            (
                record
                for record in (prior, metadata)
                if record
                and record.get("sha256") == digest
                and record.get("status") in {"AVAILABLE", "ORIGINAL_PRESENT"}
                and record.get("source_url") == url
                and record.get("offset") == offset
                and record.get("http_status") == 200
                and str(
                    {str(k).lower(): v for k, v in record.get("response_headers", {}).items()}.get(
                        "x-slice-size"
                    )
                )
                == "10"
            ),
            None,
        )
        if trusted is None:
            if revalidate_orphans:
                request = Request(
                    url,
                    headers={
                        "Accept-Encoding": "gzip",
                        "User-Agent": "crypto-strategy-lab/tardis-l2",
                    },
                )
                try:
                    with urlopen(request, timeout=timeout) as response:
                        remote = response.read()
                        headers = {str(k).lower(): v for k, v in response.headers.items()}
                        valid_headers = (
                            response.status == 200
                            and str(headers.get("x-slice-size")) == "10"
                            and (headers.get("content-length") in {None, str(len(remote))})
                        )
                        verified = valid_headers and hashlib.sha256(remote).hexdigest() == digest
                        verification_path = existing.with_name(
                            existing.name + ".verification." + hashlib.sha256(remote).hexdigest()
                        )
                        if not verified and not verification_path.exists():
                            with verification_path.open("xb") as evidence:
                                evidence.write(remote)
                        result = {
                            "offset": offset,
                            "source_url": url,
                            "status": "AVAILABLE" if verified else "INVALID",
                            "local_path": existing.as_posix(),
                            "bytes": existing.stat().st_size,
                            "sha256": digest,
                            "recovered_original": verified,
                            "download_timestamp": None,
                            "original_download_timestamp_status": "UNKNOWN_AFTER_MANIFEST_FAILURE",
                            "coverage": f"slice_offset_{offset}_10_minutes",
                            "verification_timestamp": datetime.now(UTC)
                            .isoformat()
                            .replace("+00:00", "Z"),
                            "http_status": response.status,
                            "response_headers": dict(response.headers.items()),
                            "verification_path": (
                                verification_path.as_posix() if not verified else None
                            ),
                        }
                        if not verified:
                            result["error"] = "ORPHAN_PUBLIC_BYTES_MISMATCH"
                        else:
                            if existing.suffix == ".gz":
                                with gzip.open(existing, "rb") as stream:
                                    while stream.read(1024 * 1024):
                                        pass
                                result["gzip_integrity"] = "PASS"
                            _write_raw_sidecar(existing, result)
                        return result
                except (HTTPError, URLError, OSError, TimeoutError, EOFError) as exc:
                    return {
                        "offset": offset,
                        "source_url": url,
                        "status": "INVALID",
                        "error": str(exc),
                        "local_path": existing.as_posix(),
                        "sha256": digest,
                    }
            return {
                "offset": offset,
                "source_url": url,
                "status": "INVALID",
                "error": "ORPHAN_OR_HASH_MISMATCH",
                "local_path": existing.as_posix(),
                "bytes": existing.stat().st_size,
                "sha256": digest,
            }
        if existing.suffix == ".gz":
            try:
                with gzip.open(existing, "rb") as stream:
                    while stream.read(1024 * 1024):
                        pass
            except (OSError, EOFError, gzip.BadGzipFile) as exc:
                return {**trusted, "status": "INVALID", "error": str(exc)}
        return {
            **trusted,
            "status": "ORIGINAL_PRESENT",
            "local_path": existing.as_posix(),
            "bytes": existing.stat().st_size,
            "sha256": digest,
        }
    part = directory / f"{offset:04d}.{os.getpid()}.{next(tempfile._get_candidate_names())}.part"
    item: dict[str, object] = {
        "offset": offset,
        "source_url": url,
        "download_timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "UNAVAILABLE",
    }
    try:
        for attempt in range(3):
            try:
                request = Request(
                    url,
                    headers={
                        "Accept-Encoding": "gzip",
                        "User-Agent": "crypto-strategy-lab/tardis-l2",
                    },
                )
                with urlopen(request, timeout=timeout) as response:
                    status = int(response.status)
                    item["http_status"] = status
                    item["response_headers"] = dict(response.headers.items())
                    if status in {401, 403}:
                        item["error"] = "authentication required; no bypass"
                        return item
                    if status != 200 and (status == 429 or status >= 500):
                        if attempt < 2:
                            time.sleep(_retry_delay(response, attempt))
                            continue
                        item["error"] = f"retryable HTTP status {status}"
                        return item
                    if status != 200:
                        item["status"] = "INVALID"
                        item["error"] = f"unexpected HTTP status {status}"
                        return item
                    payload = response.read()
                    break
            except HTTPError as exc:
                item.update(http_status=exc.code, response_headers=dict(exc.headers.items()))
                if exc.code in {401, 403}:
                    item["error"] = "authentication required; no bypass"
                    return item
                if (exc.code == 429 or exc.code >= 500) and attempt < 2:
                    time.sleep(_retry_delay(exc, attempt))
                    continue
                item["error"] = str(exc)
                return item
        else:
            return item
        part.write_bytes(payload)
        item["bytes"] = len(payload)
        item["sha256"] = hashlib.sha256(payload).hexdigest()
        headers = {
            str(key).lower(): value for key, value in item.get("response_headers", {}).items()
        }
        if headers.get("content-length") is not None and int(headers["content-length"]) != len(
            payload
        ):
            item.update(status="INVALID", error="HTTP_CONTENT_LENGTH_MISMATCH")
        if str(headers.get("x-slice-size")) != "10":
            item.update(status="INVALID", error="HTTP_X_SLICE_SIZE_MISMATCH")
        gzip_payload = payload[:2] == b"\x1f\x8b"
        destination = stem.with_suffix(".ndjson.gz") if gzip_payload else stem
        if destination.exists():
            raise FileExistsError(f"raw original appeared during download: {destination}")
        part.rename(destination)
        if gzip_payload:
            with gzip.open(destination, "rb") as stream:
                while stream.read(1024 * 1024):
                    pass
            item["gzip_integrity"] = "PASS"
        else:
            item["gzip_integrity"] = "NOT_COMPRESSED"
        item.update(
            status=item.get("status") if item.get("status") == "INVALID" else "AVAILABLE",
            local_path=destination.as_posix(),
            coverage=f"slice_offset_{offset}_10_minutes",
        )
        _write_raw_sidecar(destination, item)
    except (URLError, TimeoutError, OSError, EOFError, gzip.BadGzipFile) as exc:
        item.update(status="INVALID", error=str(exc))
    finally:
        if part.exists() and item.get("status") == "AVAILABLE":
            part.unlink()
    return item


def _write_raw_sidecar(original: Path, item: dict[str, object]) -> None:
    sidecar = original.with_name(original.name + ".meta.json")
    temporary = sidecar.with_suffix(sidecar.suffix + ".tmp")
    temporary.write_text(json.dumps(item, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(sidecar)


def collect_raw(
    *,
    dates: Iterable[date] | None = None,
    root: Path = ROOT,
    manifest_path: Path = MANIFEST,
    timeout: float = 60.0,
    concurrency: int = 6,
    revalidate_orphans: bool = False,
) -> dict[str, object]:
    authorized = candidate_dates()
    days = list(authorized if dates is None else dates)
    if not days or len(set(days)) != len(days) or any(day not in authorized for day in days):
        raise ValueError("ONLY_AUTHORIZED_MONTHLY_CANDIDATES_ALLOWED")
    if concurrency < 1 or concurrency > 6:
        raise ValueError("raw concurrency must be between 1 and 6")
    payload = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    )
    payload["canonical_trade_manifest_sha256"] = AUDITED_SHA
    payload["raw_acquisition_source_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    entries = {str(item["date"]): item for item in payload.get("dates", [])}
    prior_offsets = {
        day: {int(item["offset"]): item for item in entry.get("raw_slices", [])}
        for day, entry in entries.items()
    }
    jobs = [(day, offset) for day in days for offset in range(0, 1440, 10)]
    pool = ThreadPoolExecutor(max_workers=concurrency)
    futures = {}
    try:
        futures = {
            pool.submit(
                _raw_slice,
                day,
                offset,
                root,
                timeout,
                prior_offsets.get(day.isoformat(), {}).get(offset),
                revalidate_orphans,
            ): (day, offset)
            for day, offset in jobs
        }
        for future in as_completed(futures):
            day, offset = futures[future]
            entry = entries.setdefault(day.isoformat(), {"date": day.isoformat()})
            slices = prior_offsets.setdefault(day.isoformat(), {})
            item = (
                future.result()
                if not future.exception()
                else {
                    "date": day.isoformat(),
                    "offset": offset,
                    "status": "INVALID",
                    "error": str(future.exception()),
                }
            )
            slices[int(item["offset"])] = item
            entry["raw_slices"] = sorted(slices.values(), key=lambda value: value["offset"])
            _persist_raw_manifest(manifest_path, payload, entries)
    except Exception:
        for future in futures:
            future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)
    for entry in entries.values():
        key = str(entry["date"])
        if prior_offsets.get(key) or "raw_slices" in entry:
            entry["raw_slices"] = sorted(
                prior_offsets[key].values(), key=lambda item: item["offset"]
            )
    payload.update(
        {
            "schema_version": payload.get("schema_version", "tardis-free-l2-v1"),
            "symbol": "USDCUSDT",
            "source": "Tardis",
            "dates": [entries[day.isoformat()] for day in days],
        }
    )
    _persist_raw_manifest(manifest_path, payload, entries)
    return payload


def _write_raw_manifest(
    path: Path, payload: dict[str, object], entries: dict[str, dict[str, object]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = dict(payload)
    merged.update(
        {
            "schema_version": payload.get("schema_version", "tardis-free-l2-v1"),
            "symbol": "USDCUSDT",
            "source": "Tardis",
            "dates": [entries[key] for key in sorted(entries)],
        }
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _persist_raw_manifest(
    path: Path, payload: dict[str, object], entries: dict[str, dict[str, object]]
) -> None:
    deadline = time.monotonic() + 2.0
    while True:
        try:
            _write_raw_manifest(path, payload, entries)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="validate existing originals only")
    parser.add_argument("--resume", action="store_true", help="reuse manifest-verified originals")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--raw", action="store_true", help="collect native raw 10-minute sidecars")
    parser.add_argument(
        "--dates",
        nargs="*",
        type=date.fromisoformat,
        help="authorized first-of-month dates (raw probe/resume)",
    )
    parser.add_argument(
        "--revalidate-orphans",
        action="store_true",
        help="verify unknown originals against a fresh public response",
    )
    args = parser.parse_args()
    if args.raw:
        if args.offline:
            parser.error("--offline cannot be combined with --raw")
        result = collect_raw(
            dates=args.dates,
            root=args.root,
            manifest_path=args.manifest,
            timeout=args.timeout,
            revalidate_orphans=args.revalidate_orphans,
        )
    elif args.offline:
        result = collect(
            dates=args.dates or candidate_dates(),
            root=args.root,
            manifest_path=args.manifest,
            timeout=args.timeout,
            concurrency=1,
            download=False,
        )
    else:
        result = collect(root=args.root, manifest_path=args.manifest, timeout=args.timeout)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
