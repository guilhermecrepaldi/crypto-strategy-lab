"""Register the reviewed M020 zonal ping-pong design append-only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelSpec, ModelStatus

SPEC = Path("docs/microstructure/M020_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M020_ZONAL_PING_PONG_PREREGISTRATION.md")
OWNER = Path("docs/microstructure/STABLECOIN_ZONAL_PING_PONG_OWNER_DIRECTIVE.md")
OCCUPANCY = Path("reports/usdcusdt/M020-price-occupancy-2025.json")


def lf_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def register():
    design = json.loads(SPEC.read_bytes())
    if (
        design["model_id"] != "M020"
        or design["strategy"] != "STABLECOIN_ZONAL_PING_PONG_5H_V1"
        or design["initial_total_equity"] != "100"
        or design["physical_band_count"] != 9
        or design["order_notional_mode"] != "NORMALIZED_1_USDT_NON_EXECUTABLE"
        or design["virtual_filter_override"] != "MIN_NOTIONAL_ONLY"
        or design["negative_exit_allowed"] is not False
        or design["economic_duration_hours"] != 5
        or design["day2_authorized"] is not False
    ):
        raise ValueError("M020_OWNER_POLICY_MISMATCH")
    occupancy = json.loads(OCCUPANCY.read_bytes())
    if (
        occupancy["ranges"]["P80"]["low"] != "0.99940"
        or occupancy["ranges"]["P80"]["high"] != "1.00030"
        or occupancy["record_count"] != 166_291_613
    ):
        raise ValueError("M020_OCCUPANCY_AUTHORITY_MISMATCH")
    registry = ModelRegistry()
    if any(entry.model_id == "M020" for entry in registry.entries()):
        return registry.get("M020")
    parent = registry.get("M019")
    model = {
        **design,
        "spec_sha256_lf": lf_sha(SPEC),
        "preregistration_sha256_lf": lf_sha(PREREG),
        "owner_directive_sha256_lf": lf_sha(OWNER),
        "occupancy_sha256_lf": lf_sha(OCCUPANCY),
    }
    result = registry.register(
        ModelSpec(
            model_id="M020",
            model=model,
            status=ModelStatus.CREATED,
            hypothesis={
                "observation": (
                    "M019 completed10 D1 cycles and then concentrated capital in inventory, "
                    "including an18.503-hour cycle plateau."
                ),
                "hypothesis": (
                    "Immutable price zones with one unresolved sequence per zone and rolling "
                    "four-by-four coverage can preserve more independent recycling capacity."
                ),
                "change": (
                    "Replace mid-following ladder offsets with a full-2025 P80 fixed map, "
                    "one sequence per band and normalized one-USDC throughput units for5h."
                ),
                "expected_effect": (
                    "Measure structural complete-cycle capacity and concentration without "
                    "assuming profit optimization or a minimum cycle result."
                ),
                "reason_for_new_model": (
                    "Fixed retrospective zones, bidirectional roundtrips, normalized filters "
                    "and a five-hour objective materially change M019 semantics."
                ),
            },
            lineage={
                "parent_model_id": "M019",
                "ancestor_chain": (*parent.lineage.ancestor_chain, "M019"),
                "change_category": "OWNER_ZONAL_PING_PONG_5H",
                "change_summary": (
                    "New fixed-zone normalized throughput diagnostic; M019 preserved."
                ),
                "references": {
                    "parent_observation": "M019_DAY1_INVENTORY_LOCK",
                    "owner_directive": str(OWNER),
                    "occupancy": str(OCCUPANCY),
                },
            },
        )
    )
    print(json.dumps({"MODEL_ID": result.model_id, "MODEL_HASH": result.model_hash}))
    return result


if __name__ == "__main__":
    register()
