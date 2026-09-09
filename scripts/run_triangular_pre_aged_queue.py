"""Single-run, published-source M024 three-hour normalized FIFO mechanics probe."""

from __future__ import annotations

import json
import os
import re
import subprocess
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelStatus, compute_model_hash
from scripts import run_serial_hot_line as parent_runner
from scripts.register_triangular_pre_aged_queue import (
    OWNER as OWNER_DIRECTIVE,
)
from scripts.register_triangular_pre_aged_queue import (
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
MODEL_ID = "M024"
START, END = parent_runner.START, parent_runner.END
START_US, END_US = parent_runner.START_US, parent_runner.END_US
OWNER_WINDOW = Path("docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md")
REVIEW = Path("reports/usdcusdt/M024-preflight-independent-review.md")
JOURNAL = Path("docs/research/M024_JOURNAL.md")
PARENT_RESULT = Path("reports/usdcusdt/M023-3h-result.json")
OUTPUT = Path("artifacts/usdcusdt/l2-monthly-samples/M024/OWNER_GATED_3H/PRICE_PRIORITY")
RESULT = Path("reports/usdcusdt/M024-3h-result.json")
SOURCE_PATHS = tuple(
    dict.fromkeys(
        (
            Path("scripts/run_triangular_pre_aged_queue.py"),
            Path("scripts/register_triangular_pre_aged_queue.py"),
            Path("src/crypto_strategy_lab/microstructure/triangular_pre_aged_queue.py"),
            Path("tests/test_triangular_pre_aged_queue.py"),
            Path("tests/test_run_triangular_pre_aged_queue.py"),
            Path("scripts/run_b10_reality.py"),
            Path("src/crypto_strategy_lab/microstructure/b10_reality.py"),
            *parent_runner.SOURCE_PATHS,
        )
    )
)
M023_INPUT_BINDING = {
    "bounded_slice_count": 18,
    "bounded_slice_offsets": list(range(0, 180, 10)),
    "bounded_slice_sha256": "9c1cd1a409ea4282ff85365166be13afbdf0f1c7759502a420848114d9a36c5a",
    "canonical_trade_count": 29538,
    "canonical_first_trade_id": 206597089,
    "canonical_last_trade_id": 206626626,
}


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def require_owner_gate(root: Path = ROOT) -> None:
    try:
        authority = (root / OWNER_WINDOW).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("M024_OWNER_GATE_REQUIRED:AUTHORITY_UNAVAILABLE") from exc
    for key, value in {
        "APPROVED_COMPARISON_DAYS": "1",
        "EXTENSION_AUTHORIZED": "false",
        "NEW_REPLAY_AUTHORIZED_NOW": "true",
        "AUTHORIZED_MODEL": MODEL_ID,
    }.items():
        if re.findall(rf"^{key}=(.*)$", authority, flags=re.MULTILINE) != [value]:
            raise ValueError(f"M024_OWNER_GATE_REQUIRED:{key}")


def validate_frozen_design(design: dict[str, Any]) -> None:
    validate_registration_design(design)


def _assert_unused_output(output: Path = OUTPUT, result: Path = RESULT) -> None:
    if output.exists() or result.exists():
        raise ValueError("EXISTING_M024_EXPERIMENT_PRESERVED")


def _assert_published_head(sha: str) -> None:
    if _git_output("status", "--porcelain"):
        raise ValueError("PRE_EXECUTION_WORKTREE_NOT_CLEAN")
    if _git_output("branch", "--show-current") != "main":
        raise ValueError("CANONICAL_MAIN_REQUIRED")
    if any(_git_output("rev-parse", ref) != sha for ref in ("HEAD", "origin/main")):
        raise ValueError("M024_REQUIRES_PUBLISHED_HEAD")


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
        raise ValueError("M024_REQUIRES_CREATED_STATUS")
    model = registry.get(MODEL_ID)
    if dict(model.model) != expected or model.model_hash != compute_model_hash(expected):
        raise ValueError("M024_REGISTERED_DESIGN_MISMATCH")
    if registry.current_status("M023") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M024_REQUIRES_PRESERVED_INCONCLUSIVE_M023")
    return sha, json.loads(MANIFEST.read_bytes()), json.loads(VALIDATION_REPORT.read_bytes())


def bounded_inputs(manifest: dict[str, Any], validation: dict[str, Any]):
    """Reuse M023's immutable three-hour reader, then bind its exact input identity."""
    profile, canonical, slices, evidence = parent_runner.bounded_inputs(manifest, validation)
    for key, value in M023_INPUT_BINDING.items():
        if evidence.get(key) != value:
            raise ValueError(f"M024_M023_INPUT_BINDING_MISMATCH:{key}")
    if tuple(item["offset"] for item in slices) != tuple(range(0, 180, 10)):
        raise ValueError("M024_EXACT_FIRST_18_SLICES_REQUIRED")
    if (
        profile.name != "B_REALISTIC_CONSERVATIVE"
        or profile.latency_us != 1179525
        or profile.cancel_latency_us != 1179525
        or profile.maker_fee != D(0)
        or profile.taker_fee != D(0)
    ):
        raise ValueError("M024_FROZEN_PROFILE_CHANGED")
    if len(canonical) != 29538 or any(
        not START_US <= trade.time_us < END_US for trade in canonical.values()
    ):
        raise ValueError("M024_CANONICAL_TRADE_SCOPE_MISMATCH")
    return profile, canonical, slices, {**evidence, "m024_end_us": END_US}


def bounded_native_events(slices):
    if tuple(item["offset"] for item in slices) != tuple(range(0, 180, 10)):
        raise ValueError("M024_EXACT_FIRST_18_SLICES_REQUIRED")
    for event in parent_runner.bounded_native_events(slices):
        if not (
            START_US <= event["local_us"] < END_US and START_US <= event["exchange_us"] < END_US
        ):
            raise ValueError("M024_NATIVE_EVENT_ESCAPED_3H_BOUND")
        yield event


def make_probe(profile):
    # The kernel is intentionally imported only after execution gates and input checks.
    from crypto_strategy_lab.microstructure.triangular_pre_aged_queue import (
        TriangularPreAgedQueueProbe,
    )

    return TriangularPreAgedQueueProbe(
        start_us=START_US,
        end_us=END_US,
        latency_us=profile.latency_us,
        cancel_latency_us=profile.cancel_latency_us,
    )


def independent_execution_audit(rows, terminal, canonical, metrics):
    """Reconstruct physical ownership and FIFO independently of the kernel counters."""

    def require(condition, reason):
        if not condition:
            raise ValueError(f"M024_AUDIT_{reason}")

    state = terminal.get("state")
    require(
        isinstance(state, dict) and terminal.get("sha256") == canonical_hash(state),
        "TERMINAL_HASH_MISMATCH",
    )
    require(terminal.get("schema") == "M024_TRIANGULAR_PRE_AGED_QUEUE_V1", "SCHEMA")
    config = state["config"]
    require(
        config
        == {
            "start_us": START_US,
            "end_us": END_US,
            "latency_us": 1179525,
            "cancel_latency_us": 1179525,
            "max_open_orders": 200,
        },
        "CONFIG",
    )
    require(canonical_hash(state["audit"]) == canonical_hash(rows), "LEDGER_BINDING")
    zero = D(0)
    cash, free, inventory, reserved_quote, reserved_base = D("74.9900"), D(75), zero, zero, zero
    profit, disposal_profit, growth, growth_earned = zero, zero, zero, zero
    orders, groups, delivered, debits, completions, cycle_ids = {}, {}, {}, {}, {}, set()
    lots, funded = {}, set()
    shadow_rows = []
    max_open = fill_count = initialized = 0
    last_time = START_US

    def group_key(order):
        return order["side"], D(order["price"])

    def remove(order_id):
        for segment in groups.get(group_key(orders[order_id]), []):
            if order_id in segment["ids"]:
                segment["ids"].remove(order_id)

    def locked_sell_proceeds(excluded_source=None):
        total = zero
        for source_id, lot in lots.items():
            source = orders[source_id]
            if (
                source["side"] != "SELL"
                or source_id == excluded_source
                or lot["stage"] in {"RESTORED", "RECYCLED"}
            ):
                continue
            backed = any(
                order["role"] == "RETURN"
                and order["direction"] == "SELL_FIRST"
                and order["source_order_id"] == source_id
                and order["status"] in {"PENDING", "ACTIVE", "CANCEL_PENDING", "FILLED"}
                for order in orders.values()
            )
            if not backed:
                total += lot["quantity"] * lot["basis"]
        return total

    def physical_trade(row):
        source = str(row["source_id"])
        trade = canonical.get(int(source)) if source.isdigit() else None
        require(trade is not None and source not in delivered, "NONCANONICAL_SOURCE")
        quantity = D(row["quantity"])
        require(quantity > 0, "NONPOSITIVE_DEBIT")
        debits[source] = debits.get(source, zero) + quantity
        require(debits[source] <= trade.quantity, "GLOBAL_TRADE_BUDGET")
        require(trade.time_us <= row["time_us"], "FUTURE_PRINT")
        return trade, quantity

    for row in rows:
        event, now = row["event"], int(row["time_us"])
        require(START_US <= now < END_US and now >= last_time, "EVENT_CLOCK")
        last_time = now
        if event == "SUBMIT":
            oid, quantity, price = int(row["order_id"]), D(row["quantity"]), D(row["price"])
            require(oid not in orders and quantity == 1 and price > 0, "ORDER_ID_OR_QUANTITY")
            require(price % D(".0001") == 0 and row["side"] in {"BUY", "SELL"}, "FILTERS")
            require(row["active_us"] == now + config["latency_us"], "SUBMISSION_LATENCY")
            order = {
                **row,
                "filled": zero,
                "status": "PENDING",
                "activation": None,
                "reserved_quote": zero,
                "reserved_base": zero,
                "cancel_us": None,
            }
            if row["role"] == "RETURN":
                source = orders.get(row["source_order_id"])
                require(
                    source is not None
                    and source["status"] == "FILLED"
                    and source["role"] == "ENTRY",
                    "RETURN_WITHOUT_OWNED_ENTRY",
                )
                require(
                    quantity == 1
                    and source["filled"] == quantity
                    and source["order_id"] in lots
                    and lots[source["order_id"]]["quantity"] == quantity,
                    "RETURN_QUANTITY_OR_LOT",
                )
                require(
                    source["side"] != row["side"]
                    and source["direction"] == row["direction"]
                    and source["column"] == row["column"],
                    "RETURN_OWNERSHIP",
                )
                require(
                    not any(
                        o["role"] == "RETURN"
                        and o["source_order_id"] == source["order_id"]
                        and o["status"]
                        not in {"CANCELED", "REJECTED_POST_ONLY", "REJECTED_COVERAGE"}
                        for o in orders.values()
                    ),
                    "DUPLICATE_RETURN",
                )
            else:
                require(row["role"] == "ENTRY" and quantity == 1, "UNKNOWN_ORDER_ROLE")
            if row["side"] == "BUY":
                excluded_source = (
                    row["source_order_id"]
                    if row["role"] == "RETURN" and row["direction"] == "SELL_FIRST"
                    else None
                )
                locked = locked_sell_proceeds(excluded_source)
                if row["capital_source"] == "OWN":
                    require(
                        cash - growth - locked >= price * quantity,
                        "OWN_SPENDS_GROWTH_OR_LOCKED_PROCEEDS",
                    )
                else:
                    require(cash - locked >= price * quantity, "GROWTH_SPENDS_LOCKED_PROCEEDS")
                cash -= price * quantity
                reserved_quote += price * quantity
                order["reserved_quote"] = price * quantity
                if row["capital_source"] == "GROWTH":
                    growth -= price * quantity
            else:
                if row["role"] == "RETURN":
                    inventory -= quantity
                else:
                    free -= quantity
                reserved_base += quantity
                order["reserved_base"] = quantity
            orders[oid] = order
            count = sum(
                o["status"] in {"PENDING", "ACTIVE", "CANCEL_PENDING"} for o in orders.values()
            )
            max_open = max(max_open, count)
            require(count <= 200, "ORDER_CAP")
        elif event == "ACTIVATED":
            oid = int(row["order_id"])
            order = orders[oid]
            require(order["status"] == "PENDING" and now >= order["active_us"], "ACTIVATION")
            require(group_key(row) == group_key(order), "ACTIVATION_PRICE")
            require(
                row["native_book_upper_us"] is not None and row["native_book_upper_us"] <= now,
                "ACTIVATION_BOOK_CLOCK",
            )
            segments = groups.setdefault(group_key(order), [])
            represented = sum((s["remaining"] for s in segments), zero)
            same = bool(segments and segments[-1]["time"] == now)
            added = zero if same else max(zero, D(row["public_queue_ahead"]) - represented)
            require(D(row["public_barrier_added"]) == added and added >= 0, "PUBLIC_BARRIER")
            if not same:
                segments.append({"time": now, "barrier": added, "remaining": added, "ids": []})
            predecessor = sum((1 - orders[i]["filled"] for s in segments for i in s["ids"]), zero)
            segments[-1]["ids"].append(oid)
            require(
                D(row["public_remaining"]) == represented + added
                and D(row["queue_ahead_at_activation"]) == represented + added + predecessor,
                "QUEUE_AT_ACTIVATION",
            )
            order.update(status="ACTIVE", activation=row)
        elif event == "PUBLIC_QUEUE_CONSUMED":
            trade, quantity = physical_trade(row)
            key = group_key(row)
            require(
                trade.price == key[1] and trade.buyer_maker == (key[0] == "BUY"),
                "PUBLIC_PRINT_ELIGIBILITY",
            )
            segments = groups[key]
            segment = next(s for s in segments if s["time"] == row["cohort_activation_us"])
            require(
                trade.time_us > segment["time"] and quantity <= segment["remaining"],
                "PUBLIC_DEBIT_OR_CLOCK",
            )
            earlier = segments[: segments.index(segment)]
            require(not any(s["remaining"] > 0 or s["ids"] for s in earlier), "PUBLIC_FIFO")
            segment["remaining"] -= quantity
        elif event == "FILL":
            trade, quantity = physical_trade(row)
            oid = int(row["order_id"])
            order = orders[oid]
            activation = order["activation"]
            require(
                order["status"] in {"ACTIVE", "CANCEL_PENDING"} and activation is not None,
                "FILL_INACTIVE",
            )
            require(
                trade.time_us > activation["time_us"]
                and trade.time_us >= activation["native_book_upper_us"],
                "FILL_BEFORE_ACTIVATION",
            )
            require(order["cancel_us"] is None or now < order["cancel_us"], "FILL_AFTER_CANCEL_ACK")
            side, price = group_key(order)
            require(
                group_key(row) == (side, price)
                and trade.buyer_maker == (side == "BUY")
                and (trade.price <= price if side == "BUY" else trade.price >= price),
                "FILL_PRINT_ELIGIBILITY",
            )
            eligible = [
                o
                for o in orders.values()
                if o["status"] in {"ACTIVE", "CANCEL_PENDING"}
                and o["activation"] is not None
                and o["side"] == side
                and (
                    trade.price <= D(o["price"]) if side == "BUY" else trade.price >= D(o["price"])
                )
            ]
            eligible.sort(
                key=lambda o: (
                    (-D(o["price"]) if side == "BUY" else D(o["price"])),
                    o["activation"]["time_us"],
                    o["time_us"],
                    o["order_id"],
                )
            )
            require(eligible and eligible[0]["order_id"] == oid, "OWN_FIFO")
            if trade.price == price:
                for segment in groups[(side, price)]:
                    require(segment["remaining"] == 0, "FILL_BEFORE_PUBLIC_QUEUE")
                    if oid in segment["ids"]:
                        break
            require(order["filled"] + quantity <= D(order["quantity"]), "ORDER_OVERFILLED")
            order["filled"] += quantity
            fill_count += 1
            if side == "BUY":
                reserved_quote -= quantity * price
                order["reserved_quote"] -= quantity * price
                if order["role"] == "ENTRY":
                    inventory += quantity
                else:
                    free += quantity
            else:
                reserved_base -= quantity
                order["reserved_base"] -= quantity
                cash += quantity * price
            if order["role"] == "ENTRY":
                lot = lots.setdefault(
                    oid,
                    {
                        "quantity": zero,
                        "basis": price,
                        "asset_basis": D(order.get("asset_basis", "0")) or price,
                        "created_us": now,
                        "stage": "PARTIAL_HOLDING" if side == "BUY" else "PARTIAL_SOLD",
                        "closed_quantity": zero,
                        "restored_cost": zero,
                    },
                )
                lot["quantity"] += quantity
            else:
                lot = lots[order["source_order_id"]]
                lot["closed_quantity"] += quantity
                if side == "BUY":
                    lot["restored_cost"] += quantity * price
                    lot["stage"] = "RESTORING"
                else:
                    lot["stage"] = "CLOSING"
            if side == "SELL":
                require(
                    D(order["asset_basis"]) == 0 or price > lot["asset_basis"],
                    "NEGATIVE_EXIT_FILL",
                )
                disposal_profit += quantity * (price - lot["asset_basis"])
            if order["filled"] == D(order["quantity"]):
                order["status"] = "FILLED"
                completions[oid] = now
                remove(oid)
                if order["role"] == "ENTRY":
                    lot["stage"] = "HOLDING" if side == "BUY" else "SOLD"
        elif event == "CANCEL_REQUEST":
            order = orders[int(row["order_id"])]
            require(
                order["status"] in {"PENDING", "ACTIVE"} and order["filled"] == 0,
                "CANCEL_PARTIAL_OR_DUPLICATE",
            )
            require(row["effective_us"] == now + config["cancel_latency_us"], "CANCEL_LATENCY")
            order.update(status="CANCEL_PENDING", cancel_us=row["effective_us"])
        elif event in {
            "CANCEL_ACK",
            "REJECTED_POST_ONLY",
            "REJECTED_COVERAGE",
            "REJECTED_SELF_CROSS",
            "REJECTED_NEGATIVE_EXIT",
        }:
            order = orders[int(row["order_id"])]
            if event == "CANCEL_ACK":
                require(
                    order["status"] == "CANCEL_PENDING" and now >= order["cancel_us"],
                    "CANCEL_ACK_CLOCK",
                )
            else:
                require(order["status"] == "PENDING" and now >= order["active_us"], "REJECTION")
            quote, base = order["reserved_quote"], order["reserved_base"]
            reserved_quote -= quote
            reserved_base -= base
            cash += quote
            if order["capital_source"] == "GROWTH":
                growth += quote
            if order["side"] == "SELL" and order["role"] == "RETURN":
                inventory += base
            else:
                free += base
            order.update(
                status=(
                    "CANCELED_PARTIAL"
                    if event == "CANCEL_ACK" and order["filled"] > 0
                    else ("CANCELED" if event == "CANCEL_ACK" else event)
                ),
                reserved_quote=zero,
                reserved_base=zero,
            )
            remove(order["order_id"])
        elif event == "CYCLE":
            oid = int(row["order_id"])
            order = orders[oid]
            source = orders[order["source_order_id"]]
            require(
                oid not in cycle_ids
                and order["status"] == "FILLED"
                and order["role"] == "RETURN"
                and source["status"] == "FILLED",
                "INCOMPLETE_OR_DUPLICATE_CYCLE",
            )
            expected = D(order["quantity"]) * (D(order["price"]) - D(source["price"])) * (
                1 if source["side"] == "BUY" else -1
            )
            require(expected >= D(".0001") and D(row["profit"]) == expected, "NONPOSITIVE_CYCLE")
            require(row["source_order_id"] == source["order_id"], "CYCLE_SOURCE")
            profit += expected
            growth += expected
            growth_earned += expected
            cycle_ids.add(oid)
            lot = lots[source["order_id"]]
            if source["side"] == "BUY":
                lot["stage"] = "CLOSED"
            else:
                if lot["closed_quantity"] > 0:
                    lot["asset_basis"] = lot["restored_cost"] / lot["closed_quantity"]
                lot["stage"] = "RESTORED"
        elif event == "GROWTH_CELL_FUNDED":
            oid = int(row["order_id"])
            order = orders[oid]
            require(
                oid not in funded
                and order["capital_source"] == "GROWTH"
                and order["side"] == "BUY"
                and D(row["amount"]) == D(order["price"]),
                "GROWTH_FUNDING",
            )
            funded.add(oid)
        elif event == "PRINCIPAL_RECYCLED":
            recycled = orders[int(row["order_id"])]
            completed_return = orders[int(row["source_order_id"])]
            require(recycled["cell_id"] == completed_return["cell_id"], "RECYCLE_CELL")
            if completed_return["direction"] == "SELL_FIRST":
                lots[completed_return["source_order_id"]]["stage"] = "RECYCLED"
        elif event == "TRIANGLE_INITIALIZED":
            initialized += 1
            require(
                D(row["initial_usdt"]) == D("74.9900")
                and D(row["initial_usdc"]) == 75
                and len(orders) == 150,
                "INITIAL_CAPITAL_OR_GEOMETRY",
            )
            for order in orders.values():
                rank = order["level"]
                expected = (
                    D("1.0020") - D(rank) * D(".0001")
                    if order["side"] == "BUY"
                    else D("1.0019") + D(rank) * D(".0001")
                )
                require(
                    1 <= rank <= 50
                    and 1 <= order["column"] <= (2 if rank <= 25 else 1)
                    and D(order["price"]) == expected,
                    "INITIAL_GEOMETRY",
                )
                require(
                    D(order["asset_basis"])
                    == (D("1.0019") if order["side"] == "SELL" else 0),
                    "INITIAL_ASSET_BASIS",
                )
            require(
                len({(o["side"], o["level"], o["column"]) for o in orders.values()}) == 150,
                "INITIAL_DUPLICATE_CELL",
            )
        elif event == "TRADE":
            tid = str(row["trade_id"])
            trade = canonical.get(int(tid)) if tid.isdigit() else None
            require(trade is not None and tid not in delivered, "TRADE_COVERAGE")
            require(
                row["native_time_us"] == trade.time_us
                and D(row["price"]) == trade.price
                and row["buyer_maker"] is trade.buyer_maker
                and D(row["original_quantity"]) == trade.quantity,
                "CANONICAL_PRINT",
            )
            require(D(row["consumed_quantity"]) == debits.get(tid, zero), "TRADE_CONSUMPTION")
            if row.get("blocked_future_book"):
                require(
                    D(row["consumed_quantity"]) == 0
                    and row["current_book_upper_us"] > row["native_time_us"],
                    "FUTURE_BOOK_BLOCK",
                )
            delivered[tid] = row
        elif event in {
            "SHADOW_ACTIVATED",
            "SHADOW_REJECTED",
            "SHADOW_TRADE_APPLIED",
            "SHADOW_FILL",
        }:
            shadow_rows.append(row)
            if event == "SHADOW_TRADE_APPLIED":
                source = str(row["source_id"])
                trade = canonical.get(int(source)) if source.isdigit() else None
                total = D(row["public_debit"]) + D(row["own_debit"]) + D(row["fill_debit"])
                require(
                    trade is not None
                    and row["native_time_us"] == trade.time_us
                    and D(row["price"]) == trade.price
                    and D(0) < total <= trade.quantity
                    and D(row["original_quantity"]) == trade.quantity,
                    "SHADOW_CANONICAL_DEBIT",
                )
        elif event == "PARTIAL_LOT_SUBSTEP_LOCKED":
            oid = int(row["order_id"])
            order = orders[oid]
            lot = lots[oid]
            require(
                order["status"] == "CANCELED_PARTIAL"
                and D(0) < order["filled"] < D(order["quantity"])
                and D(row["quantity"]) == order["filled"]
                and D(row["minimum_order_quantity"]) == 1
                and row["cycle_counted"] is False
                and not any(o["source_order_id"] == oid for o in orders.values()),
                "INVALID_SUBSTEP_LOCK",
            )
            lot["stage"] = (
                "SUBSTEP_INVENTORY_LOCKED"
                if order["side"] == "BUY"
                else "SUBSTEP_RETURN_DEBT_LOCKED"
            )
        elif event not in {
            "RETURN_DEFERRED",
            "RETURN_WAITING_FOR_FREE_CANCEL",
            "RETURN_WAITING_FOR_HEADROOM_CANCEL",
            "PRINCIPAL_RECYCLE_DEFERRED",
            "ROLLING_CANCEL_REQUESTED",
            "ROLLING_REPLACEMENT_SUBMITTED",
            "ROLLING_PARTIAL_CANCEL_ACK",
            "GROWTH_CELL_BLOCKED_ASSET",
        }:
            require(False, f"UNKNOWN_EVENT:{event}")
        require(
            min(cash, free, inventory, reserved_quote, reserved_base, growth) >= 0,
            "NEGATIVE_OWNERSHIP_OR_GROWTH",
        )
        require(growth <= cash - locked_sell_proceeds(), "GROWTH_POOL_NOT_FREE_CASH")

    require(initialized == 1, "INITIALIZATION_COUNT")
    require(
        set(delivered) == {str(t) for t in canonical} == set(state["processed_trades"]),
        "TRADE_COVERAGE",
    )
    terminal_orders = {int(o["order_id"]): o for o in state["orders"]}
    require(
        len(terminal_orders) == len(state["orders"]) and set(terminal_orders) == set(orders),
        "TERMINAL_ORDER_SET",
    )
    for oid, order in orders.items():
        saved = terminal_orders[oid]
        for field in (
            "side",
            "role",
            "column",
            "level",
            "direction",
            "capital_source",
            "source_order_id",
            "cell_id",
            "active_us",
            "status",
            "cancel_us",
        ):
            require(saved[field] == order[field], f"ORDER_BINDING:{field}")
        for field in (
            "filled",
            "price",
            "quantity",
            "reserved_quote",
            "reserved_base",
            "asset_basis",
        ):
            require(D(saved[field]) == D(order[field]), f"ORDER_ACCOUNTING:{field}")
        activation = order["activation"]
        require(
            saved["submitted_us"] == order["time_us"]
            and saved["activation_evaluated_us"] == (activation["time_us"] if activation else None),
            "QUEUE_AGE_RESET",
        )
    saved_groups = {(g["side"], D(g["price"])): g for g in state["groups"]}
    require(
        len(saved_groups) == len(state["groups"]) and set(saved_groups) == set(groups), "GROUP_SET"
    )
    for key, segments in groups.items():
        saved = saved_groups[key]
        require(
            D(saved["public_remaining"]) == sum((s["remaining"] for s in segments), zero)
            and D(saved["public_queue"]) == sum((s["barrier"] for s in segments), zero)
            and len(saved["segments"]) == len(segments),
            "PUBLIC_TERMINAL",
        )
        for original, actual in zip(segments, saved["segments"], strict=True):
            require(
                original["ids"] == actual["order_ids"]
                and original["time"] == actual["activation_us"]
                and original["barrier"] == D(actual["public_barrier"])
                and original["remaining"] == D(actual["public_remaining"]),
                "SEGMENT_MEMBERSHIP",
            )
    saved_lots = {int(lot["entry_order_id"]): lot for lot in state["lots"]}
    require(len(saved_lots) == len(state["lots"]) and set(saved_lots) == set(lots), "LOT_SET")
    for oid, expected in lots.items():
        saved = saved_lots[oid]
        require(
            all(
                D(saved[f]) == expected[f]
                for f in (
                    "quantity",
                    "basis",
                    "asset_basis",
                    "closed_quantity",
                    "restored_cost",
                )
            )
            and saved["stage"] == expected["stage"]
            and saved["created_us"] == expected["created_us"],
            "LOT_ACCOUNTING",
        )
    for field, expected in {
        "cash": cash,
        "free_usdc": free,
        "inventory_qty": inventory,
        "reserved_usdt": reserved_quote,
        "reserved_usdc": reserved_base,
        "growth_pool": growth,
        "realized_pnl": profit,
        "realized_disposal_pnl": disposal_profit,
        "growth_earned": growth_earned,
        "initial_usdt": D("74.9900"),
        "initial_usdc": D(75),
        "initial_mark": D("150.1325"),
    }.items():
        require(D(state[field]) == expected, f"CAPITAL_RECONSTRUCTION:{field}")
    require(
        funded == {oid for oid, o in orders.items() if o["capital_source"] == "GROWTH"},
        "GROWTH_EVENT_COVERAGE",
    )
    require(
        cycle_ids
        == {oid for oid, o in orders.items() if o["role"] == "RETURN" and o["status"] == "FILLED"},
        "CYCLE_COVERAGE",
    )
    final_quote, final_base = cash + reserved_quote, free + inventory + reserved_base
    mark = D(state["last_book"]["bids"][0][0])
    equity = final_quote + final_base * mark
    latest_sell_cells = {}
    for order in orders.values():
        if order["role"] == "ENTRY" and order["side"] == "SELL":
            previous = latest_sell_cells.get(order["cell_id"])
            if previous is None or order["order_id"] > previous["order_id"]:
                latest_sell_cells[order["cell_id"]] = order
    marked_quantity = zero
    inventory_cost = zero
    for order in latest_sell_cells.values():
        held = D(1) - order["filled"]
        marked_quantity += held
        inventory_cost += held * D(order["asset_basis"])
    for entry_id, lot in lots.items():
        source = orders[entry_id]
        if source["side"] == "BUY":
            held = lot["quantity"] - lot["closed_quantity"]
            marked_quantity += held
            inventory_cost += held * lot["asset_basis"]
        elif lot["stage"] != "RECYCLED" and lot["closed_quantity"] > 0:
            marked_quantity += lot["closed_quantity"]
            inventory_cost += lot["restored_cost"]
    inventory_unrealized = marked_quantity * mark - inventory_cost
    require(marked_quantity == final_base, "INVENTORY_LAYER_QUANTITY")
    require(
        equity - D("150.1325") - disposal_profit - inventory_unrealized == 0,
        "PNL_IDENTITY",
    )
    for field, expected in {
        "FINAL_USDT": final_quote,
        "FINAL_USDC": final_base,
        "FINAL_MARKED_EQUITY": equity,
        "REALIZED_PNL": profit,
        "REALIZED_DISPOSAL_PNL": disposal_profit,
        "GROWTH_ELIGIBLE_PNL_CUMULATIVE": growth_earned,
        "UNREALIZED_PNL": inventory_unrealized,
        "INVENTORY_MARKED_QUANTITY": marked_quantity,
        "INVENTORY_COST_BASIS": inventory_cost,
        "PNL_IDENTITY_RESIDUAL": zero,
        "GROWTH_POOL_FINAL": growth,
        "LOCKED_SELL_PROCEEDS_USDT": locked_sell_proceeds(),
        "PARTIAL_SUBSTEP_LOCKED_LOTS": sum(
            lot["stage"] in {"SUBSTEP_INVENTORY_LOCKED", "SUBSTEP_RETURN_DEBT_LOCKED"}
            for lot in lots.values()
        ),
        "TOTAL_CYCLES": len(cycle_ids),
        "TOTAL_FILLS": fill_count,
        "MAX_OPEN_ORDERS": max_open,
        "NEW_QUEUE_CELLS_FUNDED_BY_PROFIT": len(funded),
    }.items():
        require(D(metrics[field]) == expected, f"METRIC_RECONSTRUCTION:{field}")
    require(
        state["cycles"] == len(cycle_ids)
        and state["fill_count"] == fill_count
        and state["max_open_orders"] == max_open
        and state["growth_cells"] == len(funded),
        "STATE_COUNTERS",
    )
    seen_c2 = set()
    for case in state["preaging_cases"]:
        c1, c2 = int(case["c1_order_id"]), int(case["c2_order_id"])
        require(
            group_key(orders[c1]) == group_key(orders[c2])
            and orders[c1]["role"] == orders[c2]["role"] == "ENTRY",
            "PREAGING_PAIR",
        )
        require(
            c2 not in seen_c2
            and case["c1_fill_us"] == completions[c1]
            and case["c2_activation_us"] == orders[c2]["activation"]["time_us"]
            and case["actual_fill_us"] == completions.get(c2),
            "PREAGING_ACTUAL_BINDING",
        )
        seen_c2.add(c2)
        shadow = case["shadow"]
        require(
            shadow["submitted_us"] == completions[c1]
            and shadow["active_us"] == completions[c1] + config["latency_us"],
            "SHADOW_LATENCY",
        )
        if shadow["fill_us"] is not None:
            require(
                shadow["activation_us"] >= shadow["active_us"]
                and shadow["fill_us"] > shadow["activation_us"],
                "SHADOW_CREATING_TRADE",
            )
        case_rows = [row for row in shadow_rows if row["c2_order_id"] == c2]
        activation_rows = [row for row in case_rows if row["event"] == "SHADOW_ACTIVATED"]
        rejection_rows = [row for row in case_rows if row["event"] == "SHADOW_REJECTED"]
        if shadow["activation_us"] is not None:
            require(
                len(activation_rows) == 1
                and not rejection_rows
                and activation_rows[0]["time_us"] == shadow["activation_us"]
                and activation_rows[0]["native_book_upper_us"]
                == shadow["activation_native_upper_us"],
                "SHADOW_ACTIVATION_BINDING",
            )
            public = D(activation_rows[0]["public_queue_ahead"])
            own = D(activation_rows[0]["own_queue_ahead"])
            filled = zero
            applied = [row for row in case_rows if row["event"] == "SHADOW_TRADE_APPLIED"]
            for applied_row in applied:
                require(
                    applied_row["time_us"] > shadow["activation_us"]
                    and applied_row["native_time_us"] > shadow["activation_native_upper_us"],
                    "SHADOW_NATIVE_OR_CAPTURE_CLOCK",
                )
                public -= D(applied_row["public_debit"])
                own -= D(applied_row["own_debit"])
                filled += D(applied_row["fill_debit"])
                require(min(public, own, filled) >= 0 and filled <= 1, "SHADOW_RECONSTRUCTION")
            require(
                public == D(shadow["public_remaining"])
                and own == D(shadow["own_remaining"])
                and filled == D(shadow["filled"]),
                "SHADOW_TERMINAL_RECONSTRUCTION",
            )
        elif shadow["status"].startswith("SHADOW_REJECTED"):
            require(len(rejection_rows) == 1 and not activation_rows, "SHADOW_REJECTION_BINDING")
        expected = (
            shadow["fill_us"] - case["actual_fill_us"]
            if shadow["fill_us"] is not None and case["actual_fill_us"] is not None
            else None
        )
        require(case["benefit_us"] == expected, "PREAGING_BENEFIT")
    return {
        "status": "PASS_M024_PHYSICAL_LEDGER",
        "trades_delivered": len(delivered),
        "fill_fragments": fill_count,
        "complete_positive_cycles": len(cycle_ids),
        "max_open_orders": max_open,
        "growth_cells": len(funded),
        "capital_reconciled": True,
        "segmented_fifo_reconciled": True,
        "canonical_trade_budget_reconciled": True,
        "lots_reconciled": True,
        "preaging_actual_times_reconciled": True,
        "shadow_scope": "DIAGNOSTIC_ONLY_TIMING_CHECK_NOT_MAIN_FINANCIAL_FLOW",
    }


def _write_ledger(path: Path, rows) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def execute(engine, canonical, slices, identity, evidence, output=OUTPUT, result_path=RESULT):
    _assert_unused_output(output, result_path)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "run-manifest.json", {**identity, "evidence": evidence})
    audit_file = output / "execution-audit.jsonl"
    try:
        seen = set()
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
            if event["kind"] != "TRADE":
                raise ValueError("M024_UNKNOWN_NATIVE_EVENT")
            native = event["data"]
            trade = canonical.get(native["t"])
            if (
                trade is None
                or trade.trade_id in seen
                or D(native["p"]) != trade.price
                or D(native["q"]) != trade.quantity
                or native["m"] is not trade.buyer_maker
                or not trade_timestamp_matches(trade.time_us, native["T"])
            ):
                raise ValueError("M024_CANONICAL_TRADE_BINDING_CHANGED")
            consumed = engine.receive_trade(trade, capture_time_us=event["local_us"])
            if not D(0) <= consumed <= trade.quantity:
                raise ValueError("M024_GLOBAL_TRADE_BUDGET_EXCEEDED")
            seen.add(trade.trade_id)
        if seen != set(canonical):
            raise ValueError("M024_CANONICAL_3H_NOT_FULLY_DELIVERED")
        metrics = {
            key: value for key, value in engine.finish(time_us=END_US).items() if key != "AUDIT"
        }
        terminal = engine.checkpoint()
        _write_ledger(audit_file, engine.audit)
        write_json(output / "terminal-engine-state.json", terminal)
        audit = independent_execution_audit(engine.audit, terminal, canonical, metrics)
        audit.update(terminal_sha256=terminal["sha256"], ledger_sha256=file_sha(audit_file))
        result = {
            **identity,
            "MODEL": MODEL_ID,
            "PERIOD": "3H",
            "RUN_STATUS": "COMPLETE",
            "VERDICT": "M024_MECHANICS_MEASURED_NOT_STRATEGY_APPROVAL",
            "DISCLAIMER": engine.normalized_label,
            "METRICS": metrics,
            "AUDIT": audit,
            "AUDIT_FILE": str(audit_file),
        }
        write_json(output / "all-fill-audit.json", audit)
        write_json(output / "summary.json", result)
        write_json(result_path, result)
        return result
    except BaseException as exc:
        if not audit_file.exists():
            _write_ledger(audit_file, engine.audit)
        write_json(
            output / "failure.json",
            {
                "RUN_STATUS": "INCOMPLETE_PRESERVED",
                "exception_type": type(exc).__name__,
                "error": str(exc),
                "run_hash": identity.get("run_hash"),
                "ledger_sha256": file_sha(audit_file),
            },
        )
        raise


def run():
    sha, manifest, validation = campaign_preflight()
    with campaign_writer_lock():
        _assert_unused_output()
        profile, canonical, slices, evidence = bounded_inputs(manifest, validation)
        # Input preparation never licenses a source or authority change before execution.
        require_owner_gate()
        _assert_published_head(sha)
        model = ModelRegistry().get(MODEL_ID)
        identity = {
            "model_id": MODEL_ID,
            "model_hash": model.model_hash,
            "capital_mode": "NORMALIZED_MECHANICS_PROBE",
            "order_notional_mode": "NORMALIZED_1_USDC_NON_EXECUTABLE_PRE_AGED_FIFO",
            "normalized_quantity_usdc": "1",
            "virtual_filter_override": "MIN_NOTIONAL_ONLY",
            "start": "2025-01-01T00:00:00Z",
            "end_exclusive": "2025-01-01T03:00:00Z",
            "published_config_sha": sha,
            "expected_trade_count": len(canonical),
            "source_sha256_lf": {p.as_posix(): lf_sha(p) for p in SOURCE_PATHS},
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
            "cutoff_liquidation": False,
            "day2_authorized": False,
            "evidence_sha256": json_hash(evidence),
        }
        identity["run_hash"] = json_hash(identity)
        return execute(make_probe(profile), canonical, slices, identity, evidence)


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, default=str))
