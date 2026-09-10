"""Run the sole OWNER-authorized M030 full-day treatment."""

from __future__ import annotations

import json
import random
import re
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from crypto_strategy_lab.microstructure.hotline_first_reallocation import (
    DEFAULT_EVALUATION_WINDOWS,
    HotlineFirstDynamic321Probe,
)
from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelStatus, compute_model_hash
from scripts import run_m026_24h_extension as base
from scripts.audit_hotline_first_reallocation import (
    independent_m030_audit,
    reconstruct_m029_hot_coverage,
)
from scripts.audit_m026_24h_extension import normalize_full_day_metrics
from scripts.register_hotline_first_reallocation import (
    OWNER,
    PREREG,
    SPEC,
    registered_model_payload,
)
from scripts.run_high_uptime_recovery import (
    PROFILE_CONFIG,
    PROFILE_CONFIG_SHA,
    campaign_writer_lock,
    lf_sha,
    published_bytes,
    published_sha,
    validate_review,
)
from scripts.run_l2_monthly_samples import json_hash
from scripts.validate_tardis_l2_samples import MANIFEST, TRADE_MANIFEST
from scripts.validate_tardis_l2_samples import OUTPUT as VALIDATION_REPORT

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "M030"
RANDOM_SEED = 13_525_809_254_189_156_280
SELECTED_HOURS = (6, 12, 13)
OWNER_WINDOW = Path("docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md")
REVIEW = Path("reports/usdcusdt/M030-preflight-independent-review.md")
JOURNAL = Path("docs/research/M030_JOURNAL.md")
BASELINE_RESULT = Path("reports/usdcusdt/M029-m026-24h-result.json")
BASELINE_LEDGER = Path(
    "artifacts/usdcusdt/l2-monthly-samples/M029/OWNER_GATED_24H/PRICE_PRIORITY/"
    "execution-audit.jsonl"
)
OUTPUT = Path("artifacts/usdcusdt/l2-monthly-samples/M030/OWNER_GATED_24H/PRICE_PRIORITY")
RESULT = Path("reports/usdcusdt/M030-hotline-first-result.json")
MANAGEMENT_GATE_ADDENDUM = Path("docs/microstructure/M030_MANAGEMENT_GATE_ADDENDUM.md")
MANAGEMENT_COVERAGE_MIN_PP = D(5)
MANAGEMENT_STRANDED_REDUCTION_MIN_PCT = D(50)
SOURCE_PATHS = tuple(
    dict.fromkeys(
        (
            Path("src/crypto_strategy_lab/microstructure/hotline_first_reallocation.py"),
            Path("scripts/run_hotline_first_reallocation.py"),
            Path("scripts/audit_hotline_first_reallocation.py"),
            Path("scripts/register_hotline_first_reallocation.py"),
            Path("tests/test_hotline_first_reallocation.py"),
            Path("tests/test_run_hotline_first_reallocation.py"),
            Path("scripts/run_m026_24h_extension.py"),
            Path("scripts/audit_m026_24h_extension.py"),
            Path("scripts/audit_dynamic_hotline_321.py"),
            MANAGEMENT_GATE_ADDENDUM,
            *base.parent_runner.SOURCE_PATHS,
        )
    )
)


def require_owner_gate(root: Path = ROOT) -> None:
    authority = (root / OWNER_WINDOW).read_text(encoding="utf-8")
    for key, value in {
        "APPROVED_COMPARISON_DAYS": "1",
        "EXTENSION_AUTHORIZED": "false",
        "NEW_REPLAY_AUTHORIZED_NOW": "true",
        "AUTHORIZED_MODEL": MODEL_ID,
        "AUTHORIZED_SCENARIO_COUNT": "1",
    }.items():
        if re.findall(rf"^{key}=(.*)$", authority, flags=re.MULTILINE) != [value]:
            raise ValueError(f"M030_OWNER_GATE_REQUIRED:{key}")


def selected_hours(seed: int = RANDOM_SEED) -> tuple[int, ...]:
    return tuple(sorted(random.Random(seed).sample(range(3, 24), 3)))


def _assert_unused_output() -> None:
    if OUTPUT.exists() or RESULT.exists():
        raise ValueError("EXISTING_M030_EXPERIMENT_PRESERVED")


def campaign_preflight() -> tuple[str, dict[str, Any], dict[str, Any]]:
    require_owner_gate()
    _assert_unused_output()
    if selected_hours() != SELECTED_HOURS:
        raise ValueError("M030_RANDOM_SELECTION_DRIFT")
    if Path.cwd().resolve() != ROOT.resolve():
        raise ValueError("CANONICAL_REPOSITORY_CWD_REQUIRED")
    sha = published_sha()
    base._assert_published_head(sha)
    for path in (
        *SOURCE_PATHS,
        OWNER,
        OWNER_WINDOW,
        SPEC,
        PREREG,
        REVIEW,
        JOURNAL,
        BASELINE_RESULT,
        MANIFEST,
        VALIDATION_REPORT,
        TRADE_MANIFEST,
        PROFILE_CONFIG,
    ):
        published_bytes(path, sha)
    validate_review(REVIEW, SOURCE_PATHS)
    base._assert_parent_source_unchanged()
    baseline = json.loads(BASELINE_RESULT.read_bytes())
    physical = baseline["REGISTRY"]["physical_file_sha256"]
    if base.file_sha(BASELINE_LEDGER) != physical[str(BASELINE_LEDGER)]:
        raise ValueError("M030_BASELINE_LEDGER_CHANGED")
    if base.file_sha(PROFILE_CONFIG) != PROFILE_CONFIG_SHA:
        raise ValueError("M030_FROZEN_PROFILE_CHANGED")
    expected = registered_model_payload()
    registry = ModelRegistry()
    if registry.current_status("M026") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M030_REQUIRES_M026")
    if registry.current_status("M029") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M030_REQUIRES_M029")
    if registry.current_status(MODEL_ID) != ModelStatus.CREATED:
        raise ValueError("M030_REQUIRES_CREATED_STATUS")
    model = registry.get(MODEL_ID)
    if dict(model.model) != expected or model.model_hash != compute_model_hash(expected):
        raise ValueError("M030_REGISTERED_DESIGN_MISMATCH")
    return sha, json.loads(MANIFEST.read_bytes()), json.loads(VALIDATION_REPORT.read_bytes())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def matched_baseline() -> dict[str, Any]:
    result = json.loads(BASELINE_RESULT.read_bytes())
    metrics = result["METRICS"]
    cycles = [
        row
        for row in metrics["CYCLE_RECONCILIATION"]
        if any(left <= int(row["time_us"]) < right for left, right in DEFAULT_EVALUATION_WINDOWS)
    ]
    slots = sum(int(row["slot_equivalent_weight"]) for row in cycles)
    order_by_id = {
        int(row["order_id"]): row
        for row in _read_jsonl(BASELINE_LEDGER)
        if row["event"] == "SUBMIT"
    }
    return {
        "MODEL": "M029",
        "PHYSICAL_CYCLES": len(cycles),
        "PHYSICAL_CYCLES_PER_HOUR": str(D(len(cycles)) / D(3)),
        "SLOT_CYCLES": slots,
        "SLOT_CYCLES_PER_HOUR": str(D(slots) / D(3)),
        "BUY_FIRST": sum(
            order_by_id[int(row["entry_order_id"])]["direction"] == "BUY_FIRST" for row in cycles
        ),
        "SELL_FIRST": sum(
            order_by_id[int(row["entry_order_id"])]["direction"] == "SELL_FIRST" for row in cycles
        ),
        "ZONE_CYCLES": {
            zone: sum(row["origin_zone"] == zone for row in cycles)
            for zone in ("HOT", "MID", "FAR")
        },
        "COLUMN_CYCLES": {
            str(column): sum(int(row["column"]) == column for row in cycles) for column in (1, 2, 3)
        },
        "HOT_COVERAGE": reconstruct_m029_hot_coverage(
            _read_jsonl(BASELINE_LEDGER), DEFAULT_EVALUATION_WINDOWS
        ),
        "FULL_DAY_PHYSICAL_CYCLES": metrics["PHYSICAL_CYCLES"],
        "FULL_DAY_SLOT_CYCLES": metrics["SLOT_EQUIVALENT_CYCLES"],
        "BASELINE_LEDGER_SHA256": base.file_sha(BASELINE_LEDGER),
    }


def make_probe(profile) -> HotlineFirstDynamic321Probe:
    return HotlineFirstDynamic321Probe(
        start_us=base.START_US,
        end_us=base.END_US,
        latency_us=profile.latency_us,
        cancel_latency_us=profile.cancel_latency_us,
        evaluation_windows=DEFAULT_EVALUATION_WINDOWS,
    )


def execute(engine, canonical, slices, identity, evidence):
    _assert_unused_output()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    base.write_json(OUTPUT / "run-manifest.json", {**identity, "evidence": evidence})
    audit_file = OUTPUT / "execution-audit.jsonl"
    try:
        seen: set[str] = set()
        for event in base.bounded_native_events(slices):
            if event["kind"] == "BOOK":
                if event["sequence_validated"]:
                    engine.receive_book(
                        {
                            "exchange_time_us": event["exchange_us"],
                            "exchange_upper_us": event["exchange_upper_us"],
                            "capture_time_us": event["local_us"],
                            "bids": event["bids"],
                            "asks": event["asks"],
                            "known_bid_floor": event["known_bid_floor"],
                            "known_ask_ceiling": event["known_ask_ceiling"],
                        }
                    )
                continue
            if event["kind"] != "TRADE":
                raise ValueError("M030_UNKNOWN_NATIVE_EVENT")
            native = event["data"]
            trade = canonical.get(native["t"])
            if (
                trade is None
                or trade.trade_id in seen
                or D(native["p"]) != trade.price
                or D(native["q"]) != trade.quantity
                or native["m"] is not trade.buyer_maker
                or not base.trade_timestamp_matches(trade.time_us, native["T"])
            ):
                raise ValueError("M030_CANONICAL_TRADE_BINDING_CHANGED")
            consumed = engine.receive_trade(trade, capture_time_us=event["local_us"])
            if not D(0) <= consumed <= trade.quantity:
                raise ValueError("M030_GLOBAL_TRADE_BUDGET_EXCEEDED")
            seen.add(trade.trade_id)
        if seen != {trade.trade_id for trade in canonical.values()}:
            raise ValueError("M030_CANONICAL_24H_NOT_FULLY_DELIVERED")
        metrics = normalize_full_day_metrics(engine.finish(time_us=base.END_US), model_id=MODEL_ID)
        terminal = engine.checkpoint()
        base._write_ledger(audit_file, engine.audit)
        base.write_json(OUTPUT / "terminal-engine-state.json", terminal)
        audit = independent_m030_audit(
            engine.audit,
            terminal,
            metrics,
            canonical,
            DEFAULT_EVALUATION_WINDOWS,
        )
        audit.update(terminal_sha256=terminal["sha256"], ledger_sha256=base.file_sha(audit_file))
        baseline = matched_baseline()
        treatment_cycles = int(metrics["M030_EVAL_PHYSICAL_CYCLES"])
        baseline_cycles = int(baseline["PHYSICAL_CYCLES"])
        delta = treatment_cycles - baseline_cycles
        improvement_pct = D(delta) / D(baseline_cycles) * D(100) if baseline_cycles else None
        comparison = {
            "BASELINE": baseline,
            "TREATMENT": {
                "MODEL": MODEL_ID,
                "PHYSICAL_CYCLES": treatment_cycles,
                "PHYSICAL_CYCLES_PER_HOUR": metrics["M030_EVAL_PHYSICAL_CYCLES_PER_HOUR"],
                "SLOT_CYCLES": metrics["M030_EVAL_SLOT_CYCLES"],
                "SLOT_CYCLES_PER_HOUR": metrics["M030_EVAL_SLOT_CYCLES_PER_HOUR"],
                "HOT_COVERAGE_RANDOM_3H_TIME_WEIGHTED": metrics[
                    "HOT_FUNDING_COVERAGE_RANDOM_3H_TIME_WEIGHTED"
                ],
                "HOT_COVERAGE_FULL_DAY_TIME_WEIGHTED": metrics[
                    "HOT_FUNDING_COVERAGE_TIME_WEIGHTED"
                ],
                "RECLAIMABLE_STRANDED_RANDOM_3H_TIME_PCT": metrics[
                    "RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"
                ],
            },
            "PHYSICAL_CYCLE_DELTA": delta,
            "PHYSICAL_CYCLE_IMPROVEMENT_PCT": (
                None if improvement_pct is None else str(improvement_pct)
            ),
            "FREQUENCY_IMPROVEMENT_PASS": treatment_cycles > baseline_cycles,
            "STRONG_IMPROVEMENT_20PCT_PASS": (
                improvement_pct is not None and improvement_pct >= D(20)
            ),
        }
        baseline_coverage = D(baseline["HOT_COVERAGE"]["RANDOM_3H_TIME_WEIGHTED"])
        treatment_coverage = D(metrics["HOT_FUNDING_COVERAGE_RANDOM_3H_TIME_WEIGHTED"])
        coverage_delta_pp = (treatment_coverage - baseline_coverage) * D(100)
        baseline_stranded = D(
            baseline["HOT_COVERAGE"]["RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"]
        )
        treatment_stranded = D(metrics["RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"])
        stranded_reduction_pct = (
            (baseline_stranded - treatment_stranded) / baseline_stranded * D(100)
            if baseline_stranded > 0
            else (D(100) if treatment_stranded == 0 else D(-100))
        )
        coverage_pass = coverage_delta_pp >= MANAGEMENT_COVERAGE_MIN_PP
        stranded_pass = (
            treatment_stranded == 0
            if baseline_stranded == 0
            else stranded_reduction_pct >= MANAGEMENT_STRANDED_REDUCTION_MIN_PCT
        )
        comparison["MANAGEMENT"] = {
            "BASELINE_HOT_COVERAGE_RANDOM_3H": str(baseline_coverage),
            "TREATMENT_HOT_COVERAGE_RANDOM_3H": str(treatment_coverage),
            "COVERAGE_DELTA_PERCENTAGE_POINTS": str(coverage_delta_pp),
            "COVERAGE_MINIMUM_PERCENTAGE_POINTS": str(MANAGEMENT_COVERAGE_MIN_PP),
            "COVERAGE_PASS": coverage_pass,
            "BASELINE_RECLAIMABLE_STRANDED_TIME_PCT": str(baseline_stranded),
            "TREATMENT_RECLAIMABLE_STRANDED_TIME_PCT": str(treatment_stranded),
            "STRANDED_REDUCTION_PCT": str(stranded_reduction_pct),
            "STRANDED_REDUCTION_MINIMUM_PCT": str(MANAGEMENT_STRANDED_REDUCTION_MIN_PCT),
            "STRANDED_REDUCTION_PASS": stranded_pass,
            "MANAGEMENT_SUCCESS_PASS": coverage_pass
            and stranded_pass
            and audit["status"].startswith("PASS_"),
        }
        metrics["AUDIT"] = audit["status"]
        metrics["STATUS"] = "COMPLETE"
        result = {
            **identity,
            "MODEL": MODEL_ID,
            "PARENT_STRATEGY": "M026",
            "BASELINE": "M029",
            "PERIOD": "24H_CONTINUOUS_RANDOM_3H_PRIMARY",
            "RUN_STATUS": "COMPLETE",
            "VERDICT": "PENDING_POST_RUN_INTERPRETATION",
            "DISCLAIMER": engine.normalized_label,
            "RANDOM_EVALUATION": {
                "SEED": RANDOM_SEED,
                "HOURS_UTC": list(SELECTED_HOURS),
                "WINDOWS_US": [list(row) for row in DEFAULT_EVALUATION_WINDOWS],
                "MASK_AFFECTS_DECISIONS": False,
            },
            "MATCHED_COMPARISON": comparison,
            "METRICS": metrics,
            "AUDIT": audit,
            "AUDIT_FILE": str(audit_file),
        }
        base.write_json(OUTPUT / "independent-audit.json", audit)
        base.write_json(OUTPUT / "summary.json", result)
        base.write_json(RESULT, result)
        return result
    except BaseException as exc:
        if not audit_file.exists():
            base._write_ledger(audit_file, engine.audit)
        base.write_json(
            OUTPUT / "failure.json",
            {
                "RUN_STATUS": "INCOMPLETE_PRESERVED",
                "exception_type": type(exc).__name__,
                "error": str(exc),
                "run_hash": identity.get("run_hash"),
                "ledger_sha256": base.file_sha(audit_file),
            },
        )
        raise


def run():
    sha, manifest, validation = campaign_preflight()
    with campaign_writer_lock():
        profile, canonical, slices, evidence = base.bounded_inputs(manifest, validation)
        evidence["m030_random_windows"] = list(SELECTED_HOURS)
        evidence["m030_random_seed"] = RANDOM_SEED
        require_owner_gate()
        base._assert_published_head(sha)
        registry = ModelRegistry()
        model = registry.get(MODEL_ID)
        identity = {
            "model_id": MODEL_ID,
            "model_hash": model.model_hash,
            "parent_model_id": "M026",
            "baseline_model_id": "M029",
            "capital_mode": "PHYSICAL_DYNAMIC_NORMALIZED_MECHANICS_BANK",
            "order_notional_mode": "SLOT_BASE_1_USDT_EQ_WHOLE_USDC_NON_EXECUTABLE",
            "virtual_filter_override": "MIN_NOTIONAL_ONLY",
            "start": "2025-01-01T00:00:00Z",
            "end_exclusive": "2025-01-02T00:00:00Z",
            "published_config_sha": sha,
            "expected_trade_count": len(canonical),
            "source_sha256_lf": {path.as_posix(): lf_sha(path) for path in SOURCE_PATHS},
            "owner_directive_sha256_lf": lf_sha(OWNER),
            "owner_window_sha256_lf": lf_sha(OWNER_WINDOW),
            "spec_sha256_lf": lf_sha(SPEC),
            "protocol_sha256_lf": lf_sha(PREREG),
            "review_sha256_lf": lf_sha(REVIEW),
            "pre_run_journal_sha256_lf": lf_sha(JOURNAL),
            "data_manifest_sha256": base.file_sha(MANIFEST),
            "profile_sha256": base.file_sha(PROFILE_CONFIG),
            "baseline_result_sha256": base.file_sha(BASELINE_RESULT),
            "baseline_ledger_sha256": base.file_sha(BASELINE_LEDGER),
            "latency_us": profile.latency_us,
            "cancel_latency_us": profile.cancel_latency_us,
            "cutoff_liquidation": False,
            "another_day_authorized": False,
            "random_seed": RANDOM_SEED,
            "random_hours_utc": list(SELECTED_HOURS),
            "evidence_sha256": json_hash(evidence),
        }
        identity["run_hash"] = json_hash(identity)
        return execute(make_probe(profile), canonical, slices, identity, evidence)


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, default=str))
