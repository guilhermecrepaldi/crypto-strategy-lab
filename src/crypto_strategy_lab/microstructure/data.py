from __future__ import annotations

import csv
import hashlib
import io
import tempfile
import urllib.request
import zipfile
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from crypto_strategy_lab.microstructure.models import TradeEvent


class MicrostructureIntegrityError(ValueError):
    """Archive content is malformed or fails sequence integrity checks."""


class MicrostructureManifest(BaseModel):
    model_config = ConfigDict(frozen=True)
    origin: str
    period: str
    sha256: str
    record_count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    gaps: list[tuple[int, int]]
    duplicates: list[int]


def _timestamp(value: str) -> datetime:
    try:
        integer = int(value)
    except ValueError as exc:
        raise MicrostructureIntegrityError(f"invalid timestamp: {value!r}") from exc
    # Binance switched archive timestamps from milliseconds to microseconds in 2025.
    scale = 1_000_000 if abs(integer) >= 10**14 else 1_000
    seconds, remainder = divmod(integer, scale)
    micros = remainder * (1_000_000 // scale)
    return datetime.fromtimestamp(seconds, UTC).replace(microsecond=micros)


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise MicrostructureIntegrityError(f"invalid decimal: {value!r}") from exc


def parse_archive(
    path: str | Path, kind: Literal["trades", "aggTrades"] = "trades"
) -> list[TradeEvent]:
    """Parse one official Binance Spot ZIP archive without converting numbers to float."""
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if not n.endswith("/")]
        if len(names) != 1:
            raise MicrostructureIntegrityError("archive must contain exactly one CSV")
        text = io.TextIOWrapper(archive.open(names[0]), encoding="utf-8", newline="")
        rows = csv.reader(text)
        events: list[TradeEvent] = []
        for row in rows:
            if not row or not row[0].lstrip("-").isdigit():
                continue
            try:
                if kind == "trades":
                    event_id, price, quantity, _, stamp, maker = row[:6]
                    last_id = int(event_id)
                else:
                    event_id, price, quantity, _first, last, stamp, maker = row[:7]
                    last_id = int(last)
                events.append(
                    TradeEvent(
                        trade_id=int(event_id),
                        price=_decimal(price),
                        quantity=_decimal(quantity),
                        timestamp=_timestamp(stamp),
                        buyer_is_maker=maker.strip().lower() == "true",
                        sequence=last_id,
                    )
                )
            except (ValueError, IndexError) as exc:
                raise MicrostructureIntegrityError(f"invalid row in {path}: {row!r}") from exc
    return events


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
    checksum = checksum_bytes.decode("ascii").split()[0].lower()
    if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
        raise MicrostructureIntegrityError("invalid SHA256 checksum")
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
    path: str | Path, events: list[TradeEvent], *, origin: str, period: str
) -> MicrostructureManifest:
    if not events:
        raise MicrostructureIntegrityError("archive contains no trade events")
    gaps, duplicates = validate_events(events)
    timestamps = [event.timestamp for event in events]
    return MicrostructureManifest(
        origin=origin,
        period=period,
        sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        record_count=len(events),
        first_timestamp=min(timestamps) if timestamps else None,
        last_timestamp=max(timestamps) if timestamps else None,
        gaps=gaps,
        duplicates=duplicates,
    )
