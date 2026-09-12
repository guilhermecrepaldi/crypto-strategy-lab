"""Frozen dual native-tape validation and deterministic M035 event merge."""

from __future__ import annotations

import gzip
import hashlib
import heapq
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

from crypto_strategy_lab.microstructure.data import iter_archive
from crypto_strategy_lab.microstructure.tardis_l2 import iter_native_events, validate_raw_lines

START_US = 1_735_689_600_000_000
END_US = 1_735_700_400_000_000
SYMBOLS = ("USDCUSDT", "FDUSDUSDT")
OFFSETS = tuple(range(0, 180, 10))


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _raw_root(root: Path, symbol: str) -> Path:
    return root / "data/l2/tardis/binance" / symbol.lower() / "2025-01-01/raw"


def trade_path(root: Path, symbol: str) -> Path:
    nested = (
        root
        / "data/raw/binance-microstructure"
        / symbol
        / "trades/2025-01-01"
        / f"{symbol}-trades-2025-01-01.zip"
    )
    if nested.exists():
        return nested
    return (
        root
        / "data/raw/binance-microstructure"
        / symbol
        / "trades"
        / f"{symbol}-trades-2025-01-01.zip"
    )


def raw_lines(root: Path, symbol: str) -> Iterator[str]:
    for offset in OFFSETS:
        path = _raw_root(root, symbol) / f"{offset:04d}.ndjson.gz"
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            yield from stream


@lru_cache(maxsize=4)
def _usdc_slice_metadata(manifest_path: str) -> dict[int, dict[str, Any]]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    day = next(row for row in manifest["dates"] if row["date"] == "2025-01-01")
    return {int(row["offset"]): row for row in day["raw_slices"]}


def _slice_metadata(root: Path, symbol: str, offset: int) -> dict[str, Any]:
    path = _raw_root(root, symbol) / f"{offset:04d}.ndjson.gz"
    sidecar = path.with_name(path.name + ".meta.json")
    if sidecar.exists():
        return cast(dict[str, Any], json.loads(sidecar.read_text(encoding="utf-8")))
    if symbol != "USDCUSDT":
        raise ValueError(f"M035_RAW_SLICE_METADATA_MISSING:{symbol}:{offset}")
    manifest_path = (root / "data/manifests/usdcusdt-tardis-free-l2.json").resolve()
    return _usdc_slice_metadata(str(manifest_path))[offset]


def _validate_slice(root: Path, symbol: str, offset: int) -> dict[str, Any]:
    path = _raw_root(root, symbol) / f"{offset:04d}.ndjson.gz"
    metadata = _slice_metadata(root, symbol, offset)
    digest = file_sha256(path)
    url = urlparse(metadata["source_url"])
    params = parse_qs(url.query)
    filters = json.loads(params["filters"][0])
    if (
        metadata.get("status") not in {"AVAILABLE", "ORIGINAL_PRESENT"}
        or metadata.get("http_status") != 200
        or metadata.get("offset") != offset
        or metadata.get("sha256") != digest
        or metadata.get("bytes") != path.stat().st_size
        or url.scheme != "https"
        or url.netloc != "api.tardis.dev"
        or url.path != "/v1/data-feeds/binance"
        or params.get("from") != ["2025-01-01"]
        or params.get("offset") != [str(offset)]
        or params.get("sliceSize") != ["10"]
        or params.get("compression") != ["gzip"]
        or {item["channel"] for item in filters} != {"depth", "depthSnapshot", "trade"}
        or any(item["symbols"] != [symbol.lower()] for item in filters)
    ):
        raise ValueError(f"M035_RAW_SLICE_BINDING_FAILED:{symbol}:{offset}")
    headers = {str(key).lower(): str(value) for key, value in metadata["response_headers"].items()}
    if headers.get("x-slice-size") != "10":
        raise ValueError(f"M035_RAW_SLICE_HEADER_FAILED:{symbol}:{offset}")
    return {
        "offset": offset,
        "bytes": path.stat().st_size,
        "sha256": digest,
        "url": metadata["source_url"],
    }


def _verify_official_checksum(path: Path) -> str:
    sidecar = path.with_name(path.name + ".CHECKSUM")
    match = re.search(r"\b([0-9a-f]{64})\b", sidecar.read_text(encoding="ascii"), re.I)
    digest = file_sha256(path)
    if match is None or match.group(1).lower() != digest:
        raise ValueError("M035_OFFICIAL_TRADE_CHECKSUM_FAILED")
    return digest


def validate_pair(root: Path, symbol: str) -> dict[str, Any]:
    if symbol not in SYMBOLS:
        raise ValueError("M035_UNAUTHORIZED_PAIR")
    slices = [_validate_slice(root, symbol, offset) for offset in OFFSETS]
    raw = validate_raw_lines(raw_lines(root, symbol), expected_symbol=symbol)
    if raw["sequence_gate"] != "PASS":
        raise ValueError(f"M035_NATIVE_SEQUENCE_FAILED:{symbol}")
    projected = list(iter_native_events(raw_lines(root, symbol), expected_symbol=symbol))
    if not projected or any(
        event["symbol"] != symbol
        or not START_US <= int(event["local_us"]) < END_US
        or not START_US <= int(event["exchange_us"]) < END_US
        for event in projected
    ):
        raise ValueError(f"M035_NATIVE_WINDOW_FAILED:{symbol}")
    if any(event["kind"] == "BOOK" and not event["sequence_validated"] for event in projected):
        raise ValueError(f"M035_UNVALIDATED_BOOK_EXPOSED:{symbol}")
    archive_path = trade_path(root, symbol)
    archive_sha = _verify_official_checksum(archive_path)
    canonical = {
        record.trade_id: record
        for record in iter_archive(archive_path)
        if START_US <= int(record.timestamp.timestamp() * 1_000_000) < END_US
    }
    native = {
        int(event["data"]["t"]): event["data"] for event in projected if event["kind"] == "TRADE"
    }
    if set(canonical) != set(native):
        raise ValueError(f"M035_NATIVE_OFFICIAL_TRADE_IDS_FAILED:{symbol}")
    for trade_id, data in native.items():
        record = canonical[trade_id]
        if (
            record.price != Decimal(data["p"])
            or record.quantity != Decimal(data["q"])
            or record.buyer_is_maker is not data["m"]
            or int(record.timestamp.timestamp() * 1000) != data["T"]
        ):
            raise ValueError(f"M035_NATIVE_OFFICIAL_TRADE_FIELDS_FAILED:{symbol}:{trade_id}")
    payload = {
        "symbol": symbol,
        "venue": "BINANCE_SPOT",
        "start": "2025-01-01T00:00:00Z",
        "end_exclusive": "2025-01-01T03:00:00Z",
        "raw_slices": slices,
        "raw_validation": {
            key: raw[key]
            for key in (
                "sequence_gate",
                "counts",
                "first_local_timestamp",
                "last_local_timestamp",
                "last_update_id",
            )
        },
        "book_events": sum(event["kind"] == "BOOK" for event in projected),
        "trade_events": len(native),
        "all_books_sequence_validated": True,
        "official_trade_archive": {
            "path": archive_path.resolve().relative_to(root.resolve()).as_posix(),
            "sha256": archive_sha,
        },
        "native_official_trade_binding": "PASS",
    }
    payload["pair_data_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


def _checked_events(root: Path, symbol: str) -> Iterator[dict[str, Any]]:
    previous: tuple[int, int] | None = None
    for event in iter_native_events(raw_lines(root, symbol), expected_symbol=symbol):
        key = (int(event["local_us"]), int(event["capture_order"]))
        if previous is not None and key < previous:
            raise ValueError(f"M035_PAIR_EVENT_ORDER_REGRESSION:{symbol}")
        previous = key
        if START_US <= key[0] < END_US:
            yield event


def merged_events(root: Path, symbols: Iterable[str] = SYMBOLS) -> Iterator[dict[str, Any]]:
    selected = tuple(symbols)
    if not selected or any(symbol not in SYMBOLS for symbol in selected):
        raise ValueError("M035_INVALID_MERGE_SYMBOLS")
    order = {symbol: index for index, symbol in enumerate(SYMBOLS)}
    sources = [_checked_events(root, symbol) for symbol in selected]

    def key(event: Mapping[str, Any]) -> tuple[int, int, int, int]:
        return (
            int(event["local_us"]),
            int(event["exchange_us"]),
            order[str(event["symbol"])],
            int(event["capture_order"]),
        )

    previous: tuple[int, int, int, int] | None = None
    for event in heapq.merge(*sources, key=key):
        current = key(event)
        if previous is not None and current < previous:
            raise ValueError("M035_MERGED_EVENT_ORDER_REGRESSION")
        previous = current
        yield event


def validate_dual_tape(root: Path) -> dict[str, Any]:
    pairs = {symbol: validate_pair(root, symbol) for symbol in SYMBOLS}
    counts = {symbol: {"books": 0, "trades": 0} for symbol in SYMBOLS}
    events = 0
    for event in merged_events(root):
        counts[event["symbol"]]["books" if event["kind"] == "BOOK" else "trades"] += 1
        events += 1
    window = {
        "selection": "OWNER_ABSOLUTE_PREFERENCE_VALIDATED_NOT_PNL_SELECTED",
        "start_us": START_US,
        "end_us": END_US,
        "tie_break": "local_us,exchange_us,PAIR_A_before_PAIR_B,capture_order",
        "pair_hashes": {symbol: pairs[symbol]["pair_data_hash"] for symbol in SYMBOLS},
    }
    window_hash = hashlib.sha256(
        json.dumps(window, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "identity": "M035_DUAL_TAPE_2025_01_01_00_03_V1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "PASS",
        "pairs": pairs,
        "merged_event_counts": counts,
        "merged_events": events,
        "window": window,
        "window_hash": window_hash,
        "no_pnl_inspected": True,
    }
