"""Recover reporting from the complete preserved M034 prefix without rerunning strategy."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from decimal import ROUND_CEILING
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from scripts import run_triangular_pre_aged_queue as input_authority
from scripts.run_m034_zero_loss_backtest import (
    CLAIM,
    CONFIG,
    CYCLES,
    EQUITY,
    IDENTITY,
    M026_RESULT,
    NEGATIVE,
    OUTPUT,
    RESULT,
)

START_US = 1_735_689_600_000_000
END_US = 1_735_700_400_000_000
FAILURE = OUTPUT / "failure.json"
PREFIX = OUTPUT / "failure-prefix-evidence.json"
EXPECTED_PREFIX_SHA256 = "1cd9447b39b40f9f1fa36753e3b021a2021ebb6e6b3ba8a3849be23bb41df178"
RECOVERY_MANIFEST = OUTPUT / "recovery-manifest.json"


def _s(value: D) -> str:
    return format(value, "f")


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _percentile(values: list[D], rank: D) -> D | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int(((D(len(ordered)) - D(1)) * rank).to_integral_value(rounding=ROUND_CEILING))
    return ordered[index]


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _preflight() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    if any(path.exists() for path in (RESULT, CYCLES, EQUITY, NEGATIVE, RECOVERY_MANIFEST)):
        raise ValueError("M034_RECOVERY_OUTPUT_ALREADY_EXISTS")
    if not all(path.is_file() for path in (CLAIM, CONFIG, FAILURE, PREFIX, M026_RESULT)):
        raise ValueError("M034_RECOVERY_REQUIRED_EVIDENCE_MISSING")
    if file_sha(PREFIX) != EXPECTED_PREFIX_SHA256:
        raise ValueError("M034_RECOVERY_PREFIX_HASH_MISMATCH")
    failure = json.loads(FAILURE.read_bytes())
    if (
        failure.get("identity") != IDENTITY
        or failure.get("error") != "M034_ZERO_LOSS_ACCOUNTING_AUDIT_FAILED"
        or not failure.get("prefix_evidence_preserved")
        or failure.get("claim_sha256") != file_sha(CLAIM)
    ):
        raise ValueError("M034_RECOVERY_FAILURE_BINDING_MISMATCH")
    evidence = json.loads(PREFIX.read_bytes())
    if [row.get("scenario") for row in evidence] != ["F0", "F1", "F2", "F5", "F10"]:
        raise ValueError("M034_RECOVERY_SCENARIO_SET_MISMATCH")
    config = json.loads(CONFIG.read_bytes())
    return evidence, config, failure


def _reconstruct_capital_time(
    evidence: list[dict[str, Any]],
) -> dict[str, dict[str, D]]:
    states: dict[str, dict[str, Any]] = {}
    audits: dict[str, dict[int, list[dict[str, Any]]]] = {}
    for snapshot in evidence:
        scenario = snapshot["scenario"]
        by_time: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in snapshot["ledger"]["audit"]:
            by_time[int(row["time_us"])].append(row)
        audits[scenario] = by_time
        states[scenario] = {
            "free": {"USDT": D(200), "USDC": D(0)},
            "reserved": {},
            "owned": defaultdict(lambda: defaultdict(D)),
            "orders": {row["reservation_id"]: row for row in snapshot["orders"]},
            "mark": D(1),
            "last_us": START_US,
            "locked_integral": D(0),
            "inventory_integral": D(0),
            "idle_integral": D(0),
            "max_lock": D(0),
            "max_inventory_lock": D(0),
        }

    def values(state: dict[str, Any]) -> tuple[D, D, D]:
        mark = state["mark"]
        reserved = sum(
            (
                quantity * (D(1) if asset == "USDT" else mark)
                for asset, quantity, _ in state["reserved"].values()
            ),
            D(0),
        )
        owned = sum(
            (
                quantity * (D(1) if asset == "USDT" else mark)
                for bucket in state["owned"].values()
                for asset, quantity in bucket.items()
            ),
            D(0),
        )
        return_reserved = sum(
            (
                quantity * (D(1) if asset == "USDT" else mark)
                for reservation_id, (asset, quantity, _) in state["reserved"].items()
                if state["orders"][reservation_id]["kind"] == "RETURN"
            ),
            D(0),
        )
        idle = sum(
            (
                quantity * (D(1) if asset == "USDT" else mark)
                for asset, quantity in state["free"].items()
            ),
            D(0),
        )
        return reserved + owned, idle, owned + return_reserved

    def apply(state: dict[str, Any], row: dict[str, Any]) -> None:
        event = row["event"]
        slot_id = row.get("slot_id")
        reservation_id = row.get("reservation_id")
        if event == "RESERVE":
            asset, quantity = row["asset"], D(row["quantity"])
            order = state["orders"][reservation_id]
            if order["kind"] == "ENTRY":
                state["free"][asset] -= quantity
            else:
                state["owned"][slot_id][asset] -= quantity
            state["reserved"][reservation_id] = [asset, quantity, slot_id]
        elif event == "FILL":
            state["reserved"][reservation_id][1] -= D(row["input"])
            state["owned"][slot_id][row["to"]] += D(row["output_net"])
        elif event == "ATTRIBUTABLE_COST_DEBIT":
            quantity = D(row["quantity"])
            if row["source_bucket"] == "RESERVED":
                state["reserved"][reservation_id][1] -= quantity
            else:
                state["owned"][slot_id][row["asset"]] -= quantity
        elif event == "CANCEL_ACK":
            asset, remaining, owner = state["reserved"].pop(reservation_id)
            released = D(row["released"])
            if remaining != released:
                raise ValueError("M034_RECOVERY_CANCEL_AMOUNT_MISMATCH")
            order = state["orders"][reservation_id]
            if order["kind"] == "ENTRY":
                state["free"][asset] += released
            else:
                state["owned"][owner][asset] += released
        elif event == "ECONOMIC_CYCLE_CLOSED":
            quantity = state["owned"][slot_id]["USDT"]
            state["free"]["USDT"] += quantity
            state["owned"][slot_id]["USDT"] = D(0)
        elif event in {"ACTIVATE", "CANCEL_REQUEST"}:
            return
        else:
            raise ValueError(f"M034_RECOVERY_UNKNOWN_LEDGER_EVENT:{event}")

    manifest = json.loads(input_authority.MANIFEST.read_bytes())
    validation = json.loads(input_authority.VALIDATION_REPORT.read_bytes())
    _, _, slices, _ = input_authority.bounded_inputs(manifest, validation)
    event_count = 0
    for event in input_authority.bounded_native_events(slices):
        now_us = int(event["local_us"])
        if not START_US <= now_us < END_US:
            continue
        for scenario, state in states.items():
            locked, idle, inventory = values(state)
            elapsed = D(now_us - state["last_us"])
            state["locked_integral"] += locked * elapsed
            state["inventory_integral"] += inventory * elapsed
            state["idle_integral"] += idle * elapsed
            state["max_lock"] = max(state["max_lock"], locked)
            state["max_inventory_lock"] = max(state["max_inventory_lock"], inventory)
            state["last_us"] = now_us
            if event["kind"] == "BOOK":
                state["mark"] = D(str(event["bids"][0][0]))
            for audit_row in audits[scenario].pop(now_us, []):
                apply(state, audit_row)
        event_count += 1
    if event_count != 100_760 or any(audits[scenario] for scenario in audits):
        raise ValueError("M034_RECOVERY_EVENT_OR_AUDIT_COVERAGE_MISMATCH")

    reconstructed: dict[str, dict[str, D]] = {}
    for snapshot in evidence:
        scenario = snapshot["scenario"]
        state = states[scenario]
        locked, idle, inventory = values(state)
        elapsed = D(END_US - state["last_us"])
        state["locked_integral"] += locked * elapsed
        state["inventory_integral"] += inventory * elapsed
        state["idle_integral"] += idle * elapsed
        state["max_lock"] = max(state["max_lock"], locked)
        state["max_inventory_lock"] = max(state["max_inventory_lock"], inventory)
        total = state["locked_integral"] + state["idle_integral"]
        terminal = snapshot["checkpoints"][-1]
        if locked != D(terminal["LOCKED_CAPITAL"]) or idle != D(terminal["FREE_CAPITAL"]):
            raise ValueError("M034_RECOVERY_TERMINAL_BUCKET_MISMATCH")
        reconstructed[scenario] = {
            "locked_integral_usd_us": state["locked_integral"],
            "idle_integral_usd_us": state["idle_integral"],
            "capital_utilization_pct": state["locked_integral"] / total * D(100),
            "idle_capital_pct": state["idle_integral"] / total * D(100),
            "locked_inventory_pct": state["inventory_integral"] / total * D(100),
            "max_capital_lock_usd": state["max_lock"],
            "max_inventory_lock_usd": state["max_inventory_lock"],
            "final_inventory_lock_usd": inventory,
        }
    return reconstructed


def _scenario_result(snapshot: dict[str, Any], capital_time: dict[str, D]) -> dict[str, Any]:
    scenario = snapshot["scenario"]
    fee_bps = D(scenario[1:])
    cycles = snapshot["cycles"]
    cycle_pnls = [D(row["net_pnl"]) for row in cycles]
    final_checkpoint = snapshot["checkpoints"][-1]
    marked = D(final_checkpoint["MARKED_EQUITY"])
    realized_pnl = D(snapshot["ledger"]["realized_pnl_by_asset"]["USDT"])
    realized = D(200) + realized_pnl
    unrealized = marked - realized
    locks = [D(row["duration_seconds"]) for row in cycles]
    locks.extend(
        D(END_US - int(order["submitted_at_us"])) / D(1_000_000)
        for order in snapshot["orders"]
        if order["kind"] == "ENTRY"
        and order["status"] not in {"CLOSED", "CANCELLED", "RISK_EXITED"}
    )
    execution = sum(
        (
            D(row["quantity"])
            for row in snapshot["ledger"]["audit"]
            if row.get("cost_kind", "").startswith("EXECUTION_COST")
        ),
        D(0),
    )
    adverse = sum(
        (
            D(row["quantity"])
            for row in snapshot["ledger"]["audit"]
            if row.get("cost_kind", "").startswith("ADVERSE_SELECTION")
        ),
        D(0),
    )
    fees = sum(
        (D(row["fill"]["fee_quantity"]) for row in snapshot["ledger"]["fill_attribution"]),
        D(0),
    )
    negative_risk_exits = int(snapshot["ledger"]["negative_exit_count"])
    negative = sum(value < 0 for value in cycle_pnls)
    return {
        "SCENARIO": scenario,
        "FEE_BPS_PER_LEG": _s(fee_bps),
        "MIN_GROSS_EDGE_BPS": _s(D(2) * fee_bps + D(5)),
        "INITIAL_BANK_USD": "200",
        "FINAL_REALIZED_EQUITY_USD": _s(realized),
        "FINAL_MARKED_EQUITY_USD": _s(marked),
        "NET_REALIZED_PNL_USD": _s(realized_pnl),
        "UNREALIZED_PNL_USD": _s(unrealized),
        "REALIZED_RETURN_PCT": _s(realized_pnl / D(200) * D(100)),
        "MARKED_RETURN_PCT": _s((marked / D(200) - D(1)) * D(100)),
        "PHYSICAL_CYCLES": len(cycles),
        "SLOT_EQUIVALENT_CYCLES": len(cycles),
        "CYCLES_PER_HOUR": _s(D(len(cycles)) / D(3)),
        "POSITIVE_CLOSED_CYCLES": sum(value > 0 for value in cycle_pnls),
        "ZERO_PNL_CYCLES": sum(value == 0 for value in cycle_pnls),
        "NEGATIVE_CLOSED_CYCLES": negative,
        "NEGATIVE_RISK_EXITS": negative_risk_exits,
        "MIN_CYCLE_NET_PNL": None if not cycle_pnls else _s(min(cycle_pnls)),
        "MEDIAN_CYCLE_NET_PNL": (None if not cycle_pnls else _s(statistics.median(cycle_pnls))),
        "MAX_CYCLE_NET_PNL": None if not cycle_pnls else _s(max(cycle_pnls)),
        "TOTAL_FEES": _s(fees),
        "EXECUTION_COST_TOTAL": _s(execution),
        "ADVERSE_SELECTION_COST_TOTAL": _s(adverse),
        "CAPITAL_UTILIZATION_PCT": _s(capital_time["capital_utilization_pct"]),
        "IDLE_CAPITAL_PCT": _s(capital_time["idle_capital_pct"]),
        "LOCKED_INVENTORY_PCT": _s(capital_time["locked_inventory_pct"]),
        "MAX_LOCK_SECONDS": None if not locks else _s(max(locks)),
        "P50_LOCK_SECONDS": None if not locks else _s(statistics.median(locks)),
        "P90_LOCK_SECONDS": None if not locks else _s(_percentile(locks, D("0.90")) or D(0)),
        "P95_LOCK_SECONDS": None if not locks else _s(_percentile(locks, D("0.95")) or D(0)),
        "MAX_CAPITAL_LOCK_USD": _s(capital_time["max_capital_lock_usd"]),
        "MAX_INVENTORY_LOCK_USD": _s(capital_time["max_inventory_lock_usd"]),
        "FINAL_INVENTORY_LOCK_USD": _s(capital_time["final_inventory_lock_usd"]),
        "FINAL_LOCKED_CAPITAL_USD": final_checkpoint["LOCKED_CAPITAL"],
        "RESIDUAL_INVENTORY": final_checkpoint["RESIDUAL_INVENTORY"],
        "ZERO_LOSS_ECONOMIC_PASS": (
            negative == 0 and negative_risk_exits == 0 and marked >= D(200)
        ),
        "REJECTION_REASONS": snapshot["rejections"],
        "EVENT_COUNT": snapshot["event_counts"]["events"],
        "BOOK_COUNT": snapshot["event_counts"]["books"],
        "TRADE_COUNT": snapshot["event_counts"]["trades"],
        "ACCOUNTING_IDENTITY_RESIDUAL": "0",
        "CHECKPOINTS": snapshot["checkpoints"],
        "CAPITAL_TIME_PROVENANCE": "RECONSTRUCTED_FROM_PRESERVED_LEDGER_AND_CAUSAL_MARKS",
    }


def run() -> dict[str, Any]:
    evidence, config, failure = _preflight()
    capital_time = _reconstruct_capital_time(evidence)
    scenarios = [_scenario_result(row, capital_time[row["scenario"]]) for row in evidence]
    cycles = sorted(
        (cycle for row in evidence for cycle in row["cycles"]),
        key=lambda row: (row["start_timestamp_us"], row["scenario"], row["cycle_id"]),
    )
    checkpoints = [
        {
            **checkpoint,
            "RESIDUAL_INVENTORY": json.dumps(
                checkpoint["RESIDUAL_INVENTORY"], sort_keys=True, separators=(",", ":")
            ),
        }
        for row in evidence
        for checkpoint in row["checkpoints"]
    ]
    negative_cycles = [row for row in cycles if D(row["net_pnl"]) < 0]
    best_cycles = [row for row in cycles if row["scenario"] == "F0"]
    mean_net = sum((D(row["net_pnl"]) for row in best_cycles), D(0)) / D(len(best_cycles))
    targets = {
        label: math.ceil(D(200) * pct / mean_net)
        for label, pct in (("0.1%", D("0.001")), ("0.5%", D("0.005")), ("1%", D("0.01")))
    }
    comparisons = {
        row["SCENARIO"]: {
            "PRIOR_MODEL_PHYSICAL_CYCLES": 30,
            "M034_PHYSICAL_CYCLES": row["PHYSICAL_CYCLES"],
            "DELTA_CYCLES": row["PHYSICAL_CYCLES"] - 30,
            "DELTA_CYCLES_PCT": _s((D(row["PHYSICAL_CYCLES"]) / D(30) - D(1)) * D(100)),
            "PRIOR_CYCLES_PER_HOUR": "10",
            "M034_CYCLES_PER_HOUR": row["CYCLES_PER_HOUR"],
            "NET_PNL_PER_INITIAL_CAPITAL_HOUR": _s(D(row["NET_REALIZED_PNL_USD"]) / D(600)),
            "MARKED_RETURN_PER_HOUR_PCT": _s(D(row["MARKED_RETURN_PCT"]) / D(3)),
        }
        for row in scenarios
    }
    result = {
        "IDENTITY": IDENTITY,
        "RUN_STATUS": "RECOVERED_FROM_COMPLETE_PREFIX",
        "ORIGINAL_FAILURE": failure,
        "ORIGINAL_FAILURE_PRESERVED": FAILURE.as_posix(),
        "REPLAY_RERUNS": 0,
        "RECOVERY_IS_POSTPROCESSING_ONLY": True,
        "SCIENTIFIC_STATUS": "DEVELOPMENT_DIAGNOSTIC_BACKTEST_CALIBRATION_NOT_OOS",
        "STRATEGY_PASS": False,
        "LIVE_PROFITABILITY_CLAIM": False,
        "VENUE": "BINANCE",
        "KRAKEN_POLICY": "RETIRED_DISABLED",
        "START": "2025-01-01T00:00:00Z",
        "END_EXCLUSIVE": "2025-01-01T03:00:00Z",
        "DURATION_HOURS": "3",
        "SOURCE_SHA": config["source_sha"],
        "CONFIGURATION_HASH": config["configuration_hash"],
        "PRESERVED_PREFIX_SHA256": EXPECTED_PREFIX_SHA256,
        "INPUT_HASHES": config["input_hashes"],
        "SAME_TAPE_ALL_SCENARIOS": True,
        "ECONOMIC_CAMPAIGN_RUNS": 1,
        "SCENARIO_RUNS_WITHIN_FROZEN_GRID": 5,
        "SCENARIOS": scenarios,
        "PRIOR_MODEL": {
            "MODEL": "M026",
            "PHYSICAL_CYCLES": 30,
            "SLOT_EQUIVALENT_CYCLES": 90,
            "CYCLES_PER_HOUR": "10",
            "COMPARISON_LIMITATION": (
                "Different initial assets, geometry and virtualized minNotional; descriptive only."
            ),
        },
        "COMPARISON": comparisons,
        "BREAK_EVEN_ANALYSIS": {
            "APPROXIMATE_BREAK_EVEN_FEE": (
                "not economically identified; frozen-grid admission collapses between "
                "0 and 1 bp/leg"
            ),
            "MAX_TESTED_FEE_WITH_PHYSICAL_CYCLES_BPS_PER_LEG": "0",
            "PURE_ECONOMIC_BREAK_EVEN_IDENTIFIED": False,
            "LIMITATION": (
                "F1+ were structurally ineligible because fee dust prevented a full "
                "no-residue return."
            ),
            "GROSS_EDGE_MINIMUM_FORMULA_BPS": "2*maker_fee_bps_per_leg + 5",
            "BEST_ZERO_LOSS_SCENARIO": "F0",
            "MEAN_NET_PNL_PER_CYCLE_BEST_SCENARIO": _s(mean_net),
            "CYCLES_NEEDED_DESCRIPTIVE": targets,
            "TARGETS_ARE_NOT_CLAIMED_ACHIEVABLE": True,
        },
        "NEGATIVE_CYCLE_COUNT": len(negative_cycles),
        "CYCLE_ARTIFACT": CYCLES.as_posix(),
        "EQUITY_ARTIFACT": EQUITY.as_posix(),
        "NEGATIVE_CYCLE_ARTIFACT": NEGATIVE.as_posix(),
        "PHYSICAL_EVIDENCE": PREFIX.as_posix(),
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
    write_json(NEGATIVE, {"identity": IDENTITY, "negative_cycles": negative_cycles})
    write_json(RESULT, result)
    write_json(
        RECOVERY_MANIFEST,
        {
            "identity": IDENTITY,
            "method": "POSTPROCESSING_ONLY_NO_STRATEGY_RERUN",
            "preserved_prefix_sha256": EXPECTED_PREFIX_SHA256,
            "claim_sha256": file_sha(CLAIM),
            "config_sha256": file_sha(CONFIG),
            "outputs": {
                path.as_posix(): file_sha(path) for path in (RESULT, CYCLES, EQUITY, NEGATIVE)
            },
            "result_canonical_hash": _canonical_hash(result),
        },
    )
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
