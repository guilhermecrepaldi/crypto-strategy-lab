"""Register the reviewed M019 ladder design in the append-only authority."""

import hashlib
import json
from pathlib import Path

from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelSpec, ModelStatus


def lf_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def register():
    spec_path = Path("docs/microstructure/M019_MODEL_SPEC.json")
    prereg_path = Path("docs/microstructure/M019_ADAPTIVE_LADDER_PREREGISTRATION.md")
    owner_path = Path("docs/microstructure/ADAPTIVE_STABLECOIN_LADDER_OWNER_DIRECTIVE.md")
    design = json.loads(spec_path.read_bytes())
    if (
        design["model_id"] != "M019"
        or design["strategy"] != "ADAPTIVE_STABLECOIN_LADDER_V1"
        or design["initial_total_equity"] != "100"
        or design["buy_slots"] != 6
        or design["sell_slots"] != 6
        or design["negative_exit_allowed"] is not False
        or design["calendar_days"] != 1
    ):
        raise ValueError("M019_OWNER_POLICY_MISMATCH")
    registry = ModelRegistry()
    if any(entry.model_id == "M019" for entry in registry.entries()):
        return registry.get("M019")
    parent = registry.get("M015")
    model = {
        **design,
        "spec_sha256_lf": lf_sha(spec_path),
        "preregistration_sha256_lf": lf_sha(prereg_path),
        "owner_directive_sha256_lf": lf_sha(owner_path),
    }
    result = registry.register(
        ModelSpec(
            model_id="M019",
            model=model,
            status=ModelStatus.CREATED,
            hypothesis={
                "observation": (
                    "Serial observed-L2 control completed only9 positive cycles while "
                    "price-path diagnostics showed substantially more oscillation."
                ),
                "hypothesis": (
                    "Twelve small capital-backed logical quotes with persistent lots can "
                    "increase complete positive cycles without realizing losses or degrading "
                    "marked equity."
                ),
                "change": (
                    "Replace one serial lot and reserve release with six BUY and six SELL "
                    "slots, global liquidity consumption, lot memory and profit-only exits."
                ),
                "expected_effect": (
                    "Increase parallel turnover while exposing rather than liquidating "
                    "underwater inventory; no guarantee of1000 cycles."
                ),
                "reason_for_new_model": (
                    "Material OWNER change to capital ownership, parallelism, inventory and "
                    "exit semantics requires a new identity."
                ),
            },
            lineage={
                "parent_model_id": "M015",
                "ancestor_chain": (*parent.lineage.ancestor_chain, "M015"),
                "change_category": "OWNER_ADAPTIVE_STABLECOIN_LADDER",
                "change_summary": "New12-slot inventory ladder; B10/M014/M015/M018 preserved.",
                "references": {
                    "execution_diagnosis": "M018_DAY1_OBSERVED_L2",
                    "owner_directive": str(owner_path),
                },
            },
        )
    )
    print(json.dumps({"MODEL_ID": result.model_id, "MODEL_HASH": result.model_hash}))
    return result


if __name__ == "__main__":
    register()
