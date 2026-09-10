"""Register the audited M030 result without replaying market events."""

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
from scripts.run_hotline_first_reallocation import OUTPUT, RESULT

SOURCE_COMMIT = "459d0237ae9005fd272a91e00de744c21da71435"
EXPECTED_RUN_HASH = "83483b9bfaaeae68f49c23504650a93f7e5701017a7c37a05d416d6095d376ee"
EXPECTED_AUDIT = "PASS_M030_HOTLINE_FIRST_LEDGER_TERMINAL_AND_MASK_AUDIT"


def finalize() -> dict:
    result = json.loads(RESULT.read_bytes())
    metrics = result["METRICS"]
    comparison = result["MATCHED_COMPARISON"]
    management = comparison["MANAGEMENT"]
    audit = result["AUDIT"]
    if (
        result.get("MODEL") != "M030"
        or result.get("published_config_sha") != SOURCE_COMMIT
        or result.get("run_hash") != EXPECTED_RUN_HASH
        or result.get("RUN_STATUS") != "COMPLETE_AUDITED_REPORTING_RECOVERY"
        or result.get("VERDICT") != "INCONCLUSIVE"
        or audit.get("status") != EXPECTED_AUDIT
        or result.get("REPORTING_RECOVERY", {}).get("EVENTS_DELIVERED_DURING_RECOVERY") != 0
        or metrics.get("M030_EVAL_PHYSICAL_CYCLES") != 13
        or comparison.get("BASELINE", {}).get("PHYSICAL_CYCLES") != 6
        or comparison.get("PHYSICAL_CYCLE_IMPROVEMENT_PCT")
        != "116.6666666666666666666666667"
        or metrics.get("PHYSICAL_CYCLES") != 170
        or metrics.get("SLOT_EQUIVALENT_CYCLES") != 509
        or metrics.get("INITIAL_TOTAL_MARKED") != "156.25220000"
        or metrics.get("FINAL_TOTAL_MARKED") != "156.3188000000000000"
        or metrics.get("TOTAL_MARKED_GAIN") != "0.0666000000000000"
        or management.get("COVERAGE_PASS") is not True
        or management.get("STRANDED_REDUCTION_PASS") is not False
        or management.get("MANAGEMENT_SUCCESS_PASS") is not False
    ):
        raise ValueError("M030_FINAL_RESULT_IDENTITY_MISMATCH")

    manifest = json.loads((OUTPUT / "run-manifest.json").read_bytes())
    physical_paths = (
        OUTPUT / "run-manifest.json",
        OUTPUT / "execution-audit.jsonl",
        OUTPUT / "terminal-engine-state.json",
        OUTPUT / "failure.json",
        OUTPUT / "posthoc-independent-audit.json",
    )
    physical_files = {str(path): file_sha(path) for path in physical_paths}

    registry = ModelRegistry()
    if registry.current_status("M030") != ModelStatus.CREATED:
        raise ValueError("M030_FINALIZATION_REQUIRES_CREATED_STATUS")
    scenario_event = registry.append_scenario(
        "M030",
        {
            "scenario": {
                "name": "M030_HOTLINE_FIRST_RANDOM_3H_FULL_DAY_ENGINE",
                "execution_profile": "B_REALISTIC_CONSERVATIVE",
                "execution_envelope": "PRICE_PRIORITY",
                "initial_marked_equity": metrics["INITIAL_TOTAL_MARKED"],
                "capital_mode": "PHYSICAL_DYNAMIC_NORMALIZED_MECHANICS_BANK",
                "campaign_run_hash": EXPECTED_RUN_HASH,
                "random_hours_utc": result["RANDOM_EVALUATION"]["HOURS_UTC"],
                "normalized_non_executable": True,
            }
        },
    )
    scenario_hash = scenario_event["payload"]["SCENARIO_HASH"]
    run_event = registry.append_run(
        "M030",
        RunSpec(
            scenario_hash=scenario_hash,
            dataset_hash=manifest["evidence"]["validation"]["input_sha256"],
            campaign_snapshot_id=audit["terminal_sha256"],
            interval={"start": result["start"], "end_exclusive": result["end_exclusive"]},
            code_commit=SOURCE_COMMIT,
            technical_revision="M030_REPORTING_RECOVERY_NO_EVENT_REPLAY_V1",
            backend=BackendSpec(backend="CPU"),
            initial_capital=D(metrics["INITIAL_TOTAL_MARKED"]),
            capital_mode="NORMALIZED_MECHANICS_PROBE",
            run={
                "artifact_directory": str(OUTPUT),
                "campaign_run_hash": EXPECTED_RUN_HASH,
                "audit_status": EXPECTED_AUDIT,
                "event_replay_during_finalization": False,
                "reporting_recovery_events_delivered": 0,
            },
        ),
    )
    registry.transition(
        "M030", ModelStatus.RUNNING, reason="Register the sole completed physical M030 run"
    )
    registry.append_evaluation(
        "M030",
        EvaluationSpec(
            scenario_hash=scenario_hash,
            campaign_snapshot_id=audit["terminal_sha256"],
            run_hash=run_event["payload"]["RUN_HASH"],
            comparison={
                "baseline": "M029",
                "random_hours_utc": result["RANDOM_EVALUATION"]["HOURS_UTC"],
                "m029_matched_physical_cycles": 6,
                "m030_matched_physical_cycles": 13,
                "physical_cycle_improvement_pct": comparison[
                    "PHYSICAL_CYCLE_IMPROVEMENT_PCT"
                ],
            },
            criteria={
                "physical_audit_pass": True,
                "frequency_improvement_pass": comparison["FREQUENCY_IMPROVEMENT_PASS"],
                "strong_improvement_pass": comparison["STRONG_IMPROVEMENT_20PCT_PASS"],
                "coverage_pass": management["COVERAGE_PASS"],
                "stranded_reduction_pass": management["STRANDED_REDUCTION_PASS"],
                "management_success_pass": management["MANAGEMENT_SUCCESS_PASS"],
                "live_executable_result": False,
                "strategy_pass": False,
                "event_rerun_performed": False,
            },
            metrics={
                "initial_marked_equity": metrics["INITIAL_TOTAL_MARKED"],
                "final_marked_equity": metrics["FINAL_TOTAL_MARKED"],
                "marked_gain": metrics["TOTAL_MARKED_GAIN"],
                "marked_gain_pct": metrics["TOTAL_MARKED_GAIN_PCT"],
                "random_3h_physical_cycles": metrics["M030_EVAL_PHYSICAL_CYCLES"],
                "random_3h_slot_cycles": metrics["M030_EVAL_SLOT_CYCLES"],
                "full_day_physical_cycles": metrics["PHYSICAL_CYCLES"],
                "full_day_slot_cycles": metrics["SLOT_EQUIVALENT_CYCLES"],
                "hot_coverage_random_3h": metrics[
                    "HOT_FUNDING_COVERAGE_RANDOM_3H_TIME_WEIGHTED"
                ],
                "literal_reclaimable_stranded_random_3h_pct": metrics[
                    "RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"
                ],
                "realized_cycle_pnl": metrics["REALIZED_CYCLE_PNL"],
                "realized_disposal_pnl": metrics["REALIZED_DISPOSAL_PNL"],
                "unrealized_pnl": metrics["UNREALIZED_PNL"],
            },
            replay={
                "start": result["start"],
                "end_exclusive": result["end_exclusive"],
                "campaign_run_hash": EXPECTED_RUN_HASH,
                "random_seed": result["RANDOM_EVALUATION"]["SEED"],
            },
            decision={
                "status": "INCONCLUSIVE",
                "reason": (
                    "Matched frequency and HOT coverage improved, but literal stranded-time "
                    "reduction was 40.72%, below the frozen 50% management gate; the result "
                    "is normalized below minNotional and not live-executable."
                ),
            },
        ),
    )
    registry.transition(
        "M030", ModelStatus.EVALUATED, reason="Physical and reporting-recovery audits passed"
    )
    registry.transition(
        "M030",
        ModelStatus.INCONCLUSIVE,
        reason=(
            "Frequency improved 6 to 13 in matched random3h, but the complete management "
            "gate failed and live-executable evidence is absent"
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
    write_json(OUTPUT / "posthoc-summary.json", result)
    write_json(RESULT, result)
    return result


if __name__ == "__main__":
    value = finalize()
    print(
        json.dumps(
            {
                "MODEL": value["MODEL"],
                "MODEL_STATUS": value["MODEL_STATUS"],
                "RANDOM_3H_CYCLES": value["METRICS"]["M030_EVAL_PHYSICAL_CYCLES"],
                "FULL_DAY_CYCLES": value["METRICS"]["PHYSICAL_CYCLES"],
                "FINAL": value["METRICS"]["FINAL_TOTAL_MARKED"],
                "RERUN": False,
            },
            sort_keys=True,
        )
    )
