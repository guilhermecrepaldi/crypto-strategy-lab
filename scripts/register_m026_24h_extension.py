"""Append-only registration for the OWNER-authorized M026 full-day replication."""

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

MODEL_ID = "M028"
SPEC = Path("docs/microstructure/M028_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M028_M026_24H_EXTENSION_PREREGISTRATION.md")
OWNER = Path("docs/microstructure/M028_M026_24H_EXTENSION_OWNER_DIRECTIVE.md")


def validate_registration_design(design: dict[str, Any]) -> None:
    expected = {
        "model_id": MODEL_ID,
        "strategy": "M026_DYNAMIC_HOTLINE_321_TEMPORAL_REPLICATION_V1",
        "parent_model_id": "M026",
        "source_day": "2025-01-01",
        "start": "2025-01-01T00:00:00Z",
        "end_exclusive": "2025-01-02T00:00:00Z",
        "economic_duration_hours": 24,
        "only_change_from_parent": "END_EXCLUSIVE_3H_TO_24H",
        "levels_per_side": 15,
        "initial_physical_orders": 60,
        "initial_operational_slot_units": 140,
        "mobility_slot_units_per_asset_side": 8,
        "initial_architectural_slot_units": 156,
        "hard_simulated_open_order_cap": 200,
        "prefix_equivalence_required": True,
        "prefix_reference_model": "M026",
        "prefix_end_exclusive": "2025-01-01T03:00:00Z",
        "auxiliary_physical_ruler_24h": 304,
        "auxiliary_slot_ruler_24h": 480,
        "runs": 1,
        "negative_exit_allowed": False,
        "capital_injection": False,
        "another_day_authorized": False,
        "extension_authorized": False,
        "automatic_successor_authorized": False,
    }
    for key, value in expected.items():
        if type(design.get(key)) is not type(value) or design[key] != value:
            raise ValueError(f"M028_OWNER_POLICY_MISMATCH:{key}")


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
        raise ValueError("M028_REQUIRES_PRESERVED_INCONCLUSIVE_M026")
    if any(entry.model_id == MODEL_ID for entry in registry.entries()):
        existing = registry.get(MODEL_ID)
        if dict(existing.model) != model or existing.model_hash != compute_model_hash(model):
            raise ValueError("M028_EXISTING_IDENTITY_MISMATCH")
        return existing
    parent = registry.get("M026")
    return registry.register(
        ModelSpec(
            model_id=MODEL_ID,
            model=model,
            status=ModelStatus.CREATED,
            hypothesis={
                "observation": (
                    "M026 completed 30 physical cycles and increased marked equity by "
                    "0.0287996% in its frozen first three hours."
                ),
                "hypothesis": (
                    "The unchanged M026 engine can continue operating for the full "
                    "January 1 tape without a reset while preserving positive marked return."
                ),
                "change": (
                    "Change only the replay end from 03:00 to 24:00 UTC; preserve all "
                    "M026 strategy and execution parameters."
                ),
                "expected_effect": (
                    "Measure full-day cycles, cycles/hour and marked equity before/after; "
                    "no minimum return is assumed."
                ),
                "reason_for_new_model": (
                    "Replay duration is part of the immutable M026 model identity."
                ),
            },
            lineage={
                "parent_model_id": "M026",
                "ancestor_chain": (*parent.lineage.ancestor_chain, "M026"),
                "change_category": "OWNER_TEMPORAL_REPLICATION_24H",
                "change_summary": ("Unchanged M026 strategy on the complete January 1 UTC day."),
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
