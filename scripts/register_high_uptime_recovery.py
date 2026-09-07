"""Register the reviewed M012 design in the existing append-only model authority."""

import hashlib
import json
from pathlib import Path

from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelSpec, ModelStatus


def register():
    spec_path = Path("docs/microstructure/M012_MODEL_SPEC.json")
    prereg = Path("docs/microstructure/M012_HIGH_UPTIME_RECOVERY_PREREGISTRATION.md")
    design = json.loads(spec_path.read_bytes())
    if (
        design["capital_mode"] != "COMPOUNDING"
        or design["strategy"] != "HIGH_UPTIME_DYNAMIC_RECOVERY"
        or design["reserve_profit_funding_ratio"] != "0.05"
        or design["reserve_target_ratio"] != "0.05"
    ):
        raise ValueError("OWNER_CAPITAL_POLICY_MISMATCH")
    registry = ModelRegistry()
    ancestor = registry.get("M007")
    model = dict(design)
    model["preregistration_sha256_lf"] = hashlib.sha256(
        prereg.read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest()
    model["spec_sha256_lf"] = hashlib.sha256(
        spec_path.read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest()
    result = registry.register(
        ModelSpec(
            model_id="M012",
            model=model,
            status=ModelStatus.CREATED,
            hypothesis={
                "observation": (
                    "Frozen B10 reality A accumulated multi-day capital lock and1"
                    "01 zero days by86.54% of frozen DEVELOPMENT; fixed100 result"
                    "s are auxiliary only."
                ),
                "hypothesis": (
                    "A5% funded dynamic recovery reserve and causal12/18/24h urge"
                    "ncy can preserve motor uptime with compounding capital and n"
                    "onzero reserve."
                ),
                "change": (
                    "New complete strategy:5% profit funding, dynamic5% target/no"
                    "nzerofloor, mandatory24h unlock state, current available ban"
                    "k compound sizing, reality execution."
                ),
                "expected_effect": (
                    "Reduce zero days and long holds while reinvesting95% of real"
                    "ized positive profit; test sustainability without guaranteei"
                    "ng liquidity."
                ),
                "reason_for_new_model": (
                    "Material OWNER strategy and capital-policy update; historica"
                    "l B10 remains immutable. M011 occupied and unchanged."
                ),
            },
            lineage={
                "parent_model_id": "M007",
                "ancestor_chain": (*ancestor.lineage.ancestor_chain, "M007"),
                "change_category": "OWNER_HIGH_UPTIME_COMPOUNDING_RECOVERY",
                "change_summary": (
                    "B10 recovery-policy successor; M007 canonical selector ances"
                    "try; not M011 mutation."
                ),
                "references": {
                    "historical_parent": "B10_FROZEN / RRV2_H1_B10_F0",
                    "artifact": design["b10_artifact_id"],
                },
            },
        )
    )
    print(json.dumps({"MODEL_ID": result.model_id, "MODEL_HASH": result.model_hash}))


if __name__ == "__main__":
    register()
