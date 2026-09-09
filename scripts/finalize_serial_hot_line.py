"""Register and publish the immutable M023 physical result without replaying it."""

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
RUN_DIR = Path("artifacts/usdcusdt/l2-monthly-samples/M023/OWNER_GATED_3H/PRICE_PRIORITY")
PHYSICAL_SUMMARY = RUN_DIR / "summary.json"
RUN_MANIFEST = RUN_DIR / "run-manifest.json"
TERMINAL = RUN_DIR / "terminal-engine-state.json"
AUDIT = RUN_DIR / "execution-audit.jsonl"
RESULT = Path("reports/usdcusdt/M023-3h-result.json")
POST_REVIEW = Path("reports/usdcusdt/M023-3h-independent-post-run-review.md")
SOURCE_COMMIT = "68841b11f2bb27bc819d8f60715a8bf45e6dd7a4"


def finalize() -> dict:
    physical = json.loads(PHYSICAL_SUMMARY.read_bytes())
    metrics = physical["METRICS"]
    if (
        physical["model_id"] != "M023"
        or physical["published_config_sha"] != SOURCE_COMMIT
        or physical["RUN_STATUS"] != "COMPLETE"
        or physical["AUDIT"]["status"] != "PASS_M023_SERIAL_HOT_LINE_LEDGER"
        or physical["TOTAL_COMPLETE_POSITIVE_BUY_SELL_CYCLES"] != 4
        or physical["AUDIT"]["completed_legs"] != 9
        or metrics["inventory"] != "1"
        or metrics["marked_equity"] != "1.00220000"
        or metrics["realized_profit"] != "0.00040000"
        or metrics["unrealized_pnl"] != "-0.00010000"
    ):
        raise ValueError("M023_PHYSICAL_RESULT_MISMATCH")
    if not POST_REVIEW.is_file():
        raise ValueError("M023_POST_RUN_REVIEW_REQUIRED")

    physical_files = {
        "run_manifest": file_sha(RUN_MANIFEST),
        "summary": file_sha(PHYSICAL_SUMMARY),
        "terminal": file_sha(TERMINAL),
        "execution_audit": file_sha(AUDIT),
        "all_fill_audit": file_sha(RUN_DIR / "all-fill-audit.json"),
    }
    physical_hash = canonical_hash(physical_files)
    rows = [json.loads(line) for line in AUDIT.read_text(encoding="utf-8").splitlines()]
    event_counts = Counter(row["event"] for row in rows)
    duration_us = 3 * 3_600_000_000
    order_uptime = D(metrics["active_order_time_us"]) / D(duration_us) * D("100")
    usdt_final = D(metrics["total_usdt_owned"])
    usdc_final = D(metrics["inventory"])
    equity = D(metrics["marked_equity"])
    usdc_marked = equity - usdt_final

    report = json.loads(json.dumps(physical))
    report.update(
        {
            "PHYSICAL_RUN_HASH": physical_hash,
            "PHYSICAL_FILE_SHA256": physical_files,
            "POST_RUN_REVIEW_SHA256": file_sha(POST_REVIEW),
            "USDT_FINAL": str(usdt_final),
            "USDC_FINAL": str(usdc_final),
            "USDC_MARKED_VALUE": str(usdc_marked),
            "TOTAL_FINAL_EQUITY": str(equity),
            "REALIZED_NET_PNL": metrics["realized_profit"],
            "UNREALIZED_PNL": metrics["unrealized_pnl"],
            "PASS_1000": False,
            "PASS_2000": False,
            "MECHANISM_OBSERVED": True,
            "MAIN_LIMITER": "SERIAL_FIFO_QUEUE_AND_PRICE_RECOVERY_WAIT",
            "ORDER_UPTIME_PERCENT": str(order_uptime),
            "AUTOPSY": {
                "complete_cycles": 4,
                "completed_buy_legs": 5,
                "completed_sell_legs": 4,
                "projected_24h_at_observed_rate_not_validation": "32",
                "orders_submitted": event_counts["SUBMIT"],
                "orders_canceled": event_counts["CANCEL_ACK"],
                "post_only_rejections": event_counts["REJECTED_POST_ONLY"],
                "coverage_rejections": event_counts["REJECTED_COVERAGE"],
                "queue_flow_events": event_counts["QUEUE_FLOW"],
                "queue_quantity_ahead_consumed": metrics["queue_blocked_quantity"],
                "no_order_seconds": str(D(metrics["no_order_time_us"]) / D("1000000")),
                "final_open_sell": True,
                "final_open_sell_censored_seconds": "424.65",
                "interpretation": (
                    "The manager almost always had exactly one order working and produced no "
                    "post-only rejection storm. Throughput nevertheless remained low because "
                    "the serial order waited behind observed FIFO depth and for profitable "
                    "price recovery. The virtual deck removed no physical queue constraint."
                ),
            },
        }
    )

    registry = ModelRegistry()
    if registry.current_status("M023") != ModelStatus.CREATED:
        raise ValueError("M023_FINALIZATION_REQUIRES_CREATED_STATUS")
    run_manifest = json.loads(RUN_MANIFEST.read_bytes())
    scenario_event = registry.append_scenario(
        "M023",
        {
            "scenario": {
                "name": "M023_SERIAL_HOT_LINE_3H_NORMALIZED_MECHANICS",
                "execution_profile": "B_REALISTIC_CONSERVATIVE",
                "execution_envelope": "PRICE_PRIORITY",
                "initial_usdt": "1.0019",
                "initial_usdc": "0",
                "capital_mode": "NORMALIZED_MECHANICS_PROBE",
                "physical_run_hash": physical_hash,
            }
        },
    )
    scenario_hash = scenario_event["payload"]["SCENARIO_HASH"]
    run_event = registry.append_run(
        "M023",
        RunSpec(
            scenario_hash=scenario_hash,
            dataset_hash=run_manifest["evidence"]["validation"]["input_sha256"],
            campaign_snapshot_id=physical_hash,
            interval={"start": physical["start"], "end_exclusive": physical["end_exclusive"]},
            code_commit=SOURCE_COMMIT,
            technical_revision="SERIAL_HOT_LINE_PING_PONG_V1",
            backend=BackendSpec(backend="CPU"),
            initial_capital=D("1.0019"),
            capital_mode="NORMALIZED_MECHANICS_PROBE",
            run={
                "artifact_directory": str(RUN_DIR),
                "physical_run_hash": physical_hash,
                "identity_run_hash": physical["run_hash"],
                "audit_status": physical["AUDIT"]["status"],
            },
        ),
    )
    registry_run_hash = run_event["payload"]["RUN_HASH"]
    registry.transition(
        "M023",
        ModelStatus.RUNNING,
        reason="Register immutable completed OWNER-authorized M023 physical evidence",
    )
    registry.append_evaluation(
        "M023",
        EvaluationSpec(
            scenario_hash=scenario_hash,
            campaign_snapshot_id=physical_hash,
            run_hash=registry_run_hash,
            comparison={
                "parent": "M022",
                "direct_financial_comparison_valid": False,
                "reason": "Different capital and three-hour versus five-hour window",
            },
            criteria={
                "mechanism_observed": True,
                "preregistered_minimum_cycle_gate": None,
                "owner_1000_cycle_goal_met": False,
                "strategy_pass": False,
                "live_executable": False,
            },
            metrics={
                "total_complete_cycles": 4,
                "cycles_per_hour": physical["CYCLES_PER_HOUR"],
                "total_marked_equity": str(equity),
                "realized_net_pnl": metrics["realized_profit"],
                "unrealized_pnl": metrics["unrealized_pnl"],
                "audit_status": physical["AUDIT"]["status"],
                "main_limiter": report["MAIN_LIMITER"],
            },
            replay={
                "start": physical["start"],
                "end_exclusive": physical["end_exclusive"],
                "physical_run_hash": physical_hash,
            },
            decision={
                "status": "INCONCLUSIVE",
                "mechanism_observed": True,
                "reason": (
                    "Four cycles establish that the serial mechanism can complete, but the "
                    "normalized non-executable probe and low three-hour throughput do not "
                    "establish strategy efficacy or justify automatic expansion."
                ),
            },
        ),
    )
    registry.transition(
        "M023",
        ModelStatus.EVALUATED,
        reason="Three-hour physical result and post-run audit reconciled",
    )
    registry.transition(
        "M023",
        ModelStatus.INCONCLUSIVE,
        reason="Mechanism observed, but throughput low and one-USDC result non-executable",
    )
    report["REGISTRY_RUN_HASH"] = registry_run_hash
    report["MODEL_STATUS"] = "INCONCLUSIVE"
    write_json(RESULT, report)
    return report


if __name__ == "__main__":
    value = finalize()
    print(
        json.dumps(
            {
                "MODEL": value["MODEL"],
                "TOTAL_COMPLETE_CYCLES": value["TOTAL_COMPLETE_POSITIVE_BUY_SELL_CYCLES"],
                "TOTAL_FINAL_EQUITY": value["TOTAL_FINAL_EQUITY"],
                "PHYSICAL_RUN_HASH": value["PHYSICAL_RUN_HASH"],
                "MODEL_STATUS": value["MODEL_STATUS"],
            },
            sort_keys=True,
        )
    )
