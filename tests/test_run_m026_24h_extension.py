import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.run_m026_24h_extension as runner
from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.dynamic_hotline_321 import DynamicHotline321Probe


def test_owner_gate_accepts_only_m028(tmp_path: Path) -> None:
    authority = tmp_path / runner.OWNER_WINDOW
    authority.parent.mkdir(parents=True)
    authority.write_text(
        "\n".join(
            (
                "APPROVED_COMPARISON_DAYS=1",
                "EXTENSION_AUTHORIZED=false",
                "NEW_REPLAY_AUTHORIZED_NOW=true",
                "AUTHORIZED_MODEL=M028",
                "AUTHORIZED_SCENARIO_COUNT=1",
            )
        ),
        encoding="utf-8",
    )
    runner.require_owner_gate(tmp_path)
    authority.write_text(
        authority.read_text(encoding="utf-8").replace("AUTHORIZED_MODEL=M028", "M026"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="M028_OWNER_GATE_REQUIRED"):
        runner.require_owner_gate(tmp_path)


def test_prefix_gate_requires_exact_ledger_and_normalized_state(
    tmp_path: Path, monkeypatch
) -> None:
    rows = [{"event": "TRADE", "trade_id": "1"}]
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    state = {
        "parent": {"config": {"end_us": runner.M026_END_US}},
        "m026": {"value": 1},
    }
    terminal = tmp_path / "terminal.json"
    terminal.write_text(
        json.dumps({"schema": "M026_DYNAMIC_HOTLINE_321_V1", "state": state}),
        encoding="utf-8",
    )
    metrics = {
        "PHYSICAL_CYCLES": 30,
        "SLOT_EQUIVALENT_CYCLES": 90,
        "TOTAL_FILLS": 78,
        "FINAL_USDT": "128.2356000000000000",
        "FINAL_USDC": "28.00000000",
        "FINAL_TOTAL_MARKED": "156.2972000000000000",
        "REALIZED_CYCLE_PNL": "0.01080000",
        "REALIZED_DISPOSAL_PNL": "0.0380000000000000",
        "UNREALIZED_PNL": "0.0070000000000000",
        "ORDERS_CREATED": 169,
        "HOTLINE_EPOCHS": 30,
    }
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps({"expected_trade_count": 1, "METRICS": metrics}), encoding="utf-8"
    )

    class FakeEngine:
        audit = rows

        def _observe(self, time_us):
            assert time_us == runner.M026_END_US

        def metrics(self):
            return metrics

        def checkpoint(self):
            actual = {
                "parent": {"config": {"end_us": runner.END_US}},
                "m026": {"value": 1},
            }
            return {"state": actual, "sha256": canonical_hash(actual)}

    monkeypatch.setattr(runner, "PARENT_LEDGER", ledger)
    monkeypatch.setattr(runner, "PARENT_TERMINAL", terminal)
    monkeypatch.setattr(runner, "PARENT_RESULT", result)
    trade = SimpleNamespace(trade_id="1", time_us=runner.START_US + 1)
    value = runner.verify_m026_prefix(FakeEngine(), {"1"}, {1: trade})
    assert value["LEDGER_EXACT_MATCH"] is True
    assert value["ECONOMIC_STATE_MATCH"] is True


def test_prefix_gate_rejects_ledger_drift(tmp_path: Path, monkeypatch) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text('{"event":"EXPECTED"}\n', encoding="utf-8")
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"expected_trade_count": 0, "METRICS": {}}), encoding="utf-8")
    monkeypatch.setattr(runner, "PARENT_LEDGER", ledger)
    monkeypatch.setattr(runner, "PARENT_RESULT", result)
    engine = SimpleNamespace(
        audit=[{"event": "DRIFT"}],
        _observe=lambda _: None,
        metrics=lambda: {},
    )
    with pytest.raises(ValueError, match="M028_M026_PREFIX_LEDGER_MISMATCH"):
        runner.verify_m026_prefix(engine, set(), {})


def test_bounded_native_events_rejects_incomplete_slice_set() -> None:
    with pytest.raises(ValueError, match="M028_ALL_SLICES_REQUIRED"):
        list(runner.bounded_native_events(tuple()))


def test_real_kernel_crosses_three_hour_boundary_without_reset() -> None:
    short_end = 10_800_000_000
    long_end = 14_400_000_000
    short = DynamicHotline321Probe(
        start_us=0, end_us=short_end, latency_us=0, cancel_latency_us=0
    )
    long = DynamicHotline321Probe(
        start_us=0, end_us=long_end, latency_us=0, cancel_latency_us=0
    )
    first_book = {
        "time_us": 1,
        "exchange_upper_us": 1,
        "bids": [["1.0019", "1000"]],
        "asks": [["1.0020", "1000"]],
        "known_bid_floor": "0.98",
        "known_ask_ceiling": "1.02",
    }
    short.receive_book(first_book)
    long.receive_book(first_book)
    short.finish(time_us=short_end)
    long._observe(short_end)
    expected = short.checkpoint()["state"]
    observed = long.checkpoint()["state"]
    observed["parent"]["config"]["end_us"] = short_end
    assert observed == expected
    order_ids = [order.order_id for order in long.orders]
    initial_mark = long.initial_mark
    buy_reserve = long.buy_mobility_reserve
    sell_reserve = long.sell_mobility_reserve
    long.receive_book({**first_book, "time_us": short_end + 1, "exchange_upper_us": short_end + 1})
    assert long.initial_mark == initial_mark
    assert long.buy_mobility_reserve == buy_reserve
    assert long.sell_mobility_reserve == sell_reserve
    assert [order.order_id for order in long.orders] == order_ids
    assert long._last_observation_us == short_end + 1
