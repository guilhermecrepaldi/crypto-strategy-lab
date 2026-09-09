"""Bounded, fail-closed M023 three-hour runner.

This module is intentionally an execution authority only for M023.  It does
not alter the M022 runner or its artifacts; the input helpers are reused and
their output is cut to the M023 three-hour causal prefix before delivery.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.b10_reality import ExecutionProfile, Trade
from crypto_strategy_lab.microstructure.data import (
    HistoryManifest,
    iter_history,
    select_history_archives,
)
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from crypto_strategy_lab.microstructure.serial_hot_line import (
    INITIAL_CASH,
    SerialHotLinePingPongProbe,
)
from crypto_strategy_lab.microstructure.serial_replay import _datetime_to_micros
from crypto_strategy_lab.microstructure.tardis_l2 import iter_native_events
from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelStatus, compute_model_hash
from scripts.run_b10_reality import typed
from scripts.run_high_uptime_recovery import (
    PROFILE_CONFIG,
    PROFILE_CONFIG_SHA,
    campaign_writer_lock,
    lf_sha,
    published_bytes,
    published_sha,
    validate_review,
)
from scripts.run_l2_monthly_samples import json_hash, verify_published_day_evidence
from scripts.validate_tardis_l2_samples import (
    MANIFEST,
    TRADE_MANIFEST,
    checked_path,
    raw_lines,
    validate_slice_metadata,
)
from scripts.validate_tardis_l2_samples import OUTPUT as VALIDATION_REPORT

D0 = D("0")
ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "M023"
SOURCE_DAY = "2025-01-01"
START = datetime(2025, 1, 1, tzinfo=UTC)
END = datetime(2025, 1, 1, 3, tzinfo=UTC)
START_US = _datetime_to_micros(START)
END_US = _datetime_to_micros(END)
OWNER_WINDOW = Path("docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md")
OWNER_DIRECTIVE = Path("docs/microstructure/M023_SERIAL_HOT_LINE_OWNER_DIRECTIVE.md")
SPEC = Path("docs/microstructure/M023_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M023_SERIAL_HOT_LINE_PREREGISTRATION.md")
REVIEW = Path("reports/usdcusdt/M023-preflight-independent-review.md")
JOURNAL = Path("docs/research/M023_JOURNAL.md")
GRID = Path("reports/usdcusdt/M021-dense-grid.json")
OUTPUT = Path("artifacts/usdcusdt/l2-monthly-samples/M023/OWNER_GATED_3H/PRICE_PRIORITY")
RESULT = Path("reports/usdcusdt/M023-3h-result.json")
SOURCE_PATHS = (
    Path("scripts/run_serial_hot_line.py"),
    Path("scripts/register_serial_hot_line.py"),
    Path("scripts/run_zonal_ping_pong.py"),
    Path("scripts/validate_tardis_l2_samples.py"),
    Path("scripts/run_l2_monthly_samples.py"),
    Path("scripts/run_high_uptime_recovery.py"),
    Path("src/crypto_strategy_lab/microstructure/serial_hot_line.py"),
    Path("src/crypto_strategy_lab/microstructure/zonal_ping_pong.py"),
    Path("src/crypto_strategy_lab/microstructure/data.py"),
    Path("src/crypto_strategy_lab/microstructure/tardis_l2.py"),
    Path("src/crypto_strategy_lab/microstructure/recovery_reserve_study.py"),
    Path("src/crypto_strategy_lab/microstructure/serial_replay.py"),
    Path("src/crypto_strategy_lab/domain.py"),
    Path("src/crypto_strategy_lab/ml/model_registry.py"),
    Path("tests/test_serial_hot_line.py"),
    Path("tests/test_run_serial_hot_line.py"),
    Path("tests/test_model_registry.py"),
)


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


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
            raise ValueError(f"M023_OWNER_GATE_REQUIRED:{key}")


def validate_frozen_design(design: dict[str, Any]) -> None:
    required = {
        "model_id": MODEL_ID,
        "start": "2025-01-01T00:00:00Z",
        "end_exclusive": "2025-01-01T03:00:00Z",
        "normalized_quantity_usdc": "1",
        "candidate_radar_addresses": 200,
        "candidate_radar_anchor": "1.0020",
        "buy_deck_cards": 100,
        "sell_deck_cards": 100,
        "max_simultaneous_nonterminal_orders": 1,
        "initial_usdt": "1.0019",
        "initial_usdc": "0",
        "economic_sequence": "BUY_THEN_SELL_STRICTLY_ALTERNATING",
        "day2_authorized": False,
        "extension_authorized": False,
    }
    for key, value in required.items():
        if design.get(key) != value:
            raise ValueError(f"M023_FROZEN_INVARIANT_MISMATCH:{key}")


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
        raise ValueError("M023_REQUIRES_PUBLISHED_HEAD")
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
    design = json.loads((ROOT / SPEC).read_bytes())
    validate_frozen_design(design)
    expected_model = {
        **design,
        "spec_sha256_lf": lf_sha(SPEC),
        "preregistration_sha256_lf": lf_sha(PREREG),
        "owner_directive_sha256_lf": lf_sha(OWNER_DIRECTIVE),
    }
    registry = ModelRegistry()
    model = registry.get(MODEL_ID)
    if registry.current_status(MODEL_ID) != ModelStatus.CREATED:
        raise ValueError("M023_REQUIRES_CREATED_STATUS")
    if dict(model.model) != expected_model or model.model_hash != compute_model_hash(
        expected_model
    ):
        raise ValueError("M023_REGISTERED_DESIGN_MISMATCH")
    return sha, json.loads(MANIFEST.read_bytes()), json.loads(VALIDATION_REPORT.read_bytes())


def bounded_inputs(
    manifest: dict[str, Any], validation: dict[str, Any]
) -> tuple[ExecutionProfile, dict[int, Trade], tuple[dict[str, Any], ...], dict[str, Any]]:
    trade_manifest = json.loads(TRADE_MANIFEST.read_bytes())
    entry = next(item for item in manifest["dates"] if item["date"] == SOURCE_DAY)
    checked = next(item for item in validation["days"] if item["date"] == SOURCE_DAY)
    verified = verify_published_day_evidence(entry, checked, trade_manifest)
    slices = tuple(
        sorted(
            (item for item in entry["raw_slices"] if int(item["offset"]) < 180),
            key=lambda item: int(item["offset"]),
        )
    )
    if len(slices) != 18 or tuple(item["offset"] for item in slices) != tuple(range(0, 180, 10)):
        raise ValueError("M023_EXACT_FIRST_18_SLICES_REQUIRED")
    for item in slices:
        validate_slice_metadata(SOURCE_DAY, item)
        path = checked_path(ROOT, item["local_path"], SOURCE_DAY, raw=True)
        if path.stat().st_size != item["bytes"] or file_sha(path) != item["sha256"]:
            raise ValueError("M023_BOUNDED_NATIVE_EVIDENCE_CHANGED")

    history = HistoryManifest.model_validate_json(TRADE_MANIFEST.read_bytes())
    read_start = max(START, history.first_timestamp)
    selected = select_history_archives(history, start=read_start, end_exclusive=END)
    if len(selected) != 1 or selected[0].cadence != "daily":
        raise ValueError("M023_EXACT_DAILY_TRADE_ARCHIVE_REQUIRED")
    if file_sha(Path(selected[0].local_path)) != selected[0].sha256:
        raise ValueError("M023_CANONICAL_ARCHIVE_CHANGED")
    canonical: dict[int, Trade] = {}
    for event in iter_history(history, start=read_start, end_exclusive=END):
        if event.trade_id in canonical:
            raise ValueError("M023_DUPLICATE_CANONICAL_TRADE")
        canonical[event.trade_id] = Trade(
            _datetime_to_micros(event.timestamp),
            event.trade_id,
            event.price,
            event.quantity,
            event.buyer_is_maker,
        )
    config = json.loads(PROFILE_CONFIG.read_bytes())
    profile_row = next(
        row for row in config["profiles"] if row["profile"]["name"] == "B_REALISTIC_CONSERVATIVE"
    )
    profile = typed(ExecutionProfile, profile_row["profile"])
    return (
        profile,
        canonical,
        slices,
        {
            "validation": verified,
            "bounded_slice_count": len(slices),
            "bounded_slice_offsets": [item["offset"] for item in slices],
            "bounded_slice_sha256": hashlib.sha256(
                "\n".join(f"{item['offset']}:{item['sha256']}" for item in slices).encode()
            ).hexdigest(),
            "canonical_trade_count": len(canonical),
            "canonical_first_trade_id": min(canonical),
            "canonical_last_trade_id": max(canonical),
            "m023_end_us": END_US,
        },
    )


def bounded_native_events(slices: tuple[dict[str, Any], ...]):
    for event in iter_native_events(raw_lines(ROOT, SOURCE_DAY, slices)):
        if event["local_us"] >= END_US or event["exchange_us"] >= END_US:
            raise ValueError("M023_NATIVE_EVENT_ESCAPED_3H_BOUND")
        yield event


def independent_execution_audit(
    rows: list[dict[str, Any]],
    terminal: dict[str, Any],
    canonical: dict[int, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    state = terminal.get("state")
    if not isinstance(state, dict) or terminal.get("sha256") != canonical_hash(state):
        raise ValueError("M023_AUDIT_TERMINAL_HASH_MISMATCH")
    expected_config = {
        "start_us": START_US,
        "end_us": END_US,
        "latency_us": state.get("config", {}).get("latency_us"),
        "cancel_latency_us": state.get("config", {}).get("cancel_latency_us"),
    }
    if state.get("config") != expected_config:
        raise ValueError("M023_AUDIT_CONFIG_MISMATCH")
    submitted: dict[int, dict[str, Any]] = {}
    activated: dict[int, dict[str, Any]] = {}
    filled: dict[int, D] = {}
    fills_by_trade: dict[str, D] = {}
    queue_by_trade: dict[str, D] = {}
    queue_remaining: dict[int, D] = {}
    delivered: dict[str, dict[str, Any]] = {}
    cancel_acks: dict[int, int] = {}
    max_open = 0
    open_ids: set[int] = set()
    expected_completed_side = "BUY"
    inventory = D0
    inventory_cost = D0
    realized_profit = D0
    realized_by_order: dict[int, D] = {}
    completed_legs = 0
    for row in rows:
        event = row.get("event")
        if event == "SUBMIT":
            order_id = int(row["order_id"])
            if order_id in submitted or D(row["quantity"]) != D("1"):
                raise ValueError("M023_AUDIT_INVALID_SUBMISSION")
            if row["side"] != expected_completed_side or D(row["price"]) <= D0:
                raise ValueError("M023_AUDIT_SUBMISSION_SEQUENCE_DRIFT")
            submitted[order_id] = row
            filled[order_id] = D0
            open_ids.add(order_id)
            max_open = max(max_open, len(open_ids))
            if len(open_ids) > 1:
                raise ValueError("M023_AUDIT_ORDER_CAP_EXCEEDED")
        elif event == "ACTIVATED":
            order_id = int(row["order_id"])
            if order_id not in submitted or order_id in activated:
                raise ValueError("M023_AUDIT_INVALID_ACTIVATION")
            if int(row["time_us"]) < int(submitted[order_id]["time_us"]):
                raise ValueError("M023_AUDIT_PRE_SUBMISSION_ACTIVATION")
            activated[order_id] = row
            queue_remaining[order_id] = D(row["queue"])
        elif event == "FILL":
            order_id = int(row["order_id"])
            if order_id not in submitted or order_id not in activated or D(row["quantity"]) <= D0:
                raise ValueError("M023_AUDIT_FILL_WITHOUT_SUBMISSION")
            if D(row["price"]) != D(submitted[order_id]["price"]):
                raise ValueError("M023_AUDIT_FILL_PRICE_MISMATCH")
            if int(row["time_us"]) < int(activated[order_id]["time_us"]):
                raise ValueError("M023_AUDIT_FILL_BEFORE_ACTIVATION")
            if order_id in cancel_acks and int(row["time_us"]) >= cancel_acks[order_id]:
                raise ValueError("M023_AUDIT_FILL_AFTER_CANCEL_ACK")
            source_id = str(row.get("source_id"))
            trade = canonical.get(int(source_id)) if source_id.isdigit() else None
            activation = activated[order_id]
            if (
                trade is None
                or trade.time_us <= int(activation["time_us"])
                or int(activation["native_book_upper_us"]) > trade.time_us
            ):
                raise ValueError("M023_AUDIT_NONCANONICAL_OR_NONCAUSAL_FILL")
            filled[order_id] += D(row["quantity"])
            if filled[order_id] > D("1"):
                raise ValueError("M023_AUDIT_ORDER_OVERFILLED")
            source = submitted[order_id]
            side = str(row["side"])
            if side != source["side"]:
                raise ValueError("M023_AUDIT_FILL_SIDE_MISMATCH")
            price = D(source["price"])
            quantity = D(row["quantity"])
            eligible = (side == "BUY" and trade.buyer_maker and trade.price <= price) or (
                side == "SELL" and not trade.buyer_maker and trade.price >= price
            )
            if not eligible:
                raise ValueError("M023_AUDIT_FILL_PRINT_INELIGIBLE")
            if trade.price == price and queue_remaining.get(order_id, D0) != D0:
                raise ValueError("M023_AUDIT_EXACT_FILL_BEFORE_QUEUE_DEPLETION")
            fills_by_trade[source_id] = fills_by_trade.get(source_id, D0) + quantity
            if side == "BUY":
                inventory += quantity
                inventory_cost += quantity * price
            else:
                if inventory < quantity or inventory <= D0:
                    raise ValueError("M023_AUDIT_UNBACKED_SELL")
                basis = inventory_cost / inventory
                if quantity * price <= quantity * basis:
                    raise ValueError("M023_AUDIT_NONPOSITIVE_EXIT")
                inventory -= quantity
                inventory_cost -= quantity * basis
                fill_profit = quantity * (price - basis)
                realized_profit += fill_profit
                realized_by_order[order_id] = realized_by_order.get(order_id, D0) + fill_profit
            if filled[order_id] == D("1"):
                open_ids.discard(order_id)
                if side != expected_completed_side:
                    raise ValueError("M023_AUDIT_SEQUENCE_DRIFT")
                expected_completed_side = "SELL" if side == "BUY" else "BUY"
                completed_legs += 1
        elif event == "QUEUE_FLOW":
            order_id = int(row["order_id"])
            source_id = str(row.get("source_id"))
            trade = canonical.get(int(source_id)) if source_id.isdigit() else None
            activation = activated.get(order_id)
            quantity = D(row["quantity"])
            if (
                trade is None
                or activation is None
                or quantity <= D0
                or trade.time_us <= int(activation["time_us"])
                or int(activation["native_book_upper_us"]) > trade.time_us
                or trade.price != D(submitted[order_id]["price"])
                or quantity > queue_remaining.get(order_id, D("-1"))
            ):
                raise ValueError("M023_AUDIT_INVALID_QUEUE_FLOW")
            queue_remaining[order_id] -= quantity
            if D(row["queue_after"]) != queue_remaining[order_id]:
                raise ValueError("M023_AUDIT_QUEUE_TRANSITION_MISMATCH")
            queue_by_trade[source_id] = queue_by_trade.get(source_id, D0) + quantity
        elif event in {"TRADE", "TRADE_BLOCKED_FUTURE_BOOK"}:
            trade_id = str(row["trade_id"])
            if trade_id in delivered:
                raise ValueError("M023_AUDIT_DUPLICATE_TRADE_DELIVERY")
            delivered[trade_id] = row
        elif event == "CANCEL_ACK":
            cancel_acks[int(row["order_id"])] = int(row["time_us"])
            open_ids.discard(int(row["order_id"]))
        elif event.startswith("REJECTED_"):
            open_ids.discard(int(row["order_id"]))
    expected_trade_ids = {str(value) for value in canonical}
    if set(delivered) != expected_trade_ids or set(state["processed_trades"]) != expected_trade_ids:
        raise ValueError("M023_AUDIT_TRADE_COVERAGE_MISMATCH")
    for trade_id, row in delivered.items():
        source = canonical[int(trade_id)]
        if (
            int(row["native_time_us"]) != source.time_us
            or D(row["price"]) != source.price
            or bool(row["buyer_maker"]) != source.buyer_maker
            or D(row["original_quantity"]) != source.quantity
        ):
            raise ValueError("M023_AUDIT_CANONICAL_PRINT_MISMATCH")
        consumed = D(row["consumed_quantity"])
        if consumed < D0 or consumed > source.quantity:
            raise ValueError("M023_AUDIT_GLOBAL_TRADE_BUDGET_EXCEEDED")
        if fills_by_trade.get(trade_id, D0) + queue_by_trade.get(trade_id, D0) != consumed:
            raise ValueError("M023_AUDIT_TRADE_CONSUMPTION_MISMATCH")
    if max_open > 1 or int(metrics.get("max_open", max_open)) > 1:
        raise ValueError("M023_AUDIT_ORDER_CAP_EXCEEDED")
    if len(state.get("buy_deck", [])) != 100 or len(state.get("sell_deck", [])) != 100:
        raise ValueError("M023_AUDIT_RADAR_DECK_SIZE")
    terminal_open = {
        int(order["order_id"])
        for order in state.get("orders", [])
        if order["status"] in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
    }
    if open_ids != terminal_open:
        raise ValueError("M023_AUDIT_OPEN_ORDER_TIMELINE_MISMATCH")
    terminal_orders = {int(order["order_id"]): order for order in state["orders"]}
    if set(terminal_orders) != set(submitted):
        raise ValueError("M023_AUDIT_ORDER_DISAPPEARED")
    for order_id, source in submitted.items():
        terminal_order = terminal_orders[order_id]
        if (
            D(terminal_order["filled"]) != filled[order_id]
            or D(terminal_order["price"]) != D(source["price"])
            or terminal_order["side"] != source["side"]
            or D(terminal_order["quantity"]) != D(source["quantity"])
        ):
            raise ValueError("M023_AUDIT_ORDER_LEDGER_MISMATCH")
    cycle_events = [row for row in rows if row.get("event") == "CYCLE"]
    cycle_rows = len(cycle_events)
    completed_sell_profit = sum(
        (
            realized_by_order.get(order_id, D0)
            for order_id, quantity in filled.items()
            if quantity == D("1") and submitted[order_id]["side"] == "SELL"
        ),
        D0,
    )
    if (
        cycle_rows != completed_legs // 2
        or cycle_rows != int(metrics["total_cycles"])
        or any(row["side"] != "SELL" or D(row["profit"]) <= D0 for row in cycle_events)
        or sum((D(row["profit"]) for row in cycle_events), D0) != completed_sell_profit
    ):
        raise ValueError("M023_AUDIT_CYCLE_COUNT_MISMATCH")
    if D(state["inventory"]) != inventory or D(state["inventory_cost"]) != inventory_cost:
        raise ValueError("M023_AUDIT_INVENTORY_RECONSTRUCTION_MISMATCH")
    if D(state["realized_profit"]) != realized_profit:
        raise ValueError("M023_AUDIT_REALIZED_PROFIT_MISMATCH")
    active_statuses = {"PENDING", "ACTIVE", "CANCEL_PENDING"}
    reserved_quote = sum(
        (
            D(order["reserved_quote"])
            for order in state["orders"]
            if order["status"] in active_statuses
        ),
        D0,
    )
    reconstructed_owned_usdt = INITIAL_CASH - inventory_cost + realized_profit
    if D(state["cash"]) + reserved_quote != reconstructed_owned_usdt:
        raise ValueError("M023_AUDIT_CASH_RECONSTRUCTION_MISMATCH")
    if (
        D(metrics["cash"]) != D(state["cash"])
        or D(metrics["reserved_quote"]) != reserved_quote
        or D(metrics["total_usdt_owned"]) != reconstructed_owned_usdt
        or D(metrics["inventory"]) != inventory
        or D(metrics["inventory_cost"]) != inventory_cost
        or D(metrics["realized_profit"]) != realized_profit
    ):
        raise ValueError("M023_AUDIT_METRIC_FINANCIAL_MISMATCH")
    mark = D(state["last_book"]["bids"][0][0]) if state.get("last_book") else D0
    if D(metrics["marked_equity"]) != reconstructed_owned_usdt + inventory * mark:
        raise ValueError("M023_AUDIT_MARKED_EQUITY_MISMATCH")
    rotations = [row for row in rows if row.get("event") == "RADAR_ROTATION"]
    if len(rotations) != completed_legs or len(rotations) != int(metrics["deck_rotations"]):
        raise ValueError("M023_AUDIT_DECK_ROTATION_MISMATCH")
    if (
        len({card["position"] for card in state["buy_deck"]}) != 100
        or len({card["position"] for card in state["sell_deck"]}) != 100
    ):
        raise ValueError("M023_AUDIT_RADAR_POSITION_DUPLICATION")
    return {
        "status": "PASS_M023_SERIAL_HOT_LINE_LEDGER",
        "submissions": len(submitted),
        "fills": sum(1 for row in rows if row.get("event") == "FILL"),
        "cycles": cycle_rows,
        "completed_legs": completed_legs,
        "deck_rotations": len(rotations),
        "trades_delivered": len(delivered),
        "max_open": max_open,
        "cash_reconciled": True,
        "canonical_fills_reconciled": True,
        "queue_reconciled": True,
    }


def execute(
    engine: SerialHotLinePingPongProbe,
    canonical: dict[int, Any],
    slices: tuple[dict[str, Any], ...],
    identity: dict[str, Any],
    evidence: dict[str, Any],
    output: Path = OUTPUT,
) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise ValueError("EXISTING_M023_EXPERIMENT_PRESERVED")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "run-manifest.json", {**identity, "evidence": evidence})
    seen: set[int] = set()
    for event in bounded_native_events(slices):
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
        native = event["data"]
        trade = canonical.get(native["t"])
        if trade is None or trade.trade_id in seen:
            raise ValueError("M023_CANONICAL_TRADE_BINDING_CHANGED")
        consumed = engine.receive_trade(trade, capture_time_us=event["local_us"])
        if consumed < D0 or consumed > trade.quantity:
            raise ValueError("M023_GLOBAL_TRADE_BUDGET_EXCEEDED")
        seen.add(trade.trade_id)
    if seen != set(canonical):
        raise ValueError("M023_CANONICAL_3H_NOT_FULLY_DELIVERED")
    metrics = engine.finish(time_us=END_US)
    terminal = engine.checkpoint()
    audit = independent_execution_audit(engine.audit, terminal, canonical, metrics)
    audit_file = output / "execution-audit.jsonl"
    audit_file.write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in engine.audit),
        encoding="utf-8",
    )
    result = {
        **identity,
        "DISCLAIMER": engine.normalized_label,
        "RUN_STATUS": "COMPLETE",
        "VERDICT": "M023_MECHANICS_MEASURED_NOT_STRATEGY_APPROVAL",
        "MODEL": MODEL_ID,
        "PERIOD": "3H",
        "TOTAL_COMPLETE_POSITIVE_BUY_SELL_CYCLES": metrics["total_cycles"],
        "CYCLES_PER_HOUR": metrics["cycles_per_hour"],
        "METRICS": metrics,
        "AUDIT": {**audit, "terminal_sha256": terminal["sha256"]},
        "AUDIT_FILE": str(audit_file),
    }
    write_json(output / "summary.json", result)
    write_json(output / "terminal-engine-state.json", terminal)
    write_json(output / "all-fill-audit.json", result["AUDIT"])
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
        "order_notional_mode": "NORMALIZED_1_USDC_NON_EXECUTABLE_SERIAL_HOT_LINE",
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
    engine = SerialHotLinePingPongProbe(
        start_us=START_US,
        end_us=END_US,
        latency_us=profile.latency_us,
        cancel_latency_us=profile.cancel_latency_us,
    )
    with campaign_writer_lock():
        return execute(engine, canonical, slices, identity, evidence)


__all__ = [
    "END_US",
    "MODEL_ID",
    "OUTPUT",
    "RESULT",
    "START_US",
    "bounded_inputs",
    "bounded_native_events",
    "campaign_preflight",
    "execute",
    "independent_execution_audit",
    "require_owner_gate",
    "run",
    "validate_frozen_design",
]


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, default=str))
