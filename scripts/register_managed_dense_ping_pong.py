"""Register the reviewed M022 order-manager comparison append-only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelSpec, ModelStatus

SPEC = Path("docs/microstructure/M022_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M022_ORDER_MANAGER_PREREGISTRATION.md")
OWNER = Path("docs/microstructure/M022_ORDER_MANAGER_OWNER_DIRECTIVE.md")


def lf_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def validate_registration_design(design: dict) -> None:
    if (
        design["model_id"] != "M022"
        or design["strategy"] != "DENSE_PING_PONG_ORDER_MANAGER_V2"
        or design["parent_model_id"] != "M021"
        or design["total_economic_lanes"] != 200
        or design["max_simultaneous_open_orders"] != 160
        or design["normalized_quantity_usdc"] != "1"
        or design["ping_pong_distance_ticks"] != 1
        or design["negative_exit_allowed"] is not False
        or design["economic_duration_hours"] != 5
        or design["day2_authorized"] is not False
    ):
        raise ValueError("M022_OWNER_POLICY_MISMATCH")


def register():
    design = json.loads(SPEC.read_bytes())
    validate_registration_design(design)
    registry = ModelRegistry()
    if registry.current_status("M021") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M022_REQUIRES_PRESERVED_INCONCLUSIVE_M021")
    if any(entry.model_id == "M022" for entry in registry.entries()):
        return registry.get("M022")
    parent = registry.get("M021")
    model = {
        **design,
        "spec_sha256_lf": lf_sha(SPEC),
        "preregistration_sha256_lf": lf_sha(PREREG),
        "owner_directive_sha256_lf": lf_sha(OWNER),
    }
    result = registry.register(
        ModelSpec(
            model_id="M022",
            model=model,
            status=ModelStatus.CREATED,
            hypothesis={
                "observation": (
                    "M021 completed 19 cycles but owned returns were repeatedly blocked "
                    "by free entries and most free quotes rested far from the market."
                ),
                "hypothesis": (
                    "Owned-return priority plus a causal floating free-quote window can "
                    "increase five-hour throughput under otherwise frozen M021 controls."
                ),
                "change": (
                    "Keep 200 economic lanes but cap open orders at 160, preempt only "
                    "unfilled free entries for returns, and float free entries over the "
                    "fixed M021 lattice near the causal midpoint."
                ),
                "expected_effect": (
                    "Reduce free-entry return conflicts and distant inactive quoting while "
                    "preserving queue, latency, capital, liquidity and one-tick economics."
                ),
                "reason_for_new_model": (
                    "Return claims, preemption, moving free addresses and the 160-order "
                    "manager materially change order management while M021 stays immutable."
                ),
            },
            lineage={
                "parent_model_id": "M021",
                "ancestor_chain": (*parent.lineage.ancestor_chain, "M021"),
                "change_category": "OWNER_ORDER_MANAGER_CONTROLLED_COMPARISON",
                "change_summary": "Return priority and floating free window; M021 preserved.",
                "references": {
                    "parent_result": "reports/usdcusdt/M021-5h-result.json",
                    "owner_directive": str(OWNER),
                    "preregistration": str(PREREG),
                },
            },
        )
    )
    print(json.dumps({"MODEL_ID": result.model_id, "MODEL_HASH": result.model_hash}))
    return result


if __name__ == "__main__":
    register()
