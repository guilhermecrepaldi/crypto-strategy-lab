"""Append-only registration for the OWNER-authorized M025 capacity curve."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crypto_strategy_lab.ml.model_registry import (
    ModelRegistry,
    ModelSpec,
    ModelStatus,
    compute_model_hash,
)
from scripts.run_high_uptime_recovery import lf_sha

MODEL_ID = "M025"
SPEC = Path("docs/microstructure/M025_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M025_ORDER_SIZE_CAPACITY_PREREGISTRATION.md")
OWNER = Path("docs/microstructure/M025_ORDER_SIZE_CAPACITY_OWNER_DIRECTIVE.md")


def validate_registration_design(design: dict[str, Any]) -> None:
    expected = {
        "model_id": MODEL_ID,
        "strategy": "M024_ORDER_SIZE_CAPACITY_CURVE_V1",
        "parent_model_id": "M024",
        "scientific_status": "OWNER_AUTHORIZED_CONTROLLED_ORDER_SIZE_CAPACITY_SWEEP",
        "source_day": "2025-01-01",
        "start": "2025-01-01T00:00:00Z",
        "end_exclusive": "2025-01-01T03:00:00Z",
        "economic_duration_hours": 3,
        "scenario_quantities_usdc": [
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
        ],
        "scenario_count": 11,
        "runs_per_scenario": 1,
        "only_independent_variable": "ORDER_QUANTITY_USDC",
        "logical_price_levels_per_side": 50,
        "initial_double_depth_levels_per_side": 25,
        "initial_orders_per_side": 75,
        "initial_open_orders": 150,
        "hard_simulated_open_order_cap": 200,
        "expected_initial_usdt_per_q": "74.9900",
        "expected_initial_usdc_per_q": "75",
        "expected_initial_marked_equity_per_q": "150.1325",
        "global_liquidity_consumption": "ONCE_PER_SCENARIO",
        "negative_exit_allowed": False,
        "complete_cycle_rule": "FULL_Q_ENTRY_PLUS_FULL_Q_RETURN_POSITIVE_ONLY",
        "partial_cancel_policy": "PARTIAL_ENTRY_CANCELED_LOCKED_NO_RETURN_NO_CYCLE",
        "growth_pool_measured": True,
        "growth_structural_expansion_enabled": False,
        "capital_injection": False,
        "cutoff_liquidation": False,
        "endogenous_market_impact": False,
        "true_historical_queue_rank_known": False,
        "scenario_execution_order": "SINGLE_TAPE_BROADCAST_ASCENDING_Q_PER_EVENT",
        "knee_cycle_drop_threshold": "0.20",
        "knee_requires_orthogonal_confirmation": True,
        "knee_residual_partial_confirmation_min_additional_orders": 1,
        "knee_full_fill_rate_confirmation_drop": "0.10",
        "knee_median_full_fill_time_confirmation_increase": "0.20",
        "zero_baseline_ratio_policy": "UNDEFINED",
        "ranking_tie_breaker": "LOWER_Q",
        "diagnostic_future_base_rule": "B250_B500_B1000_EACH_WITH_3X_2X_1X_SIZES_UNEXECUTED",
        "future_base_executed": False,
        "day2_authorized": False,
        "extension_authorized": False,
        "automatic_successor_authorized": False,
    }
    for key, value in expected.items():
        if type(design.get(key)) is not type(value) or design[key] != value:
            raise ValueError(f"M025_OWNER_POLICY_MISMATCH:{key}")


def registered_model_payload() -> dict[str, Any]:
    design = json.loads(SPEC.read_bytes())
    validate_registration_design(design)
    return {
        **design,
        "spec_sha256_lf": lf_sha(SPEC),
        "preregistration_sha256_lf": lf_sha(PREREG),
        "owner_directive_sha256_lf": lf_sha(OWNER),
    }


def register():
    model = registered_model_payload()
    registry = ModelRegistry()
    if registry.current_status("M024") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M025_REQUIRES_PRESERVED_INCONCLUSIVE_M024")
    if any(entry.model_id == MODEL_ID for entry in registry.entries()):
        existing = registry.get(MODEL_ID)
        if dict(existing.model) != model or existing.model_hash != compute_model_hash(model):
            raise ValueError("M025_EXISTING_IDENTITY_MISMATCH")
        return existing
    parent = registry.get("M024")
    return registry.register(
        ModelSpec(
            model_id=MODEL_ID,
            model=model,
            status=ModelStatus.CREATED,
            hypothesis={
                "observation": "M024 closed 35 cycles at Q1 but did not measure size capacity.",
                "hypothesis": (
                    "Increasing Q eventually lowers full-cycle throughput when observed "
                    "flow cannot complete entry and return quantities."
                ),
                "change": (
                    "Run eleven independent proportional-capital scenarios with only Q "
                    "changed and growth expansion disabled."
                ),
                "expected_effect": (
                    "Locate a robust throughput-capacity region or show that no knee is "
                    "observed up to Q5000 under the frozen exogenous tape."
                ),
                "reason_for_new_model": (
                    "Order quantity materially changes fill completion, residual inventory "
                    "and capital requirements."
                ),
            },
            lineage={
                "parent_model_id": "M024",
                "ancestor_chain": (*parent.lineage.ancestor_chain, "M024"),
                "change_category": "OWNER_ORDER_SIZE_CAPACITY_CURVE",
                "change_summary": "Controlled eleven-size Q curve with proportional capital.",
                "references": {
                    "parent_result": "reports/usdcusdt/M024-3h-result.json",
                    "owner_directive": str(OWNER),
                    "preregistration": str(PREREG),
                },
            },
        )
    )


if __name__ == "__main__":
    result = register()
    print(json.dumps({"MODEL_ID": result.model_id, "MODEL_HASH": result.model_hash}))
