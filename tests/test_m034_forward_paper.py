from __future__ import annotations

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
        "fee_maker_rate": "0.001",
        "fee_taker_rate": "0.001",
        "fee_evidence_status": "PROVEN_FORWARD",
        "fee_source_reference": "https://www.binance.com/en/fee/trading",
        "fee_evidence_artifact": "reports/m034/fee-evidence.json",
        "fee_evidence_sha256": "c" * 64,
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
        last_event_us=10,
    )
    decisions = runner.evaluate(now_us=10)
    assert decisions and all(not row.eligible for row in decisions)
    assert all(
        DecisionReasonCode.COMPLETION_PROBABILITY_UNKNOWN in row.decision_reason_codes
        for row in decisions
    )
    assert runner.decision_ledger.capital_states[-1].state == CapitalState.BLOCKED_DATA
    assert runner.paper_queue.orders == {}


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
    monotonic_values = iter([0, 900_000_000_000, 900_000_000_001])
    runner = ForwardPaperDiagnosticRunner(
        config=configuration,
        public_client=NoopClient(),
        stream_factory=lambda _symbols: fake_stream(messages),
        wall_time_us=lambda: start_us - 1,
        monotonic_ns=lambda: next(monotonic_values),
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
