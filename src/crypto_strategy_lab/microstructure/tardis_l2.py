"""Capture-ordered Tardis book validation, independent of strategy execution.

Normalized CSV cannot prove native sequence continuity. Native validation is
separate evidence and never silently promotes an unrelated normalized file.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from itertools import groupby, zip_longest
from pathlib import Path
from typing import Any

CSV_SCHEMA = (
    "exchange",
    "symbol",
    "timestamp",
    "local_timestamp",
    "is_snapshot",
    "side",
    "price",
    "amount",
)


def native_exchange_microseconds(value: Any) -> int:
    """Normalize Binance milliseconds or newer microsecond subscriptions.

    The magnitude split is unambiguous within this campaign's 2025-2026
    horizon. Preserve the reported integer; never use float timestamp math.
    """
    if type(value) is not int or value <= 0:
        raise ValueError("invalid native exchange timestamp")
    return value if value >= 100_000_000_000_000 else value * 1000


def native_exchange_interval(value: Any) -> tuple[int, int, str]:
    """Return the reported timestamp's closed uncertainty interval in microseconds."""
    lower = native_exchange_microseconds(value)
    if value >= 100_000_000_000_000:
        return lower, lower, "MICROSECOND_EXACT"
    return lower, lower + 999, "MILLISECOND_INTERVAL"


def _level(price: Any, amount: Any) -> tuple[Decimal, Decimal]:
    try:
        p, q = Decimal(str(price)), Decimal(str(amount))
    except InvalidOperation as exc:
        raise ValueError("invalid decimal level") from exc
    if not p.is_finite() or not q.is_finite() or p <= 0 or q < 0:
        raise ValueError("nonfinite, nonpositive price or negative quantity")
    return p, q


class _Book:
    def __init__(self) -> None:
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}

    def clear(self) -> None:
        self.bids.clear()
        self.asks.clear()

    def apply(self, side: str, price: Decimal, quantity: Decimal) -> None:
        book = self.bids if side == "bid" else self.asks
        if quantity == 0:
            book.pop(price, None)
        else:
            book[price] = quantity

    def crossed(self) -> bool:
        return bool(self.bids and self.asks and max(self.bids) >= min(self.asks))

    def result(self) -> dict[str, list[list[str]]]:
        return {
            "bids": [[str(p), str(q)] for p, q in sorted(self.bids.items(), reverse=True)],
            "asks": [[str(p), str(q)] for p, q in sorted(self.asks.items())],
        }


def iter_csv_rows(path: str | Path) -> Iterator[dict[str, str]]:
    """Read immutable CSV/gzip without sorting rows or assuming exchange order."""
    source = Path(path)
    opener = gzip.open if source.suffix == ".gz" else open
    with opener(source, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != CSV_SCHEMA:
            raise ValueError("unexpected normalized L2 CSV schema")
        yield from reader


def _snapshot(row: Mapping[str, str]) -> bool:
    if row["is_snapshot"] not in {"true", "false"}:
        raise ValueError("invalid is_snapshot")
    return row["is_snapshot"] == "true"


def validate_csv_rows(rows: Iterable[Mapping[str, str]]) -> dict[str, Any]:
    """Validate observable CSV invariants; sequence and disconnect gates UNKNOWN.

    Consecutive local_timestamp/snapshot groups are atomic. Snapshot runs clear
    once on entry; a new run after deltas is a resnapshot. No crossed level is
    removed to repair evidence. Empty sides are recorded, never fabricated.
    """
    book = _Book()
    counts: Counter[str] = Counter()
    previous_local = previous_exchange = first_local = first_exchange = None
    active = in_snapshot = False
    errors: list[str] = []
    try:
        for (_, snapshot), batch in groupby(
            rows, key=lambda row: (row["local_timestamp"], _snapshot(row))
        ):
            counts["batches"] += 1
            if snapshot and not in_snapshot:
                counts["snapshots"] += 1
                book.clear()
                active = True
            in_snapshot = snapshot
            parsed: list[tuple[str, Decimal, Decimal]] = []
            for row in batch:
                counts["rows"] += 1
                if row["exchange"] != "binance" or row["symbol"] != "USDCUSDT":
                    raise ValueError("wrong exchange or symbol")
                local, exchange = int(row["local_timestamp"]), int(row["timestamp"])
                if local <= 0 or exchange <= 0:
                    raise ValueError("nonpositive timestamp")
                if first_local is None:
                    first_local, first_exchange = local, exchange
                counts["local_time_regressions"] += int(
                    previous_local is not None and local < previous_local
                )
                counts["exchange_time_regressions"] += int(
                    previous_exchange is not None and exchange < previous_exchange
                )
                previous_local, previous_exchange = local, exchange
                side = row["side"]
                if side not in {"bid", "ask"}:
                    raise ValueError("invalid side")
                price, quantity = _level(row["price"], row["amount"])
                parsed.append((side, price, quantity))
            if not active:
                counts["prefix_rows_skipped"] += len(parsed)
                continue
            for side, price, quantity in parsed:
                counts["zero_quantity_updates"] += int(quantity == 0)
                book.apply(side, price, quantity)
            counts["crossed_batches"] += int(book.crossed())
            counts["one_sided_batches"] += int(not book.bids or not book.asks)
    except (ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    observable = bool(counts["snapshots"]) and not errors and not counts["crossed_batches"]
    observable = observable and not counts["local_time_regressions"]
    return {
        "format": "TARDIS_NORMALIZED_INCREMENTAL_BOOK_L2",
        "counts": dict(counts),
        "errors": errors,
        "first_local_timestamp": first_local,
        "last_local_timestamp": previous_local,
        "first_timestamp": first_exchange,
        "last_timestamp": previous_exchange,
        "resnapshots": max(0, counts["snapshots"] - 1),
        "observable_invariants_pass": observable,
        "sequence_gate": "UNKNOWN",
        "disconnect_gate": "UNKNOWN",
        "full_day_coverage_gate": "UNKNOWN",
        "L2_DAY_VALID": False if not observable else None,
        "final_book": book.result(),
    }


def validate_csv_file(path: str | Path) -> dict[str, Any]:
    return validate_csv_rows(iter_csv_rows(path))


def validate_raw_lines(
    lines: Iterable[str], *, expected_symbol: str = "USDCUSDT"
) -> dict[str, Any]:
    """Validate native Binance U/u messages in Tardis capture order.

    Lines are ``ISO_LOCAL_TIMESTAMP {stream:...,data:...}``; blank lines mean
    disconnect. Snapshot data has lastUpdateId/bids/asks. Pre-snapshot deltas
    are buffered in arrival order, stale updates ignored, bridging updates
    applied atomically. Any observed gap/disconnect remains a day-level failure
    even when a later snapshot restores the current book.
    """
    book = _Book()
    counts: Counter[str] = Counter()
    errors: list[str] = []
    last_id: int | None = None
    buffered: list[dict[str, Any]] = []
    first_local = previous_local = None
    first_exchange = previous_exchange = None
    previous_trade_id = previous_trade_exchange = None
    bridged = False

    def levels(data: Mapping[str, Any], snapshot: bool) -> list[tuple[str, Decimal, Decimal]]:
        result = []
        for side, key in (
            ("bid", "bids" if snapshot else "b"),
            ("ask", "asks" if snapshot else "a"),
        ):
            for item in data[key]:
                if len(item) != 2:
                    raise ValueError("malformed level")
                p, q = _level(*item)
                result.append((side, p, q))
        return result

    def apply_delta(data: dict[str, Any]) -> None:
        nonlocal last_id, bridged
        first, final = data["U"], data["u"]
        if type(first) is not int or type(final) is not int or first < 0 or final < first:
            raise ValueError("invalid native update IDs")
        changes = levels(data, False)
        if last_id is None:
            buffered.append(data)
            return
        if final <= last_id:
            counts["stale_updates_ignored"] += 1
            return
        if first > last_id + 1:
            counts["sequence_gaps"] += 1
            last_id, bridged = None, False
            buffered.append(data)
            return
        for side, price, quantity in changes:
            book.apply(side, price, quantity)
        last_id, bridged = final, True
        counts["applied_deltas"] += 1
        counts["crossed_states"] += int(book.crossed())
        counts["one_sided_states"] += int(not book.bids or not book.asks)

    for line_number, line in enumerate(lines, 1):
        counts["lines"] += 1
        if not line.strip():
            counts["disconnects"] += 1
            last_id, bridged = None, False
            buffered.clear()
            book.clear()
            continue
        try:
            local_text, payload_text = line.strip().split(" ", 1)
            local = datetime.fromisoformat(local_text.replace("Z", "+00:00"))
            if local.tzinfo is None:
                raise ValueError("native local timestamp lacks timezone")
            if first_local is None:
                first_local = local
            counts["local_time_regressions"] += int(
                previous_local is not None and local < previous_local
            )
            previous_local = local
            payload = json.loads(payload_text)
            data = payload["data"]
            stream = payload["stream"]
            symbol_lower = expected_symbol.lower()
            is_trade = stream.lower() == f"{symbol_lower}@trade"
            if not stream.lower().startswith(f"{symbol_lower}@depth") and not is_trade:
                raise ValueError("unexpected native stream")
            if "s" in data and data["s"] != expected_symbol.upper():
                raise ValueError("wrong native symbol")
            if is_trade:
                if data.get("e") != "trade" or data.get("s") != expected_symbol.upper():
                    raise ValueError("unexpected trade event")
                if any(type(data[key]) is not int or data[key] < 0 for key in ("t", "T", "E")):
                    raise ValueError("invalid trade ID or timestamp")
                if type(data["m"]) is not bool:
                    raise ValueError("invalid trade maker flag")
                _, quantity = _level(data["p"], data["q"])
                if quantity == 0:
                    raise ValueError("zero trade quantity")
                trade_exchange = native_exchange_microseconds(data["T"])
                if previous_trade_id is not None:
                    counts["trade_id_regressions"] += data["t"] < previous_trade_id
                    counts["trade_id_duplicates"] += data["t"] == previous_trade_id
                    counts["trade_id_gaps"] += data["t"] > previous_trade_id + 1
                counts["trade_time_regressions"] += (
                    previous_trade_exchange is not None
                    and trade_exchange < previous_trade_exchange
                )
                previous_trade_id = data["t"]
                previous_trade_exchange = trade_exchange
                counts["trades"] += 1
            elif "lastUpdateId" in data:
                changes = levels(data, True)
                snapshot_id = data["lastUpdateId"]
                if type(snapshot_id) is not int or snapshot_id < 0:
                    raise ValueError("invalid snapshot update ID")
                book.clear()
                for side, price, quantity in changes:
                    book.apply(side, price, quantity)
                last_id, bridged = snapshot_id, False
                counts["snapshots"] += 1
                counts["crossed_states"] += int(book.crossed())
                pending, buffered = buffered, []
                for delta in pending:
                    apply_delta(delta)
            elif data.get("e") == "depthUpdate":
                exchange = native_exchange_microseconds(data["E"])
                if first_exchange is None:
                    first_exchange = exchange
                counts["exchange_time_regressions"] += int(
                    previous_exchange is not None and exchange < previous_exchange
                )
                previous_exchange = exchange
                counts["deltas"] += 1
                apply_delta(data)
            else:
                raise ValueError("unexpected native event")
        except (ValueError, KeyError, TypeError) as exc:
            if len(errors) < 20:
                errors.append(f"line {line_number}: {exc}")
            counts["malformed_records"] += 1
            last_id, bridged = None, False
            buffered.clear()
    fail = any(
        counts[key]
        for key in (
            "sequence_gaps",
            "disconnects",
            "crossed_states",
            "local_time_regressions",
            "malformed_records",
            "trade_id_regressions",
            "trade_id_duplicates",
            "trade_id_gaps",
            "trade_time_regressions",
        )
    )
    sequence_pass = bool(counts["snapshots"] and bridged and not buffered and not fail)
    return {
        "format": "TARDIS_NATIVE_BINANCE_DEPTH",
        "counts": dict(counts),
        "errors": errors,
        "first_local_timestamp": first_local.isoformat() if first_local else None,
        "last_local_timestamp": previous_local.isoformat() if previous_local else None,
        "first_timestamp": first_exchange,
        "last_timestamp": previous_exchange,
        "last_update_id": last_id,
        "current_book_bridged": bridged,
        "buffered_unapplied_deltas": len(buffered),
        "sequence_gate": "PASS" if sequence_pass else "FAIL" if fail else "UNKNOWN",
        "full_day_coverage_gate": "UNKNOWN",
        "normalized_binding_gate": "UNKNOWN",
        "L2_DAY_VALID": False if fail else None,
        "final_book": book.result(),
    }


def _local_microseconds(text: str) -> int:
    local = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if local.tzinfo is None:
        raise ValueError("native local timestamp lacks timezone")
    elapsed = local.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return ((elapsed.days * 86400 + elapsed.seconds) * 1_000_000) + elapsed.microseconds


def iter_native_delta_rows(
    lines: Iterable[str], *, expected_symbol: str = "USDCUSDT"
) -> Iterator[dict[str, str]]:
    """Project *all captured* native depth changes, without accepting/repairing them.

    This is for provenance binding only. It is NOT an execution feed: stale,
    pre-snapshot and sequence-invalid deltas remain present for exact comparison.
    Native snapshot and trade records are excluded, as are disconnect markers.
    ISO submicrosecond digits are floored by datetime's microsecond resolution.
    """
    for line in lines:
        if not line.strip():
            continue
        local_text, payload_text = line.strip().split(" ", 1)
        payload = json.loads(payload_text)
        data = payload["data"]
        if data.get("e") != "depthUpdate":
            continue
        if not payload["stream"].lower().startswith(f"{expected_symbol.lower()}@depth"):
            raise ValueError("unexpected native depth stream")
        if data.get("s", expected_symbol.upper()) != expected_symbol.upper():
            raise ValueError("wrong native symbol")
        local = str(_local_microseconds(local_text))
        if type(data["E"]) is not int:
            raise ValueError("invalid native exchange timestamp")
        for side, key in (("bid", "b"), ("ask", "a")):
            for item in data[key]:
                price, amount = _level(*item)
                yield {
                    "exchange": "binance",
                    "symbol": expected_symbol.upper(),
                    "timestamp": str(native_exchange_microseconds(data["E"])),
                    "local_timestamp": local,
                    "is_snapshot": "false",
                    "side": side,
                    "price": str(price),
                    "amount": str(amount),
                }


def iter_native_events(
    lines: Iterable[str],
    *,
    include_book: bool = True,
    expected_symbol: str = "USDCUSDT",
) -> Iterator[dict[str, Any]]:
    """Reconstruct Tardis snapshot-plus-buffer normalization in capture order.

    A REST snapshot is behind already captured updates. Apply its buffered
    bridging updates first, then expose the reconstructed snapshot at REST
    capture time. Pre-snapshot updates are represented by that snapshot, not
    emitted again. Subsequent stale deltas are ignored by their native IDs.
    Gaps and disconnects raise; execution cannot cross an unknown interval.
    This projection must be compared to the immutable CSV before being trusted.
    BOOK events include physical capture_order, native ID, conservative initial
    coverage bounds, changes and optionally full sorted immutable Decimal levels.
    TRADE events retain native payloads even before the first snapshot. A BOOK
    with sequence_validated=False must not enable order activation: wait until
    a bridging update arrives. Empty but sequenced deltas remain BOOK events.
    exchange_upper_us preserves native millisecond uncertainty; snapshot metadata
    is CAPTURE_BOUND, not a fabricated native exchange timestamp. Snapshot changes
    retain final zero-quantity wire tombstones from REST+buffer normalization,
    while executable bids/asks always contain only strictly positive quantities.
    """
    book = _Book()
    last_id: int | None = None
    pending: list[Mapping[str, Any]] = []
    known_bid_floor = known_ask_ceiling = None
    bridged = False

    def apply(data: Mapping[str, Any]) -> list[tuple[str, Decimal, Decimal]]:
        nonlocal last_id, bridged
        first, final = data["U"], data["u"]
        if type(first) is not int or type(final) is not int or first < 0 or final < first:
            raise ValueError("invalid native update IDs")
        if last_id is None:
            raise ValueError("snapshot required")
        if final <= last_id:
            return []
        if first > last_id + 1:
            raise ValueError("native sequence gap during normalization")
        changes = []
        for side, key in (("bid", "b"), ("ask", "a")):
            for item in data[key]:
                price, quantity = _level(*item)
                book.apply(side, price, quantity)
                changes.append((side, price, quantity))
        last_id = final
        bridged = True
        return changes

    for capture_order, line in enumerate(lines, 1):
        if not line.strip():
            raise ValueError("native disconnect in execution projection")
        local_text, encoded = line.strip().split(" ", 1)
        payload = json.loads(encoded)
        data = payload["data"]
        local = _local_microseconds(local_text)
        snapshot = "lastUpdateId" in data
        if data.get("e") == "trade":
            if (
                payload["stream"].lower() != f"{expected_symbol.lower()}@trade"
                or data.get("s") != expected_symbol.upper()
            ):
                raise ValueError("wrong native trade identity")
            exchange, exchange_upper, precision = native_exchange_interval(data["T"])
            yield {
                "kind": "TRADE",
                "symbol": expected_symbol.upper(),
                "local_us": local,
                "exchange_us": exchange,
                "exchange_upper_us": exchange_upper,
                "exchange_precision": precision,
                "capture_order": capture_order,
                "data": data,
            }
            continue
        if snapshot:
            if not payload["stream"].lower().startswith(f"{expected_symbol.lower()}@depth"):
                raise ValueError("wrong snapshot stream")
            if "s" in data and data["s"] != expected_symbol.upper():
                raise ValueError("wrong native symbol")
            last_id = data["lastUpdateId"]
            if type(last_id) is not int or last_id < 0:
                raise ValueError("invalid snapshot ID")
            book.clear()
            bridged = False
            tombstones: dict[tuple[str, Decimal], Decimal] = {}
            for side, key in (("bid", "bids"), ("ask", "asks")):
                for item in data[key]:
                    price, quantity = _level(*item)
                    book.apply(side, price, quantity)
                    if quantity == 0:
                        tombstones[side, price] = quantity
                    else:
                        tombstones.pop((side, price), None)
            if not book.bids or not book.asks:
                raise ValueError("native snapshot lacks two-sided coverage")
            known_bid_floor, known_ask_ceiling = min(book.bids), max(book.asks)
            for update in pending:
                for side, price, quantity in apply(update):
                    if quantity == 0:
                        tombstones[side, price] = quantity
                    else:
                        tombstones.pop((side, price), None)
            pending.clear()
            changes = [("bid", p, q) for p, q in book.bids.items()]
            changes.extend(("ask", p, q) for p, q in book.asks.items())
            changes.extend(
                (side, price, quantity) for (side, price), quantity in tombstones.items()
            )
            exchange = local
            exchange_upper, precision = local, "CAPTURE_BOUND"
        elif data.get("e") == "depthUpdate":
            if not payload["stream"].lower().startswith(f"{expected_symbol.lower()}@depth"):
                raise ValueError("wrong native depth stream")
            if data.get("s", expected_symbol.upper()) != expected_symbol.upper():
                raise ValueError("wrong native symbol")
            if last_id is None:
                pending.append(data)
                continue
            old_id = last_id
            changes = apply(data)
            if old_id == last_id:
                continue
            exchange, exchange_upper, precision = native_exchange_interval(data["E"])
        else:
            continue
        event: dict[str, Any] = {
            "kind": "BOOK",
            "symbol": expected_symbol.upper(),
            "local_us": local,
            "exchange_us": exchange,
            "exchange_upper_us": exchange_upper,
            "exchange_precision": precision,
            "capture_order": capture_order,
            "native_update_id": last_id,
            "is_snapshot": snapshot,
            "sequence_validated": bridged,
            "known_bid_floor": known_bid_floor,
            "known_ask_ceiling": known_ask_ceiling,
            "changes": tuple(changes),
        }
        if include_book:
            event["bids"] = tuple(sorted(book.bids.items(), reverse=True))
            event["asks"] = tuple(sorted(book.asks.items()))
        yield event


def iter_reconstructed_native_rows(
    lines: Iterable[str], *, expected_symbol: str = "USDCUSDT"
) -> Iterator[dict[str, str]]:
    """Normalized projection of the single native-event reconstruction authority."""
    for event in iter_native_events(
        lines, include_book=False, expected_symbol=expected_symbol
    ):
        if event["kind"] != "BOOK":
            continue
        for side, price, quantity in event["changes"]:
            yield {
                "exchange": "binance",
                "symbol": expected_symbol.upper(),
                "timestamp": str(event["exchange_us"]),
                "local_timestamp": str(event["local_us"]),
                "is_snapshot": "true" if event["is_snapshot"] else "false",
                "side": side,
                "price": str(price),
                "amount": str(quantity),
            }


def bind_csv_reconstructed_native(
    rows: Iterable[Mapping[str, str]],
    raw_lines: Iterable[str],
) -> dict[str, Any]:
    """Compare all normalized snapshot/delta batches against native reconstruction."""
    counts: Counter[str] = Counter()
    digests = {"csv": hashlib.sha256(), "native": hashlib.sha256()}
    errors: list[str] = []
    mismatches: list[dict[str, Any]] = []

    def signatures(source: Iterable[Mapping[str, str]]) -> Iterator[tuple[bool, int, int, str]]:
        for (_, snapshot), batch in groupby(
            source, key=lambda item: (item["local_timestamp"], _snapshot(item))
        ):
            # Reuse exact Decimal multiset implementation; snapshot identity is
            # carried outside its hash, so it cannot match a delta accidentally.
            projected = ({**item, "is_snapshot": "false"} for item in batch)
            for local, count, digest in _delta_batch_signatures(projected):
                yield snapshot, local, count, digest

    try:
        for left, right in zip_longest(
            signatures(rows), signatures(iter_reconstructed_native_rows(raw_lines))
        ):
            for label, batch in (("csv", left), ("native", right)):
                if batch is not None:
                    counts[f"{label}_rows"] += batch[2]
                    counts[f"{label}_snapshots" if batch[0] else f"{label}_delta_batches"] += 1
                    digests[label].update(json.dumps(batch, separators=(",", ":")).encode())
                    digests[label].update(b"\n")
            if left != right:
                counts["mismatched_batches"] += 1
                if len(mismatches) < 10:
                    mismatches.append({"csv": left, "native": right})
            else:
                counts["matched_batches"] += 1
    except (ValueError, TypeError, KeyError) as exc:
        errors.append(str(exc))
    gate = (
        "FAIL"
        if errors or counts["mismatched_batches"]
        else ("PASS" if counts["csv_snapshots"] and counts["matched_batches"] else "UNKNOWN")
    )
    return {
        "normalized_binding_gate": gate,
        "counts": dict(counts),
        "errors": errors,
        "mismatches": mismatches,
        "csv_sha256": digests["csv"].hexdigest(),
        "native_sha256": digests["native"].hexdigest(),
        "semantics": "REST_SNAPSHOT_PLUS_BUFFERED_BRIDGE_THEN_NONSTALE_DELTAS",
    }


def _delta_batch_signatures(
    rows: Iterable[Mapping[str, str]],
) -> Iterator[tuple[int, int, str]]:
    """Canonical multiset per capture batch; preserve batch order and duplicates."""
    deltas = (row for row in rows if not _snapshot(row))
    for local_text, batch in groupby(deltas, key=lambda row: row["local_timestamp"]):
        entries = []
        for row in batch:
            if row["exchange"] != "binance" or row["symbol"] != "USDCUSDT":
                raise ValueError("wrong exchange or symbol")
            if row["side"] not in {"bid", "ask"}:
                raise ValueError("invalid side")
            price, quantity = _level(row["price"], row["amount"])

            # Decimal tuple equality gives exact, formatting-independent values.
            # normalize() uses Decimal context precision, so use fixed format and
            # strip only fractional trailing zeros instead of rounding values.
            def canonical(value: Decimal) -> str:
                if value == 0:
                    return "0"
                text = format(value, "f")
                return text.rstrip("0").rstrip(".") if "." in text else text

            entries.append(
                (int(row["timestamp"]), row["side"], canonical(price), canonical(quantity))
            )
        encoded = json.dumps(sorted(entries), separators=(",", ":")).encode("ascii")
        yield int(local_text), len(entries), hashlib.sha256(encoded).hexdigest()


def bind_csv_native_deltas(
    rows: Iterable[Mapping[str, str]],
    raw_lines: Iterable[str],
) -> dict[str, Any]:
    """Stream exact normalized/native delta binding, independent of validity.

    Equality includes local microseconds, exchange microseconds, side, price,
    amount and duplicate multiplicity. Level order within one capture batch is
    irrelevant. Hashes and counts cover every non-snapshot row. A mismatch can
    reflect documented normalization semantics; it never silently becomes PASS.
    Initial/generated snapshot binding requires separate book-state evidence.
    """
    counts: Counter[str] = Counter()
    csv_hash, native_hash = hashlib.sha256(), hashlib.sha256()
    mismatches: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        for csv_batch, raw_batch in zip_longest(
            _delta_batch_signatures(rows),
            _delta_batch_signatures(iter_native_delta_rows(raw_lines)),
        ):
            for label, batch, digest in (
                ("csv", csv_batch, csv_hash),
                ("native", raw_batch, native_hash),
            ):
                if batch is not None:
                    counts[f"{label}_batches"] += 1
                    counts[f"{label}_rows"] += batch[1]
                    digest.update(json.dumps(batch, separators=(",", ":")).encode("ascii"))
                    digest.update(b"\n")
            if csv_batch != raw_batch:
                counts["mismatched_batch_positions"] += 1
                if len(mismatches) < 20:
                    mismatches.append({"csv": csv_batch, "native": raw_batch})
            else:
                counts["matched_batches"] += 1
    except (ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    gate = (
        "FAIL"
        if errors or counts["mismatched_batch_positions"]
        else ("PASS" if counts["matched_batches"] else "UNKNOWN")
    )
    return {
        "delta_binding_gate": gate,
        "snapshot_binding_gate": "UNKNOWN",
        "normalized_binding_gate": "FAIL" if gate == "FAIL" else "UNKNOWN",
        "counts": dict(counts),
        "errors": errors,
        "mismatches": mismatches,
        "csv_delta_sha256": csv_hash.hexdigest(),
        "native_delta_sha256": native_hash.hexdigest(),
        "semantics": "EXACT_CAPTURE_BATCH_MULTISET_ALL_NATIVE_DELTAS",
    }
