"""Append-only registration for the corrected M026 full-day retry."""

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

MODEL_ID = "M029"
SPEC = Path("docs/microstructure/M029_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M029_M026_24H_TECHNICAL_RETRY_PREREGISTRATION.md")
OWNER = Path("docs/microstructure/M029_M026_24H_TECHNICAL_RETRY_OWNER_DIRECTIVE.md")


def validate_registration_design(design: dict[str, Any]) -> None:
    expected = {
        "model_id": MODEL_ID,
        "strategy": "M026_DYNAMIC_HOTLINE_321_TEMPORAL_REPLICATION_V1",
        "parent_model_id": "M026",
        "technical_failure_predecessor": "M028",
        "source_day": "2025-01-01",
        "start": "2025-01-01T00:00:00Z",
        "end_exclusive": "2025-01-02T00:00:00Z",
        "economic_duration_hours": 24,
        "only_economic_change_from_parent": "END_EXCLUSIVE_3H_TO_24H",
        "only_technical_change_from_m028": (
            "CANONICAL_JSON_CHECKPOINT_STATE_COMPARISON"
        ),
        "levels_per_side": 15,
        "initial_physical_orders": 60,
        "initial_operational_slot_units": 140,
        "mobility_slot_units_per_asset_side": 8,
        "initial_architectural_slot_units": 156,
        "hard_simulated_open_order_cap": 200,
        "prefix_equivalence_required": True,
        "prefix_reference_model": "M026",
        "prefix_end_exclusive": "2025-01-01T03:00:00Z",
        "runs": 1,
        "negative_exit_allowed": False,
        "capital_injection": False,
        "another_day_authorized": False,
        "extension_authorized": False,
        "automatic_successor_authorized": False,
    }
    for key, value in expected.items():
        if type(design.get(key)) is not type(value) or design[key] != value:
            raise ValueError(f"M029_OWNER_POLICY_MISMATCH:{key}")


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
        raise ValueError("M029_REQUIRES_PRESERVED_INCONCLUSIVE_M026")
    if registry.current_status("M028") != ModelStatus.INVALIDATED_TECHNICAL:
        raise ValueError("M029_REQUIRES_PRESERVED_INVALIDATED_M028")
    if any(entry.model_id == MODEL_ID for entry in registry.entries()):
        existing = registry.get(MODEL_ID)
        if dict(existing.model) != model or existing.model_hash != compute_model_hash(model):
            raise ValueError("M029_EXISTING_IDENTITY_MISMATCH")
        return existing
    parent = registry.get("M026")
    return registry.register(
        ModelSpec(
            model_id=MODEL_ID,
            model=model,
            status=ModelStatus.CREATED,
            hypothesis={
                "observation": (
                    "M028 reproduced M026's byte-identical 3h economic ledger but was "
                    "technically invalidated before the 21h extension by a raw checkpoint "
                    "representation comparison."
                ),
                "hypothesis": (
                    "The unchanged M026 engine can complete the full January 1 tape once "
                    "both checkpoint states are compared in one canonical representation."
                ),
                "change": (
                    "Canonicalize both 3h checkpoint states through deterministic JSON "
                    "before equality; change no economic or execution parameter."
                ),
                "expected_effect": (
                    "Pass the exact M026 prefix gate and measure 24h cycles and marked return."
                ),
                "reason_for_new_model": (
                    "M028 is terminal INVALIDATED_TECHNICAL and its one-run gate is consumed."
                ),
            },
            lineage={
                "parent_model_id": "M026",
                "ancestor_chain": [*parent.lineage.ancestor_chain, "M026"],
                "change_category": "TECHNICAL_RETRY_AND_OWNER_TEMPORAL_REPLICATION_24H",
                "change_summary": (
                    "Unchanged M026 full-day replication with canonical checkpoint comparison."
                ),
                "references": {
                    "owner_directive": str(OWNER),
                    "preregistration": str(PREREG),
                    "m028_failure": "reports/usdcusdt/M028-technical-failure.json",
                    "parent_result": "reports/usdcusdt/M026-3h-result.json",
                },
            },
        )
    )


if __name__ == "__main__":
    result = register()
    print(result.model_id, result.model_hash, result.status.value)
