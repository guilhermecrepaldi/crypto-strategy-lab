from __future__ import annotations

import csv
import gzip
import io
import json
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from itertools import pairwise
from pathlib import Path
from urllib.error import HTTPError

from pydantic import BaseModel, ConfigDict, Field

from crypto_strategy_lab.data.aggregation import aggregate_candles
from crypto_strategy_lab.data.binance import (
    DatasetIntegrityError,
    DownloadManifest,
    _read_url,
    _sha256,
    download_verified_archive,
    epoch_to_utc,
    monthly_kline_url,
    parse_kline_archive,
    validate_candle_sequence,
)
from crypto_strategy_lab.data.universe import static_symbol_exclusion
from crypto_strategy_lab.domain import Candle, canonical_hash, require_utc


class GapPolicy(StrEnum):
    STOP = "STOP"
    INVALIDATE_EPISODE = "INVALIDATE_EPISODE"


class ArchiveEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    year: int
    month: int = Field(ge=1, le=12)
    source_url: str
    local_path: str
    sha256: str
    size_bytes: int
    candle_count: int
    first_open_time: datetime
    last_close_time: datetime


class SymbolCoverage(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    first_open_time: datetime
    last_close_time: datetime
    candle_count: int
    expected_count: int
    missing_count: int
    coverage_ratio: str
    gaps: list[tuple[datetime, datetime]]
    duplicate_count: int = 0
    invalid_timestamp_count: int = 0
    valid: bool


class HistoricalDatasetManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "historical-dataset-v1"
    source: str = "BINANCE_PUBLIC_DATA_SPOT_MONTHLY_KLINES"
    interval: str = "5m"
    generated_at: datetime
    requested_start: datetime
    requested_end: datetime
    data_available_until: datetime
    gap_policy: GapPolicy
    archives: list[ArchiveEvidence]
    coverage: list[SymbolCoverage]
    symbols: list[str]
    candle_count: int
    archive_bytes: int
    duplicate_count: int
    invalid_timestamp_count: int
    dataset_hash: str
    normalized_path: str
    locked_test_accessed: bool = False


class HistoricalCatalogEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    monthly_archives: list[str]
    checksum_sha256: list[str]


class HistoricalCatalogManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "historical-catalog-v1"
    source: str = "BINANCE_PUBLIC_DATA_S3_ARCHIVE_KEYS"
    generated_at: datetime
    effective_at: datetime
    lookback_start: datetime
    entries: list[HistoricalCatalogEntry]
    exclusions: dict[str, str]
    catalog_hash: str
    uses_current_exchange_status: bool = False
    locked_test_accessed: bool = False


class DailyLiquidityEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    rank: int
    symbol: str
    quote_volume_usdt: Decimal
    daily_candle_count: int
    first_open_time: datetime
    last_open_time: datetime
    archive_sha256: list[str]


class DailyLiquidityAudit(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "daily-liquidity-audit-v1"
    catalog_hash: str
    episode_start: datetime
    lookback_start: datetime
    selected_symbols: list[str]
    ranking: list[DailyLiquidityEntry]
    exclusions: dict[str, str]
    ranking_hash: str
    future_rows_used: int = 0
    locked_test_accessed: bool = False


@dataclass(frozen=True)
class DownloadBatch:
    verified: list[DownloadManifest]
    unavailable_urls: list[str]


def parse_utc_date(value: str) -> datetime:
    parsed = date.fromisoformat(value)
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def iter_months(start: datetime, end: datetime) -> list[tuple[int, int]]:
    start = require_utc(start)
    end = require_utc(end)
    if start >= end:
        raise ValueError("history period must be non-empty")
    cursor = datetime(start.year, start.month, 1, tzinfo=UTC)
    result: list[tuple[int, int]] = []
    while cursor < end:
        result.append((cursor.year, cursor.month))
        cursor = (
            datetime(cursor.year + 1, 1, 1, tzinfo=UTC)
            if cursor.month == 12
            else datetime(cursor.year, cursor.month + 1, 1, tzinfo=UTC)
        )
    return result


def discover_historical_catalog(
    *,
    effective_at: datetime,
    lookback: timedelta,
    max_workers: int = 16,
) -> HistoricalCatalogManifest:
    """Discover archive-backed pairs without consulting current exchangeInfo."""
    effective_at = require_utc(effective_at)
    lookback_start = effective_at - lookback
    symbols = _list_archive_symbol_directories()
    exclusions = {
        symbol: reason
        for symbol in symbols
        if (reason := static_symbol_exclusion(symbol)) is not None
    }
    candidates = [symbol for symbol in symbols if symbol not in exclusions]
    months = iter_months(lookback_start, effective_at)

    def probe(symbol: str) -> HistoricalCatalogEntry | None:
        urls: list[str] = []
        checksums: list[str] = []
        for year, month in months:
            url = monthly_kline_url(symbol, year, month)
            try:
                checksum = _read_url(f"{url}.CHECKSUM").decode("ascii").split()[0].lower()
            except HTTPError as error:
                if error.code == 404:
                    return None
                raise
            if len(checksum) != 64:
                raise DatasetIntegrityError(f"invalid historical checksum for {url}")
            urls.append(url)
            checksums.append(checksum)
        return HistoricalCatalogEntry(
            symbol=symbol,
            monthly_archives=urls,
            checksum_sha256=checksums,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        entries = [item for item in executor.map(probe, candidates) if item is not None]
    for symbol in candidates:
        if not any(item.symbol == symbol for item in entries):
            exclusions[symbol] = "no complete official archive coverage in lookback"
    identity = {
        "source": "BINANCE_PUBLIC_DATA_S3_ARCHIVE_KEYS",
        "effective_at": effective_at,
        "lookback_start": lookback_start,
        "entries": [item.model_dump(mode="json") for item in entries],
        "exclusions": exclusions,
    }
    return HistoricalCatalogManifest(
        generated_at=datetime.now(UTC),
        effective_at=effective_at,
        lookback_start=lookback_start,
        entries=sorted(entries, key=lambda item: item.symbol),
        exclusions=dict(sorted(exclusions.items())),
        catalog_hash=canonical_hash(identity),
    )


def _list_archive_symbol_directories() -> list[str]:
    endpoint = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
    prefix = "data/spot/monthly/klines/"
    marker = ""
    symbols: list[str] = []
    while True:
        query = urllib.parse.urlencode({"delimiter": "/", "prefix": prefix, "marker": marker})
        root = ET.fromstring(_read_url(f"{endpoint}?{query}"))
        namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        for node in root.findall("s3:CommonPrefixes/s3:Prefix", namespace):
            if node.text:
                symbols.append(node.text.removeprefix(prefix).strip("/"))
        truncated = root.findtext("s3:IsTruncated", default="false", namespaces=namespace)
        if truncated.lower() != "true":
            break
        marker = root.findtext("s3:NextMarker", default="", namespaces=namespace)
        if not marker:
            raise DatasetIntegrityError("truncated Binance archive listing omitted NextMarker")
    return sorted(set(symbols))


def download_history_period(
    symbols: list[str],
    *,
    start: datetime,
    end: datetime,
    destination: Path,
    allow_unavailable: bool = False,
    interval: str = "5m",
    max_workers: int = 8,
) -> DownloadBatch:
    """Download official monthly Spot archives; never calls authenticated APIs."""
    if interval not in {"5m", "1d"}:
        raise ValueError("history download interval must be 5m or 1d")
    jobs = [
        (symbol, year, month)
        for symbol in sorted({item.upper() for item in symbols})
        for year, month in iter_months(start, end)
    ]

    def download(job: tuple[str, int, int]) -> tuple[DownloadManifest | None, str | None]:
        symbol, year, month = job
        url = monthly_kline_url(symbol, year, month, interval)
        try:
            return download_verified_archive(url, destination / symbol / interval), None
        except HTTPError as error:
            if error.code == 404 and allow_unavailable:
                return None, url
            raise

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(download, jobs))
    verified = [item for item, _missing in results if item is not None]
    unavailable = [missing for _item, missing in results if missing is not None]
    return DownloadBatch(verified=verified, unavailable_urls=unavailable)


def ingest_history_period(
    symbols: list[str],
    *,
    start: datetime,
    end: datetime,
    raw_root: Path,
    normalized_path: Path,
    manifest_path: Path,
    gap_policy: GapPolicy = GapPolicy.STOP,
) -> HistoricalDatasetManifest:
    """Verify local checksums and create one normalized artifact usable without network."""
    start = require_utc(start)
    end = require_utc(end)
    archives: list[ArchiveEvidence] = []
    candles: list[Candle] = []
    for symbol in sorted({item.upper() for item in symbols}):
        for year, month in iter_months(start, end):
            filename = f"{symbol}-5m-{year:04d}-{month:02d}.zip"
            path = raw_root / symbol / "5m" / filename
            checksum_path = path.with_name(f"{filename}.CHECKSUM")
            if not path.exists() or not checksum_path.exists():
                raise DatasetIntegrityError(f"missing verified archive or checksum: {path}")
            expected = checksum_path.read_text(encoding="ascii").strip().split()[0].lower()
            actual = _sha256(path)
            if actual != expected:
                raise DatasetIntegrityError(f"local checksum mismatch for {path}")
            parsed = parse_kline_archive(path, symbol)
            selected = [item for item in parsed if start <= item.open_time < end]
            if not selected:
                raise DatasetIntegrityError(f"archive has no requested candles: {path}")
            candles.extend(selected)
            archives.append(
                ArchiveEvidence(
                    symbol=symbol,
                    year=year,
                    month=month,
                    source_url=monthly_kline_url(symbol, year, month),
                    local_path=str(path),
                    sha256=actual,
                    size_bytes=path.stat().st_size,
                    candle_count=len(selected),
                    first_open_time=selected[0].open_time,
                    last_close_time=selected[-1].close_time,
                )
            )
    candles.sort(key=lambda item: (item.symbol, item.open_time))
    coverage = _coverage(candles, start, end)
    invalid = [item for item in coverage if not item.valid]
    if invalid and gap_policy == GapPolicy.STOP:
        summary = ", ".join(f"{item.symbol}:{item.missing_count}" for item in invalid)
        raise DatasetIntegrityError(f"history contains incomplete symbol coverage: {summary}")
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(normalized_path, "wt", encoding="utf-8", newline="\n") as handle:
        for candle in sorted(candles, key=lambda item: (item.open_time, item.symbol)):
            handle.write(json.dumps(candle.model_dump(mode="json"), sort_keys=True) + "\n")
    identity = {
        "schema_version": "historical-dataset-v1",
        "source": "BINANCE_PUBLIC_DATA_SPOT_MONTHLY_KLINES",
        "start": start,
        "end": end,
        "gap_policy": gap_policy,
        "archives": [item.model_dump(mode="json", exclude={"local_path"}) for item in archives],
        "coverage": [item.model_dump(mode="json") for item in coverage],
    }
    manifest = HistoricalDatasetManifest(
        generated_at=datetime.now(UTC),
        requested_start=start,
        requested_end=end,
        data_available_until=end - timedelta(microseconds=1),
        gap_policy=gap_policy,
        archives=archives,
        coverage=coverage,
        symbols=sorted({item.symbol for item in candles}),
        candle_count=len(candles),
        archive_bytes=sum(item.size_bytes for item in archives),
        duplicate_count=sum(item.duplicate_count for item in coverage),
        invalid_timestamp_count=sum(item.invalid_timestamp_count for item in coverage),
        dataset_hash=canonical_hash(identity),
        normalized_path=str(normalized_path),
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def load_normalized_history(
    normalized_path: Path,
    *,
    not_after: datetime | None = None,
) -> list[Candle]:
    cutoff = require_utc(not_after) if not_after else None
    candles: list[Candle] = []
    with gzip.open(normalized_path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                candle = Candle.model_validate(json.loads(line))
            except (ValueError, json.JSONDecodeError) as error:
                raise DatasetIntegrityError(
                    f"invalid normalized candle at line {line_number}: {error}"
                ) from error
            if cutoff is not None and candle.available_at > cutoff:
                raise DatasetIntegrityError(f"future candle at normalized line {line_number}")
            candles.append(candle)
    validate_candle_sequence(sorted(candles, key=lambda item: (item.symbol, item.open_time)))
    return sorted(candles, key=lambda item: (item.open_time, item.symbol))


def verify_local_archives(
    symbols: list[str],
    *,
    start: datetime,
    end: datetime,
    raw_root: Path,
) -> list[ArchiveEvidence]:
    evidence: list[ArchiveEvidence] = []
    for symbol in sorted({item.upper() for item in symbols}):
        for year, month in iter_months(start, end):
            filename = f"{symbol}-5m-{year:04d}-{month:02d}.zip"
            path = raw_root / symbol / "5m" / filename
            checksum_path = path.with_name(f"{filename}.CHECKSUM")
            if not path.exists() or not checksum_path.exists():
                raise DatasetIntegrityError(f"missing archive or checksum: {path}")
            expected = checksum_path.read_text(encoding="ascii").strip().split()[0].lower()
            actual = _sha256(path)
            if actual != expected:
                raise DatasetIntegrityError(f"local checksum mismatch for {path}")
            candles = parse_kline_archive(path, symbol)
            evidence.append(
                ArchiveEvidence(
                    symbol=symbol,
                    year=year,
                    month=month,
                    source_url=monthly_kline_url(symbol, year, month),
                    local_path=str(path),
                    sha256=actual,
                    size_bytes=path.stat().st_size,
                    candle_count=len(candles),
                    first_open_time=candles[0].open_time,
                    last_close_time=candles[-1].close_time,
                )
            )
    return evidence


def verify_aggregations(candles: list[Candle]) -> dict[str, int]:
    return {f"{minutes}m": len(aggregate_candles(candles, minutes)) for minutes in (15, 30, 60)}


def rank_catalog_by_daily_quote_volume(
    catalog: HistoricalCatalogManifest,
    *,
    raw_root: Path,
) -> DailyLiquidityAudit:
    """Rank the complete archive-backed catalog with compact official 1d klines."""
    if catalog.locked_test_accessed:
        raise ValueError("LOCKED_TEST catalogs are forbidden")
    expected_days = int((catalog.effective_at - catalog.lookback_start) / timedelta(days=1))
    ranked: list[tuple[str, Decimal, list[datetime], list[str]]] = []
    exclusions: dict[str, str] = {}
    for catalog_entry in catalog.entries:
        symbol = catalog_entry.symbol
        times: list[datetime] = []
        total = Decimal("0")
        hashes: list[str] = []
        for year, month in iter_months(catalog.lookback_start, catalog.effective_at):
            filename = f"{symbol}-1d-{year:04d}-{month:02d}.zip"
            path = raw_root / symbol / "1d" / filename
            checksum_path = path.with_name(f"{filename}.CHECKSUM")
            if not path.exists() or not checksum_path.exists():
                raise DatasetIntegrityError(f"missing daily ranking evidence: {path}")
            expected = checksum_path.read_text(encoding="ascii").split()[0].lower()
            actual = _sha256(path)
            if actual != expected:
                raise DatasetIntegrityError(f"daily ranking checksum mismatch: {path}")
            hashes.append(actual)
            with zipfile.ZipFile(path) as archive:
                members = [item for item in archive.infolist() if not item.is_dir()]
                if len(members) != 1 or Path(members[0].filename).name != members[0].filename:
                    raise DatasetIntegrityError(f"unsafe daily ranking archive: {path}")
                with archive.open(members[0]) as raw:
                    reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
                    for row_number, row in enumerate(reader, start=1):
                        if not row:
                            continue
                        try:
                            open_time = epoch_to_utc(row[0])
                            quote_volume = Decimal(row[7])
                        except (ValueError, OverflowError, InvalidOperation, IndexError):
                            if row_number == 1:
                                continue
                            raise DatasetIntegrityError(
                                f"invalid daily ranking row {row_number} in {path}"
                            ) from None
                        if catalog.lookback_start <= open_time < catalog.effective_at:
                            times.append(open_time)
                            total += quote_volume
        times.sort()
        if len(times) != expected_days or any(
            right != left + timedelta(days=1) for left, right in pairwise(times)
        ):
            exclusions[symbol] = (
                f"incomplete daily coverage: expected {expected_days}, got {len(times)}"
            )
            continue
        ranked.append((symbol, total, times, hashes))
    ranked.sort(key=lambda item: (-item[1], item[0]))
    entries = [
        DailyLiquidityEntry(
            rank=index,
            symbol=symbol,
            quote_volume_usdt=total,
            daily_candle_count=len(times),
            first_open_time=times[0],
            last_open_time=times[-1],
            archive_sha256=hashes,
        )
        for index, (symbol, total, times, hashes) in enumerate(ranked, start=1)
    ]
    if len(entries) < 4:
        raise DatasetIntegrityError("fewer than four complete pairs in daily liquidity ranking")
    identity = {
        "catalog_hash": catalog.catalog_hash,
        "episode_start": catalog.effective_at,
        "lookback_start": catalog.lookback_start,
        "ranking": [item.model_dump(mode="json") for item in entries],
        "exclusions": exclusions,
    }
    return DailyLiquidityAudit(
        catalog_hash=catalog.catalog_hash,
        episode_start=catalog.effective_at,
        lookback_start=catalog.lookback_start,
        selected_symbols=[item.symbol for item in entries[:4]],
        ranking=entries,
        exclusions=dict(sorted(exclusions.items())),
        ranking_hash=canonical_hash(identity),
    )


def _coverage(candles: list[Candle], start: datetime, end: datetime) -> list[SymbolCoverage]:
    result: list[SymbolCoverage] = []
    expected = int((end - start) / timedelta(minutes=5))
    for symbol in sorted({item.symbol for item in candles}):
        series = [item for item in candles if item.symbol == symbol]
        gaps = validate_candle_sequence(series)
        missing = sum(
            int((gap_end - gap_start) / timedelta(minutes=5)) for gap_start, gap_end in gaps
        )
        boundary_missing = int((series[0].open_time - start) / timedelta(minutes=5)) + int(
            (end - (series[-1].open_time + timedelta(minutes=5))) / timedelta(minutes=5)
        )
        missing += max(0, boundary_missing)
        result.append(
            SymbolCoverage(
                symbol=symbol,
                first_open_time=series[0].open_time,
                last_close_time=series[-1].close_time,
                candle_count=len(series),
                expected_count=expected,
                missing_count=missing,
                coverage_ratio=str(len(series) / expected),
                gaps=gaps,
                valid=missing == 0 and len(series) == expected,
            )
        )
    return result
