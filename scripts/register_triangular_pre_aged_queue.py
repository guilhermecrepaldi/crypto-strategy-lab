"""Register M024 append-only; importing this module never mutates the registry."""

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

MODEL_ID = "M024"
SPEC = Path("docs/microstructure/M024_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M024_TRIANGULAR_PRE_AGED_QUEUE_PREREGISTRATION.md")
OWNER = Path("docs/microstructure/M024_TRIANGULAR_PRE_AGED_QUEUE_OWNER_DIRECTIVE.md")


def validate_registration_design(design: dict[str, Any]) -> None:
    expected = {
        "model_id": MODEL_ID,
        "strategy": "TRIANGULAR_PRE_AGED_QUEUE_V1",
        "order_mode": "NORMALIZED_1_USDC_NON_EXECUTABLE_PRE_AGED_FIFO",
        "parent_model_id": "M023",
        "source_day": "2025-01-01",
        "start": "2025-01-01T00:00:00Z",
        "end_exclusive": "2025-01-01T03:00:00Z",
        "economic_duration_hours": 3,
        "normalized_quantity_usdc": "1",
        "virtual_filter_override": "MIN_NOTIONAL_ONLY",
        "historical_tick_size": "0.0001",
        "historical_step_size": "1",
        "execution_profile": "B_REALISTIC_CONSERVATIVE",
        "execution_envelope": "PRICE_PRIORITY",
        "fee_assumption": "FROZEN_PROFILE_ZERO_CONDITIONAL_NOT_ACCOUNT_FACT",
        "initial_usdt": "74.9900",
        "initial_usdc": "75",
        "initial_marked_equity": "150.1325",
        "logical_price_levels_per_side": 50,
        "initial_double_depth_levels_per_side": 25,
        "initial_max_queue_columns": 2,
        "initial_orders_per_side": 75,
        "initial_open_orders": 150,
        "hard_simulated_open_order_cap": 200,
        "initial_anchor_bid": "1.0019",
        "initial_anchor_ask": "1.0020",
        "initial_mark_price": "1.0019",
        "buy_level_rule": "INITIAL_ASK_MINUS_LEVEL_RANK_TICKS",
        "sell_level_rule": "INITIAL_BID_PLUS_LEVEL_RANK_TICKS",
        "same_activation_queue_rule": "PUBLIC_THEN_OWN_SUBMISSION_TIME_ORDER_ID",
        "later_activation_queue_rule": "SEGMENTED_PUBLIC_BARRIER_BEFORE_NEW_OWN_COHORT",
        "later_public_barrier_rule": "MAX_ZERO_DISPLAYED_PUBLIC_MINUS_REPRESENTED_PUBLIC_REMAINING",
        "public_cancellation_credit": False,
        "global_liquidity_consumption": "ONCE_PER_PHYSICAL_SCENARIO",
        "minimum_profit_ticks": 1,
        "reserve": "0",
        "aged_order_retention": True,
        "aged_order_distance_rule": "KEEP_WHILE_PASSIVE_AND_INSIDE_CURRENT_50_LEVEL_SIDE_WINDOW",
        "free_eviction_rule": "FARTHEST_THEN_YOUNGEST_FREE_ENTRY_AFTER_CANCEL_ACK",
        "owned_return_priority": "OLDEST_LOT_THEN_LOT_ID",
        "owned_return_semantics": "CAUSAL_PASSIVE_ECONOMIC_FRONTIER",
        "partial_fill_policy": (
            "RESIDUAL_RETAINS_FIFO; "
            "IF_CANCEL_ACK_LEAVES_SUBSTEP_LOT_LOCK_IT_WITHOUT_RETURN_OR_CYCLE"
        ),
        "activation_cross_policy": "REJECT_RELEASE_WITHOUT_QUEUE_AGE",
        "queue_policy": (
            "M023_DISPLAYED_DEPTH_NO_CANCELLATION_CREDIT_STRICT_COMPATIBLE_"
            "TRADE_THROUGH_WITH_SEGMENTED_OWN_FIFO"
        ),
        "cancel_ack_precedence": "DUE_ACK_BEFORE_CURRENT_MARKET_EVENT",
        "growth_pool_asset": "USDT_EQ_REALIZED_COMPLETED_CYCLE_PROFIT_ONLY",
        "own_buy_budget": "FREE_CASH_MINUS_GROWTH_POOL_MINUS_UNBACKED_SELL_RETURN_OBLIGATIONS",
        "growth_candidate_order": "LEVEL_ASCENDING_THEN_BUY_THEN_SELL",
        "growth_sell_rule": "BLOCK_WITHOUT_REAL_UNRESERVED_USDC_NO_FREE_CONVERSION",
        "rectangle_denominator": "ALL_PHYSICALLY_ACTIVE_FREE_ENTRY_LEVELS_BOTH_SIDES",
        "rectangle_target_depth": 8,
        "counterfactual_mode": "DIAGNOSTIC_ONLY_CAUSAL_BRANCH_NORMAL_LATENCY",
        "counterfactual_creating_trade_eligible": False,
        "counterfactual_replaces_physical_c2": True,
        "counterfactual_censored_cases_visible": True,
        "run_count_authorized": 1,
        "target_cycles": 30,
        "target_cycles_per_hour": "10",
        "negative_exit_allowed": False,
        "sell_price_floor": "OWNED_USDC_ASSET_BASIS_PLUS_ONE_TICK",
        "breakeven_positive_cycle": False,
        "capital_injection": False,
        "cutoff_liquidation": False,
        "parameter_sweep": False,
        "day2_authorized": False,
        "extension_authorized": False,
        "automatic_successor_authorized": False,
    }
    for key, value in expected.items():
        if type(design.get(key)) is not type(value) or design[key] != value:
            raise ValueError(f"M024_OWNER_POLICY_MISMATCH:{key}")


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
    if registry.current_status("M023") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M024_REQUIRES_PRESERVED_INCONCLUSIVE_M023")
    if any(entry.model_id == MODEL_ID for entry in registry.entries()):
        existing = registry.get(MODEL_ID)
        if dict(existing.model) != model or existing.model_hash != compute_model_hash(model):
            raise ValueError("M024_EXISTING_IDENTITY_MISMATCH")
        return existing
    parent = registry.get("M023")
    return registry.register(
        ModelSpec(
            model_id=MODEL_ID,
            model=model,
            status=ModelStatus.CREATED,
            hypothesis={
                "observation": (
                    "M023 removed the self-cross/post-only storm but completed four "
                    "positive cycles in three hours under public FIFO and price recovery."
                ),
                "hypothesis": (
                    "Independently funded own orders already resting in segmented FIFO "
                    "can preserve column-two age when column one completes."
                ),
                "change": (
                    "Use the OWNER-frozen triangular same-price queue geometry, shared "
                    "public queue cohorts, owned-return priority and realized-profit growth."
                ),
                "expected_effect": (
                    "Measure physical throughput, column pre-aging and capital efficiency "
                    "without transferring priority or injecting capital."
                ),
                "reason_for_new_model": (
                    "Multiple physical FIFO columns and separately owned capital materially "
                    "change M023's single-order mechanics."
                ),
            },
            lineage={
                "parent_model_id": "M023",
                "ancestor_chain": (*parent.lineage.ancestor_chain, "M023"),
                "change_category": "OWNER_TRIANGULAR_PRE_AGED_QUEUE_MECHANICS",
                "change_summary": "Segmented own-order FIFO with independently funded columns.",
                "references": {
                    "parent_result": "reports/usdcusdt/M023-3h-result.json",
                    "owner_directive": str(OWNER),
                    "preregistration": str(PREREG),
                },
            },
        )
    )


if __name__ == "__main__":
    result = register()
    print(json.dumps({"MODEL_ID": result.model_id, "MODEL_HASH": result.model_hash}))
