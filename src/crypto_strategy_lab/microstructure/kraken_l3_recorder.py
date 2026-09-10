"""Immutable raw-message capture primitives for Kraken L3.

Kraken's Spot L3 subscription requires an authenticated WebSocket token.  M033
does not access credentials, so this module deliberately separates durable raw
capture from transport/authentication and fails closed for unauthenticated use.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from crypto_strategy_lab.microstructure.multi_venue_models import BookKey, Venue


@dataclass
class CaptureManifest:
    venue: str
    symbol: str
    source_endpoint: str
    source_channel: str
    started_at_us: int
    ended_at_us: int | None = None
    raw_sha256: str | None = None
    normalized_sha256: str | None = None
    event_count: int = 0
    normalized_event_count: int = 0
    sequence_valid: bool = True
    capture_valid: bool = True
    gaps: list[dict[str, object]] = field(default_factory=list)
    reconnects: list[dict[str, object]] = field(default_factory=list)


class KrakenL3RawRecorder:
    """Write each native message before any normalization and emit a manifest."""

    endpoint = "wss://ws-auth.kraken.com/v2"
    channel = "level3"

    def __init__(self, root: Path, *, book: BookKey, started_at_us: int) -> None:
        if book.venue != Venue.KRAKEN:
            raise ValueError("M033_L3_RECORDER_KRAKEN_ONLY")
        self.root = root
        self.root.mkdir(parents=True, exist_ok=False)
        self.raw_path = root / "raw.ndjson"
        self.normalized_path = root / "normalized.ndjson"
        self.manifest_path = root / "manifest.json"
        self.manifest = CaptureManifest(
            venue=book.venue.value,
            symbol=book.symbol,
            source_endpoint=self.endpoint,
            source_channel=self.channel,
            started_at_us=started_at_us,
        )
        self._last_sequence: int | None = None
        self._raw_hash_by_sequence: dict[int, str] = {}
        self._normalized_bindings: set[tuple[int, int]] = set()
        self._closed = False

    @staticmethod
    def require_subscription_token(token: str | None) -> str:
        if not token:
            raise PermissionError("M033_KRAKEN_L3_AUTH_TOKEN_REQUIRED_NO_PRIVATE_ACCESS")
        return token

    def append_raw(self, raw_message: bytes, *, local_capture_time_us: int, sequence: int) -> str:
        self._require_open()
        if sequence in self._raw_hash_by_sequence:
            raise ValueError("M033_DUPLICATE_RAW_SEQUENCE")
        if self._last_sequence is not None and sequence != self._last_sequence + 1:
            self.manifest.sequence_valid = False
            self.record_gap(
                start_sequence=self._last_sequence + 1,
                end_sequence=sequence - 1,
                detected_at_us=local_capture_time_us,
            )
        raw_sha256 = hashlib.sha256(raw_message).hexdigest()
        envelope = {
            "local_capture_time_us": local_capture_time_us,
            "recorder_sequence": sequence,
            "native_message_sha256": raw_sha256,
            "native_message": raw_message.decode("utf-8"),
        }
        with self.raw_path.open("ab") as output:
            output.write(json.dumps(envelope, sort_keys=True).encode("utf-8") + b"\n")
        self._last_sequence = sequence
        self._raw_hash_by_sequence[sequence] = raw_sha256
        self.manifest.event_count += 1
        return raw_sha256

    def append_normalized(
        self,
        payload: dict[str, object],
        *,
        raw_sequence: int,
        source_event_index: int,
    ) -> None:
        self._require_open()
        if raw_sequence not in self._raw_hash_by_sequence:
            raise ValueError("M033_NORMALIZATION_BEFORE_RAW_PERSISTENCE")
        binding = (raw_sequence, source_event_index)
        if binding in self._normalized_bindings:
            raise ValueError("M033_DUPLICATE_NORMALIZED_SOURCE_BINDING")
        envelope = {
            "raw_sequence": raw_sequence,
            "source_event_index": source_event_index,
            "native_message_sha256": self._raw_hash_by_sequence[raw_sequence],
            "normalized_event": payload,
        }
        with self.normalized_path.open("ab") as output:
            output.write(json.dumps(envelope, sort_keys=True).encode("utf-8") + b"\n")
        self._normalized_bindings.add(binding)
        self.manifest.normalized_event_count += 1

    def record_gap(self, *, start_sequence: int, end_sequence: int, detected_at_us: int) -> None:
        self._require_open()
        self.manifest.sequence_valid = False
        self.manifest.capture_valid = False
        self.manifest.gaps.append(
            {
                "start_sequence": start_sequence,
                "end_sequence": end_sequence,
                "detected_at_us": detected_at_us,
            }
        )

    def record_reconnect(self, *, at_us: int, reason: str) -> None:
        self._require_open()
        self.manifest.capture_valid = False
        self.manifest.reconnects.append({"at_us": at_us, "reason": reason})

    def close(self, *, ended_at_us: int) -> CaptureManifest:
        self._require_open()
        self.manifest.ended_at_us = ended_at_us
        self.manifest.raw_sha256 = _sha256(self.raw_path)
        self.manifest.normalized_sha256 = (
            _sha256(self.normalized_path) if self.normalized_path.exists() else None
        )
        self.manifest_path.write_text(
            json.dumps(self.manifest.__dict__, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self._closed = True
        return self.manifest

    def _require_open(self) -> None:
        if self._closed:
            raise ValueError("M033_CAPTURE_ALREADY_CLOSED")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["CaptureManifest", "KrakenL3RawRecorder"]
