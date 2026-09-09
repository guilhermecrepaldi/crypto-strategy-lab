"""Register the completed M025 capacity campaign without replaying market events."""

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
from scripts.run_order_size_capacity import OUTPUT, RESULT

SOURCE_COMMIT = "7745600715bdc321a65296b67b0faba67cfe1b79"
EXPECTED_RUN_HASH = "a2ada49ad8c237ad8b41b7da9096b15e67c5005e81c31fc7ed6e2672090adc22"


def finalize() -> dict:
    result = json.loads(RESULT.read_bytes())
    if (
        result.get("run_hash") != EXPECTED_RUN_HASH
        or result.get("published_config_sha") != SOURCE_COMMIT
        or result.get("RUN_STATUS") != "COMPLETE"
        or result.get("AUDIT", {}).get("status")
        != "PASS_ALL_11_INDEPENDENT_SCENARIO_AUDITS"
        or result.get("REPORTING_CORRECTION", {}).get("status") != "PASS"
        or result["REPORTING_CORRECTION"].get("event_replay_performed") is not False
    ):
        raise ValueError("M025_FINAL_RESULT_IDENTITY_MISMATCH")

    run_manifest = json.loads((OUTPUT / "run-manifest.json").read_bytes())
    registry = ModelRegistry()
    if registry.current_status("M025") != ModelStatus.CREATED:
        raise ValueError("M025_FINALIZATION_REQUIRES_CREATED_STATUS")

    physical_files: dict[str, str] = {}
    scenario_records = []
    for scenario in result["SCENARIOS"]:
        quantity = scenario["ORDER_QUANTITY_USDC"]
        directory = OUTPUT / f"Q{int(D(quantity)):05d}"
        ledger = directory / "execution-audit.jsonl"
        terminal = directory / "terminal-engine-state.json"
        summary = directory / "summary.json"
        for path in (ledger, terminal, summary):
            physical_files[str(path)] = file_sha(path)
        metrics = scenario["METRICS"]
        scenario_event = registry.append_scenario(
            "M025",
            {
                "scenario": {
                    "name": f"M025_ORDER_SIZE_Q{quantity}_3H",
                    "order_quantity_usdc": quantity,
                    "execution_profile": "B_REALISTIC_CONSERVATIVE",
                    "execution_envelope": "PRICE_PRIORITY",
                    "initial_marked_equity": metrics["INITIAL_MARKED_EQUITY"],
                    "capital_mode": "PROPORTIONAL_NORMALIZED_CAPACITY_CURVE",
                    "growth_expansion_enabled": False,
                    "campaign_run_hash": EXPECTED_RUN_HASH,
                }
            },
        )
        scenario_hash = scenario_event["payload"]["SCENARIO_HASH"]
        terminal_sha = scenario["AUDIT"]["terminal_sha256"]
        run_event = registry.append_run(
            "M025",
            RunSpec(
                scenario_hash=scenario_hash,
                dataset_hash=run_manifest["evidence"]["validation"]["input_sha256"],
                campaign_snapshot_id=terminal_sha,
                interval={"start": result["start"], "end_exclusive": result["end_exclusive"]},
                code_commit=SOURCE_COMMIT,
                technical_revision="M024_ORDER_SIZE_CAPACITY_CURVE_V1",
                backend=BackendSpec(backend="CPU"),
                initial_capital=D(metrics["INITIAL_MARKED_EQUITY"]),
                capital_mode="NORMALIZED_MECHANICS_PROBE",
                run={
                    "artifact_directory": str(directory),
                    "campaign_run_hash": EXPECTED_RUN_HASH,
                    "audit_status": scenario["AUDIT"]["status"],
                    "reporting_correction": "NO_EVENT_REPLAY",
                },
            ),
        )
        scenario_records.append((scenario, scenario_hash, run_event["payload"]["RUN_HASH"]))

    registry.transition(
        "M025",
        ModelStatus.RUNNING,
        reason="Register the one completed OWNER-authorized M025 capacity campaign",
    )
    for scenario, scenario_hash, registry_run_hash in scenario_records:
        metrics = scenario["METRICS"]
        quantity = scenario["ORDER_QUANTITY_USDC"]
        registry.append_evaluation(
            "M025",
            EvaluationSpec(
                scenario_hash=scenario_hash,
                campaign_snapshot_id=scenario["AUDIT"]["terminal_sha256"],
                run_hash=registry_run_hash,
                comparison={
                    "only_independent_variable": "ORDER_QUANTITY_USDC",
                    "order_quantity_usdc": quantity,
                    "capacity_knee": result["ANALYSIS"]["CAPACITY_KNEE_ORDER_SIZE"],
                },
                criteria={
                    "physical_audit_pass": True,
                    "live_executable_result": False,
                    "strategy_pass": False,
                    "event_rerun_performed": False,
                },
                metrics={
                    "order_quantity_usdc": quantity,
                    "complete_positive_cycles": metrics["TOTAL_CYCLES"],
                    "cycles_per_hour": metrics["CYCLES_PER_HOUR"],
                    "completed_roundtrip_usdc_per_hour": metrics[
                        "COMPLETED_ROUNDTRIP_USDC_PER_HOUR"
                    ],
                    "final_marked_equity": metrics["FINAL_MARKED_EQUITY"],
                    "completed_cycle_pnl": metrics["REALIZED_PNL"],
                    "realized_disposal_pnl": metrics["REALIZED_DISPOSAL_PNL"],
                    "unrealized_pnl": metrics["UNREALIZED_PNL"],
                    "residual_partial_orders": metrics["RESIDUAL_PARTIAL_ORDER_COUNT"],
                },
                replay={
                    "start": result["start"],
                    "end_exclusive": result["end_exclusive"],
                    "campaign_run_hash": EXPECTED_RUN_HASH,
                },
                decision={
                    "status": "INCONCLUSIVE",
                    "reason": (
                        "Developmental exogenous-tape capacity result; no live capacity, "
                        "strategy profitability or successor authorization is established."
                    ),
                },
            ),
        )
    registry.transition(
        "M025",
        ModelStatus.EVALUATED,
        reason="All eleven physical scenarios and corrected derived report reconciled",
    )
    registry.transition(
        "M025",
        ModelStatus.INCONCLUSIVE,
        reason="Capacity knee not observed through Q5000; live rank and impact remain unknown",
    )
    registry_summary = {
        "status": "INCONCLUSIVE",
        "scenario_count": len(scenario_records),
        "registry_run_hashes": [record[2] for record in scenario_records],
        "physical_campaign_hash": canonical_hash(physical_files),
        "physical_file_sha256": physical_files,
        "event_replay_during_finalization": False,
    }
    result["REGISTRY"] = registry_summary
    result["MODEL_STATUS"] = "INCONCLUSIVE"
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
                "SCENARIOS": value["REGISTRY"]["scenario_count"],
                "CAPACITY_KNEE": value["ANALYSIS"]["CAPACITY_KNEE_ORDER_SIZE"],
                "RERUN": False,
            },
            sort_keys=True,
        )
    )
