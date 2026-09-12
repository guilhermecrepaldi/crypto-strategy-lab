"""Forward-only Binance evidence capture for the M035 two-pair data gate.

This module records public market evidence only.  It has no account, order,
capital, strategy, fill, or replay interface.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from base64 import b64encode
from collections import Counter
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .public_calibration import BookGap, LocalDepth, validate_public_trade

CAPTURE_IDENTITY = "M035_DUAL_PAIR_FORWARD_CAPTURE_V1"
CAPTURE_SYMBOLS = ("USDCUSDT", "FDUSDUSDT")
CAPTURE_DURATION_SECONDS = 10_800
DEPTH_INTERVAL_MS = 100
SNAPSHOT_LIMIT = 5_000
MAX_STARTUP_SECONDS = 120
MAX_STREAM_SILENCE_SECONDS = 10
MAX_PAIR_STREAM_GAP_SECONDS = 10


class M035CaptureError(RuntimeError):
    """Capture is unsafe, incomplete, or physically discontinuous."""


class PublicClient(Protocol):
    def exchange_info(self, symbol: str) -> dict[str, Any]: ...

    def depth_snapshot(self, symbol: str, *, limit: int = 5000) -> dict[str, Any]: ...


class StreamConnection(Protocol):
    def recv(self, timeout: float | None = None) -> str | bytes: ...


class StreamFactory(Protocol):
    def __call__(
        self, symbols: tuple[str, ...]
    ) -> AbstractContextManager[StreamConnection]: ...


@dataclass
class PairCaptureState:
    symbol: str
    book: LocalDepth = field(init=False)
    last_trade_id: int | None = None
    last_trade_time_us: int | None = None
    last_depth_time_us: int | None = None
    trade_count: int = 0
    depth_count: int = 0
    last_received_by_type: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.book = LocalDepth(self.symbol)

    @property
    def ready(self) -> bool:
        return self.book.valid and self.trade_count > 0


def frozen_capture_spec() -> dict[str, Any]:
    """Return the preregistered, non-economic capture specification."""
    return {
        "identity": CAPTURE_IDENTITY,
        "venue": "BINANCE",
        "symbols": list(CAPTURE_SYMBOLS),
        "streams": ["trade", "depth@100ms"],
        "trade_semantics": "INDIVIDUAL_PUBLIC_TRADE_NOT_AGGTRADE",
        "depth_semantics": "L2_SNAPSHOT_PLUS_ABSOLUTE_DIFFS",
        "duration_seconds": CAPTURE_DURATION_SECONDS,
        "depth_interval_ms": DEPTH_INTERVAL_MS,
        "snapshot_limit": SNAPSHOT_LIMIT,
        "max_startup_seconds": MAX_STARTUP_SECONDS,
        "max_stream_silence_seconds": MAX_STREAM_SILENCE_SECONDS,
        "max_pair_stream_gap_seconds": MAX_PAIR_STREAM_GAP_SECONDS,
        "window_selection": "FIRST_PUBLISHED_SOURCE_RUN_NO_PNL_SELECTION",
        "economic_actions": False,
        "account_access": False,
        "kraken": "RETIRED_DISABLED",
    }


def capture_spec_hash() -> str:
    encoded = json.dumps(frozen_capture_spec(), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _event_time_us(data: dict[str, Any]) -> int:
    value = data.get("T", data.get("E"))
    if type(value) is not int or value <= 0:
        raise M035CaptureError("INVALID_EVENT_TIMESTAMP")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class DualPairForwardCapture:
    """Capture one simultaneous physical window for both M035 pairs."""

    def __init__(
        self,
        *,
        public_client: PublicClient,
        stream_factory: StreamFactory,
        source_sha: str,
        wall_time_us: Callable[[], int] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
    ) -> None:
        if len(source_sha) != 40 or any(c not in "0123456789abcdef" for c in source_sha):
            raise M035CaptureError("PUBLISHED_SOURCE_SHA_REQUIRED")
        self.public_client = public_client
        self.stream_factory = stream_factory
        self.source_sha = source_sha
        self.wall_time_us = wall_time_us or (lambda: time.time_ns() // 1000)
        self.monotonic_ns = monotonic_ns or time.monotonic_ns
        self.states = {symbol: PairCaptureState(symbol) for symbol in CAPTURE_SYMBOLS}
        self.counts: Counter[str] = Counter()
        self.window_counts: Counter[str] = Counter()
        self.coverage_origin_ns: dict[str, int] = {}
        self.coverage_first_ns: dict[str, int] = {}
        self.coverage_last_ns: dict[str, int] = {}
        self.coverage_max_gap_ns: Counter[str] = Counter()

    def _validate_exchange_info(self, symbol: str, payload: dict[str, Any]) -> None:
        rows = payload.get("symbols")
        if not isinstance(rows, list) or len(rows) != 1:
            raise M035CaptureError(f"{symbol}_INVALID_EXCHANGE_INFO")
        row = rows[0]
        if row.get("symbol") != symbol or row.get("status") != "TRADING":
            raise M035CaptureError(f"{symbol}_NOT_TRADING")
        filters = row.get("filters")
        if not isinstance(filters, list):
            raise M035CaptureError(f"{symbol}_RULES_MISSING")
        filter_types = {item.get("filterType") for item in filters if isinstance(item, dict)}
        if not {"PRICE_FILTER", "LOT_SIZE"}.issubset(filter_types):
            raise M035CaptureError(f"{symbol}_RULES_INSUFFICIENT")

    def _apply(self, data: dict[str, Any], *, received_mono_ns: int) -> tuple[str, int, str]:
        symbol = data.get("s")
        if symbol not in self.states:
            raise M035CaptureError("UNEXPECTED_SYMBOL")
        state = self.states[symbol]
        event_time_us = _event_time_us(data)
        kind = data.get("e")
        if kind == "trade":
            previous_id = state.last_trade_id
            try:
                trade_id = validate_public_trade(
                    data, last_trade_id=previous_id, expected_symbol=symbol
                )
            except ValueError as exc:
                raise M035CaptureError(f"{symbol}_{exc}") from exc
            if previous_id is not None and trade_id != previous_id + 1:
                raise M035CaptureError(f"{symbol}_TRADE_SEQUENCE_GAP")
            if state.last_trade_time_us is not None and event_time_us < state.last_trade_time_us:
                raise M035CaptureError(f"{symbol}_TRADE_TIMESTAMP_REGRESSION")
            state.last_trade_id = trade_id
            state.last_trade_time_us = event_time_us
            state.trade_count += 1
            state.last_received_by_type["trade"] = received_mono_ns
            self.counts[f"{symbol}:trade"] += 1
        elif kind == "depthUpdate":
            if state.last_depth_time_us is not None and event_time_us < state.last_depth_time_us:
                raise M035CaptureError(f"{symbol}_DEPTH_TIMESTAMP_REGRESSION")
            already_valid = state.book.valid
            try:
                applied = state.book.apply(data)
            except (BookGap, KeyError, TypeError, ValueError) as exc:
                raise M035CaptureError(f"{symbol}_DEPTH_INVALID:{exc}") from exc
            if not applied:
                if already_valid:
                    raise M035CaptureError(f"{symbol}_DEPTH_UPDATE_REGRESSION_OR_DUPLICATE")
                return symbol, event_time_us, "depthUpdate"
            state.last_depth_time_us = event_time_us
            state.depth_count += 1
            state.last_received_by_type["depthUpdate"] = received_mono_ns
            self.counts[f"{symbol}:depth"] += 1
        else:
            raise M035CaptureError("UNEXPECTED_EVENT_TYPE")
        return symbol, event_time_us, str(kind)

    def _check_pair_stream_freshness(self, now_mono_ns: int) -> None:
        maximum_gap = MAX_PAIR_STREAM_GAP_SECONDS * 1_000_000_000
        for symbol, state in self.states.items():
            for kind in ("trade", "depthUpdate"):
                previous = state.last_received_by_type.get(kind)
                if previous is None or now_mono_ns - previous > maximum_gap:
                    raise M035CaptureError(f"{symbol}_{kind.upper()}_STREAM_STALE")

    def _start_coverage(self, started_mono_ns: int) -> None:
        for symbol, state in self.states.items():
            for kind in ("trade", "depthUpdate"):
                key = f"{symbol}:{kind}"
                previous = state.last_received_by_type[kind]
                self.coverage_origin_ns[key] = previous
                self.coverage_max_gap_ns[key] = started_mono_ns - previous

    def _record_window_event(self, key: str, received_mono_ns: int) -> None:
        previous = self.coverage_last_ns.get(key, self.coverage_origin_ns[key])
        self.coverage_max_gap_ns[key] = max(
            self.coverage_max_gap_ns[key], received_mono_ns - previous
        )
        self.coverage_first_ns.setdefault(key, received_mono_ns)
        self.coverage_last_ns[key] = received_mono_ns

    def _close_coverage(self, cutoff_mono_ns: int) -> None:
        for key, origin in self.coverage_origin_ns.items():
            previous = self.coverage_last_ns.get(key, origin)
            self.coverage_max_gap_ns[key] = max(
                self.coverage_max_gap_ns[key], cutoff_mono_ns - previous
            )

    @staticmethod
    def _wire_payload(message: str | bytes) -> tuple[str, str]:
        if isinstance(message, str):
            return "utf-8", message
        try:
            return "utf-8", message.decode("utf-8")
        except UnicodeDecodeError:
            return "base64", b64encode(message).decode("ascii")

    def run(self, output: Path) -> dict[str, Any]:
        output.mkdir(parents=True, exist_ok=False)
        spec = frozen_capture_spec()
        _write_json(
            output / "configuration.json",
            {**spec, "source_sha": self.source_sha, "configuration_sha256": capture_spec_hash()},
        )
        status = "RUNNING"
        failure: str | None = None
        started_wall_us: int | None = None
        started_mono_ns: int | None = None
        ended_wall_us: int | None = None
        ingest_sequence = 0
        exchange_rows: list[dict[str, Any]] = []
        snapshot_rows: list[dict[str, Any]] = []
        raw_path = output / "raw-market.jsonl.gz"
        validated_path = output / "validated-market.jsonl.gz"
        rest_path = output / "rest-evidence.jsonl"
        startup_mono_ns = self.monotonic_ns()
        last_message_mono_ns = startup_mono_ns
        try:
            with (
                self.stream_factory(CAPTURE_SYMBOLS) as stream,
                gzip.open(raw_path, "wt", encoding="utf-8") as raw_file,
                gzip.open(validated_path, "wt", encoding="utf-8") as validated_file,
                rest_path.open("w", encoding="utf-8") as rest_file,
            ):
                for symbol in CAPTURE_SYMBOLS:
                    exchange = self.public_client.exchange_info(symbol)
                    rest_file.write(
                        json.dumps(
                            {
                                "endpoint": "exchangeInfo",
                                "symbol": symbol,
                                "received_us": self.wall_time_us(),
                                "payload": exchange,
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                    rest_file.flush()
                    if self.monotonic_ns() - startup_mono_ns > (
                        MAX_STARTUP_SECONDS * 1_000_000_000
                    ):
                        raise M035CaptureError("PAIR_READINESS_TIMEOUT")
                    self._validate_exchange_info(symbol, exchange)
                    exchange_rows.append({"symbol": symbol, "payload": exchange})
                    snapshot = self.public_client.depth_snapshot(symbol, limit=SNAPSHOT_LIMIT)
                    rest_file.write(
                        json.dumps(
                            {
                                "endpoint": "depth",
                                "symbol": symbol,
                                "received_us": self.wall_time_us(),
                                "payload": snapshot,
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                    rest_file.flush()
                    if self.monotonic_ns() - startup_mono_ns > (
                        MAX_STARTUP_SECONDS * 1_000_000_000
                    ):
                        raise M035CaptureError("PAIR_READINESS_TIMEOUT")
                    self.states[symbol].book.snapshot(snapshot)
                    snapshot_rows.append({"symbol": symbol, "payload": snapshot})
                _write_json(output / "exchange-info.json", exchange_rows)
                _write_json(output / "depth-snapshots.json", snapshot_rows)

                while True:
                    try:
                        message = stream.recv(timeout=1.0)
                    except TimeoutError:
                        now_mono_ns = self.monotonic_ns()
                        if (
                            started_mono_ns is not None
                            and now_mono_ns - started_mono_ns
                            >= CAPTURE_DURATION_SECONDS * 1_000_000_000
                        ):
                            self._check_pair_stream_freshness(
                                started_mono_ns + CAPTURE_DURATION_SECONDS * 1_000_000_000
                            )
                            self._close_coverage(
                                started_mono_ns + CAPTURE_DURATION_SECONDS * 1_000_000_000
                            )
                            assert started_wall_us is not None
                            ended_wall_us = (
                                started_wall_us + CAPTURE_DURATION_SECONDS * 1_000_000
                            )
                            break
                        if now_mono_ns - last_message_mono_ns > (
                            MAX_STREAM_SILENCE_SECONDS * 1_000_000_000
                        ):
                            raise M035CaptureError("STREAM_SILENCE") from None
                        if (
                            started_mono_ns is None
                            and now_mono_ns - startup_mono_ns
                            > MAX_STARTUP_SECONDS * 1_000_000_000
                        ):
                            raise M035CaptureError("PAIR_READINESS_TIMEOUT") from None
                        continue

                    received_wall_us = self.wall_time_us()
                    received_mono_ns = self.monotonic_ns()
                    last_message_mono_ns = received_mono_ns
                    ingest_sequence += 1
                    wire_encoding, wire_payload = self._wire_payload(message)
                    raw_file.write(
                        json.dumps(
                            {
                                "ingest_sequence": ingest_sequence,
                                "received_us": received_wall_us,
                                "received_monotonic_ns": received_mono_ns,
                                "wire_encoding": wire_encoding,
                                "wire_payload": wire_payload,
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                    raw_file.flush()
                    if (
                        started_mono_ns is None
                        and received_mono_ns - startup_mono_ns
                        > MAX_STARTUP_SECONDS * 1_000_000_000
                    ):
                        raise M035CaptureError("PAIR_READINESS_TIMEOUT")
                    if started_mono_ns is not None:
                        cutoff_mono_ns = (
                            started_mono_ns + CAPTURE_DURATION_SECONDS * 1_000_000_000
                        )
                        if received_mono_ns >= cutoff_mono_ns:
                            self._check_pair_stream_freshness(cutoff_mono_ns)
                            self._close_coverage(cutoff_mono_ns)
                            assert started_wall_us is not None
                            ended_wall_us = (
                                started_wall_us + CAPTURE_DURATION_SECONDS * 1_000_000
                            )
                            break
                        self._check_pair_stream_freshness(received_mono_ns)
                    try:
                        payload = json.loads(message)
                    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                        raise M035CaptureError("INVALID_STREAM_JSON") from exc
                    if not isinstance(payload, dict):
                        raise M035CaptureError("INVALID_STREAM_PAYLOAD")
                    data = payload.get("data", payload)
                    if not isinstance(data, dict):
                        raise M035CaptureError("INVALID_STREAM_DATA")
                    symbol, event_time_us, kind = self._apply(
                        data, received_mono_ns=received_mono_ns
                    )
                    if started_mono_ns is None and all(
                        state.ready for state in self.states.values()
                    ):
                        started_mono_ns = received_mono_ns
                        started_wall_us = received_wall_us
                        self._start_coverage(started_mono_ns)
                    included = started_mono_ns is not None
                    if included:
                        channel = f"{symbol}:{kind}"
                        self.window_counts[channel] += 1
                        self._record_window_event(channel, received_mono_ns)
                    validated_file.write(
                        json.dumps(
                            {
                                "ingest_sequence": ingest_sequence,
                                "received_us": received_wall_us,
                                "received_monotonic_ns": received_mono_ns,
                                "event_time_us": event_time_us,
                                "symbol": symbol,
                                "phase": "CAPTURE" if included else "WARMUP",
                                "included_in_window": included,
                                "payload": data,
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                if started_mono_ns is None or started_wall_us is None:
                    raise M035CaptureError("PAIR_READINESS_NOT_REACHED")
                if not all(
                    self.window_counts[f"{symbol}:trade"] > 0
                    and self.window_counts[f"{symbol}:depthUpdate"] > 0
                    for symbol in CAPTURE_SYMBOLS
                ):
                    raise M035CaptureError("PAIR_STREAM_COVERAGE_INSUFFICIENT")
                status = "COMPLETE"
        except Exception as exc:
            status = "INVALIDATED_TECHNICAL"
            failure = f"{type(exc).__name__}:{exc}"

        result = {
            "identity": CAPTURE_IDENTITY,
            "status": status,
            "failure": failure,
            "source_sha": self.source_sha,
            "configuration_sha256": capture_spec_hash(),
            "symbols": list(CAPTURE_SYMBOLS),
            "started_wall_us": started_wall_us,
            "ended_wall_us": ended_wall_us,
            "duration_seconds": CAPTURE_DURATION_SECONDS if status == "COMPLETE" else None,
            "ingest_records": ingest_sequence,
            "event_counts": dict(sorted(self.counts.items())),
            "window_event_counts": dict(sorted(self.window_counts.items())),
            "channel_coverage": {
                key: {
                    "start_age_ns": (
                        None
                        if started_mono_ns is None
                        else started_mono_ns - self.coverage_origin_ns[key]
                    ),
                    "first_window_offset_ns": (
                        None
                        if started_mono_ns is None or key not in self.coverage_first_ns
                        else self.coverage_first_ns[key] - started_mono_ns
                    ),
                    "last_window_offset_ns": (
                        None
                        if started_mono_ns is None or key not in self.coverage_last_ns
                        else self.coverage_last_ns[key] - started_mono_ns
                    ),
                    "max_gap_ns_including_boundaries": self.coverage_max_gap_ns.get(key),
                }
                for key in sorted(self.coverage_origin_ns)
            },
            "pair_state": {
                symbol: {
                    "book_valid": state.book.valid,
                    "last_depth_update_id": state.book.update_id,
                    "last_trade_id": state.last_trade_id,
                    "trade_count": state.trade_count,
                    "depth_count": state.depth_count,
                }
                for symbol, state in self.states.items()
            },
            "economic_actions": 0,
            "account_access": False,
            "tape_role": "FORWARD_DEVELOPMENT_EVIDENCE_NOT_OOS_RESULT",
        }
        _write_json(output / "result.json", result)
        files = []
        for path in sorted(output.iterdir()):
            if path.is_file() and path.name != "manifest.json":
                files.append(
                    {
                        "path": path.name,
                        "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
        _write_json(
            output / "manifest.json",
            {
                "identity": CAPTURE_IDENTITY,
                "created_at": datetime.now(UTC).isoformat(),
                "status": status,
                "source_sha": self.source_sha,
                "configuration_sha256": capture_spec_hash(),
                "files": files,
                "private_or_order_endpoints_present": False,
            },
        )
        return result
