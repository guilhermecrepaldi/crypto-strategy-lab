"""Repair M025 queue-zero reporting from preserved ledgers without event replay."""

from __future__ import annotations

import json
from decimal import Decimal as D
from pathlib import Path

from crypto_strategy_lab.microstructure.order_size_capacity import OrderSizeCapacityProbe
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from scripts.run_order_size_capacity import (
    END_US,
    MANIFEST,
    OUTPUT,
    RESULT,
    START_US,
    VALIDATION_REPORT,
    analyze_curve,
    bounded_inputs,
    compact_metrics,
    independent_scenario_audit,
)

RAW_RESULT = Path("reports/usdcusdt/M025-order-size-capacity-result-reporting-bug.json")
RAW_SUMMARY = OUTPUT / "summary-reporting-bug.json"
CORRECTION_SCHEMA = "M025_CORRECTED_DERIVED_REPORT_NO_EVENT_REPLAY_V1"
QUEUE_REPORT_FIELDS = {
    "MEDIAN_TIME_TO_QUEUE_ZERO_US",
    "QUEUE_ZERO_ACTIVATED_ORDER_DENOMINATOR",
    "QUEUE_ZERO_CENSORED_WITHOUT_FILL_COUNT",
    "QUEUE_ZERO_MISSING_REASON",
    "QUEUE_ZERO_NOT_OBSERVED_BEFORE_FIRST_FILL_COUNT",
    "QUEUE_ZERO_REACHED_COUNT",
    "QUEUE_ZERO_THEN_FILLED_COUNT",
    "QUEUE_ZERO_TIME_DEFINITION",
    "QUEUE_ZERO_TO_FIRST_FILL_DENOMINATOR",
    "TIME_PUBLIC_QUEUE_ZERO_TO_FIRST_OWN_FILL_US",
    "TIME_PUBLIC_QUEUE_ZERO_TO_FULL_OWN_FILL_US",
    "TIME_WAITING_PUBLIC_FIFO_US",
}


def _read(path: Path):
    return json.loads(path.read_bytes())


def _ledger(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _without_queue_reporting(metrics: dict) -> dict:
    return {key: value for key, value in metrics.items() if key not in QUEUE_REPORT_FIELDS}


def _jsonable(value):
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def recover() -> dict:
    original = _read(RESULT)
    physical_summary = _read(OUTPUT / "summary.json")
    if original != physical_summary:
        raise ValueError("M025_ORIGINAL_REPORT_COPIES_DIVERGED")
    if original["RUN_STATUS"] != "COMPLETE" or original["AUDIT"]["status"] != (
        "PASS_ALL_11_INDEPENDENT_SCENARIO_AUDITS"
    ):
        raise ValueError("M025_PHYSICAL_RUN_NOT_COMPLETE")

    if RAW_RESULT.exists() or RAW_SUMMARY.exists():
        if not (RAW_RESULT.exists() and RAW_SUMMARY.exists()):
            raise ValueError("M025_INCOMPLETE_REPORT_RECOVERY_PRESERVATION")
        if _read(RAW_RESULT) != original or _read(RAW_SUMMARY) != physical_summary:
            raise ValueError("M025_REPORT_RECOVERY_ALREADY_PERFORMED")
    else:
        write_json(RAW_RESULT, original)
        write_json(RAW_SUMMARY, original)

    manifest = _read(MANIFEST)
    validation = _read(VALIDATION_REPORT)
    _profile, canonical, _slices, _evidence = bounded_inputs(manifest, validation)
    corrected_full = []
    corrected_compact = []
    for old_scenario in original["SCENARIOS"]:
        quantity = D(old_scenario["ORDER_QUANTITY_USDC"])
        directory = OUTPUT / f"Q{int(quantity):05d}"
        terminal = _read(directory / "terminal-engine-state.json")
        ledger_path = directory / "execution-audit.jsonl"
        old_summary = directory / "summary.json"
        old_full_scenario = _read(old_summary)
        rows = _ledger(ledger_path)
        engine = OrderSizeCapacityProbe.from_checkpoint(
            terminal,
            start_us=START_US,
            end_us=END_US,
            order_quantity=quantity,
        )
        metrics = {key: value for key, value in engine.metrics().items() if key != "AUDIT"}
        old_metrics = old_full_scenario["METRICS"]
        if _jsonable(_without_queue_reporting(metrics)) != _without_queue_reporting(old_metrics):
            raise ValueError(f"M025_NONREPORTING_METRIC_CHANGED:Q{quantity}")
        for field in (
            "TIME_PUBLIC_QUEUE_ZERO_TO_FIRST_OWN_FILL_US",
            "TIME_PUBLIC_QUEUE_ZERO_TO_FULL_OWN_FILL_US",
            "TIME_WAITING_PUBLIC_FIFO_US",
        ):
            if any(value is not None and value < 0 for value in metrics[field].values()):
                raise ValueError(f"M025_NEGATIVE_CORRECTED_DURATION:{field}:Q{quantity}")
        audit = independent_scenario_audit(rows, terminal, canonical, metrics, quantity)
        audit.update(
            terminal_sha256=terminal["sha256"],
            ledger_sha256=file_sha(ledger_path),
            reporting_recovery="PASS_NO_EVENT_REPLAY",
        )
        scenario = {
            "ORDER_QUANTITY_USDC": str(quantity),
            "RUN_STATUS": "COMPLETE",
            "METRICS": metrics,
            "AUDIT": audit,
            "ARTIFACT_DIRECTORY": str(directory),
        }
        write_json(directory / "summary-reporting-bug.json", old_full_scenario)
        write_json(old_summary, scenario)
        corrected_full.append(scenario)
        corrected_compact.append({**scenario, "METRICS": compact_metrics(metrics)})

    analysis = analyze_curve(corrected_full)
    if analysis != original["ANALYSIS"]:
        raise ValueError("M025_ECONOMIC_CURVE_CHANGED_DURING_REPORT_RECOVERY")
    corrected = {
        **original,
        "SCENARIOS": corrected_compact,
        "ANALYSIS": analysis,
        "REPORTING_CORRECTION": {
            "schema": CORRECTION_SCHEMA,
            "status": "PASS",
            "event_replay_performed": False,
            "original_result_sha256": file_sha(RAW_RESULT),
            "physical_run_hash_unchanged": original["run_hash"],
            "changed_scope": sorted(QUEUE_REPORT_FIELDS),
            "economic_curve_unchanged": True,
            "all_11_physical_audits_repeated_from_preserved_ledgers": True,
            "cause": (
                "PUBLIC_ZERO_WAS_ATTRIBUTED_AFTER_FIRST_FILL_OR_CANCEL_ACK; "
                "CORRECTED_BY_LEDGER_ORDINAL_CENSORING"
            ),
        },
    }
    write_json(OUTPUT / "summary.json", corrected)
    write_json(RESULT, corrected)
    return corrected


if __name__ == "__main__":
    value = recover()
    print(
        json.dumps(
            {
                "STATUS": value["REPORTING_CORRECTION"]["status"],
                "RUN_HASH": value["run_hash"],
                "CAPACITY_KNEE": value["ANALYSIS"]["CAPACITY_KNEE_ORDER_SIZE"],
            },
            sort_keys=True,
        )
    )
