"""Register the reviewed M023 serial hot-line experiment append-only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelSpec, ModelStatus

SPEC = Path("docs/microstructure/M023_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M023_SERIAL_HOT_LINE_PREREGISTRATION.md")
OWNER = Path("docs/microstructure/M023_SERIAL_HOT_LINE_OWNER_DIRECTIVE.md")


def lf_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def validate_registration_design(design: dict) -> None:
    if (
        design["model_id"] != "M023"
        or design["strategy"] != "SERIAL_HOT_LINE_PING_PONG_V1"
        or design["parent_model_id"] != "M022"
        or design["economic_duration_hours"] != 3
        or design["normalized_quantity_usdc"] != "1"
        or design["candidate_radar_addresses"] != 200
        or design["candidate_radar_anchor"] != "1.0020"
        or design["buy_deck_cards"] != 100
        or design["sell_deck_cards"] != 100
        or design["candidate_count_policy"]
        != "TWO_CONSTANT_100_CARD_VIRTUAL_DECKS"
        or design["hot_line_refill"]
        != "FILLED_MIDDLE_POSITION_REFILLED_FROM_SAME_SIDE_FREE_EDGE"
        or design["buy_template_eviction"] != "HIGHEST_PRICE_FREE_BUY_FIRST"
        or design["sell_template_eviction"] != "LOWEST_PRICE_FREE_SELL_FIRST"
        or design["owned_or_armed_template_eviction_allowed"] is not False
        or design["max_simultaneous_nonterminal_orders"] != 1
        or design["economic_sequence"] != "BUY_THEN_SELL_STRICTLY_ALTERNATING"
        or design["negative_exit_allowed"] is not False
        or design["day2_authorized"] is not False
        or design["extension_authorized"] is not False
    ):
        raise ValueError("M023_OWNER_POLICY_MISMATCH")


def register():
    design = json.loads(SPEC.read_bytes())
    validate_registration_design(design)
    registry = ModelRegistry()
    if registry.current_status("M022") != ModelStatus.REJECTED:
        raise ValueError("M023_REQUIRES_PRESERVED_REJECTED_M022")
    if any(entry.model_id == "M023" for entry in registry.entries()):
        return registry.get("M023")
    parent = registry.get("M022")
    model = {
        **design,
        "spec_sha256_lf": lf_sha(SPEC),
        "preregistration_sha256_lf": lf_sha(PREREG),
        "owner_directive_sha256_lf": lf_sha(OWNER),
    }
    result = registry.register(
        ModelSpec(
            model_id="M023",
            model=model,
            status=ModelStatus.CREATED,
            hypothesis={
                "observation": (
                    "M022 maintained nearly 160 open orders yet matched M021 at 19 "
                    "cycles and generated 18,492 post-only EXIT rejections."
                ),
                "hypothesis": (
                    "A broad virtual radar plus exactly one causal real order and strict "
                    "BUY-SELL alternation can remove internal execution impediments."
                ),
                "change": (
                    "Replace parallel lanes with one serial economic sequence; select the "
                    "hot-line price causally and treat profitable SELL as an economic floor."
                ),
                "expected_effect": (
                    "Eliminate self-competition and repeated unchanged-context rejection "
                    "while measuring physically achievable three-hour serial throughput."
                ),
                "reason_for_new_model": (
                    "Serial capital, virtual candidates, hot-line pricing and strict side "
                    "alternation materially change M022 order management."
                ),
            },
            lineage={
                "parent_model_id": "M022",
                "ancestor_chain": (*parent.lineage.ancestor_chain, "M022"),
                "change_category": "OWNER_SERIAL_HOT_LINE_MECHANICS",
                "change_summary": "Virtual candidate radar with one strict BUY-SELL lane.",
                "references": {
                    "parent_result": "reports/usdcusdt/M022-5h-result.json",
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
