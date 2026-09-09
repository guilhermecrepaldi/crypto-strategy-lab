from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import pytest

from crypto_strategy_lab.domain import canonical_hash
from scripts import run_serial_hot_line as runner


def terminal_state(*, orders: list[dict] | None = None) -> dict:
    state = {
        "config": {
            "start_us": runner.START_US,
            "end_us": runner.END_US,
            "latency_us": 1,
            "cancel_latency_us": 1,
        },
        "buy_deck": [{"position": index} for index in range(100)],
        "sell_deck": [{"position": index} for index in range(100)],
        "orders": orders
        or [
            {
                "order_id": 1,
                "status": "FILLED",
                "filled": "1",
                "price": "1.0001",
                "side": "BUY",
                "quantity": "1",
                "reserved_quote": "0",
            }
        ],
        "inventory": "1",
        "inventory_cost": "1.0001",
        "realized_profit": "0",
        "cash": "0.0018",
        "processed_trades": ["1"],
        "last_book": {"bids": [["1.0000", "1"]]},
    }
    return {"state": state, "sha256": canonical_hash(state)}


def test_frozen_design_is_exact_three_hour_two_deck_probe() -> None:
    design = __import__("json").loads(runner.SPEC.read_bytes())
    runner.validate_frozen_design(design)
    assert runner.END_US - runner.START_US == 3 * 3_600_000_000


def test_owner_gate_fails_closed_when_not_authorized(tmp_path: Path, monkeypatch) -> None:
    gate = tmp_path / runner.OWNER_WINDOW
    gate.parent.mkdir(parents=True)
    gate.write_text(
        "APPROVED_COMPARISON_DAYS=1\n"
        "EXTENSION_AUTHORIZED=false\n"
        "NEW_REPLAY_AUTHORIZED_NOW=false\n"
        "AUTHORIZED_MODEL=NONE\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "OWNER_WINDOW", runner.OWNER_WINDOW)
    with pytest.raises(ValueError, match="M023_OWNER_GATE_REQUIRED"):
        runner.require_owner_gate(tmp_path)


def test_audit_enforces_single_order_cap_and_terminal_hash() -> None:
    canonical = {
        1: SimpleNamespace(
            quantity=D("1"), time_us=runner.START_US + 2, price=D("1.0000"), buyer_maker=True
        )
    }
    rows = [
        {
            "event": "SUBMIT",
            "order_id": 1,
            "quantity": "1",
            "side": "BUY",
            "price": "1.0001",
            "time_us": runner.START_US,
        },
        {
            "event": "ACTIVATED",
            "order_id": 1,
            "time_us": runner.START_US + 1,
            "queue": "0",
            "native_book_upper_us": runner.START_US,
        },
        {
            "event": "FILL",
            "order_id": 1,
            "quantity": "1",
            "side": "BUY",
            "price": "1.0001",
            "source_id": "1",
            "time_us": runner.START_US + 2,
        },
        {"event": "RADAR_ROTATION"},
        {
            "event": "TRADE",
            "trade_id": "1",
            "consumed_quantity": "1",
            "native_time_us": runner.START_US + 2,
            "price": "1.0000",
            "buyer_maker": True,
            "original_quantity": "1",
        },
    ]
    audit = runner.independent_execution_audit(
        rows,
        terminal_state(),
        canonical,
        {
            "max_open": 1,
            "total_cycles": 0,
            "deck_rotations": 1,
            "cash": "0.0018",
            "reserved_quote": "0",
            "total_usdt_owned": "0.0018",
            "inventory": "1",
            "inventory_cost": "1.0001",
            "realized_profit": "0",
            "marked_equity": "1.0018",
        },
    )
    assert audit["status"] == "PASS_M023_SERIAL_HOT_LINE_LEDGER"


def test_audit_rejects_two_open_orders() -> None:
    rows = [
        {
            "event": "SUBMIT",
            "order_id": 1,
            "quantity": "1",
            "side": "BUY",
            "price": "1",
            "time_us": runner.START_US,
        },
        {
            "event": "SUBMIT",
            "order_id": 2,
            "quantity": "1",
            "side": "BUY",
            "price": "1",
            "time_us": runner.START_US,
        },
    ]
    with pytest.raises(ValueError, match="ORDER_CAP"):
        runner.independent_execution_audit(
            rows,
            terminal_state(
                orders=[
                    {"order_id": 1, "status": "ACTIVE", "reserved_quote": "1"},
                    {"order_id": 2, "status": "ACTIVE", "reserved_quote": "0"},
                ]
            ),
            {},
            {"max_open": 2, "total_cycles": 0, "deck_rotations": 0},
        )


def test_audit_accepts_partial_fragments_of_same_leg() -> None:
    rows = [
        {
            "event": "SUBMIT",
            "order_id": 1,
            "quantity": "1",
            "side": "BUY",
            "price": "1",
            "time_us": runner.START_US,
        },
        {
            "event": "ACTIVATED",
            "order_id": 1,
            "time_us": runner.START_US + 1,
            "queue": "0",
            "native_book_upper_us": runner.START_US,
        },
        {
            "event": "FILL",
            "order_id": 1,
            "quantity": "0.4",
            "side": "BUY",
            "price": "1",
            "source_id": "1",
            "time_us": runner.START_US + 2,
        },
        {
            "event": "TRADE",
            "trade_id": "1",
            "consumed_quantity": "0.4",
            "native_time_us": runner.START_US + 2,
            "price": "0.9",
            "buyer_maker": True,
            "original_quantity": "0.4",
        },
        {
            "event": "FILL",
            "order_id": 1,
            "quantity": "0.6",
            "side": "BUY",
            "price": "1",
            "source_id": "2",
            "time_us": runner.START_US + 3,
        },
        {
            "event": "TRADE",
            "trade_id": "2",
            "consumed_quantity": "0.6",
            "native_time_us": runner.START_US + 3,
            "price": "0.9",
            "buyer_maker": True,
            "original_quantity": "0.6",
        },
        {"event": "RADAR_ROTATION"},
    ]
    state = terminal_state()["state"]
    state["inventory_cost"] = "1.0"
    state["cash"] = "0.0019"
    state["processed_trades"] = ["1", "2"]
    state["orders"][0]["price"] = "1"
    terminal = {"state": state, "sha256": canonical_hash(state)}
    canonical = {
        1: SimpleNamespace(
            quantity=D("0.4"),
            time_us=runner.START_US + 2,
            price=D("0.9"),
            buyer_maker=True,
        ),
        2: SimpleNamespace(
            quantity=D("0.6"),
            time_us=runner.START_US + 3,
            price=D("0.9"),
            buyer_maker=True,
        ),
    }
    audit = runner.independent_execution_audit(
        rows,
        terminal,
        canonical,
        {
            "max_open": 1,
            "total_cycles": 0,
            "deck_rotations": 1,
            "cash": "0.0019",
            "reserved_quote": "0",
            "total_usdt_owned": "0.0019",
            "inventory": "1",
            "inventory_cost": "1",
            "realized_profit": "0",
            "marked_equity": "1.0019",
        },
    )
    assert audit["completed_legs"] == 1


def test_audit_rejects_noncanonical_fill_source_and_tampered_cash() -> None:
    canonical = {
        1: SimpleNamespace(
            quantity=D("1"),
            time_us=runner.START_US + 2,
            price=D("1.0000"),
            buyer_maker=True,
        )
    }
    rows = [
        {
            "event": "SUBMIT",
            "order_id": 1,
            "quantity": "1",
            "side": "BUY",
            "price": "1.0001",
            "time_us": runner.START_US,
        },
        {
            "event": "ACTIVATED",
            "order_id": 1,
            "time_us": runner.START_US + 1,
            "queue": "0",
            "native_book_upper_us": runner.START_US,
        },
        {
            "event": "FILL",
            "order_id": 1,
            "quantity": "1",
            "side": "BUY",
            "price": "1.0001",
            "source_id": "999999",
            "time_us": runner.START_US + 2,
        },
    ]
    metrics = {
        "max_open": 1,
        "total_cycles": 0,
        "deck_rotations": 1,
        "cash": "0.0018",
        "reserved_quote": "0",
        "total_usdt_owned": "0.0018",
        "inventory": "1",
        "inventory_cost": "1.0001",
        "realized_profit": "0",
        "marked_equity": "1.0018",
    }
    with pytest.raises(ValueError, match="NONCANONICAL"):
        runner.independent_execution_audit(rows, terminal_state(), canonical, metrics)

    valid_rows = [dict(row) for row in rows]
    valid_rows[2]["source_id"] = "1"
    valid_rows.extend(
        [
            {"event": "RADAR_ROTATION"},
            {
                "event": "TRADE",
                "trade_id": "1",
                "consumed_quantity": "1",
                "native_time_us": runner.START_US + 2,
                "price": "1.0000",
                "buyer_maker": True,
                "original_quantity": "1",
            },
        ]
    )
    state = terminal_state()["state"]
    state["cash"] = "999"
    tampered_terminal = {"state": state, "sha256": canonical_hash(state)}
    with pytest.raises(ValueError, match="CASH_RECONSTRUCTION"):
        runner.independent_execution_audit(valid_rows, tampered_terminal, canonical, metrics)
