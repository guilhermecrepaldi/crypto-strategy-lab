"""Run the single authorized five-scenario M034 development backtest campaign."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import subprocess
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from crypto_strategy_lab.microstructure.m034_zero_loss_backtest import (
    BacktestExecutionError,
    ZeroLossConfig,
    run_scenarios,
)
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from scripts import run_triangular_pre_aged_queue as input_authority
from scripts.run_high_uptime_recovery import campaign_writer_lock, lf_sha

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_V1"
CONFIG = Path("reports/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_CONFIG.json")
REVIEW = Path("reports/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_SOURCE_REVIEW.json")
PROTOCOL = Path("docs/research/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H.md")
RESULT = Path("reports/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H.json")
CYCLES = Path("reports/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_CYCLES.csv")
EQUITY = Path("reports/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_EQUITY.csv")
NEGATIVE = Path("reports/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_NEGATIVE_CYCLES.json")
OUTPUT = Path("artifacts/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_V1")
CLAIM = Path("data/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_V1.claim.json")
M026_RESULT = Path("reports/usdcusdt/M026-3h-result.json")
SOURCE_PATHS = (
    Path("src/crypto_strategy_lab/microstructure/m034_zero_loss_backtest.py"),
    Path("src/crypto_strategy_lab/microstructure/economic_eligibility.py"),
    Path("src/crypto_strategy_lab/microstructure/multi_stable_ledger.py"),
    Path("src/crypto_strategy_lab/microstructure/multi_stable_queue.py"),
    Path("src/crypto_strategy_lab/microstructure/multi_stable_routing.py"),
    Path("src/crypto_strategy_lab/microstructure/adaptive_multi_stable_manager.py"),
    Path("src/crypto_strategy_lab/microstructure/multi_venue_models.py"),
    Path("src/crypto_strategy_lab/microstructure/tardis_l2.py"),
    Path("scripts/run_m034_zero_loss_backtest.py"),
    Path("tests/test_m034_zero_loss_backtest.py"),
)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _assert_unused() -> None:
    existing = [path for path in (CLAIM, OUTPUT, RESULT, CYCLES, EQUITY, NEGATIVE) if path.exists()]
    if existing:
        raise ValueError(f"M034_ZERO_LOSS_ONE_SHOT_ALREADY_CONSUMED:{existing}")


def _assert_published_head() -> str:
    if Path.cwd().resolve() != ROOT.resolve():
        raise ValueError("CANONICAL_REPOSITORY_CWD_REQUIRED")
    if _git("status", "--porcelain"):
        raise ValueError("PRE_EXECUTION_WORKTREE_NOT_CLEAN")
    if _git("branch", "--show-current") != "main":
        raise ValueError("CANONICAL_MAIN_REQUIRED")
    head = _git("rev-parse", "HEAD")
    if _git("rev-parse", "origin/main") != head:
        raise ValueError("M034_ZERO_LOSS_REQUIRES_PUBLISHED_HEAD")
    return head


def _validate_config(payload: dict[str, Any]) -> ZeroLossConfig:
    expected_hash = payload.get("configuration_hash")
    unhashed = {key: value for key, value in payload.items() if key != "configuration_hash"}
    if not expected_hash or _canonical_hash(unhashed) != expected_hash:
        raise ValueError("M034_ZERO_LOSS_CONFIGURATION_HASH_MISMATCH")
    config = ZeroLossConfig.from_mapping(payload)
    if (
        payload.get("scientific_status") != "DEVELOPMENT_DIAGNOSTIC_BACKTEST"
        or payload.get("dataset_role") != "CALIBRATION"
        or payload.get("strategy_pass") is not False
        or payload.get("kraken_policy") != "RETIRED_DISABLED"
    ):
        raise ValueError("M034_ZERO_LOSS_CONFIG_SCOPE_MISMATCH")
    return config


def _validate_source_review(payload: dict[str, Any]) -> str:
    source_sha = str(payload.get("source_sha", ""))
    if (
        payload.get("verdict") != "PASS_FOR_DEVELOPMENT_DIAGNOSTIC_BACKTEST"
        or payload.get("reviewer_model") != "gpt-6-astra"
        or payload.get("identity") != IDENTITY
        or not source_sha
    ):
        raise ValueError("M034_ZERO_LOSS_SOURCE_REVIEW_NOT_PASS")
    subprocess.check_call(["git", "merge-base", "--is-ancestor", source_sha, "HEAD"], cwd=ROOT)
    reviewed = payload.get("source_sha256_lf", {})
    if set(reviewed) != {path.as_posix() for path in SOURCE_PATHS}:
        raise ValueError("M034_ZERO_LOSS_SOURCE_REVIEW_CLOSURE_MISMATCH")
    for path in SOURCE_PATHS:
        expected = reviewed[path.as_posix()]
        if lf_sha(path) != expected:
            raise ValueError(f"M034_ZERO_LOSS_REVIEWED_SOURCE_CHANGED:{path}")
        published = subprocess.check_output(
            ["git", "show", f"{source_sha}:{path.as_posix()}"], cwd=ROOT
        ).replace(b"\r\n", b"\n")
        if hashlib.sha256(published).hexdigest() != expected:
            raise ValueError(f"M034_ZERO_LOSS_REVIEW_SHA_NOT_SOURCE_BOUND:{path}")
    return source_sha


def preflight() -> tuple[str, str, ZeroLossConfig, dict[str, Any]]:
    _assert_unused()
    head = _assert_published_head()
    config_payload = json.loads(CONFIG.read_bytes())
    review_payload = json.loads(REVIEW.read_bytes())
    config = _validate_config(config_payload)
    source_sha = _validate_source_review(review_payload)
    for path in (CONFIG, REVIEW, PROTOCOL, M026_RESULT):
        if not path.is_file():
            raise ValueError(f"M034_ZERO_LOSS_REQUIRED_ARTIFACT_MISSING:{path}")
    parent = json.loads(M026_RESULT.read_bytes())
    if (
        parent.get("METRICS", {}).get("PHYSICAL_CYCLES") != 30
        or parent.get("METRICS", {}).get("SLOT_EQUIVALENT_CYCLES") != 90
        or parent.get("AUDIT", {}).get("status")
        != "PASS_M026_INDEPENDENT_LEDGER_AND_TERMINAL_AUDIT"
    ):
        raise ValueError("M034_ZERO_LOSS_M026_BASELINE_CHANGED")
    return head, source_sha, config, config_payload


def _claim(head: str, source_sha: str, config_hash: str) -> None:
    CLAIM.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "identity": IDENTITY,
        "claimed_at": datetime.now(UTC).isoformat(),
        "published_head": head,
        "source_sha": source_sha,
        "configuration_hash": config_hash,
        "authorized_scenario_count": 5,
        "rerun_allowed": False,
    }
    with CLAIM.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        stream.flush()
        os.fsync(stream.fileno())


def _analysis(results: list[dict[str, Any]], cycles: list[dict[str, Any]]) -> dict[str, Any]:
    profitable = [
        row for row in results if D(row["FINAL_MARKED_EQUITY_USD"]) > D(row["INITIAL_BANK_USD"])
    ]
    nonprofitable = [
        row for row in results if D(row["FINAL_MARKED_EQUITY_USD"]) <= D(row["INITIAL_BANK_USD"])
    ]
    positive_zero_loss = [
        row
        for row in results
        if row["ZERO_LOSS_ECONOMIC_PASS"]
        and D(row["FINAL_MARKED_EQUITY_USD"]) > D(row["INITIAL_BANK_USD"])
    ]
    best = max(positive_zero_loss, key=lambda row: D(row["FINAL_MARKED_EQUITY_USD"]), default=None)
    best_cycles = [row for row in cycles if best and row["scenario"] == best["SCENARIO"]]
    mean_net = (
        sum((D(row["net_pnl"]) for row in best_cycles), D(0)) / D(len(best_cycles))
        if best_cycles
        else None
    )
    targets = {}
    for label, pct in (("0.1%", D("0.001")), ("0.5%", D("0.005")), ("1%", D("0.01"))):
        targets[label] = (
            None if mean_net is None or mean_net <= 0 else math.ceil(D(200) * pct / mean_net)
        )
    max_profitable = max((D(row["FEE_BPS_PER_LEG"]) for row in profitable), default=None)
    first_nonprofitable = min((D(row["FEE_BPS_PER_LEG"]) for row in nonprofitable), default=None)
    if max_profitable is None:
        break_even = "NOT_IDENTIFIABLE_NO_PROFITABLE_GRID_POINT"
    elif first_nonprofitable is None:
        break_even = f">{max_profitable} bps/leg"
    else:
        break_even = f">{max_profitable} and <={first_nonprofitable} bps/leg"
    return {
        "APPROXIMATE_BREAK_EVEN_FEE": break_even,
        "MAX_PROFITABLE_GRID_FEE_BPS_PER_LEG": (
            None if max_profitable is None else str(max_profitable)
        ),
        "FIRST_NONPROFITABLE_GRID_FEE_BPS_PER_LEG": (
            None if first_nonprofitable is None else str(first_nonprofitable)
        ),
        "GROSS_EDGE_MINIMUM_FORMULA_BPS": "2*maker_fee_bps_per_leg + 5",
        "BEST_ZERO_LOSS_SCENARIO": None if best is None else best["SCENARIO"],
        "MEAN_NET_PNL_PER_CYCLE_BEST_SCENARIO": None if mean_net is None else str(mean_net),
        "CYCLES_NEEDED_DESCRIPTIVE": targets,
        "TARGETS_ARE_NOT_CLAIMED_ACHIEVABLE": True,
    }


def execute(
    head: str,
    source_sha: str,
    config: ZeroLossConfig,
    config_payload: dict[str, Any],
) -> dict[str, Any]:
    manifest = json.loads(input_authority.MANIFEST.read_bytes())
    validation = json.loads(input_authority.VALIDATION_REPORT.read_bytes())
    profile, canonical, slices, evidence = input_authority.bounded_inputs(manifest, validation)
    if (
        tuple(item["offset"] for item in slices) != tuple(range(0, 180, 10))
        or len(canonical) != 29_538
        or profile.latency_us != config.activation_latency_us
        or profile.cancel_latency_us != config.cancel_ack_latency_us
    ):
        raise ValueError("M034_ZERO_LOSS_INPUT_OR_LATENCY_BINDING_CHANGED")
    _claim(head, source_sha, config_payload["configuration_hash"])
    OUTPUT.mkdir(parents=True, exist_ok=False)
    evidence: list[dict[str, Any]] = []
    try:
        results, cycles, checkpoints, evidence = run_scenarios(
            config, input_authority.bounded_native_events(slices)
        )
        event_counts = {
            (row["EVENT_COUNT"], row["BOOK_COUNT"], row["TRADE_COUNT"]) for row in results
        }
        if event_counts != {(100_760, 71_222, 29_538)}:
            raise ValueError(f"M034_ZERO_LOSS_EVENT_COUNT_MISMATCH:{event_counts}")
        if any(row["ACCOUNTING_IDENTITY_RESIDUAL"] != "0" for row in results):
            raise ValueError("M034_ZERO_LOSS_ACCOUNTING_AUDIT_FAILED")
        cycles.sort(key=lambda row: (row["start_timestamp_us"], row["scenario"], row["cycle_id"]))
        negative = [row for row in cycles if D(row["net_pnl"]) < 0]
        analysis = _analysis(results, cycles)
        comparisons = {
            row["SCENARIO"]: {
                "PRIOR_MODEL_PHYSICAL_CYCLES": 30,
                "M034_PHYSICAL_CYCLES": row["PHYSICAL_CYCLES"],
                "DELTA_CYCLES": row["PHYSICAL_CYCLES"] - 30,
                "DELTA_CYCLES_PCT": str((D(row["PHYSICAL_CYCLES"]) / D(30) - D(1)) * D(100)),
                "PRIOR_CYCLES_PER_HOUR": "10",
                "M034_CYCLES_PER_HOUR": row["CYCLES_PER_HOUR"],
                "NET_PNL_PER_INITIAL_CAPITAL_HOUR": str(D(row["NET_REALIZED_PNL_USD"]) / D(600)),
                "MARKED_PNL_PER_INITIAL_CAPITAL_HOUR": row["MARKED_PNL_PER_INITIAL_CAPITAL_HOUR"],
            }
            for row in results
        }
        result = {
            "IDENTITY": IDENTITY,
            "RUN_STATUS": "COMPLETE",
            "SCIENTIFIC_STATUS": "DEVELOPMENT_DIAGNOSTIC_BACKTEST",
            "DATASET_ROLE": "CALIBRATION_NOT_OOS",
            "STRATEGY_PASS": False,
            "LIVE_PROFITABILITY_CLAIM": False,
            "VENUE": "BINANCE",
            "KRAKEN_POLICY": "RETIRED_DISABLED",
            "START": "2025-01-01T00:00:00Z",
            "END_EXCLUSIVE": "2025-01-01T03:00:00Z",
            "DURATION_HOURS": "3",
            "PUBLISHED_HEAD": head,
            "SOURCE_SHA": source_sha,
            "CONFIGURATION_HASH": config_payload["configuration_hash"],
            "THRESHOLD_CONFIG_HASH": config.threshold_registry().config_hash,
            "INPUT_EVIDENCE": evidence,
            "SAME_TAPE_ALL_SCENARIOS": True,
            "ECONOMIC_CAMPAIGN_RUNS": 1,
            "SCENARIO_RUNS_WITHIN_FROZEN_GRID": 5,
            "SCENARIOS": results,
            "PRIOR_MODEL": {
                "MODEL": "M026",
                "PHYSICAL_CYCLES": 30,
                "SLOT_EQUIVALENT_CYCLES": 90,
                "CYCLES_PER_HOUR": "10",
                "COMPARISON_LIMITATION": (
                    "M026 began with USDT+USDC, used geometry 15 with 3/2/1 columns, "
                    "and virtualized minimum notional; comparison is descriptive."
                ),
            },
            "COMPARISON": comparisons,
            "BREAK_EVEN_ANALYSIS": analysis,
            "NEGATIVE_CYCLE_COUNT": len(negative),
            "CYCLE_ARTIFACT": CYCLES.as_posix(),
            "EQUITY_ARTIFACT": EQUITY.as_posix(),
            "NEGATIVE_CYCLE_ARTIFACT": NEGATIVE.as_posix(),
            "PHYSICAL_EVIDENCE_DIRECTORY": OUTPUT.as_posix(),
        }
        _write_csv(
            CYCLES,
            cycles,
            [
                "scenario",
                "cycle_id",
                "slot_id",
                "capital_origin",
                "route",
                "start_timestamp_us",
                "end_timestamp_us",
                "duration_seconds",
                "capital_used",
                "cost_basis",
                "entry_price",
                "exit_price",
                "gross_pnl",
                "fees",
                "execution_cost",
                "adverse_selection_cost",
                "net_pnl",
                "return_pct",
                "rank",
                "column",
            ],
        )
        _write_csv(
            EQUITY,
            checkpoints,
            [
                "SCENARIO",
                "TIME_US",
                "REALIZED_EQUITY",
                "MARKED_EQUITY",
                "PHYSICAL_CYCLES",
                "FREE_CAPITAL",
                "LOCKED_CAPITAL",
                "RESIDUAL_INVENTORY",
            ],
        )
        write_json(NEGATIVE, {"identity": IDENTITY, "negative_cycles": negative})
        write_json(RESULT, result)
        write_json(OUTPUT / "result.json", result)
        evidence_paths = []
        for snapshot in evidence:
            path = OUTPUT / f"physical-evidence-{snapshot['scenario']}.json"
            write_json(path, snapshot)
            evidence_paths.append(path)
        manifest_payload = {
            "identity": IDENTITY,
            "claim_sha256": file_sha(CLAIM),
            "files": {
                path.as_posix(): file_sha(path)
                for path in (RESULT, CYCLES, EQUITY, NEGATIVE, CONFIG, REVIEW, PROTOCOL)
            },
            "event_counts": list(next(iter(event_counts))),
            "same_tape_all_scenarios": True,
            "physical_evidence": {path.as_posix(): file_sha(path) for path in evidence_paths},
        }
        write_json(OUTPUT / "manifest.json", manifest_payload)
        return result
    except BaseException as exc:
        prefix_evidence = exc.evidence if isinstance(exc, BacktestExecutionError) else evidence
        if prefix_evidence:
            write_json(OUTPUT / "failure-prefix-evidence.json", prefix_evidence)
        write_json(
            OUTPUT / "failure.json",
            {
                "identity": IDENTITY,
                "run_status": "INCOMPLETE_PRESERVED_NO_RERUN",
                "exception_type": (
                    exc.cause_type
                    if isinstance(exc, BacktestExecutionError)
                    else type(exc).__name__
                ),
                "error": str(exc),
                "claim_sha256": file_sha(CLAIM),
                "prefix_evidence_preserved": bool(prefix_evidence),
            },
        )
        raise


def run() -> dict[str, Any]:
    head, source_sha, config, payload = preflight()
    with campaign_writer_lock():
        if _assert_published_head() != head:
            raise ValueError("M034_ZERO_LOSS_HEAD_CHANGED_DURING_PREFLIGHT")
        return execute(head, source_sha, config, payload)


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
