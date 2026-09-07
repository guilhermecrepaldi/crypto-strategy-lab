"""Exercise the actual public collector, including its receiver and persisted evidence.

The only replacements are public transport endpoints. Epoch/monotonic clocks,
receiver thread, queue, snapshot reconstruction, statistics and manifests are real.
"""

import gzip
import hashlib
import json
import time
from contextlib import contextmanager
from decimal import Decimal
from itertools import pairwise

import pytest

from crypto_strategy_lab.microstructure import public_calibration as calibration


def install_public_transport(monkeypatch, events, *, fail_rest=False):
    calls = []

    class PublicClient:
        last_response = None

        def _request_json(self, path, params=None):
            calls.append((path, params))
            assert path in {"/api/v3/time", "/api/v3/exchangeInfo", "/api/v3/depth"}
            if fail_rest:
                raise RuntimeError("SYNTHETIC_PUBLIC_TRANSPORT_FAILURE")
            received = time.time_ns() // 1000
            if path == "/api/v3/time":
                payload = {"serverTime": received - 500}
            elif path == "/api/v3/exchangeInfo":
                assert params == {"symbol": "USDCUSDT"}
                payload = {
                    "symbols": [
                        {
                            "symbol": "USDCUSDT",
                            "status": "TRADING",
                            "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.0001"}],
                        }
                    ]
                }
            else:
                assert params == {"symbol": "USDCUSDT", "limit": 5000}
                payload = {
                    "lastUpdateId": 100,
                    "bids": [["0.9999", "1000"]],
                    "asks": [["1.0001", "2000"]],
                }
            self.last_response = {
                "url": "https://data-api.binance.vision" + path,
                "sent_us": received - 2000,
                "received_us": received,
                "rtt_us": 2000,
                "status": 200,
                "headers": {},
                "body": json.dumps(payload),
            }
            return payload

    class Stream:
        def __init__(self):
            self.rows = iter(events)

        def recv(self, timeout):
            time.sleep(0.005)
            try:
                event = dict(next(self.rows))
            except StopIteration:
                raise TimeoutError from None
            # Do not add event time to Spot bookTicker; other event times are
            # exchange epoch microseconds, intentionally unlike monotonic ns.
            if "e" in event:
                event.setdefault("E", time.time_ns() // 1000 - 2000)
            if event.get("e") == "trade":
                event.setdefault("T", event["E"])
            return json.dumps(event)

    @contextmanager
    def stream(*, calibration):
        assert calibration is True
        yield Stream()

    monkeypatch.setattr(calibration, "PublicMarketClient", PublicClient)
    monkeypatch.setattr(calibration, "connect_market_stream", stream)
    return calls


def depth(first=100, last=101):
    return {
        "e": "depthUpdate",
        "s": "USDCUSDT",
        "U": first,
        "u": last,
        "b": [["0.9999", "900"]],
        "a": [["1.0001", "1900"]],
    }


def raw_trade(**changes):
    return {"e": "trade", "s": "USDCUSDT", "t": 123, "p": "1.0", "q": "2", "m": True, **changes}


def test_collect_integrates_raw_trade_epoch_latency_and_nonoverlapping_joint_time(
    monkeypatch, tmp_path
):
    ticker = {"s": "USDCUSDT", "u": 101, "b": "0.9999", "B": "900", "a": "1.0001", "A": "1900"}
    calls = install_public_transport(monkeypatch, [depth(), ticker, raw_trade(), depth(102, 102)])
    output = tmp_path / "capture"
    result = calibration.collect(output, seconds=1)
    assert result["status"] == "CAPTURED"
    assert result["counts"]["trade"] == 1
    assert result["statistics"]["trade_quantity"]["p50"] == "2"
    latency = result["statistics"]["ws_delay_offset_adjusted_us"]
    assert Decimal(1000) <= Decimal(latency["p50"]) < Decimal(100000)
    assert result["rest_rtt_us"]["p50"] == "2000"
    assert result["clock_offset_server_minus_local_us"]["p50"] == "500"
    assert (
        0
        < result["synchronized_valid_duration_seconds"]
        <= result["actual_captured_duration_seconds"]
    )
    assert 0 < result["synchronized_valid_coverage"] <= 1
    rows = json.loads((output / "joint-book-samples.json").read_text())
    for before, after in pairwise(rows):
        assert before["start_monotonic_ns"] + before["duration_ns"] <= after["start_monotonic_ns"]
    assert (
        sum(row["duration_ns"] for row in rows) / 1e9
        == result["synchronized_valid_duration_seconds"]
    )
    with gzip.open(output / "messages.jsonl.gz", "rt") as stream:
        messages = [json.loads(line) for line in stream]
    trade_rows = [row for row in messages if row.get("payload", {}).get("e") == "trade"]
    assert trade_rows[0]["payload"]["t"] == 123
    assert "a" not in trade_rows[0]["payload"]  # Raw trades, not aggTrade parsing.
    assert all("received_monotonic_ns" in row and "received_us" in row for row in messages)
    for item in result["files"]:
        with open(item["path"], "rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == item["sha256"]
    assert all("account" not in path and "order" not in path for path, _ in calls)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"s": "OTHER"}, "INVALID_TRADE_SYMBOL"),
        ({"t": True}, "INVALID_TRADE_ID"),
        ({"m": "true"}, "INVALID_AGGRESSOR"),
        ({"T": 0}, "INVALID_TRADE_TIMESTAMP"),
        ({"p": "NaN"}, "INVALID_TRADE_P"),
        ({"q": "-1"}, "INVALID_TRADE_Q"),
    ],
)
def test_collect_rejects_malformed_actual_raw_trade_and_persists_failure(
    monkeypatch, tmp_path, changes, reason
):
    install_public_transport(monkeypatch, [raw_trade(**changes)])
    output = tmp_path / "capture"
    result = calibration.collect(output, seconds=1)
    assert result["status"] == "INCOMPLETE"
    assert reason in result["failure"]
    assert json.loads((output / "manifest.json").read_text())["failure"] == result["failure"]
    assert result["statistics"]["trade_quantity"]["n"] == 0


def test_collect_without_market_data_cannot_claim_calibration(monkeypatch, tmp_path):
    install_public_transport(monkeypatch, [])
    result = calibration.collect(tmp_path / "empty", seconds=1)
    assert result["status"] == "INCOMPLETE"
    assert result["pilot_status"] == "NO_VALID_DATA"
    assert result["synchronized_valid_duration_seconds"] == 0
    assert result["time_weighted_statistics"]["spread"]["p50"] is None
    assert result["order_ack"] == "UNKNOWN_NOT_AUTHORIZED"
    assert result["stress_regime_representativeness"].startswith("UNKNOWN")


def test_collect_initial_public_failure_still_writes_manifest(monkeypatch, tmp_path):
    install_public_transport(monkeypatch, [], fail_rest=True)
    output = tmp_path / "failure"
    result = calibration.collect(output, seconds=1)
    assert result["status"] == "INCOMPLETE"
    assert "SYNTHETIC_PUBLIC_TRANSPORT_FAILURE" in result["failure"]
    assert json.loads((output / "manifest.json").read_text()) == result
    with pytest.raises(FileExistsError):
        calibration.collect(output, seconds=1)
