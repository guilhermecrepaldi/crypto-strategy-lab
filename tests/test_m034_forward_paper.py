from __future__ import annotations

import gzip
import json
from contextlib import contextmanager
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest

from crypto_strategy_lab.microstructure.economic_eligibility import (
    CapitalState,
    DecisionReasonCode,
)
from crypto_strategy_lab.microstructure.m034_forward_paper import (
    IDENTITY,
    DiagnosticConfig,
    ForwardDiagnosticError,
    ForwardPaperDiagnosticRunner,
    PaperOrderState,
    PaperQueueModel,
    SymbolState,
    claim_identity,
    parse_forward_rule,
)
from crypto_strategy_lab.microstructure.public_calibration import LocalDepth


def threshold_rows() -> list[dict[str, object]]:
    values = {
        "MIN_COMPLETION_PROBABILITY": ("0.9", "ratio"),
        "MAX_EXPECTED_LOCK_TIME": ("300", "seconds"),
        "RISK_BUFFER": ("2", "bps"),
        "MAX_INVENTORY_EXPOSURE": ("20", "USD"),
        "PEG_DEVIATION_THRESHOLD": ("0.0025", "ratio"),
        "MIN_NET_EDGE": ("1", "bps"),
        "TAIL_RISK_BOUND": ("1", "USD"),
        "MAX_SPREAD": ("5", "bps"),
        "MIN_DEPTH": ("1000", "USD"),
        "MIN_COMPATIBLE_FLOW": ("10", "asset/second"),
    }
    return [
        {
            "name": name,
            "value": value,
            "unit": unit,
            "source_type": "PROTOCOL_CONSTANT",
            "source_reference": "M034_OWNER_DIAGNOSTIC_FORWARD_3H_200USD",
            "derivation_method": "conservative diagnostic assumption; not calibration",
            "calibration_dataset_hash": None,
            "effective_from_us": 1,
            "frozen_at_us": 1,
        }
        for name, (value, unit) in values.items()
    ]


def config_payload() -> dict[str, object]:
    return {
        "identity": IDENTITY,
        "source_sha": "a" * 40,
        "source_review_status": "PASS_GPT_6_ASTRA",
        "source_review_artifact": "reports/m034/source-review.json",
        "source_review_sha256": "b" * 64,
        "run_claim_artifact": "data/m034/M034_OWNER_DIAGNOSTIC_FORWARD_3H_200USD.claim.json",
        "duration_seconds": 10800,
        "warmup_seconds": 900,
        "initial_equity_usdt": "200",
        "slot_base_usdt": "10",
        "decision_interval_seconds": 5,
        "activation_latency_us": 1_000_000,
        "cancel_ack_latency_us": 1_000_000,
        "max_book_age_us": 3_000_000,
        "flow_window_seconds": 60,
        "depth_band_bps": "10",
        "max_stream_silence_seconds": 30,
        "rule_refresh_seconds": 1800,
        "max_market_clock_lead_us": 5_000_000,
        "max_market_clock_lag_us": 30_000_000,
        "fee_maker_rate": "0.001",
        "fee_taker_rate": "0.001",
        "fee_evidence_status": "UNPROVEN",
        "fee_source_reference": "https://www.binance.com/en/fee/trading",
        "fee_evidence_artifact": "reports/m034/fee-evidence.json",
        "fee_evidence_sha256": "c" * 64,
        "fee_applicable_symbols": [
            "USDCUSDT",
            "FDUSDUSDT",
            "FDUSDUSDC",
            "USD1USDT",
            "USD1USDC",
            "TUSDUSDT",
            "USDPUSDT",
        ],
        "fee_observed_at_us": 1,
        "thresholds": threshold_rows(),
    }


def exchange_info(symbol: str = "USDCUSDT") -> dict[str, object]:
    assets = {
        "USDCUSDT": ("USDC", "USDT"),
        "FDUSDUSDT": ("FDUSD", "USDT"),
        "FDUSDUSDC": ("FDUSD", "USDC"),
        "USD1USDT": ("USD1", "USDT"),
        "USD1USDC": ("USD1", "USDC"),
        "TUSDUSDT": ("TUSD", "USDT"),
        "USDPUSDT": ("USDP", "USDT"),
    }
    base, quote = assets[symbol]
    return {
        "symbols": [
            {
                "symbol": symbol,
                "status": "TRADING",
                "baseAsset": base,
                "quoteAsset": quote,
                "quoteAssetPrecision": 8,
                "filters": [
                    {
                        "filterType": "PRICE_FILTER",
                        "minPrice": "0.00010000",
                        "maxPrice": "1000.00000000",
                        "tickSize": "0.00010000",
                    },
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.10000000",
                        "maxQty": "1000000.00000000",
                        "stepSize": "0.10000000",
                    },
                    {
                        "filterType": "NOTIONAL",
                        "minNotional": "5.00000000",
                        "applyMinToMarket": True,
                    },
                ],
            }
        ]
    }


def test_diagnostic_config_is_exact_and_hash_stable() -> None:
    first = DiagnosticConfig.from_mapping(config_payload())
    second = DiagnosticConfig.from_mapping(config_payload())
    assert first.configuration_hash == second.configuration_hash
    assert first.duration_seconds == 10800
    changed = config_payload()
    changed["duration_seconds"] = 10799
    with pytest.raises(ForwardDiagnosticError, match="FIXED_WINDOW"):
        DiagnosticConfig.from_mapping(changed)


def test_identity_claim_is_canonical_and_one_shot(tmp_path: Path) -> None:
    configuration = DiagnosticConfig.from_mapping(config_payload())
    output = tmp_path / "output"
    marker = claim_identity(configuration, output, root=tmp_path)
    assert marker.is_file()
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["configuration_hash"] == configuration.configuration_hash
    with pytest.raises(ForwardDiagnosticError, match="IDENTITY_ALREADY_CLAIMED"):
        claim_identity(configuration, tmp_path / "other-output", root=tmp_path)


def test_rule_capture_requires_trading_and_all_required_filters() -> None:
    rule, evidence = parse_forward_rule(exchange_info(), symbol="USDCUSDT", acquired_at_us=10)
    assert rule.minimum_notional == D("5")
    assert rule.quantity_step == D("0.1")
    assert evidence["status"] == "TRADING"
    invalid = exchange_info()
    invalid["symbols"][0]["status"] = "BREAK"  # type: ignore[index]
    with pytest.raises(ForwardDiagnosticError, match="SYMBOL_NOT_TRADING"):
        parse_forward_rule(invalid, symbol="USDCUSDT", acquired_at_us=10)


def test_paper_order_is_post_only_and_cannot_fill_before_activation() -> None:
    model = PaperQueueModel()
    with pytest.raises(ForwardDiagnosticError, match="POST_ONLY_WOULD_TAKE"):
        model.place(
            order_id="take",
            symbol="USDCUSDT",
            side="BUY",
            price=D("1.0001"),
            quantity=D("10"),
            now_us=10,
            activation_latency_us=5,
            best_bid=D("1.0000"),
            best_ask=D("1.0001"),
            public_quantity_at_price=D("3"),
        )
    order = model.place(
        order_id="maker",
        symbol="USDCUSDT",
        side="BUY",
        price=D("0.9999"),
        quantity=D("10"),
        now_us=10,
        activation_latency_us=5,
        best_bid=D("1.0000"),
        best_ask=D("1.0001"),
        public_quantity_at_price=D("3"),
    )
    assert (
        model.consume_trade(
            symbol="USDCUSDT",
            trade_id=1,
            price=D("0.9999"),
            quantity=D("20"),
            buyer_is_maker=True,
            trade_time_us=14,
        )
        == {}
    )
    PaperQueueModel.activate(order, now_us=15, best_bid=D("1.0000"), best_ask=D("1.0001"))
    fills = model.consume_trade(
        symbol="USDCUSDT",
        trade_id=2,
        price=D("0.9999"),
        quantity=D("8"),
        buyer_is_maker=True,
        trade_time_us=16,
    )
    assert fills == {"maker": D("5")}
    assert order.queue_ahead == 0 and order.remaining == 5
    assert order.state == PaperOrderState.PARTIAL


def test_cancel_pending_keeps_fifo_until_ack_and_trade_ids_are_unique() -> None:
    model = PaperQueueModel()
    order = model.place(
        order_id="maker",
        symbol="USDCUSDT",
        side="SELL",
        price=D("1.0002"),
        quantity=D("2"),
        now_us=10,
        activation_latency_us=1,
        best_bid=D("1.0000"),
        best_ask=D("1.0001"),
        public_quantity_at_price=D("0"),
    )
    PaperQueueModel.activate(order, now_us=11, best_bid=D("1.0000"), best_ask=D("1.0001"))
    PaperQueueModel.request_cancel(order, now_us=12, cancel_ack_latency_us=5)
    assert model.consume_trade(
        symbol="USDCUSDT",
        trade_id=3,
        price=D("1.0002"),
        quantity=D("1"),
        buyer_is_maker=False,
        trade_time_us=13,
    ) == {"maker": D("1")}
    with pytest.raises(ForwardDiagnosticError, match="DUPLICATE_PUBLIC_TRADE"):
        model.consume_trade(
            symbol="USDCUSDT",
            trade_id=3,
            price=D("1.0002"),
            quantity=D("1"),
            buyer_is_maker=False,
            trade_time_us=14,
        )
    with pytest.raises(ForwardDiagnosticError, match="CANCEL_ACK_NOT_DUE"):
        PaperQueueModel.acknowledge_cancel(order, now_us=16)
    PaperQueueModel.acknowledge_cancel(order, now_us=17)
    assert order.state == PaperOrderState.CANCELED


def test_c1_c2_share_public_queue_ahead_once() -> None:
    model = PaperQueueModel()
    orders = [
        model.place(
            order_id=order_id,
            symbol="USDCUSDT",
            side="BUY",
            price=D("0.9999"),
            quantity=D("5"),
            now_us=10 + index,
            activation_latency_us=1,
            best_bid=D("0.9999"),
            best_ask=D("1.0001"),
            public_quantity_at_price=D("10"),
        )
        for index, order_id in enumerate(("C1", "C2"))
    ]
    for order in orders:
        PaperQueueModel.activate(order, now_us=20, best_bid=D("0.9999"), best_ask=D("1.0001"))
    fills = model.consume_trade(
        symbol="USDCUSDT",
        trade_id=4,
        price=D("0.9999"),
        quantity=D("20"),
        buyer_is_maker=True,
        trade_time_us=21,
    )
    assert fills == {"C1": D("5"), "C2": D("5")}
    assert all(order.state == PaperOrderState.FILLED for order in orders)


def test_new_terminal_cohort_observes_new_public_queue() -> None:
    model = PaperQueueModel()
    first = model.place(
        order_id="first",
        symbol="USDCUSDT",
        side="BUY",
        price=D("0.9999"),
        quantity=D("1"),
        now_us=10,
        activation_latency_us=1,
        best_bid=D("0.9999"),
        best_ask=D("1.0001"),
        public_quantity_at_price=D("0"),
    )
    PaperQueueModel.activate(first, now_us=11, best_bid=D("0.9999"), best_ask=D("1.0001"))
    assert model.consume_trade(
        symbol="USDCUSDT",
        trade_id=5,
        price=D("0.9999"),
        quantity=D("1"),
        buyer_is_maker=True,
        trade_time_us=12,
    ) == {"first": D("1")}
    second = model.place(
        order_id="second",
        symbol="USDCUSDT",
        side="BUY",
        price=D("0.9999"),
        quantity=D("1"),
        now_us=20,
        activation_latency_us=1,
        best_bid=D("0.9999"),
        best_ask=D("1.0001"),
        public_quantity_at_price=D("100"),
    )
    PaperQueueModel.activate(second, now_us=21, best_bid=D("0.9999"), best_ask=D("1.0001"))
    assert (
        model.consume_trade(
            symbol="USDCUSDT",
            trade_id=6,
            price=D("0.9999"),
            quantity=D("1"),
            buyer_is_maker=True,
            trade_time_us=22,
        )
        == {}
    )
    assert second.queue_ahead == D("99")


class NoopClient:
    last_response = None

    def exchange_info(self, symbol: str) -> dict[str, Any]:
        return exchange_info(symbol)

    def depth_snapshot(self, symbol: str, *, limit: int = 5000) -> dict[str, Any]:
        del symbol, limit
        return {"lastUpdateId": 1, "bids": [["0.9999", "1000"]], "asks": [["1.0001", "1000"]]}


def test_unknown_estimators_flow_through_gate_and_block_all_capital() -> None:
    configuration = DiagnosticConfig.from_mapping(config_payload())
    runner = ForwardPaperDiagnosticRunner(
        config=configuration,
        public_client=NoopClient(),
        stream_factory=lambda _symbols: pytest.fail("stream must not be used"),
    )
    rule, _ = parse_forward_rule(exchange_info(), symbol="USDCUSDT", acquired_at_us=1)
    book = LocalDepth(expected_symbol="USDCUSDT")
    book.snapshot({"lastUpdateId": 1, "bids": [["0.9999", "1000"]], "asks": [["1.0001", "1000"]]})
    book.apply(
        {
            "e": "depthUpdate",
            "s": "USDCUSDT",
            "U": 2,
            "u": 2,
            "b": [["0.9999", "1000"]],
            "a": [["1.0001", "1000"]],
        }
    )
    runner.states["USDCUSDT"] = SymbolState(
        symbol="USDCUSDT",
        base_asset="USDC",
        quote_asset="USDT",
        rule=rule,
        book=book,
        acquired_at_us=1,
        rule_evidence_hash="d" * 64,
        last_depth_event_us=10,
    )
    decisions = runner.evaluate(now_us=10)
    assert decisions and all(not row.eligible for row in decisions)
    assert all(
        DecisionReasonCode.COMPLETION_PROBABILITY_UNKNOWN in row.decision_reason_codes
        for row in decisions
    )
    assert all(DecisionReasonCode.FEE_UNPROVEN in row.decision_reason_codes for row in decisions)
    assert runner.decision_ledger.capital_states[-1].state == CapitalState.BLOCKED_DATA
    assert runner.paper_queue.orders == {}


def test_trade_and_duplicate_depth_do_not_refresh_stale_book() -> None:
    configuration = DiagnosticConfig.from_mapping(config_payload())
    runner = ForwardPaperDiagnosticRunner(
        config=configuration,
        public_client=NoopClient(),
        stream_factory=lambda _symbols: pytest.fail("stream must not be used"),
    )
    base_us = 2_000_000_000_000_000
    rule, _ = parse_forward_rule(exchange_info(), symbol="USDCUSDT", acquired_at_us=base_us - 100)
    book = LocalDepth(expected_symbol="USDCUSDT")
    book.snapshot({"lastUpdateId": 1, "bids": [["0.9999", "1000"]], "asks": [["1.0001", "1000"]]})
    book.apply(
        {
            "e": "depthUpdate",
            "s": "USDCUSDT",
            "E": base_us,
            "U": 2,
            "u": 2,
            "b": [],
            "a": [],
        }
    )
    runner.states["USDCUSDT"] = SymbolState(
        symbol="USDCUSDT",
        base_asset="USDC",
        quote_asset="USDT",
        rule=rule,
        book=book,
        acquired_at_us=base_us - 100,
        rule_evidence_hash="d" * 64,
        last_depth_event_us=base_us,
    )
    runner._apply_event(
        {
            "e": "trade",
            "s": "USDCUSDT",
            "T": base_us + 4_000_000,
            "t": 1,
            "p": "1.0000",
            "q": "2",
            "m": True,
        },
        received_us=base_us + 4_000_100,
        received_monotonic_ns=4_000_100_000,
    )
    runner._apply_event(
        {
            "e": "depthUpdate",
            "s": "USDCUSDT",
            "E": base_us + 4_100_000,
            "U": 2,
            "u": 2,
            "b": [],
            "a": [],
        },
        received_us=base_us + 4_100_100,
        received_monotonic_ns=4_100_100_000,
    )
    assert runner.states["USDCUSDT"].last_depth_event_us == base_us
    assert runner.states["USDCUSDT"].last_trade_event_us == base_us + 4_000_000
    decisions = runner.evaluate(now_us=base_us + 4_100_000)
    assert decisions
    assert all(
        DecisionReasonCode.DATA_INSUFFICIENT in row.decision_reason_codes for row in decisions
    )


def test_exchange_timestamp_is_required() -> None:
    configuration = DiagnosticConfig.from_mapping(config_payload())
    runner = ForwardPaperDiagnosticRunner(
        config=configuration,
        public_client=NoopClient(),
        stream_factory=lambda _symbols: pytest.fail("stream must not be used"),
    )
    runner._capture_rules()
    with pytest.raises(ForwardDiagnosticError, match="EXCHANGE_TIMESTAMP_REQUIRED"):
        runner._apply_event(
            {"e": "trade", "s": "USDCUSDT", "t": 1, "p": "1", "q": "1", "m": True},
            received_us=2_000_000_000_000_000,
            received_monotonic_ns=1,
        )


class FakeStream:
    def __init__(self, messages: list[str]) -> None:
        self.messages = iter(messages)

    def recv(self, timeout: float | None = None) -> str:
        del timeout
        return next(self.messages)


@contextmanager
def fake_stream(messages: list[str]):
    yield FakeStream(messages)


def test_runner_uses_exact_market_window_and_writes_seven_checkpoints(tmp_path: Path) -> None:
    configuration = DiagnosticConfig.from_mapping(config_payload())
    start_us = 2_000_000_000_000_000
    messages = [
        json.dumps(
            {
                "data": {
                    "e": "depthUpdate",
                    "s": "USDCUSDT",
                    "E": start_us,
                    "U": 2,
                    "u": 2,
                    "b": [["0.9999", "1000"]],
                    "a": [["1.0001", "1000"]],
                }
            }
        ),
        json.dumps(
            {
                "data": {
                    "e": "depthUpdate",
                    "s": "USDCUSDT",
                    "E": start_us + 10_800_000_000,
                    "U": 3,
                    "u": 3,
                    "b": [],
                    "a": [],
                }
            }
        ),
    ]
    monotonic_values = iter([0, 900_000_000_000, 11_700_000_000_000])
    claim = tmp_path / "claim.json"
    claim.write_text("{}\n", encoding="utf-8")
    runner = ForwardPaperDiagnosticRunner(
        config=configuration,
        public_client=NoopClient(),
        stream_factory=lambda _symbols: fake_stream(messages),
        wall_time_us=lambda: start_us - 1,
        monotonic_ns=lambda: next(monotonic_values),
        claim_artifact=claim,
    )
    output = tmp_path / "one-shot"
    result = runner.run(output)
    assert result["status"] == "COMPLETE"
    assert result["END_TIMESTAMP_US"] - result["START_TIMESTAMP_US"] == 10_800_000_000
    assert [row["offset_seconds"] for row in result["checkpoints"]] == [
        0,
        1800,
        3600,
        5400,
        7200,
        9000,
        10800,
    ]
    assert result["PHYSICAL_CYCLES"] == 0
    assert result["CAPITAL_UTILIZATION_PCT"] == "0.00"
    assert (output / "manifest.json").is_file()
    snapshots = json.loads((output / "depth-snapshots.json").read_text(encoding="utf-8"))
    assert len(snapshots) == 7
    assert snapshots[0]["snapshot"]["bids"]


def test_timestamp_jump_cannot_fake_three_hours(tmp_path: Path) -> None:
    configuration = DiagnosticConfig.from_mapping(config_payload())
    start_us = 2_000_000_000_000_000
    messages = [
        json.dumps(
            {
                "data": {
                    "e": "depthUpdate",
                    "s": "USDCUSDT",
                    "E": start_us,
                    "U": 2,
                    "u": 2,
                    "b": [],
                    "a": [],
                }
            }
        ),
        json.dumps(
            {
                "data": {
                    "e": "depthUpdate",
                    "s": "USDCUSDT",
                    "E": start_us + 10_800_000_000,
                    "U": 3,
                    "u": 3,
                    "b": [],
                    "a": [],
                }
            }
        ),
    ]
    monotonic_values = iter([0, 900_000_000_000, 900_000_000_001])
    claim = tmp_path / "claim.json"
    claim.write_text("{}\n", encoding="utf-8")
    runner = ForwardPaperDiagnosticRunner(
        config=configuration,
        public_client=NoopClient(),
        stream_factory=lambda _symbols: fake_stream(messages),
        wall_time_us=lambda: start_us - 1,
        monotonic_ns=lambda: next(monotonic_values),
        claim_artifact=claim,
    )
    result = runner.run(tmp_path / "jump")
    assert result["status"] == "INVALIDATED_TECHNICAL"
    assert result["failure"] == "ForwardDiagnosticError:M034_FORWARD_MARKET_CLOCK_JUMP"
    assert result["DURATION_HOURS"] == "0.000"
    assert result["END_TIMESTAMP_US"] == result["START_TIMESTAMP_US"]


def test_cutoff_waits_for_monotonic_clock_without_including_late_event(tmp_path: Path) -> None:
    configuration = DiagnosticConfig.from_mapping(config_payload())
    start_us = 2_000_000_000_000_000
    messages = [
        json.dumps(
            {
                "data": {
                    "e": "depthUpdate",
                    "s": "USDCUSDT",
                    "E": start_us,
                    "U": 2,
                    "u": 2,
                    "b": [],
                    "a": [],
                }
            }
        ),
        json.dumps(
            {
                "data": {
                    "e": "depthUpdate",
                    "s": "USDCUSDT",
                    "E": start_us + 10_800_000_000,
                    "U": 3,
                    "u": 3,
                    "b": [],
                    "a": [],
                }
            }
        ),
        json.dumps(
            {
                "data": {
                    "e": "depthUpdate",
                    "s": "USDCUSDT",
                    "E": start_us + 10_800_002_000,
                    "U": 4,
                    "u": 4,
                    "b": [],
                    "a": [],
                }
            }
        ),
    ]
    monotonic_values = iter([0, 900_000_000_000, 11_699_999_000_000, 11_700_001_000_000])
    claim = tmp_path / "claim.json"
    claim.write_text("{}\n", encoding="utf-8")
    runner = ForwardPaperDiagnosticRunner(
        config=configuration,
        public_client=NoopClient(),
        stream_factory=lambda _symbols: fake_stream(messages),
        wall_time_us=lambda: start_us - 1,
        monotonic_ns=lambda: next(monotonic_values),
        claim_artifact=claim,
    )
    output = tmp_path / "cutoff-wait"
    result = runner.run(output)
    assert result["status"] == "COMPLETE"
    assert result["DURATION_HOURS"] == "3.000"
    with gzip.open(output / "raw-market.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    assert [row["included_before_cutoff"] for row in rows] == [True, False, False]
