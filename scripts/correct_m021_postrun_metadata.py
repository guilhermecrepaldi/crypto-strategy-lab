"""Append the factual M021 active-time clarification without changing physical evidence."""

from __future__ import annotations

import json
from pathlib import Path

from crypto_strategy_lab.microstructure.recovery_reserve_study import write_json
from crypto_strategy_lab.ml.model_registry import EvaluationSpec, ModelRegistry, ModelStatus

PHYSICAL = Path(
    "artifacts/usdcusdt/l2-monthly-samples/M021/OWNER_GATED_5H/PRICE_PRIORITY/summary.json"
)
RESULT = Path("reports/usdcusdt/M021-5h-result.json")


def correct() -> dict:
    physical = json.loads(PHYSICAL.read_bytes())
    result = json.loads(RESULT.read_bytes())
    physical_times = {row["SLOT"]: row["ACTIVE_TIME_US"] for row in physical["ALL_SLOTS"]}
    result_times = {row["SLOT"]: row["ACTIVE_TIME_US"] for row in result["ALL_SLOTS"]}
    changed = sorted(slot for slot, value in physical_times.items() if result_times[slot] != value)
    if changed:
        raise ValueError(f"M021_UNEXPECTED_ACTIVE_TIME_CHANGE:{changed}")
    result["REPORTING_CORRECTION"] = {
        "scope": "DEFENSIVE_CODE_HARDENING_NO_M021_VALUE_CHANGED",
        "reason": (
            "The rejected-status predicate was broadened defensively, but all 182 M021 "
            "post-only rejections had activation_evaluated_us=None and were already excluded."
        ),
        "active_time_changed_slots": 0,
        "economic_fields_changed": False,
        "economic_replay_repeated": False,
        "physical_summary_preserved": str(PHYSICAL),
    }
    write_json(RESULT, result)

    registry = ModelRegistry()
    if registry.current_status("M021") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M021_CORRECTION_REQUIRES_INCONCLUSIVE_STATUS")
    events = [json.loads(line) for line in registry.registry_path.read_text().splitlines()]
    run = next(
        row["payload"]
        for row in reversed(events)
        if row["event_type"] == "RUN_REGISTERED" and row["payload"]["model_id"] == "M021"
    )
    correction = registry.append_evaluation(
        "M021",
        EvaluationSpec(
            scenario_hash=run["SCENARIO_HASH"],
            campaign_snapshot_id=run["campaign_snapshot_id"],
            run_hash=run["RUN_HASH"],
            comparison={"scope": "POST_RUN_REPORTING_FACT_CORRECTION"},
            criteria={"physical_and_derived_active_time_must_match": True},
            metrics={
                "active_time_changed_slots": 0,
                "rejected_post_only_orders": 182,
                "economic_fields_changed": False,
                "economic_replay_repeated": False,
            },
            replay={"physical_summary": str(PHYSICAL), "replayed": False},
            decision={
                "status": "FACTUAL_CORRECTION",
                "supersedes_claim": "ACTIVE_TIME_US_ONLY_REPORTING_CORRECTION",
                "correct_statement": (
                    "Defensive predicate hardening only; no M021 active-time or economic "
                    "value changed."
                ),
            },
        ),
    )
    return {
        "active_time_changed_slots": 0,
        "evaluation_hash": correction["payload"]["EVALUATION_HASH"],
    }


if __name__ == "__main__":
    print(json.dumps(correct(), sort_keys=True))
