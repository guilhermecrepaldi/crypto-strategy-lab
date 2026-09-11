"""Reconcile and register the immutable M021 physical result without replaying it."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from crypto_strategy_lab.microstructure.zonal_ping_pong import DensePingPongProbe
from crypto_strategy_lab.ml.model_registry import (
    BackendSpec,
    EvaluationSpec,
    ModelRegistry,
    ModelStatus,
    RunSpec,
)

D = Decimal
ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = Path("artifacts/usdcusdt/l2-monthly-samples/M021/OWNER_GATED_5H/PRICE_PRIORITY")
PHYSICAL_SUMMARY = RUN_DIR / "summary.json"
TERMINAL = RUN_DIR / "terminal-engine-state.json"
AUDIT = RUN_DIR / "execution-audit.jsonl"
RESULT = Path("reports/usdcusdt/M021-5h-result.json")
SOURCE_COMMIT = "f430a07a416dc31e0b06a7198cd8f51fdd0b5a89"


def finalize() -> dict:
    original = json.loads(PHYSICAL_SUMMARY.read_bytes())
    terminal = json.loads(TERMINAL.read_bytes())
    if (
        original["model_id"] != "M021"
        or original["published_config_sha"] != SOURCE_COMMIT
        or original["RUN_STATUS"] != "COMPLETE"
        or original["AUDIT"]["status"] != "PASS_M021_LEDGER_EXECUTION_LIQUIDITY"
        or original["TOTAL_COMPLETE_CYCLES"] != 19
    ):
        raise ValueError("M021_PHYSICAL_RESULT_MISMATCH")
    physical_files = {
        "run_manifest": file_sha(RUN_DIR / "run-manifest.json"),
        "summary": file_sha(PHYSICAL_SUMMARY),
        "terminal": file_sha(TERMINAL),
        "execution_audit": file_sha(AUDIT),
    }
    physical_hash = canonical_hash(physical_files)

    engine = DensePingPongProbe.from_checkpoint(terminal)
    engine.validate_invariants()
    corrected = {row["slot_id"]: row for row in engine.metrics()["slot_report"]}
    report = json.loads(json.dumps(original))
    for row in report["ALL_SLOTS"]:
        derived = corrected[row["SLOT"]]
        row["ACTIVE_TIME_US"] = derived["active_time_us"]
        row["OPEN_POSITION_AT_CUTOFF"] = derived["open_position_at_cutoff"]

    rows = [json.loads(line) for line in AUDIT.read_text(encoding="utf-8").splitlines()]
    submissions = {int(row["order_id"]): row for row in rows if row["event"] == "SUBMIT"}
    self_cross = Counter(row["band_id"] for row in rows if row["event"] == "SELF_CROSS_BLOCKED")
    post_only = Counter(
        submissions[int(row["order_id"])]["band_id"]
        for row in rows
        if row["event"] == "REJECTED_POST_ONLY"
    )
    filled_slots = {row["SLOT"] for row in report["ALL_SLOTS"] if row["FILLS"] > 0}
    productive_slots = {row["SLOT"] for row in report["ALL_SLOTS"] if row["COMPLETE_CYCLES"] > 0}
    report.update(
        {
            "PHYSICAL_RUN_HASH": physical_hash,
            "PHYSICAL_FILE_SHA256": physical_files,
            "MAIN_LIMITER": "NARROW_PRICE_PATH_PLUS_EXIT_SELF_CROSS_POST_ONLY_CONFLICT",
            "REPORTING_CORRECTION": {
                "scope": "DEFENSIVE_CODE_HARDENING_NO_M021_VALUE_CHANGED",
                "reason": (
                    "The status predicate was broadened defensively, but every M021 post-only "
                    "rejection had no activation timestamp and was already excluded."
                ),
                "economic_replay_repeated": False,
                "economic_fields_changed": False,
                "active_time_values_changed": False,
                "physical_summary_preserved": str(PHYSICAL_SUMMARY),
            },
            "AUTOPSY": {
                "market_tick_span": 10,
                "filled_slots": len(filled_slots),
                "productive_slots": len(productive_slots),
                "zero_fill_slots": 200 - len(filled_slots),
                "self_cross_recheck_events": sum(self_cross.values()),
                "self_cross_affected_slots": sorted(self_cross),
                "post_only_rejections": sum(post_only.values()),
                "post_only_affected_slots": sorted(post_only),
                "interpretation": (
                    "Only the ten entries touched by the 1.0017-1.0027 path filled. "
                    "Seven slots completed cycles. S005-S007 sold once but their owned "
                    "buybacks conflicted with lower resting SELL entries; repeated event "
                    "counts are reconciliation attempts, not independent opportunities."
                ),
            },
        }
    )

    registry = ModelRegistry()
    if registry.current_status("M021") != ModelStatus.CREATED:
        raise ValueError("M021_FINALIZATION_REQUIRES_CREATED_STATUS")
    scenario_event = registry.append_scenario(
        "M021",
        {
            "scenario": {
                "name": "M021_DENSE_PING_PONG_5H_NORMALIZED_MECHANICS",
                "execution_profile": "B_REALISTIC_CONSERVATIVE",
                "execution_envelope": "PRICE_PRIORITY",
                "grid_anchor": "1.0020",
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
        "M021",
        RunSpec(
            scenario_hash=scenario_hash,
            dataset_hash=report["DATA_INTEGRITY"]["validation"]["input_sha256"],
            campaign_snapshot_id=physical_hash,
            interval={"start": report["start"], "end_exclusive": report["end_exclusive"]},
            code_commit=SOURCE_COMMIT,
            technical_revision="DENSE_200_SLOT_PING_PONG_MECHANICS_PROBE_V1",
            backend=BackendSpec(backend="CPU"),
            initial_capital=D("199.88500000"),
            capital_mode="NORMALIZED_MECHANICS_PROBE",
            run={
                "artifact_directory": str(RUN_DIR),
                "physical_run_hash": physical_hash,
                "identity_run_hash": report["run_hash"],
                "audit_status": report["AUDIT"]["status"],
                "reporting_correction": report["REPORTING_CORRECTION"],
            },
        ),
    )
    registry_run_hash = run_event["payload"]["RUN_HASH"]
    registry.transition(
        "M021",
        ModelStatus.RUNNING,
        reason="Register immutable already-completed OWNER-authorized physical run evidence",
    )
    registry.append_evaluation(
        "M021",
        EvaluationSpec(
            scenario_hash=scenario_hash,
            campaign_snapshot_id=physical_hash,
            run_hash=registry_run_hash,
            comparison={
                "parent": "M020",
                "controlled_profitability_comparison": False,
                "reason": "Capital and geometry differ; only mechanical observation is compared.",
            },
            criteria={
                "informational_gate": "TOTAL_COMPLETE_CYCLES_GT_ZERO",
                "strategy_pass": False,
                "live_executable": False,
            },
            metrics={
                "total_complete_cycles": report["TOTAL_COMPLETE_CYCLES"],
                "cycles_per_hour": report["CYCLES_PER_HOUR"],
                "buy_first_cycles": report["BUY_FIRST_CYCLES"],
                "sell_first_cycles": report["SELL_FIRST_CYCLES"],
                "total_marked_equity": report["TOTAL_MARKED_EQUITY"],
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
                "status": "INCONCLUSIVE",
                "mechanic_observed": True,
                "reason": (
                    "The normalized mechanic completed cycles, but 3.8 cycles/hour is not "
                    "high throughput and the one-USDC orders are not exchange executable."
                ),
            },
        ),
    )
    registry.transition(
        "M021",
        ModelStatus.EVALUATED,
        reason="Five-hour physical result and independent execution audit reconciled",
    )
    registry.transition(
        "M021",
        ModelStatus.INCONCLUSIVE,
        reason=(
            "Mechanic observed at normalized notional; insufficient throughput and no "
            "live-executable or profitability conclusion"
        ),
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
                "TOTAL_COMPLETE_CYCLES": value["TOTAL_COMPLETE_CYCLES"],
                "PHYSICAL_RUN_HASH": value["PHYSICAL_RUN_HASH"],
                "MODEL_STATUS": value["MODEL_STATUS"],
            },
            sort_keys=True,
        )
    )
