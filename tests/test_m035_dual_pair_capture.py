from __future__ import annotations

import gzip
import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

import crypto_strategy_lab.microstructure.m035_dual_pair_capture as capture_module
import scripts.run_m035_dual_pair_capture as capture_cli
from crypto_strategy_lab.microstructure.m035_dual_pair_capture import (
    CAPTURE_SYMBOLS,
    DualPairForwardCapture,
    capture_spec_hash,
    frozen_capture_spec,
)


def exchange_info(symbol: str, *, status: str = "TRADING") -> dict:
    return {
        "symbols": [
            {
                "symbol": symbol,
                "status": status,
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.0001"},
                    {"filterType": "LOT_SIZE", "stepSize": "0.1"},
                ],
            }
        ]
    }


def snapshot() -> dict:
    return {
        "lastUpdateId": 100,
        "bids": [["0.9999", "1000"]],
        "asks": [["1.0001", "1000"]],
    }


def depth(symbol: str, first: int, last: int) -> dict:
    return {
        "e": "depthUpdate",
        "s": symbol,
        "E": 1_000_000 + last,
        "U": first,
        "u": last,
        "b": [["0.9999", "900"]],
        "a": [],
    }


def trade(symbol: str, trade_id: int) -> dict:
    return {
        "e": "trade",
        "s": symbol,
        "T": 2_000_000 + trade_id,
        "t": trade_id,
        "p": "1.0000",
        "q": "5",
        "m": True,
    }


class Client:
    def exchange_info(self, symbol: str) -> dict:
        return exchange_info(symbol)

    def depth_snapshot(self, symbol: str, *, limit: int = 5000) -> dict:
        assert symbol in CAPTURE_SYMBOLS and limit == 5000
        return snapshot()


class Stream:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = iter(rows)

    def recv(self, timeout: float | None = None) -> str:
        assert timeout == 1.0
        return json.dumps(next(self.rows))


def stream_factory(rows: list[dict]):
    @contextmanager
    def factory(symbols: tuple[str, ...]):
        assert symbols == CAPTURE_SYMBOLS
        yield Stream(rows)

    return factory


class SequenceClock:
    def __init__(self, values: list[int]) -> None:
        self.values = iter(values)
        self.last = values[-1]

    def __call__(self) -> int:
        return next(self.values, self.last)


def complete_rows() -> list[dict]:
    return [
        depth("USDCUSDT", 101, 101),
        trade("USDCUSDT", 10),
        depth("FDUSDUSDT", 101, 101),
        trade("FDUSDUSDT", 20),
        trade("USDCUSDT", 11),
        depth("USDCUSDT", 102, 102),
        trade("FDUSDUSDT", 21),
        depth("FDUSDUSDT", 102, 102),
        trade("USDCUSDT", 12),
        depth("USDCUSDT", 103, 103),
        trade("FDUSDUSDT", 22),
        depth("FDUSDUSDT", 103, 103),
        trade("USDCUSDT", 13),
    ]


def run_capture(
    output: Path, rows: list[dict], *, event_mono_ns: list[int] | None = None
) -> dict:
    event_times = event_mono_ns or [
        0,
        0,
        0,
        0,
        1_000_000_000,
        1_000_000_000,
        1_000_000_000,
        1_000_000_000,
        11_000_000_000,
        11_000_000_000,
        11_000_000_000,
        11_000_000_000,
        20_000_000_000,
    ]
    capture = DualPairForwardCapture(
        public_client=Client(),
        stream_factory=stream_factory(rows),
        source_sha="a" * 40,
        wall_time_us=SequenceClock(list(range(10, 240, 10))),
        monotonic_ns=SequenceClock([0, 0, 0, 0, 0, *event_times]),
    )
    with patch.object(capture_module, "CAPTURE_DURATION_SECONDS", 20):
        return capture.run(output)


def test_frozen_capture_spec_is_dual_pair_individual_trade_and_non_economic():
    spec = frozen_capture_spec()
    assert spec["symbols"] == ["USDCUSDT", "FDUSDUSDT"]
    assert spec["streams"] == ["trade", "depth@100ms"]
    assert spec["trade_semantics"] == "INDIVIDUAL_PUBLIC_TRADE_NOT_AGGTRADE"
    assert spec["duration_seconds"] == 10_800
    assert not spec["economic_actions"] and not spec["account_access"]
    assert spec["kraken"] == "RETIRED_DISABLED"
    assert len(capture_spec_hash()) == 64


def test_complete_capture_has_one_global_order_and_exclusive_cutoff(tmp_path: Path):
    output = tmp_path / "capture"
    result = run_capture(output, complete_rows())
    assert result["status"] == "COMPLETE"
    assert result["duration_seconds"] == 20
    assert result["economic_actions"] == 0
    assert result["pair_state"]["USDCUSDT"]["trade_count"] == 3
    assert result["pair_state"]["FDUSDUSDT"]["trade_count"] == 3
    assert result["window_event_counts"] == {
        "FDUSDUSDT:depthUpdate": 2,
        "FDUSDUSDT:trade": 3,
        "USDCUSDT:depthUpdate": 2,
        "USDCUSDT:trade": 2,
    }
    assert set(result["channel_coverage"]) == {
        "FDUSDUSDT:depthUpdate",
        "FDUSDUSDT:trade",
        "USDCUSDT:depthUpdate",
        "USDCUSDT:trade",
    }
    assert all(
        row["max_gap_ns_including_boundaries"] <= 10_000_000_000
        for row in result["channel_coverage"].values()
    )
    with gzip.open(output / "raw-market.jsonl.gz", "rt", encoding="utf-8") as handle:
        raw_rows = [json.loads(line) for line in handle]
    assert [row["ingest_sequence"] for row in raw_rows] == list(range(1, 14))
    with gzip.open(output / "validated-market.jsonl.gz", "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    assert [row["included_in_window"] for row in rows] == [
        False,
        False,
        False,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
    ]
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE"
    assert not manifest["private_or_order_endpoints_present"]
    assert {row["path"] for row in manifest["files"]} == {
        "configuration.json",
        "depth-snapshots.json",
        "exchange-info.json",
        "raw-market.jsonl.gz",
        "rest-evidence.jsonl",
        "result.json",
        "validated-market.jsonl.gz",
    }


def test_trade_gap_invalidates_capture_and_preserves_failure_artifacts(tmp_path: Path):
    rows = complete_rows()
    rows[4] = trade("USDCUSDT", 12)
    output = tmp_path / "capture"
    result = run_capture(output, rows)
    assert result["status"] == "INVALIDATED_TECHNICAL"
    assert "TRADE_SEQUENCE_GAP" in result["failure"]
    assert (output / "raw-market.jsonl.gz").is_file()
    with gzip.open(output / "raw-market.jsonl.gz", "rt", encoding="utf-8") as handle:
        raw_rows = [json.loads(line) for line in handle]
    assert json.loads(raw_rows[-1]["wire_payload"])["t"] == 12
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))["status"] == (
        "INVALIDATED_TECHNICAL"
    )


def test_depth_gap_invalidates_capture(tmp_path: Path):
    rows = complete_rows()
    rows[0] = depth("USDCUSDT", 102, 102)
    result = run_capture(tmp_path / "capture", rows)
    assert result["status"] == "INVALIDATED_TECHNICAL"
    assert "DEPTH_SEQUENCE_GAP" in result["failure"]


def test_depth_regression_after_bridge_is_not_coverage(tmp_path: Path):
    rows = complete_rows()
    rows[5] = {**depth("USDCUSDT", 100, 100), "E": 3_000_000}
    result = run_capture(tmp_path / "capture", rows)
    assert result["status"] == "INVALIDATED_TECHNICAL"
    assert "DEPTH_UPDATE_REGRESSION_OR_DUPLICATE" in result["failure"]


def test_pair_specific_silence_invalidates_even_while_other_pair_flows(tmp_path: Path):
    rows = complete_rows()[:5]
    result = run_capture(
        tmp_path / "capture",
        rows,
        event_mono_ns=[0, 0, 0, 0, 11_000_000_001],
    )
    assert result["status"] == "INVALIDATED_TECHNICAL"
    assert "STREAM_STALE" in result["failure"]


def test_continuous_messages_cannot_bypass_startup_deadline(tmp_path: Path):
    result = run_capture(
        tmp_path / "capture",
        [trade("USDCUSDT", 10)],
        event_mono_ns=[121_000_000_000],
    )
    assert result["status"] == "INVALIDATED_TECHNICAL"
    assert "PAIR_READINESS_TIMEOUT" in result["failure"]


def test_event_at_exclusive_cutoff_cannot_invalidate_window(tmp_path: Path):
    rows = complete_rows()
    rows[-1] = trade("USDCUSDT", 99)
    result = run_capture(tmp_path / "capture", rows)
    assert result["status"] == "COMPLETE"
    assert result["pair_state"]["USDCUSDT"]["last_trade_id"] == 12


def test_rest_evidence_is_preserved_if_second_snapshot_fails(tmp_path: Path):
    class FailingClient(Client):
        def depth_snapshot(self, symbol: str, *, limit: int = 5000) -> dict:
            if symbol == "FDUSDUSDT":
                raise RuntimeError("snapshot unavailable")
            return super().depth_snapshot(symbol, limit=limit)

    capture = DualPairForwardCapture(
        public_client=FailingClient(),
        stream_factory=stream_factory(complete_rows()),
        source_sha="c" * 40,
        wall_time_us=SequenceClock(list(range(1, 20))),
        monotonic_ns=lambda: 0,
    )
    output = tmp_path / "capture"
    result = capture.run(output)
    assert result["status"] == "INVALIDATED_TECHNICAL"
    rest_rows = [
        json.loads(line)
        for line in (output / "rest-evidence.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [(row["endpoint"], row["symbol"]) for row in rest_rows] == [
        ("exchangeInfo", "USDCUSDT"),
        ("depth", "USDCUSDT"),
        ("exchangeInfo", "FDUSDUSDT"),
    ]


def test_pairs_must_both_be_trading(tmp_path: Path):
    class HaltedClient(Client):
        def exchange_info(self, symbol: str) -> dict:
            return exchange_info(symbol, status="BREAK" if symbol == "FDUSDUSDT" else "TRADING")

    capture = DualPairForwardCapture(
        public_client=HaltedClient(),
        stream_factory=stream_factory(complete_rows()),
        source_sha="b" * 40,
        monotonic_ns=lambda: 0,
    )
    result = capture.run(tmp_path / "capture")
    assert result["status"] == "INVALIDATED_TECHNICAL"
    assert "FDUSDUSDT_NOT_TRADING" in result["failure"]


def test_published_source_gate_covers_transport_and_validator(monkeypatch):
    assert "src/crypto_strategy_lab/microstructure/public_market.py" in capture_cli.SOURCE_PATHS
    calibration_path = "src/crypto_strategy_lab/microstructure/public_calibration.py"
    assert calibration_path in capture_cli.SOURCE_PATHS

    def clean_git(*args: str) -> str:
        if args[:2] == ("rev-parse", "HEAD") or args[:2] == ("rev-parse", "origin/main"):
            return "a" * 40
        if args[:2] == ("status", "--porcelain"):
            return ""
        raise AssertionError(args)

    monkeypatch.setattr(capture_cli, "git", clean_git)
    capture_cli.verify_published_source("a" * 40)
    with pytest.raises(capture_module.M035CaptureError, match="NOT_PUBLISHED"):
        capture_cli.verify_published_source("b" * 40)

    monkeypatch.setattr(
        capture_cli,
        "git",
        lambda *args: "dirty" if args[:2] == ("status", "--porcelain") else "a" * 40,
    )
    with pytest.raises(capture_module.M035CaptureError, match="SOURCE_DIRTY"):
        capture_cli.verify_published_source("a" * 40)
