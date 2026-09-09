"""Published offline M021 five-hour dense ping-pong mechanics runner."""

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
from crypto_strategy_lab.microstructure.zonal_ping_pong import DensePingPongProbe
from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelStatus, compute_model_hash
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
MODEL_ID = "M021"
START = datetime(2025, 1, 1, tzinfo=UTC)
END = datetime(2025, 1, 1, 5, tzinfo=UTC)
START_US = _datetime_to_micros(START)
END_US = _datetime_to_micros(END)
OWNER_WINDOW = Path("docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md")
OWNER_DIRECTIVE = Path("docs/microstructure/M021_DENSE_PING_PONG_OWNER_DIRECTIVE.md")
SPEC = Path("docs/microstructure/M021_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M021_DENSE_PING_PONG_PREREGISTRATION.md")
REVIEW = Path("reports/usdcusdt/M021-preflight-independent-review.md")
JOURNAL = Path("docs/research/M021_JOURNAL.md")
GRID = Path("reports/usdcusdt/M021-dense-grid.json")
OUTPUT = Path("artifacts/usdcusdt/l2-monthly-samples/M021/OWNER_GATED_5H/PRICE_PRIORITY")
RESULT = Path("reports/usdcusdt/M021-5h-result.json")
SOURCE_PATHS = (
    Path("scripts/run_dense_ping_pong.py"),
    Path("scripts/register_dense_ping_pong.py"),
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
            raise ValueError(f"M021_OWNER_GATE_REQUIRED:{key}")


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def expected_grid() -> dict[str, tuple[tuple[str, str, str], ...]]:
    anchor = D("1.0020")
    tick = D("0.0001")
    return {
        "buy": tuple(
            (f"B{index:03d}", str(anchor - tick * index), str(anchor - tick * (index - 1)))
            for index in range(1, 101)
        ),
        "sell": tuple(
            (f"S{index:03d}", str(anchor + tick * index), str(anchor + tick * (index - 1)))
            for index in range(1, 101)
        ),
    }


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
        raise ValueError("M021_GRID_ARTIFACT_MISMATCH")
    if (
        design["start"] != "2025-01-01T00:00:00Z"
        or design["end_exclusive"] != "2025-01-01T05:00:00Z"
        or design["grid_anchor"] != "1.0020"
        or design["initial_usdt"] != "99.6950"
        or design["initial_usdc"] != "100"
        or design["total_logical_slots"] != 200
        or design["virtual_filter_override"] != "MIN_NOTIONAL_ONLY"
        or design["rolling_recenter"] is not False
        or design["day2_authorized"] is not False
    ):
        raise ValueError("M021_FROZEN_INVARIANT_MISMATCH")


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
        raise ValueError("M021_REQUIRES_PUBLISHED_HEAD")
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
        "grid_sha256_lf": lf_sha(GRID),
    }
    registry = ModelRegistry()
    model = registry.get(MODEL_ID)
    if registry.current_status(MODEL_ID) != ModelStatus.CREATED:
        raise ValueError("M021_REQUIRES_CREATED_STATUS")
    if dict(model.model) != expected_model or model.model_hash != compute_model_hash(
        expected_model
    ):
        raise ValueError("M021_REGISTERED_DESIGN_MISMATCH")
    return sha, json.loads(MANIFEST.read_bytes()), json.loads(VALIDATION_REPORT.read_bytes())


def execute(
    engine: DensePingPongProbe,
    canonical: dict[int, Any],
    slices: tuple[dict[str, Any], ...],
    identity: dict[str, Any],
    evidence: dict[str, Any],
    output: Path = OUTPUT,
) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise ValueError("EXISTING_M021_EXPERIMENT_PRESERVED")
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
                raise ValueError("M021_UNBOUND_INTERIOR_NATIVE_TRADE")
            if trade.trade_id in seen or not trade_timestamp_matches(trade.time_us, native["T"]):
                raise ValueError("M021_CANONICAL_TRADE_BINDING_CHANGED")
            if (trade.price, trade.quantity, trade.buyer_maker) != (
                D(native["p"]),
                D(native["q"]),
                native["m"],
            ):
                raise ValueError("M021_CANONICAL_TRADE_FIELDS_CHANGED")
            consumed = engine.receive_trade(trade, capture_time_us=event["local_us"])
            if consumed < 0 or consumed > trade.quantity:
                raise ValueError("M021_GLOBAL_TRADE_BUDGET_EXCEEDED")
            seen.add(trade.trade_id)
            market_low = trade.price if market_low is None else min(market_low, trade.price)
            market_high = trade.price if market_high is None else max(market_high, trade.price)
        if event_count % 50_000 == 0:
            engine.validate_invariants()
    if seen != set(canonical):
        raise ValueError("M021_CANONICAL_5H_NOT_FULLY_DELIVERED")
    engine.finish(time_us=END_US)
    engine.validate_invariants()

    metrics = engine.metrics()
    if (
        metrics["grid_anchor"] != "1.0020"
        or metrics["initial_usdt"] != "99.6950"
        or metrics["initial_usdc"] != "100"
        or metrics["max_simultaneous_open_orders"] != 200
    ):
        raise ValueError("M021_PHYSICAL_INITIALIZATION_MISMATCH")
    terminal = engine.checkpoint()
    audit_validation = independent_execution_audit(
        engine.audit,
        terminal,
        {str(trade_id): trade for trade_id, trade in canonical.items()},
        metrics,
    )
    audit_validation["status"] = "PASS_M021_LEDGER_EXECUTION_LIQUIDITY"
    audit_file = _audit_rows(output / "execution-audit.jsonl", engine.audit)
    audit = {**audit_validation, "file": audit_file}

    total = int(metrics["total_positive_cycles"])
    slots = []
    for row in metrics["slot_report"]:
        slots.append(
            {
                "SLOT": row["slot_id"],
                "INITIAL_SIDE": row["initial_side"],
                "PRICE": row["price"],
                "FILLS": row["fills"],
                "FILLED_QUANTITY": row["filled_quantity"],
                "COMPLETE_CYCLES": row["complete_cycles"],
                "ACTIVE_TIME_US": row["active_time_us"],
                "QUEUE_BLOCKED_QUANTITY": row["queue_blocked"],
                "OPEN_POSITION_AT_CUTOFF": row["open_position_at_cutoff"],
            }
        )
    buckets = []
    for bucket, row in metrics["bucket_report"].items():
        buckets.append(
            {
                "BUCKET": bucket,
                "FILLS": row["fills"],
                "CYCLES": row["cycles"],
                "SHARE_OF_TOTAL": str(D(row["cycles"]) / D(total)) if total else "0",
            }
        )
    slot_ranking = sorted(slots, key=lambda row: (-row["COMPLETE_CYCLES"], row["SLOT"]))
    bucket_ranking = sorted(buckets, key=lambda row: (-row["CYCLES"], row["BUCKET"]))
    event_counts = Counter(row["event"] for row in engine.audit)
    queue_blocked = int(metrics.get("queue_blocked_events", 0))
    partial_stalls = sum(
        1 for order in engine.orders if order.filled > 0 and order.remaining > 0
    )
    open_positions = sum(bool(row["OPEN_POSITION_AT_CUTOFF"]) for row in slots)
    limiter = "UNDETERMINED_PENDING_POST_RUN_AUTOPSY"
    result = {
        **identity,
        "DISCLAIMER": DensePingPongProbe.normalized_label,
        "RUN_STATUS": "COMPLETE",
        "VERDICT": "MECHANICS_MEASURED_NOT_STRATEGY_APPROVAL",
        "MODEL": MODEL_ID,
        "PERIOD": "5H",
        "TOTAL_COMPLETE_CYCLES": int(metrics["total_cycles"]),
        "TOTAL_POSITIVE_CYCLES": total,
        "CYCLES_PER_HOUR": metrics["cycles_per_hour"],
        "PING_PONG_MECHANIC_OBSERVED": total > 0,
        "BUY_FIRST_CYCLES": metrics["buy_first_cycles"],
        "SELL_FIRST_CYCLES": metrics["sell_first_cycles"],
        "TOTAL_FILL_EVENTS": metrics["total_fills"],
        "BUY_FILL_EVENTS": metrics["buy_fills"],
        "SELL_FILL_EVENTS": metrics["sell_fills"],
        "FULL_ORDER_FILLS": sum(order.status == "FILLED" for order in engine.orders),
        "MAX_SIMULTANEOUS_OPEN_ORDERS": metrics["max_simultaneous_open_orders"],
        "TOP_10_SLOTS": [
            {"RANK": index + 1, "SLOT": row["SLOT"], "CYCLES": row["COMPLETE_CYCLES"]}
            for index, row in enumerate(slot_ranking[:10])
        ],
        "TOP_5_BUCKETS": [
            {"RANK": index + 1, "BUCKET": row["BUCKET"], "CYCLES": row["CYCLES"]}
            for index, row in enumerate(bucket_ranking[:5])
        ],
        "ALL_SLOTS": slots,
        "ALL_BUCKETS": buckets,
        "INITIAL_USDT": metrics["initial_usdt"],
        "INITIAL_USDC": metrics["initial_usdc"],
        "INITIAL_MARKED_EQUITY": metrics["initial_marked_equity"],
        "USDT_FINAL": metrics["usdt_final"],
        "USDC_FINAL": metrics["usdc_final"],
        "TOTAL_MARKED_EQUITY": metrics["total_marked_equity"],
        "REALIZED_NET_PNL": metrics["realized_profit"],
        "UNREALIZED_PNL": metrics["unrealized_pnl"],
        "OPEN_POSITIONS_AT_CUTOFF": open_positions,
        "MARKET_LOW": None if market_low is None else str(market_low),
        "MARKET_HIGH": None if market_high is None else str(market_high),
        "POST_ONLY_REJECTIONS": event_counts["REJECTED_POST_ONLY"],
        "SELF_CROSS_BLOCKS": event_counts["SELF_CROSS_BLOCKED"]
        + event_counts["REJECTED_SELF_CROSS"],
        "QUEUE_BLOCKED_EVENTS": queue_blocked,
        "PARTIAL_FILL_STALLS": partial_stalls,
        "CAPITAL_BLOCKS": event_counts["CAPITAL_BLOCKED"],
        "INVENTORY_BLOCKS": event_counts["INVENTORY_BLOCKED"],
        "BOOK_COVERAGE_BLOCKS": event_counts["COVERAGE_BLOCKED"],
        "ORDERS_CANCELED": metrics["orders_canceled"],
        "ORDERS_RECENTERED": 0,
        "IMPLEMENTATION_BUG": False,
        "MAIN_LIMITER": limiter,
        "CAPTURED_EVENTS": event_count,
        "PROCESSED_TRADES": len(seen),
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
        "order_notional_mode": "NORMALIZED_1_USDC_NON_EXECUTABLE_MECHANICS_PROBE",
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
        "grid_sha256_lf": lf_sha(GRID),
        "data_manifest_sha256": file_sha(MANIFEST),
        "cutoff_liquidation": False,
        "day2_authorized": False,
    }
    identity["run_hash"] = json_hash(identity)
    engine = DensePingPongProbe(
        start_us=START_US,
        end_us=END_US,
        latency_us=profile.latency_us,
        cancel_latency_us=profile.cancel_latency_us,
    )
    with campaign_writer_lock():
        return execute(engine, canonical, slices, identity, evidence)


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
