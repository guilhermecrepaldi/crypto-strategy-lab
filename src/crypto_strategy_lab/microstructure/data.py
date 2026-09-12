from __future__ import annotations

import csv
import hashlib
import io
import re
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.models import TradeEvent


class MicrostructureIntegrityError(ValueError):
    """Archive content is malformed or fails sequence integrity checks."""


TimestampUnit = Literal["milliseconds", "microseconds"]
ArchiveCadence = Literal["daily", "monthly"]


@dataclass(frozen=True, slots=True)
class ArchiveTrade:
    """Lightweight decoded trade record yielded by :func:`iter_archive`."""

    trade_id: int
    sequence: int
    individual_trade_count: int
    timestamp: datetime
    timestamp_unit: TimestampUnit
    price: Decimal
    quantity: Decimal
    buyer_is_maker: bool


class MicrostructureManifest(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: str = "microstructure-archive-v1"
    symbol: str
    kind: Literal["trades", "aggTrades"]
    utc_date: date
    downloaded_at: datetime
    local_path: str
    size_bytes: int
    origin: str
    sha256: str
    record_count: int
    first_timestamp: datetime
    last_timestamp: datetime
    first_trade_id: int
    last_trade_id: int
    gaps: list[tuple[int, int]]
    duplicates: list[int]
    # Default keeps historical manifests readable; newly built manifests always set it
    # from the raw archive rather than relying on this compatibility value.
    timestamp_unit: TimestampUnit = "milliseconds"
    # ``None`` is intentional for manifests written before coverage was added.
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    cadence: ArchiveCadence = "daily"
    first_event_offset_seconds: Decimal
    last_event_before_day_end_seconds: Decimal
    # Keep parse_status for manifests produced before integrity_status was added.
    parse_status: Literal["VALID", "INVALID"] = "VALID"
    integrity_status: Literal["VALID", "INVALID"] = "VALID"

    @property
    def period(self) -> str:
        return self.utc_date.isoformat()


class HistoryManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "microstructure-history-v1"
    symbol: str
    kind: Literal["trades", "aggTrades"]
    requested_start: date
    requested_end: date
    all_available: bool
    discovered_first_date: date
    discovered_last_date: date
    archives: tuple[MicrostructureManifest, ...]
    missing_dates: tuple[date, ...]
    missing_date_ranges: tuple[tuple[date, date], ...] = ()
    no_trade_date_ranges: tuple[tuple[date, date], ...] = ()
    unresolved_missing_date_ranges: tuple[tuple[date, date], ...] = ()
    cross_archive_gaps: tuple[tuple[int, int], ...]
    cross_archive_overlaps: tuple[tuple[int, int], ...]
    cross_archive_timestamp_gaps: tuple[tuple[datetime, datetime], ...] = ()
    cross_archive_timestamp_overlaps: tuple[tuple[datetime, datetime], ...] = ()
    invalidity_reasons: tuple[str, ...] = ()
    total_records: int
    total_size_bytes: int
    first_timestamp: datetime
    last_timestamp: datetime
    dataset_hash: str
    integrity_status: Literal["VALID", "INVALID"]


def _timestamp(value: str) -> datetime:
    try:
        integer = int(value)
    except ValueError as exc:
        raise MicrostructureIntegrityError(f"invalid timestamp: {value!r}") from exc
    scale = 1_000_000 if _timestamp_unit(value) == "microseconds" else 1_000
    seconds, remainder = divmod(integer, scale)
    micros = remainder * (1_000_000 // scale)
    return datetime.fromtimestamp(seconds, UTC).replace(microsecond=micros)


def _timestamp_unit(value: str) -> TimestampUnit:
    """Identify the unit used by one raw Binance timestamp."""
    try:
        integer = int(value)
    except ValueError as exc:
        raise MicrostructureIntegrityError(f"invalid timestamp: {value!r}") from exc
    # Binance switched archive timestamps from milliseconds to microseconds in 2025.
    return "microseconds" if abs(integer) >= 10**14 else "milliseconds"


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise MicrostructureIntegrityError(f"invalid decimal: {value!r}") from exc


def _positive_decimal(value: str) -> Decimal:
    number = _decimal(value)
    if not number.is_finite() or number <= 0:
        raise MicrostructureIntegrityError(f"decimal must be finite and positive: {value!r}")
    return number


def _strict_bool(value: str) -> bool:
    if value not in {"true", "false"}:
        raise MicrostructureIntegrityError(f"invalid maker boolean: {value!r}")
    return value == "true"


def parse_archive(
    path: str | Path, kind: Literal["trades", "aggTrades"] = "trades"
) -> list[TradeEvent]:
    """Parse one official Binance Spot ZIP archive without converting numbers to float."""
    return [_trade_event(record) for record in iter_archive(path, kind)]


def iter_archive(
    path: str | Path, kind: Literal["trades", "aggTrades"] = "trades"
) -> Iterator[ArchiveTrade]:
    """Stream decoded rows from one official Binance Spot ZIP archive.

    The ZIP and CSV handles stay open only for the lifetime of iteration. Each yielded
    record is a small frozen dataclass; no archive-sized list is materialized.
    """
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise MicrostructureIntegrityError("archive must contain exactly one CSV")
        text = io.TextIOWrapper(archive.open(names[0]), encoding="utf-8", newline="")
        for row in csv.reader(text):
            if _is_header(row):
                continue
            yield _archive_trade_from_row(row, path, kind)


def select_history_archives(
    manifest: HistoryManifest,
    *,
    start: datetime,
    end_exclusive: datetime,
) -> tuple[MicrostructureManifest, ...]:
    """Select one non-overlapping archive authority for an already validated interval."""
    start = start.astimezone(UTC)
    end_exclusive = end_exclusive.astimezone(UTC)
    if start >= end_exclusive:
        raise ValueError("start must precede end_exclusive")
    if manifest.integrity_status != "VALID" or manifest.invalidity_reasons:
        raise MicrostructureIntegrityError("history iteration requires a VALID manifest")
    if start < manifest.first_timestamp:
        raise MicrostructureIntegrityError("requested history precedes validated coverage")
    if end_exclusive > manifest.last_timestamp + timedelta(microseconds=1):
        raise MicrostructureIntegrityError("requested history exceeds validated coverage")
    selected = tuple(
        item
        for item in manifest.archives
        if item.last_timestamp >= start and item.first_timestamp < end_exclusive
    )
    if not selected:
        raise MicrostructureIntegrityError("requested history has no archives")
    monthly = tuple(item for item in selected if item.cadence == "monthly")
    if monthly:
        selected = tuple(
            item
            for item in selected
            if item.cadence == "monthly"
            or not any(_coverage_overlaps(item, replacement) for replacement in monthly)
        )
    return tuple(sorted(selected, key=_coverage_start))


def iter_history(
    manifest: HistoryManifest,
    *,
    start: datetime,
    end_exclusive: datetime,
) -> Iterator[ArchiveTrade]:
    """Stream a validated consolidated interval without materializing trade objects."""
    for item in select_history_archives(manifest, start=start, end_exclusive=end_exclusive):
        for event in iter_archive(Path(item.local_path), manifest.kind):
            # Binance public archives are sorted by event time. Stop consuming the
            # physical member at the hard boundary so an economic replay cannot
            # even parse rows from its sealed suffix.
            if event.timestamp >= end_exclusive:
                break
            if start <= event.timestamp < end_exclusive:
                yield event


def _is_header(row: list[str]) -> bool:
    return bool(row) and row[0].strip().lower() in {
        "id",
        "aggtradeid",
        "agg_trade_id",
        "aggid",
        "agg",
    }


def _archive_trade_from_row(
    row: list[str], path: Path, kind: Literal["trades", "aggTrades"]
) -> ArchiveTrade:
    try:
        if kind == "trades":
            event_id, price, quantity, _, stamp, maker = row[:6]
            last_id = int(event_id)
            individual_trade_count = 1
        else:
            event_id, price, quantity, first, last, stamp, maker = row[:7]
            first_id = int(first)
            last_id = int(last)
            individual_trade_count = last_id - first_id + 1
            if individual_trade_count <= 0:
                raise MicrostructureIntegrityError(
                    f"aggTrade ID range is invalid in {path}: {row!r}"
                )
        return ArchiveTrade(
            trade_id=int(event_id),
            sequence=last_id,
            individual_trade_count=individual_trade_count,
            timestamp=_timestamp(stamp),
            timestamp_unit=_timestamp_unit(stamp),
            price=_positive_decimal(price),
            quantity=_positive_decimal(quantity),
            buyer_is_maker=_strict_bool(maker.strip().lower()),
        )
    except (ValueError, IndexError) as exc:
        raise MicrostructureIntegrityError(f"invalid row in {path}: {row!r}") from exc


def _trade_event(record: ArchiveTrade) -> TradeEvent:
    return TradeEvent(
        trade_id=record.trade_id,
        sequence=record.sequence,
        timestamp=record.timestamp,
        price=record.price,
        quantity=record.quantity,
        buyer_is_maker=record.buyer_is_maker,
    )


def validate_events(events: list[TradeEvent]) -> tuple[list[tuple[int, int]], list[int]]:
    gaps: list[tuple[int, int]] = []
    duplicates: list[int] = []
    for previous, current in pairwise(events):
        if current.trade_id < previous.trade_id:
            raise MicrostructureIntegrityError("event IDs are not monotonic")
        if current.trade_id == previous.trade_id:
            duplicates.append(current.trade_id)
        if current.timestamp < previous.timestamp:
            raise MicrostructureIntegrityError("timestamps are not monotonic")
        if current.trade_id > previous.trade_id + 1:
            gaps.append((previous.trade_id, current.trade_id))
    return gaps, duplicates


def download_archive(url: str, destination: str | Path) -> Path:
    """Download an archive once, verifying/reusing its adjacent official CHECKSUM."""
    destination = Path(destination)
    checksum_path = destination.with_name(destination.name + ".CHECKSUM")
    checksum_bytes = _read_url(url + ".CHECKSUM")
    try:
        checksum_text = checksum_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise MicrostructureIntegrityError("invalid SHA256 checksum") from exc
    checksum_match = re.search(r"\b([0-9a-f]{64})\b", checksum_text, re.IGNORECASE)
    if checksum_match is None:
        raise MicrostructureIntegrityError("invalid SHA256 checksum")
    checksum = checksum_match.group(1).lower()
    if destination.exists():
        if _sha256_file(destination) != checksum:
            raise MicrostructureIntegrityError(
                "existing archive checksum mismatch; refusing overwrite"
            )
        checksum_path.write_bytes(checksum_bytes)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            digest = hashlib.sha256()
            request = urllib.request.Request(url, headers={"User-Agent": "crypto-strategy-lab/0.1"})
            with urllib.request.urlopen(request, timeout=120) as response:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    handle.write(chunk)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    assert temporary is not None
    if digest.hexdigest() != checksum:
        temporary.unlink(missing_ok=True)
        raise MicrostructureIntegrityError("download checksum mismatch")
    temporary.replace(destination)
    checksum_path.write_bytes(checksum_bytes)
    return destination


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "crypto-strategy-lab/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return cast(bytes, response.read())


def manifest_for(
    path: str | Path,
    events: list[TradeEvent],
    *,
    origin: str,
    period: str,
    symbol: str = "USDCUSDT",
    kind: Literal["trades", "aggTrades"] = "aggTrades",
    timestamp_unit: TimestampUnit | None = None,
    cadence: ArchiveCadence = "daily",
) -> MicrostructureManifest:
    if not events:
        raise MicrostructureIntegrityError("archive contains no trade events")
    gaps, duplicates = validate_events(events)
    archive_path = Path(path)
    archive_timestamp_unit = timestamp_unit or timestamp_unit_for_archive(archive_path, kind)
    try:
        if cadence == "monthly":
            year, month = (int(part) for part in period.split("-"))
            utc_date = date(year, month, 1)
            coverage_start, coverage_end = _month_bounds(utc_date)
        else:
            utc_date = date.fromisoformat(period)
            coverage_start = datetime.combine(utc_date, time.min, tzinfo=UTC)
            coverage_end = datetime.combine(utc_date, time.max, tzinfo=UTC)
    except (ValueError, TypeError) as exc:
        # Offline fixtures may use a descriptive daily period label; derive the
        # represented UTC day while retaining strict validation.
        if cadence == "monthly":
            raise MicrostructureIntegrityError(f"invalid monthly period: {period!r}") from exc
        utc_date = events[0].timestamp.date()
        coverage_start = datetime.combine(utc_date, time.min, tzinfo=UTC)
        coverage_end = datetime.combine(utc_date, time.max, tzinfo=UTC)
    if any(
        not (coverage_start.date() <= event.timestamp.date() <= coverage_end.date())
        for event in events
    ):
        raise MicrostructureIntegrityError(
            f"archive {archive_path} contains timestamps outside {period}"
        )
    archive_integrity: Literal["VALID", "INVALID"] = (
        "VALID" if not gaps and not duplicates else "INVALID"
    )
    return MicrostructureManifest(
        symbol=symbol.upper(),
        kind=kind,
        utc_date=utc_date,
        downloaded_at=datetime.fromtimestamp(archive_path.stat().st_mtime, tz=UTC),
        local_path=str(archive_path),
        size_bytes=archive_path.stat().st_size,
        origin=origin,
        sha256=_sha256_file(archive_path),
        record_count=len(events),
        first_timestamp=events[0].timestamp,
        last_timestamp=events[-1].timestamp,
        first_trade_id=events[0].trade_id,
        last_trade_id=events[-1].trade_id,
        gaps=gaps,
        duplicates=duplicates,
        timestamp_unit=archive_timestamp_unit,
        first_event_offset_seconds=_seconds(events[0].timestamp - coverage_start),
        last_event_before_day_end_seconds=_seconds(coverage_end - events[-1].timestamp),
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        cadence=cadence,
        parse_status=archive_integrity,
        integrity_status=archive_integrity,
    )


def manifest_from_archive(
    path: str | Path,
    *,
    origin: str,
    period: str,
    symbol: str = "USDCUSDT",
    kind: Literal["trades", "aggTrades"] = "trades",
    cadence: ArchiveCadence = "daily",
    timestamp_unit: TimestampUnit | None = None,
) -> MicrostructureManifest:
    """Build one archive manifest without materializing its decoded events."""
    archive_path = Path(path)
    declared_date: date | None = None
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    if cadence == "monthly":
        try:
            year, month = (int(part) for part in period.split("-"))
            declared_date = date(year, month, 1)
        except (TypeError, ValueError) as exc:
            raise MicrostructureIntegrityError(f"invalid monthly period: {period!r}") from exc
        coverage_start, coverage_end = _month_bounds(declared_date)
    else:
        try:
            declared_date = date.fromisoformat(period)
            coverage_start = datetime.combine(declared_date, time.min, tzinfo=UTC)
            coverage_end = datetime.combine(declared_date, time.max, tzinfo=UTC)
        except ValueError:
            # Daily fixture labels may be descriptive; derive the date from row one.
            declared_date = None

    first: ArchiveTrade | None = None
    previous: ArchiveTrade | None = None
    record_count = 0
    gaps: list[tuple[int, int]] = []
    duplicates: list[int] = []
    units: set[TimestampUnit] = set()
    for record in iter_archive(archive_path, kind):
        if declared_date is None:
            declared_date = record.timestamp.date()
            coverage_start = datetime.combine(declared_date, time.min, tzinfo=UTC)
            coverage_end = datetime.combine(declared_date, time.max, tzinfo=UTC)
        assert coverage_start is not None and coverage_end is not None
        if not (coverage_start.date() <= record.timestamp.date() <= coverage_end.date()):
            raise MicrostructureIntegrityError(
                f"archive {archive_path} contains timestamps outside {period}"
            )
        units.add(record.timestamp_unit)
        if previous is not None:
            if record.trade_id < previous.trade_id:
                raise MicrostructureIntegrityError("event IDs are not monotonic")
            if record.trade_id == previous.trade_id:
                duplicates.append(record.trade_id)
            if record.trade_id > previous.trade_id + 1:
                gaps.append((previous.trade_id, record.trade_id))
            if record.timestamp < previous.timestamp:
                raise MicrostructureIntegrityError("timestamps are not monotonic")
        first = first or record
        previous = record
        record_count += 1
    if first is None or previous is None:
        raise MicrostructureIntegrityError("archive contains no trade events")
    assert declared_date is not None and coverage_start is not None and coverage_end is not None
    if len(units) != 1:
        raise MicrostructureIntegrityError(
            f"archive {archive_path} has no single timestamp unit: {sorted(units)!r}"
        )
    archive_timestamp_unit: TimestampUnit = (
        timestamp_unit if timestamp_unit is not None else next(iter(units))
    )
    archive_integrity: Literal["VALID", "INVALID"] = (
        "VALID" if not gaps and not duplicates else "INVALID"
    )
    return MicrostructureManifest(
        symbol=symbol.upper(),
        kind=kind,
        utc_date=declared_date,
        downloaded_at=datetime.fromtimestamp(archive_path.stat().st_mtime, tz=UTC),
        local_path=str(archive_path),
        size_bytes=archive_path.stat().st_size,
        origin=origin,
        sha256=_sha256_file(archive_path),
        record_count=record_count,
        first_timestamp=first.timestamp,
        last_timestamp=previous.timestamp,
        first_trade_id=first.trade_id,
        last_trade_id=previous.trade_id,
        gaps=gaps,
        duplicates=duplicates,
        timestamp_unit=archive_timestamp_unit,
        first_event_offset_seconds=_seconds(first.timestamp - coverage_start),
        last_event_before_day_end_seconds=_seconds(coverage_end - previous.timestamp),
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        cadence=cadence,
        parse_status=archive_integrity,
        integrity_status=archive_integrity,
    )


def timestamp_unit_for_archive(
    path: str | Path, kind: Literal["trades", "aggTrades"]
) -> TimestampUnit:
    """Validate and identify the sole raw timestamp unit in an archive."""
    units = {record.timestamp_unit for record in iter_archive(path, kind)}
    if len(units) != 1:
        raise MicrostructureIntegrityError(
            f"archive {path} has no single timestamp unit: {sorted(units)!r}"
        )
    return units.pop()


def list_daily_archives(
    symbol: str, kind: Literal["trades", "aggTrades"] = "aggTrades"
) -> list[tuple[str, str]]:
    """List official daily archive keys, following S3 pagination."""
    prefix = f"data/spot/daily/{kind}/{symbol.strip().upper()}/"
    endpoint = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
    token = ""
    result: list[tuple[str, str]] = []
    while True:
        parameters = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            parameters["continuation-token"] = token
        root = ET.fromstring(_read_url(f"{endpoint}?{urllib.parse.urlencode(parameters)}"))
        for node in root.findall(".//{*}Contents"):
            key = node.findtext("{*}Key", "")
            if key.endswith(".zip"):
                result.append((key, "https://data.binance.vision/" + key))
        truncated = root.findtext("{*}IsTruncated", "false").lower() == "true"
        token = root.findtext("{*}NextContinuationToken", "")
        if not truncated:
            return sorted(result)


def list_monthly_archives(
    symbol: str, kind: Literal["trades", "aggTrades"] = "trades"
) -> list[tuple[str, str]]:
    """List official monthly archive keys, following the same offline-testable S3 path."""
    prefix = f"data/spot/monthly/{kind}/{symbol.strip().upper()}/"
    endpoint = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
    token = ""
    result: list[tuple[str, str]] = []
    while True:
        parameters = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            parameters["continuation-token"] = token
        root = ET.fromstring(_read_url(f"{endpoint}?{urllib.parse.urlencode(parameters)}"))
        for node in root.findall(".//{*}Contents"):
            key = node.findtext("{*}Key", "")
            if key.endswith(".zip"):
                result.append((key, "https://data.binance.vision/" + key))
        truncated = root.findtext("{*}IsTruncated", "false").lower() == "true"
        token = root.findtext("{*}NextContinuationToken", "")
        if not truncated:
            return sorted(result)


def reconcile_history_manifest(
    daily_manifest: HistoryManifest,
    destination: str | Path,
) -> HistoryManifest:
    """Fill incomplete USDCUSDT months with their complete official monthly archive.

    This function only consults the monthly catalog and local checksum-aware downloader;
    callers can inject both for fully offline verification.  Every daily archive in a
    month replaced by a monthly archive is omitted from the resulting manifest.
    """
    if daily_manifest.symbol.upper() != "USDCUSDT" or daily_manifest.kind != "trades":
        raise ValueError("monthly reconciliation is restricted to USDCUSDT trades")
    normalized = _build_history_manifest(
        daily_manifest.archives,
        symbol=daily_manifest.symbol,
        kind=daily_manifest.kind,
        requested_start=daily_manifest.requested_start,
        requested_end=daily_manifest.requested_end,
        all_available=daily_manifest.all_available,
        discovered_start=daily_manifest.discovered_first_date,
        discovered_end=daily_manifest.discovered_last_date,
    )
    unresolved = {
        day
        for first, last in normalized.unresolved_missing_date_ranges
        for day in (first + timedelta(days=offset) for offset in range((last - first).days + 1))
    }
    missing_months = sorted({(item.year, item.month) for item in unresolved})
    if not missing_months:
        return normalized
    entries = list_monthly_archives("USDCUSDT", "trades")
    by_month: dict[tuple[int, int], tuple[str, str]] = {}
    for key, url in entries:
        archive_month = _archive_month(key)
        by_month[archive_month] = (key, url)
    root = Path(destination)
    monthly: list[MicrostructureManifest] = []
    for year, month in missing_months:
        key_url = by_month.get((year, month))
        if key_url is None:
            raise MicrostructureIntegrityError(
                f"official monthly trades archive is missing for {year:04d}-{month:02d}"
            )
        key, url = key_url
        try:
            path = download_archive(url, root / key.rsplit("/", 1)[-1])
            monthly.append(
                manifest_from_archive(
                    path,
                    origin=url,
                    period=f"{year:04d}-{month:02d}",
                    symbol="USDCUSDT",
                    kind="trades",
                    cadence="monthly",
                )
            )
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise MicrostructureIntegrityError(
                f"monthly trades archive is absent or corrupt for {year:04d}-{month:02d}"
            ) from exc
    replaced = set(missing_months)
    retained = [item for item in normalized.archives if _coverage_month(item) not in replaced]
    return _build_history_manifest(
        [*retained, *monthly],
        symbol=normalized.symbol,
        kind=normalized.kind,
        requested_start=normalized.requested_start,
        requested_end=normalized.requested_end,
        all_available=normalized.all_available,
        discovered_start=normalized.discovered_first_date,
        discovered_end=normalized.discovered_last_date,
    )


def download_history_range(
    symbol: str,
    destination: str | Path,
    *,
    start: date | None = None,
    end: date | None = None,
    all_available: bool = False,
    kind: Literal["trades", "aggTrades"] = "aggTrades",
    max_workers: int = 8,
) -> HistoryManifest:
    if not all_available and start is None and end is None:
        raise ValueError("provide a range or all_available")
    entries = list_daily_archives(symbol, kind)
    if not entries:
        raise MicrostructureIntegrityError(f"no official daily {kind} archives for {symbol}")
    available = [(_archive_date(key), key, url) for key, url in entries]
    discovered_start = available[0][0]
    discovered_end = available[-1][0]
    requested_start = discovered_start if all_available or start is None else start
    requested_end = discovered_end if all_available or end is None else end
    if requested_start > requested_end:
        raise ValueError("start cannot exceed end")
    chosen = [
        (utc_date, key, url)
        for utc_date, key, url in available
        if requested_start <= utc_date <= requested_end
    ]
    if not chosen:
        raise MicrostructureIntegrityError("requested range has no official archives")
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)

    def obtain(item: tuple[date, str, str]) -> MicrostructureManifest:
        utc_date, key, url = item
        path = download_archive(url, root / key.rsplit("/", 1)[-1])
        return manifest_from_archive(
            path,
            origin=url,
            period=utc_date.isoformat(),
            symbol=symbol,
            kind=kind,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        manifests = sorted(pool.map(obtain, chosen), key=lambda item: item.utc_date)
    return _build_history_manifest(
        manifests,
        symbol=symbol,
        kind=kind,
        requested_start=requested_start,
        requested_end=requested_end,
        all_available=all_available,
        discovered_start=discovered_start,
        discovered_end=discovered_end,
    )


def slice_history_manifest(
    manifest: HistoryManifest,
    *,
    start: date,
    end: date,
) -> HistoryManifest:
    """Build a deterministic offline sub-manifest from already audited archives."""
    if start > end:
        raise ValueError("start cannot exceed end")
    if start < manifest.requested_start or end > manifest.requested_end:
        raise ValueError("slice must stay inside the parent manifest request")
    selected = tuple(
        item
        for item in manifest.archives
        if _coverage_start(item).date() <= end and _coverage_end(item).date() >= start
    )
    if not selected:
        raise MicrostructureIntegrityError("requested slice has no local archives")
    return _build_history_manifest(
        selected,
        symbol=manifest.symbol,
        kind=manifest.kind,
        requested_start=start,
        requested_end=end,
        all_available=False,
        discovered_start=manifest.discovered_first_date,
        discovered_end=manifest.discovered_last_date,
    )


def _build_history_manifest(
    manifests: Sequence[MicrostructureManifest],
    *,
    symbol: str,
    kind: Literal["trades", "aggTrades"],
    requested_start: date,
    requested_end: date,
    all_available: bool,
    discovered_start: date,
    discovered_end: date,
) -> HistoryManifest:
    if not manifests:
        raise MicrostructureIntegrityError("history manifest requires at least one archive")
    ordered = tuple(sorted(manifests, key=_coverage_start))
    expected_dates = {
        requested_start + timedelta(days=offset)
        for offset in range((requested_end - requested_start).days + 1)
    }
    present_dates: set[date] = set()
    for item in ordered:
        coverage_start = max(_coverage_start(item).date(), requested_start)
        coverage_end = min(_coverage_end(item).date(), requested_end)
        if coverage_start <= coverage_end:
            present_dates.update(
                coverage_start + timedelta(days=offset)
                for offset in range((coverage_end - coverage_start).days + 1)
            )
    missing_dates = tuple(sorted(expected_dates - present_dates))
    missing_date_ranges = _date_ranges(missing_dates)
    cross_gaps: list[tuple[int, int]] = []
    overlaps: list[tuple[int, int]] = []
    timestamp_gaps: list[tuple[datetime, datetime]] = []
    timestamp_overlaps: list[tuple[datetime, datetime]] = []
    proven_no_trade_dates: set[date] = set()
    for previous, current in pairwise(ordered):
        if current.first_trade_id <= previous.last_trade_id:
            overlaps.append((previous.last_trade_id, current.first_trade_id))
        elif current.first_trade_id > previous.last_trade_id + 1:
            cross_gaps.append((previous.last_trade_id, current.first_trade_id))
        if _coverage_start(current) > _coverage_end(previous) + timedelta(microseconds=1):
            timestamp_gaps.append((_coverage_end(previous), _coverage_start(current)))
        if current.first_timestamp <= previous.last_timestamp:
            timestamp_overlaps.append((previous.last_timestamp, current.first_timestamp))
        first_missing = _coverage_end(previous).date() + timedelta(days=1)
        last_missing = _coverage_start(current).date() - timedelta(days=1)
        if previous.last_trade_id + 1 == current.first_trade_id and first_missing <= last_missing:
            proven_no_trade_dates.update(
                first_missing + timedelta(days=offset)
                for offset in range((last_missing - first_missing).days + 1)
            )
    proven_no_trade_dates.intersection_update(missing_dates)
    unresolved_missing_dates = tuple(sorted(set(missing_dates) - proven_no_trade_dates))
    no_trade_date_ranges = _date_ranges(tuple(sorted(proven_no_trade_dates)))
    unresolved_missing_date_ranges = _date_ranges(unresolved_missing_dates)
    invalidity_reasons: list[str] = []
    if unresolved_missing_dates:
        invalidity_reasons.append("missing_requested_dates")
    if cross_gaps:
        invalidity_reasons.append("cross_archive_id_gaps")
    if overlaps:
        invalidity_reasons.append("cross_archive_id_overlaps")
    if timestamp_overlaps:
        invalidity_reasons.append("cross_archive_timestamp_overlaps")
    if any(item.gaps for item in ordered):
        invalidity_reasons.append("within_archive_id_gaps")
    if any(item.duplicates for item in ordered):
        invalidity_reasons.append("within_archive_duplicate_ids")
    integrity: Literal["VALID", "INVALID"] = "VALID" if not invalidity_reasons else "INVALID"
    dataset_entries: list[dict[str, object]] = []
    for item in ordered:
        entry: dict[str, object] = {
            "utc_date": item.utc_date,
            "sha256": item.sha256,
            "record_count": item.record_count,
        }
        if item.cadence != "daily" or item.coverage_start is not None:
            entry.update(
                {
                    "cadence": item.cadence,
                    "coverage_start": _coverage_start(item),
                    "coverage_end": _coverage_end(item),
                }
            )
        dataset_entries.append(entry)
    dataset_hash = canonical_hash(dataset_entries)
    return HistoryManifest(
        symbol=symbol.upper(),
        kind=kind,
        requested_start=requested_start,
        requested_end=requested_end,
        all_available=all_available,
        discovered_first_date=discovered_start,
        discovered_last_date=discovered_end,
        archives=ordered,
        missing_dates=missing_dates,
        missing_date_ranges=missing_date_ranges,
        no_trade_date_ranges=no_trade_date_ranges,
        unresolved_missing_date_ranges=unresolved_missing_date_ranges,
        cross_archive_gaps=tuple(cross_gaps),
        cross_archive_overlaps=tuple(overlaps),
        cross_archive_timestamp_gaps=tuple(timestamp_gaps),
        cross_archive_timestamp_overlaps=tuple(timestamp_overlaps),
        invalidity_reasons=tuple(invalidity_reasons),
        total_records=sum(item.record_count for item in ordered),
        total_size_bytes=sum(item.size_bytes for item in ordered),
        first_timestamp=ordered[0].first_timestamp,
        last_timestamp=ordered[-1].last_timestamp,
        dataset_hash=dataset_hash,
        integrity_status=integrity,
    )


def discover_daily_archive_dates(
    symbol: str, kind: Literal["trades", "aggTrades"] = "aggTrades"
) -> list[str]:
    return [_archive_date(key).isoformat() for key, _ in list_daily_archives(symbol, kind)]


def verify_history_manifest(manifest: HistoryManifest) -> None:
    """Re-validate every local archive and the consolidated manifest fully offline."""
    rebuilt: list[dict[str, object]] = []
    previous: MicrostructureManifest | None = None
    for expected in manifest.archives:
        path = Path(expected.local_path)
        if not path.is_file():
            raise MicrostructureIntegrityError(f"missing local archive: {path}")
        if path.stat().st_size != expected.size_bytes:
            raise MicrostructureIntegrityError(f"size changed for {path}")
        actual = manifest_from_archive(
            path,
            origin=expected.origin,
            period=(
                f"{expected.utc_date.year:04d}-{expected.utc_date.month:02d}"
                if expected.cadence == "monthly"
                else expected.utc_date.isoformat()
            ),
            symbol=manifest.symbol,
            kind=manifest.kind,
            cadence=expected.cadence,
        )
        comparable_fields = [
            "symbol",
            "kind",
            "utc_date",
            "sha256",
            "record_count",
            "first_timestamp",
            "last_timestamp",
            "first_trade_id",
            "last_trade_id",
            "gaps",
            "duplicates",
        ]
        # Older manifests did not contain these fields. Compare them whenever the
        # field was actually persisted, while still allowing historical artifacts
        # to be re-read and verified.
        if "timestamp_unit" in expected.model_fields_set:
            comparable_fields.append("timestamp_unit")
        if "coverage_start" in expected.model_fields_set:
            comparable_fields.extend(["coverage_start", "coverage_end"])
        if "cadence" in expected.model_fields_set:
            comparable_fields.append("cadence")
        if "integrity_status" in expected.model_fields_set:
            comparable_fields.append("integrity_status")
        if any(getattr(actual, field) != getattr(expected, field) for field in comparable_fields):
            raise MicrostructureIntegrityError(f"manifest metadata changed for {path}")
        if previous is not None:
            if actual.first_trade_id <= previous.last_trade_id:
                raise MicrostructureIntegrityError("cross-archive ID overlap")
            if actual.first_trade_id > previous.last_trade_id + 1:
                raise MicrostructureIntegrityError("cross-archive ID gap")
            if actual.first_timestamp <= previous.last_timestamp:
                raise MicrostructureIntegrityError("cross-archive timestamp overlap")
        rebuilt_entry: dict[str, object] = {
            "utc_date": actual.utc_date,
            "sha256": actual.sha256,
            "record_count": actual.record_count,
        }
        if expected.cadence != "daily" or "coverage_start" in expected.model_fields_set:
            rebuilt_entry.update(
                {
                    "cadence": actual.cadence,
                    "coverage_start": _coverage_start(actual),
                    "coverage_end": _coverage_end(actual),
                }
            )
        rebuilt.append(rebuilt_entry)
        previous = actual
    if canonical_hash(rebuilt) != manifest.dataset_hash:
        raise MicrostructureIntegrityError("consolidated dataset hash mismatch")
    expected_dates = {
        manifest.requested_start + timedelta(days=offset)
        for offset in range((manifest.requested_end - manifest.requested_start).days + 1)
    }
    present_dates: set[date] = set()
    for item in manifest.archives:
        coverage_start = max(_coverage_start(item).date(), manifest.requested_start)
        coverage_end = min(_coverage_end(item).date(), manifest.requested_end)
        if coverage_start <= coverage_end:
            present_dates.update(
                coverage_start + timedelta(days=offset)
                for offset in range((coverage_end - coverage_start).days + 1)
            )
    missing_dates = tuple(sorted(expected_dates - present_dates))
    if missing_dates != manifest.missing_dates:
        raise MicrostructureIntegrityError("missing date metadata changed")
    if (
        "missing_date_ranges" in manifest.model_fields_set
        and _date_ranges(missing_dates) != manifest.missing_date_ranges
    ):
        raise MicrostructureIntegrityError("missing date range metadata changed")
    rebuilt_history = _build_history_manifest(
        manifest.archives,
        symbol=manifest.symbol,
        kind=manifest.kind,
        requested_start=manifest.requested_start,
        requested_end=manifest.requested_end,
        all_available=manifest.all_available,
        discovered_start=manifest.discovered_first_date,
        discovered_end=manifest.discovered_last_date,
    )
    if rebuilt_history.cross_archive_gaps != manifest.cross_archive_gaps:
        raise MicrostructureIntegrityError("cross-archive ID gap metadata changed")
    if rebuilt_history.cross_archive_overlaps != manifest.cross_archive_overlaps:
        raise MicrostructureIntegrityError("cross-archive ID overlap metadata changed")
    if "cross_archive_timestamp_gaps" in manifest.model_fields_set and (
        rebuilt_history.cross_archive_timestamp_gaps != manifest.cross_archive_timestamp_gaps
    ):
        raise MicrostructureIntegrityError("timestamp gap metadata changed")
    if "cross_archive_timestamp_overlaps" in manifest.model_fields_set and (
        rebuilt_history.cross_archive_timestamp_overlaps
        != manifest.cross_archive_timestamp_overlaps
    ):
        raise MicrostructureIntegrityError("timestamp overlap metadata changed")
    if manifest.integrity_status != "VALID":
        raise MicrostructureIntegrityError("history manifest is not valid")


def _coverage_start(item: MicrostructureManifest) -> datetime:
    if item.coverage_start is not None:
        return item.coverage_start
    return datetime.combine(item.utc_date, time.min, tzinfo=UTC)


def _coverage_end(item: MicrostructureManifest) -> datetime:
    if item.coverage_end is not None:
        return item.coverage_end
    return datetime.combine(item.utc_date, time.max, tzinfo=UTC)


def _coverage_overlaps(left: MicrostructureManifest, right: MicrostructureManifest) -> bool:
    return _coverage_start(left) <= _coverage_end(right) and _coverage_start(
        right
    ) <= _coverage_end(left)


def _coverage_month(item: MicrostructureManifest) -> tuple[int, int]:
    start = _coverage_start(item)
    return start.year, start.month


def _month_bounds(first_day: date) -> tuple[datetime, datetime]:
    if first_day.month == 12:
        next_month = date(first_day.year + 1, 1, 1)
    else:
        next_month = date(first_day.year, first_day.month + 1, 1)
    return (
        datetime.combine(first_day, time.min, tzinfo=UTC),
        datetime.combine(next_month, time.min, tzinfo=UTC) - timedelta(microseconds=1),
    )


def _archive_date(key: str) -> date:
    match = re.search(r"(\d{4}-\d{2}-\d{2})\.zip$", key)
    if match is None:
        raise MicrostructureIntegrityError(f"unrecognized daily archive key {key}")
    return date.fromisoformat(match.group(1))


def _archive_month(key: str) -> tuple[int, int]:
    match = re.search(r"(\d{4})-(\d{2})\.zip$", key)
    if match is None:
        raise MicrostructureIntegrityError(f"unrecognized monthly archive key {key}")
    month = int(match.group(2))
    if month < 1 or month > 12:
        raise MicrostructureIntegrityError(f"unrecognized monthly archive key {key}")
    return int(match.group(1)), month


def _seconds(delta: timedelta) -> Decimal:
    return Decimal(delta.days * 86_400 + delta.seconds) + Decimal(delta.microseconds) / Decimal(
        "1000000"
    )


def _date_ranges(values: tuple[date, ...]) -> tuple[tuple[date, date], ...]:
    if not values:
        return ()
    ranges: list[tuple[date, date]] = []
    start = previous = values[0]
    for current in values[1:]:
        if current != previous + timedelta(days=1):
            ranges.append((start, previous))
            start = current
        previous = current
    ranges.append((start, previous))
    return tuple(ranges)
