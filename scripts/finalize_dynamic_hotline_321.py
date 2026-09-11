"""Register the completed M026 result without replaying market events."""

from __future__ import annotations

import json
from decimal import Decimal as D

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from crypto_strategy_lab.ml.model_registry import (
    BackendSpec,
    EvaluationSpec,
    ModelRegistry,
    ModelStatus,
    RunSpec,
)
from scripts.run_dynamic_hotline_321 import OUTPUT, RESULT

SOURCE_COMMIT = "9e0664faf79d172a2a8a7dc4e800504712983cfd"
EXPECTED_RUN_HASH = "9ddb531b506225885a02290d04eb57eb172be33aba88562f1e654b83f526fb7c"


def finalize() -> dict:
    """Append registry evidence and add only derived metadata to the result."""
    result = json.loads(RESULT.read_bytes())
    metrics = result["METRICS"]
    if (
        result.get("run_hash") != EXPECTED_RUN_HASH
        or result.get("published_config_sha") != SOURCE_COMMIT
        or result.get("RUN_STATUS") != "COMPLETE"
        or metrics.get("AUDIT") != "PASS_M026_INDEPENDENT_LEDGER_AND_TERMINAL_AUDIT"
        or metrics.get("PHYSICAL_CYCLES") != 30
        or metrics.get("SLOT_EQUIVALENT_CYCLES") != 90
        or metrics.get("PHYSICAL_GATE_GT_12_3333_PASS") is not False
        or metrics.get("SLOT_GATE_20_PER_HOUR_PASS") is not True
    ):
        raise ValueError("M026_FINAL_RESULT_IDENTITY_MISMATCH")

    run_manifest = json.loads((OUTPUT / "run-manifest.json").read_bytes())
    physical_paths = (
        OUTPUT / "run-manifest.json",
        OUTPUT / "execution-audit.jsonl",
        OUTPUT / "terminal-engine-state.json",
        OUTPUT / "independent-audit.json",
    )
    physical_files = {str(path): file_sha(path) for path in physical_paths}

    registry = ModelRegistry()
    if registry.current_status("M026") != ModelStatus.CREATED:
        raise ValueError("M026_FINALIZATION_REQUIRES_CREATED_STATUS")

    scenario_event = registry.append_scenario(
        "M026",
        {
            "scenario": {
                "name": "M026_DYNAMIC_HOTLINE_321_3H",
                "execution_profile": "B_REALISTIC_CONSERVATIVE",
                "execution_envelope": "PRICE_PRIORITY",
                "initial_marked_equity": metrics["INITIAL_TOTAL_MARKED"],
                "capital_mode": "PHYSICAL_DYNAMIC_NORMALIZED_MECHANICS_BANK",
                "campaign_run_hash": EXPECTED_RUN_HASH,
                "normalized_non_executable": True,
            }
        },
    )
    scenario_hash = scenario_event["payload"]["SCENARIO_HASH"]
    run_event = registry.append_run(
        "M026",
        RunSpec(
            scenario_hash=scenario_hash,
            dataset_hash=run_manifest["evidence"]["validation"]["input_sha256"],
            campaign_snapshot_id=result["AUDIT"]["terminal_sha256"],
            interval={"start": result["start"], "end_exclusive": result["end_exclusive"]},
            code_commit=SOURCE_COMMIT,
            technical_revision="M026_DYNAMIC_HOTLINE_321_V1",
            backend=BackendSpec(backend="CPU"),
            initial_capital=D(metrics["INITIAL_TOTAL_MARKED"]),
            capital_mode="NORMALIZED_MECHANICS_PROBE",
            run={
                "artifact_directory": str(OUTPUT),
                "campaign_run_hash": EXPECTED_RUN_HASH,
                "audit_status": metrics["AUDIT"],
                "event_replay_during_finalization": False,
            },
        ),
    )
    registry.transition(
        "M026",
        ModelStatus.RUNNING,
        reason="Register the one completed OWNER-authorized M026 physical run",
    )
    registry.append_evaluation(
        "M026",
        EvaluationSpec(
            scenario_hash=scenario_hash,
            campaign_snapshot_id=result["AUDIT"]["terminal_sha256"],
            run_hash=run_event["payload"]["RUN_HASH"],
            comparison={
                "parent": "M024",
                "supporting_reference": "M025_BEST_Q5000",
                "m024_physical_cycles_per_hour": "11.6666666666666667",
                "m025_best_physical_cycles_per_hour": "12.3333333333333333",
                "m026_physical_cycles_per_hour": metrics["PHYSICAL_CYCLES_PER_HOUR"],
            },
            criteria={
                "physical_audit_pass": True,
                "physical_gate_pass": False,
                "slot_gate_pass": True,
                "live_executable_result": False,
                "strategy_pass": False,
                "event_rerun_performed": False,
            },
            metrics={
                "physical_cycles": metrics["PHYSICAL_CYCLES"],
                "physical_cycles_per_hour": metrics["PHYSICAL_CYCLES_PER_HOUR"],
                "slot_equivalent_cycles": metrics["SLOT_EQUIVALENT_CYCLES"],
                "slot_equivalent_cycles_per_hour": metrics["SLOT_EQUIVALENT_CYCLES_PER_HOUR"],
                "final_marked_equity": metrics["FINAL_TOTAL_MARKED"],
                "realized_cycle_pnl": metrics["REALIZED_CYCLE_PNL"],
                "realized_disposal_pnl": metrics["REALIZED_DISPOSAL_PNL"],
                "unrealized_pnl": metrics["UNREALIZED_PNL"],
                "underfunded_promotions": metrics["UNDERFUNDED_PROMOTIONS"],
                "mobility_reserve_exhaustion_events": metrics["MOBILITY_RESERVE_EXHAUSTION_EVENTS"],
            },
            replay={
                "start": result["start"],
                "end_exclusive": result["end_exclusive"],
                "campaign_run_hash": EXPECTED_RUN_HASH,
            },
            decision={
                "status": "INCONCLUSIVE",
                "reason": (
                    "Physical throughput gate failed while the weighted slot ruler passed; "
                    "the normalized exogenous-tape probe does not establish live capacity."
                ),
            },
        ),
    )
    registry.transition(
        "M026",
        ModelStatus.EVALUATED,
        reason="Physical ledger and terminal audit reconciled the only authorized run",
    )
    registry.transition(
        "M026",
        ModelStatus.INCONCLUSIVE,
        reason="Physical gate failed; slot gate alone cannot establish physical acceleration",
    )

    result["REGISTRY"] = {
        "status": "INCONCLUSIVE",
        "scenario_count": 1,
        "registry_run_hash": run_event["payload"]["RUN_HASH"],
        "physical_campaign_hash": canonical_hash(physical_files),
        "physical_file_sha256": physical_files,
        "event_replay_during_finalization": False,
    }
    result["MODEL_STATUS"] = "INCONCLUSIVE"
    result["RUN_STATUS"] = "COMPLETE_INCONCLUSIVE_NORMALIZED_MECHANICS"
    write_json(OUTPUT / "summary.json", result)
    write_json(RESULT, result)
    return result


if __name__ == "__main__":
    value = finalize()
    print(
        json.dumps(
            {
                "MODEL": value["MODEL"],
                "MODEL_STATUS": value["MODEL_STATUS"],
                "PHYSICAL_CYCLES": value["METRICS"]["PHYSICAL_CYCLES"],
                "SLOT_EQUIVALENT_CYCLES": value["METRICS"]["SLOT_EQUIVALENT_CYCLES"],
                "RERUN": False,
            },
            sort_keys=True,
        )
    )
