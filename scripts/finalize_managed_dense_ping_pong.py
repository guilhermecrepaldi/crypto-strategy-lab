"""Reconcile and register the immutable M022 physical result without replaying it."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from crypto_strategy_lab.ml.model_registry import (
    BackendSpec,
    EvaluationSpec,
    ModelRegistry,
    ModelStatus,
    RunSpec,
)

D = Decimal
RUN_DIR = Path("artifacts/usdcusdt/l2-monthly-samples/M022/OWNER_GATED_5H/PRICE_PRIORITY")
PHYSICAL_SUMMARY = RUN_DIR / "summary.json"
TERMINAL = RUN_DIR / "terminal-engine-state.json"
AUDIT = RUN_DIR / "execution-audit.jsonl"
RESULT = Path("reports/usdcusdt/M022-5h-result.json")
SOURCE_COMMIT = "f826b1c09368457c9252874e3dcf85f67ba64ef6"


def finalize() -> dict:
    physical = json.loads(PHYSICAL_SUMMARY.read_bytes())
    if (
        physical["model_id"] != "M022"
        or physical["published_config_sha"] != SOURCE_COMMIT
        or physical["RUN_STATUS"] != "COMPLETE"
        or physical["AUDIT"]["status"] != "PASS_M022_MANAGER_LEDGER_EXECUTION_LIQUIDITY"
        or physical["TOTAL_COMPLETE_CYCLES"] != 19
        or physical["DELTA_VS_M021"] != 0
    ):
        raise ValueError("M022_PHYSICAL_RESULT_MISMATCH")

    physical_files = {
        "run_manifest": file_sha(RUN_DIR / "run-manifest.json"),
        "summary": file_sha(PHYSICAL_SUMMARY),
        "terminal": file_sha(TERMINAL),
        "execution_audit": file_sha(AUDIT),
        "all_fill_audit": file_sha(RUN_DIR / "all-fill-audit.json"),
    }
    physical_hash = canonical_hash(physical_files)
    rows = [json.loads(line) for line in AUDIT.read_text(encoding="utf-8").splitlines()]
    submissions = {int(row["order_id"]): row for row in rows if row["event"] == "SUBMIT"}
    post_only = Counter(
        (submissions[int(row["order_id"])]["role"], submissions[int(row["order_id"])]["band_id"])
        for row in rows
        if row["event"] == "REJECTED_POST_ONLY"
    )
    cycles = [row for row in rows if row["event"] == "CYCLE"]
    cycle_profit_by_direction = Counter()
    for row in cycles:
        cycle_profit_by_direction[row["direction"]] += D(row["profit"])
    cycle_profit = sum(cycle_profit_by_direction.values(), D("0"))

    report = json.loads(json.dumps(physical))
    report.update(
        {
            "DISCLAIMER": (
                "M022 DENSE PING-PONG ORDER MANAGER V2. NORMALIZED 1-USDC "
                "ORDERS ARE NOT LIVE-EXECUTABLE."
            ),
            "PHYSICAL_RUN_HASH": physical_hash,
            "PHYSICAL_FILE_SHA256": physical_files,
            "MAIN_LIMITER": ("FIXED_RETURN_PUBLIC_POST_ONLY_CONFLICT_WITH_QUEUE_LIMITED_REMAINDER"),
            "SUM_ROUNDTRIP_CYCLE_PROFIT": str(cycle_profit),
            "ROUNDTRIP_PROFIT_BY_DIRECTION": {
                key: str(value) for key, value in sorted(cycle_profit_by_direction.items())
            },
            "POST_WRITE_PRESENTATION_FAILURE": {
                "occurred": True,
                "scope": "STDOUT_JSON_SERIALIZATION_AFTER_ALL_ARTIFACT_WRITES",
                "exception": "TypeError: Decimal is not JSON serializable",
                "economic_replay_repeated": False,
                "physical_artifacts_complete": True,
            },
            "REPORTING_CORRECTION": {
                "physical_summary_preserved": str(PHYSICAL_SUMMARY),
                "economic_fields_replayed": False,
                "disclaimer_changed_from_m021_to_m022": True,
                "physical_roundtrip_field": physical["SUM_ROUNDTRIP_CYCLE_PROFIT"],
                "corrected_all_cycle_profit": str(cycle_profit),
                "reason": (
                    "The inherited accumulator represented SELL_BUY only; the derived "
                    "report now sums all 19 physical CYCLE events without changing them."
                ),
            },
            "AUTOPSY": {
                "m021_baseline_cycles": 19,
                "m022_cycles": 19,
                "delta_cycles": 0,
                "market_tick_span": 10,
                "exit_post_only_rejections": sum(
                    count for (role, _lane), count in post_only.items() if role == "EXIT"
                ),
                "entry_post_only_rejections": sum(
                    count for (role, _lane), count in post_only.items() if role == "ENTRY"
                ),
                "exit_post_only_by_lane": {
                    lane: count
                    for (role, lane), count in sorted(post_only.items())
                    if role == "EXIT"
                },
                "return_submissions": report["RETURN_SUBMISSIONS"],
                "return_fills": report["RETURN_FILLS"],
                "return_preemptions": report["RETURN_PREEMPTIONS"],
                "free_cancels_for_float": report["FREE_CANCELS_FOR_FLOAT"],
                "free_orders_reposted": report["FREE_ORDERS_REPOSTED"],
                "queue_blocked_events": report["QUEUE_BLOCKED_EVENTS"],
                "censored_return_claim_count": report["MANAGER_METRICS"][
                    "censored_return_claim_count"
                ],
                "censored_return_claim_max_age_us": report["MANAGER_METRICS"][
                    "censored_return_claim_max_age_us"
                ],
                "unique_productive_lanes": report["UNIQUE_PRODUCTIVE_LANES"],
                "mean_active_open_orders": report["MEAN_ACTIVE_OPEN_ORDERS"],
                "percent_active_within_5_ticks": report[
                    "PERCENT_ACTIVE_ORDERS_WITHIN_5_TICKS_OF_MID"
                ],
                "percent_active_within_10_ticks": report[
                    "PERCENT_ACTIVE_ORDERS_WITHIN_10_TICKS_OF_MID"
                ],
                "interpretation": (
                    "The manager kept almost 160 orders open and floated 84 free entries, "
                    "but return priority never preempted a free order. Repeated owned "
                    "returns for S005-S007 were non-passive at their fixed one-tick prices, "
                    "causing 18,492 EXIT post-only rejections. The package changed order "
                    "activity but did not increase completed cycles on this tape."
                ),
            },
        }
    )

    if len(cycles) != 19 or cycle_profit != D("0.0019"):
        raise ValueError("M022_CYCLE_EVENT_RECONSTRUCTION_MISMATCH")
    if report["AUTOPSY"]["exit_post_only_rejections"] != 18492:
        raise ValueError("M022_POST_ONLY_AUTOPSY_MISMATCH")

    registry = ModelRegistry()
    if registry.current_status("M022") != ModelStatus.CREATED:
        raise ValueError("M022_FINALIZATION_REQUIRES_CREATED_STATUS")
    scenario_event = registry.append_scenario(
        "M022",
        {
            "scenario": {
                "name": "M022_ORDER_MANAGER_5H_NORMALIZED_COMPARISON",
                "execution_profile": "B_REALISTIC_CONSERVATIVE",
                "execution_envelope": "PRICE_PRIORITY",
                "control_model": "M021",
                "control_cycles": 19,
                "initial_usdt": "99.6950",
                "initial_usdc": "100",
                "initial_marked_equity": "199.88500000",
                "capital_mode": "NORMALIZED_MECHANICS_PROBE",
                "physical_run_hash": physical_hash,
            }
        },
    )
    scenario_hash = scenario_event["payload"]["SCENARIO_HASH"]
    run_event = registry.append_run(
        "M022",
        RunSpec(
            scenario_hash=scenario_hash,
            dataset_hash=report["DATA_INTEGRITY"]["validation"]["input_sha256"],
            campaign_snapshot_id=physical_hash,
            interval={"start": report["start"], "end_exclusive": report["end_exclusive"]},
            code_commit=SOURCE_COMMIT,
            technical_revision="DENSE_PING_PONG_ORDER_MANAGER_V2",
            backend=BackendSpec(backend="CPU"),
            initial_capital=D("199.88500000"),
            capital_mode="NORMALIZED_MECHANICS_PROBE",
            run={
                "artifact_directory": str(RUN_DIR),
                "physical_run_hash": physical_hash,
                "identity_run_hash": report["run_hash"],
                "audit_status": report["AUDIT"]["status"],
                "post_write_presentation_failure": report["POST_WRITE_PRESENTATION_FAILURE"],
                "reporting_correction": report["REPORTING_CORRECTION"],
            },
        ),
    )
    registry_run_hash = run_event["payload"]["RUN_HASH"]
    registry.transition(
        "M022",
        ModelStatus.RUNNING,
        reason="Register immutable completed OWNER-authorized physical M022 evidence",
    )
    registry.append_evaluation(
        "M022",
        EvaluationSpec(
            scenario_hash=scenario_hash,
            campaign_snapshot_id=physical_hash,
            run_hash=registry_run_hash,
            comparison={
                "parent": "M021",
                "controlled_throughput_comparison": True,
                "m021_cycles": 19,
                "m022_cycles": 19,
                "delta_cycles": 0,
                "multiplier": "1",
            },
            criteria={
                "primary_gate": "TOTAL_COMPLETE_CYCLES_GT_M021_19",
                "primary_gate_pass": False,
                "strategy_pass": False,
                "live_executable": False,
            },
            metrics={
                "total_complete_cycles": report["TOTAL_COMPLETE_CYCLES"],
                "cycles_per_hour": report["CYCLES_PER_HOUR"],
                "buy_first_cycles": report["BUY_FIRST_CYCLES"],
                "sell_first_cycles": report["SELL_FIRST_CYCLES"],
                "delta_vs_m021": report["DELTA_VS_M021"],
                "total_marked_equity": report["FINAL_MARKED_EQUITY"],
                "realized_net_pnl": report["REALIZED_NET_PNL"],
                "unrealized_pnl": report["UNREALIZED_PNL"],
                "audit_status": report["AUDIT"]["status"],
                "main_limiter": report["MAIN_LIMITER"],
            },
            replay={
                "start": report["start"],
                "end_exclusive": report["end_exclusive"],
                "physical_run_hash": physical_hash,
            },
            decision={
                "status": "REJECTED",
                "did_order_management_improve_throughput": False,
                "reason": (
                    "The controlled manager package produced the same 19 cycles as M021. "
                    "It changed quote activity but did not improve the primary metric."
                ),
            },
        ),
    )
    registry.transition(
        "M022",
        ModelStatus.EVALUATED,
        reason="Five-hour physical result and manager audit reconciled",
    )
    registry.transition(
        "M022",
        ModelStatus.REJECTED,
        reason="Controlled throughput delta versus M021 was zero",
    )
    report["REGISTRY_RUN_HASH"] = registry_run_hash
    report["MODEL_STATUS"] = "REJECTED"
    write_json(RESULT, report)
    return report


if __name__ == "__main__":
    value = finalize()
    print(
        json.dumps(
            {
                "MODEL": value["MODEL"],
                "TOTAL_COMPLETE_CYCLES": value["TOTAL_COMPLETE_CYCLES"],
                "DELTA_VS_M021": value["DELTA_VS_M021"],
                "PHYSICAL_RUN_HASH": value["PHYSICAL_RUN_HASH"],
                "MODEL_STATUS": value["MODEL_STATUS"],
            },
            sort_keys=True,
        )
    )
