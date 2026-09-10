"""Append-only registration for OWNER-authorized M026."""

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

MODEL_ID = "M026"
SPEC = Path("docs/microstructure/M026_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M026_DYNAMIC_HOTLINE_321_PREREGISTRATION.md")
OWNER = Path("docs/microstructure/M026_DYNAMIC_HOTLINE_321_OWNER_DIRECTIVE.md")


def validate_registration_design(design: dict[str, Any]) -> None:
    expected = {
        "model_id": MODEL_ID,
        "strategy": "DYNAMIC_HOTLINE_321_PREAGED_SLOT_GRID_V1",
        "parent_model_id": "M024",
        "supporting_diagnostic": "M025",
        "source_day": "2025-01-01",
        "start": "2025-01-01T00:00:00Z",
        "end_exclusive": "2025-01-01T03:00:00Z",
        "economic_duration_hours": 3,
        "initial_slot_base_usdt_eq": "1",
        "quantity_quantization": "ROUND_HALF_UP_HISTORICAL_STEP_MIN_ONE",
        "normalized_balance_quantum": "0.00000001",
        "slot_base_balance_quantization": (
            "ROUND_DOWN_TO_NORMALIZED_BALANCE_QUANTUM_AT_NEW_EPOCH"
        ),
        "levels_per_side": 15,
        "initial_physical_orders": 60,
        "initial_operational_slot_units": 140,
        "mobility_slot_units_per_asset_side": 8,
        "initial_architectural_slot_units": 156,
        "hard_simulated_open_order_cap": 200,
        "physical_gate_min_cycles_3h": 38,
        "slot_gate_min_cycles_3h": 60,
        "runs": 1,
        "negative_exit_allowed": False,
        "capital_injection": False,
        "day2_authorized": False,
        "extension_authorized": False,
        "automatic_successor_authorized": False,
    }
    for key, value in expected.items():
        if type(design.get(key)) is not type(value) or design[key] != value:
            raise ValueError(f"M026_OWNER_POLICY_MISMATCH:{key}")


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
        raise ValueError("M026_REQUIRES_PRESERVED_INCONCLUSIVE_M024")
    if registry.current_status("M025") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M026_REQUIRES_PRESERVED_INCONCLUSIVE_M025")
    if any(entry.model_id == MODEL_ID for entry in registry.entries()):
        existing = registry.get(MODEL_ID)
        if dict(existing.model) != model or existing.model_hash != compute_model_hash(model):
            raise ValueError("M026_EXISTING_IDENTITY_MISMATCH")
        return existing
    parent = registry.get("M024")
    return registry.register(
        ModelSpec(
            model_id=MODEL_ID,
            model=model,
            status=ModelStatus.CREATED,
            hypothesis={
                "observation": (
                    "M024 produced 35 cycles and M025 peaked at 37, with static geometry."
                ),
                "hypothesis": (
                    "A causal moving 3/2/1 grid concentrates real capital near the "
                    "hotline while retaining useful old FIFO age."
                ),
                "change": (
                    "Replace M024's static 50-level triangle with a 15-level dynamic "
                    "3/2/1 slot grid and real per-asset mobility buffers."
                ),
                "expected_effect": (
                    "Exceed 37 physical cycles and produce at least 60 slot-equivalent "
                    "cycles in the same three hours."
                ),
                "reason_for_new_model": (
                    "Hotline mobility, variable order sizing and slot-weight semantics "
                    "materially change strategy mechanics."
                ),
            },
            lineage={
                "parent_model_id": "M024",
                "ancestor_chain": (*parent.lineage.ancestor_chain, "M024"),
                "change_category": "OWNER_DYNAMIC_HOTLINE_321_SLOT_GRID",
                "change_summary": (
                    "Causal 3/2/1 moving grid with real mobility capital and preserved aged orders."
                ),
                "references": {
                    "supporting_diagnostic": (
                        "reports/usdcusdt/M025-order-size-capacity-result.json"
                    ),
                    "owner_directive": str(OWNER),
                    "preregistration": str(PREREG),
                },
            },
        )
    )


if __name__ == "__main__":
    result = register()
    print(json.dumps({"MODEL_ID": result.model_id, "MODEL_HASH": result.model_hash}))
