from __future__ import annotations

from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import pytest

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.order_size_capacity import OrderSizeCapacityProbe
from scripts import register_order_size_capacity as registration
from scripts import run_order_size_capacity as runner


def authority(root: Path, **changes: str) -> None:
    values = {
        "APPROVED_COMPARISON_DAYS": "1",
        "EXTENSION_AUTHORIZED": "false",
        "NEW_REPLAY_AUTHORIZED_NOW": "true",
        "AUTHORIZED_MODEL": "M025",
        "AUTHORIZED_SCENARIO_COUNT": "11",
    }
    values.update(changes)
    path = root / runner.OWNER_WINDOW
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))


def empty_initialized(q: str = "500"):
    engine = OrderSizeCapacityProbe(
        order_quantity=q,
        start_us=runner.START_US,
        end_us=runner.END_US,
        latency_us=1179525,
        cancel_latency_us=1179525,
    )
    at = runner.START_US + 1
    engine.receive_book(
        {
            "exchange_time_us": at,
            "exchange_upper_us": at,
            "capture_time_us": at,
            "bids": ((D("1.0019"), D("10000")),),
            "asks": ((D("1.0020"), D("10000")),),
            "known_bid_floor": D("0.9900"),
            "known_ask_ceiling": D("1.0100"),
        }
    )
    later = at + 2 * 1179525
    engine.receive_book(
        {
            "exchange_time_us": later,
            "exchange_upper_us": later,
            "capture_time_us": later,
            "bids": ((D("1.0019"), D("10000")),),
            "asks": ((D("1.0020"), D("10000")),),
            "known_bid_floor": D("0.9900"),
            "known_ask_ceiling": D("1.0100"),
        }
    )
    metrics = {
        key: value for key, value in engine.finish(time_us=runner.END_US).items() if key != "AUDIT"
    }
    return engine.audit, engine.checkpoint(), {}, metrics


def test_frozen_design_and_scenario_order() -> None:
    design = __import__("json").loads(registration.SPEC.read_bytes())
    runner.validate_frozen_design(design)
    assert design["scenario_quantities_usdc"] == [
        "10",
        "50",
        "100",
        "250",
        "500",
        "750",
        "1000",
        "1500",
        "2000",
        "3000",
        "5000",
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("scenario_quantities_usdc", ["500"]),
        ("growth_structural_expansion_enabled", True),
        ("endogenous_market_impact", True),
        ("runs_per_scenario", 2),
        ("end_exclusive", "2025-01-01T05:00:00Z"),
        ("capital_injection", True),
        ("future_base_executed", True),
    ],
)
def test_policy_mutations_fail_closed(field, value) -> None:
    design = __import__("json").loads(registration.SPEC.read_bytes())
    design[field] = value
    with pytest.raises(ValueError, match=r"POLICY_MISMATCH|SCENARIO_SET_CHANGED"):
        runner.validate_frozen_design(design)


@pytest.mark.parametrize(
    "changes",
    [
        {"AUTHORIZED_MODEL": "M024"},
        {"AUTHORIZED_SCENARIO_COUNT": "10"},
        {"NEW_REPLAY_AUTHORIZED_NOW": "false"},
        {"EXTENSION_AUTHORIZED": "true"},
        {"APPROVED_COMPARISON_DAYS": "2"},
    ],
)
def test_owner_gate_rejects_any_mutation(tmp_path, changes) -> None:
    authority(tmp_path, **changes)
    with pytest.raises(ValueError, match="OWNER_GATE_REQUIRED"):
        runner.require_owner_gate(tmp_path)


def test_owner_gate_valid_and_output_is_one_campaign(tmp_path) -> None:
    authority(tmp_path)
    runner.require_owner_gate(tmp_path)
    output, result = tmp_path / "campaign", tmp_path / "result.json"
    output.mkdir()
    with pytest.raises(ValueError, match="EXISTING_M025"):
        runner._assert_unused_output(output, result)


@pytest.mark.parametrize(
    "q", ["10", "50", "100", "250", "500", "750", "1000", "1500", "2000", "3000", "5000"]
)
def test_independent_audit_accepts_each_empty_physical_prefix(q: str) -> None:
    result = runner.independent_scenario_audit(*empty_initialized(q), D(q))
    assert result["status"] == "PASS_M025_INDEPENDENT_SCENARIO_AUDIT"
    assert result["complete_positive_cycles"] == 0
    assert result["max_open_orders"] == 150
    assert result["exact_physical_unit_reconstruction"] is True
    assert result["normalized_reconstruction_used"] is False


@pytest.mark.parametrize("q", [D("500"), D("750"), D("1500"), D("3000")])
def test_exact_auditor_accepts_nondivisible_fragments_and_full_physical_cycle(q: D) -> None:
    latency = 1179525
    engine = OrderSizeCapacityProbe(
        order_quantity=q,
        start_us=runner.START_US,
        end_us=runner.END_US,
        latency_us=latency,
        cancel_latency_us=latency,
    )
    now = runner.START_US + 1

    def send_book() -> None:
        engine.receive_book(
            {
                "exchange_time_us": now,
                "exchange_upper_us": now,
                "capture_time_us": now,
                "bids": ((D("1.0019"), D(2) * q),),
                "asks": ((D("1.0020"), D(2) * q),),
                "known_bid_floor": D(".99"),
                "known_ask_ceiling": D("1.02"),
            }
        )

    send_book()
    now += 2 * latency
    send_book()
    canonical = {}

    def send_trade(buyer_maker: bool, price: str, quantity: D) -> None:
        nonlocal now
        now += 2 * latency
        trade_id = len(canonical) + 1
        item = SimpleNamespace(
            trade_id=trade_id,
            time_us=now,
            buyer_maker=buyer_maker,
            price=D(price),
            quantity=quantity,
        )
        canonical[trade_id] = item
        engine.receive_trade(item, capture_time_us=now)

    send_trade(True, "1.0019", D(2) * q + D(1))
    send_trade(True, "1.0019", q - D(1))
    for _ in range(5):
        now += 2 * latency
        send_book()
    send_trade(False, "1.0020", D(3) * q)
    metrics = {
        key: value for key, value in engine.finish(time_us=runner.END_US).items() if key != "AUDIT"
    }
    audit = runner.independent_scenario_audit(
        engine.audit, engine.checkpoint(), canonical, metrics, q
    )
    assert metrics["TOTAL_CYCLES"] == 1
    assert audit["status"] == "PASS_M025_INDEPENDENT_SCENARIO_AUDIT"
    assert audit["exact_physical_unit_reconstruction"] is True


@pytest.mark.parametrize(
    "mutation,error",
    [
        ("q", "Q_BINDING"),
        ("initial", "initial_usdt|INITIAL_USDT"),
        ("growth", "GROWTH_POLICY"),
        ("latency", "LATENCY"),
        ("compensated_negative_cash", "NEGATIVE|CAPITAL_RECONSTRUCTION"),
        ("public_barrier", "PUBLIC_BARRIER|QUEUE_AT_ACTIVATION"),
    ],
)
def test_independent_audit_rejects_scenario_capital_and_policy_tampering(mutation, error) -> None:
    rows, terminal, canonical, metrics = empty_initialized()
    rows = deepcopy(rows)
    terminal = deepcopy(terminal)
    state = terminal["state"]
    if mutation == "q":
        state["config"]["order_quantity_usdc"] = "750"
    elif mutation == "initial":
        state["initial_usdt"] = str(D(state["initial_usdt"]) + 1)
    elif mutation == "growth":
        state["config"]["growth_expansion_enabled"] = True
    elif mutation == "latency":
        state["config"]["latency_us"] = 0
    elif mutation == "compensated_negative_cash":
        state["cash"] = "-100000"
        state["reserved_usdt"] = str(D(state["reserved_usdt"]) + D("100000"))
    else:
        activation = next(row for row in rows if row["event"] == "ACTIVATED")
        activation["public_barrier_added"] = "999999999"
        activation["queue_ahead_at_activation"] = "999999999"
        state["audit"] = deepcopy(rows)
    terminal["sha256"] = canonical_hash(state)
    with pytest.raises(ValueError, match=rf"{error}"):
        runner.independent_scenario_audit(rows, terminal, canonical, metrics, D("500"))


def scenario(q: str, cycles: int, full_rate: str, residual: int, latency: int = 100):
    return {
        "METRICS": {
            "ORDER_QUANTITY_USDC": q,
            "INITIAL_MARKED_EQUITY": str(D("150.1325") * D(q)),
            "TOTAL_CYCLES": cycles,
            "CYCLES_PER_HOUR": str(D(cycles) / 3),
            "CYCLE_CLOSED_NOTIONAL_USDT": str(D(q) * cycles),
            "CYCLE_CLOSED_NOTIONAL_PER_HOUR_USDT": str(D(q) * cycles / 3),
            "CYCLES_PER_HOUR_PER_1000_INITIAL_USDT": "0",
            "COMPLETED_NOTIONAL_PER_HOUR_PER_1000_INITIAL_USDT": "0",
            "COMPLETED_ROUNDTRIP_USDC": str(D(q) * cycles),
            "COMPLETED_ROUNDTRIP_USDC_PER_HOUR": str(D(q) * cycles / 3),
            "ROUNDTRIP_USDC_PER_HOUR_PER_1000_INITIAL_USDT": str(cycles),
            "TOTAL_FILL_EVENTS": cycles * 2,
            "TOTAL_FILLED_QTY_USDC": str(D(q) * cycles * 2),
            "PARTIAL_FILL_EVENTS": 0,
            "PARTIAL_FILL_RATE": "0",
            "RESIDUAL_PARTIAL_ORDER_COUNT": residual,
            "RESIDUAL_PARTIAL_QTY_USDC": str(D(q) * residual / 2),
            "ORDER_FULL_FILL_RATE": full_rate,
            "FULL_FILL_RATE": full_rate,
            "MEDIAN_TIME_TO_FULL_FILL_US": latency,
            "P95_TIME_TO_FULL_FILL_US": latency,
            "FINAL_MARKED_EQUITY": str(D("150.1325") * D(q)),
            "REALIZED_PNL": "0",
            "REALIZED_PNL_PER_HOUR": "0",
            "PNL_PER_HOUR_PER_1000_INITIAL_USDT": "0",
            "UNREALIZED_PNL": "0",
        }
    }


def test_knee_requires_cycle_drop_and_orthogonal_confirmation() -> None:
    quantities = ["10", "50", "100", "250", "500", "750", "1000", "1500", "2000", "3000", "5000"]
    scenarios = [scenario(q, 100, "0.90", 0) for q in quantities]
    scenarios[4] = scenario("500", 79, "0.90", 0)
    analysis = runner.analyze_curve(scenarios)
    assert analysis["FIRST_SIZE_WITH_GE20_CYCLE_RATE_DROP"] == "500"
    assert analysis["CAPACITY_KNEE"] == "CYCLE_DROP_WITHOUT_ORTHOGONAL_CONFIRMATION"
    scenarios[4] = scenario("500", 79, "0.79", 0)
    assert runner.analyze_curve(scenarios)["CAPACITY_KNEE"] == "500"


def test_zero_baseline_ratio_is_undefined_and_ties_choose_lower_q() -> None:
    quantities = ["10", "50", "100", "250", "500", "750", "1000", "1500", "2000", "3000", "5000"]
    scenarios = [scenario(q, 0 if index == 0 else 1, "0", 0) for index, q in enumerate(quantities)]
    result = runner.analyze_curve(scenarios)
    assert result["CURVE"][1]["CYCLE_RATE_RETENTION_VS_PREVIOUS"] is None
    assert result["BEST_RAW_CYCLES"] == "50"
    assert result["DIAGNOSTIC_FUTURE_BASES"]["B500"] == {
        "HOT_3B": "1500",
        "MID_2B": "1000",
        "FAR_1B": "500",
        "ALL_THREE_SIZES_BELOW_OBSERVED_KNEE": None,
    }


def test_all_zero_curve_is_insufficient_not_no_saturation() -> None:
    quantities = [
        "10",
        "50",
        "100",
        "250",
        "500",
        "750",
        "1000",
        "1500",
        "2000",
        "3000",
        "5000",
    ]
    result = runner.analyze_curve([scenario(q, 0, "0", 0) for q in quantities])
    assert result["CAPACITY_KNEE_ORDER_SIZE"] == ("INSUFFICIENT_EVIDENCE_ALL_SCENARIOS_ZERO_CYCLES")
    assert result["OWNER_500_BOTTLENECK"] == "INCONCLUSIVE"


def test_regression_m024_source_still_rejects_non_one_quantity() -> None:
    from crypto_strategy_lab.microstructure.triangular_pre_aged_queue import (
        TriangularPreAgedQueueProbe,
    )

    old = TriangularPreAgedQueueProbe(start_us=0, end_us=10)
    old.seed_capital(usdt="10")
    with pytest.raises(ValueError, match="M024_INVALID_ORDER"):
        old.submit_order("BUY", "1", quantity="10", time_us=1)
