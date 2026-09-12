#!/usr/bin/env python3
"""Run the one-shot M035 single-versus-parallel economic campaign."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
import traceback
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from crypto_strategy_lab.microstructure.m035_data import merged_events, validate_dual_tape
from crypto_strategy_lab.microstructure.m035_economic_backtest import (
    M035BacktestConfig,
    M035BacktestExecutionError,
    run_mode,
)

IDENTITY = "M035_200USD_3H_PARALLEL_DEVELOPMENT_BACKTEST_V1"
CONFIG_PATH = Path("reports/m035/M035_200USD_3H_CONFIG.json")
DATA_REPORT_PATH = Path("reports/m035/M035_DUAL_TAPE_VALIDATION.json")
ECONOMIC_CONFORMANCE_PATH = Path("reports/m035/M035_ECONOMIC_CONFORMANCE_REPORT.json")
REVIEW_PATH = Path("reports/m035/M035_ECONOMIC_SOURCE_REVIEW.json")
RESULT_PATH = Path("reports/m035/M035_200USD_3H_RESULT.json")
CLAIM_PATH = Path("data/m035/M035_200USD_3H_PARALLEL_DEVELOPMENT_BACKTEST_V1.claim.json")
FEES = (D(0), D(1), D(2), D(5), D(10))
REQUIRED_REVIEW_FILES = {
    "src/crypto_strategy_lab/microstructure/m035_economic_backtest.py",
    "src/crypto_strategy_lab/microstructure/m035_data.py",
    "src/crypto_strategy_lab/microstructure/parallel_pair_capital_manager.py",
    "src/crypto_strategy_lab/microstructure/multi_stable_queue.py",
    "src/crypto_strategy_lab/microstructure/tardis_l2.py",
    "src/crypto_strategy_lab/microstructure/data.py",
    "scripts/run_m035_economic_backtest.py",
    "scripts/validate_m035_dual_tape.py",
    "tests/test_m035_economic_backtest.py",
    "reports/m035/M035_200USD_3H_CONFIG.json",
    "reports/m035/M035_DUAL_TAPE_VALIDATION.json",
    "reports/m035/M035_ECONOMIC_CONFORMANCE_REPORT.json",
    "docs/research/M035_200USD_3H_ECONOMIC_PROTOCOL.md",
}
ECONOMIC_CONFORMANCE_FILES = {
    "src/crypto_strategy_lab/microstructure/m035_economic_backtest.py",
    "src/crypto_strategy_lab/microstructure/m035_data.py",
    "src/crypto_strategy_lab/microstructure/parallel_pair_capital_manager.py",
    "src/crypto_strategy_lab/microstructure/multi_stable_queue.py",
    "tests/test_m035_economic_backtest.py",
    "tests/test_m035_parallel_pair_capital_manager.py",
}


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8").strip()


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _create_json_exclusive(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for original in rows:
            row = {
                key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                for key, value in original.items()
            }
            writer.writerow(row)


def _config(row: dict[str, Any]) -> M035BacktestConfig:
    return M035BacktestConfig(
        identity=row["identity"],
        start_us=int(row["start_us"]),
        end_us=int(row["end_us"]),
        initial_bank_usdt=D(row["initial_bank_usdt"]),
        order_quantity=D(row["order_quantity"]),
        tick_size=D(row["tick_size"]),
        quantity_step=D(row["quantity_step"]),
        minimum_quantity=D(row["minimum_quantity"]),
        minimum_notional=D(row["minimum_notional"]),
        activation_latency_us=int(row["activation_latency_us"]),
        cancel_ack_latency_us=int(row["cancel_ack_latency_us"]),
        execution_cost_bps=D(row["execution_cost_bps_round_trip"]),
        adverse_selection_bps=D(row["adverse_selection_bps_round_trip"]),
        risk_buffer_bps=D(row["risk_buffer_bps"]),
        minimum_net_edge_bps=D(row["minimum_net_edge_bps"]),
        maximum_spread_bps=D(row["maximum_spread_bps"]),
        minimum_depth_usd=D(row["minimum_depth_usd"]),
        minimum_flow_per_second=D(row["minimum_compatible_flow_asset_per_second"]),
        flow_window_seconds=int(row["flow_window_seconds"]),
        maximum_book_age_us=int(row["maximum_book_age_us"]),
        emergency_peg_deviation=D(row["emergency_peg_deviation"]),
        taker_fee_bps=D(row["taker_contingency_fee_bps"]),
    )


def _validate_pre_run(root: Path) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    if _git(root, "status", "--porcelain"):
        raise RuntimeError("M035_PRE_RUN_REQUIRES_CLEAN_TREE")
    head = _git(root, "rev-parse", "HEAD")
    origin = _git(root, "rev-parse", "origin/main")
    if head != origin:
        raise RuntimeError("M035_HEAD_NOT_PUBLISHED_ORIGIN_MAIN")
    config = json.loads((root / CONFIG_PATH).read_text(encoding="utf-8"))
    if config["identity"] != IDENTITY or tuple(map(D, config["fee_scenarios_bps"])) != FEES:
        raise RuntimeError("M035_FROZEN_CONFIG_MISMATCH")
    config_hash = _canonical_hash(config)
    conformance = json.loads(
        (root / "reports/m035/M035_CONFORMANCE_REPORT.json").read_text(encoding="utf-8")
    )
    required = {
        "HOTLINE_ISOLATION",
        "GRID_FOLLOWS_HOTLINE",
        "C1_FIFO_PRESERVATION",
        "C2_MOBILITY",
        "GLOBAL_CAPITAL_CONSERVATION",
        "NO_DOUBLE_CAPITAL",
        "OWNED_RETURN_PRIORITY",
        "DUST_ACCOUNTING",
        "ZERO_LOSS_ATTRIBUTION",
        "CANCEL_ACK",
        "NO_SELF_FILL",
        "NO_FUTURE_DATA",
    }
    if not conformance["ALL_REQUIRED_GATES_PASS"] or any(
        conformance["CHECKS"][name]["STATUS"] != "PASS" for name in required
    ):
        raise RuntimeError("M035_CONFORMANCE_GATE_FAILED")
    economic_conformance = json.loads(
        (root / ECONOMIC_CONFORMANCE_PATH).read_text(encoding="utf-8")
    )
    economic_required = {
        *required,
        "ATOMIC_FILL",
        "DUAL_TAPE_ALIGNMENT",
        "DUAL_TAPE_CONTINUITY",
        "DETERMINISTIC_MERGE_ORDERING",
        "EXCLUSIVE_ONE_SHOT_CLAIM",
        "PREFIX_PRESERVATION",
    }
    tested_commit = str(economic_conformance.get("tested_source_commit", ""))
    if (
        economic_conformance.get("identity") != IDENTITY
        or economic_conformance.get("status") != "PASS"
        or not economic_conformance.get("all_required_gates_pass")
        or economic_conformance.get("config_sha256") != config_hash
        or economic_conformance.get("window_hash") != config["window_hash"]
        or economic_conformance.get("pair_a_data_hash") != config["pair_a_data_hash"]
        or economic_conformance.get("pair_b_data_hash") != config["pair_b_data_hash"]
        or any(
            economic_conformance.get("checks", {}).get(name, {}).get("status") != "PASS"
            for name in economic_required
        )
        or not tested_commit
    ):
        raise RuntimeError("M035_ECONOMIC_CONFORMANCE_GATE_FAILED")
    if (
        subprocess.call(["git", "merge-base", "--is-ancestor", tested_commit, head], cwd=root)
        != 0
        or subprocess.call(
            [
                "git",
                "diff",
                "--quiet",
                tested_commit,
                "--",
                *sorted(ECONOMIC_CONFORMANCE_FILES),
            ],
            cwd=root,
        )
        != 0
    ):
        raise RuntimeError("M035_ECONOMIC_CONFORMANCE_SOURCE_CLOSURE_FAILED")
    review = json.loads((root / REVIEW_PATH).read_text(encoding="utf-8"))
    reviewed_commit = str(review.get("reviewed_source_commit", ""))
    if (
        review.get("identity") != IDENTITY
        or review.get("status") != "PASS_NO_P1_P2"
        or review.get("blocking_findings")
        or review.get("config_sha256") != config_hash
        or review.get("window_hash") != config["window_hash"]
        or review.get("pair_a_data_hash") != config["pair_a_data_hash"]
        or review.get("pair_b_data_hash") != config["pair_b_data_hash"]
        or set(review.get("file_sha256", {})) != REQUIRED_REVIEW_FILES
        or not reviewed_commit
    ):
        raise RuntimeError("M035_SOURCE_REVIEW_NOT_PASS")
    for relative, expected in review["file_sha256"].items():
        if _sha(root / relative) != expected:
            raise RuntimeError(f"M035_REVIEWED_SOURCE_CHANGED:{relative}")
    if (
        subprocess.call(["git", "merge-base", "--is-ancestor", reviewed_commit, head], cwd=root)
        != 0
        or subprocess.call(
            ["git", "diff", "--quiet", reviewed_commit, "--", *sorted(REQUIRED_REVIEW_FILES)],
            cwd=root,
        )
        != 0
    ):
        raise RuntimeError("M035_REVIEW_COMMIT_CLOSURE_FAILED")
    data = validate_dual_tape(root)
    if (
        data["status"] != "PASS"
        or data["window_hash"] != config["window_hash"]
        or data["pairs"]["USDCUSDT"]["pair_data_hash"] != config["pair_a_data_hash"]
        or data["pairs"]["FDUSDUSDT"]["pair_data_hash"] != config["pair_b_data_hash"]
    ):
        raise RuntimeError("M035_DUAL_TAPE_GATE_FAILED")
    return config, data, config_hash, head


def _gain(treatment: D, baseline: D) -> str:
    if baseline == 0:
        return "NOT_DEFINED"
    return format((treatment - baseline) / abs(baseline) * 100, "f")


def _comparison(single: dict[str, Any], parallel: dict[str, Any]) -> dict[str, Any]:
    return {
        "SCENARIO": single["SCENARIO"],
        "PARALLEL_CYCLE_GAIN_PCT": _gain(
            D(parallel["PHYSICAL_CYCLES"]), D(single["PHYSICAL_CYCLES"])
        ),
        "PARALLEL_PRODUCTIVITY_GAIN_PCT": _gain(
            D(parallel["NET_PNL_PER_CAPITAL_HOUR"]),
            D(single["NET_PNL_PER_CAPITAL_HOUR"]),
        ),
        "SINGLE_CYCLES": single["PHYSICAL_CYCLES"],
        "PARALLEL_CYCLES": parallel["PHYSICAL_CYCLES"],
        "SINGLE_MARKED_PNL_USD": single["MARKED_PNL_USD"],
        "PARALLEL_MARKED_PNL_USD": parallel["MARKED_PNL_USD"],
        "SINGLE_MARKED_RETURN_PCT": single["MARKED_RETURN_PCT"],
        "PARALLEL_MARKED_RETURN_PCT": parallel["MARKED_RETURN_PCT"],
    }


def _extract_artifacts(
    results: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    cycles: list[dict[str, Any]] = []
    capital: list[dict[str, Any]] = []
    pair_a: list[dict[str, Any]] = []
    pair_b: list[dict[str, Any]] = []
    for result in results:
        context = {
            "MODE": result["MODE"],
            "SCENARIO": result["SCENARIO"],
            "FEE_BPS_PER_LEG": result["FEE_BPS_PER_LEG"],
        }
        cycles.extend({**context, **row} for row in result.pop("CYCLES"))
        capital.extend({**context, **row} for row in result.pop("CAPITAL_TIMELINE"))
        result["CHECKPOINTS"] = [{**context, **row} for row in result["CHECKPOINTS"]]
        timelines = result.pop("PAIR_TIMELINES")
        for pair_id, destination in (("PAIR_A", pair_a), ("PAIR_B", pair_b)):
            for row in timelines.get(pair_id, []):
                destination.append({**context, "TYPE": "HOTLINE_CHANGE", **row})
            for row in result["CHECKPOINTS"]:
                destination.append(
                    {
                        **context,
                        "TYPE": "CHECKPOINT",
                        "TIME_US": row["TIME_US"],
                        "PAIR_ID": pair_id,
                        "CAPITAL": row[f"{pair_id}_CAPITAL"],
                        "CYCLES": row[f"{pair_id}_CYCLES"],
                    }
                )
    return cycles, capital, pair_a, pair_b


def _write_artifacts(root: Path, payload: dict[str, Any], results: list[dict[str, Any]]) -> None:
    cycles, capital, pair_a, pair_b = _extract_artifacts(results)
    _write_json(root / RESULT_PATH, payload)
    _write_csv(
        root / "reports/m035/M035_CYCLES.csv",
        sorted(cycles, key=lambda row: (row["MODE"], row["SCENARIO"], row["end_timestamp_us"])),
        [
            "MODE",
            "SCENARIO",
            "FEE_BPS_PER_LEG",
            "cycle_id",
            "cycle_type",
            "counted_physical_cycle",
            "pair_id",
            "route",
            "start_timestamp_us",
            "end_timestamp_us",
            "duration_seconds",
            "capital_used",
            "entry_price",
            "exit_price",
            "gross_proceeds",
            "gross_pnl",
            "cost_basis_ex_received_asset_fee",
            "ledger_cost_basis_including_received_asset_fee",
            "entry_fee_value",
            "return_fee_value",
            "fees",
            "execution_cost",
            "adverse_selection_cost",
            "net_pnl",
            "cost_attribution_residual",
            "return_pct",
            "residual_dust_quantity",
            "residual_dust_cost_basis",
        ],
    )
    capital_fields = [
        "MODE",
        "SCENARIO",
        "FEE_BPS_PER_LEG",
        "TIME_US",
        "FREE_USDT",
        "PAIR_A_RESERVED",
        "PAIR_A_INVENTORY",
        "PAIR_A_RETURN",
        "PAIR_A_DUST",
        "PAIR_B_RESERVED",
        "PAIR_B_INVENTORY",
        "PAIR_B_RETURN",
        "PAIR_B_DUST",
        "TOTAL_MARKED_EQUITY",
        "GLOBAL_CAPITAL_CONSERVATION_RESIDUAL",
    ]
    _write_csv(root / "reports/m035/M035_CAPITAL_TIMELINE.csv", capital, capital_fields)
    pair_fields = [
        "MODE",
        "SCENARIO",
        "FEE_BPS_PER_LEG",
        "TYPE",
        "TIME_US",
        "PAIR_ID",
        "SYMBOL",
        "CAPITAL",
        "CYCLES",
        "OLD_HOTLINE",
        "NEW_HOTLINE",
        "REASON",
        "AFFECTED_C2_ORDER_IDS",
    ]
    _write_csv(root / "reports/m035/M035_PAIR_A_TIMELINE.csv", pair_a, pair_fields)
    _write_csv(root / "reports/m035/M035_PAIR_B_TIMELINE.csv", pair_b, pair_fields)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    config_row, data, config_hash, head = _validate_pre_run(root)
    config = _config(config_row)
    config.validate()
    claim = {
        "identity": IDENTITY,
        "status": "STARTED",
        "started_at": datetime.now(UTC).isoformat(),
        "head": head,
        "config_sha256": config_hash,
        "window_hash": data["window_hash"],
        "execution_order": ["SINGLE_PAIR", "PARALLEL_TWO_PAIR"],
        "rerun_allowed": False,
    }
    try:
        _create_json_exclusive(root / CLAIM_PATH, claim)
    except FileExistsError:
        raise RuntimeError("M035_ONE_SHOT_CLAIM_ALREADY_EXISTS_NO_RERUN") from None
    completed_prefix: dict[str, Any] = {}
    try:
        single = run_mode(config, events=merged_events(root), fees=FEES, parallel=False)
        single_prefix_path = root / "data/m035/M035_SINGLE_PAIR_COMPLETED_PREFIX.json"
        _write_json(single_prefix_path, single)
        completed_prefix["SINGLE_PAIR"] = {
            "path": str(single_prefix_path.relative_to(root)).replace("\\", "/"),
            "sha256": _sha(single_prefix_path),
        }
        claim["single_pair_status"] = "COMPLETE"
        claim["single_pair_prefix_sha256"] = _sha(single_prefix_path)
        _write_json(root / CLAIM_PATH, claim)
        parallel = run_mode(config, events=merged_events(root), fees=FEES, parallel=True)
        claim["parallel_status"] = "COMPLETE"
        results = [*single, *parallel]
        comparisons = [
            _comparison(single_row, parallel_row)
            for single_row, parallel_row in zip(single, parallel, strict=True)
        ]
        payload = {
            "IDENTITY": IDENTITY,
            "STATUS": "COMPLETE",
            "CLASSIFICATION": "DEVELOPMENT_DIAGNOSTIC_BACKTEST_NOT_OOS_NOT_LIVE",
            "GENERATED_AT": datetime.now(UTC).isoformat(),
            "SOURCE_HEAD": head,
            "CONFIG_SHA256": config_hash,
            "DATA": {
                "START": config_row["start"],
                "END_EXCLUSIVE": config_row["end_exclusive"],
                "WINDOW_HASH": data["window_hash"],
                "PAIR_A_DATA_HASH": data["pairs"]["USDCUSDT"]["pair_data_hash"],
                "PAIR_B_DATA_HASH": data["pairs"]["FDUSDUSDT"]["pair_data_hash"],
                "L2_SOURCE": "TARDIS_BINANCE_NATIVE_DEPTH_AND_SNAPSHOT",
                "TRADE_SOURCE": "TARDIS_NATIVE_BOUND_TO_BINANCE_VISION_INDIVIDUAL_TRADES",
                "MIXED_SOURCE_DISCLOSED": True,
            },
            "INITIAL_BANK_USDT_PER_SCENARIO": "200",
            "SHARED_BANK_IN_PARALLEL": True,
            "SCENARIOS_EXECUTED": 10,
            "RESULTS": results,
            "PARALLEL_COMPARISONS": comparisons,
            "HISTORICAL_REFERENCE_NOT_CAUSAL_BASELINE": {
                "M026": {"PHYSICAL_CYCLES": 30, "DURATION_HOURS": 3},
                "M029": {"PHYSICAL_CYCLES": 98, "DURATION_HOURS": 24},
                "M030_RANDOM_EVAL_HOURS": {
                    "M029_PHYSICAL_CYCLES": 6,
                    "M030_PHYSICAL_CYCLES": 13,
                    "DURATION_HOURS": 3,
                },
            },
            "NO_RERUN": True,
        }
        _write_artifacts(root, payload, results)
        claim["status"] = "COMPLETE"
        claim["completed_at"] = datetime.now(UTC).isoformat()
        claim["result_sha256"] = _sha(root / RESULT_PATH)
        _write_json(root / CLAIM_PATH, claim)
        print(json.dumps({"status": "COMPLETE", "result": str(RESULT_PATH)}))
        return 0
    except BaseException as error:
        failure_evidence: dict[str, Any] = {"completed_prefix": completed_prefix}
        if isinstance(error, M035BacktestExecutionError):
            failure_evidence["failed_mode"] = error.mode
            failure_evidence["event_index"] = error.event_index
            failure_evidence["event"] = error.event
            failure_evidence["scenarios"] = error.evidence
        failure_path = root / "data/m035/M035_FAILED_PREFIX_EVIDENCE.json"
        _write_json(failure_path, failure_evidence)
        claim["status"] = "INVALIDATED_TECHNICAL"
        claim["failed_at"] = datetime.now(UTC).isoformat()
        claim["error_type"] = type(error).__name__
        claim["error"] = str(error)
        claim["traceback"] = traceback.format_exc()
        claim["failure_evidence_path"] = str(failure_path.relative_to(root)).replace("\\", "/")
        claim["failure_evidence_sha256"] = _sha(failure_path)
        _write_json(root / CLAIM_PATH, claim)
        raise


if __name__ == "__main__":
    sys.exit(main())
