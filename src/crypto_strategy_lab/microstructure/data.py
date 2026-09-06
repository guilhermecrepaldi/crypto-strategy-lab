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
    cross_archive_gaps: tuple[tuple[int, int], ...]
    cross_archive_overlaps: tuple[tuple[int, int], ...]
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
            price=_decimal(price),
            quantity=_decimal(quantity),
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
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == checksum:
        checksum_path.write_bytes(checksum_bytes)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = _read_url(url)
    if hashlib.sha256(data).hexdigest() != checksum:
        raise MicrostructureIntegrityError("download checksum mismatch")
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix=f".{destination.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    temporary.replace(destination)
    checksum_path.write_bytes(checksum_bytes)
    return destination


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
) -> MicrostructureManifest:
    if not events:
        raise MicrostructureIntegrityError("archive contains no trade events")
    gaps, duplicates = validate_events(events)
    archive_path = Path(path)
    archive_timestamp_unit = timestamp_unit or timestamp_unit_for_archive(archive_path, kind)
    try:
        utc_date = date.fromisoformat(period)
    except ValueError:
        # Offline fixtures may use a descriptive period label; derive the
        # represented UTC day from the parsed events while retaining the
        # strict single-day integrity check below.
        utc_date = events[0].timestamp.date()
    if any(event.timestamp.date() != utc_date for event in events):
        raise MicrostructureIntegrityError(
            f"archive {archive_path} contains timestamps outside {utc_date.isoformat()}"
        )
    day_start = datetime.combine(utc_date, time.min, tzinfo=UTC)
    day_end = datetime.combine(utc_date, time.max, tzinfo=UTC)
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
        sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        record_count=len(events),
        first_timestamp=events[0].timestamp,
        last_timestamp=events[-1].timestamp,
        first_trade_id=events[0].trade_id,
        last_trade_id=events[-1].trade_id,
        gaps=gaps,
        duplicates=duplicates,
        timestamp_unit=archive_timestamp_unit,
        first_event_offset_seconds=_seconds(events[0].timestamp - day_start),
        last_event_before_day_end_seconds=_seconds(day_end - events[-1].timestamp),
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
        events = parse_archive(path, kind)
        return manifest_for(
            path,
            events,
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
    selected = tuple(item for item in manifest.archives if start <= item.utc_date <= end)
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
    ordered = tuple(sorted(manifests, key=lambda item: item.utc_date))
    expected_dates = {
        requested_start + timedelta(days=offset)
        for offset in range((requested_end - requested_start).days + 1)
    }
    present_dates = {item.utc_date for item in ordered}
    missing_dates = tuple(sorted(expected_dates - present_dates))
    missing_date_ranges = _date_ranges(missing_dates)
    cross_gaps: list[tuple[int, int]] = []
    overlaps: list[tuple[int, int]] = []
    for previous, current in pairwise(ordered):
        if current.first_trade_id <= previous.last_trade_id:
            overlaps.append((previous.last_trade_id, current.first_trade_id))
        elif current.first_trade_id > previous.last_trade_id + 1:
            cross_gaps.append((previous.last_trade_id, current.first_trade_id))
    invalidity_reasons: list[str] = []
    if missing_dates:
        invalidity_reasons.append("missing_requested_dates")
    if cross_gaps:
        invalidity_reasons.append("cross_archive_id_gaps")
    if overlaps:
        invalidity_reasons.append("cross_archive_id_overlaps")
    if any(item.gaps for item in ordered):
        invalidity_reasons.append("within_archive_id_gaps")
    if any(item.duplicates for item in ordered):
        invalidity_reasons.append("within_archive_duplicate_ids")
    integrity: Literal["VALID", "INVALID"] = "VALID" if not invalidity_reasons else "INVALID"
    dataset_hash = canonical_hash(
        [
            {
                "utc_date": item.utc_date,
                "sha256": item.sha256,
                "record_count": item.record_count,
            }
            for item in ordered
        ]
    )
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
        cross_archive_gaps=tuple(cross_gaps),
        cross_archive_overlaps=tuple(overlaps),
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
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected.sha256:
            raise MicrostructureIntegrityError(f"hash changed for {path}")
        events = parse_archive(path, manifest.kind)
        actual = manifest_for(
            path,
            events,
            origin=expected.origin,
            period=expected.utc_date.isoformat(),
            symbol=manifest.symbol,
            kind=manifest.kind,
        )
        comparable_fields = [
            "symbol",
            "kind",
            "utc_date",
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
        rebuilt.append(
            {
                "utc_date": actual.utc_date,
                "sha256": actual.sha256,
                "record_count": actual.record_count,
            }
        )
        previous = actual
    if canonical_hash(rebuilt) != manifest.dataset_hash:
        raise MicrostructureIntegrityError("consolidated dataset hash mismatch")
    expected_dates = {
        manifest.requested_start + timedelta(days=offset)
        for offset in range((manifest.requested_end - manifest.requested_start).days + 1)
    }
    present_dates = {item.utc_date for item in manifest.archives}
    missing_dates = tuple(sorted(expected_dates - present_dates))
    if missing_dates != manifest.missing_dates:
        raise MicrostructureIntegrityError("missing date metadata changed")
    if (
        "missing_date_ranges" in manifest.model_fields_set
        and _date_ranges(missing_dates) != manifest.missing_date_ranges
    ):
        raise MicrostructureIntegrityError("missing date range metadata changed")
    if manifest.integrity_status != "VALID":
        raise MicrostructureIntegrityError("history manifest is not valid")


def _archive_date(key: str) -> date:
    match = re.search(r"(\d{4}-\d{2}-\d{2})\.zip$", key)
    if match is None:
        raise MicrostructureIntegrityError(f"unrecognized daily archive key {key}")
    return date.fromisoformat(match.group(1))


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
