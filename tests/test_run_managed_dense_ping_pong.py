import copy
import json
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.zonal_ping_pong import ManagedDensePingPongProbe
from scripts import register_managed_dense_ping_pong as registration
from scripts import run_managed_dense_ping_pong as runner


def test_frozen_design_and_m021_lattice() -> None:
    design = json.loads(runner.SPEC.read_bytes())
    grid = json.loads(runner.GRID.read_bytes())
    runner.validate_frozen_design(design, grid)
    registration.validate_registration_design(design)


def test_m022_control_values_are_exact() -> None:
    design = json.loads(runner.SPEC.read_bytes())
    assert design["control_model"] == "M021"
    assert design["control_cycles"] == 19
    assert design["max_simultaneous_open_orders"] == 160
    assert design["initial_usdt"] == "99.6950"
    assert design["initial_usdc"] == "100"
    assert runner.END_US - runner.START_US == 5 * 3_600_000_000


def test_owner_gate_is_m022_only_and_fails_closed(monkeypatch, tmp_path) -> None:
    gate = tmp_path / "gate.md"
    gate.write_text(
        "APPROVED_COMPARISON_DAYS=1\n"
        "EXTENSION_AUTHORIZED=false\n"
        "NEW_REPLAY_AUTHORIZED_NOW=false\n"
        "AUTHORIZED_MODEL=NONE\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "OWNER_WINDOW", gate)
    with pytest.raises(ValueError, match="M022_OWNER_GATE_REQUIRED"):
        runner.require_owner_gate(tmp_path)


def test_manager_audit_rejects_untraced_preemption() -> None:
    metrics = {
        "max_simultaneous_open_orders": 0,
        "return_preemptions": 1,
        "return_fills": 0,
    }
    with pytest.raises(ValueError, match="M022_PREEMPTION_TRACE_MISMATCH"):
        runner.manager_audit([], {"state": {"orders": []}}, metrics)


def test_manager_audit_rejects_cap_breach() -> None:
    metrics = {
        "max_simultaneous_open_orders": 161,
        "return_preemptions": 0,
        "return_fills": 0,
    }
    with pytest.raises(ValueError, match="M022_OPEN_ORDER_CAP_EXCEEDED"):
        rows = [
            {
                "event": "SUBMIT",
                "order_id": index,
                "time_us": index,
                "band_id": "S001",
                "side": "SELL",
                "price": "1.0002",
                "quantity": "1",
                "role": "EXIT",
            }
            for index in range(1, 162)
        ]
        terminal = {
            "state": {
                "orders": [{"order_id": index, "status": "ACTIVE"} for index in range(1, 162)]
            }
        }
        runner.manager_audit(rows, terminal, metrics)


def test_manager_audit_rejects_return_fill_with_wrong_lane() -> None:
    rows = [
        {
            "event": "RETURN_PRICE_CLAIM",
            "lane": "S001",
            "return_side": "BUY",
            "return_price": "1.0000",
        },
        {
            "event": "RETURN_SUBMISSION",
            "lane": "S001",
            "order_id": 4,
            "side": "BUY",
            "price": "1.0000",
        },
        {
            "event": "RETURN_FILL",
            "lane": "S999",
            "order_id": 4,
            "quantity": "1",
        },
    ]
    metrics = {
        "max_simultaneous_open_orders": 0,
        "return_preemptions": 0,
        "return_submissions": 1,
        "return_fills": 1,
    }
    with pytest.raises(ValueError, match="M022_RETURN_FILL_WITHOUT_MATCHING_SUBMISSION"):
        runner.manager_audit(rows, {"state": {"orders": []}}, metrics)


def test_manager_audit_rejects_tampered_return_fill_economics() -> None:
    rows = [
        {
            "event": "SUBMIT",
            "time_us": 1,
            "order_id": 1,
            "band_id": "S001",
            "side": "SELL",
            "price": "1.0002",
            "quantity": "1",
            "role": "ENTRY",
        },
        {
            "event": "FILL",
            "time_us": 2,
            "order_id": 1,
            "band_id": "S001",
            "side": "SELL",
            "price": "1.0002",
            "quantity": "1",
            "role": "ENTRY",
        },
        {
            "event": "RETURN_PRICE_CLAIM",
            "time_us": 2,
            "lane": "S001",
            "source_order_id": 1,
            "return_side": "BUY",
            "return_price": "1.0001",
        },
        {
            "event": "SUBMIT",
            "time_us": 3,
            "order_id": 2,
            "band_id": "S001",
            "side": "BUY",
            "price": "1.0001",
            "quantity": "1",
            "role": "EXIT",
        },
        {
            "event": "RETURN_SUBMISSION",
            "time_us": 3,
            "lane": "S001",
            "order_id": 2,
            "side": "BUY",
            "price": "1.0001",
        },
        {
            "event": "FILL",
            "time_us": 4,
            "order_id": 2,
            "band_id": "S001",
            "side": "BUY",
            "price": "1.0001",
            "quantity": "1",
            "role": "EXIT",
        },
        {
            "event": "RETURN_FILL",
            "time_us": 4,
            "lane": "S001",
            "order_id": 2,
            "side": "BUY",
            "price": "88",
            "quantity": "999",
        },
    ]
    metrics = {
        "max_simultaneous_open_orders": 1,
        "return_preemptions": 0,
        "return_submissions": 1,
        "return_fills": 1,
        "free_orders_canceled_for_return": 0,
        "free_orders_canceled_for_float": 0,
        "free_orders_reposted": 0,
    }
    terminal = {"state": {"orders": [], "dense_anchor": "1.0001"}}
    with pytest.raises(ValueError, match="M022_RETURN_FILL_PHYSICAL_MISMATCH"):
        runner.manager_audit(rows, terminal, metrics)


def test_manager_audit_reconstructs_s_lane_ownership_independently() -> None:
    engine = ManagedDensePingPongProbe(start_us=0, end_us=100)
    book = {
        "exchange_time_us": 1,
        "exchange_upper_us": 1,
        "capture_time_us": 1,
        "bids": ((D("1.0000"), D("1000")),),
        "asks": ((D("1.0002"), D("1000")),),
        "known_bid_floor": D(".98"),
        "known_ask_ceiling": D("1.02"),
    }
    engine.receive_book(book)
    engine.receive_book({**book, "exchange_time_us": 2, "exchange_upper_us": 2})
    engine.finish(time_us=100)
    terminal = engine.checkpoint()
    metrics = engine.metrics()
    runner.manager_audit(engine.audit, terminal, metrics)

    tampered_terminal = copy.deepcopy(terminal)
    tampered_metrics = copy.deepcopy(metrics)
    left = tampered_terminal["state"]["manager_s_free"]["S001"]
    right = tampered_terminal["state"]["manager_s_free"]["S100"]
    tampered_terminal["state"]["manager_s_free"]["S001"] = right
    tampered_terminal["state"]["manager_s_free"]["S100"] = left
    for lane in ("S001", "S100"):
        mirror = tampered_terminal["state"]["manager_s_free"][lane]
        tampered_metrics["lane_ownership"][lane]["free_usdc"] = mirror["quantity"]
        tampered_metrics["lane_ownership"][lane]["free_usdc_cost"] = mirror["cost"]
    with pytest.raises(ValueError, match="M022_S_LANE_OWNERSHIP_RECONSTRUCTION_MISMATCH"):
        runner.manager_audit(engine.audit, tampered_terminal, tampered_metrics)
