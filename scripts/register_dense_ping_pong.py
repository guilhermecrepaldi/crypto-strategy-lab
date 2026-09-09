"""Register reviewed M021 dense ping-pong mechanics probe append-only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelSpec, ModelStatus

SPEC = Path("docs/microstructure/M021_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M021_DENSE_PING_PONG_PREREGISTRATION.md")
OWNER = Path("docs/microstructure/M021_DENSE_PING_PONG_OWNER_DIRECTIVE.md")
GRID = Path("reports/usdcusdt/M021-dense-grid.json")


def lf_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def validate_registration_design(design: dict, grid: dict) -> None:
    if (
        design["model_id"] != "M021"
        or design["strategy"] != "DENSE_200_SLOT_PING_PONG_MECHANICS_PROBE_V1"
        or design["total_logical_slots"] != 200
        or design["normalized_quantity_usdc"] != "1"
        or design["virtual_filter_override"] != "MIN_NOTIONAL_ONLY"
        or design["negative_exit_allowed"] is not False
        or design["economic_duration_hours"] != 5
        or design["day2_authorized"] is not False
        or grid["anchor"] != design["grid_anchor"]
        or grid["initial_usdt"] != design["initial_usdt"]
        or len(grid["buy_slots"]) != 100
        or len(grid["sell_slots"]) != 100
    ):
        raise ValueError("M021_OWNER_POLICY_MISMATCH")


def register():
    design = json.loads(SPEC.read_bytes())
    grid = json.loads(GRID.read_bytes())
    validate_registration_design(design, grid)
    registry = ModelRegistry()
    if registry.current_status("M020") != ModelStatus.REJECTED:
        raise ValueError("M021_REQUIRES_REJECTED_M020")
    if any(entry.model_id == "M021" for entry in registry.entries()):
        return registry.get("M021")
    parent = registry.get("M020")
    model = {
        **design,
        "spec_sha256_lf": lf_sha(SPEC),
        "preregistration_sha256_lf": lf_sha(PREREG),
        "owner_directive_sha256_lf": lf_sha(OWNER),
        "grid_sha256_lf": lf_sha(GRID),
    }
    result = registry.register(
        ModelSpec(
            model_id="M021",
            model=model,
            status=ModelStatus.CREATED,
            hypothesis={
                "observation": (
                    "M020 produced zero fills because its fixed P80 map did not overlap "
                    "the observed five-hour price path."
                ),
                "hypothesis": (
                    "A dense 200-slot immutable grid centered on the first causal L2 book "
                    "can expose whether one-tick ping-pong mechanics complete at all."
                ),
                "change": (
                    "Use 100 BUY-first and 100 SELL-first one-USDC slots around one frozen "
                    "causal anchor, without recentering or P80 selection."
                ),
                "expected_effect": (
                    "Measure normalized five-hour completed-cycle mechanics, fill distribution "
                    "and execution blockers without claiming profitability or capacity."
                ),
                "reason_for_new_model": (
                    "The causal anchor, 200 slots, capital near 200 and one-tick bilateral "
                    "state machines materially differ from M020."
                ),
            },
            lineage={
                "parent_model_id": "M020",
                "ancestor_chain": (*parent.lineage.ancestor_chain, "M020"),
                "change_category": "OWNER_DENSE_PING_PONG_MECHANICS_5H",
                "change_summary": "New normalized causal-anchor mechanics probe; M020 preserved.",
                "references": {
                    "parent_observation": "M020_ZERO_FILLS_PRICE_OUTSIDE_FIXED_P80_MAP",
                    "owner_directive": str(OWNER),
                    "grid": str(GRID),
                },
            },
        )
    )
    print(json.dumps({"MODEL_ID": result.model_id, "MODEL_HASH": result.model_hash}))
    return result


if __name__ == "__main__":
    register()
