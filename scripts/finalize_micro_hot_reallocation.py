"""Register the completed M027 A/B result without replaying market events."""

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
from scripts.run_micro_hot_reallocation import OUTPUT, RESULT

SOURCE_COMMIT = "c653292c836621def5952b4e7e04b8ed8ce53ea8"
EXPECTED_RUN_HASHES = {
    "CONTROL": "fb10dbc7eed0890710087b8729f603c7d747a8de52a40529c13a06167983475e",
    "TREATMENT": "041a139a3dc0f9d6e2b8bfe2f1c3a61028a7c3c829f1a888db94e14250a67b5e",
}
EXPECTED_LEDGER_HASHES = {
    "CONTROL": "618082ba47eec02cb2d540cd7e30a41df0b0aa328c32613ad652d333556fb129",
    "TREATMENT": "af687d287e74e95186ef32dd8757aec985a3605f7986a1347b0c6cce1c82102b",
}


def _validate_result(result: dict) -> None:
    comparison = result["COMPARISON"]
    if (
        result.get("MODEL") != "M027"
        or result.get("RUN_STATUS") != "COMPLETE"
        or comparison.get("AUDIT") != "PASS"
        or comparison.get("CONTROL_PHYSICAL_CYCLES") != 0
        or comparison.get("TREATMENT_PHYSICAL_CYCLES") != 0
        or comparison.get("MICRO_HOT_PHYSICAL_CYCLES") != 0
        or comparison.get("MICRO_HOT_MECHANICS_FAVORABLE") is not False
    ):
        raise ValueError("M027_FINAL_RESULT_IDENTITY_MISMATCH")
    for scenario, expected_run_hash in EXPECTED_RUN_HASHES.items():
        value = result["SCENARIOS"][scenario]
        if (
            value.get("run_hash") != expected_run_hash
            or value.get("published_config_sha") != SOURCE_COMMIT
            or value.get("RUN_STATUS") != "COMPLETE"
            or value.get("AUDIT", {}).get("ledger_sha256")
            != EXPECTED_LEDGER_HASHES[scenario]
            or value.get("METRICS", {}).get("TOTAL_FILLS") != 0
            or value.get("METRICS", {}).get("PHYSICAL_CYCLES") != 0
        ):
            raise ValueError(f"M027_{scenario}_IDENTITY_MISMATCH")


def finalize() -> dict:
    """Append registry evidence and derived metadata only; never replay events."""
    result = json.loads(RESULT.read_bytes())
    _validate_result(result)

    physical_files: dict[str, str] = {}
    manifests: dict[str, dict] = {}
    for scenario in ("CONTROL", "TREATMENT"):
        scenario_root = OUTPUT / scenario
        paths = (
            scenario_root / "run-manifest.json",
            scenario_root / "execution-audit.jsonl",
            scenario_root / "terminal-engine-state.json",
            scenario_root / "independent-audit.json",
        )
        physical_files.update({str(path): file_sha(path) for path in paths})
        manifests[scenario] = json.loads(paths[0].read_bytes())

    registry = ModelRegistry()
    if registry.current_status("M027") != ModelStatus.CREATED:
        raise ValueError("M027_FINALIZATION_REQUIRES_CREATED_STATUS")

    run_events: dict[str, dict] = {}
    scenario_hashes: dict[str, str] = {}
    for scenario in ("CONTROL", "TREATMENT"):
        scenario_result = result["SCENARIOS"][scenario]
        metrics = scenario_result["METRICS"]
        scenario_event = registry.append_scenario(
            "M027",
            {
                "scenario": {
                    "name": f"M027_MICRO_HOT_REALLOCATION_{scenario}_3H",
                    "scenario": scenario,
                    "execution_envelope": "PRICE_PRIORITY",
                    "initial_marked_equity": metrics["INITIAL_TOTAL_MARKED"],
                    "capital_mode": "NORMALIZED_NON_LIVE_EXECUTABLE",
                    "campaign_run_hash": EXPECTED_RUN_HASHES[scenario],
                    "normalized_non_executable": True,
                },
                "label": scenario,
            },
        )
        scenario_hash = scenario_event["payload"]["SCENARIO_HASH"]
        scenario_hashes[scenario] = scenario_hash
        manifest = manifests[scenario]
        run_events[scenario] = registry.append_run(
            "M027",
            RunSpec(
                scenario_hash=scenario_hash,
                dataset_hash=manifest["evidence"]["validation"]["input_sha256"],
                campaign_snapshot_id=scenario_result["AUDIT"]["terminal_sha256"],
                interval={
                    "start": scenario_result["start"],
                    "end_exclusive": scenario_result["end_exclusive"],
                },
                code_commit=SOURCE_COMMIT,
                technical_revision=f"M027_MICRO_HOT_REALLOCATION_{scenario}_V1",
                backend=BackendSpec(backend="CPU"),
                initial_capital=D(metrics["INITIAL_TOTAL_MARKED"]),
                capital_mode="NORMALIZED_MECHANICS_PROBE",
                run={
                    "artifact_directory": str(OUTPUT / scenario),
                    "campaign_run_hash": EXPECTED_RUN_HASHES[scenario],
                    "audit_status": metrics["AUDIT"],
                    "event_replay_during_finalization": False,
                },
            ),
        )

    registry.transition(
        "M027",
        ModelStatus.RUNNING,
        reason="Register both completed OWNER-authorized M027 physical scenarios",
    )
    treatment = result["SCENARIOS"]["TREATMENT"]
    treatment_run_hash = run_events["TREATMENT"]["payload"]["RUN_HASH"]
    registry.append_evaluation(
        "M027",
        EvaluationSpec(
            scenario_hash=scenario_hashes["TREATMENT"],
            campaign_snapshot_id=treatment["AUDIT"]["terminal_sha256"],
            run_hash=treatment_run_hash,
            comparison=result["COMPARISON"],
            criteria={
                "independent_audit_pass": True,
                "treatment_exceeds_control": False,
                "strong_frequency_gate_pass": False,
                "micro_touch_observed": False,
                "live_executable_result": False,
                "strategy_pass": False,
                "event_rerun_performed": False,
            },
            metrics={
                "control_physical_cycles": 0,
                "treatment_physical_cycles": 0,
                "control_total_fills": 0,
                "treatment_total_fills": 0,
                "micro_unique_price_touches": 0,
                "capital_match_error_pct": result["COMPARISON"][
                    "CAPITAL_MATCH_ERROR_PCT"
                ],
            },
            replay={
                "start": treatment["start"],
                "end_exclusive": treatment["end_exclusive"],
                "control_campaign_run_hash": EXPECTED_RUN_HASHES["CONTROL"],
                "treatment_campaign_run_hash": EXPECTED_RUN_HASHES["TREATMENT"],
            },
            decision={
                "status": "INCONCLUSIVE",
                "reason": (
                    "Neither arm received a fill and the micro prices were never touched; "
                    "this tape cannot identify the causal effect of micro-hot reallocation."
                ),
            },
        ),
    )
    registry.transition(
        "M027",
        ModelStatus.EVALUATED,
        reason="Both physical ledgers and terminal states passed independent audit",
    )
    registry.transition(
        "M027",
        ModelStatus.INCONCLUSIVE,
        reason=(
            "Zero fills in both arms and zero micro-price touches leave the treatment effect "
            "unidentified on the authorized tape"
        ),
    )

    result["REGISTRY"] = {
        "status": "INCONCLUSIVE",
        "scenario_count": 2,
        "registry_run_hashes": {
            scenario: event["payload"]["RUN_HASH"]
            for scenario, event in run_events.items()
        },
        "physical_campaign_hash": canonical_hash(physical_files),
        "physical_file_sha256": physical_files,
        "event_replay_during_finalization": False,
    }
    result["MODEL_STATUS"] = "INCONCLUSIVE"
    result["RUN_STATUS"] = "COMPLETE_INCONCLUSIVE_NORMALIZED_MECHANICS"
    write_json(OUTPUT / "comparison.json", result)
    write_json(RESULT, result)
    return result


if __name__ == "__main__":
    value = finalize()
    print(
        json.dumps(
            {
                "MODEL": value["MODEL"],
                "MODEL_STATUS": value["MODEL_STATUS"],
                "CONTROL_PHYSICAL_CYCLES": value["COMPARISON"][
                    "CONTROL_PHYSICAL_CYCLES"
                ],
                "TREATMENT_PHYSICAL_CYCLES": value["COMPARISON"][
                    "TREATMENT_PHYSICAL_CYCLES"
                ],
                "RERUN": False,
            },
            sort_keys=True,
        )
    )
