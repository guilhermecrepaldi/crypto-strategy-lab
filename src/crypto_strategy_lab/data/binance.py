from __future__ import annotations

import csv
import hashlib
import io
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from crypto_strategy_lab.domain import FIVE_MINUTES, Candle, require_utc

BINANCE_ARCHIVE_ROOT = "https://data.binance.vision/data/spot"


class DatasetIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class DownloadManifest:
    source_url: str
    local_path: Path
    sha256: str
    size_bytes: int
    ingested_at: datetime
    status: str = "VERIFIED"


def monthly_kline_url(symbol: str, year: int, month: int, interval: str = "5m") -> str:
    normalized = symbol.upper()
    filename = f"{normalized}-{interval}-{year:04d}-{month:02d}.zip"
    return f"{BINANCE_ARCHIVE_ROOT}/monthly/klines/{normalized}/{interval}/{filename}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "crypto-strategy-lab/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return cast(bytes, response.read())


def download_verified_archive(url: str, destination: Path) -> DownloadManifest:
    """Download an official archive exactly once and verify its published checksum."""
    destination.mkdir(parents=True, exist_ok=True)
    filename = url.rsplit("/", 1)[-1]
    target = destination / filename
    checksum_bytes = _read_url(f"{url}.CHECKSUM")
    expected = checksum_bytes.decode("ascii").strip().split()[0].lower()
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise DatasetIntegrityError("invalid checksum document")

    if target.exists() and _sha256(target) == expected:
        (destination / f"{filename}.CHECKSUM").write_bytes(checksum_bytes)
        return DownloadManifest(url, target, expected, target.stat().st_size, datetime.now(UTC))

    quarantine = destination / "quarantine"
    quarantine.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination, suffix=".part", delete=False) as temp:
        temp_path = Path(temp.name)
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "crypto-strategy-lab/0.1"}),
            timeout=120,
        ) as response:
            shutil.copyfileobj(response, temp)
    actual = _sha256(temp_path)
    if actual != expected:
        quarantined = quarantine / f"{filename}.{actual}.invalid"
        temp_path.replace(quarantined)
        raise DatasetIntegrityError(
            f"checksum mismatch: expected {expected}, got {actual}; quarantined at {quarantined}"
        )
    temp_path.replace(target)
    (destination / f"{filename}.CHECKSUM").write_bytes(checksum_bytes)
    return DownloadManifest(url, target, actual, target.stat().st_size, datetime.now(UTC))


def epoch_to_utc(raw: str) -> datetime:
    value = int(raw)
    divisor = 1_000_000 if abs(value) >= 1_000_000_000_000_000 else 1_000
    whole_seconds, remainder = divmod(value, divisor)
    microseconds = remainder if divisor == 1_000_000 else remainder * 1_000
    return datetime.fromtimestamp(whole_seconds, tz=UTC) + timedelta(microseconds=microseconds)


def parse_kline_archive(
    path: Path,
    symbol: str,
    *,
    not_after: datetime | None = None,
) -> list[Candle]:
    """Parse a Binance 5m archive without binary floating-point conversions."""
    limit = require_utc(not_after) if not_after else None
    with zipfile.ZipFile(path) as archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        if len(members) != 1 or Path(members[0].filename).name != members[0].filename:
            raise DatasetIntegrityError("archive must contain exactly one root-level CSV")
        with archive.open(members[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            candles: list[Candle] = []
            for row_number, row in enumerate(reader, start=1):
                if not row:
                    continue
                try:
                    open_time = epoch_to_utc(row[0])
                except (ValueError, OverflowError, OSError, InvalidOperation):
                    if row_number == 1:
                        continue
                    raise DatasetIntegrityError(f"invalid timestamp at row {row_number}") from None
                if len(row) < 11:
                    raise DatasetIntegrityError(f"incomplete kline row {row_number}")
                close_time = epoch_to_utc(row[6])
                available_at = close_time
                if limit is not None and available_at > limit:
                    raise DatasetIntegrityError(f"future candle at row {row_number}")
                try:
                    candles.append(
                        Candle(
                            symbol=symbol.upper(),
                            open_time=open_time,
                            close_time=close_time,
                            available_at=available_at,
                            open=Decimal(row[1]),
                            high=Decimal(row[2]),
                            low=Decimal(row[3]),
                            close=Decimal(row[4]),
                            volume=Decimal(row[5]),
                            quote_asset_volume=Decimal(row[7]),
                            trade_count=int(row[8]),
                        )
                    )
                except (InvalidOperation, ValueError) as error:
                    raise DatasetIntegrityError(
                        f"invalid kline row {row_number}: {error}"
                    ) from error
    validate_candle_sequence(candles)
    return candles


def validate_candle_sequence(candles: list[Candle]) -> list[tuple[datetime, datetime]]:
    if not candles:
        raise DatasetIntegrityError("dataset is empty")
    seen: set[tuple[str, datetime]] = set()
    gaps: list[tuple[datetime, datetime]] = []
    previous_by_symbol: dict[str, Candle] = {}
    for candle in candles:
        key = (candle.symbol, candle.open_time)
        if key in seen:
            raise DatasetIntegrityError(f"duplicate candle {candle.symbol} {candle.open_time}")
        seen.add(key)
        previous = previous_by_symbol.get(candle.symbol)
        if previous is not None:
            if candle.open_time <= previous.open_time:
                raise DatasetIntegrityError("candles are out of order")
            expected = previous.open_time + FIVE_MINUTES
            if candle.open_time != expected:
                gaps.append((expected, candle.open_time))
        previous_by_symbol[candle.symbol] = candle
    return gaps
