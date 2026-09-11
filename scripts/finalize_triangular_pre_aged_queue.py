"""Publish M024 from its immutable preserved physical ledger without replaying events."""

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
from scripts import run_triangular_pre_aged_queue as runner

D = Decimal
RUN_DIR = runner.OUTPUT
RUN_MANIFEST = RUN_DIR / "run-manifest.json"
TERMINAL = RUN_DIR / "terminal-engine-state.json"
LEDGER = RUN_DIR / "execution-audit.jsonl"
FAILURE = RUN_DIR / "failure.json"
RECOVERED_AUDIT = RUN_DIR / "recovered-independent-audit.json"
RECOVERED_SUMMARY = RUN_DIR / "recovered-summary.json"
RESULT = runner.RESULT
POST_REVIEW = Path("reports/usdcusdt/M024-3h-independent-post-run-review.md")
SOURCE_COMMIT = "74baeedfa8e1b36d7cb1f47c7aefda6d93524c5c"
RECOVERY_AUDITOR_COMMIT = "82999f7ef51ba0e8227fd480f9fdb9a94b714d30"
RECOVERY_AUDITOR_SHA256_LF = "102c768517c6febe551ebe56dea4d372e72e59b0d6ce142c779161c5efa6fa4d"
RECOVERY_TEST_SHA256_LF = "c41cc102f5e485c6e3f8b83cdb7d61a30296b159e29fbeb9ed5b17a09a0b0bdc"
POST_REVIEW_SHA256_LF = "ed9a81f3f901afd788040da86365c113bf9e718214f130c2cd0d10138fc9c77d"
EXPECTED_PHYSICAL_SHA256 = {
    "execution-audit.jsonl": "05ccf076f76926428afc5271bfe5f52413ea4dbb0653326cc7b7cea9911149b9",
    "failure.json": "a25864c6e5d7ec626a16ad061c2e57091b8e863846cdd51ce328aad9cb172878",
    "run-manifest.json": "832b61044cbfc46d4646e31ad07fd02d85baee1c9955cdc1a29462ec1176daf2",
    "terminal-engine-state.json": (
        "908deaffe3c708dcaa29f34876ccf8891e73a6b60c9fe5112073307057abea34"
    ),
}


def _physical_hashes() -> dict[str, str]:
    return {name: file_sha(RUN_DIR / name) for name in EXPECTED_PHYSICAL_SHA256}


def recover_preserved_result() -> dict:
    """Audit the preserved terminal state; never call the event replay state machine."""
    if RESULT.exists() or RECOVERED_AUDIT.exists() or RECOVERED_SUMMARY.exists():
        raise ValueError("M024_RECOVERY_OUTPUT_ALREADY_EXISTS")
    if _physical_hashes() != EXPECTED_PHYSICAL_SHA256:
        raise ValueError("M024_PRESERVED_PHYSICAL_HASH_MISMATCH")
    review = POST_REVIEW.read_text(encoding="utf-8")
    if (
        "STATUS=PASS_PRESERVED_PHYSICAL_RUN_RECOVERABLE" not in review
        or runner.lf_sha(POST_REVIEW) != POST_REVIEW_SHA256_LF
        or runner.lf_sha(Path("scripts/run_triangular_pre_aged_queue.py"))
        != RECOVERY_AUDITOR_SHA256_LF
        or runner.lf_sha(Path("tests/test_run_triangular_pre_aged_queue.py"))
        != RECOVERY_TEST_SHA256_LF
    ):
        raise ValueError("M024_RECOVERY_REVIEW_REQUIRED")

    run_manifest = json.loads(RUN_MANIFEST.read_bytes())
    failure = json.loads(FAILURE.read_bytes())
    terminal = json.loads(TERMINAL.read_bytes())
    if (
        run_manifest["model_id"] != "M024"
        or run_manifest["published_config_sha"] != SOURCE_COMMIT
        or failure["RUN_STATUS"] != "INCOMPLETE_PRESERVED"
        or failure["error"] != "M024_AUDIT_ACTIVATION"
        or failure["ledger_sha256"] != EXPECTED_PHYSICAL_SHA256["execution-audit.jsonl"]
        or terminal["schema"] != "M024_TRIANGULAR_PRE_AGED_QUEUE_V1"
    ):
        raise ValueError("M024_PRESERVED_IDENTITY_MISMATCH")
    for source_path, expected_sha in run_manifest["source_sha256_lf"].items():
        if source_path in {
            "scripts/run_triangular_pre_aged_queue.py",
            "tests/test_run_triangular_pre_aged_queue.py",
        }:
            continue
        if runner.lf_sha(Path(source_path)) != expected_sha:
            raise ValueError(f"M024_EXECUTION_SOURCE_DRIFT:{source_path}")

    manifest = json.loads(runner.MANIFEST.read_bytes())
    validation = json.loads(runner.VALIDATION_REPORT.read_bytes())
    profile, canonical, _slices, _evidence = runner.bounded_inputs(manifest, validation)
    rows = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines()]
    engine = runner.make_probe(profile)
    engine.restore(terminal)
    metrics = {key: value for key, value in engine.metrics().items() if key != "AUDIT"}
    audit = runner.independent_execution_audit(rows, terminal, canonical, metrics)
    if (
        audit["status"] != "PASS_M024_PHYSICAL_LEDGER"
        or audit["trades_delivered"] != 29538
        or audit["fill_fragments"] != 72
        or audit["complete_positive_cycles"] != 35
        or metrics["TOTAL_CYCLES"] != 35
        or metrics["FINAL_MARKED_EQUITY"] != "150.16160000"
        or metrics["PNL_IDENTITY_RESIDUAL"] != "0E-8"
    ):
        raise ValueError("M024_RECOVERED_AUDIT_MISMATCH")

    event_counts = Counter(row["event"] for row in rows)
    public_queue_consumed = sum(
        (D(row["quantity"]) for row in rows if row["event"] == "PUBLIC_QUEUE_CONSUMED"),
        D(0),
    )
    main_limiter = "UNDETERMINED_PENDING_POST_RUN_AUTOPSY"
    metrics = {**metrics, "MAIN_LIMITER": main_limiter}
    audit = {
        **audit,
        "terminal_sha256": terminal["sha256"],
        "ledger_sha256": file_sha(LEDGER),
        "recovery_mode": "READ_ONLY_CHECKPOINT_AND_LEDGER_NO_EVENT_REPLAY",
        "recovery_auditor_commit": RECOVERY_AUDITOR_COMMIT,
    }
    identity = {key: value for key, value in run_manifest.items() if key != "evidence"}
    return {
        **identity,
        "MODEL": "M024",
        "PERIOD": "3H",
        "RUN_STATUS": "COMPLETE_RECOVERED_FROM_PRESERVED_PHYSICAL_RUN",
        "ORIGINAL_RUN_EXIT_STATUS": "INCOMPLETE_PRESERVED_AUDITOR_DEFECT",
        "VERDICT": "M024_MECHANICS_MEASURED_NOT_STRATEGY_APPROVAL",
        "DISCLAIMER": engine.normalized_label,
        "METRICS": metrics,
        "AUDIT": audit,
        "AUDIT_FILE": str(LEDGER),
        "PHYSICAL_RUN_HASH": canonical_hash(EXPECTED_PHYSICAL_SHA256),
        "PHYSICAL_FILE_SHA256": EXPECTED_PHYSICAL_SHA256,
        "POST_RUN_REVIEW_SHA256": file_sha(POST_REVIEW),
        "RECOVERY_AUDITOR_COMMIT": RECOVERY_AUDITOR_COMMIT,
        "USDT_FINAL": metrics["FINAL_USDT"],
        "USDC_FINAL": metrics["FINAL_USDC"],
        "USDC_MARKED_VALUE": str(D(metrics["FINAL_MARKED_EQUITY"]) - D(metrics["FINAL_USDT"])),
        "TOTAL_FINAL_EQUITY": metrics["FINAL_MARKED_EQUITY"],
        "REALIZED_NET_PNL": metrics["REALIZED_DISPOSAL_PNL"],
        "COMPLETED_CYCLE_PNL": metrics["REALIZED_PNL"],
        "UNREALIZED_PNL": metrics["UNREALIZED_PNL"],
        "TARGET_10_PER_HOUR_PASS": metrics["TARGET_10_PER_HOUR_PASS"],
        "PASS_1000": False,
        "PASS_2000": False,
        "MAIN_LIMITER": main_limiter,
        "AUTOPSY": {
            "public_queue_consumption_events": event_counts["PUBLIC_QUEUE_CONSUMED"],
            "public_queue_quantity_consumed_usdc": str(public_queue_consumed),
            "orders_open_at_cutoff": metrics["OPEN_ORDER_COUNT"],
            "preaging_cases_censored_or_rejected": 10,
            "median_completed_order_wait_seconds": str(
                D(str(metrics["ORDER_QUEUE_WAIT_MEDIAN_US"])) / D(1_000_000)
            ),
            "p95_completed_order_wait_seconds": str(
                D(metrics["ORDER_QUEUE_WAIT_P95_US"]) / D(1_000_000)
            ),
            "m023_absolute_throughput_multiplier": "8.75",
            "capital_matched_comparison_valid": False,
            "m024_cycles_per_hour_per_100_usdt_eq": metrics["CYCLES_PER_100_USDT_EQ"],
            "interpretation": (
                "Absolute throughput exceeded the 30-cycle mechanics ruler, but used about "
                "150.13 USDT-equivalent versus about 1.00 in M023. The ledger records large "
                "public-queue consumption, long-tail completed-order waits and 138 orders "
                "open at cutoff. These are descriptive signals and do not isolate whether "
                "FIFO, price recovery, capital geometry or another interaction was causal."
            ),
        },
    }


def finalize() -> dict:
    report = recover_preserved_result()
    if _physical_hashes() != EXPECTED_PHYSICAL_SHA256:
        raise ValueError("M024_PHYSICAL_FILES_CHANGED_BEFORE_REGISTRY_APPEND")
    registry = ModelRegistry()
    if registry.current_status("M024") != ModelStatus.CREATED:
        raise ValueError("M024_FINALIZATION_REQUIRES_CREATED_STATUS")
    run_manifest = json.loads(RUN_MANIFEST.read_bytes())
    physical_hash = report["PHYSICAL_RUN_HASH"]
    scenario_event = registry.append_scenario(
        "M024",
        {
            "scenario": {
                "name": "M024_TRIANGULAR_PRE_AGED_QUEUE_3H_NORMALIZED_MECHANICS",
                "execution_profile": "B_REALISTIC_CONSERVATIVE",
                "execution_envelope": "PRICE_PRIORITY",
                "initial_usdt": "74.9900",
                "initial_usdc": "75",
                "capital_mode": "NORMALIZED_MECHANICS_PROBE",
                "physical_run_hash": physical_hash,
            }
        },
    )
    scenario_hash = scenario_event["payload"]["SCENARIO_HASH"]
    run_event = registry.append_run(
        "M024",
        RunSpec(
            scenario_hash=scenario_hash,
            dataset_hash=run_manifest["evidence"]["validation"]["input_sha256"],
            campaign_snapshot_id=physical_hash,
            interval={"start": report["start"], "end_exclusive": report["end_exclusive"]},
            code_commit=SOURCE_COMMIT,
            technical_revision="TRIANGULAR_PRE_AGED_QUEUE_V1",
            backend=BackendSpec(backend="CPU"),
            initial_capital=D("150.1325"),
            capital_mode="NORMALIZED_MECHANICS_PROBE",
            run={
                "artifact_directory": str(RUN_DIR),
                "physical_run_hash": physical_hash,
                "identity_run_hash": report["run_hash"],
                "audit_status": report["AUDIT"]["status"],
                "recovered_from_preserved_auditor_failure": True,
                "recovery_auditor_commit": RECOVERY_AUDITOR_COMMIT,
            },
        ),
    )
    registry_run_hash = run_event["payload"]["RUN_HASH"]
    registry.transition(
        "M024",
        ModelStatus.RUNNING,
        reason="Register the one immutable OWNER-authorized M024 physical run",
    )
    registry.append_evaluation(
        "M024",
        EvaluationSpec(
            scenario_hash=scenario_hash,
            campaign_snapshot_id=physical_hash,
            run_hash=registry_run_hash,
            comparison={
                "parent": "M023",
                "absolute_throughput_multiplier": "8.75",
                "capital_matched_comparison_valid": False,
                "reason": "M024 used about150.13 versus about1.00 USDT-equivalent in M023",
            },
            criteria={
                "preregistered_10_cycles_per_hour_gate": True,
                "strategy_pass": False,
                "live_executable": False,
                "rerun_performed": False,
            },
            metrics={
                "total_complete_cycles": 35,
                "cycles_per_hour": report["METRICS"]["CYCLES_PER_HOUR"],
                "total_marked_equity": report["TOTAL_FINAL_EQUITY"],
                "realized_net_pnl": report["REALIZED_NET_PNL"],
                "completed_cycle_pnl": report["COMPLETED_CYCLE_PNL"],
                "unrealized_pnl": report["UNREALIZED_PNL"],
                "audit_status": report["AUDIT"]["status"],
                "main_limiter": report["MAIN_LIMITER"],
            },
            replay={
                "start": report["start"],
                "end_exclusive": report["end_exclusive"],
                "physical_run_hash": physical_hash,
                "original_failure_preserved": str(FAILURE),
            },
            decision={
                "status": "INCONCLUSIVE",
                "mechanics_gate_passed": True,
                "reason": (
                    "The normalized three-hour mechanics gate passed and pre-aging benefit "
                    "was observed, but the result is non-executable and not capital-matched "
                    "to M023; no strategy or live-efficacy conclusion is authorized."
                ),
            },
        ),
    )
    registry.transition(
        "M024",
        ModelStatus.EVALUATED,
        reason="Preserved physical ledger and corrected independent audit reconciled",
    )
    registry.transition(
        "M024",
        ModelStatus.INCONCLUSIVE,
        reason="Mechanics gate passed, but one-USDC normalized result is not live-executable",
    )
    report["REGISTRY_RUN_HASH"] = registry_run_hash
    report["MODEL_STATUS"] = "INCONCLUSIVE"
    write_json(RECOVERED_AUDIT, report["AUDIT"])
    write_json(RECOVERED_SUMMARY, report)
    write_json(RESULT, report)
    if _physical_hashes() != EXPECTED_PHYSICAL_SHA256:
        raise ValueError("M024_PHYSICAL_FILES_CHANGED_DURING_FINALIZATION")
    return report


if __name__ == "__main__":
    value = finalize()
    print(
        json.dumps(
            {
                "MODEL": value["MODEL"],
                "TOTAL_CYCLES": value["METRICS"]["TOTAL_CYCLES"],
                "CYCLES_PER_HOUR": value["METRICS"]["CYCLES_PER_HOUR"],
                "TOTAL_FINAL_EQUITY": value["TOTAL_FINAL_EQUITY"],
                "MODEL_STATUS": value["MODEL_STATUS"],
                "RERUN": False,
            },
            sort_keys=True,
        )
    )
