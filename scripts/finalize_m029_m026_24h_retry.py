"""Register and publish the completed M029 result without replaying market events."""

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
from scripts.run_m029_m026_24h_retry import OUTPUT, RESULT

SOURCE_COMMIT = "9dde81b16c5cd3144efc88c471d70407f1249af7"
EXPECTED_CAMPAIGN_RUN_HASH = (
    "b3055640e7d23aa83008e4d2f030bec014581eeb2ee4de7485e0d22e8b986ec6"
)
EXPECTED_AUDIT = "PASS_M029_M026_24H_LEDGER_TERMINAL_PREFIX_AND_RETURN_AUDIT"


def finalize() -> dict:
    """Append registry evidence and add derived registry metadata only."""
    result = json.loads(RESULT.read_bytes())
    metrics = result["METRICS"]
    audit = result["AUDIT"]
    if (
        result.get("model_id") != "M029"
        or result.get("MODEL") != "M029"
        or result.get("published_config_sha") != SOURCE_COMMIT
        or result.get("run_hash") != EXPECTED_CAMPAIGN_RUN_HASH
        or result.get("RUN_STATUS") != "COMPLETE"
        or audit.get("status") != EXPECTED_AUDIT
        or result.get("PREFIX_EQUIVALENCE", {}).get("STATUS")
        != "PASS_EXACT_M026_3H_PREFIX_EQUIVALENCE"
        or metrics.get("INITIAL_TOTAL_MARKED") != "156.25220000"
        or metrics.get("FINAL_TOTAL_MARKED") != "156.3012000000000000"
        or metrics.get("TOTAL_MARKED_GAIN") != "0.0490000000000000"
        or metrics.get("PHYSICAL_CYCLES") != 98
        or metrics.get("SLOT_EQUIVALENT_CYCLES") != 289
    ):
        raise ValueError("M029_FINAL_RESULT_IDENTITY_MISMATCH")

    manifest = json.loads((OUTPUT / "run-manifest.json").read_bytes())
    physical_paths = (
        OUTPUT / "run-manifest.json",
        OUTPUT / "execution-audit.jsonl",
        OUTPUT / "terminal-engine-state.json",
        OUTPUT / "independent-audit.json",
    )
    physical_files = {str(path): file_sha(path) for path in physical_paths}

    registry = ModelRegistry()
    if registry.current_status("M029") != ModelStatus.CREATED:
        raise ValueError("M029_FINALIZATION_REQUIRES_CREATED_STATUS")
    scenario_event = registry.append_scenario(
        "M029",
        {
            "scenario": {
                "name": "M029_M026_CORRECTED_FULL_DAY_RETRY",
                "execution_profile": "B_REALISTIC_CONSERVATIVE",
                "execution_envelope": "PRICE_PRIORITY",
                "initial_marked_equity": metrics["INITIAL_TOTAL_MARKED"],
                "capital_mode": "NORMALIZED_MECHANICS_PROBE",
                "campaign_run_hash": EXPECTED_CAMPAIGN_RUN_HASH,
                "normalized_non_executable": True,
            }
        },
    )
    scenario_hash = scenario_event["payload"]["SCENARIO_HASH"]
    run_event = registry.append_run(
        "M029",
        RunSpec(
            scenario_hash=scenario_hash,
            dataset_hash=manifest["evidence"]["validation"]["input_sha256"],
            campaign_snapshot_id=audit["terminal_sha256"],
            interval={"start": result["start"], "end_exclusive": result["end_exclusive"]},
            code_commit=SOURCE_COMMIT,
            technical_revision="M029_CANONICAL_CHECKPOINT_RETRY_V1",
            backend=BackendSpec(backend="CPU"),
            initial_capital=D(metrics["INITIAL_TOTAL_MARKED"]),
            capital_mode="NORMALIZED_MECHANICS_PROBE",
            run={
                "artifact_directory": str(OUTPUT),
                "campaign_run_hash": EXPECTED_CAMPAIGN_RUN_HASH,
                "audit_status": EXPECTED_AUDIT,
                "event_replay_during_finalization": False,
            },
        ),
    )
    registry.transition(
        "M029",
        ModelStatus.RUNNING,
        reason="Register the sole completed OWNER-authorized M029 physical run",
    )
    registry.append_evaluation(
        "M029",
        EvaluationSpec(
            scenario_hash=scenario_hash,
            campaign_snapshot_id=audit["terminal_sha256"],
            run_hash=run_event["payload"]["RUN_HASH"],
            comparison={
                "parent": "M026",
                "m026_3h_marked_equity": metrics["M026_3H_MARKED_EQUITY"],
                "m029_24h_marked_equity": metrics["FINAL_TOTAL_MARKED"],
                "m026_3h_physical_cycles": 30,
                "m029_24h_physical_cycles": metrics["PHYSICAL_CYCLES"],
            },
            criteria={
                "physical_audit_pass": True,
                "prefix_equivalence_pass": True,
                "live_executable_result": False,
                "strategy_pass": False,
                "event_rerun_performed": False,
            },
            metrics={
                "initial_marked_equity": metrics["INITIAL_TOTAL_MARKED"],
                "final_marked_equity": metrics["FINAL_TOTAL_MARKED"],
                "marked_gain": metrics["TOTAL_MARKED_GAIN"],
                "marked_gain_pct": metrics["TOTAL_MARKED_GAIN_PCT"],
                "post_3h_marked_gain_pct": metrics["POST_3H_MARKED_GAIN_PCT"],
                "physical_cycles": metrics["PHYSICAL_CYCLES"],
                "physical_cycles_per_hour": metrics["PHYSICAL_CYCLES_PER_HOUR"],
                "slot_equivalent_cycles": metrics["SLOT_EQUIVALENT_CYCLES"],
                "slot_cycles_per_hour": metrics["SLOT_EQUIVALENT_CYCLES_PER_HOUR"],
                "realized_cycle_pnl": metrics["REALIZED_CYCLE_PNL"],
                "realized_disposal_pnl": metrics["REALIZED_DISPOSAL_PNL"],
                "unrealized_pnl": metrics["UNREALIZED_PNL"],
            },
            replay={
                "start": result["start"],
                "end_exclusive": result["end_exclusive"],
                "campaign_run_hash": EXPECTED_CAMPAIGN_RUN_HASH,
            },
            decision={
                "status": "INCONCLUSIVE",
                "reason": (
                    "The normalized 24h development replay gained marked equity but "
                    "produced 98 physical cycles, far below 1000/day; live rank, fees, "
                    "minimum notional and endogenous impact remain unvalidated."
                ),
            },
        ),
    )
    registry.transition(
        "M029",
        ModelStatus.EVALUATED,
        reason="Full-day ledger, terminal, prefix and marked return reconciled",
    )
    registry.transition(
        "M029",
        ModelStatus.INCONCLUSIVE,
        reason=(
            "Positive normalized marked return but only 98 physical cycles/day and no "
            "live-executable evidence"
        ),
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
                "INITIAL": value["METRICS"]["INITIAL_TOTAL_MARKED"],
                "FINAL": value["METRICS"]["FINAL_TOTAL_MARKED"],
                "GAIN_PCT": value["METRICS"]["TOTAL_MARKED_GAIN_PCT"],
                "PHYSICAL_CYCLES": value["METRICS"]["PHYSICAL_CYCLES"],
                "RERUN": False,
            },
            sort_keys=True,
        )
    )
