"""Deterministic time-weighted trade-price occupancy for M020 geometry research."""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections import defaultdict
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any, Literal

from crypto_strategy_lab.microstructure.data import HistoryManifest, select_history_archives

MICROS_PER_SECOND = 1_000_000


@dataclass(frozen=True, slots=True)
class ArchiveOccupancy:
    path: str
    record_count: int
    first_timestamp_us: int
    first_price_ticks: int
    last_timestamp_us: int
    last_price_ticks: int
    minimum_price_ticks: int
    maximum_price_ticks: int
    duration_by_price_ticks: dict[int, int]


def _timestamp_us(raw: bytes) -> int:
    value = int(raw)
    return value if abs(value) >= 10**14 else value * 1_000


def _price_ticks(raw: bytes, decimals: int) -> int:
    text = raw.decode("ascii")
    whole, _dot, fraction = text.partition(".")
    sign = -1 if whole.startswith("-") else 1
    whole_value = abs(int(whole))
    padded = (fraction + ("0" * decimals))[:decimals]
    remainder = fraction[decimals:]
    if remainder and any(character != "0" for character in remainder):
        raise ValueError(f"price is not aligned to 1e-{decimals}: {text}")
    return int(sign * (whole_value * (10**decimals) + int(padded or "0")))


def _scan_archive(args: tuple[str, Literal["trades", "aggTrades"], int]) -> ArchiveOccupancy:
    path_text, kind, decimals = args
    path = Path(path_text)
    price_index = 1
    timestamp_index = 4 if kind == "trades" else 5
    duration_by_price: dict[int, int] = defaultdict(int)
    count = 0
    first_timestamp_us = first_price_ticks = 0
    previous_timestamp_us = previous_price_ticks = 0
    minimum_price_ticks: int | None = None
    maximum_price_ticks: int | None = None

    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"archive must contain exactly one CSV: {path}")
        with archive.open(names[0]) as stream:
            for line in stream:
                columns = line.rstrip(b"\r\n").split(b",")
                if not columns or columns[0].lower() in {b"id", b"aggtradeid", b"agg_trade_id"}:
                    continue
                timestamp_us = _timestamp_us(columns[timestamp_index])
                price_ticks = _price_ticks(columns[price_index], decimals)
                if count:
                    if timestamp_us < previous_timestamp_us:
                        raise ValueError(f"non-monotonic timestamps in {path}")
                    duration_by_price[previous_price_ticks] += timestamp_us - previous_timestamp_us
                else:
                    first_timestamp_us = timestamp_us
                    first_price_ticks = price_ticks
                previous_timestamp_us = timestamp_us
                previous_price_ticks = price_ticks
                minimum_price_ticks = (
                    price_ticks
                    if minimum_price_ticks is None
                    else min(minimum_price_ticks, price_ticks)
                )
                maximum_price_ticks = (
                    price_ticks
                    if maximum_price_ticks is None
                    else max(maximum_price_ticks, price_ticks)
                )
                count += 1

    if not count or minimum_price_ticks is None or maximum_price_ticks is None:
        raise ValueError(f"archive contains no trades: {path}")
    return ArchiveOccupancy(
        path=path_text,
        record_count=count,
        first_timestamp_us=first_timestamp_us,
        first_price_ticks=first_price_ticks,
        last_timestamp_us=previous_timestamp_us,
        last_price_ticks=previous_price_ticks,
        minimum_price_ticks=minimum_price_ticks,
        maximum_price_ticks=maximum_price_ticks,
        duration_by_price_ticks=dict(duration_by_price),
    )


def _datetime_us(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = value.astimezone(UTC) - epoch
    return (
        delta.days * 86_400 * MICROS_PER_SECOND
        + delta.seconds * MICROS_PER_SECOND
        + delta.microseconds
    )


def _format_price(ticks: int, decimals: int) -> str:
    scale = 10**decimals
    sign = "-" if ticks < 0 else ""
    absolute = abs(ticks)
    return f"{sign}{absolute // scale}.{absolute % scale:0{decimals}d}"


def narrowest_interval(
    duration_by_price_ticks: dict[int, int], fraction: Decimal
) -> dict[str, int | str]:
    if not (Decimal("0") < fraction <= Decimal("1")):
        raise ValueError("fraction must be in (0, 1]")
    levels = sorted(duration_by_price_ticks)
    total = sum(duration_by_price_ticks.values())
    if total <= 0 or not levels:
        raise ValueError("occupancy duration must be positive")
    target = int((Decimal(total) * fraction).to_integral_value(rounding=ROUND_CEILING))
    left = 0
    mass = 0
    best: tuple[int, int, int, int] | None = None
    for right, high in enumerate(levels):
        mass += duration_by_price_ticks[high]
        while left <= right and mass - duration_by_price_ticks[levels[left]] >= target:
            mass -= duration_by_price_ticks[levels[left]]
            left += 1
        if mass >= target:
            low = levels[left]
            candidate = (high - low, -mass, low, high)
            if best is None or candidate < best:
                best = candidate
    if best is None:
        raise ValueError("no occupancy interval reaches target")
    width, negative_mass, low, high = best
    covered = -negative_mass
    return {
        "fraction": str(fraction),
        "target_duration_us": target,
        "covered_duration_us": covered,
        "covered_fraction": str(Decimal(covered) / Decimal(total)),
        "low_ticks": low,
        "high_ticks": high,
        "width_ticks": width,
        "distinct_price_levels_inclusive": width + 1,
    }


def analyze_price_occupancy(
    manifest: HistoryManifest,
    *,
    start: datetime,
    end_exclusive: datetime,
    tick_decimals: int = 5,
    fractions: Iterable[Decimal] = (
        Decimal("0.80"),
        Decimal("0.90"),
        Decimal("0.95"),
        Decimal("0.99"),
    ),
    workers: int = 1,
) -> dict[str, Any]:
    selection_start = max(start, manifest.first_timestamp)
    selected = select_history_archives(manifest, start=selection_start, end_exclusive=end_exclusive)
    selected = tuple(sorted(selected, key=lambda item: item.first_timestamp))
    arguments = [(item.local_path, manifest.kind, tick_decimals) for item in selected]
    if workers == 1:
        scans = [_scan_archive(argument) for argument in arguments]
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            scans = list(executor.map(_scan_archive, arguments, chunksize=1))
    scans.sort(key=lambda item: item.first_timestamp_us)
    if len(scans) != len(selected):
        raise ValueError("archive scan count mismatch")
    for scan, authority in zip(scans, selected, strict=True):
        if Path(scan.path) != Path(authority.local_path):
            raise ValueError("archive scan order/path mismatch")
        if scan.record_count != authority.record_count:
            raise ValueError("archive record count differs from validated manifest")

    start_us = _datetime_us(start)
    end_us = _datetime_us(end_exclusive)
    duration_by_price: dict[int, int] = defaultdict(int)
    records = 0
    previous: ArchiveOccupancy | None = None
    minimum_price: int | None = None
    maximum_price: int | None = None
    for scan in scans:
        if scan.first_timestamp_us < start_us or scan.last_timestamp_us >= end_us:
            raise ValueError("selected archive scan escaped requested calendar interval")
        if previous is not None:
            if scan.first_timestamp_us < previous.last_timestamp_us:
                raise ValueError("archive scan timestamps overlap")
            duration_by_price[previous.last_price_ticks] += (
                scan.first_timestamp_us - previous.last_timestamp_us
            )
        for price_ticks, duration_us in scan.duration_by_price_ticks.items():
            duration_by_price[price_ticks] += duration_us
        records += scan.record_count
        minimum_price = (
            scan.minimum_price_ticks
            if minimum_price is None
            else min(minimum_price, scan.minimum_price_ticks)
        )
        maximum_price = (
            scan.maximum_price_ticks
            if maximum_price is None
            else max(maximum_price, scan.maximum_price_ticks)
        )
        previous = scan
    if previous is None or minimum_price is None or maximum_price is None:
        raise ValueError("no archive scans")
    duration_by_price[previous.last_price_ticks] += end_us - previous.last_timestamp_us
    known_start_us = scans[0].first_timestamp_us
    known_duration_us = sum(duration_by_price.values())
    expected_known_duration_us = end_us - known_start_us
    if known_duration_us != expected_known_duration_us:
        raise ValueError("time-weighted occupancy does not conserve the known interval")

    interval_results: dict[str, dict[str, int | str]] = {}
    for fraction in fractions:
        key = f"P{int(fraction * 100)}"
        interval = narrowest_interval(dict(duration_by_price), fraction)
        interval["low"] = _format_price(int(interval["low_ticks"]), tick_decimals)
        interval["high"] = _format_price(int(interval["high_ticks"]), tick_decimals)
        interval["width"] = _format_price(int(interval["width_ticks"]), tick_decimals)
        interval_results[key] = interval

    source_paths = [scan.path for scan in scans]
    source_binding = hashlib.sha256("\n".join(source_paths).encode("utf-8")).hexdigest()
    archive_authority_binding = hashlib.sha256(
        "\n".join(
            f"{item.utc_date.isoformat()}:{item.sha256}:{item.record_count}" for item in selected
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema": "PRICE_OCCUPANCY_2025_V1",
        "method": "LAST_CANONICAL_TRADE_PRICE_STEP_FUNCTION_TIME_WEIGHTED",
        "development_range_selection_uses_historical_occupancy": True,
        "out_of_sample": False,
        "interval_semantics": (
            "[start,end_exclusive); pre-first-trade time UNKNOWN; last trade held to end"
        ),
        "range_selection": "minimum width; ties maximum covered duration; then lower low",
        "start": start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "end_exclusive": end_exclusive.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "tick_size": _format_price(1, tick_decimals),
        "archive_count": len(scans),
        "record_count": records,
        "first_trade_timestamp_us": known_start_us,
        "last_trade_timestamp_us": previous.last_timestamp_us,
        "unknown_prefix_duration_us": known_start_us - start_us,
        "known_duration_us": known_duration_us,
        "requested_duration_us": end_us - start_us,
        "known_coverage_fraction": str(Decimal(known_duration_us) / Decimal(end_us - start_us)),
        "annual_low_ticks": minimum_price,
        "annual_high_ticks": maximum_price,
        "annual_low": _format_price(minimum_price, tick_decimals),
        "annual_high": _format_price(maximum_price, tick_decimals),
        "observed_price_level_count": len(duration_by_price),
        "ranges": interval_results,
        "source_path_list_sha256": source_binding,
        "history_manifest_dataset_hash": manifest.dataset_hash,
        "selected_archive_authority_sha256": archive_authority_binding,
        "source_paths": source_paths,
    }


def load_history_manifest(path: Path) -> HistoryManifest:
    return HistoryManifest.model_validate_json(path.read_text(encoding="utf-8"))


def write_occupancy(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
