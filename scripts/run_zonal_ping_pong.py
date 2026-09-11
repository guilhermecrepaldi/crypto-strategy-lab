"""Published offline M020 five-hour fixed-zone throughput runner."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.b10_reality import ExecutionProfile, Trade
from crypto_strategy_lab.microstructure.data import (
    HistoryManifest,
    iter_history,
    select_history_archives,
)
from crypto_strategy_lab.microstructure.recovery_reserve_study import (
    file_sha,
    published_sha,
    write_json,
)
from crypto_strategy_lab.microstructure.serial_replay import _datetime_to_micros
from crypto_strategy_lab.microstructure.tardis_l2 import iter_native_events
from crypto_strategy_lab.microstructure.zonal_ping_pong import ZonalBand, ZonalPingPong
from crypto_strategy_lab.ml.model_registry import ModelRegistry, compute_model_hash
from scripts.run_b10_reality import typed
from scripts.run_high_uptime_recovery import (
    PROFILE,
    PROFILE_CONFIG,
    PROFILE_CONFIG_SHA,
    campaign_writer_lock,
    lf_sha,
    published_bytes,
    validate_review,
)
from scripts.run_l2_monthly_samples import json_hash, verify_published_day_evidence
from scripts.validate_tardis_l2_samples import (
    MANIFEST,
    TRADE_MANIFEST,
    checked_path,
    raw_lines,
    trade_timestamp_matches,
    validate_slice_metadata,
)
from scripts.validate_tardis_l2_samples import (
    OUTPUT as VALIDATION_REPORT,
)

D = Decimal
ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "M020"
SOURCE_DAY = "2025-01-01"
START = datetime(2025, 1, 1, tzinfo=UTC)
END = datetime(2025, 1, 1, 5, tzinfo=UTC)
START_US = _datetime_to_micros(START)
END_US = _datetime_to_micros(END)
OWNER_WINDOW = Path("docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md")
OWNER_DIRECTIVE = Path("docs/microstructure/STABLECOIN_ZONAL_PING_PONG_OWNER_DIRECTIVE.md")
SPEC = Path("docs/microstructure/M020_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M020_ZONAL_PING_PONG_PREREGISTRATION.md")
REVIEW = Path("reports/usdcusdt/M020-preflight-independent-review.md")
JOURNAL = Path("docs/research/M020_JOURNAL.md")
OCCUPANCY = Path("reports/usdcusdt/M020-price-occupancy-2025.json")
OUTPUT = Path("artifacts/usdcusdt/l2-monthly-samples/M020/OWNER_GATED_5H/PRICE_PRIORITY")
RESULT = Path("reports/usdcusdt/M020-5h-result.json")
SOURCE_PATHS = (
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
    Path("tests/test_zonal_ping_pong.py"),
    Path("tests/test_run_zonal_ping_pong.py"),
)


def fixed_bands() -> tuple[ZonalBand, ...]:
    edges = [D("0.9994") + D(index) * D("0.0001") for index in range(10)]
    return tuple(
        ZonalBand(
            band_id=f"Z{index + 1:03d}",
            price_low=edges[index],
            price_high=edges[index + 1],
            buy_price=edges[index],
            sell_price=edges[index + 1],
            buy_capacity=D(1),
            sell_capacity=D(1),
        )
        for index in range(9)
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
            raise ValueError(f"M020_OWNER_GATE_REQUIRED:{key}")


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


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
        raise ValueError("M020_REQUIRES_PUBLISHED_HEAD")
    for path in (
        *SOURCE_PATHS,
        OWNER_DIRECTIVE,
        OWNER_WINDOW,
        SPEC,
        PREREG,
        REVIEW,
        JOURNAL,
        OCCUPANCY,
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
    occupancy = json.loads(OCCUPANCY.read_bytes())
    expected_model = {
        **design,
        "spec_sha256_lf": lf_sha(SPEC),
        "preregistration_sha256_lf": lf_sha(PREREG),
        "owner_directive_sha256_lf": lf_sha(OWNER_DIRECTIVE),
        "occupancy_sha256_lf": lf_sha(OCCUPANCY),
    }
    model = ModelRegistry().get(MODEL_ID)
    if dict(model.model) != expected_model or model.model_hash != compute_model_hash(
        expected_model
    ):
        raise ValueError("M020_REGISTERED_DESIGN_MISMATCH")
    if (
        design["start"] != "2025-01-01T00:00:00Z"
        or design["end_exclusive"] != "2025-01-01T05:00:00Z"
        or design["physical_band_count"] != 9
        or design["normalized_quantity"] != "1"
        or design["virtual_filter_override"] != "MIN_NOTIONAL_ONLY"
        or design["day2_authorized"] is not False
    ):
        raise ValueError("M020_FROZEN_INVARIANT_MISMATCH")
    if (
        occupancy["ranges"]["P80"]["low"] != "0.99940"
        or occupancy["ranges"]["P80"]["high"] != "1.00030"
        or occupancy["history_manifest_dataset_hash"]
        != "8cb436b68d6953573d8e7e5dc89eaf53e344e46bde18ce749b440abdd757dd91"
    ):
        raise ValueError("M020_OCCUPANCY_BINDING_CHANGED")
    manifest = json.loads(MANIFEST.read_bytes())
    validation = json.loads(VALIDATION_REPORT.read_bytes())
    return sha, manifest, validation


def bounded_inputs(
    manifest: dict[str, Any], validation: dict[str, Any]
) -> tuple[ExecutionProfile, dict[int, Trade], tuple[dict[str, Any], ...], dict[str, Any]]:
    trade_manifest = json.loads(TRADE_MANIFEST.read_bytes())
    entry = next(item for item in manifest["dates"] if item["date"] == SOURCE_DAY)
    checked = next(item for item in validation["days"] if item["date"] == SOURCE_DAY)
    verified = verify_published_day_evidence(entry, checked, trade_manifest)
    slices = tuple(
        sorted(
            (item for item in entry["raw_slices"] if item["offset"] < 300),
            key=lambda item: item["offset"],
        )
    )
    if len(slices) != 30 or tuple(item["offset"] for item in slices) != tuple(range(0, 300, 10)):
        raise ValueError("M020_EXACT_FIRST_30_SLICES_REQUIRED")
    for item in slices:
        validate_slice_metadata(SOURCE_DAY, item)
        path = checked_path(ROOT, item["local_path"], SOURCE_DAY, raw=True)
        if path.stat().st_size != item["bytes"] or file_sha(path) != item["sha256"]:
            raise ValueError("M020_BOUNDED_NATIVE_EVIDENCE_CHANGED")

    history = HistoryManifest.model_validate_json(TRADE_MANIFEST.read_bytes())
    read_start = max(START, history.first_timestamp)
    selected = select_history_archives(history, start=read_start, end_exclusive=END)
    if len(selected) != 1 or selected[0].cadence != "daily":
        raise ValueError("M020_EXACT_DAILY_TRADE_ARCHIVE_REQUIRED")
    if file_sha(Path(selected[0].local_path)) != selected[0].sha256:
        raise ValueError("M020_CANONICAL_ARCHIVE_CHANGED")
    canonical: dict[int, Trade] = {}
    for event in iter_history(history, start=read_start, end_exclusive=END):
        if event.trade_id in canonical:
            raise ValueError("M020_DUPLICATE_CANONICAL_TRADE")
        canonical[event.trade_id] = Trade(
            _datetime_to_micros(event.timestamp),
            event.trade_id,
            event.price,
            event.quantity,
            event.buyer_is_maker,
        )
    config = json.loads(PROFILE_CONFIG.read_bytes())
    profile_row = next(row for row in config["profiles"] if row["profile"]["name"] == PROFILE)
    profile = typed(ExecutionProfile, profile_row["profile"])
    evidence = {
        "validation": verified,
        "bounded_slice_count": len(slices),
        "bounded_slice_offsets": [item["offset"] for item in slices],
        "bounded_slice_sha256": hashlib.sha256(
            "\n".join(f"{item['offset']}:{item['sha256']}" for item in slices).encode()
        ).hexdigest(),
        "canonical_trade_count": len(canonical),
        "canonical_first_trade_id": min(canonical),
        "canonical_last_trade_id": max(canonical),
    }
    return profile, canonical, slices, evidence


def bounded_native_events(slices: tuple[dict[str, Any], ...]):
    for event in iter_native_events(raw_lines(ROOT, SOURCE_DAY, slices)):
        if event["local_us"] >= END_US or event["exchange_us"] >= END_US:
            raise ValueError("M020_NATIVE_EVENT_ESCAPED_5H_BOUND")
        yield event


def _band_for_price(price: D, bands: tuple[ZonalBand, ...]) -> str | None:
    for index, band in enumerate(bands):
        if band.price_low <= price < band.price_high or (
            index == len(bands) - 1 and price == band.price_high
        ):
            return band.band_id
    return None


def band_occupancy(canonical: dict[int, Trade], bands: tuple[ZonalBand, ...]) -> dict[str, Any]:
    rows = sorted(canonical.values(), key=lambda item: (item.time_us, item.trade_id))
    duration: Counter[str] = Counter()
    trades: Counter[str] = Counter()
    volume: dict[str, D] = {band.band_id: D(0) for band in bands}
    previous: Trade | None = None
    for trade in rows:
        if previous is not None:
            band_id = _band_for_price(previous.price, bands)
            if band_id is not None:
                duration[band_id] += trade.time_us - previous.time_us
        band_id = _band_for_price(trade.price, bands)
        if band_id is not None:
            trades[band_id] += 1
            volume[band_id] += trade.quantity
        previous = trade
    if previous is not None:
        band_id = _band_for_price(previous.price, bands)
        if band_id is not None:
            duration[band_id] += END_US - previous.time_us
    return {
        band.band_id: {
            "TIME_PRICE_INSIDE_BAND_US": duration[band.band_id],
            "PERCENT_OF_5H_INSIDE_BAND": str(
                D(duration[band.band_id]) / D(END_US - START_US) * D(100)
            ),
            "TRADES_INSIDE_BAND": trades[band.band_id],
            "TOTAL_VOLUME_INSIDE_BAND": str(volume[band.band_id]),
        }
        for band in bands
    }


def _audit_rows(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with path.open("wb") as stream:
        for row in rows:
            line = json.dumps(row, sort_keys=True, default=str).encode() + b"\n"
            stream.write(line)
            digest.update(line)
    return {"rows": len(rows), "sha256": digest.hexdigest()}


def independent_execution_audit(
    rows: list[dict[str, Any]],
    terminal: dict[str, Any],
    canonical_trades: dict[str, Trade],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """Independently reconcile execution, liquidity, cycles, and ownership."""
    state = terminal.get("state")
    if not isinstance(state, dict) or terminal.get("sha256") != canonical_hash(state):
        raise ValueError("M020_AUDIT_TERMINAL_HASH_MISMATCH")

    submissions: dict[int, dict[str, Any]] = {}
    activations: dict[int, dict[str, Any]] = {}
    cancel_acks: dict[int, int] = {}
    terminal_trades: dict[str, dict[str, Any]] = {}
    fills: list[dict[str, Any]] = []
    queue_flows: list[dict[str, Any]] = []
    cycles: list[dict[str, Any]] = []
    endowments: list[dict[str, Any]] = []
    for row in rows:
        event = row.get("event")
        if event == "SUBMIT":
            order_id = int(row["order_id"])
            if order_id in submissions or D(row["quantity"]) <= 0 or D(row["price"]) <= 0:
                raise ValueError("M020_AUDIT_INVALID_OR_DUPLICATE_SUBMISSION")
            submissions[order_id] = row
        elif event == "ACTIVATED":
            order_id = int(row["order_id"])
            if order_id not in submissions or order_id in activations:
                raise ValueError("M020_AUDIT_INVALID_ACTIVATION")
            if int(row["time_us"]) < int(submissions[order_id]["time_us"]):
                raise ValueError("M020_AUDIT_PRE_SUBMISSION_ACTIVATION")
            activations[order_id] = row
        elif event == "CANCEL_ACK":
            cancel_acks[int(row["order_id"])] = int(row["time_us"])
        elif event == "FILL":
            fills.append(row)
        elif event == "QUEUE_FLOW":
            queue_flows.append(row)
        elif event in {"TRADE", "TRADE_BLOCKED_FUTURE_BOOK"}:
            trade_id = str(row["trade_id"])
            if trade_id in terminal_trades:
                raise ValueError("M020_AUDIT_DUPLICATE_TRADE_DELIVERY")
            terminal_trades[trade_id] = row
        elif event == "CYCLE":
            cycles.append(row)
        elif event == "ENDOWMENT":
            endowments.append(row)

    expected_trade_ids = set(canonical_trades)
    if set(terminal_trades) != expected_trade_ids:
        raise ValueError("M020_AUDIT_TRADE_COVERAGE_MISMATCH")
    if set(state["processed_trades"]) != expected_trade_ids:
        raise ValueError("M020_AUDIT_ENGINE_TRADE_COVERAGE_MISMATCH")
    fill_by_order: Counter[int] = Counter()
    fill_by_trade: dict[str, D] = {}
    for row in fills:
        order_id = int(row["order_id"])
        if order_id not in submissions or order_id not in activations:
            raise ValueError("M020_AUDIT_FILL_WITHOUT_ACTIVATION")
        if row["side"] != submissions[order_id]["side"]:
            raise ValueError("M020_AUDIT_FILL_SIDE_MISMATCH")
        if D(row["price"]) != D(submissions[order_id]["price"]):
            raise ValueError("M020_AUDIT_FILL_PRICE_NOT_RESTING_LIMIT")
        if int(row["time_us"]) < int(activations[order_id]["time_us"]):
            raise ValueError("M020_AUDIT_FILL_BEFORE_ACTIVATION")
        if order_id in cancel_acks and int(row["time_us"]) >= cancel_acks[order_id]:
            raise ValueError("M020_AUDIT_FILL_AFTER_CANCEL_ACK")
        quantity = D(row["quantity"])
        if quantity <= 0:
            raise ValueError("M020_AUDIT_NONPOSITIVE_FILL")
        fill_by_order[order_id] += quantity
        source_id = str(row["source_id"])
        trade = canonical_trades.get(source_id)
        activation = activations[order_id]
        if trade is None or trade.time_us <= int(activation["time_us"]):
            raise ValueError("M020_AUDIT_NONCAUSAL_NATIVE_FILL")
        if int(activation["native_book_upper_us"]) > trade.time_us:
            raise ValueError("M020_AUDIT_FILL_USES_FUTURE_BOOK")
        trade_price = D(trade.price)
        if row["side"] == "BUY":
            eligible = trade.buyer_maker and trade_price <= D(row["price"])
        else:
            eligible = not trade.buyer_maker and trade_price >= D(row["price"])
        if not eligible:
            raise ValueError("M020_AUDIT_FILL_PRINT_INELIGIBLE")
        fill_by_trade[source_id] = fill_by_trade.get(source_id, D(0)) + quantity
        if row["side"] == "SELL" and D(row["realized_profit"]) <= 0:
            raise ValueError("M020_AUDIT_NONPOSITIVE_SELL_EXIT")

    for order_id, quantity in fill_by_order.items():
        if quantity > D(submissions[order_id]["quantity"]):
            raise ValueError("M020_AUDIT_ORDER_OVERFILL")
    terminal_orders = {int(order["order_id"]): order for order in state["orders"]}
    for order_id, submission in submissions.items():
        terminal_order = terminal_orders.get(order_id)
        if terminal_order is None:
            raise ValueError("M020_AUDIT_ORDER_DISAPPEARED")
        if fill_by_order.get(order_id, D(0)) != D(terminal_order["filled"]):
            raise ValueError("M020_AUDIT_ORDER_FILL_LEDGER_MISMATCH")
        if D(terminal_order["quantity"]) != D(submission["quantity"]):
            raise ValueError("M020_AUDIT_ORDER_QUANTITY_MUTATED")
    queue_by_trade: dict[str, D] = {}
    queue_remaining: dict[int, D] = {}
    for row in rows:
        event = row.get("event")
        if event == "ACTIVATED":
            queue_remaining[int(row["order_id"])] = D(row["queue"])
        elif event == "QUEUE_FLOW":
            order_id = int(row["order_id"])
            source_id = str(row["source_id"])
            quantity = D(row["quantity"])
            trade = canonical_trades.get(source_id)
            activation = activations.get(order_id)
            if trade is None or activation is None or quantity <= 0:
                raise ValueError("M020_AUDIT_INVALID_QUEUE_FLOW")
            if trade.time_us <= int(activation["time_us"]):
                raise ValueError("M020_AUDIT_NONCAUSAL_QUEUE_FLOW")
            if int(activation["native_book_upper_us"]) > trade.time_us:
                raise ValueError("M020_AUDIT_QUEUE_USES_FUTURE_BOOK")
            if D(trade.price) != D(submissions[order_id]["price"]):
                raise ValueError("M020_AUDIT_QUEUE_FLOW_NOT_EXACT_LEVEL")
            if quantity > queue_remaining.get(order_id, D(-1)):
                raise ValueError("M020_AUDIT_QUEUE_OVERCONSUMED")
            queue_remaining[order_id] -= quantity
            if D(row["queue_after"]) != queue_remaining[order_id]:
                raise ValueError("M020_AUDIT_QUEUE_TRANSITION_MISMATCH")
            queue_by_trade[source_id] = queue_by_trade.get(source_id, D(0)) + quantity
        elif event == "FILL":
            order_id = int(row["order_id"])
            trade = canonical_trades.get(str(row["source_id"]))
            if (
                trade is not None
                and D(trade.price) == D(row["price"])
                and queue_remaining.get(order_id, D(0)) != 0
            ):
                raise ValueError("M020_AUDIT_EXACT_FILL_BEFORE_QUEUE_DEPLETION")

    for trade_id, quantity in fill_by_trade.items():
        trade = terminal_trades.get(trade_id)
        if trade is None or trade["event"] != "TRADE":
            raise ValueError("M020_AUDIT_FILL_WITHOUT_USABLE_TRADE")
        if quantity > D(trade["consumed_quantity"]):
            raise ValueError("M020_AUDIT_FILL_EXCEEDS_CONSUMED_LIQUIDITY")
    for row in terminal_trades.values():
        trade_id = str(row["trade_id"])
        canonical = canonical_trades[trade_id]
        if (
            int(row["native_time_us"]) != canonical.time_us
            or D(row["price"]) != D(canonical.price)
            or bool(row["buyer_maker"]) != canonical.buyer_maker
            or D(row["original_quantity"]) != D(canonical.quantity)
        ):
            raise ValueError("M020_AUDIT_CANONICAL_PRINT_MISMATCH")
        original = D(row["original_quantity"])
        consumed = D(row["consumed_quantity"])
        if original < 0 or consumed < 0 or consumed > original:
            raise ValueError("M020_AUDIT_GLOBAL_LIQUIDITY_OVERCONSUMED")
        if fill_by_trade.get(trade_id, D(0)) + queue_by_trade.get(trade_id, D(0)) != consumed:
            raise ValueError("M020_AUDIT_TRADE_CONSUMPTION_LEDGER_MISMATCH")

    cycle_keys: set[tuple[str, int]] = set()
    for row in cycles:
        key = (str(row["direction"]), int(row["source_order_id"]))
        if key in cycle_keys or D(row["profit"]) <= 0:
            raise ValueError("M020_AUDIT_INVALID_OR_DUPLICATE_CYCLE")
        cycle_keys.add(key)
        source = submissions.get(key[1])
        if source is None or source["side"] != "BUY":
            raise ValueError("M020_AUDIT_CYCLE_WITHOUT_BUY_SEQUENCE")
        if fill_by_order.get(key[1], D(0)) != D(source["quantity"]):
            raise ValueError("M020_AUDIT_CYCLE_WITHOUT_FULL_ENTRY_OR_REENTRY")
        cycle_quantity = D(row["quantity"])
        if key[0] == "BUY_SELL":
            linked_fills = [
                fill
                for fill in fills
                if fill["side"] == "SELL" and key[1] in fill.get("economic_source_order_ids", [])
            ]
            linked_exit = sum(
                (D(fill["quantity"]) for fill in linked_fills),
                D(0),
            )
            if linked_exit != cycle_quantity or linked_exit != D(source["quantity"]):
                raise ValueError("M020_AUDIT_BUY_SELL_LINK_MISMATCH")
            if sum((D(fill["realized_profit"]) for fill in linked_fills), D(0)) != D(row["profit"]):
                raise ValueError("M020_AUDIT_BUY_SELL_PROFIT_MISMATCH")
        elif key[0] == "SELL_BUY":
            entry_sell_id = row.get("entry_sell_order_id")
            entry_sell = submissions.get(int(entry_sell_id)) if entry_sell_id is not None else None
            if (
                entry_sell is None
                or entry_sell["side"] != "SELL"
                or entry_sell["band_id"] != source["band_id"]
                or fill_by_order.get(int(entry_sell_id), D(0)) != cycle_quantity
                or D(source["quantity"]) != cycle_quantity
            ):
                raise ValueError("M020_AUDIT_SELL_BUY_LINK_MISMATCH")
            sale_proceeds = sum(
                (
                    D(fill["quantity"]) * D(fill["price"])
                    for fill in fills
                    if int(fill["order_id"]) == int(entry_sell_id)
                ),
                D(0),
            )
            reentry_cost = sum(
                (
                    D(fill["quantity"]) * D(fill["price"])
                    for fill in fills
                    if int(fill["order_id"]) == key[1]
                ),
                D(0),
            )
            if sale_proceeds - reentry_cost != D(row["profit"]):
                raise ValueError("M020_AUDIT_SELL_BUY_PROFIT_MISMATCH")
        else:
            raise ValueError("M020_AUDIT_UNKNOWN_CYCLE_DIRECTION")
    if len(cycles) != int(metrics["total_positive_cycles"]):
        raise ValueError("M020_AUDIT_CYCLE_COUNT_MISMATCH")

    active_statuses = {"PENDING", "ACTIVE", "CANCEL_PENDING"}
    reserved_quote = sum(
        (
            D(order["reserved_quote"])
            for order in state["orders"]
            if order["status"] in active_statuses
        ),
        D(0),
    )
    cash = D(state["cash"])
    inventory = D(state["inventory"])
    inventory_cost = D(state["inventory_cost"])
    realized_profit = D(state["realized_profit"])
    reentry_escrow = sum((D(value) for value in state["sell_proceeds"].values()), D(0))
    if cash + reserved_quote + reentry_escrow + inventory_cost - realized_profit != D(
        state["config"]["initial_capital"]
    ):
        raise ValueError("M020_AUDIT_CAPITAL_OWNERSHIP_DRIFT")

    if len(endowments) != 1:
        raise ValueError("M020_AUDIT_ENDOWMENT_COUNT_MISMATCH")
    endowment = endowments[0]
    reconstructed_inventory = D(endowment["quantity"])
    reconstructed_cost = D(endowment["quantity"]) * D(endowment["bid"])
    reconstructed_liquid_usdt = D(state["config"]["initial_capital"]) - reconstructed_cost
    reconstructed_realized = D(0)
    for fill in fills:
        quantity = D(fill["quantity"])
        proceeds_or_cost = quantity * D(fill["price"])
        if fill["side"] == "BUY":
            reconstructed_inventory += quantity
            reconstructed_cost += proceeds_or_cost
            reconstructed_liquid_usdt -= proceeds_or_cost
        else:
            fill_profit = D(fill["realized_profit"])
            reconstructed_inventory -= quantity
            reconstructed_cost -= proceeds_or_cost - fill_profit
            reconstructed_liquid_usdt += proceeds_or_cost
            reconstructed_realized += fill_profit
    if (
        reconstructed_inventory != inventory
        or reconstructed_cost != inventory_cost
        or reconstructed_realized != realized_profit
        or reconstructed_liquid_usdt != cash + reserved_quote + reentry_escrow
    ):
        raise ValueError("M020_AUDIT_FILL_BASED_FINANCIAL_RECONCILIATION_FAILED")
    lots_inventory = D(state["endowment_free_quantity"]) + sum(
        (D(lot["remaining"]) for lot in state["lots"]), D(0)
    )
    lots_cost = D(state["endowment_cost"]) + sum(
        (D(lot["remaining_cost"]) for lot in state["lots"]), D(0)
    )
    if lots_inventory != inventory or lots_cost != inventory_cost:
        raise ValueError("M020_AUDIT_INVENTORY_OWNERSHIP_DRIFT")
    if D(metrics["usdt_final"]) != cash + reserved_quote + reentry_escrow:
        raise ValueError("M020_AUDIT_METRIC_CASH_MISMATCH")
    if D(metrics["realized_profit"]) != reconstructed_realized:
        raise ValueError("M020_AUDIT_METRIC_REALIZED_PNL_MISMATCH")
    if D(state["roundtrip_profit"]) != sum(
        (D(row["profit"]) for row in cycles if row["direction"] == "SELL_BUY"), D(0)
    ):
        raise ValueError("M020_AUDIT_ROUNDTRIP_PROFIT_MISMATCH")
    if not state.get("finished") or int(state["config"]["end_us"]) != END_US:
        raise ValueError("M020_AUDIT_CUTOFF_OR_FINISH_MISMATCH")
    return {
        "status": "PASS_M020_LEDGER_EXECUTION_LIQUIDITY",
        "submitted_orders": len(submissions),
        "fills": len(fills),
        "cycles": len(cycles),
        "trade_deliveries": len(terminal_trades),
        "ownership_reconciled": True,
        "global_liquidity_reconciled": True,
        "queue_reconciled": True,
        "native_causality_reconciled": True,
        "negative_exits": 0,
    }


def execute(
    engine: ZonalPingPong,
    canonical: dict[int, Trade],
    slices: tuple[dict[str, Any], ...],
    identity: dict[str, Any],
    evidence: dict[str, Any],
    output: Path = OUTPUT,
) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise ValueError("EXISTING_M020_EXPERIMENT_PRESERVED")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "run-manifest.json", identity)
    seen: set[int] = set()
    event_count = 0
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
                raise ValueError("M020_UNBOUND_INTERIOR_NATIVE_TRADE")
            if trade.trade_id in seen or not trade_timestamp_matches(trade.time_us, native["T"]):
                raise ValueError("M020_CANONICAL_TRADE_BINDING_CHANGED")
            if (trade.price, trade.quantity, trade.buyer_maker) != (
                D(native["p"]),
                D(native["q"]),
                native["m"],
            ):
                raise ValueError("M020_CANONICAL_TRADE_FIELDS_CHANGED")
            consumed = engine.receive_trade(trade, capture_time_us=event["local_us"])
            if consumed < 0 or consumed > trade.quantity:
                raise ValueError("M020_GLOBAL_TRADE_BUDGET_EXCEEDED")
            seen.add(trade.trade_id)
        if event_count % 50_000 == 0:
            engine.validate_invariants()
    if seen != set(canonical):
        raise ValueError("M020_CANONICAL_5H_NOT_FULLY_DELIVERED")
    engine.finish(time_us=END_US)
    engine.validate_invariants()

    metrics = engine.metrics()
    terminal = engine.checkpoint()
    audit_validation = independent_execution_audit(
        engine.audit,
        terminal,
        {str(trade_id): trade for trade_id, trade in canonical.items()},
        metrics,
    )
    audit_file = _audit_rows(output / "execution-audit.jsonl", engine.audit)
    audit = {**audit_validation, "file": audit_file}
    bands = fixed_bands()
    occupancy = band_occupancy(canonical, bands)
    cycles_by_band = {
        band.band_id: int(metrics.get("cycles_by_band", {}).get(band.band_id, 0)) for band in bands
    }
    total = int(metrics["total_positive_cycles"])
    all_bands = []
    submitted_by_band = Counter(row["band_id"] for row in engine.audit if row["event"] == "SUBMIT")
    fills_by_band = Counter(row["band_id"] for row in engine.audit if row["event"] == "FILL")
    canceled_by_band = Counter(
        next(order.band_id for order in engine.orders if order.order_id == row["order_id"])
        for row in engine.audit
        if row["event"] == "CANCEL_ACK"
    )
    repositioned_by_band: Counter[str] = Counter()
    awaiting_reposition: set[str] = set()
    order_band = {order.order_id: order.band_id for order in engine.orders}
    for row in engine.audit:
        if row["event"] == "CANCEL_ACK":
            awaiting_reposition.add(order_band[int(row["order_id"])])
        elif row["event"] == "SUBMIT" and row["band_id"] in awaiting_reposition:
            repositioned_by_band[row["band_id"]] += 1
            awaiting_reposition.remove(row["band_id"])
    for band in bands:
        cycles = cycles_by_band[band.band_id]
        all_bands.append(
            {
                "BAND": band.band_id,
                "PRICE_LOW": str(band.price_low),
                "PRICE_HIGH": str(band.price_high),
                "CYCLES": cycles,
                "SHARE_OF_TOTAL": str(D(cycles) / D(total)) if total else "0",
                "ORDERS_SUBMITTED": submitted_by_band[band.band_id],
                "FILLS": fills_by_band[band.band_id],
                "ORDERS_CANCELED": canceled_by_band[band.band_id],
                "ORDERS_REPOSITIONED": repositioned_by_band[band.band_id],
                "OPEN_USDC": str(
                    sum(
                        (lot.remaining for lot in engine.lots if lot.band_id == band.band_id),
                        D(0),
                    )
                ),
                "STATE": metrics["band_states"][band.band_id],
                **occupancy[band.band_id],
            }
        )
    ranking = sorted(all_bands, key=lambda row: (-row["CYCLES"], row["BAND"]))
    top5 = ranking[:5]
    top_counts = [row["CYCLES"] for row in top5]
    bands_for_80 = 0
    if total:
        running = 0
        for row in ranking:
            bands_for_80 += 1
            running += row["CYCLES"]
            if D(running) / D(total) >= D("0.8"):
                break
    if sum(row["TIME_PRICE_INSIDE_BAND_US"] for row in all_bands) == 0:
        limiter = "PRICE_OUTSIDE_FIXED_P80_MAP"
    else:
        limiter = "UNDETERMINED_PENDING_POST_RUN_AUTOPSY"
    result = {
        **identity,
        "DISCLAIMER": ZonalPingPong.normalized_label,
        "RUN_STATUS": "COMPLETE",
        "VERDICT": "THROUGHPUT_MEASURED_NOT_STRATEGY_APPROVAL",
        "MODEL": MODEL_ID,
        "PERIOD": "5H",
        "TOTAL_COMPLETE_CYCLES": int(metrics["total_cycles"]),
        "TOTAL_POSITIVE_CYCLES": total,
        "BUY_SELL_POSITIVE_CYCLES": int(metrics.get("cycles_by_direction", {}).get("BUY_SELL", 0)),
        "SELL_BUY_POSITIVE_CYCLES": int(metrics.get("cycles_by_direction", {}).get("SELL_BUY", 0)),
        "CYCLES_PER_HOUR": metrics["cycles_per_hour"],
        "TOP_5_BANDS": [
            {"RANK": index + 1, "BAND": row["BAND"], "CYCLES": row["CYCLES"]}
            for index, row in enumerate(top5)
        ],
        "ALL_BANDS": all_bands,
        "USDT_FINAL": metrics["usdt_final"],
        "USDC_FINAL": metrics["usdc_final"],
        "TOTAL_MARKED_EQUITY": metrics["total_marked_equity"],
        "REALIZED_NET_PNL": metrics.get("realized_profit", "0"),
        "ROUNDTRIP_CYCLE_PROFIT": metrics.get("roundtrip_profit", "0"),
        "REENTRY_ESCROW_FINAL": metrics.get("reentry_escrow", "0"),
        "UNREALIZED_PNL": metrics.get("unrealized_pnl", "0"),
        "ACTIVE_BANDS": metrics["active_bands"],
        "DORMANT_BANDS": metrics["dormant_bands"],
        "TOP_BAND_SHARE": str(D(top_counts[0]) / D(total)) if total else "0",
        "TOP_3_SHARE": str(D(sum(top_counts[:3])) / D(total)) if total else "0",
        "TOP_5_SHARE": str(D(sum(top_counts)) / D(total)) if total else "0",
        "PERCENT_BANDS_RESPONSIBLE_FOR_80_PERCENT_CYCLES": str(
            D(bands_for_80) / D(len(bands)) * D(100)
        )
        if total
        else "0",
        "MAIN_LIMITER": limiter,
        "ORDERS_CANCELED": metrics["orders_canceled"],
        "ORDERS_REPOSITIONED": sum(repositioned_by_band.values()),
        "WINDOW_UNDERSUPPORTED": metrics["window_unsupported"],
        "QUEUE_BLOCKED_FILLS": int(metrics.get("queue_blocked_events", 0)),
        "EXACT_LEVEL_FILLS": int(metrics.get("exact_fill_events", 0)),
        "TRADE_THROUGH_FILLS": int(metrics.get("trade_through_fill_events", 0)),
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
        "order_notional_mode": "NORMALIZED_1_USDT_NON_EXECUTABLE",
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
        "occupancy_sha256_lf": lf_sha(OCCUPANCY),
        "data_manifest_sha256": file_sha(MANIFEST),
        "priority_trade_through": True,
        "cutoff_liquidation": False,
        "day2_authorized": False,
    }
    identity["run_hash"] = json_hash(identity)
    engine = ZonalPingPong(
        fixed_bands(),
        start_us=START_US,
        end_us=END_US,
        latency_us=profile.latency_us,
        cancel_latency_us=profile.cancel_latency_us,
    )
    with campaign_writer_lock():
        return execute(engine, canonical, slices, identity, evidence)


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
