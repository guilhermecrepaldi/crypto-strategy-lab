"""One published-source M025 order-size capacity campaign."""

from __future__ import annotations

import json
import os
import re
import subprocess
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from crypto_strategy_lab.microstructure.order_size_capacity import AUTHORIZED_QUANTITIES
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelStatus, compute_model_hash
from scripts import run_triangular_pre_aged_queue as parent_runner
from scripts.audit_order_size_capacity import independent_order_size_audit
from scripts.register_order_size_capacity import (
    OWNER as OWNER_DIRECTIVE,
)
from scripts.register_order_size_capacity import (
    PREREG,
    SPEC,
    registered_model_payload,
    validate_registration_design,
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
from scripts.validate_tardis_l2_samples import MANIFEST, TRADE_MANIFEST, trade_timestamp_matches
from scripts.validate_tardis_l2_samples import OUTPUT as VALIDATION_REPORT

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "M025"
START, END = parent_runner.START, parent_runner.END
START_US, END_US = parent_runner.START_US, parent_runner.END_US
OWNER_WINDOW = Path("docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md")
REVIEW = Path("reports/usdcusdt/M025-preflight-independent-review.md")
JOURNAL = Path("docs/research/M025_JOURNAL.md")
PARENT_RESULT = Path("reports/usdcusdt/M024-3h-result.json")
OUTPUT = Path("artifacts/usdcusdt/l2-monthly-samples/M025/OWNER_GATED_3H/CAPACITY_CURVE")
RESULT = Path("reports/usdcusdt/M025-order-size-capacity-result.json")
AUTOPSY = Path("reports/usdcusdt/M025-order-size-capacity-autopsy.md")
SOURCE_PATHS = tuple(
    dict.fromkeys(
        (
            Path("scripts/run_order_size_capacity.py"),
            Path("scripts/audit_order_size_capacity.py"),
            Path("scripts/register_order_size_capacity.py"),
            Path("src/crypto_strategy_lab/microstructure/order_size_capacity.py"),
            Path("tests/test_order_size_capacity.py"),
            Path("tests/test_run_order_size_capacity.py"),
            Path("src/crypto_strategy_lab/microstructure/triangular_pre_aged_queue.py"),
            Path("scripts/run_triangular_pre_aged_queue.py"),
            *parent_runner.SOURCE_PATHS,
        )
    )
)


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def require_owner_gate(root: Path = ROOT) -> None:
    try:
        authority = (root / OWNER_WINDOW).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("M025_OWNER_GATE_REQUIRED:AUTHORITY_UNAVAILABLE") from exc
    for key, value in {
        "APPROVED_COMPARISON_DAYS": "1",
        "EXTENSION_AUTHORIZED": "false",
        "NEW_REPLAY_AUTHORIZED_NOW": "true",
        "AUTHORIZED_MODEL": MODEL_ID,
        "AUTHORIZED_SCENARIO_COUNT": "11",
    }.items():
        if re.findall(rf"^{key}=(.*)$", authority, flags=re.MULTILINE) != [value]:
            raise ValueError(f"M025_OWNER_GATE_REQUIRED:{key}")


def _assert_unused_output(output: Path = OUTPUT, result: Path = RESULT) -> None:
    if output.exists() or result.exists():
        raise ValueError("EXISTING_M025_CAMPAIGN_PRESERVED")


def _assert_published_head(sha: str) -> None:
    if _git_output("status", "--porcelain"):
        raise ValueError("PRE_EXECUTION_WORKTREE_NOT_CLEAN")
    if _git_output("branch", "--show-current") != "main":
        raise ValueError("CANONICAL_MAIN_REQUIRED")
    if any(_git_output("rev-parse", ref) != sha for ref in ("HEAD", "origin/main")):
        raise ValueError("M025_REQUIRES_PUBLISHED_HEAD")


def validate_frozen_design(design: dict[str, Any]) -> None:
    validate_registration_design(design)
    if tuple(D(value) for value in design["scenario_quantities_usdc"]) != AUTHORIZED_QUANTITIES:
        raise ValueError("M025_SCENARIO_SET_CHANGED")


def campaign_preflight() -> tuple[str, dict[str, Any], dict[str, Any]]:
    require_owner_gate()
    _assert_unused_output()
    if Path.cwd().resolve() != ROOT.resolve():
        raise ValueError("CANONICAL_REPOSITORY_CWD_REQUIRED")
    sha = published_sha()
    _assert_published_head(sha)
    for path in (
        *SOURCE_PATHS,
        OWNER_DIRECTIVE,
        OWNER_WINDOW,
        SPEC,
        PREREG,
        REVIEW,
        JOURNAL,
        PARENT_RESULT,
        MANIFEST,
        VALIDATION_REPORT,
        TRADE_MANIFEST,
        PROFILE_CONFIG,
    ):
        published_bytes(path, sha)
    validate_review(REVIEW, SOURCE_PATHS)
    if file_sha(PROFILE_CONFIG) != PROFILE_CONFIG_SHA:
        raise ValueError("FROZEN_PROFILE_CHANGED")
    expected = registered_model_payload()
    registry = ModelRegistry()
    if registry.current_status(MODEL_ID) != ModelStatus.CREATED:
        raise ValueError("M025_REQUIRES_CREATED_STATUS")
    model = registry.get(MODEL_ID)
    if dict(model.model) != expected or model.model_hash != compute_model_hash(expected):
        raise ValueError("M025_REGISTERED_DESIGN_MISMATCH")
    if registry.current_status("M024") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M025_REQUIRES_PRESERVED_INCONCLUSIVE_M024")
    return sha, json.loads(MANIFEST.read_bytes()), json.loads(VALIDATION_REPORT.read_bytes())


def bounded_inputs(manifest: dict[str, Any], validation: dict[str, Any]):
    return parent_runner.bounded_inputs(manifest, validation)


def bounded_native_events(slices):
    yield from parent_runner.bounded_native_events(slices)


def make_probe(profile, quantity: D):
    from crypto_strategy_lab.microstructure.order_size_capacity import OrderSizeCapacityProbe

    return OrderSizeCapacityProbe(
        order_quantity=quantity,
        start_us=START_US,
        end_us=END_US,
        latency_us=profile.latency_us,
        cancel_latency_us=profile.cancel_latency_us,
    )


def _write_ledger(path: Path, rows) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def independent_scenario_audit(rows, terminal, canonical, metrics, quantity: D):
    """Run the full M025 reconstruction in unscaled physical USDC units."""

    audit = independent_order_size_audit(rows, terminal, canonical, metrics, quantity)
    if audit["growth_cells"] != 0:
        raise ValueError("M025_AUDIT_GROWTH_EXPANSION_DISABLED")
    return {
        **audit,
        "status": "PASS_M025_INDEPENDENT_SCENARIO_AUDIT",
        "order_quantity_usdc": str(quantity),
        "exact_physical_unit_reconstruction": True,
        "normalized_reconstruction_used": False,
    }


def _ratio(current: D, previous: D) -> str | None:
    return str(current / previous) if previous != 0 else None


def compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    detailed = {
        "AUDIT",
        "QUEUE_AHEAD_AT_ACTIVATION",
        "QUEUE_AHEAD_AT_ACTIVATION_C1",
        "QUEUE_AHEAD_AT_ACTIVATION_C2",
        "QUEUE_AHEAD_AT_TIME_C1_FILLED_FOR_C2",
        "PRE_AGING_CASE_ROWS",
        "COLUMN_TABLE",
    }
    return {key: value for key, value in metrics.items() if key not in detailed}


def analyze_curve(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    first_drop: str | None = None
    knee: str | None = None
    for index, scenario in enumerate(scenarios):
        metrics = scenario["METRICS"]
        q = D(metrics["ORDER_QUANTITY_USDC"])
        cycles = D(metrics["TOTAL_CYCLES"])
        rate = D(metrics["CYCLES_PER_HOUR"])
        row: dict[str, Any] = {
            "ORDER_QTY_USDC": str(q),
            "INITIAL_MARKED_EQUITY": metrics["INITIAL_MARKED_EQUITY"],
            "TOTAL_CYCLES": int(cycles),
            "CYCLES_PER_HOUR": str(rate),
            "COMPLETED_ROUNDTRIP_USDC": metrics["COMPLETED_ROUNDTRIP_USDC"],
            "COMPLETED_ROUNDTRIP_USDC_PER_HOUR": metrics["COMPLETED_ROUNDTRIP_USDC_PER_HOUR"],
            "ROUNDTRIP_USDC_PER_HOUR_PER_1000_INITIAL_USDT": metrics[
                "ROUNDTRIP_USDC_PER_HOUR_PER_1000_INITIAL_USDT"
            ],
            "TOTAL_FILL_EVENTS": metrics["TOTAL_FILL_EVENTS"],
            "TOTAL_FILLED_QTY_USDC": metrics["TOTAL_FILLED_QTY_USDC"],
            "PARTIAL_FILL_RATE": metrics["PARTIAL_FILL_RATE"],
            "RESIDUAL_PARTIAL_ORDER_COUNT": metrics["RESIDUAL_PARTIAL_ORDER_COUNT"],
            "RESIDUAL_PARTIAL_QTY_USDC": metrics["RESIDUAL_PARTIAL_QTY_USDC"],
            "FULL_FILL_RATE": metrics["FULL_FILL_RATE"],
            "MEDIAN_TIME_TO_FULL_FILL_US": metrics["MEDIAN_TIME_TO_FULL_FILL_US"],
            "P95_TIME_TO_FULL_FILL_US": metrics["P95_TIME_TO_FULL_FILL_US"],
            "FINAL_MARKED_EQUITY": metrics["FINAL_MARKED_EQUITY"],
            "REALIZED_PNL": metrics["REALIZED_PNL"],
            "REALIZED_PNL_PER_HOUR": metrics["REALIZED_PNL_PER_HOUR"],
            "PNL_PER_HOUR_PER_1000_INITIAL_USDT": metrics["PNL_PER_HOUR_PER_1000_INITIAL_USDT"],
            "UNREALIZED_PNL": metrics["UNREALIZED_PNL"],
        }
        if index:
            prior = scenarios[index - 1]["METRICS"]
            prev_rate = D(prior["CYCLES_PER_HOUR"])
            retention = rate / prev_rate if prev_rate else None
            drop = (prev_rate - rate) / prev_rate if prev_rate else None
            size_multiplier = q / D(prior["ORDER_QUANTITY_USDC"])
            prior_roundtrip = D(prior["COMPLETED_ROUNDTRIP_USDC_PER_HOUR"])
            roundtrip = D(metrics["COMPLETED_ROUNDTRIP_USDC_PER_HOUR"])
            throughput_multiplier = roundtrip / prior_roundtrip if prior_roundtrip else None
            row.update(
                CYCLE_RATE_RETENTION_VS_PREVIOUS=(
                    str(retention) if retention is not None else None
                ),
                CYCLE_RATE_DROP_VS_PREVIOUS=(str(drop) if drop is not None else None),
                CYCLE_RATE_PERCENT_CHANGE_VS_PREVIOUS=(
                    str(retention - D(1)) if retention is not None else None
                ),
                SIZE_MULTIPLIER=str(size_multiplier),
                ROUNDTRIP_THROUGHPUT_MULTIPLIER=(
                    str(throughput_multiplier) if throughput_multiplier is not None else None
                ),
                SCALING_EFFICIENCY=(
                    str(throughput_multiplier / size_multiplier)
                    if throughput_multiplier is not None
                    else None
                ),
            )
            row["SCALING_EFFICIENCY_ALIAS"] = row["CYCLE_RATE_RETENTION_VS_PREVIOUS"]
            previous_full_rate = D(prior["FULL_FILL_RATE"])
            full_rate = D(metrics["FULL_FILL_RATE"])
            prior_latency = prior["MEDIAN_TIME_TO_FULL_FILL_US"]
            latency = metrics["MEDIAN_TIME_TO_FULL_FILL_US"]
            confirmations = {
                "residual_partial_orders_increased": metrics["RESIDUAL_PARTIAL_ORDER_COUNT"]
                > prior["RESIDUAL_PARTIAL_ORDER_COUNT"],
                "full_fill_rate_dropped_ge_10pp": previous_full_rate - full_rate >= D("0.10"),
                "median_full_fill_time_increased_ge_20pct": (
                    prior_latency is not None
                    and latency is not None
                    and D(str(latency)) >= D(str(prior_latency)) * D("1.20")
                ),
            }
            row["ORTHOGONAL_CONFIRMATIONS"] = confirmations
            if drop is not None and drop >= D("0.20") and first_drop is None:
                first_drop = str(q)
            if (
                drop is not None
                and drop >= D("0.20")
                and any(confirmations.values())
                and knee is None
            ):
                knee = str(q)
        else:
            row.update(
                CYCLE_RATE_RETENTION_VS_PREVIOUS=None,
                CYCLE_RATE_DROP_VS_PREVIOUS=None,
                CYCLE_RATE_PERCENT_CHANGE_VS_PREVIOUS=None,
                SIZE_MULTIPLIER=None,
                ROUNDTRIP_THROUGHPUT_MULTIPLIER=None,
                SCALING_EFFICIENCY=None,
                SCALING_EFFICIENCY_ALIAS=None,
                ORTHOGONAL_CONFIRMATIONS=None,
            )
        rows.append(row)

    def rank(metric: str) -> list[dict[str, Any]]:
        return sorted(
            rows,
            key=lambda row: (
                -D(row[metric]),
                D(row["ORDER_QTY_USDC"]),
            ),
        )

    ranked_cycles = rank("TOTAL_CYCLES")
    ranked_roundtrip = rank("COMPLETED_ROUNDTRIP_USDC_PER_HOUR")
    ranked_realized = rank("REALIZED_PNL_PER_HOUR")
    ranked_efficiency = rank("ROUNDTRIP_USDC_PER_HOUR_PER_1000_INITIAL_USDT")
    q500 = next(row for row in rows if row["ORDER_QTY_USDC"] == "500")
    all_zero = all(row["TOTAL_CYCLES"] == 0 for row in rows)
    if all_zero:
        capacity_knee = "INSUFFICIENT_EVIDENCE_ALL_SCENARIOS_ZERO_CYCLES"
    elif knee:
        capacity_knee = knee
    elif first_drop:
        capacity_knee = "CYCLE_DROP_WITHOUT_ORTHOGONAL_CONFIRMATION"
    else:
        capacity_knee = "NOT_OBSERVED_UP_TO_5000_USDC"
    future_bases: dict[str, dict[str, Any]] = {
        "B250": {"HOT_3B": "750", "MID_2B": "500", "FAR_1B": "250"},
        "B500": {"HOT_3B": "1500", "MID_2B": "1000", "FAR_1B": "500"},
        "B1000": {"HOT_3B": "3000", "MID_2B": "2000", "FAR_1B": "1000"},
    }
    for base in future_bases.values():
        base["ALL_THREE_SIZES_BELOW_OBSERVED_KNEE"] = (
            all(D(base[key]) < D(knee) for key in ("HOT_3B", "MID_2B", "FAR_1B"))
            if knee is not None
            else None
        )
    owner_500_bottleneck = (
        "INCONCLUSIVE"
        if all_zero or capacity_knee == "CYCLE_DROP_WITHOUT_ORTHOGONAL_CONFIRMATION"
        else ("YES" if knee is not None and D(knee) <= D(500) else "NO")
    )
    return {
        "CURVE": rows,
        "FIRST_SIZE_WITH_GE20_CYCLE_RATE_DROP": first_drop,
        "FIRST_MATERIAL_CYCLE_RATE_DEGRADATION": first_drop,
        "CAPACITY_KNEE": capacity_knee,
        "CAPACITY_KNEE_ORDER_SIZE": capacity_knee,
        "BEST_RAW_CYCLES": ranked_cycles[0]["ORDER_QTY_USDC"],
        "BEST_CYCLES_PER_HOUR_SIZE": ranked_cycles[0]["ORDER_QTY_USDC"],
        "MAX_ROUNDTRIP_USDC_PER_HOUR_SIZE": ranked_roundtrip[0]["ORDER_QTY_USDC"],
        "MAX_REALIZED_PNL_PER_HOUR_SIZE": ranked_realized[0]["ORDER_QTY_USDC"],
        "MAX_CAPITAL_EFFICIENCY_SIZE": ranked_efficiency[0]["ORDER_QTY_USDC"],
        "Q500_SCOREBOARD": q500,
        "Q500_COMPARISONS": {
            q: next(row for row in rows if row["ORDER_QTY_USDC"] == q)
            for q in ("250", "750", "1000")
        },
        "Q1000_TO_Q1500": {
            q: next(row for row in rows if row["ORDER_QTY_USDC"] == q) for q in ("1000", "1500")
        },
        "OWNER_500_BOTTLENECK": owner_500_bottleneck,
        "OWNER_500_CYCLES_PER_HOUR": q500["CYCLES_PER_HOUR"],
        "OWNER_500_ROUNDTRIP_USDC_PER_HOUR": q500["COMPLETED_ROUNDTRIP_USDC_PER_HOUR"],
        "OWNER_500_PARTIAL_FILL_RATE": q500["PARTIAL_FILL_RATE"],
        "OWNER_500_MEDIAN_FULL_FILL_SECONDS": (
            q500["MEDIAN_TIME_TO_FULL_FILL_US"] / 1_000_000
            if q500["MEDIAN_TIME_TO_FULL_FILL_US"] is not None
            else None
        ),
        "OWNER_500_P95_FULL_FILL_SECONDS": (
            q500["P95_TIME_TO_FULL_FILL_US"] / 1_000_000
            if q500["P95_TIME_TO_FULL_FILL_US"] is not None
            else None
        ),
        "OWNER_500_REALIZED_PNL_PER_HOUR": q500["REALIZED_PNL_PER_HOUR"],
        "DIAGNOSTIC_FUTURE_BASES": future_bases,
        "DIAGNOSTIC_FUTURE_EXECUTED": False,
        "LIMITATION": "EXOGENOUS_TAPE_NO_ENDOGENOUS_MARKET_IMPACT_TRUE_QUEUE_RANK_UNKNOWN",
    }


def execute(engines, canonical, slices, identity, evidence, output=OUTPUT, result_path=RESULT):
    _assert_unused_output(output, result_path)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "run-manifest.json", {**identity, "evidence": evidence})
    try:
        seen: set[int] = set()
        for event in bounded_native_events(slices):
            if event["kind"] == "BOOK":
                if event["sequence_validated"]:
                    payload = {
                        "exchange_time_us": event["exchange_us"],
                        "exchange_upper_us": event["exchange_upper_us"],
                        "capture_time_us": event["local_us"],
                        "bids": event["bids"],
                        "asks": event["asks"],
                        "known_bid_floor": event["known_bid_floor"],
                        "known_ask_ceiling": event["known_ask_ceiling"],
                    }
                    for engine in engines.values():
                        engine.receive_book(payload)
                continue
            if event["kind"] != "TRADE":
                raise ValueError("M025_UNKNOWN_NATIVE_EVENT")
            native = event["data"]
            item = canonical.get(native["t"])
            if (
                item is None
                or item.trade_id in seen
                or D(native["p"]) != item.price
                or D(native["q"]) != item.quantity
                or native["m"] is not item.buyer_maker
                or not trade_timestamp_matches(item.time_us, native["T"])
            ):
                raise ValueError("M025_CANONICAL_TRADE_BINDING_CHANGED")
            for engine in engines.values():
                consumed = engine.receive_trade(item, capture_time_us=event["local_us"])
                if not D(0) <= consumed <= item.quantity:
                    raise ValueError("M025_GLOBAL_TRADE_BUDGET_EXCEEDED")
            seen.add(item.trade_id)
        if seen != set(canonical):
            raise ValueError("M025_CANONICAL_3H_NOT_FULLY_DELIVERED")

        scenarios = []
        compact_scenarios = []
        for quantity, engine in engines.items():
            scenario_dir = output / f"Q{int(quantity):05d}"
            scenario_dir.mkdir()
            metrics = {
                key: value for key, value in engine.finish(time_us=END_US).items() if key != "AUDIT"
            }
            terminal = engine.checkpoint()
            ledger = scenario_dir / "execution-audit.jsonl"
            _write_ledger(ledger, engine.audit)
            write_json(scenario_dir / "terminal-engine-state.json", terminal)
            audit = independent_scenario_audit(engine.audit, terminal, canonical, metrics, quantity)
            audit.update(terminal_sha256=terminal["sha256"], ledger_sha256=file_sha(ledger))
            scenario = {
                "ORDER_QUANTITY_USDC": str(quantity),
                "RUN_STATUS": "COMPLETE",
                "METRICS": metrics,
                "AUDIT": audit,
                "ARTIFACT_DIRECTORY": str(scenario_dir),
            }
            write_json(scenario_dir / "summary.json", scenario)
            scenarios.append(scenario)
            compact_scenarios.append(
                {
                    **scenario,
                    "METRICS": compact_metrics(metrics),
                }
            )
        analysis = analyze_curve(scenarios)
        owner_scoreboard = {
            "MODEL": MODEL_ID,
            "PERIOD": "3H_PER_SCENARIO",
            "SCENARIOS_COMPLETED": len(scenarios),
            "BEST_CYCLES_PER_HOUR_SIZE": analysis["BEST_CYCLES_PER_HOUR_SIZE"],
            "MAX_ROUNDTRIP_USDC_PER_HOUR_SIZE": analysis["MAX_ROUNDTRIP_USDC_PER_HOUR_SIZE"],
            "MAX_REALIZED_PNL_PER_HOUR_SIZE": analysis["MAX_REALIZED_PNL_PER_HOUR_SIZE"],
            "MAX_CAPITAL_EFFICIENCY_SIZE": analysis["MAX_CAPITAL_EFFICIENCY_SIZE"],
            "FIRST_MATERIAL_CYCLE_RATE_DEGRADATION": analysis[
                "FIRST_MATERIAL_CYCLE_RATE_DEGRADATION"
            ],
            "CAPACITY_KNEE_ORDER_SIZE": analysis["CAPACITY_KNEE_ORDER_SIZE"],
            "OWNER_500_BOTTLENECK": analysis["OWNER_500_BOTTLENECK"],
            "OWNER_500_CYCLES_PER_HOUR": analysis["OWNER_500_CYCLES_PER_HOUR"],
            "OWNER_500_ROUNDTRIP_USDC_PER_HOUR": analysis["OWNER_500_ROUNDTRIP_USDC_PER_HOUR"],
            "OWNER_500_PARTIAL_FILL_RATE": analysis["OWNER_500_PARTIAL_FILL_RATE"],
            "OWNER_500_MEDIAN_FULL_FILL_SECONDS": analysis["OWNER_500_MEDIAN_FULL_FILL_SECONDS"],
            "OWNER_500_P95_FULL_FILL_SECONDS": analysis["OWNER_500_P95_FULL_FILL_SECONDS"],
            "OWNER_500_REALIZED_PNL_PER_HOUR": analysis["OWNER_500_REALIZED_PNL_PER_HOUR"],
            "BASE500_FUTURE_3X_SIZE": "1500",
            "BASE500_FUTURE_2X_SIZE": "1000",
            "BASE500_FUTURE_1X_SIZE": "500",
            "BASE500_ALL_BELOW_CAPACITY_KNEE": analysis["DIAGNOSTIC_FUTURE_BASES"]["B500"][
                "ALL_THREE_SIZES_BELOW_OBSERVED_KNEE"
            ],
            "AUDIT": "PASS_ALL_11_INDEPENDENT_SCENARIO_AUDITS",
            "STATUS": "COMPLETE_CAPACITY_CURVE_NOT_LIVE_VALIDATION",
        }
        result = {
            **identity,
            "MODEL": MODEL_ID,
            "PERIOD": "3H",
            "RUN_STATUS": "COMPLETE",
            "VERDICT": "M025_CAPACITY_CURVE_MEASURED_NOT_LIVE_VALIDATION",
            "DISCLAIMER": next(iter(engines.values())).normalized_label,
            "SCENARIOS": compact_scenarios,
            "ANALYSIS": analysis,
            "OWNER_SCOREBOARD": owner_scoreboard,
            "AUDIT": {
                "status": "PASS_ALL_11_INDEPENDENT_SCENARIO_AUDITS",
                "scenario_count": len(scenarios),
                "all_trade_budgets_independent": True,
                "all_growth_expansion_disabled": True,
            },
        }
        write_json(output / "summary.json", result)
        write_json(result_path, result)
        return result
    except BaseException as exc:
        for quantity, engine in engines.items():
            scenario_dir = output / f"Q{int(quantity):05d}"
            scenario_dir.mkdir(exist_ok=True)
            ledger = scenario_dir / "execution-audit.jsonl"
            if not ledger.exists():
                _write_ledger(ledger, engine.audit)
            checkpoint = scenario_dir / "preserved-prefix-state.json"
            if not checkpoint.exists():
                write_json(checkpoint, engine.checkpoint())
        write_json(
            output / "failure.json",
            {
                "RUN_STATUS": "INCOMPLETE_PRESERVED_NO_RERUN",
                "exception_type": type(exc).__name__,
                "error": str(exc),
                "run_hash": identity.get("run_hash"),
            },
        )
        raise


def run():
    sha, manifest, validation = campaign_preflight()
    with campaign_writer_lock():
        _assert_unused_output()
        profile, canonical, slices, evidence = bounded_inputs(manifest, validation)
        require_owner_gate()
        _assert_published_head(sha)
        model = ModelRegistry().get(MODEL_ID)
        identity = {
            "model_id": MODEL_ID,
            "model_hash": model.model_hash,
            "capital_mode": "PROPORTIONAL_NORMALIZED_CAPACITY_CURVE",
            "scenario_quantities_usdc": [str(value) for value in AUTHORIZED_QUANTITIES],
            "only_independent_variable": "ORDER_QUANTITY_USDC",
            "start": "2025-01-01T00:00:00Z",
            "end_exclusive": "2025-01-01T03:00:00Z",
            "published_config_sha": sha,
            "expected_trade_count_per_scenario": len(canonical),
            "source_sha256_lf": {path.as_posix(): lf_sha(path) for path in SOURCE_PATHS},
            "owner_directive_sha256_lf": lf_sha(OWNER_DIRECTIVE),
            "owner_window_sha256_lf": lf_sha(OWNER_WINDOW),
            "spec_sha256_lf": lf_sha(SPEC),
            "protocol_sha256_lf": lf_sha(PREREG),
            "review_sha256_lf": lf_sha(REVIEW),
            "pre_run_journal_sha256_lf": lf_sha(JOURNAL),
            "data_manifest_sha256": file_sha(MANIFEST),
            "profile_sha256": file_sha(PROFILE_CONFIG),
            "latency_us": profile.latency_us,
            "cancel_latency_us": profile.cancel_latency_us,
            "growth_structural_expansion_enabled": False,
            "endogenous_market_impact": False,
            "true_historical_queue_rank_known": False,
            "cutoff_liquidation": False,
            "day2_authorized": False,
            "evidence_sha256": json_hash(evidence),
        }
        identity["run_hash"] = json_hash(identity)
        engines = {quantity: make_probe(profile, quantity) for quantity in AUTHORIZED_QUANTITIES}
        return execute(engines, canonical, slices, identity, evidence)


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, default=str))
