"""Published offline M022 five-hour order-manager comparison runner."""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from crypto_strategy_lab.microstructure.serial_replay import _datetime_to_micros
from crypto_strategy_lab.microstructure.zonal_ping_pong import (
    M021_TICK_SIZE,
    ManagedDensePingPongProbe,
)
from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelStatus, compute_model_hash
from scripts.run_dense_ping_pong import expected_grid
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
from scripts.run_zonal_ping_pong import (
    _audit_rows,
    bounded_inputs,
    bounded_native_events,
    independent_execution_audit,
)
from scripts.validate_tardis_l2_samples import MANIFEST, TRADE_MANIFEST, trade_timestamp_matches
from scripts.validate_tardis_l2_samples import OUTPUT as VALIDATION_REPORT

D = Decimal
ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "M022"
START = datetime(2025, 1, 1, tzinfo=UTC)
END = datetime(2025, 1, 1, 5, tzinfo=UTC)
START_US = _datetime_to_micros(START)
END_US = _datetime_to_micros(END)
OWNER_WINDOW = Path("docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md")
OWNER_DIRECTIVE = Path("docs/microstructure/M022_ORDER_MANAGER_OWNER_DIRECTIVE.md")
SPEC = Path("docs/microstructure/M022_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M022_ORDER_MANAGER_PREREGISTRATION.md")
REVIEW = Path("reports/usdcusdt/M022-preflight-independent-review.md")
JOURNAL = Path("docs/research/M022_JOURNAL.md")
GRID = Path("reports/usdcusdt/M021-dense-grid.json")
OUTPUT = Path("artifacts/usdcusdt/l2-monthly-samples/M022/OWNER_GATED_5H/PRICE_PRIORITY")
RESULT = Path("reports/usdcusdt/M022-5h-result.json")
SOURCE_PATHS = (
    Path("scripts/run_managed_dense_ping_pong.py"),
    Path("scripts/register_managed_dense_ping_pong.py"),
    Path("scripts/run_dense_ping_pong.py"),
    Path("scripts/run_zonal_ping_pong.py"),
    Path("scripts/validate_tardis_l2_samples.py"),
    Path("scripts/run_l2_monthly_samples.py"),
    Path("scripts/run_high_uptime_recovery.py"),
    Path("scripts/run_b10_reality.py"),
    Path("src/crypto_strategy_lab/microstructure/zonal_ping_pong.py"),
    Path("src/crypto_strategy_lab/microstructure/data.py"),
    Path("src/crypto_strategy_lab/microstructure/tardis_l2.py"),
    Path("src/crypto_strategy_lab/microstructure/b10_reality.py"),
    Path("src/crypto_strategy_lab/microstructure/recovery_reserve_study.py"),
    Path("src/crypto_strategy_lab/microstructure/serial_replay.py"),
    Path("src/crypto_strategy_lab/domain.py"),
    Path("src/crypto_strategy_lab/ml/model_registry.py"),
    Path("tests/test_managed_dense_ping_pong.py"),
    Path("tests/test_run_managed_dense_ping_pong.py"),
    Path("tests/test_dense_ping_pong.py"),
    Path("tests/test_run_dense_ping_pong.py"),
    Path("tests/test_zonal_ping_pong.py"),
    Path("tests/test_run_zonal_ping_pong.py"),
    Path("tests/test_model_registry.py"),
)


def require_owner_gate(root: Path = ROOT) -> None:
    authority = (root / OWNER_WINDOW).read_text(encoding="utf-8")
    expected = {
        "APPROVED_COMPARISON_DAYS": "1",
        "EXTENSION_AUTHORIZED": "false",
        "NEW_REPLAY_AUTHORIZED_NOW": "true",
        "AUTHORIZED_MODEL": MODEL_ID,
    }
    for key, value in expected.items():
        observed = re.findall(rf"^{key}=(.*)$", authority, flags=re.MULTILINE)
        if observed != [value]:
            raise ValueError(f"M022_OWNER_GATE_REQUIRED:{key}")


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def validate_frozen_design(design: dict[str, Any], grid: dict[str, Any]) -> None:
    expected = expected_grid()
    observed_buy = tuple(
        (row["slot_id"], row["entry_price"], row["return_price"])
        for row in grid["buy_slots"]
    )
    observed_sell = tuple(
        (row["slot_id"], row["entry_price"], row["return_price"])
        for row in grid["sell_slots"]
    )
    if observed_buy != expected["buy"] or observed_sell != expected["sell"]:
        raise ValueError("M022_REQUIRES_IMMUTABLE_M021_LATTICE")
    if (
        design["start"] != "2025-01-01T00:00:00Z"
        or design["end_exclusive"] != "2025-01-01T05:00:00Z"
        or design["initial_usdt"] != "99.6950"
        or design["initial_usdc"] != "100"
        or design["total_economic_lanes"] != 200
        or design["max_simultaneous_open_orders"] != 160
        or design["virtual_filter_override"] != "MIN_NOTIONAL_ONLY"
        or design["day2_authorized"] is not False
    ):
        raise ValueError("M022_FROZEN_INVARIANT_MISMATCH")


def campaign_preflight() -> tuple[str, dict[str, Any], dict[str, Any]]:
    require_owner_gate()
    if Path.cwd().resolve() != ROOT.resolve():
        raise ValueError("CANONICAL_REPOSITORY_CWD_REQUIRED")
    if _git_output("branch", "--show-current") != "main":
        raise ValueError("CANONICAL_MAIN_REQUIRED")
    if _git_output("status", "--porcelain"):
        raise ValueError("PRE_EXECUTION_WORKTREE_NOT_CLEAN")
    sha = published_sha()
    if _git_output("rev-parse", "HEAD") != sha or _git_output("rev-parse", "origin/main") != sha:
        raise ValueError("M022_REQUIRES_PUBLISHED_HEAD")
    for path in (
        *SOURCE_PATHS,
        OWNER_DIRECTIVE,
        OWNER_WINDOW,
        SPEC,
        PREREG,
        REVIEW,
        JOURNAL,
        GRID,
        MANIFEST,
        VALIDATION_REPORT,
        TRADE_MANIFEST,
        PROFILE_CONFIG,
    ):
        published_bytes(path, sha)
    validate_review(REVIEW, SOURCE_PATHS)
    if file_sha(PROFILE_CONFIG) != PROFILE_CONFIG_SHA:
        raise ValueError("FROZEN_PROFILE_CHANGED")

    design = json.loads(SPEC.read_bytes())
    grid = json.loads(GRID.read_bytes())
    validate_frozen_design(design, grid)
    expected_model = {
        **design,
        "spec_sha256_lf": lf_sha(SPEC),
        "preregistration_sha256_lf": lf_sha(PREREG),
        "owner_directive_sha256_lf": lf_sha(OWNER_DIRECTIVE),
    }
    registry = ModelRegistry()
    model = registry.get(MODEL_ID)
    if registry.current_status(MODEL_ID) != ModelStatus.CREATED:
        raise ValueError("M022_REQUIRES_CREATED_STATUS")
    if dict(model.model) != expected_model or model.model_hash != compute_model_hash(
        expected_model
    ):
        raise ValueError("M022_REGISTERED_DESIGN_MISMATCH")
    return sha, json.loads(MANIFEST.read_bytes()), json.loads(VALIDATION_REPORT.read_bytes())


def manager_audit(
    rows: list[dict[str, Any]], terminal: dict[str, Any], metrics: dict[str, Any]
) -> dict[str, Any]:
    counts = Counter(row["event"] for row in rows)
    canceled_ids = {row["order_id"] for row in rows if row["event"] == "CANCEL_ACK"}
    requested_ids = {row["order_id"] for row in rows if row["event"] == "CANCEL_REQUEST"}
    if not canceled_ids.issubset(requested_ids):
        raise ValueError("M022_CANCEL_ACK_WITHOUT_REQUEST")

    submitted: dict[int, dict[str, Any]] = {}
    open_ids: set[int] = set()
    filled: dict[int, D] = {}
    lane_profit_timeline: dict[str, D] = {}
    observed_max = 0
    claims: dict[str, dict[str, Any]] = {}
    return_orders: dict[int, dict[str, Any]] = {}
    cancel_request_index: dict[int, int] = {}
    for index, row in enumerate(rows):
        event = row["event"]
        if event == "SUBMIT":
            order_id = int(row["order_id"])
            if order_id in submitted:
                raise ValueError("M022_DUPLICATE_ORDER_ID")
            submitted[order_id] = row
            open_ids.add(order_id)
            filled[order_id] = D(0)
            observed_max = max(observed_max, len(open_ids))
            lane = row["band_id"]
            if row.get("role") == "ENTRY" and row["side"] == "BUY":
                index_value = int(lane[1:])
                original_budget = D(terminal["state"]["dense_anchor"]) - (
                    M021_TICK_SIZE * index_value
                )
                if D(row["price"]) > original_budget + lane_profit_timeline.get(lane, D(0)):
                    raise ValueError("M022_CROSS_LANE_BUY_FUNDING_DETECTED")
        elif event == "CANCEL_REQUEST":
            cancel_request_index[int(row["order_id"])] = index
        elif event == "RETURN_PRICE_CLAIM":
            claims[row["lane"]] = row
        elif event == "RETURN_SUBMISSION":
            order_id = int(row["order_id"])
            claim = claims.get(row["lane"])
            if (
                claim is None
                or claim["return_side"] != row["side"]
                or D(claim["return_price"]) != D(row["price"])
            ):
                raise ValueError("M022_RETURN_SUBMISSION_WITHOUT_MATCHING_CLAIM")
            return_orders[order_id] = row
        elif event == "RETURN_FILL":
            order_id = int(row["order_id"])
            submission = return_orders.get(order_id)
            if submission is None or submission["lane"] != row["lane"]:
                raise ValueError("M022_RETURN_FILL_WITHOUT_MATCHING_SUBMISSION")
        elif event == "RETURN_PREEMPTION":
            order_id = int(row["free_order_id"])
            source = submitted.get(order_id)
            if (
                source is None
                or source.get("role") != "ENTRY"
                or order_id not in cancel_request_index
                or cancel_request_index[order_id] > index
            ):
                raise ValueError("M022_UNTRACEABLE_RETURN_PREEMPTION")
        elif event == "FILL":
            order_id = int(row["order_id"])
            source = submitted.get(order_id)
            if source is None:
                raise ValueError("M022_FILL_WITHOUT_SUBMISSION")
            filled[order_id] += D(row["quantity"])
            if filled[order_id] >= D(source["quantity"]):
                open_ids.discard(order_id)
        elif event == "CYCLE":
            lane = row["band_id"]
            lane_profit_timeline[lane] = lane_profit_timeline.get(lane, D(0)) + D(
                row["profit"]
            )
            claims.pop(lane, None)
        elif event == "CANCEL_ACK" or event.startswith("REJECTED_"):
            open_ids.discard(int(row["order_id"]))

    terminal_open = {
        int(order["order_id"])
        for order in terminal["state"]["orders"]
        if order["status"] in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
    }
    if open_ids != terminal_open:
        raise ValueError("M022_OPEN_ORDER_TIMELINE_MISMATCH")
    if observed_max != int(metrics["max_simultaneous_open_orders"]):
        raise ValueError("M022_REPORTED_OPEN_ORDER_MAX_MISMATCH")
    if observed_max > 160:
        raise ValueError("M022_OPEN_ORDER_CAP_EXCEEDED")
    if counts["RETURN_PREEMPTION"] != int(metrics["return_preemptions"]):
        raise ValueError("M022_PREEMPTION_TRACE_MISMATCH")
    if counts["RETURN_SUBMISSION"] != int(metrics["return_submissions"]):
        raise ValueError("M022_RETURN_SUBMISSION_TRACE_MISMATCH")
    if counts["RETURN_FILL"] != int(metrics["return_fills"]):
        raise ValueError("M022_RETURN_FILL_TRACE_MISMATCH")
    if counts["FREE_ORDER_CANCELED_FOR_RETURN"] != int(
        metrics["free_orders_canceled_for_return"]
    ):
        raise ValueError("M022_RETURN_CANCEL_TRACE_MISMATCH")
    if counts["FREE_ORDER_CANCELED_FOR_FLOAT"] != int(
        metrics["free_orders_canceled_for_float"]
    ):
        raise ValueError("M022_FLOAT_CANCEL_TRACE_MISMATCH")
    if counts["FREE_ORDER_REPOSTED"] != int(metrics["free_orders_reposted"]):
        raise ValueError("M022_REPOST_TRACE_MISMATCH")

    physical_submissions = {
        (
            int(row["order_id"]),
            row["band_id"],
            row["side"],
            D(row["price"]),
            row["time_us"],
        )
        for row in rows
        if row["event"] == "SUBMIT" and row.get("role") == "EXIT"
    }
    traced_submissions = {
        (
            int(row["order_id"]),
            row["lane"],
            row["side"],
            D(row["price"]),
            row["time_us"],
        )
        for row in rows
        if row["event"] == "RETURN_SUBMISSION"
    }
    if physical_submissions != traced_submissions:
        raise ValueError("M022_RETURN_SUBMISSION_PHYSICAL_MISMATCH")

    physical_return_fills = Counter(
        (
            int(row["order_id"]),
            row["band_id"],
            row["side"],
            D(row["price"]),
            D(row["quantity"]),
            row["time_us"],
        )
        for row in rows
        if row["event"] == "FILL" and row.get("role") == "EXIT"
    )
    traced_return_fills = Counter(
        (
            int(row["order_id"]),
            row["lane"],
            row["side"],
            D(row["price"]),
            D(row["quantity"]),
            row["time_us"],
        )
        for row in rows
        if row["event"] == "RETURN_FILL"
    )
    if physical_return_fills != traced_return_fills:
        raise ValueError("M022_RETURN_FILL_PHYSICAL_MISMATCH")

    physical_entry_fills: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if row["event"] == "FILL" and row.get("role") == "ENTRY":
            physical_entry_fills.setdefault(int(row["order_id"]), []).append(row)
    for row in rows:
        if row["event"] != "RETURN_PRICE_CLAIM":
            continue
        source_id = int(row["source_order_id"])
        source = submitted.get(source_id)
        source_fills = physical_entry_fills.get(source_id, [])
        if (
            source is None
            or source.get("role") != "ENTRY"
            or source["band_id"] != row["lane"]
            or not any(fill_row["time_us"] == row["time_us"] for fill_row in source_fills)
        ):
            raise ValueError("M022_RETURN_CLAIM_PHYSICAL_MISMATCH")
        expected_side = "SELL" if source["side"] == "BUY" else "BUY"
        expected_price = D(source["price"]) + (
            M021_TICK_SIZE if expected_side == "SELL" else -M021_TICK_SIZE
        )
        if row["return_side"] != expected_side or D(row["return_price"]) != expected_price:
            raise ValueError("M022_RETURN_CLAIM_PRICE_MISMATCH")

    state = terminal["state"]
    state_ownership = state.get("manager_lane_ownership", {})
    metric_ownership = metrics["lane_ownership"]
    if set(state_ownership) != set(metric_ownership):
        raise ValueError("M022_LANE_OWNERSHIP_REPORT_MISMATCH")
    for lane, initial in state_ownership.items():
        reported = metric_ownership[lane]
        expected_usdt = D(0)
        expected_usdc = D(0)
        if lane.startswith("B"):
            expected_usdt = D(state["dense_anchor"]) - M021_TICK_SIZE * int(lane[1:])
        else:
            expected_usdc = D(1)
        if (
            D(initial["initial_usdt"]) != expected_usdt
            or D(initial["initial_usdc"]) != expected_usdc
            or D(reported["initial_usdt"]) != expected_usdt
            or D(reported["initial_usdc"]) != expected_usdc
            or D(state["manager_lane_profit"][lane])
            != lane_profit_timeline.get(lane, D(0))
            or D(reported["profit"]) != lane_profit_timeline.get(lane, D(0))
        ):
            raise ValueError("M022_LANE_OWNERSHIP_REPORT_MISMATCH")
    s_free = state.get("manager_s_free", {})
    if sum((D(value["quantity"]) for value in s_free.values()), D(0)) != D(
        state["endowment_free_quantity"]
    ):
        raise ValueError("M022_PARKED_USDC_OWNERSHIP_MISMATCH")

    expected_s_free = {
        f"S{index:03d}": {"quantity": D(1), "cost": D(state["dense_first_bid"])}
        for index in range(1, 101)
    }
    s_entry_reservations: dict[int, tuple[str, D, D]] = {}
    closed_s_entries: set[int] = set()
    chronological_filled: dict[int, D] = {}
    for row in rows:
        event = row["event"]
        if event == "SUBMIT":
            order_id = int(row["order_id"])
            if (
                row.get("role") == "ENTRY"
                and row["side"] == "SELL"
                and row["band_id"].startswith("S")
            ):
                lane = row["band_id"]
                quantity = D(row["quantity"])
                free = expected_s_free[lane]
                if quantity <= 0 or free["quantity"] < quantity:
                    raise ValueError("M022_CROSS_LANE_SELL_FUNDING_DETECTED")
                basis = free["cost"] / free["quantity"]
                free["quantity"] -= quantity
                free["cost"] -= quantity * basis
                s_entry_reservations[order_id] = (lane, quantity, basis)
            chronological_filled[order_id] = D(0)
        elif event == "FILL":
            order_id = int(row["order_id"])
            chronological_filled[order_id] = chronological_filled.get(order_id, D(0)) + D(
                row["quantity"]
            )
        elif event == "CANCEL_ACK" or event.startswith("REJECTED_"):
            order_id = int(row["order_id"])
            reservation = s_entry_reservations.get(order_id)
            if reservation is not None and order_id not in closed_s_entries:
                lane, quantity, basis = reservation
                remainder = quantity - chronological_filled.get(order_id, D(0))
                if remainder < 0:
                    raise ValueError("M022_S_LANE_RESERVATION_UNDERFLOW")
                expected_s_free[lane]["quantity"] += remainder
                expected_s_free[lane]["cost"] += remainder * basis
                closed_s_entries.add(order_id)
        elif event == "CYCLE" and row.get("direction") == "SELL_BUY":
            lane = row["band_id"]
            quantity = D(row["quantity"])
            return_order = submitted.get(int(row["source_order_id"]))
            if return_order is None or return_order.get("role") != "EXIT":
                raise ValueError("M022_S_LANE_RETURN_SOURCE_MISSING")
            expected_s_free[lane]["quantity"] += quantity
            expected_s_free[lane]["cost"] += quantity * D(return_order["price"])

    if set(s_free) != set(expected_s_free):
        raise ValueError("M022_S_LANE_OWNERSHIP_SET_MISMATCH")
    for lane, expected in expected_s_free.items():
        observed = s_free[lane]
        reported = metric_ownership[lane]
        if (
            D(observed["quantity"]) != expected["quantity"]
            or D(observed["cost"]) != expected["cost"]
            or D(reported["free_usdc"]) != expected["quantity"]
            or D(reported["free_usdc_cost"]) != expected["cost"]
        ):
            raise ValueError("M022_S_LANE_OWNERSHIP_RECONSTRUCTION_MISMATCH")
    return {
        "status": "PASS_M022_MANAGER_LEDGER_EXECUTION_LIQUIDITY",
        "cancel_requests": len(requested_ids),
        "cancel_acks": len(canceled_ids),
        "open_cancel_requests_at_cutoff": len(requested_ids - canceled_ids),
        "return_claim_events": counts["RETURN_PRICE_CLAIM"],
        "return_preemption_events": counts["RETURN_PREEMPTION"],
        "owned_return_conflicts": counts["OWNED_RETURN_CONFLICT"],
        "partial_residual_blocks": counts["PARTIAL_RESIDUAL_BLOCKED"],
        "cap_observed": observed_max,
    }


def execute(
    engine: ManagedDensePingPongProbe,
    canonical: dict[int, Any],
    slices: tuple[dict[str, Any], ...],
    identity: dict[str, Any],
    evidence: dict[str, Any],
    output: Path = OUTPUT,
) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise ValueError("EXISTING_M022_EXPERIMENT_PRESERVED")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "run-manifest.json", identity)
    seen: set[int] = set()
    event_count = 0
    market_low: D | None = None
    market_high: D | None = None
    for event_count, event in enumerate(bounded_native_events(slices), 1):
        if event["kind"] == "BOOK":
            if event["sequence_validated"]:
                engine.receive_book(
                    {
                        "exchange_time_us": event["exchange_us"],
                        "exchange_upper_us": event["exchange_upper_us"],
                        "capture_time_us": event["local_us"],
                        "capture_order": event["capture_order"],
                        "bids": event["bids"],
                        "asks": event["asks"],
                        "known_bid_floor": event["known_bid_floor"],
                        "known_ask_ceiling": event["known_ask_ceiling"],
                    }
                )
        else:
            native = event["data"]
            trade = canonical.get(native["t"])
            if trade is None:
                raise ValueError("M022_UNBOUND_INTERIOR_NATIVE_TRADE")
            if trade.trade_id in seen or not trade_timestamp_matches(trade.time_us, native["T"]):
                raise ValueError("M022_CANONICAL_TRADE_BINDING_CHANGED")
            if (trade.price, trade.quantity, trade.buyer_maker) != (
                D(native["p"]),
                D(native["q"]),
                native["m"],
            ):
                raise ValueError("M022_CANONICAL_TRADE_FIELDS_CHANGED")
            consumed = engine.receive_trade(trade, capture_time_us=event["local_us"])
            if consumed < 0 or consumed > trade.quantity:
                raise ValueError("M022_GLOBAL_TRADE_BUDGET_EXCEEDED")
            seen.add(trade.trade_id)
            market_low = trade.price if market_low is None else min(market_low, trade.price)
            market_high = trade.price if market_high is None else max(market_high, trade.price)
        if event_count % 50_000 == 0:
            engine.validate_invariants()
    if seen != set(canonical):
        raise ValueError("M022_CANONICAL_5H_NOT_FULLY_DELIVERED")
    engine.finish(time_us=END_US)
    engine.validate_invariants()

    metrics = engine.metrics()
    if (
        metrics["grid_anchor"] != "1.0020"
        or metrics["initial_usdt"] != "99.6950"
        or metrics["initial_usdc"] != "100"
        or int(metrics["max_simultaneous_open_orders"]) > 160
    ):
        raise ValueError("M022_PHYSICAL_INITIALIZATION_OR_CAP_MISMATCH")
    terminal = engine.checkpoint()
    base_audit = independent_execution_audit(
        engine.audit,
        terminal,
        {str(trade_id): trade for trade_id, trade in canonical.items()},
        metrics,
    )
    manager_validation = manager_audit(engine.audit, terminal, metrics)
    audit_file = _audit_rows(output / "execution-audit.jsonl", engine.audit)
    audit = {**base_audit, **manager_validation, "file": audit_file}

    total = int(metrics["total_positive_cycles"])
    delta = total - 19
    event_counts = Counter(row["event"] for row in engine.audit)
    open_positions = sum(
        bool(row["open_position_at_cutoff"]) for row in metrics["slot_report"]
    )
    result = {
        **identity,
        "DISCLAIMER": ManagedDensePingPongProbe.normalized_label,
        "RUN_STATUS": "COMPLETE",
        "VERDICT": "ORDER_MANAGER_COMPARISON_MEASURED_NOT_STRATEGY_APPROVAL",
        "MODEL": MODEL_ID,
        "PERIOD": "5H",
        "TOTAL_COMPLETE_CYCLES": int(metrics["total_cycles"]),
        "TOTAL_POSITIVE_CYCLES": total,
        "CYCLES_PER_HOUR": metrics["cycles_per_hour"],
        "M021_BASELINE": 19,
        "DELTA_VS_M021": delta,
        "MULTIPLIER_VS_M021": str(D(total) / D(19)),
        "DID_ORDER_MANAGEMENT_IMPROVE_THROUGHPUT": total > 19,
        "BUY_FIRST_CYCLES": metrics["buy_first_cycles"],
        "SELL_FIRST_CYCLES": metrics["sell_first_cycles"],
        "TOTAL_FILL_EVENTS": metrics["total_fills"],
        "BUY_FILL_EVENTS": metrics["buy_fills"],
        "SELL_FILL_EVENTS": metrics["sell_fills"],
        "RETURN_PREEMPTIONS": metrics["return_preemptions"],
        "FREE_CANCELS_FOR_RETURN": metrics["free_orders_canceled_for_return"],
        "FREE_CANCELS_FOR_FLOAT": metrics["free_orders_canceled_for_float"],
        "FREE_ORDERS_REPOSTED": metrics["free_orders_reposted"],
        "RETURN_SUBMISSIONS": metrics["return_submissions"],
        "RETURN_FILLS": metrics["return_fills"],
        "RETURN_WAIT_TIME_MEAN": metrics["return_wait_time_mean"],
        "RETURN_WAIT_TIME_MEDIAN": metrics["return_wait_time_median"],
        "RETURN_WAIT_TIME_P95": metrics["return_wait_time_p95"],
        "RETURN_BLOCKED_BY_FREE_ORDER_COUNT": metrics["return_blocked_by_free_order_count"],
        "RETURN_BLOCKED_BY_OWNED_RETURN_COUNT": metrics[
            "return_blocked_by_owned_return_count"
        ],
        "SELF_CROSS_RECHECKS": metrics["self_cross_rechecks"],
        "POST_ONLY_REJECTIONS": metrics["post_only_rejections"],
        "QUEUE_BLOCKED_EVENTS": metrics["queue_blocked_events"],
        "MAX_SIMULTANEOUS_OPEN_ORDERS": metrics["max_simultaneous_open_orders"],
        "MEAN_ACTIVE_OPEN_ORDERS": metrics["mean_active_open_orders"],
        "MIN_ACTIVE_OPEN_ORDERS_AFTER_WARMUP": metrics[
            "min_active_open_orders_after_warmup"
        ],
        "PARKED_LANES_MEAN": metrics["parked_lanes_mean"],
        "UNIQUE_LANES_USED": metrics["unique_lanes_used"],
        "UNIQUE_PRICE_LEVELS_USED": metrics["unique_price_levels_used"],
        "UNIQUE_PRODUCTIVE_LANES": metrics["unique_productive_lanes"],
        "PERCENT_ACTIVE_ORDERS_WITHIN_5_TICKS_OF_MID": metrics[
            "percent_active_orders_within_5_ticks_of_mid"
        ],
        "PERCENT_ACTIVE_ORDERS_WITHIN_10_TICKS_OF_MID": metrics[
            "percent_active_orders_within_10_ticks_of_mid"
        ],
        "TIME_WEIGHTED_DISTANCE_FROM_MID": metrics["time_weighted_distance_from_mid"],
        "TOP_10_LANES_BY_CYCLES": metrics["top_10_lanes_by_cycles"],
        "TOP_10_PRICE_LEVELS_BY_CYCLES": metrics["top_10_price_levels_by_cycles"],
        "INITIAL_USDT": metrics["initial_usdt"],
        "INITIAL_USDC": metrics["initial_usdc"],
        "INITIAL_MARKED_EQUITY": metrics["initial_marked_equity"],
        "FINAL_USDT": metrics["usdt_final"],
        "FINAL_USDC": metrics["usdc_final"],
        "FINAL_MARKED_EQUITY": metrics["total_marked_equity"],
        "REALIZED_NET_PNL": metrics["realized_profit"],
        "UNREALIZED_PNL": metrics["unrealized_pnl"],
        "SUM_ROUNDTRIP_CYCLE_PROFIT": metrics["roundtrip_profit"],
        "OPEN_POSITIONS_AT_CUTOFF": open_positions,
        "MARKET_LOW": None if market_low is None else str(market_low),
        "MARKET_HIGH": None if market_high is None else str(market_high),
        "CAPITAL_BLOCKS": event_counts["CAPITAL_BLOCKED"],
        "INVENTORY_BLOCKS": event_counts["INVENTORY_BLOCKED"],
        "BOOK_COVERAGE_BLOCKS": event_counts["COVERAGE_BLOCKED"],
        "CAPTURED_EVENTS": event_count,
        "PROCESSED_TRADES": len(seen),
        "MAIN_LIMITER": "UNDETERMINED_PENDING_POST_RUN_AUTOPSY",
        "MANAGER_METRICS": metrics,
        "DATA_INTEGRITY": evidence,
        "AUDIT": audit,
    }
    write_json(output / "all-fill-audit.json", audit)
    write_json(output / "terminal-engine-state.json", terminal)
    write_json(output / "summary.json", result)
    write_json(RESULT, result)
    return result


def run() -> dict[str, Any]:
    sha, manifest, validation = campaign_preflight()
    profile, canonical, slices, evidence = bounded_inputs(manifest, validation)
    model = ModelRegistry().get(MODEL_ID)
    identity = {
        "model_id": MODEL_ID,
        "model_hash": model.model_hash,
        "capital_mode": "NORMALIZED_MECHANICS_PROBE",
        "order_notional_mode": "NORMALIZED_1_USDC_NON_EXECUTABLE_ORDER_MANAGER_PROBE",
        "normalized_quantity_usdc": "1",
        "virtual_filter_override": "MIN_NOTIONAL_ONLY",
        "start": START.isoformat().replace("+00:00", "Z"),
        "end_exclusive": END.isoformat().replace("+00:00", "Z"),
        "published_config_sha": sha,
        "expected_trade_count": len(canonical),
        "source_sha256_lf": {str(path): lf_sha(path) for path in SOURCE_PATHS},
        "owner_directive_sha256_lf": lf_sha(OWNER_DIRECTIVE),
        "owner_window_sha256_lf": lf_sha(OWNER_WINDOW),
        "spec_sha256_lf": lf_sha(SPEC),
        "protocol_sha256_lf": lf_sha(PREREG),
        "review_sha256_lf": lf_sha(REVIEW),
        "pre_run_journal_sha256_lf": lf_sha(JOURNAL),
        "m021_grid_sha256_lf": lf_sha(GRID),
        "data_manifest_sha256": file_sha(MANIFEST),
        "cutoff_liquidation": False,
        "day2_authorized": False,
    }
    identity["run_hash"] = json_hash(identity)
    engine = ManagedDensePingPongProbe(
        start_us=START_US,
        end_us=END_US,
        latency_us=profile.latency_us,
        cancel_latency_us=profile.cancel_latency_us,
    )
    with campaign_writer_lock():
        return execute(engine, canonical, slices, identity, evidence)


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, default=str))
