"""Published, offline monthly L2 runner. Never downloads or accesses accounts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from crypto_strategy_lab.microstructure.adaptive_stablecoin_ladder import (
    AdaptiveStablecoinLadder,
)
from crypto_strategy_lab.microstructure.b10_reality import (
    BookEnvelope,
    ExecutionProfile,
    SymbolRules,
    Trade,
)
from crypto_strategy_lab.microstructure.data import (
    HistoryManifest,
    iter_history,
    select_history_archives,
)
from crypto_strategy_lab.microstructure.high_uptime_recovery import DEADLINE_POLICY_HASHES
from crypto_strategy_lab.microstructure.observed_l2_execution import (
    ObservedBookBatch,
    ObservedL2Replay,
)
from crypto_strategy_lab.microstructure.operator import frozen_m007_strategy
from crypto_strategy_lab.microstructure.recovery_reserve import (
    RecoveryReserveRuntime,
    ReserveConfig,
)
from crypto_strategy_lab.microstructure.recovery_reserve_study import (
    file_sha,
    published_sha,
    write_json,
)
from crypto_strategy_lab.microstructure.serial_replay import (
    USDCUSDT_TICK_CATALOG,
    SerialScenarioConfig,
    SerialTape,
    TickCatalog,
    TickPeriod,
    TickTransition,
    _datetime_to_micros,
)
from crypto_strategy_lab.microstructure.tardis_l2 import iter_native_events
from crypto_strategy_lab.ml.model_registry import ModelRegistry, compute_model_hash
from scripts.run_b10_reality import AuditJournal, typed
from scripts.run_high_uptime_recovery import (
    PROFILE,
    PROFILE_CONFIG,
    PROFILE_CONFIG_SHA,
    SPEC,
    campaign_writer_lock,
    lf_sha,
    published_bytes,
    validate_registered_design,
    validate_review,
)
from scripts.validate_tardis_l2_samples import (
    AUTHORIZED_DATES,
    MANIFEST,
    TRADE_MANIFEST,
    atomic_json,
    checked_path,
    raw_lines,
    trade_timestamp_matches,
    validate_slice_metadata,
)
from scripts.validate_tardis_l2_samples import (
    OUTPUT as VALIDATION_REPORT,
)

D = Decimal
DEFAULT_AUDIT_INITIAL_RESERVE = D("10")
DEFAULT_AUDIT_FUNDING = D(".10")
DEFAULT_AUDIT_FLOOR = D("2.5")
DAY_US = 86_400_000_000
ROOT = Path(__file__).resolve().parents[1]
ENVELOPES = ("CONSERVATIVE_QUEUE", "PRICE_PRIORITY")
MODEL_HASH = "4231670b19b1ca5c2b5032b1476b83b3182d1463750ea944da5efb867d81a8fa"
VALIDATOR_SOURCE_COMMIT = "e1525f4cd97082f66cd99377c22e9128080064f4"
STITCHED_DATES = (
    "2025-01-01",
    "2025-02-01",
    "2025-03-01",
    "2025-04-01",
    "2025-06-01",
    "2025-08-01",
    "2026-01-01",
    "2026-02-01",
    "2026-03-01",
    "2026-04-01",
    "2026-05-01",
    "2026-07-01",
)
PROTOCOL = Path("docs/microstructure/L2_MONTHLY_SAMPLE_PROTOCOL.md")
REVIEW = Path("reports/usdcusdt/L2-monthly-sample-preflight-review.md")
DEADLINE_SPEC = Path("docs/microstructure/M016_MODEL_SPEC.json")
DEADLINE_PROTOCOL = Path("docs/microstructure/M016_DEADLINE_PREREGISTRATION.md")
DEADLINE_REVIEW = Path("reports/usdcusdt/M016-preflight-independent-review.md")
DEADLINE_MODELS = tuple(DEADLINE_POLICY_HASHES)
OWNER_WINDOW_AUTHORITY = Path("docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md")
M019_MODEL_SPEC = Path("docs/microstructure/M019_MODEL_SPEC.json")
M019_PREREGISTRATION = Path("docs/microstructure/M019_ADAPTIVE_LADDER_PREREGISTRATION.md")
M019_REVIEW = Path("reports/usdcusdt/M019-preflight-independent-review.md")
M019_MODEL_ID = "M019"
M019_CORE = Path("src/crypto_strategy_lab/microstructure/adaptive_stablecoin_ladder.py")
M019_OWNER_DIRECTIVE = Path("docs/microstructure/ADAPTIVE_STABLECOIN_LADDER_OWNER_DIRECTIVE.md")


def require_owner_replay_approval(root=ROOT, model_id="M015") -> tuple[str, ...]:
    """Fail closed against the single OWNER authority before reading replay inputs."""
    try:
        authority = (root / OWNER_WINDOW_AUTHORITY).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("OWNER_APPROVAL_REQUIRED: AUTHORITY_UNAVAILABLE") from exc
    fields = {}
    for key, pattern in (
        ("APPROVED_COMPARISON_DAYS", r"[1-9][0-9]*"),
        ("EXTENSION_AUTHORIZED", r"true|false"),
        ("NEW_REPLAY_AUTHORIZED_NOW", r"true|false"),
    ):
        values = re.findall(rf"^{key}=(.*)$", authority, flags=re.MULTILINE)
        if len(values) != 1 or re.fullmatch(pattern, values[0]) is None:
            raise ValueError("OWNER_APPROVAL_REQUIRED: INVALID_AUTHORITY_CONTRACT")
        fields[key] = values[0]
    if fields["NEW_REPLAY_AUTHORIZED_NOW"] != "true":
        raise ValueError("OWNER_APPROVAL_REQUIRED")
    approved_days = int(fields["APPROVED_COMPARISON_DAYS"])
    if approved_days != 1 or fields["EXTENSION_AUTHORIZED"] != "false":
        if model_id in {"M018", M019_MODEL_ID}:
            raise ValueError("OWNER_EXTENSION_REQUIRES_AUDITED_STATE_CONTINUATION")
        raise ValueError("OWNER_WINDOW_EXCEEDED")
    permitted = re.findall(r"^AUTHORIZED_MODEL=(.*)$", authority, flags=re.MULTILINE)
    if permitted != [model_id] or model_id not in {"M018", M019_MODEL_ID}:
        raise ValueError("OWNER_APPROVAL_REQUIRED")
    return STITCHED_DATES[:1]


def campaign_design_paths(model_id: str) -> tuple[Path, Path, Path]:
    if model_id == "M018":
        return (
            Path("docs/microstructure/M018_MODEL_SPEC.json"),
            Path("docs/microstructure/M018_PASSIVE_ADMISSION_PREREGISTRATION.md"),
            Path("reports/usdcusdt/M018-preflight-independent-review.md"),
        )
    if model_id in DEADLINE_MODELS:
        return (
            Path(f"docs/microstructure/{model_id}_MODEL_SPEC.json"),
            Path(f"docs/microstructure/{model_id}_DEADLINE_PREREGISTRATION.md"),
            Path(f"reports/usdcusdt/{model_id}-preflight-independent-review.md"),
        )
    if model_id == M019_MODEL_ID:
        return M019_MODEL_SPEC, M019_PREREGISTRATION, M019_REVIEW
    if model_id == "M015":
        return SPEC, PROTOCOL, REVIEW
    raise ValueError("UNREGISTERED_CAMPAIGN_MODEL")


OUTPUT = Path("artifacts/usdcusdt/l2-monthly-samples")
SOURCE_PATHS = tuple(
    Path(item)
    for item in (
        "scripts/run_l2_monthly_samples.py",
        "scripts/validate_tardis_l2_samples.py",
        "scripts/run_high_uptime_recovery.py",
        "scripts/run_b10_reality.py",
        "src/crypto_strategy_lab/microstructure/observed_l2_execution.py",
        "src/crypto_strategy_lab/microstructure/tardis_l2.py",
        "src/crypto_strategy_lab/microstructure/high_uptime_recovery.py",
        "src/crypto_strategy_lab/microstructure/b10_reality.py",
        "src/crypto_strategy_lab/microstructure/serial_replay.py",
        "src/crypto_strategy_lab/microstructure/recovery_reserve.py",
        "src/crypto_strategy_lab/microstructure/data.py",
        "src/crypto_strategy_lab/microstructure/tape_cache.py",
        "src/crypto_strategy_lab/microstructure/operator.py",
    )
)
M019_REVIEW_SOURCES = (
    *SOURCE_PATHS,
    M019_CORE,
    Path("scripts/register_adaptive_stablecoin_ladder.py"),
    Path("src/crypto_strategy_lab/domain.py"),
    Path("src/crypto_strategy_lab/ml/model_registry.py"),
    Path("src/crypto_strategy_lab/microstructure/recovery_reserve_study.py"),
    Path("tests/test_adaptive_stablecoin_ladder.py"),
    Path("tests/test_run_l2_monthly_samples.py"),
)


def json_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def percentile(values, percent):
    ordered = sorted(values)
    if not ordered:
        return None
    if percent == 50:
        middle = len(ordered) // 2
        return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return ordered[max(0, (percent * len(ordered) + 99) // 100 - 1)]


def weighted_percentile(histogram, percent):
    items = sorted((value, weight) for value, weight in histogram.items() if weight > 0)
    total = sum(weight for _, weight in items)
    if not total:
        return None

    def at(rank):
        accumulated = 0
        for value, weight in items:
            accumulated += weight
            if accumulated >= rank:
                return value
        raise AssertionError("weighted quantile")

    if percent == 50 and total % 2 == 0:
        return (at(total // 2) + at(total // 2 + 1)) / 2
    return at(max(1, (total * percent + 99) // 100))


class MeasuredReplay(ObservedL2Replay):
    """Only integrate requested reporting metrics; no execution policy override."""

    def __init__(self, *args, **kwargs):
        self.motor_us = 0
        self.capital_weighted_us = D(0)
        self.depth_histogram = Counter()
        self.spread_histogram = Counter()
        super().__init__(*args, **kwargs)

    def _integrate(self, timestamp):
        delta = timestamp - self.metrics_last_us
        if delta < 0:
            raise ValueError("NONCAUSAL_MEASUREMENT")
        engine = self.engine
        with localcontext() as context:
            context.prec = 128
            order = engine.order
            if (
                order is not None
                and order.status == "ACTIVE"
                and not order.release
                and engine.book_valid
            ):
                self.motor_us += delta
                committed = engine.cost
                if order.side == "BUY":
                    committed += (order.quantity - order.filled) * order.price
                bank = engine.operating_bank
                self.capital_weighted_us += D(delta) * min(D(1), committed / bank) if bank else D(0)
            if engine.book_valid and engine.displayed_bids and engine.displayed_asks:
                self.depth_histogram[engine.displayed_bids[0][1]] += delta
                spread = engine.displayed_asks[0][0] - engine.displayed_bids[0][0]
                self.spread_histogram[spread] += delta
        super()._integrate(timestamp)


def audit_all_fills(
    path: Path,
    profile: ExecutionProfile,
    *,
    initial_reserve: D = DEFAULT_AUDIT_INITIAL_RESERVE,
    funding: D = DEFAULT_AUDIT_FUNDING,
    floor: D = DEFAULT_AUDIT_FLOOR,
    profit_only: bool = False,
) -> dict[str, Any]:
    """Independently check fills and settlements under the caller's frozen ledger contract."""
    initial_reserve, funding, floor = D(initial_reserve), D(funding), D(floor)
    if min(initial_reserve, funding, floor) < 0 or funding > 1:
        raise ValueError("AUDIT_INVALID_RESERVE_CONFIGURATION")
    orders, trades, used, queue_used, active, budgets = {}, {}, Counter(), Counter(), {}, {}
    pending_book_fills = []
    fills = releases = settlements = 0
    last_trade_id = None
    latencies = []
    book_upper, book_source, ineligible_trade = None, None, None
    cancellations, terminal_orders = {}, set()
    cash, reserve, inventory, cost, dust, dust_cost = (
        D(100),
        initial_reserve,
        D(0),
        D(0),
        D(0),
        D(0),
    )
    sold_cost = sell_net = buy_fee_basis = realized_fees = total_fees = D(0)
    sell_quantity = D(0)
    with path.open(encoding="utf-8") as stream, localcontext() as context:
        context.prec = 128
        for line in stream:
            row = json.loads(line)
            kind = row["kind"]
            if kind == "SUBMIT":
                orders[row["order_id"]] = row
            elif kind == "OBSERVED_BOOK":
                book_upper, book_source = row["exchange_upper_us"], row["capture_order"]
            elif kind == "SYNTHETIC_SAMPLE_SEAM":
                book_upper, book_source = None, None
            elif kind == "CANCEL_REQUEST":
                cancellations[row["order_id"]] = row["effective_us"]
            elif kind in ("CANCELED", "REJECTION", "IOC_EXPIRED") and "order_id" in row:
                terminal_orders.add(row["order_id"])
            elif kind == "CANONICAL_TRADE_BINDING":
                if last_trade_id is not None:
                    used.pop(("trade", last_trade_id), None)
                trades.clear()
                queue_used.clear()
                last_trade_id = row["trade_id"]
                ineligible_trade = None
                trades[row["trade_id"]] = row
            elif kind == "EXECUTION_EVENT_INELIGIBLE":
                ineligible_trade = row["trade_id"]
            elif kind == "ORDER_ACTIVE":
                active[row["order_id"]] = row["evaluated_at_us"]
                order = orders[row["order_id"]]
                if not order.get("release", False) and not (
                    D(order["price"]) < D(row["ask"])
                    if order["side"] == "BUY"
                    else D(order["price"]) > D(row["best_bid"])
                ):
                    raise ValueError("AUDIT_POST_ONLY_ACTIVATION")
            elif kind == "QUEUE_FLOW":
                queue_used[row["trade_id"]] += D(row["queue_before"]) - D(row["queue_after"])
            elif kind == "OBSERVED_BUDGET_CHANGE":
                price = D(row["price"])
                old, new = D(row["old_displayed"]), D(row["displayed"])
                expected = max(D(0), min(new, D(row["old_available"]) + new - old))
                if row.get("seam_clamp"):
                    expected = min(new, D(row["old_available"]))
                if expected != D(row["available"]):
                    raise ValueError("AUDIT_DEPTH_REFRESH_RULE")
                if price in budgets and budgets[price] != D(row["old_available"]):
                    raise ValueError("AUDIT_DEPTH_OLD_BUDGET")
                budgets[price] = expected
            elif kind == "FILL":
                fills += 1
                order = orders[row["order_id"]]
                cancel_at = cancellations.get(row["order_id"])
                if row["order_id"] in terminal_orders or (
                    cancel_at is not None
                    and (
                        row["time_us"] > cancel_at
                        or (row["source"] == "TRADE_THROUGH" and row["time_us"] == cancel_at)
                    )
                ):
                    raise ValueError("AUDIT_FILL_AFTER_CANCEL_OR_TERMINAL")
                if row["time_us"] < active.get(row["order_id"], row["time_us"] + 1):
                    raise ValueError("AUDIT_FILL_BEFORE_ACTIVATION")
                latencies.append(D(row["time_us"] - order["submitted_us"]) / 1_000_000)
                quantity, price = D(row["quantity"]), D(row["price"])
                if quantity <= 0 or price <= 0 or row["side"] != order["side"]:
                    raise ValueError("AUDIT_NONPOSITIVE_OR_WRONG_SIDE_FILL")
                key = ("order", row["order_id"])
                used[key] += quantity
                if used[key] > D(order["quantity"]):
                    raise ValueError("AUDIT_ORDER_OVERFILL")
                fee = profile.taker_fee if row["release"] else profile.maker_fee
                if D(row["fee_quote"]) != quantity * price * fee:
                    raise ValueError("AUDIT_FILL_FEE")
                gross, fee_quote = quantity * price, quantity * price * fee
                total_fees += fee_quote
                if row["side"] == "BUY":
                    if row["commission_asset"] != "USDC" or D(row["commission"]) != quantity * fee:
                        raise ValueError("AUDIT_BASE_COMMISSION")
                    cash -= gross
                    inventory += quantity - quantity * fee
                    cost += gross
                    buy_fee_basis += fee_quote
                else:
                    if inventory < quantity or inventory <= 0:
                        raise ValueError("AUDIT_INVENTORY_OVERSELL")
                    if row["commission_asset"] != "USDT" or D(row["commission"]) != fee_quote:
                        raise ValueError("AUDIT_QUOTE_COMMISSION")
                    allocation = cost * quantity / inventory
                    allocated_fee = buy_fee_basis * quantity / inventory
                    cost -= allocation
                    sold_cost += allocation
                    buy_fee_basis -= allocated_fee
                    realized_fees += allocated_fee + fee_quote
                    inventory -= quantity
                    cash += gross - fee_quote
                    sell_net += gross - fee_quote
                    sell_quantity += quantity
                if row["source"] == "BOOK":
                    if row["source_id"] != book_source:
                        raise ValueError("AUDIT_WRONG_BOOK_SOURCE")
                    if not row["release"] or price < D(order["price"]):
                        raise ValueError("AUDIT_UNPROTECTED_BOOK_FILL")
                    pending_book_fills.append(row)
                else:
                    if row["source"] not in ("TRADE", "TRADE_THROUGH"):
                        raise ValueError("AUDIT_UNKNOWN_FILL_SOURCE")
                    trade = trades[row["source_id"]]
                    if (
                        book_upper is None
                        or book_upper > trade["exchange_time_us"]
                        or ineligible_trade == row["source_id"]
                    ):
                        raise ValueError("AUDIT_FUTURE_OR_INELIGIBLE_BOOK_TRADE")
                    if trade["buyer_maker"] != (row["side"] == "BUY"):
                        raise ValueError("AUDIT_INCOMPATIBLE_AGGRESSOR")
                    raw_price = D(trade["price"])
                    used[("trade", row["source_id"])] += quantity
                    if used[("trade", row["source_id"])] + queue_used[row["source_id"]] > D(
                        trade["quantity"]
                    ):
                        raise ValueError("AUDIT_REUSED_TRADE_VOLUME")
                    if (
                        price != D(order["price"])
                        or trade["exchange_time_us"] <= active[row["order_id"]]
                    ):
                        raise ValueError("AUDIT_FILL_LIMIT_OR_ACTIVATION")
                    if row["source"] == "TRADE" and raw_price != price:
                        raise ValueError("AUDIT_EXACT_PRICE_FILL")
                    if row["source"] == "TRADE_THROUGH" and not (
                        raw_price < price if row["side"] == "BUY" else raw_price > price
                    ):
                        raise ValueError("AUDIT_NONSTRICT_THROUGH")
            elif kind == "OBSERVED_DEPTH_CONSUMPTION":
                if not pending_book_fills:
                    raise ValueError("AUDIT_UNBOUND_DEPTH_CONSUMPTION")
                fill = pending_book_fills.pop(0)
                price, quantity = D(row["price"]), D(row["quantity"])
                before, after = D(row["available_before"]), D(row["available_after"])
                if (
                    (price, quantity, row["book_source_id"])
                    != (D(fill["price"]), D(fill["quantity"]), fill["source_id"])
                    or not D(0) <= after == before - quantity
                    or before > D(row["displayed_quantity"])
                ):
                    raise ValueError("AUDIT_BOOK_BUDGET_OR_SOURCE")
                if price in budgets and budgets[price] != before:
                    raise ValueError("AUDIT_BOOK_BUDGET_REUSE")
                budgets[price] = after
            elif kind == "SETTLEMENT":
                settlements += 1
                releases += int(row["release"])
                if D(row["reserve"]) < floor:
                    raise ValueError("AUDIT_RESERVE_FLOOR")
                net = D(row["net_profit"])
                if profit_only and row["release"]:
                    raise ValueError("AUDIT_PROFIT_ONLY_RELEASE")
                if profit_only and (
                    sell_quantity <= 0 or (sell_net - sold_cost) / sell_quantity <= 0
                ):
                    raise ValueError("AUDIT_PROFIT_ONLY_NONPOSITIVE_SELL_NET_PER_UNIT")
                if net != sell_net - sold_cost:
                    raise ValueError("AUDIT_REALIZED_PROFIT_RECONCILIATION")
                if D(row["realized_fees_quote"]) != realized_fees:
                    raise ValueError("AUDIT_REALIZED_FEES_RECONCILIATION")
                if D(row["reserve_contribution"]) != max(D(0), net) * funding:
                    raise ValueError("AUDIT_RESERVE_FUNDING")
                if D(row["reserve_consumption"]) != (max(D(0), -net) if row["release"] else D(0)):
                    raise ValueError("AUDIT_RESERVE_DEFICIT")
                reserve_funding = max(D(0), net) * funding
                deficit = max(D(0), -net) if row["release"] else D(0)
                cash += deficit - reserve_funding
                reserve += reserve_funding - deficit
                dust += inventory
                dust_cost += cost
                inventory = cost = D(0)
                for name, value in (
                    ("cash", cash),
                    ("reserve", reserve),
                    ("dust", dust),
                    ("dust_cost", dust_cost),
                ):
                    if D(row[name]) != value:
                        raise ValueError("AUDIT_SETTLEMENT_LEDGER_RECONCILIATION:" + name)
                sold_cost = sell_net = buy_fee_basis = realized_fees = sell_quantity = D(0)
    if pending_book_fills:
        raise ValueError("AUDIT_MISSING_DEPTH_CONSUMPTION")
    return {
        "status": "PASS_AUTOMATED_ALL_FILLS",
        "final_ledger": {
            key: str(value)
            for key, value in (
                ("cash", cash),
                ("reserve", reserve),
                ("inventory", inventory),
                ("cost", cost),
                ("dust", dust),
                ("dust_cost", dust_cost),
                ("fees", total_fees),
            )
        },
        "fills_checked": fills,
        "settlements_checked": settlements,
        "releases_checked": releases,
        "initial_reserve": str(initial_reserve),
        "funding": str(funding),
        "reserve_floor": str(floor),
        "profit_only": profit_only,
        "audit_sha256": file_sha(path),
        "independent_review": "SEPARATE_GATE",
        "median_fill_latency_seconds": str(percentile(latencies, 50)) if latencies else None,
    }


def audit_shared_trade_budget(
    lane_paths: tuple[Path, ...] | list[Path],
    canonical: dict[Any, Trade],
    coordinator_audit: list[dict[str, Any]] | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile original trade quantity against every lane's independent consumption."""
    if not lane_paths or not canonical:
        raise ValueError("SHARED_TRADE_CANONICAL_REQUIRED")
    original = {str(trade_id): D(trade.quantity) for trade_id, trade in canonical.items()}
    consumed: Counter[str] = Counter()
    lane_usage: dict[str, Counter[str]] = {}
    for lane_index, path in enumerate(lane_paths):
        usage: Counter[str] = Counter()
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                kind = row.get("kind")
                if kind == "QUEUE_FLOW":
                    trade_id = str(row["trade_id"])
                    quantity = D(row["queue_before"]) - D(row["queue_after"])
                elif kind == "FILL" and row.get("source") in ("TRADE", "TRADE_THROUGH"):
                    trade_id = str(row["source_id"])
                    quantity = D(row["quantity"])
                else:
                    continue
                if quantity < 0:
                    raise ValueError("SHARED_TRADE_NEGATIVE_CONSUMPTION")
                usage[trade_id] += quantity
                consumed[trade_id] += quantity
        lane_usage[str(lane_index)] = usage
    unknown = sorted(set(consumed) - set(original))
    if unknown:
        raise ValueError("SHARED_TRADE_UNKNOWN_ID:" + unknown[0])
    over = next(
        (trade_id for trade_id, quantity in consumed.items() if quantity > original[trade_id]),
        None,
    )
    if over is not None:
        raise ValueError("SHARED_TRADE_BUDGET_EXCEEDED:" + over)

    allocation_rows: list[dict[str, Any]] = []
    if isinstance(coordinator_audit, dict):
        candidate = coordinator_audit.get("SHARED_TRADE_ALLOCATION", [])
        allocation_rows = candidate if isinstance(candidate, list) else []
    elif coordinator_audit is not None:
        allocation_rows = [
            row
            for row in coordinator_audit
            if row.get("kind") == "SHARED_TRADE_ALLOCATION" or "SHARED_TRADE_ALLOCATION" in row
        ]
    for row in allocation_rows:
        payload = row.get("SHARED_TRADE_ALLOCATION", row)
        trade_id = str(payload.get("trade_id", payload.get("source_id")))
        if trade_id not in original:
            raise ValueError("SHARED_TRADE_UNKNOWN_ID:" + trade_id)
        declared_original = payload.get("original_quantity", payload.get("original_qty"))
        declared_consumed = payload.get("consumed_quantity", payload.get("consumed_qty"))
        if declared_original is not None and D(str(declared_original)) != original[trade_id]:
            raise ValueError("SHARED_TRADE_ORIGINAL_MISMATCH:" + trade_id)
        if declared_consumed is not None and D(str(declared_consumed)) != consumed.get(
            trade_id, D(0)
        ):
            raise ValueError("SHARED_TRADE_CONSUMED_MISMATCH:" + trade_id)
        declared_lanes = payload.get("lane_usage", payload.get("lanes"))
        if isinstance(declared_lanes, dict):
            actual_lanes = {
                lane: str(usage.get(trade_id, D(0))) for lane, usage in lane_usage.items()
            }
            if {
                str(lane): str(D(str(value))) for lane, value in declared_lanes.items()
            } != actual_lanes:
                raise ValueError("SHARED_TRADE_LANE_USAGE_MISMATCH:" + trade_id)
    return {
        "status": "PASS_INDEPENDENT_GLOBAL_TRADE_BUDGET",
        "trades_checked": len(original),
        "trades_consumed": sum(quantity > 0 for quantity in consumed.values()),
        "original_volume": str(sum(original.values(), D(0))),
        "consumed_volume": str(sum(consumed.values(), D(0))),
        "remaining_volume": str(sum(original.values(), D(0)) - sum(consumed.values(), D(0))),
        "lane_usage": {
            lane: {trade_id: str(quantity) for trade_id, quantity in usage.items()}
            for lane, usage in lane_usage.items()
        },
    }


def summary(replay: MeasuredReplay, validation, audit, identity):
    engine = replay.engine
    score = replay.metrics()
    observations = engine.activation_observations
    queues = [D(row["ahead_estimate"]) for row in observations]
    pressure = [
        engine.orders[row["order_id"] - 1].quantity / D(row["displayed_quantity"])
        for row in observations
        if D(row["displayed_quantity"]) > 0
    ]
    result = {
        **score,
        **identity,
        "DATE": identity["date"],
        "ENVELOPE": replay.execution_envelope,
        "STRATEGY_MODEL_USED": identity["model_id"],
        "MODEL_HASH": identity.get("model_hash", MODEL_HASH),
        "VALIDATION_INPUT_SHA256": validation["input_sha256"],
        "L2_VALID": True,
        "L2_ROWS": validation["CSV_ROWS"],
        "TRADES": replay.processed_trades,
        "OPERATING_START": "100",
        "RESERVE_START": "10",
        "INITIAL_STATE": "FLAT",
        "AUDIT_STATUS": "PASS_CONDITIONAL"
        if identity.get("preflight_review_sha256") and audit["status"] == "PASS_AUTOMATED_ALL_FILLS"
        else audit["status"],
        "AUDIT_AUTOMATED_STATUS": audit["status"],
        "INDEPENDENT_AUDIT_SCOPE": "PREFLIGHT_SOURCE_REVIEW; ALL_FILLS_PROGRAMMATIC_RECONCILIATION",
        "RUN_STATUS": "COMPLETE",
        "VERDICT": "COMPLETE_CONDITIONAL_EXECUTION",
        "CLOCK_MODE": "CAPTURE_ARRIVAL",
    }
    with localcontext() as context:
        context.prec = 128
        mark = engine.bids[0][0] if engine.bids else None
        operating = (
            engine.cash + (engine.inventory + engine.dust) * mark if mark is not None else None
        )
        total = operating + engine.reserve if operating is not None else None
        net = total - D(110) if total is not None else None
        duration_us = replay.end_us - replay.start_us
        motor = D(replay.motor_us) / duration_us
        result.update(
            OPERATING_FINAL=operating,
            RESERVE_FINAL=engine.reserve,
            TOTAL_EQUITY_FINAL=total,
            NET_PNL=net,
            CUMULATIVE_RETURN=net / D(110) if net is not None else None,
            SYNTHETIC_STRESS_RETURN=net / D(110) if net is not None else None,
            ORDINARY_CYCLES=engine.counts["FULLY_FILLED_CYCLES"],
            NET_POSITIVE_CYCLES=engine.counts["NET_POSITIVE_CYCLES"],
            CYCLES_PER_HOUR=D(engine.counts["NET_POSITIVE_CYCLES"]) * 3_600_000_000 / duration_us,
            FULL_STOP_HOURS=D(duration_us - replay.motor_us) / 3_600_000_000,
            DURATION_HOURS=D(duration_us) / 3_600_000_000,
            MOTOR_UPTIME=motor,
            WORKING_ORDER_UPTIME=D(replay.working_order_us) / duration_us,
            CAPITAL_WEIGHTED_UPTIME=replay.capital_weighted_us / duration_us,
            ZERO_CYCLE_DAY="YES" if engine.counts["NET_POSITIVE_CYCLES"] == 0 else "NO",
            RELEASES=engine.counts["RELEASE_FILLED"],
            RELEASE_LOSS=engine.reserve_consumption,
            MAX_HOLD=D(score["MAX_HOLD_HOURS"]),
            HARD_LOCK_VIOLATIONS=score["HOLDS_OVER_24H"],
            DISPLAYED_QUEUE_P50=percentile(queues, 50),
            DISPLAYED_QUEUE_P90=percentile(queues, 90),
            DISPLAYED_QUEUE_P99=percentile(queues, 99),
            DEPTH_BEST_SIDE="BID",
            DEPTH_BEST_P50=weighted_percentile(replay.depth_histogram, 50),
            DEPTH_BEST_P90=weighted_percentile(replay.depth_histogram, 90),
            SPREAD_P50=weighted_percentile(replay.spread_histogram, 50),
            SPREAD_P90=weighted_percentile(replay.spread_histogram, 90),
            CAPACITY_PRESSURE=percentile(pressure, 50),
            ZERO_DEPTH_ACTIVATIONS=sum(D(row["displayed_quantity"]) == 0 for row in observations),
            OPEN_HOLD_CENSORED=engine.entry_us is not None,
            MARK_PRICE=mark,
            MARK_AGE_US=replay.end_us - engine.last_book_us,
            UNREALIZED_PNL=(engine.inventory + engine.dust) * mark - engine.cost - engine.dust_cost
            if mark is not None
            else None,
        )
        median = result["DISPLAYED_QUEUE_P50"]
        proxy = engine.profile.queue_ahead
        result["OLD_PROXY_TO_OBSERVED_MEDIAN"] = proxy / median if median else None
        result["OLD_PROXY_ASSESSMENT"] = (
            "INCONCLUSIVE"
            if not queues
            else "TOO_CONSERVATIVE"
            if proxy > percentile(queues, 90)
            else "TOO_OPTIMISTIC"
            if proxy < percentile(queues, 10)
            else "REASONABLE"
        )
        for side in ("BUY", "SELL"):
            orders = [order for order in engine.orders if order.side == side and not order.release]
            result[side + "_ORDERS"] = len(orders)
            result[side + "_FULL"] = sum(order.filled == order.quantity for order in orders)
            result[side + "_PARTIAL"] = sum(0 < order.filled < order.quantity for order in orders)
            result[side + "_ZERO_FILL"] = sum(order.filled == 0 for order in orders)
        result["ORDER_STATES"] = dict(Counter(order.status for order in engine.orders))
    return {
        key: str(value) if isinstance(value, Decimal) else value for key, value in result.items()
    }


def execute_verified_experiment(replay, canonical, events, validation, identity, output):
    """Run one prevalidated immutable experiment; callable by synthetic tests."""
    if output.exists() and any(output.iterdir()):
        raise ValueError("EXISTING_EXPERIMENT_PRESERVED")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "run-manifest.json", identity)
    journal = AuditJournal(output / "execution-audit.jsonl")
    seen = set()
    market_stats = {
        "tradecount": 0,
        "buyer_aggressor_quantity": D(0),
        "seller_aggressor_quantity": D(0),
        "min_price": None,
        "max_price": None,
    }
    try:
        previous_cycles = previous_positive = 0
        previous_motor = 0
        previous_operating, previous_reserve, previous_equity = D(100), D(10), D(110)
        for index, event in enumerate(events, 1):
            if event["kind"] == "SEAM":
                replay.begin_sample_seam(event["local_us"], event["source_date"])
                replay.engine._record(
                    "SOURCE_DAY_MAPPING",
                    **{key: value for key, value in event.items() if key != "kind"},
                )
                if event["day_index"]:
                    with localcontext() as reporting_context:
                        reporting_context.prec = 128
                        engine = replay.engine
                        if not engine.bids:
                            raise ValueError("DAY_CLOSE_REQUIRES_LAST_OBSERVED_BID")
                        mark = engine.bids[0][0]
                        operating = engine.cash + (engine.inventory + engine.dust) * mark
                        equity = operating + engine.reserve
                        open_hold = (
                            event["local_us"] - engine.entry_us
                            if engine.entry_us is not None
                            else None
                        )
                        checkpoint = {
                            "SOURCE_DATE": event["previous_source_date"],
                            "LOGICAL_DAY": event["day_index"],
                            "ENVELOPE": replay.execution_envelope,
                            "RUN_STATUS": "PENDING",
                            "VERDICT": "PENDING",
                            "OPERATING_START": str(previous_operating),
                            "RESERVE_START": str(previous_reserve),
                            "OPERATING_FINAL": str(operating),
                            "RESERVE_FINAL": str(engine.reserve),
                            "TOTAL_EQUITY_FINAL": str(equity),
                            "DAILY_NET_PNL": str(equity - previous_equity),
                            "CUMULATIVE_NET_PNL": str(equity - D(110)),
                            "DAILY_ORDINARY_CYCLES": engine.counts["FULLY_FILLED_CYCLES"]
                            - previous_cycles,
                            "DAILY_NET_POSITIVE_CYCLES": engine.counts["NET_POSITIVE_CYCLES"]
                            - previous_positive,
                            "CUMULATIVE_NET_POSITIVE_CYCLES": engine.counts["NET_POSITIVE_CYCLES"],
                            "MOTOR_UPTIME": str(D(replay.motor_us - previous_motor) / DAY_US),
                            "MAX_HOLD_HOURS": str(
                                D(max([*replay.holds_us, open_hold or 0], default=0))
                                / 3_600_000_000
                            ),
                            "OPEN_POSITION": engine.inventory > 0,
                            "MARK_EVIDENCE": "LAST_AVAILABLE_OBSERVED_BID",
                            "NET_POSITIVE_CYCLES": replay.engine.counts["NET_POSITIVE_CYCLES"]
                            - previous_positive,
                            "FULLY_FILLED_CYCLES": replay.engine.counts["FULLY_FILLED_CYCLES"]
                            - previous_cycles,
                            "OPERATING_BANK": str(replay.engine.operating_bank),
                            "RESERVE": str(replay.engine.reserve),
                            "OPEN_HOLD_US": event["local_us"] - replay.engine.entry_us
                            if replay.engine.entry_us is not None
                            else None,
                            "ENGINE_STATE": replay.engine.checkpoint(),
                        }
                        daily = {
                            key: value for key, value in checkpoint.items() if key != "ENGINE_STATE"
                        }
                        (output / "daily").mkdir(exist_ok=True)
                        write_json(output / "daily" / f"{event['day_index']:02d}.json", daily)
                        write_json(
                            output / "daily" / f"{event['day_index']:02d}-engine-state.json",
                            checkpoint["ENGINE_STATE"],
                        )
                        atomic_json(output / "progress.json", daily)
                        print(
                            json.dumps(
                                {
                                    key: value
                                    for key, value in checkpoint.items()
                                    if key != "ENGINE_STATE"
                                }
                            ),
                            flush=True,
                        )
                        previous_cycles = replay.engine.counts["FULLY_FILLED_CYCLES"]
                        previous_positive = replay.engine.counts["NET_POSITIVE_CYCLES"]
                        previous_motor = replay.motor_us
                        previous_operating, previous_reserve, previous_equity = (
                            operating,
                            engine.reserve,
                            equity,
                        )
                journal.drain(replay.engine)
                journal.durable()
                continue
            if event["kind"] == "BOOK":
                if not event["sequence_validated"]:
                    continue
                replay.receive_book(
                    ObservedBookBatch(
                        event["exchange_us"],
                        event["local_us"],
                        event["capture_order"],
                        event["native_update_id"],
                        event["bids"],
                        event["asks"],
                        event["known_bid_floor"],
                        event["known_ask_ceiling"],
                        True,
                        event["is_snapshot"],
                        event.get("changes"),
                        event["exchange_upper_us"],
                        event["exchange_precision"],
                    )
                )
            else:
                native = event["data"]
                trade = canonical.get(native["t"])
                if trade is None:
                    if replay.start_us <= event["exchange_us"] < replay.end_us:
                        raise ValueError("UNBOUND_INTERIOR_NATIVE_TRADE")
                    continue
                if trade.trade_id in seen or not trade_timestamp_matches(
                    trade.time_us - event.get("clock_offset_us", 0), native["T"]
                ):
                    raise ValueError("CANONICAL_TRADE_BINDING_CHANGED")
                if (trade.price, trade.quantity, trade.buyer_maker) != (
                    D(native["p"]),
                    D(native["q"]),
                    native["m"],
                ):
                    raise ValueError("CANONICAL_TRADE_FIELDS_CHANGED")
                replay.receive_trade(
                    trade, capture_time_us=event["local_us"], capture_order=event["capture_order"]
                )
                seen.add(trade.trade_id)
                market_stats["tradecount"] += 1
                side = (
                    "seller_aggressor_quantity" if trade.buyer_maker else "buyer_aggressor_quantity"
                )
                market_stats[side] += trade.quantity
                market_stats["min_price"] = (
                    min(market_stats["min_price"], trade.price)
                    if market_stats["min_price"] is not None
                    else trade.price
                )
                market_stats["max_price"] = (
                    max(market_stats["max_price"], trade.price)
                    if market_stats["max_price"] is not None
                    else trade.price
                )
            journal.drain(replay.engine)
            if index % 50000 == 0:
                journal.durable()
                atomic_json(
                    output / "progress.json",
                    {
                        "RUN_STATUS": "PENDING",
                        "VERDICT": "PENDING",
                        "ENVELOPE": replay.execution_envelope,
                        "LOGICAL_DAY": (event["local_us"] - replay.start_us) // DAY_US + 1,
                        "CAPTURE_TIME_US": event["local_us"],
                        "CAPTURED_EVENTS": index,
                        "CUMULATIVE_NET_POSITIVE_CYCLES": replay.engine.counts[
                            "NET_POSITIVE_CYCLES"
                        ],
                        "OPERATING_BANK": str(replay.engine.operating_bank),
                        "RESERVE": str(replay.engine.reserve),
                    },
                )
                print(
                    json.dumps(
                        {
                            "date": identity["date"],
                            "envelope": replay.execution_envelope,
                            "captured_events": index,
                            "trades": len(seen),
                            "capture_time_us": event["local_us"],
                            "positive_cycles": replay.engine.counts["NET_POSITIVE_CYCLES"],
                            "operating_bank": str(replay.engine.operating_bank),
                            "reserve": str(replay.engine.reserve),
                        }
                    ),
                    flush=True,
                )
        if seen != set(canonical):
            raise ValueError("CANONICAL_DAY_NOT_FULLY_DELIVERED")
        replay.finish()
        journal.drain(replay.engine)
        binding = journal.durable()
        audit = audit_all_fills(output / "execution-audit.jsonl", replay.engine.profile)
        for name, value in audit["final_ledger"].items():
            if D(value) != getattr(replay.engine, name):
                raise ValueError("AUDIT_TERMINAL_LEDGER_RECONCILIATION:" + name)
        audit["journal"] = binding
        write_json(output / "all-fill-audit.json", audit)
        result = summary(replay, validation, audit, identity)
        market_stats.update(
            range_switches=len(replay.decisions.state.changes),
            trade_through_fills=replay.engine.counts["PRICE_THROUGH_PRIORITY_INFERENCE"],
            median_fill_latency_seconds=audit["median_fill_latency_seconds"],
            ordinary_order_limit_counts=dict(
                Counter(str(order.price) for order in replay.engine.orders if not order.release)
            ),
        )
        result["DESCRIPTIVE_MARKET_STATS"] = {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in market_stats.items()
        }
        result["AUDIT_SHA256"] = file_sha(output / "all-fill-audit.json")
        if identity["model_id"] in DEADLINE_MODELS:
            from crypto_strategy_lab.microstructure.reserve_recovery_diagnostics import (
                analyze_recovery,
            )

            result["RECOVERY_ACCOUNTING"] = analyze_recovery(
                replay.engine.settlements, D("0.10"), replay.end_us
            )
            age = (
                replay.end_us - replay.engine.entry_us if replay.engine.entry_us is not None else 0
            )
            result["HOLDS_OVER_2H"] = sum(value > 7_200_000_000 for value in replay.holds_us) + int(
                age > 7_200_000_000
            )
        write_json(output / "summary.json", result)
        write_json(output / "terminal-engine-state.json", replay.engine.checkpoint())
        return result
    except Exception as exc:
        journal.drain(replay.engine)
        binding = journal.durable()
        write_json(
            output / "failure.json",
            {
                "status": "TECHNICAL_FAILURE",
                "error": str(exc),
                "identity": identity,
                "audit_prefix": binding,
            },
        )
        raise
    finally:
        journal.close()


def audit_m019_journal(
    path: Path, canonical: dict[Any, Trade], engine: AdaptiveStablecoinLadder
) -> dict[str, Any]:
    """Rebuild M019 ownership and execution from the append-only audit journal."""
    seen_trades: set[int] = set()
    consumed_by_trade: Counter[int] = Counter()
    fills_by_trade: Counter[int] = Counter()
    queues_by_trade: Counter[int] = Counter()
    event_counts: Counter[str] = Counter()
    orders: dict[int, dict[str, Any]] = {}
    order_state: dict[int, dict[str, Any]] = {}
    lot_created: dict[str, dict[str, Any]] = {}
    lot_sold: Counter[str] = Counter()
    lot_profit: Counter[str] = Counter()
    lot_reserved: Counter[str] = Counter()
    buy_fill_quantity: Counter[int] = Counter()
    sell_fill_quantity: Counter[int] = Counter()
    buy_lot_quantity: Counter[int] = Counter()
    sell_lot_quantity: Counter[int] = Counter()
    cycles: set[int] = set()
    independent_cash = D(100)
    independent_fees = D(0)
    endowment_seen = False
    endowment_quantity = D(0)

    def _release(order_id: int, row: dict[str, Any]) -> None:
        nonlocal independent_cash
        state = order_state[order_id]
        released_quote = D(row.get("released_quote", "0"))
        released_base = D(row.get("released_base", "0"))
        if released_quote != state["reserved_quote"]:
            raise ValueError("M019_RELEASED_QUOTE_MISMATCH")
        expected_base = sum((amount for _, amount in state["reserved_lots"]), D(0))
        if released_base != expected_base:
            raise ValueError("M019_RELEASED_BASE_MISMATCH")
        independent_cash += released_quote
        state["reserved_quote"] = D(0)
        for lot_id, amount in state["reserved_lots"]:
            lot_reserved[lot_id] -= amount
            if lot_reserved[lot_id] < 0:
                raise ValueError("M019_NEGATIVE_LOT_RESERVATION")
        state["reserved_lots"] = []

    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            event = str(row.get("event", ""))
            event_counts[event] += 1
            if event == "SUBMIT":
                order_id = int(row["order_id"])
                if order_id in orders:
                    raise ValueError("M019_DUPLICATE_ORDER_ID")
                side = str(row["side"])
                price, quantity = D(row["price"]), D(row["quantity"])
                if side not in {"BUY", "SELL"} or price <= 0 or quantity <= 0:
                    raise ValueError("M019_INVALID_ORDER")
                orders[order_id] = row
                reservations = [
                    (str(lot_id), D(amount)) for lot_id, amount in row.get("reserved_lots", [])
                ]
                reserved_quote = D(row.get("reserved_quote", "0"))
                expected_quote = (
                    quantity * price * (D(1) + D(engine.profile.maker_fee))
                    if side == "BUY"
                    else D(0)
                )
                if reserved_quote != expected_quote:
                    raise ValueError("M019_ORDER_QUOTE_RESERVATION_MISMATCH")
                if side == "BUY" and reservations:
                    raise ValueError("M019_BUY_RESERVED_BASE")
                if side == "SELL":
                    if (
                        reserved_quote != 0
                        or sum((amount for _, amount in reservations), D(0)) != quantity
                    ):
                        raise ValueError("M019_SELL_RESERVATION_MISMATCH")
                    for lot_id, amount in reservations:
                        if lot_id not in lot_created or amount <= 0:
                            raise ValueError("M019_SELL_RESERVED_UNKNOWN_LOT")
                        available = D(lot_created[lot_id]["quantity"]) - lot_sold[lot_id]
                        if lot_reserved[lot_id] + amount > available:
                            raise ValueError("M019_DUPLICATE_INVENTORY_RESERVATION")
                        lot_reserved[lot_id] += amount
                independent_cash -= reserved_quote
                if independent_cash < 0:
                    raise ValueError("M019_UNBACKED_BUY")
                order_state[order_id] = {
                    "status": "PENDING",
                    "remaining": quantity,
                    "reserved_quote": reserved_quote,
                    "reserved_lots": reservations,
                    "activation_us": None,
                    "queue": D(row.get("queue", "0")),
                }
            elif event == "CANCEL":
                order_id = int(row["order_id"])
                if order_id not in order_state or order_state[order_id]["status"] not in {
                    "PENDING",
                    "ACTIVE",
                }:
                    raise ValueError("M019_INVALID_CANCEL")
                order_state[order_id]["status"] = "CANCEL_PENDING"
            elif event == "ACTIVATED":
                order_id = int(row["order_id"])
                if order_id not in orders or int(row["time_us"]) < int(
                    orders[order_id]["active_us"]
                ):
                    raise ValueError("M019_INVALID_ACTIVATION")
                state = order_state[order_id]
                if state["status"] not in {"PENDING", "CANCEL_PENDING"}:
                    raise ValueError("M019_DUPLICATE_OR_TERMINAL_ACTIVATION")
                if str(row["side"]) != str(orders[order_id]["side"]) or D(row["price"]) != D(
                    orders[order_id]["price"]
                ):
                    raise ValueError("M019_ACTIVATION_ORDER_MISMATCH")
                side, price = str(row["side"]), D(row["price"])
                bid = None if row.get("best_bid") is None else D(row["best_bid"])
                ask = None if row.get("best_ask") is None else D(row["best_ask"])
                floor, ceiling = D(row["known_bid_floor"]), D(row["known_ask_ceiling"])
                if (side == "BUY" and (ask is None or price >= ask or price < floor)) or (
                    side == "SELL" and (bid is None or price <= bid or price > ceiling)
                ):
                    raise ValueError("M019_INVALID_ACTIVATION_CONTEXT")
                for other_id, other in order_state.items():
                    if other_id == order_id or other["status"] in {
                        "FILLED",
                        "CANCELED",
                        "REJECTED",
                    }:
                        continue
                    other_order = orders[other_id]
                    if other_order["side"] == side:
                        continue
                    other_price = D(other_order["price"])
                    if (side == "BUY" and price >= other_price) or (
                        side == "SELL" and price <= other_price
                    ):
                        raise ValueError("M019_ACTIVATED_SELF_CROSS")
                state["activation_us"] = int(row["time_us"])
                state["queue"] = D(row["queue"])
                state["status"] = (
                    "CANCEL_PENDING" if state["status"] == "CANCEL_PENDING" else "ACTIVE"
                )
            elif event in {
                "POST_ONLY_REJECTED",
                "SELF_CROSS_REJECTED",
                "UNKNOWN_COVERAGE_REJECTED",
            }:
                order_id = int(row["order_id"])
                if order_id not in order_state or order_state[order_id]["status"] not in {
                    "PENDING",
                    "CANCEL_PENDING",
                }:
                    raise ValueError("M019_INVALID_REJECTION")
                if str(row["side"]) != str(orders[order_id]["side"]) or D(row["price"]) != D(
                    orders[order_id]["price"]
                ):
                    raise ValueError("M019_REJECTION_ORDER_MISMATCH")
                bid = None if row.get("best_bid") is None else D(row["best_bid"])
                ask = None if row.get("best_ask") is None else D(row["best_ask"])
                price, side = D(row["price"]), str(row["side"])
                floor = None if row.get("known_bid_floor") is None else D(row["known_bid_floor"])
                ceiling = (
                    None if row.get("known_ask_ceiling") is None else D(row["known_ask_ceiling"])
                )
                public_cross = (side == "BUY" and ask is not None and price >= ask) or (
                    side == "SELL" and bid is not None and price <= bid
                )
                coverage_unknown = (
                    floor is None
                    or ceiling is None
                    or (price < floor if side == "BUY" else price > ceiling)
                )
                if event == "POST_ONLY_REJECTED" and not public_cross:
                    raise ValueError("M019_FALSE_POST_ONLY_REJECTION")
                if event == "UNKNOWN_COVERAGE_REJECTED" and not coverage_unknown:
                    raise ValueError("M019_FALSE_COVERAGE_REJECTION")
                if event == "SELF_CROSS_REJECTED":
                    self_cross = any(
                        other_id != order_id
                        and other["status"] not in {"FILLED", "CANCELED", "REJECTED"}
                        and orders[other_id]["side"] != side
                        and (
                            (side == "BUY" and price >= D(orders[other_id]["price"]))
                            or (side == "SELL" and price <= D(orders[other_id]["price"]))
                        )
                        for other_id, other in order_state.items()
                    )
                    if not self_cross:
                        raise ValueError("M019_FALSE_SELF_CROSS_REJECTION")
                _release(order_id, row)
                order_state[order_id]["status"] = "REJECTED"
            elif event == "CANCEL_ACK":
                order_id = int(row["order_id"])
                if order_id not in order_state or order_state[order_id]["status"] != (
                    "CANCEL_PENDING"
                ):
                    raise ValueError("M019_INVALID_CANCEL_ACK")
                _release(order_id, row)
                order_state[order_id]["status"] = "CANCELED"
            if event in {"TRADE", "TRADE_BLOCKED_FUTURE_BOOK"}:
                trade_id = int(row["trade_id"])
                if trade_id in seen_trades or trade_id not in canonical:
                    raise ValueError("M019_DUPLICATE_OR_UNKNOWN_TRADE")
                seen_trades.add(trade_id)
                original = D(row["original_quantity"])
                consumed = D(row["consumed_quantity"])
                remaining = D(row["remaining_quantity"])
                if original != canonical[trade_id].quantity or min(consumed, remaining) < 0:
                    raise ValueError("M019_TRADE_QUANTITY_MISMATCH")
                if consumed + remaining != original:
                    raise ValueError("M019_SHARED_TRADE_BUDGET_MISMATCH")
                if event == "TRADE":
                    queue_consumed = D(row["queue_consumed_quantity"])
                    fill_consumed = D(row["fill_consumed_quantity"])
                    if queue_consumed + fill_consumed != consumed:
                        raise ValueError("M019_TRADE_CONSUMPTION_COMPONENT_MISMATCH")
                elif consumed != 0 or remaining != original:
                    raise ValueError("M019_BLOCKED_TRADE_CONSUMED_LIQUIDITY")
                consumed_by_trade[trade_id] += consumed
            elif event == "FILL":
                trade_id = int(row["source_id"])
                if trade_id not in canonical:
                    raise ValueError("M019_FILL_UNKNOWN_TRADE")
                order_id = int(row["order_id"])
                if order_id not in orders or order_state[order_id]["activation_us"] is None:
                    raise ValueError("M019_FILL_WITHOUT_ACTIVATION")
                state = order_state[order_id]
                if state["status"] not in {"ACTIVE", "CANCEL_PENDING"}:
                    raise ValueError("M019_FILL_AFTER_TERMINAL_STATE")
                trade = canonical[trade_id]
                if trade.time_us <= int(state["activation_us"]):
                    raise ValueError("M019_NATIVE_PRINT_NOT_AFTER_ACTIVATION")
                side = str(orders[order_id]["side"])
                order_price = D(orders[order_id]["price"])
                if str(row.get("side")) != side or D(row.get("price", "0")) != order_price:
                    raise ValueError("M019_FILL_ORDER_FIELDS_MISMATCH")
                source = str(row.get("source"))
                if source not in {"TRADE", "TRADE_THROUGH"}:
                    raise ValueError("M019_UNSUPPORTED_FILL_SOURCE")
                quantity = D(row["quantity"])
                if quantity <= 0 or quantity > state["remaining"]:
                    raise ValueError("M019_INVALID_FILL_QUANTITY")
                if trade.buyer_maker != (side == "BUY"):
                    raise ValueError("M019_AGGRESSOR_SIDE_MISMATCH")
                exact = trade.price == order_price
                through = (side == "BUY" and trade.price < order_price) or (
                    side == "SELL" and trade.price > order_price
                )
                if (source == "TRADE" and not exact) or (source == "TRADE_THROUGH" and not through):
                    raise ValueError("M019_FILL_PRICE_SOURCE_MISMATCH")
                if source == "TRADE" and state["queue"] != 0:
                    raise ValueError("M019_FILL_BEFORE_QUEUE_DEPLETION")
                state["remaining"] -= quantity
                expected_status = "FILLED" if state["remaining"] == 0 else state["status"]
                if (
                    D(row["remaining_after"]) != state["remaining"]
                    or str(row["status_after"]) != expected_status
                ):
                    raise ValueError("M019_FILL_TERMINAL_STATE_MISMATCH")
                if side == "BUY":
                    debit = quantity * order_price * (D(1) + D(engine.profile.maker_fee))
                    if debit > state["reserved_quote"]:
                        raise ValueError("M019_BUY_FILL_EXCEEDS_RESERVATION")
                    state["reserved_quote"] -= debit
                    independent_fees += quantity * order_price * D(engine.profile.maker_fee)
                    buy_fill_quantity[order_id] += quantity
                else:
                    sell_fill_quantity[order_id] += quantity
                if state["remaining"] == 0:
                    if side == "BUY":
                        independent_cash += state["reserved_quote"]
                        state["reserved_quote"] = D(0)
                    state["status"] = "FILLED"
                fills_by_trade[trade_id] += quantity
            elif event == "QUEUE_FLOW":
                trade_id = int(row["trade_id"])
                order_id = int(row["order_id"])
                if trade_id not in canonical or order_id not in orders:
                    raise ValueError("M019_QUEUE_UNKNOWN_SOURCE")
                state = order_state[order_id]
                if (
                    state["status"] not in {"ACTIVE", "CANCEL_PENDING"}
                    or state["activation_us"] is None
                ):
                    raise ValueError("M019_QUEUE_WITHOUT_ACTIVE_ORDER")
                trade = canonical[trade_id]
                side, price = str(orders[order_id]["side"]), D(orders[order_id]["price"])
                if (
                    trade.time_us <= int(state["activation_us"])
                    or trade.price != price
                    or trade.buyer_maker != (side == "BUY")
                ):
                    raise ValueError("M019_QUEUE_SOURCE_MISMATCH")
                before, after = D(row["queue_before"]), D(row["queue_after"])
                if before != state["queue"] or before - after != D(row["quantity"]) or after < 0:
                    raise ValueError("M019_QUEUE_RECONCILIATION")
                state["queue"] = after
                queues_by_trade[trade_id] += D(row["quantity"])
            elif event == "LOT_CREATED":
                lot_id = str(row["lot_id"])
                if lot_id in lot_created:
                    raise ValueError("M019_DUPLICATE_LOT")
                quantity, unit_cost = D(row["quantity"]), D(row["unit_cost"])
                if quantity <= 0 or unit_cost <= 0:
                    raise ValueError("M019_INVALID_LOT")
                lot_created[lot_id] = row
                source_order_id = row.get("source_order_id")
                if source_order_id is not None:
                    buy_lot_quantity[int(source_order_id)] += quantity
            elif event == "ENDOWMENT":
                if endowment_seen:
                    raise ValueError("M019_DUPLICATE_ENDOWMENT")
                endowment_seen = True
                bid, quantity = D(row["bid"]), D(row["quantity"])
                independent_cash -= bid * quantity
                endowment_quantity = quantity
                if independent_cash != D(row["cash"]):
                    raise ValueError("M019_ENDOWMENT_CASH_RECONCILIATION")
            elif event == "LOT_SOLD":
                lot_id = str(row["lot_id"])
                if lot_id not in lot_created:
                    raise ValueError("M019_SALE_WITHOUT_LOT")
                quantity = D(row["quantity"])
                profit = D(row["profit"])
                if quantity <= 0 or profit <= 0:
                    raise ValueError("M019_NONPOSITIVE_REALIZED_EXIT")
                if D(row["gross"]) - D(row["fee"]) - D(row["cost"]) != profit:
                    raise ValueError("M019_SALE_PNL_RECONCILIATION")
                if D(row["cost"]) != quantity * D(lot_created[lot_id]["unit_cost"]):
                    raise ValueError("M019_SALE_LOT_COST_RECONCILIATION")
                sell_order_id = int(row["sell_order_id"])
                if sell_order_id not in orders or orders[sell_order_id]["side"] != "SELL":
                    raise ValueError("M019_SALE_WITHOUT_ORDER")
                if order_state[sell_order_id]["status"] not in {
                    "ACTIVE",
                    "CANCEL_PENDING",
                }:
                    raise ValueError("M019_SALE_WITHOUT_ACTIVE_ORDER")
                gross = D(row["gross"])
                if gross != quantity * D(orders[sell_order_id]["price"]):
                    raise ValueError("M019_SALE_PRICE_RECONCILIATION")
                if D(row["fee"]) != gross * D(engine.profile.maker_fee):
                    raise ValueError("M019_SALE_FEE_RECONCILIATION")
                lot_sold[lot_id] += quantity
                lot_profit[lot_id] += profit
                lot_reserved[lot_id] -= quantity
                if lot_reserved[lot_id] < 0:
                    raise ValueError("M019_SALE_EXCEEDS_RESERVED_INVENTORY")
                state = order_state[sell_order_id]
                remaining_allocations: list[tuple[str, D]] = []
                to_remove = quantity
                for reserved_lot_id, amount in state["reserved_lots"]:
                    if reserved_lot_id == lot_id and to_remove > 0:
                        removed = min(amount, to_remove)
                        amount -= removed
                        to_remove -= removed
                    if amount > 0:
                        remaining_allocations.append((reserved_lot_id, amount))
                if to_remove != 0:
                    raise ValueError("M019_SALE_ORDER_ALLOCATION_MISMATCH")
                state["reserved_lots"] = remaining_allocations
                independent_cash += gross - D(row["fee"])
                independent_fees += D(row["fee"])
                sell_lot_quantity[sell_order_id] += quantity
                if lot_sold[lot_id] > D(lot_created[lot_id]["quantity"]):
                    raise ValueError("M019_DUPLICATE_LOT_SALE")
            elif event == "CYCLE_SETTLED":
                source_order_id = int(row["source_order_id"])
                if source_order_id in cycles:
                    raise ValueError("M019_DUPLICATE_CYCLE")
                cycles.add(source_order_id)
                linked = [
                    lot
                    for lot in lot_created.values()
                    if lot.get("source_order_id") == source_order_id
                ]
                if not linked or any(
                    lot_sold[str(lot["lot_id"])] != D(lot["quantity"]) for lot in linked
                ):
                    raise ValueError("M019_CYCLE_WITH_OPEN_ENTRY_QUANTITY")
                if source_order_id not in order_state or order_state[source_order_id][
                    "status"
                ] not in {"FILLED", "CANCELED"}:
                    raise ValueError("M019_CYCLE_BEFORE_TERMINAL_BUY")
                expected_profit = sum((lot_profit[str(lot["lot_id"])] for lot in linked), D(0))
                if expected_profit <= 0 or D(row["net_profit"]) != expected_profit:
                    raise ValueError("M019_CYCLE_PNL_RECONCILIATION")
    if seen_trades != set(canonical):
        raise ValueError("M019_CANONICAL_TRADE_COVERAGE_MISMATCH")
    for trade_id, filled in fills_by_trade.items():
        if (
            filled > consumed_by_trade[trade_id]
            or consumed_by_trade[trade_id] > canonical[trade_id].quantity
        ):
            raise ValueError("M019_DUPLICATE_LIQUIDITY")
    for trade_id, consumed in consumed_by_trade.items():
        if fills_by_trade[trade_id] + queues_by_trade[trade_id] != consumed:
            raise ValueError("M019_INDEPENDENT_TRADE_CONSUMPTION_MISMATCH")
    if len(cycles) != engine.cycle_count:
        raise ValueError("M019_CYCLE_COUNT_RECONCILIATION")
    if sum(lot_profit.values(), D(0)) != engine.realized_profit:
        raise ValueError("M019_REALIZED_PNL_RECONCILIATION")
    if independent_cash != engine.cash:
        raise ValueError("M019_INDEPENDENT_CASH_RECONCILIATION")
    if independent_fees != engine.fees:
        raise ValueError("M019_INDEPENDENT_FEE_RECONCILIATION")
    if (
        sum(
            (
                state["reserved_quote"]
                for state in order_state.values()
                if state["status"] in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
            ),
            D(0),
        )
        != engine.active_buy_notional
    ):
        raise ValueError("M019_INDEPENDENT_BUY_RESERVATION_RECONCILIATION")
    engine_reserved = Counter(
        {lot.lot_id: lot.reserved for lot in engine.lots if lot.reserved != 0}
    )
    if Counter({key: value for key, value in lot_reserved.items() if value != 0}) != (
        engine_reserved
    ):
        raise ValueError("M019_INDEPENDENT_SELL_RESERVATION_RECONCILIATION")
    for order_id, quantity in buy_fill_quantity.items():
        if buy_lot_quantity[order_id] != quantity:
            raise ValueError("M019_BUY_FILL_LOT_LINK_MISMATCH")
    if set(buy_lot_quantity) - set(buy_fill_quantity):
        raise ValueError("M019_LOT_WITHOUT_BUY_FILL")
    for order_id, quantity in sell_fill_quantity.items():
        if sell_lot_quantity[order_id] != quantity:
            raise ValueError("M019_SELL_FILL_LOT_LINK_MISMATCH")
    if set(sell_lot_quantity) - set(sell_fill_quantity):
        raise ValueError("M019_LOT_SALE_WITHOUT_SELL_FILL")
    terminal_lots = {lot.lot_id: lot for lot in engine.lots}
    if set(terminal_lots) != set(lot_created):
        raise ValueError("M019_LOT_LINEAGE_INCOMPLETE")
    for lot_id, row in lot_created.items():
        source_order_id = row.get("source_order_id")
        if source_order_id is not None:
            source_order = orders.get(int(source_order_id))
            if source_order is None or source_order["side"] != "BUY":
                raise ValueError("M019_LOT_WITHOUT_BUY")
            expected_unit_cost = D(source_order["price"]) * (D(1) + D(engine.profile.maker_fee))
            if D(row["unit_cost"]) != expected_unit_cost:
                raise ValueError("M019_BUY_COST_BASIS_RECONCILIATION")
            if bool(row.get("initial_endowment")):
                raise ValueError("M019_EXECUTED_LOT_MARKED_ENDOWMENT")
        elif not bool(row.get("initial_endowment")):
            raise ValueError("M019_UNBACKED_ENDOWMENT_LOT")
        if D(row["quantity"]) - lot_sold[lot_id] != terminal_lots[lot_id].remaining:
            raise ValueError("M019_TERMINAL_LOT_RECONCILIATION")
    if (
        not endowment_seen
        or sum(
            (
                D(row["quantity"])
                for row in lot_created.values()
                if row.get("source_order_id") is None
            ),
            D(0),
        )
        != endowment_quantity
    ):
        raise ValueError("M019_ENDOWMENT_LOT_RECONCILIATION")
    remaining_cost = sum((lot.remaining * lot.unit_cost for lot in terminal_lots.values()), D(0))
    if remaining_cost != engine.inventory_cost:
        raise ValueError("M019_INDEPENDENT_INVENTORY_COST_MISMATCH")
    if engine.cash + engine.active_buy_notional + remaining_cost != (
        D(100) + sum(lot_profit.values(), D(0))
    ):
        raise ValueError("M019_INDEPENDENT_CAPITAL_CONSERVATION")
    engine.validate_invariants()
    return {
        "status": "PASS_M019_LEDGER_EXECUTION_AND_LIQUIDITY",
        "trades_checked": len(seen_trades),
        "fills_checked": event_counts["FILL"],
        "post_only_rejections": event_counts["POST_ONLY_REJECTED"],
        "future_book_trade_blocks": event_counts["TRADE_BLOCKED_FUTURE_BOOK"],
        "lots_checked": len(lot_created),
        "cycles_checked": len(cycles),
        "event_counts": dict(event_counts),
        "audit_sha256": file_sha(path),
    }


def m019_slot_scoreboard(
    engine: AdaptiveStablecoinLadder, path: Path, mark: D
) -> dict[str, dict[str, Any]]:
    orders = {order.order_id: order for order in engine.orders}
    fills: Counter[tuple[str, int]] = Counter()
    cancels: Counter[tuple[str, int]] = Counter()
    reprices: Counter[tuple[str, int]] = Counter()
    fill_latencies: dict[tuple[str, int], list[int]] = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("event") == "FILL":
                order = orders[int(row["order_id"])]
                key = order.side, order.slot
                fills[key] += 1
                fill_latencies.setdefault(key, []).append(int(row["time_us"]) - order.active_us)
            elif row.get("event") == "CANCEL":
                order = orders[int(row["order_id"])]
                key = order.side, order.slot
                cancels[key] += 1
                if row.get("reason") == "REPRICE_TWO_TICKS":
                    reprices[key] += 1
    cycles = Counter(int(row["source_slot"]) for row in engine.settlements)
    output: dict[str, dict[str, Any]] = {}
    for side in ("BUY", "SELL"):
        for slot in range(6):
            key = side, slot
            lots = [lot for lot in engine.lots if lot.band_id == slot]
            latencies = fill_latencies.get(key, [])
            output[f"{side}_SLOT_{slot + 1}"] = {
                "BAND_SHARED_METRICS_DO_NOT_SUM_WITH_OPPOSITE_SLOT": True,
                "ORDERS_SUBMITTED": sum(
                    order.side == side and order.slot == slot for order in engine.orders
                ),
                "FILLS": fills[key],
                "CYCLES": cycles[slot],
                "REALIZED_PNL": str(sum((lot.realized_profit for lot in lots), D(0))),
                "CURRENT_INVENTORY": str(sum((lot.remaining for lot in lots), D(0))),
                "UNREALIZED_PNL": str(
                    sum((lot.remaining * (mark - lot.unit_cost) for lot in lots), D(0))
                ),
                "CANCELS": cancels[key],
                "REPRICES": reprices[key],
                "AVG_FILL_TIME_SECONDS": (
                    None
                    if not latencies
                    else str(D(sum(latencies)) / D(len(latencies)) / D(1_000_000))
                ),
            }
    return output


def execute_m019_experiment(engine, canonical, events, validation, identity, output):
    """Run the single authorized M019 day without entering the serial M015 engine."""
    if output.exists() and any(output.iterdir()):
        raise ValueError("EXISTING_EXPERIMENT_PRESERVED")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "run-manifest.json", identity)
    journal = AuditJournal(output / "execution-audit.jsonl")
    seen: set[int] = set()
    event_count = 0
    end_us = identity["source_day_mapping"][0]["logical_start_us"] + DAY_US
    try:
        for event_count, event in enumerate(events, 1):
            if event["kind"] == "SEAM":
                engine.begin_sample_seam(event["local_us"], event["source_date"])
                journal.drain(engine)
                continue
            if event["kind"] == "BOOK":
                if event["sequence_validated"]:
                    engine.receive_book(
                        ObservedBookBatch(
                            event["exchange_us"],
                            event["local_us"],
                            event["capture_order"],
                            event["native_update_id"],
                            event["bids"],
                            event["asks"],
                            event["known_bid_floor"],
                            event["known_ask_ceiling"],
                            True,
                            event["is_snapshot"],
                            event.get("changes"),
                            event.get("exchange_upper_us"),
                            event["exchange_precision"],
                        )
                    )
            else:
                native = event["data"]
                trade = canonical.get(native["t"])
                if trade is None:
                    if (
                        identity["source_day_mapping"][0]["logical_start_us"]
                        <= event["exchange_us"]
                        < end_us
                    ):
                        raise ValueError("UNBOUND_INTERIOR_NATIVE_TRADE")
                    continue
                if trade.trade_id in seen or not trade_timestamp_matches(
                    trade.time_us - event.get("clock_offset_us", 0), native["T"]
                ):
                    raise ValueError("CANONICAL_TRADE_BINDING_CHANGED")
                if (trade.price, trade.quantity, trade.buyer_maker) != (
                    D(native["p"]),
                    D(native["q"]),
                    native["m"],
                ):
                    raise ValueError("CANONICAL_TRADE_FIELDS_CHANGED")
                consumed = engine.receive_trade(
                    trade,
                    capture_time_us=event["local_us"],
                    capture_order=event["capture_order"],
                )
                if consumed < 0 or consumed > trade.quantity:
                    raise ValueError("M019_SHARED_TRADE_BUDGET_EXCEEDED")
                seen.add(trade.trade_id)
            journal.drain(engine)
            if event_count % 50_000 == 0:
                engine.validate_invariants()
                journal.durable()
                progress = engine.metrics()
                write_json(
                    output / "progress.json",
                    {
                        "RUN_STATUS": "RUNNING",
                        "VERDICT": "PENDING",
                        "DAY": "2025-01-01",
                        "MODEL": M019_MODEL_ID,
                        "CAPTURED_EVENTS": event_count,
                        "CYCLES_POSITIVE": progress["cycle_count"],
                        "TOTAL_MARKED_EQUITY": progress["equity"],
                    },
                )
                print(
                    json.dumps(
                        {
                            "model": M019_MODEL_ID,
                            "events": event_count,
                            "trades": len(seen),
                            "cycles": progress["cycle_count"],
                            "equity": progress["equity"],
                        }
                    ),
                    flush=True,
                )
        if seen != set(canonical):
            raise ValueError("CANONICAL_DAY_NOT_FULLY_DELIVERED")
        engine.finish(end_us)
        engine.validate_invariants()
        journal.drain(engine)
        journal_binding = journal.durable()
        audit = audit_m019_journal(output / "execution-audit.jsonl", canonical, engine)
        audit["journal"] = journal_binding
        audit["capital_invariants"] = "PASS"
        write_json(output / "all-fill-audit.json", audit)

        metrics = engine.metrics()
        mark = engine.current_bids[0][0] if engine.current_bids else None
        if mark is None:
            raise ValueError("M019_TERMINAL_MARK_UNAVAILABLE")
        usdt_final = engine.cash + engine.active_buy_notional
        usdc_marked = engine.inventory * mark
        equity = usdt_final + usdc_marked
        initial_usdt = D(100) - engine.endowment_quantity * D(engine.first_bid)
        open_lots = [lot for lot in engine.lots if lot.remaining > 0]
        hold_hours = [
            D((lot.closed_us if lot.closed_us is not None else end_us) - lot.entry_us)
            / D(3_600_000_000)
            for lot in engine.lots
        ]
        cycles_by_slot = Counter(int(row["source_slot"]) for row in engine.settlements)
        slot_scoreboard = m019_slot_scoreboard(engine, output / "execution-audit.jsonl", mark)
        reprices = sum(row["REPRICES"] for row in slot_scoreboard.values())
        capital_locked = sum((lot.remaining * lot.unit_cost for lot in open_lots), D(0))
        underwater_locked = sum(
            (lot.remaining * lot.unit_cost for lot in open_lots if mark < lot.unit_cost),
            D(0),
        )
        profitable_exit_inventory = sum(
            (lot.remaining * lot.unit_cost for lot in open_lots if lot.reserved > 0),
            D(0),
        )
        underwater_inventory = sum(
            (
                lot.remaining * lot.unit_cost
                for lot in open_lots
                if lot.reserved == 0
                and mark * (D(1) - D(engine.profile.maker_fee)) <= lot.unit_cost
            ),
            D(0),
        )
        dormant_inventory = capital_locked - (profitable_exit_inventory + underwater_inventory)
        top_slots = sorted(
            (
                (name, row["CYCLES"])
                for name, row in slot_scoreboard.items()
                if name.startswith("BUY_")
            ),
            key=lambda item: (-item[1], item[0]),
        )[:3]
        if audit["event_counts"].get("QUEUE_FLOW", 0) > audit["fills_checked"]:
            bottleneck_hint = "QUEUE"
        elif underwater_locked > D(".5") * equity:
            bottleneck_hint = "INVENTORY_LOCK"
        elif audit["post_only_rejections"]:
            bottleneck_hint = "POST_ONLY_REJECTION"
        elif engine.cash < engine.safe_min_notional:
            bottleneck_hint = "CAPITAL_SHORTAGE"
        else:
            bottleneck_hint = "UNDETERMINED"
        result = {
            **identity,
            "RUN_STATUS": "COMPLETE",
            "VERDICT": (
                "TARGET_ATTAINED"
                if engine.cycle_count >= 1000 and equity >= D(100)
                else "TARGET_NOT_ATTAINED"
            ),
            "DAY": "2025-01-01",
            "MODEL": M019_MODEL_ID,
            "CYCLES_POSITIVE": engine.cycle_count,
            "USDT_FINAL": str(usdt_final),
            "USDT_FREE": str(engine.cash),
            "USDT_RESERVED_FOR_BUYS": str(engine.active_buy_notional),
            "USDC_FINAL": str(engine.inventory),
            "USDC_MARKED_VALUE": str(usdc_marked),
            "TOTAL_FINAL_EQUITY": str(equity),
            "REALIZED_NET_PNL": str(engine.realized_profit),
            "UNREALIZED_PNL": str(engine.inventory * mark - engine.inventory_cost),
            "PASS_1000": engine.cycle_count >= 1000 and equity >= D(100),
            "PASS_2000": engine.cycle_count >= 2000 and equity >= D(100),
            "INITIAL_USDT": str(initial_usdt),
            "INITIAL_USDC": str(engine.endowment_quantity),
            "INITIAL_MARK": str(engine.first_bid),
            "SAFE_MIN_NOTIONAL": str(engine.safe_min_notional),
            "LOTS_OPEN": len(open_lots),
            "LOTS_OVER_1H": sum(value > 1 for value in hold_hours),
            "LOTS_OVER_2H": sum(value > 2 for value in hold_hours),
            "LOTS_OVER_6H": sum(value > 6 for value in hold_hours),
            "LOTS_OVER_24H": sum(value > 24 for value in hold_hours),
            "MAX_HOLD": str(max(hold_hours, default=D(0))),
            "ORDERS_REPOSITIONED": reprices,
            "ORDERS_SUBMITTED": len(engine.orders),
            "ACTIVE_SLOTS_AT_CUTOFF": len(engine.active_orders),
            "FEES": str(engine.fees),
            "ENDOWMENT_SALES_PNL_INCLUDED_IN_REALIZED": True,
            "CYCLES_BY_SLOT": {str(key): value for key, value in sorted(cycles_by_slot.items())},
            "SLOT_SCOREBOARD": slot_scoreboard,
            "TOP_3_SLOTS_BY_CYCLES": [
                {"slot": name, "cycles": cycles} for name, cycles in top_slots
            ],
            "CAPITAL_LOCKED": str(capital_locked),
            "UNDERWATER_CAPITAL_LOCKED": str(underwater_locked),
            "CAPITAL_BUCKETS_USDT_COST": {
                "FREE_CAPITAL": str(engine.cash),
                "WORKING_FREE_QUOTES": str(engine.active_buy_notional),
                "PROFITABLE_EXIT_INVENTORY": str(profitable_exit_inventory),
                "UNDERWATER_INVENTORY": str(underwater_inventory),
                "DORMANT_INVENTORY": str(dormant_inventory),
            },
            "MAIN_BOTTLENECK": "UNDETERMINED_PENDING_POST_RUN_AUTOPSY",
            "HEURISTIC_BOTTLENECK_HINT": bottleneck_hint,
            "DATA_INTEGRITY": validation,
            "AUDIT": audit,
            "ENGINE_METRICS": metrics,
            "AUDIT_SHA256": file_sha(output / "all-fill-audit.json"),
        }
        write_json(output / "summary.json", result)
        write_json(output / "terminal-engine-state.json", engine.checkpoint())
        return result
    except Exception as exc:
        journal.drain(engine)
        binding = journal.durable()
        write_json(
            output / "failure.json",
            {
                "status": "TECHNICAL_FAILURE",
                "error": str(exc),
                "identity": identity,
                "audit_prefix": binding,
                "captured_events": event_count,
            },
        )
        raise
    finally:
        journal.close()


def campaign_preflight(root=ROOT, model_id="M015"):
    selected_dates = require_owner_replay_approval(root, model_id)
    if Path.cwd().resolve() != root.resolve():
        raise ValueError("CANONICAL_REPOSITORY_CWD_REQUIRED")
    sha = published_sha()
    if subprocess.check_output(["git", "branch", "--show-current"], text=True).strip() != "main":
        raise ValueError("CANONICAL_MAIN_REQUIRED")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("PRE_EXECUTION_WORKTREE_NOT_CLEAN")
    if model_id not in ("M015", *DEADLINE_MODELS, M019_MODEL_ID):
        raise ValueError("UNREGISTERED_CAMPAIGN_MODEL")
    spec, protocol, review = campaign_design_paths(model_id)
    sources = (
        (
            *SOURCE_PATHS,
            Path("src/crypto_strategy_lab/microstructure/reserve_recovery_diagnostics.py"),
        )
        if model_id in DEADLINE_MODELS
        else M019_REVIEW_SOURCES
        if model_id == M019_MODEL_ID
        else SOURCE_PATHS
    )
    design_authorities = (M019_OWNER_DIRECTIVE,) if model_id == M019_MODEL_ID else ()
    for path in (
        *sources,
        spec,
        protocol,
        review,
        *design_authorities,
        MANIFEST,
        VALIDATION_REPORT,
        OWNER_WINDOW_AUTHORITY,
    ):
        published_bytes(path, sha)
    validate_review(review, sources)
    model = ModelRegistry().get(model_id)
    if model_id == M019_MODEL_ID:
        design = json.loads((root / spec).read_bytes())
        expected = {
            **design,
            "spec_sha256_lf": lf_sha(spec),
            "preregistration_sha256_lf": lf_sha(protocol),
            "owner_directive_sha256_lf": lf_sha(M019_OWNER_DIRECTIVE),
        }
        if dict(model.model) != expected or model.model_hash != compute_model_hash(expected):
            raise ValueError("M019_REGISTERED_DESIGN_MISMATCH")
        if (
            design.get("initial_total_equity") != "100"
            or design.get("buy_slots") != 6
            or design.get("sell_slots") != 6
            or design.get("negative_exit_allowed") is not False
            or design.get("source_dates") != ["2025-01-01"]
        ):
            raise ValueError("M019_OWNER_INVARIANT_MISMATCH")
    elif model_id in DEADLINE_MODELS:
        validate_registered_design(model, spec, protocol)
        if model.model["model_id"] != model_id:
            raise ValueError("DEADLINE_MODEL_ID_MISMATCH")
        if model_id == "M018" and (
            tuple(model.model["source_dates"][: len(selected_dates)]) != selected_dates
            or model.model["initial_stage_days"] != 1
            or model.model["max_stage_days"] != 3
        ):
            raise ValueError("REGISTERED_STAGE_WINDOW_MISMATCH")
    else:
        validate_registered_design(model)
    if model_id == "M015" and model.model_hash != MODEL_HASH:
        raise ValueError("CURRENT_MODEL_HASH_CHANGED")
    if file_sha(PROFILE_CONFIG) != PROFILE_CONFIG_SHA:
        raise ValueError("FROZEN_PROFILE_CHANGED")
    manifest = json.loads((root / MANIFEST).read_bytes())
    validation = json.loads((root / VALIDATION_REPORT).read_bytes())
    if validation.get("mode") != "ALL_DATA_GATES" or validation[
        "source_manifest_sha256"
    ] != file_sha(root / MANIFEST):
        raise ValueError("VALIDATION_MANIFEST_BINDING_MISMATCH")
    for collection in (manifest["dates"], validation["days"]):
        if sorted(item["date"] for item in collection) != list(AUTHORIZED_DATES):
            raise ValueError("EXACT_21_MONTHLY_DATES_REQUIRED")
    return sha, manifest, validation


def verify_published_day_evidence(entry, result, trade_manifest, root=ROOT):
    """Rehash evidence, preserving the original published validator identity."""
    day = entry["date"]
    binding = result["input_binding"]
    if (
        result.get("L2_DAY_VALID") is not True
        or binding.get("csv_only") is not False
        or binding.get("date") != day
    ):
        raise ValueError("FULL_VALID_DAY_EVIDENCE_REQUIRED")
    digest = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    if digest != result["input_sha256"]:
        raise ValueError("VALIDATION_INPUT_BINDING_CHANGED")
    expected_sources = {
        "scripts/validate_tardis_l2_samples.py",
        "src/crypto_strategy_lab/microstructure/tardis_l2.py",
        "src/crypto_strategy_lab/microstructure/serial_replay.py",
    }
    if set(binding["validator_lf_sha256"]) != expected_sources:
        raise ValueError("VALIDATOR_SOURCE_SET_CHANGED")
    for path, digest in binding["validator_lf_sha256"].items():
        original = subprocess.check_output(
            ["git", "show", f"{VALIDATOR_SOURCE_COMMIT}:{path}"], cwd=root
        )
        if hashlib.sha256(original.replace(b"\r\n", b"\n")).hexdigest() != digest:
            raise ValueError("PUBLISHED_VALIDATOR_SOURCE_MISMATCH")
    if file_sha(root / TRADE_MANIFEST) != binding["canonical_trade_manifest_sha256"]:
        raise ValueError("CANONICAL_MANIFEST_BINDING_CHANGED")
    csv = checked_path(root, entry["local_path"], day)
    if (
        csv.stat().st_size != entry["bytes"]
        or file_sha(csv) != entry["sha256"]
        or entry["sha256"] != binding["csv_sha256"]
    ):
        raise ValueError("CSV_EVIDENCE_CHANGED")
    slices = entry["raw_slices"]
    if len(slices) != 144 or {item["offset"] for item in slices} != set(range(0, 1440, 10)):
        raise ValueError("ALL_144_NATIVE_SLICES_REQUIRED")
    identities = []
    for item in slices:
        validate_slice_metadata(day, item)
        path = checked_path(root, item["local_path"], day, raw=True)
        if path.stat().st_size != item["bytes"] or file_sha(path) != item["sha256"]:
            raise ValueError("NATIVE_EVIDENCE_CHANGED")
        identities.append({"offset": item["offset"], "sha256": item["sha256"]})
    if sorted(identities, key=lambda item: item["offset"]) != binding["raw_slices"]:
        raise ValueError("NATIVE_BINDING_CHANGED")
    archives = [item for item in trade_manifest["archives"] if item["utc_date"] == day]
    if len(archives) != 1:
        raise ValueError("CANONICAL_DAY_NOT_UNIQUE")
    archive = archives[0]
    path = (root / archive["local_path"]).resolve()
    expected = (
        root / "data/raw/binance-microstructure/USDCUSDT/trades" / f"USDCUSDT-trades-{day}.zip"
    )
    if (
        path != expected.resolve()
        or path.stat().st_size != archive["size_bytes"]
        or file_sha(path) != archive["sha256"]
        or archive["sha256"] != binding["canonical_archive_sha256"]
    ):
        raise ValueError("CANONICAL_TRADE_EVIDENCE_CHANGED")
    return result


def stitched_mapping(dates=STITCHED_DATES):
    origin = datetime(2025, 1, 1, tzinfo=UTC)
    return [
        {
            "day_index": index,
            "source_date": day,
            "source_start_us": _datetime_to_micros(datetime.fromisoformat(day).replace(tzinfo=UTC)),
            "logical_start_us": _datetime_to_micros(origin + timedelta(days=index)),
        }
        for index, day in enumerate(dates)
    ]


def mapped_tick_catalog(mapping):
    periods, transitions = [], []
    original = USDCUSDT_TICK_CATALOG
    for item in mapping:
        source = datetime.fromisoformat(item["source_date"]).replace(tzinfo=UTC)
        end = source + timedelta(days=1)
        offset = timedelta(microseconds=item["logical_start_us"] - item["source_start_us"])
        for period in original.periods:
            left, right = max(source, period.start), min(end, period.end_exclusive or end)
            if left < right:
                periods.append(
                    TickPeriod(
                        start=left + offset,
                        end_exclusive=right + offset,
                        tick_size=period.tick_size,
                        evidence_class="MAPPED_SOURCE_DAY:" + item["source_date"],
                    )
                )
        for transition in original.transitions:
            left, right = max(source, transition.start), min(end, transition.end_exclusive)
            if left < right:
                transitions.append(
                    TickTransition(
                        start=left + offset,
                        end_exclusive=right + offset,
                        allowed_tick_sizes=transition.allowed_tick_sizes,
                        evidence=transition.evidence,
                    )
                )
    periods[-1] = periods[-1].model_copy(update={"end_exclusive": None})
    return TickCatalog(
        periods=tuple(periods),
        transitions=tuple(transitions),
        source_url=original.source_url,
        source_published_at=original.source_published_at,
        price_quantum=original.price_quantum,
    )


def build_stitched_inputs(history, config, mapping):
    """Only twelve source days enter this exact, fixed-point selector tape."""
    catalog = mapped_tick_catalog(mapping)
    rows = []
    for item in mapping:
        first = datetime.fromisoformat(item["source_date"]).replace(tzinfo=UTC)
        end = first + timedelta(days=1)
        # Manifest coverage begins at the first actual print, not midnight.
        # Clamp only archive reading; the logical day and source offset stay fixed.
        read_start = max(first, history.first_timestamp)
        selected = select_history_archives(history, start=read_start, end_exclusive=end)
        if len(selected) != 1 or selected[0].cadence != "daily":
            raise ValueError("EXACT_SOURCE_DAY_ARCHIVE_REQUIRED")
        if file_sha(Path(selected[0].local_path)) != selected[0].sha256:
            raise ValueError("CANONICAL_ARCHIVE_CHANGED")
        offset = item["logical_start_us"] - item["source_start_us"]
        for event in iter_history(history, start=read_start, end_exclusive=end):
            rows.append((_datetime_to_micros(event.timestamp) + offset, event))
    tape = SerialTape.from_events(
        (
            (datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=stamp), event.price)
            for stamp, event in rows
        ),
        tick_size=catalog.price_quantum,
        tick_catalog=catalog,
    )
    canonical = {}
    for encoded, (stamp, event) in zip(tape.events, rows, strict=True):
        if event.trade_id in canonical:
            raise ValueError("NATIVE_TRADE_ID_COLLISION")
        canonical[event.trade_id] = Trade(
            stamp, event.trade_id, event.price, event.quantity, event.buyer_is_maker, int(encoded)
        )
    parent = frozen_m007_strategy()
    scenario = SerialScenarioConfig(
        scenario_id="PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2",
        tick_size=tape.tick_size,
        historical_tick_catalog_hash=catalog.catalog_hash,
        historical_tick_source_url=catalog.source_url,
        historical_tick_policy="CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
    )
    runtime = RecoveryReserveRuntime(
        ReserveConfig(D(".02"), 1, D(10), D("2.5")),
        parent,
        scenario,
        tape,
        tape.timelines(catalog.absolute_distances(parent.distances)),
        catalog,
    )
    item = next(row for row in config["profiles"] if row["profile"]["name"] == PROFILE)
    profile, envelope = (
        typed(ExecutionProfile, item["profile"]),
        typed(BookEnvelope, item["envelope"]),
    )
    periods = [
        (row["start_us"], row["end_us"], typed(SymbolRules, row["rule"])) for row in config["rules"]
    ]
    origin = mapping[0]["logical_start_us"]

    def rules_at(timestamp):
        index = min((timestamp - origin) // DAY_US, len(mapping) - 1)
        if index < 0:
            raise ValueError("RULE_BEFORE_STITCHED_ORIGIN")
        source = mapping[index]["source_start_us"] + timestamp - mapping[index]["logical_start_us"]
        if source < periods[0][0] and mapping[index]["source_date"].startswith("2025-"):
            rule = periods[0][2]
        else:
            rule = next((rule for first, last, rule in periods if first <= source < last), None)
            if rule is None:
                raise ValueError("NO_SOURCE_DAY_RULE")
        logical = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=timestamp)
        return replace(rule, tick_size=catalog.tick_size_at(logical))

    return runtime, profile, envelope, rules_at, canonical


def stitched_events(entries, mapping):
    for item in mapping:
        index, day = item["day_index"], item["source_date"]
        offset = item["logical_start_us"] - item["source_start_us"]
        yield {
            "kind": "SEAM",
            **item,
            "local_us": item["logical_start_us"],
            "previous_source_date": mapping[index - 1]["source_date"] if index else None,
            "clock_offset_us": offset,
        }
        for event in iter_native_events(raw_lines(ROOT, day, entries[day]["raw_slices"])):
            mapped = {
                **event,
                "clock_offset_us": offset,
                "local_us": event["local_us"] + offset,
                "exchange_us": event["exchange_us"] + offset,
                "capture_order": index * 1_000_000_000 + event["capture_order"],
            }
            if event["capture_order"] >= 1_000_000_000:
                raise ValueError("SOURCE_CAPTURE_ORDINAL_OVERFLOW")
            if "exchange_upper_us" in event:
                mapped["exchange_upper_us"] = event["exchange_upper_us"] + offset
            yield mapped
    yield {
        "kind": "SEAM",
        "day_index": len(mapping),
        "source_date": "END",
        "previous_source_date": mapping[-1]["source_date"],
        "local_us": mapping[-1]["logical_start_us"] + DAY_US,
    }


def run(model_id="M015"):
    selected_dates = require_owner_replay_approval(model_id=model_id)
    sha, manifest, validation = campaign_preflight(model_id=model_id)
    if model_id != M019_MODEL_ID and "SYNTHETIC_CONSECUTIVE_12D" not in PROTOCOL.read_text():
        raise ValueError("STITCHED_PROTOCOL_NOT_PUBLISHED")
    config = json.loads(PROFILE_CONFIG.read_bytes())
    if file_sha(TRADE_MANIFEST) != manifest["canonical_trade_manifest_sha256"]:
        raise ValueError("CANONICAL_TRADE_MANIFEST_CHANGED")
    history = HistoryManifest.model_validate_json(TRADE_MANIFEST.read_bytes())
    trade_manifest = json.loads(TRADE_MANIFEST.read_bytes())
    entries = {item["date"]: item for item in manifest["dates"]}
    days = {item["date"]: item for item in validation["days"]}
    verified = [
        verify_published_day_evidence(entries[day], days[day], trade_manifest)
        for day in selected_dates
    ]
    mapping = stitched_mapping(selected_dates)
    window_name = (
        "OWNER_GATED_DAY1" if model_id in {"M018", M019_MODEL_ID} else "SYNTHETIC_CONSECUTIVE_12D"
    )
    with campaign_writer_lock():
        runtime, profile, envelope, rules_at, canonical = build_stitched_inputs(
            history, config, mapping
        )
        names = ("PRICE_PRIORITY",) if model_id in (*DEADLINE_MODELS, M019_MODEL_ID) else ENVELOPES
        model = ModelRegistry().get(model_id)
        for name in names:
            identity = {
                "date": window_name,
                "model_id": model_id,
                "model_hash": model.model_hash,
                "capital_mode": "COMPOUNDING",
                "priority_trade_through": True,
                "published_config_sha": sha,
                "expected_trade_count": len(canonical),
                "protocol_sha256": file_sha(campaign_design_paths(model_id)[1]),
                "preflight_review_sha256": file_sha(campaign_design_paths(model_id)[2]),
                "data_manifest_sha256": file_sha(MANIFEST),
                "validation_source_commit": VALIDATOR_SOURCE_COMMIT,
                "source_sha256_lf": {
                    str(path): lf_sha(path)
                    for path in (M019_REVIEW_SOURCES if model_id == M019_MODEL_ID else SOURCE_PATHS)
                },
                "execution_envelope": name,
                "source_day_mapping": mapping,
                "WARMUP_AVAILABLE_US": 0,
                "COLD_START": True,
                "CLOCK_MAPPING": "SOURCE_DAY_OFFSET_TO_CONSECUTIVE_LOGICAL_DAY",
                "owner_window_sha256_lf": lf_sha(OWNER_WINDOW_AUTHORITY),
            }
            if model_id in DEADLINE_MODELS:
                identity["deadline_policy_hash"] = model.model["deadline_policy_hash"]
                debt_path = Path(
                    "src/crypto_strategy_lab/microstructure/reserve_recovery_diagnostics.py"
                )
                identity["source_sha256_lf"][str(debt_path)] = lf_sha(debt_path)
            if model_id == "M018":
                identity["entry_admission_policy_hash"] = model.model["entry_admission_policy_hash"]
            if model_id == M019_MODEL_ID:
                identity.update(
                    initial_total_equity="100",
                    initial_split_rule=model.model["initial_split_rule"],
                    buy_slots=6,
                    sell_slots=6,
                    negative_exit_allowed=False,
                    liquidity_consumption="GLOBAL_ONCE_ACROSS_ALL_SLOTS",
                )
            identity["run_hash"] = json_hash(identity)
            bound = {
                "input_sha256": json_hash([item["input_sha256"] for item in verified]),
                "CSV_ROWS": sum(item.get("CSV_ROWS", 0) for item in verified),
            }
            output = (
                (OUTPUT / model_id if model_id in (*DEADLINE_MODELS, M019_MODEL_ID) else OUTPUT)
                / window_name
                / name
            )
            if model_id == M019_MODEL_ID:
                engine = AdaptiveStablecoinLadder(
                    profile,
                    rules_at(mapping[0]["logical_start_us"]),
                    lane_id="M019-6x6",
                    candidate=M019_MODEL_ID,
                )
                execute_m019_experiment(
                    engine,
                    canonical,
                    stitched_events(entries, mapping),
                    bound,
                    identity,
                    output,
                )
            else:
                replay = MeasuredReplay(
                    runtime,
                    profile,
                    rules_at,
                    envelope,
                    start_us=mapping[0]["logical_start_us"],
                    end_us=mapping[-1]["logical_start_us"] + DAY_US,
                    identity=identity,
                    envelope=name,
                )
                execute_verified_experiment(
                    replay,
                    canonical,
                    stitched_events(entries, mapping),
                    bound,
                    identity,
                    output,
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", choices=("M015", *DEADLINE_MODELS, M019_MODEL_ID), default="M015"
    )
    run(parser.parse_args().model)
