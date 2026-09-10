"""Append-only M030 registration."""

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

MODEL_ID = "M030"
SPEC = Path("docs/microstructure/M030_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M030_HOTLINE_FIRST_REALLOCATION_PREREGISTRATION.md")
OWNER = Path("docs/microstructure/M030_HOTLINE_FIRST_REALLOCATION_OWNER_DIRECTIVE.md")


def validate_registration_design(design: dict[str, Any]) -> None:
    expected = {
        "model_id": MODEL_ID,
        "strategy": "HOTLINE_FIRST_DYNAMIC_321_REALLOCATION_V1",
        "parent_model_id": "M026",
        "supporting_full_day_evidence": "M029",
        "change_category": "OWNER_HOTLINE_CAPITAL_REALLOCATION",
        "source_day": "2025-01-01",
        "start": "2025-01-01T00:00:00Z",
        "end_exclusive": "2025-01-02T00:00:00Z",
        "economic_duration_hours": 24,
        "random_evaluation_seed": 13525809254189156280,
        "random_evaluation_hours_utc": [6, 12, 13],
        "evaluation_mask_affects_decisions": False,
        "hotline_first_capital_reallocation": True,
        "hot_target_slot_units_per_side": 45,
        "levels_per_side": 15,
        "mobility_slot_units_per_asset_side": 8,
        "initial_physical_orders": 60,
        "initial_operational_slot_units": 140,
        "hard_simulated_open_order_cap": 200,
        "negative_exit_allowed": False,
        "capital_injection": False,
        "runs": 1,
        "random_reroll_allowed": False,
        "another_day_authorized": False,
        "automatic_successor_authorized": False,
    }
    for key, value in expected.items():
        if type(design.get(key)) is not type(value) or design[key] != value:
            raise ValueError(f"M030_OWNER_POLICY_MISMATCH:{key}")


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
    if registry.current_status("M026") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M030_REQUIRES_PRESERVED_INCONCLUSIVE_M026")
    if registry.current_status("M029") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M030_REQUIRES_PRESERVED_INCONCLUSIVE_M029")
    if any(entry.model_id == MODEL_ID for entry in registry.entries()):
        existing = registry.get(MODEL_ID)
        if dict(existing.model) != model or existing.model_hash != compute_model_hash(model):
            raise ValueError("M030_EXISTING_IDENTITY_MISMATCH")
        return existing
    parent = registry.get("M026")
    return registry.register(
        ModelSpec(
            model_id=MODEL_ID,
            model=model,
            status=ModelStatus.CREATED,
            hypothesis={
                "observation": (
                    "M029 moved the hotline through 72 ticks but recorded 1907 "
                    "underfunded promotions and only 98 physical cycles in 24 hours."
                ),
                "hypothesis": (
                    "Reclaiming zero-fill legacy reservations for current HOT after causal "
                    "cancel ACK, while jumping directly to each book's final hotline, improves "
                    "matched random-hour throughput and HOT funding coverage."
                ),
                "change": (
                    "Priority becomes RETURN>HOT>MID>FAR>old zero-fill; multi-tick books "
                    "perform one final-target reconciliation."
                ),
                "expected_effect": (
                    "More complete current HOT coverage and more physical cycles in the "
                    "frozen matched hours without violating economic ownership."
                ),
                "reason_for_new_model": "OWNER explicitly authorized a material manager change.",
            },
            lineage={
                "parent_model_id": "M026",
                "ancestor_chain": [*parent.lineage.ancestor_chain, "M026"],
                "change_category": "OWNER_HOTLINE_CAPITAL_REALLOCATION",
                "change_summary": (
                    "ACK-gated zero-fill reallocation and direct causal hotline jumps."
                ),
                "references": {
                    "owner_directive": str(OWNER),
                    "preregistration": str(PREREG),
                    "parent_result": "reports/usdcusdt/M026-3h-result.json",
                    "baseline_result": "reports/usdcusdt/M029-m026-24h-result.json",
                },
            },
        )
    )


if __name__ == "__main__":
    result = register()
    print(result.model_id, result.model_hash, result.status.value)
