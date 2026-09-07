"""Public-only prospective evidence, never a reconstruction of historical L2."""

from __future__ import annotations

import gzip
import hashlib
import json
import queue
import threading
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .public_market import PublicMarketClient, connect_market_stream, parse_book

D = Decimal


class BookGap(ValueError):
    pass


class LocalDepth:
    """Binance snapshot + absolute U/u updates; invalid until a bridging update."""

    def __init__(self) -> None:
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.update_id: int | None = None
        self.valid = False

    def snapshot(self, payload: dict[str, Any]) -> None:
        self.bids = self.levels(payload["bids"])
        self.asks = self.levels(payload["asks"])
        self.update_id = int(payload["lastUpdateId"])
        self.valid = False

    @staticmethod
    def levels(raw: list[list[str]]) -> dict[Decimal, Decimal]:
        result = {}
        for p, q in raw:
            price, quantity = D(p), D(q)
            if not price.is_finite() or not quantity.is_finite() or price <= 0 or quantity < 0:
                raise BookGap("INVALID_LEVEL")
            if quantity:
                result[price] = quantity
        return result

    def apply(self, event: dict[str, Any]) -> bool:
        if event.get("s") != "USDCUSDT" or event.get("e") != "depthUpdate":
            raise BookGap("INVALID_DEPTH_SYMBOL_OR_TYPE")
        first, last = event["U"], event["u"]
        if type(first) is not int or type(last) is not int or first > last:
            raise BookGap("INVALID_SEQUENCE")
        if self.update_id is None:
            raise BookGap("SNAPSHOT_REQUIRED")
        if last <= self.update_id:
            return False
        if first > self.update_id + 1:
            self.valid = False
            self.update_id = None
            raise BookGap("DEPTH_SEQUENCE_GAP")
        for target, key in ((self.bids, "b"), (self.asks, "a")):
            for p, q in event[key]:
                price, quantity = D(p), D(q)
                if not price.is_finite() or not quantity.is_finite() or price <= 0 or quantity < 0:
                    self.valid = False
                    raise BookGap("INVALID_LEVEL")
                if quantity == 0:
                    target.pop(price, None)
                else:
                    target[price] = quantity
        self.update_id = last
        self.valid = bool(self.bids and self.asks and max(self.bids) < min(self.asks))
        if not self.valid:
            raise BookGap("EMPTY_OR_CROSSED_BOOK")
        return True


def weighted_quantiles(values: list[Any], weights: list[int | float | Decimal]) -> dict[str, Any]:
    if len(values) != len(weights):
        raise ValueError("VALUES_WEIGHTS_LENGTH_MISMATCH")
    pairs = sorted(
        (D(str(value)), D(str(weight))) for value, weight in zip(values, weights, strict=True)
    )
    pairs = [(value, weight) for value, weight in pairs if weight > 0]
    if not pairs:
        return {
            "n": 0,
            "weight": "0",
            "min": None,
            "p10": None,
            "p50": None,
            "p90": None,
            "p99": None,
            "max": None,
        }
    total = sum((weight for _, weight in pairs), D(0))
    result = {
        "n": len(pairs),
        "weight": str(total),
        "min": str(pairs[0][0]),
        "max": str(pairs[-1][0]),
    }
    for label, percentile in (("p10", 10), ("p50", 50), ("p90", 90), ("p99", 99)):
        target = total * D(percentile) / D(100)
        cumulative = D(0)
        for value, weight in pairs:
            cumulative += weight
            if cumulative >= target:
                result[label] = str(value)
                break
    return result


def quantiles(values: list[Any]) -> dict[str, Any]:
    if not values:
        return {
            "n": 0,
            "min": None,
            "p10": None,
            "p50": None,
            "p90": None,
            "p99": None,
            "max": None,
        }
    ordered = sorted(D(str(v)) for v in values)
    n = len(ordered)
    result = {"n": n, "min": str(ordered[0]), "max": str(ordered[-1])}
    # Nearest rank, deterministic (no interpolation suggesting unseen measurements).
    for label, percentile in (("p10", 10), ("p50", 50), ("p90", 90), ("p99", 99)):
        rank = max(1, (n * percentile + 99) // 100)
        result[label] = str(ordered[rank - 1])
    return result


def validate_public_trade(data: dict[str, Any], *, last_trade_id: int | None = None) -> int:
    """Validate the raw trade stream actually subscribed by the collector."""
    if data.get("e") != "trade" or data.get("s") != "USDCUSDT":
        raise ValueError("INVALID_TRADE_SYMBOL_OR_TYPE")
    aggregate_id = data.get("t")
    if type(aggregate_id) is not int or aggregate_id < 0:
        raise ValueError("INVALID_TRADE_ID")
    if last_trade_id is not None and aggregate_id <= last_trade_id:
        raise ValueError("TRADE_ID_REGRESSION")
    if type(data.get("m")) is not bool:
        raise ValueError("INVALID_AGGRESSOR")
    if type(data.get("T")) is not int or data["T"] <= 0:
        raise ValueError("INVALID_TRADE_TIMESTAMP")
    for key in ("p", "q"):
        try:
            value = D(data[key])
        except Exception as exc:
            raise ValueError(f"INVALID_TRADE_{key.upper()}") from exc
        if not value.is_finite() or value <= 0:
            raise ValueError(f"INVALID_TRADE_{key.upper()}")
    return aggregate_id


class WeightedBookSamples:
    """Nonoverlapping monotonic residence intervals retaining joint observations."""

    def __init__(self) -> None:
        self.previous: tuple[int, dict[str, Any]] | None = None
        self.rows: list[dict[str, Any]] = []

    def close(self, monotonic_ns: int) -> None:
        if self.previous is not None:
            started, values = self.previous
            if monotonic_ns < started:
                raise ValueError("MONOTONIC_CLOCK_REGRESSION")
            if monotonic_ns > started:
                self.rows.append(
                    {**values, "start_monotonic_ns": started, "duration_ns": monotonic_ns - started}
                )
        self.previous = None

    def observe(self, monotonic_ns: int, values: dict[str, Any]) -> None:
        self.close(monotonic_ns)
        self.previous = monotonic_ns, values


def validate_bookticker_sequence(update_id: int, previous: int | None) -> tuple[int, bool]:
    if type(update_id) is not int or update_id <= 0:
        raise ValueError("INVALID_BOOKTICKER_UPDATE_ID")
    return update_id, previous is not None and update_id < previous


def _collect(output: Path, *, seconds: int = 300) -> dict[str, Any]:
    if seconds < 1:
        raise ValueError("POSITIVE_DURATION_REQUIRED")
    output.mkdir(parents=True, exist_ok=False)
    client = PublicMarketClient()
    rest_records: list[dict[str, Any]] = []

    def request(path: str, params: dict[str, Any] | None = None) -> Any:
        value = client._request_json(path, params)
        assert client.last_response is not None
        rest_records.append(dict(client.last_response))
        return value

    exchange = request("/api/v3/exchangeInfo", {"symbol": "USDCUSDT"})
    symbol = exchange["symbols"][0]
    if symbol["symbol"] != "USDCUSDT" or symbol["status"] != "TRADING":
        raise ValueError("PUBLIC_SYMBOL_NOT_TRADING")
    tick = D(next(x for x in symbol["filters"] if x["filterType"] == "PRICE_FILTER")["tickSize"])
    offsets, rtts = [], []
    for _ in range(12):
        server = request("/api/v3/time")["serverTime"]
        record = rest_records[-1]
        offsets.append(D(server) - D(record["sent_us"] + record["received_us"]) / 2)
        rtts.append(record["rtt_us"])
    offset = D(quantiles(offsets)["p50"])
    started_at = datetime.now(UTC).isoformat()
    deadline = time.monotonic() + seconds
    inbox: queue.Queue[Any] = queue.Queue(maxsize=100000)
    stop = threading.Event()
    counts: Counter[str] = Counter()
    depth, messages = LocalDepth(), output / "messages.jsonl.gz"
    samples: dict[str, list[Any]] = {
        k: []
        for k in (
            "spread",
            "bid_best_qty",
            "ask_best_qty",
            "bid_one_tick_qty",
            "ask_one_tick_qty",
            "bid_two_level_qty",
            "ask_two_level_qty",
            "ws_delay_raw_us",
            "ws_delay_offset_adjusted_us",
            "bbo_residence_us",
            "trade_quantity",
            "inter_trade_receive_us",
            "depth_churn_quantity",
        )
    }
    weighted = WeightedBookSamples()
    last_bbo, last_bbo_us, last_trade_us, last_trade_id = None, None, None, None
    depth_first_u, resnapshot_at = None, 0.0
    failure = None
    connection_errors: list[str] = []

    def receive() -> None:
        attempts = 0
        seq = 0
        while not stop.is_set() and attempts < 3:
            try:
                with connect_market_stream(calibration=True) as ws:
                    counts["connections"] += 1
                    while not stop.is_set():
                        try:
                            raw = ws.recv(timeout=1)
                        except TimeoutError:
                            continue
                        seq += 1
                        inbox.put_nowait((time.perf_counter_ns(), time.time_ns() // 1000, seq, raw))
            except Exception as exc:
                attempts += 1
                counts["disconnects"] += 1
                connection_errors.append(f"{type(exc).__name__}: {exc}")
                try:
                    seq += 1
                    inbox.put_nowait(
                        (
                            time.perf_counter_ns(),
                            time.time_ns() // 1000,
                            seq,
                            json.dumps({"_calibration": "DISCONNECT_GAP", "attempt": attempts}),
                        )
                    )
                except queue.Full:
                    counts["queued_gap_records_dropped"] += 1
                if attempts < 3:
                    time.sleep(min(2**attempts, 4))
        if connection_errors and attempts >= 3:
            stop.set()

    worker = threading.Thread(target=receive, daemon=True)
    worker.start()
    with gzip.open(messages, "wt", encoding="utf-8", newline="\n") as sink:
        try:
            while time.monotonic() < deadline and not stop.is_set():
                try:
                    received_ns, received_us, sequence, raw = inbox.get(timeout=1)
                except queue.Empty:
                    continue
                envelope = json.loads(raw)
                sink.write(
                    json.dumps(
                        {
                            "received_monotonic_ns": received_ns,
                            "received_us": received_us,
                            "receive_sequence": sequence,
                            "payload": envelope,
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                if envelope.get("_calibration") == "DISCONNECT_GAP":
                    counts["disconnect_gap_records"] += 1
                    weighted.close(received_ns)
                    depth = LocalDepth()
                    depth_first_u = None
                    resnapshot_at = 0.0
                    continue
                data = envelope.get("data", envelope)
                kind = data.get("e", "bookTicker")
                counts[kind] += 1
                if "E" in data:
                    samples["ws_delay_raw_us"].append(received_us - data["E"])
                    samples["ws_delay_offset_adjusted_us"].append(
                        D(received_us - data["E"]) + offset
                    )
                if kind == "serverShutdown":
                    failure = "SERVER_SHUTDOWN_RECONNECT_REQUIRED"
                    break
                if kind == "trade":
                    try:
                        current_trade_id = validate_public_trade(data, last_trade_id=last_trade_id)
                    except ValueError as exc:
                        failure = str(exc)
                        break
                    if last_trade_id is not None and current_trade_id != last_trade_id + 1:
                        counts["trade_id_discontinuities"] += 1
                    last_trade_id = current_trade_id
                    samples["trade_quantity"].append(data["q"])
                    if last_trade_us is not None:
                        samples["inter_trade_receive_us"].append(
                            received_ns // 1000 - last_trade_us
                        )
                    last_trade_us = received_ns // 1000
                elif kind == "bookTicker":
                    quote = parse_book(data, received_us=received_us)
                    _, regressed = validate_bookticker_sequence(
                        quote.update_id, counts.get("last_bookticker_update_id")
                    )
                    if regressed:
                        counts["bookticker_sequence_regressions"] += 1
                    counts["last_bookticker_update_id"] = quote.update_id
                    bbo = (quote.bid, quote.ask)
                    if last_bbo != bbo:
                        if last_bbo_us is not None:
                            samples["bbo_residence_us"].append(received_ns // 1000 - last_bbo_us)
                        last_bbo, last_bbo_us = bbo, received_ns // 1000
                elif kind == "depthUpdate":
                    if depth_first_u is None:
                        depth_first_u = data["U"]
                    if depth.update_id is None or time.monotonic() >= resnapshot_at:
                        weighted.close(received_ns)
                        snap = request("/api/v3/depth", {"symbol": "USDCUSDT", "limit": 5000})
                        counts["snapshots"] += 1
                        if snap["lastUpdateId"] < depth_first_u:
                            counts["stale_snapshots"] += 1
                            continue
                        depth.snapshot(snap)
                        resnapshot_at = time.monotonic() + 60
                    try:
                        churn = sum(
                            (
                                abs(D(q) - book.get(D(p), D(0)))
                                for book, key in ((depth.bids, "b"), (depth.asks, "a"))
                                for p, q in data[key]
                            ),
                            D(0),
                        )
                        changed = depth.apply(data)
                    except BookGap:
                        counts["book_gaps_or_invalidations"] += 1
                        weighted.close(received_ns)
                        depth = LocalDepth()
                        depth_first_u = None
                        continue
                    if changed:
                        bid, ask = max(depth.bids), min(depth.asks)
                        samples["spread"].append(ask - bid)
                        for side, book, best, direction in (
                            ("bid", depth.bids, bid, -1),
                            ("ask", depth.asks, ask, 1),
                        ):
                            best_q, next_q = book[best], book.get(best + direction * tick, D(0))
                            samples[f"{side}_best_qty"].append(best_q)
                            samples[f"{side}_one_tick_qty"].append(next_q)
                            samples[f"{side}_two_level_qty"].append(best_q + next_q)
                        samples["depth_churn_quantity"].append(churn)
                        joint = {
                            k: str(samples[k][-1])
                            for k in (
                                "spread",
                                "bid_best_qty",
                                "ask_best_qty",
                                "bid_one_tick_qty",
                                "ask_one_tick_qty",
                                "bid_two_level_qty",
                                "ask_two_level_qty",
                            )
                        }
                        joint.update(
                            bid=str(bid),
                            ask=str(ask),
                            update_id=depth.update_id,
                            received_us=received_us,
                            ws_delay_offset_adjusted_us=str(D(received_us - data["E"]) + offset),
                        )
                        weighted.observe(received_ns, joint)
                        counts["valid_book_samples"] += 1
        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"
        finally:
            weighted.close(time.perf_counter_ns())
            stop.set()
            worker.join(timeout=3)
            # Preserve received-but-unprocessed evidence without feeding it to metrics.
            while not inbox.empty():
                received_ns, received_us, sequence, raw = inbox.get_nowait()
                sink.write(
                    json.dumps(
                        {
                            "received_monotonic_ns": received_ns,
                            "received_us": received_us,
                            "receive_sequence": sequence,
                            "not_processed_at_capture_boundary": True,
                            "raw": raw,
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
    if connection_errors:
        failure = connection_errors[-1]
    rest_path = output / "rest-responses.json"
    rest_path.write_text(json.dumps(rest_records, indent=2) + "\n", encoding="utf-8")
    actual_duration = max(0.0, time.monotonic() - (deadline - seconds))
    valid_samples = counts.get("valid_book_samples", 0)
    valid_duration = sum(row["duration_ns"] for row in weighted.rows) / 1_000_000_000
    joint_path = output / "joint-book-samples.json"
    joint_path.write_text(json.dumps(weighted.rows, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema": "binance-public-calibration-v1",
        "symbol": "USDCUSDT",
        "evidence_class": "PROSPECTIVE_CALIBRATION",
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "requested_duration_seconds": seconds,
        "actual_captured_duration_seconds": actual_duration,
        "status": "CAPTURED" if failure is None and valid_samples else "INCOMPLETE",
        "pilot_status": "NO_VALID_DATA" if not valid_samples else "CAPTURED_UNQUALIFIED_DURATION",
        "failure": failure,
        "counts": dict(counts),
        "sampling": "time-weighted synchronized valid-book samples; not queue probabilities",
        "valid_book_sample_count": valid_samples,
        "synchronized_valid_duration_seconds": valid_duration,
        "synchronized_valid_coverage": valid_duration / actual_duration if actual_duration else 0,
        "queue_ahead": "UNKNOWN: displayed aggregate depth is a calibration proxy, not our queue",
        "historical_l2": "NOT_MEASURED",
        "order_ack": "UNKNOWN_NOT_AUTHORIZED",
        "clock_offset_server_minus_local_us": quantiles(offsets),
        "clock_offset_estimator": "serverTime minus local send/receive midpoint; asymmetry unknown",
        "rest_rtt_us": quantiles(rtts),
        "statistics": {k: quantiles(v) for k, v in samples.items()},
        "time_weighted_statistics": {
            k: weighted_quantiles(
                [row[k] for row in weighted.rows], [row["duration_ns"] for row in weighted.rows]
            )
            for k in (
                "spread",
                "bid_best_qty",
                "ask_best_qty",
                "bid_one_tick_qty",
                "ask_one_tick_qty",
                "bid_two_level_qty",
                "ask_two_level_qty",
            )
        },
        "tick_size_current": str(tick),
        "current_exchange_info": exchange,
        "reconnect": "bounded reconnect requires fresh snapshot; gaps recorded, never filled",
        "stress_regime_representativeness": (
            "UNKNOWN: no peg-stress regime claimed from duration alone"
        ),
        "files": [],
    }
    for path in (messages, rest_path, joint_path):
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        manifest["files"].append(
            {"path": str(path), "sha256": digest, "size_bytes": path.stat().st_size}
        )
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def collect(output: Path, *, seconds: int = 300) -> dict[str, Any]:
    """Persist a failure manifest too; an existing capture is never overwritten."""
    if output.exists():
        raise FileExistsError(output)
    try:
        return _collect(output, seconds=seconds)
    except Exception as exc:
        output.mkdir(parents=True, exist_ok=True)
        result = {
            "schema": "binance-public-calibration-v1",
            "status": "INCOMPLETE",
            "failure": f"{type(exc).__name__}: {exc}",
            "counts": {},
            "evidence_class": "PROSPECTIVE_CALIBRATION",
            "finished_at": datetime.now(UTC).isoformat(),
        }
        (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result
