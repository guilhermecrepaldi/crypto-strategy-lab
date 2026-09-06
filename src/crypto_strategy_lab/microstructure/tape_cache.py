"""Fail-closed, immutable NumPy cache for the canonical serial tape."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from crypto_strategy_lab.domain import canonical_hash, require_utc
from crypto_strategy_lab.microstructure.data import HistoryManifest
from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    SERIAL_TAPE_QUANTUM,
    USDCUSDT_TICK_CATALOG,
    SerialTape,
    TickCatalog,
    load_serial_tape,
)

CACHE_SCHEMA: Final = "usdcusdt-market-tape-v2"
_ARRAY_FILES: dict[str, tuple[str, str]] = {
    "events": ("events.npy", "<i8"),
    "price_ticks": ("price_ticks.npy", "<i4"),
    "occurrence_prices": ("occurrence_prices.npy", "<i4"),
    "occurrence_offsets": ("occurrence_offsets.npy", "<i8"),
    "occurrence_events": ("occurrence_events.npy", "<i8"),
}


class TapeCacheFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
    dtype: str
    shape: tuple[int, ...]


class TapeCacheManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["usdcusdt-market-tape-v2"] = CACHE_SCHEMA
    status: Literal["READY"] = "READY"
    dataset_hash: str
    tick_catalog_hash: str | None
    tick_source_policy: str
    tick_source_url: str | None
    start: datetime
    end_exclusive: datetime
    quantum: str
    records: int = Field(ge=1)
    observed_tick_evidence_event: int | None
    last_event: int
    last_price_tick: int
    files: dict[str, TapeCacheFile]
    total_size_bytes: int = Field(ge=0)
    build_time_seconds: float = Field(ge=0)
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    tape_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    memory_footprint_bytes: int = Field(ge=0)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class TapeCacheResult:
    tape: SerialTape
    manifest: TapeCacheManifest
    reused: bool


def tape_cache_identity(
    manifest: HistoryManifest,
    *,
    start: datetime,
    end_exclusive: datetime,
    quantum: Decimal = SERIAL_TAPE_QUANTUM,
    tick_catalog: TickCatalog | None = USDCUSDT_TICK_CATALOG,
    tick_source_policy: str = "CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
) -> dict[str, Any]:
    return {
        "schema_version": CACHE_SCHEMA,
        "dataset_hash": manifest.dataset_hash,
        "tick_catalog_hash": tick_catalog.catalog_hash if tick_catalog else None,
        "tick_source_policy": tick_source_policy,
        "tick_source_url": tick_catalog.source_url if tick_catalog else None,
        "start": require_utc(start),
        "end_exclusive": require_utc(end_exclusive),
        "quantum": str(quantum),
    }


def tape_cache_key(
    manifest: HistoryManifest,
    *,
    start: datetime,
    end_exclusive: datetime,
    quantum: Decimal = SERIAL_TAPE_QUANTUM,
    tick_catalog: TickCatalog | None = USDCUSDT_TICK_CATALOG,
    tick_source_policy: str = "CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
) -> str:
    return canonical_hash(
        tape_cache_identity(
            manifest,
            start=start,
            end_exclusive=end_exclusive,
            quantum=quantum,
            tick_catalog=tick_catalog,
            tick_source_policy=tick_source_policy,
        )
    )


def tape_cache_dir(cache_key: str, artifact_root: Path = Path("artifacts")) -> Path:
    if len(cache_key) != 64 or any(char not in "0123456789abcdef" for char in cache_key):
        raise ValueError("invalid tape cache key")
    return artifact_root / "usdcusdt" / "market-tape" / cache_key


def load_or_build_tape(
    manifest: HistoryManifest,
    *,
    start: datetime,
    end_exclusive: datetime,
    artifact_root: Path = Path("artifacts"),
    tick_size: Decimal = SERIAL_TAPE_QUANTUM,
    tick_catalog: TickCatalog | None = USDCUSDT_TICK_CATALOG,
    tick_source_policy: str = "CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
    raw_loader: Callable[[], SerialTape] | None = None,
    progress: Callable[[str, int], None] | None = None,
) -> TapeCacheResult:
    """Load a READY cache or build it once from the supplied canonical raw loader."""
    identity = tape_cache_identity(
        manifest,
        start=start,
        end_exclusive=end_exclusive,
        quantum=tick_size,
        tick_catalog=tick_catalog,
        tick_source_policy=tick_source_policy,
    )
    _validate_manifest_scope(
        manifest,
        start=start,
        end_exclusive=end_exclusive,
        quantum=tick_size,
        tick_catalog=tick_catalog,
    )
    expected_key = canonical_hash(identity)
    target = tape_cache_dir(expected_key, artifact_root)
    if target.exists():
        result = TapeCacheResult(
            tape=load_tape_cache(target, expected_identity=identity, tick_catalog=tick_catalog),
            manifest=TapeCacheManifest.model_validate_json(
                (target / "manifest.json").read_text(encoding="utf-8")
            ),
            reused=True,
        )
        _emit(progress, "MARKET_TAPE_READY", 100)
        return result
    _emit(progress, "PREPROCESS", 10)
    _emit(progress, "PREPROCESS", 25)
    loader = raw_loader or (
        lambda: load_serial_tape(
            manifest,
            tick_size=tick_size,
            start=start,
            end_exclusive=end_exclusive,
            tick_catalog=tick_catalog,
        )
    )
    begun = time.perf_counter()
    tape = loader()
    _emit(progress, "PREPROCESS", 50)
    built = _write_cache(
        tape,
        target=target,
        identity=identity,
        dataset_hash=manifest.dataset_hash,
        tick_catalog=tick_catalog,
        begun_at=begun,
    )
    _emit(progress, "PREPROCESS", 75)
    validated_tape = load_tape_cache(
        target,
        expected_identity=identity,
        tick_catalog=tick_catalog,
    )
    _emit(progress, "PREPROCESS", 100)
    _emit(progress, "MARKET_TAPE_READY", 100)
    return TapeCacheResult(
        tape=validated_tape,
        manifest=built,
        reused=False,
    )


def load_tape_cache(
    directory: Path,
    *,
    expected_identity: dict[str, Any] | None = None,
    tick_catalog: TickCatalog | None = None,
) -> SerialTape:
    manifest = TapeCacheManifest.model_validate_json(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )
    if manifest.status != "READY":
        raise ValueError("tape cache is not READY")
    identity = {
        key: getattr(manifest, key)
        for key in (
            "schema_version",
            "dataset_hash",
            "tick_catalog_hash",
            "tick_source_policy",
            "tick_source_url",
            "start",
            "end_exclusive",
            "quantum",
        )
    }
    identity["start"] = manifest.start.isoformat()
    identity["end_exclusive"] = manifest.end_exclusive.isoformat()
    cache_key = canonical_hash(identity)
    if manifest.cache_key != cache_key or directory.name != cache_key:
        raise ValueError("tape cache key does not match its identity or directory")
    if expected_identity is not None:
        expected_json = {
            key: (
                value.isoformat()
                if isinstance(value, datetime)
                else str(value)
                if isinstance(value, Decimal)
                else value
            )
            for key, value in expected_identity.items()
        }
        if canonical_hash(identity) != canonical_hash(expected_json):
            raise ValueError("tape cache identity mismatch")
    if set(manifest.files) != set(_ARRAY_FILES):
        raise ValueError("tape cache manifest has an unexpected file set")
    arrays: dict[str, np.ndarray] = {}
    for key, (filename, dtype) in _ARRAY_FILES.items():
        descriptor = manifest.files.get(key)
        if descriptor is None:
            raise ValueError(f"tape cache manifest omits {key}")
        path = directory / filename
        if not path.is_file() or path.stat().st_size != descriptor.size:
            raise ValueError(f"tape cache file {filename} has unexpected size")
        if _sha256(path) != descriptor.sha256:
            raise ValueError(f"tape cache file {filename} failed SHA256 validation")
        array_value = np.load(path, mmap_mode="r", allow_pickle=False)
        if array_value.dtype.str != dtype or tuple(array_value.shape) != descriptor.shape:
            raise ValueError(f"tape cache file {filename} has unexpected dtype or shape")
        arrays[key] = array_value
    content_hash = _content_hash(manifest.files)
    if content_hash != manifest.content_hash:
        raise ValueError("tape cache content hash validation failed")
    expected_tape_hash = _semantic_tape_hash(
        identity,
        records=manifest.records,
        observed_tick_evidence_event=manifest.observed_tick_evidence_event,
        last_event=manifest.last_event,
        last_price_tick=manifest.last_price_tick,
        content_hash=content_hash,
    )
    if manifest.tape_hash != expected_tape_hash:
        raise ValueError("tape hash does not bind the cache semantics")
    events = arrays["events"]
    prices = arrays["price_ticks"]
    if len(events) != manifest.records or len(prices) != manifest.records:
        raise ValueError("tape cache record count is inconsistent")
    if len(events) == 0 or np.any(events[1:] <= events[:-1]):
        raise ValueError("tape cache events are not strictly chronological")
    if int(events[-1]) != manifest.last_event or int(prices[-1]) != manifest.last_price_tick:
        raise ValueError("tape cache last-event provenance is inconsistent")
    if manifest.observed_tick_evidence_event is not None and not np.any(
        events == manifest.observed_tick_evidence_event
    ):
        raise ValueError("tape cache observed tick evidence is inconsistent")
    occurrence_prices = arrays["occurrence_prices"]
    offsets = arrays["occurrence_offsets"]
    occurrence_events = arrays["occurrence_events"]
    if len(offsets) != len(occurrence_prices) + 1 or int(offsets[-1]) != len(occurrence_events):
        raise ValueError("tape cache occurrence offsets are inconsistent")
    if np.any(offsets[1:] < offsets[:-1]) or np.any(offsets < 0):
        raise ValueError("tape cache occurrences are malformed")
    if np.any(occurrence_prices[1:] <= occurrence_prices[:-1]):
        raise ValueError("tape cache occurrence prices are not strictly ordered")
    occurrences = {
        int(price): occurrence_events[int(offsets[index]) : int(offsets[index + 1])]
        for index, price in enumerate(occurrence_prices)
    }
    if sum(len(value) for value in occurrences.values()) != manifest.records:
        raise ValueError("tape cache occurrence records are inconsistent")
    for price, occurrence in occurrences.items():
        if np.any(occurrence[1:] <= occurrence[:-1]):
            raise ValueError("tape cache occurrence events are not ordered")
        for offset in range(0, len(occurrence), 1_000_000):
            chunk = occurrence[offset : offset + 1_000_000]
            indexes = np.searchsorted(events, chunk)
            if np.any(indexes >= len(events)) or not np.array_equal(events[indexes], chunk):
                raise ValueError("tape cache occurrence event is not in chronological tape")
            if np.any(prices[indexes] != price):
                raise ValueError("tape cache occurrence price does not match price_ticks")
    if tick_catalog is not None:
        expected_evidence = _first_observed_tick_evidence(
            events, prices, Decimal(manifest.quantum), tick_catalog
        )
        if expected_evidence != manifest.observed_tick_evidence_event:
            raise ValueError("tape cache evidence is not the first eligible event")
    return SerialTape(
        Decimal(manifest.quantum),
        occurrences,
        events,
        prices,
        int(events[-1]),
        int(prices[-1]),
        manifest.observed_tick_evidence_event,
        manifest.tape_hash,
        manifest.cache_key,
    )


def _write_cache(
    tape: SerialTape,
    *,
    target: Path,
    identity: dict[str, Any],
    dataset_hash: str,
    tick_catalog: TickCatalog | None,
    begun_at: float,
) -> TapeCacheManifest:
    if tape.tick_size != Decimal(identity["quantum"]):
        raise ValueError("tape quantum does not match cache identity")
    events = np.asarray(tape.events, dtype="<i8")
    prices = np.asarray(tape.price_ticks, dtype="<i4")
    occurrence_prices = np.asarray(sorted(tape.occurrences), dtype="<i4")
    offsets = np.zeros(len(occurrence_prices) + 1, dtype="<i8")
    occurrence_events = np.empty(
        sum(len(tape.occurrences[int(item)]) for item in occurrence_prices), dtype="<i8"
    )
    cursor = 0
    for index, price in enumerate(occurrence_prices):
        values = np.asarray(tape.occurrences[int(price)], dtype="<i8")
        occurrence_events[cursor : cursor + len(values)] = values
        cursor += len(values)
        offsets[index + 1] = cursor
    arrays = {
        "events": events,
        "price_ticks": prices,
        "occurrence_prices": occurrence_prices,
        "occurrence_offsets": offsets,
        "occurrence_events": occurrence_events,
    }
    cache_key = canonical_hash(identity)
    temp = target.parent / f".{target.name}.{os.getpid()}.building"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)
    descriptors: dict[str, TapeCacheFile] = {}
    try:
        (temp / "build-state.json").write_text(
            json.dumps({"status": "BUILDING", "cache_key": cache_key}) + "\n",
            encoding="utf-8",
        )
        for key, (filename, _dtype) in _ARRAY_FILES.items():
            path = temp / filename
            np.save(path, arrays[key], allow_pickle=False)
            descriptors[key] = TapeCacheFile(
                sha256=_sha256(path),
                size=path.stat().st_size,
                dtype=arrays[key].dtype.str,
                shape=tuple(arrays[key].shape),
            )
        total_size = sum(item.size for item in descriptors.values())
        content_hash = _content_hash(descriptors)
        tape_hash = _semantic_tape_hash(
            identity,
            records=len(events),
            observed_tick_evidence_event=tape.observed_tick_evidence_event,
            last_event=int(events[-1]),
            last_price_tick=int(prices[-1]),
            content_hash=content_hash,
        )
        ready = TapeCacheManifest(
            dataset_hash=dataset_hash,
            tick_catalog_hash=identity["tick_catalog_hash"],
            tick_source_policy=identity["tick_source_policy"],
            tick_source_url=identity["tick_source_url"],
            start=identity["start"],
            end_exclusive=identity["end_exclusive"],
            quantum=identity["quantum"],
            records=len(events),
            observed_tick_evidence_event=tape.observed_tick_evidence_event,
            last_event=int(events[-1]),
            last_price_tick=int(prices[-1]),
            files=descriptors,
            total_size_bytes=total_size,
            build_time_seconds=time.perf_counter() - begun_at,
            cache_key=cache_key,
            tape_hash=tape_hash,
            memory_footprint_bytes=sum(int(item.nbytes) for item in arrays.values()),
            content_hash=content_hash,
        )
        (temp / "manifest.json").write_text(
            ready.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        (temp / "build-state.json").write_text(
            json.dumps({"status": "READY", "cache_key": cache_key, "tape_hash": tape_hash}) + "\n",
            encoding="utf-8",
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.rename(temp, target)
        except FileExistsError:
            shutil.rmtree(temp)
            load_tape_cache(target, expected_identity=identity, tick_catalog=tick_catalog)
            return TapeCacheManifest.model_validate_json(
                (target / "manifest.json").read_text(encoding="utf-8")
            )
        return ready
    except Exception:
        if temp.exists():
            shutil.rmtree(temp)
        raise


def _emit(progress: Callable[[str, int], None] | None, milestone: str, percent: int) -> None:
    if progress is not None:
        progress(milestone, percent)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_manifest_scope(
    manifest: HistoryManifest,
    *,
    start: datetime,
    end_exclusive: datetime,
    quantum: Decimal,
    tick_catalog: TickCatalog | None,
) -> None:
    start = require_utc(start)
    end_exclusive = require_utc(end_exclusive)
    if manifest.symbol != "USDCUSDT" or manifest.kind != "trades":
        raise ValueError("tape cache accepts only USDCUSDT trades")
    if manifest.integrity_status != "VALID" or manifest.invalidity_reasons:
        raise ValueError("tape cache requires a VALID history manifest")
    if start >= end_exclusive:
        raise ValueError("tape cache interval must be positive")
    if start < require_utc(manifest.first_timestamp):
        raise ValueError("tape cache interval precedes validated history")
    if end_exclusive > require_utc(manifest.last_timestamp) + timedelta(microseconds=1):
        raise ValueError("tape cache interval exceeds validated history")
    if tick_catalog is not None:
        tick_catalog.validate_interval(start, end_exclusive)
        if tick_catalog.price_quantum != quantum:
            raise ValueError("tape cache quantum does not match tick catalog")


def _first_observed_tick_evidence(
    events: Any,
    prices: Any,
    quantum: Decimal,
    tick_catalog: TickCatalog,
) -> int | None:
    for transition in tick_catalog.transitions:
        start_event = _datetime_to_event(transition.start)
        end_event = _datetime_to_event(transition.end_exclusive)
        start_index = int(np.searchsorted(events, start_event, side="left"))
        end_index = int(np.searchsorted(events, end_event, side="left"))
        scheduled = tick_catalog.tick_size_at(transition.start)
        multiple = scheduled / quantum
        if multiple != multiple.to_integral_value():
            raise ValueError("scheduled tick is not representable on tape quantum")
        divisor = int(multiple)
        for offset in range(start_index, end_index, 1_000_000):
            chunk = prices[offset : min(offset + 1_000_000, end_index)]
            mismatches = np.flatnonzero(chunk % divisor)
            if len(mismatches):
                return int(events[offset + int(mismatches[0])])
    return None


def _datetime_to_event(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = require_utc(value) - epoch
    micros = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    return micros * EVENT_ORDER_SCALE


def _content_hash(files: dict[str, TapeCacheFile]) -> str:
    return canonical_hash({key: files[key].model_dump(mode="json") for key in sorted(_ARRAY_FILES)})


def _semantic_tape_hash(
    identity: dict[str, Any],
    *,
    records: int,
    observed_tick_evidence_event: int | None,
    last_event: int,
    last_price_tick: int,
    content_hash: str,
) -> str:
    return canonical_hash(
        {
            "identity": identity,
            "records": records,
            "observed_tick_evidence_event": observed_tick_evidence_event,
            "last_event": last_event,
            "last_price_tick": last_price_tick,
            "content_hash": content_hash,
        }
    )


__all__ = [
    "CACHE_SCHEMA",
    "TapeCacheFile",
    "TapeCacheManifest",
    "TapeCacheResult",
    "load_or_build_tape",
    "load_tape_cache",
    "tape_cache_dir",
    "tape_cache_identity",
    "tape_cache_key",
]
