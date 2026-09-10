"""Append-only registration for OWNER-authorized M027."""

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

MODEL_ID = "M027"
SPEC = Path("docs/microstructure/M027_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M027_MICRO_HOT_REALLOCATION_PREREGISTRATION.md")
OWNER = Path("docs/microstructure/M027_MICRO_HOT_REALLOCATION_OWNER_DIRECTIVE.md")


def validate_registration_design(design: dict[str, Any]) -> None:
    expected = {
        "model_id": "M027",
        "strategy": "MICRO_HOT_REALLOCATION_CONTROLLED_AB_V1",
        "parent_model_id": "M026",
        "source_day": "2026-05-01",
        "start": "2026-05-01T00:00:00Z",
        "end_exclusive": "2026-05-01T03:00:00Z",
        "scenarios": ["CONTROL", "TREATMENT"],
        "runs_per_scenario": 1,
        "validated_tick_size": "0.00001",
        "coarse_grid_spacing": "0.0001",
        "micro_offset": "0.00005",
        "initial_physical_orders": 60,
        "initial_operational_slot_units": 140,
        "mobility_slot_units_per_asset_side": 8,
        "initial_architectural_slot_units": 156,
        "micro_columns": 2,
        "micro_slots_per_order": 1,
        "capital_match_max_error_pct": "0.01",
        "hard_simulated_open_order_cap": 200,
        "negative_exit_allowed": False,
        "capital_injection": False,
        "day2_authorized": False,
        "extension_authorized": False,
        "automatic_successor_authorized": False,
    }
    for key, value in expected.items():
        if type(design.get(key)) is not type(value) or design[key] != value:
            raise ValueError(f"M027_OWNER_POLICY_MISMATCH:{key}")


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
        raise ValueError("M027_REQUIRES_PRESERVED_INCONCLUSIVE_M026")
    if any(entry.model_id == MODEL_ID for entry in registry.entries()):
        existing = registry.get(MODEL_ID)
        if dict(existing.model) != model or existing.model_hash != compute_model_hash(model):
            raise ValueError("M027_EXISTING_IDENTITY_MISMATCH")
        return existing
    parent = registry.get("M026")
    return registry.register(
        ModelSpec(
            model_id=MODEL_ID,
            model=model,
            status=ModelStatus.CREATED,
            hypothesis={
                "observation": (
                    "M026 produced all 30 physical cycles in HOT; MID/FAR produced zero."
                ),
                "hypothesis": (
                    "Reallocating FAR14/FAR15 slot capital to a legal two-column "
                    "micro-hot line increases physical roundtrips without added capital."
                ),
                "change": (
                    "Treatment only: remove FAR14/FAR15 and add two one-slot columns "
                    "at hotline +/-0.00005; matched control keeps M026 geometry."
                ),
                "expected_effect": (
                    "Treatment physical cycles exceed control; 1.20x is a strong-evidence "
                    "ruler, not a result-preservation gate."
                ),
                "reason_for_new_model": (
                    "Fine-price geometry and a controlled two-scenario tape materially "
                    "change experimental meaning."
                ),
            },
            lineage={
                "parent_model_id": "M026",
                "ancestor_chain": (*parent.lineage.ancestor_chain, "M026"),
                "change_category": "OWNER_MICRO_HOT_CAPITAL_REALLOCATION",
                "change_summary": (
                    "Matched A/B of FAR14/FAR15 versus two-column micro-hot on "
                    "validated fine-tick L2."
                ),
                "references": {
                    "owner_directive": str(OWNER),
                    "preregistration": str(PREREG),
                    "parent_result": "reports/usdcusdt/M026-3h-result.json",
                },
            },
        )
    )


if __name__ == "__main__":
    result = register()
    print(json.dumps({"MODEL_ID": result.model_id, "MODEL_HASH": result.model_hash}))
