"""Independent M030 treatment and preserved-M029 baseline checks."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from decimal import ROUND_HALF_UP
from decimal import Decimal as D
from itertools import pairwise
from statistics import median
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from scripts.audit_dynamic_hotline_321 import independent_dynamic_hotline_audit

START_US = 1_735_689_600_000_000
END_US = 1_735_776_000_000_000
TICK = D("0.0001")
HOT_TARGET = D(45)


def _m026_compatible_audit_view(
    terminal: dict[str, Any], metrics: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Expand only the auditor's epoch view; the physical M030 state stays untouched."""
    audit_terminal = deepcopy(terminal)
    audit_metrics = deepcopy(metrics)
    actual = audit_terminal["state"]["m026"]["hotline_epochs"]
    expanded = [deepcopy(actual[0])]
    for old, new in pairwise(actual):
        old_price = D(old["HOTLINE_PRICE"])
        new_price = D(new["HOTLINE_PRICE"])
        steps = int(abs(new_price - old_price) / TICK)
        direction = D(1) if new_price > old_price else D(-1)
        for index in range(1, steps + 1):
            epoch = deepcopy(new)
            epoch["EPOCH_ID"] = len(expanded) + 1
            epoch["HOTLINE_PRICE"] = str(old_price + direction * TICK * D(index))
            expanded.append(epoch)
    audit_terminal["state"]["m026"]["hotline_epochs"] = expanded
    audit_terminal["sha256"] = canonical_hash(audit_terminal["state"])
    audit_metrics["HOTLINE_EPOCHS"] = len(expanded)
    return audit_terminal, audit_metrics


def _overlap(start: int, end: int, windows: tuple[tuple[int, int], ...]) -> int:
    return sum(max(0, min(end, right) - max(start, left)) for left, right in windows)


def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (95 * (len(ordered) - 1) + 99) // 100
    return ordered[index]


def _hot_funded(orders: dict[int, dict[str, Any]], hotline: D | None, side: str) -> D:
    if hotline is None:
        return D(0)
    total = D(0)
    for order in orders.values():
        if order["role"] != "ENTRY" or order["side"] != side or not order["open"]:
            continue
        distance = hotline - order["line_price"] if side == "BUY" else order["line_price"] - hotline
        if distance <= 0 or distance % TICK != 0 or int(distance / TICK) not in range(1, 6):
            continue
        total += D(order["slot_count"]) * order["remaining"] / order["quantity"]
    return min(HOT_TARGET, total)


def _terminal_reclaimable_capital(terminal: dict[str, Any]) -> dict[str, D]:
    parent = terminal["state"]["parent"]
    m026 = terminal["state"]["m026"]
    extra = m026["m030"]
    hotline = D(m026["hotline"])
    meta_by_id = {int(key): value for key, value in m026["order_meta"].items()}
    pending_ids = {int(value) for value in extra["reclaim_requests"]}
    result = {"USDT": D(0), "USDC": D(0)}
    for row in parent["orders"]:
        order_id = int(row["order_id"])
        if row["role"] != "ENTRY":
            continue
        pending_reclaim = order_id in pending_ids
        if not pending_reclaim and D(row["filled"]) != 0:
            continue
        if row["status"] not in {"PENDING", "ACTIVE"} and not pending_reclaim:
            continue
        meta = meta_by_id[order_id]
        line = D(meta["line_price"])
        distance = hotline - line if row["side"] == "BUY" else line - hotline
        rank = int(distance / TICK) if distance > 0 and distance % TICK == 0 else None
        hot_with_correct_weight = rank in range(1, 6) and int(meta["slot_count"]) == 3
        if hot_with_correct_weight and not pending_reclaim:
            continue
        remaining = D(row["quantity"]) - D(row["filled"])
        asset = "USDT" if row["side"] == "BUY" else "USDC"
        result[asset] += remaining * D(row["price"]) if asset == "USDT" else remaining
    return result


def _terminal_true_capital_shortfall(
    terminal: dict[str, Any], reclaimable: dict[str, D]
) -> dict[str, D]:
    """Rebuild the terminal HOT deficit from physical balances and ownership."""
    parent = terminal["state"]["parent"]
    m026 = terminal["state"]["m026"]
    hotline = D(m026["hotline"])
    slot_base = D(m026["decimal"]["slot_base"])
    orders = {int(row["order_id"]): row for row in parent["orders"]}
    latest = {str(key): int(value) for key, value in m026["cell_latest_entry"].items()}

    hot_deficit = {"USDT": D(0), "USDC": D(0)}
    for side, asset, sign in (("BUY", "USDT", D(-1)), ("SELL", "USDC", D(1))):
        for rank in range(1, 6):
            price = hotline + sign * TICK * D(rank)
            desired = (slot_base * D(3) / price).to_integral_value(rounding=ROUND_HALF_UP)
            desired = max(D(1), desired)
            for column in range(1, 4):
                order_id = latest.get(f"{side}:P{price}:C{column}")
                order = orders.get(order_id) if order_id is not None else None
                funded = D(0)
                if (
                    order is not None
                    and order["role"] == "ENTRY"
                    and order["status"] in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
                ):
                    funded = min(D(order["quantity"]) - D(order["filled"]), desired)
                missing = max(D(0), desired - funded)
                hot_deficit[asset] += missing * price if side == "BUY" else missing

    open_returns = {
        int(row["source_order_id"])
        for row in parent["orders"]
        if row["role"] == "RETURN"
        and row["direction"] == "SELL_FIRST"
        and row["source_order_id"] is not None
        and row["status"] in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
    }
    locked_sell_proceeds = sum(
        (
            D(lot["quantity"]) * D(lot["basis"])
            for lot in parent["lots"]
            if lot["side"] == "SELL"
            and lot["stage"] not in {"RESTORED", "RECYCLED"}
            and int(lot["entry_order_id"]) not in open_returns
        ),
        D(0),
    )
    buy_mobility = D(m026["decimal"]["buy_mobility_reserve"])
    sell_mobility = D(m026["decimal"]["sell_mobility_reserve"])
    operational = {
        "USDT": max(D(0), D(parent["cash"]) - buy_mobility - locked_sell_proceeds),
        "USDC": sum(
            (
                D(layer["quantity"])
                for layer in m026["free_usdc_layers"]
                if not bool(layer["mobility"])
            ),
            D(0),
        ),
    }
    mobility = {"USDT": buy_mobility, "USDC": sell_mobility}
    return {
        asset: max(
            D(0),
            hot_deficit[asset] - reclaimable[asset] - operational[asset] - mobility[asset],
        )
        for asset in ("USDT", "USDC")
    }


def reconstruct_m029_hot_coverage(
    rows: list[dict[str, Any]], windows: tuple[tuple[int, int], ...]
) -> dict[str, Any]:
    """Reconstruct funded HOT reservations from an M026-family ledger."""
    orders: dict[int, dict[str, Any]] = {}
    hotline: D | None = None
    last = START_US
    target_time = {"BUY": D(0), "SELL": D(0)}
    funded_time = {"BUY": D(0), "SELL": D(0)}
    eval_target = {"BUY": D(0), "SELL": D(0)}
    eval_funded = {"BUY": D(0), "SELL": D(0)}
    missing_time = 0
    stranded_time = 0
    eval_missing_time = 0
    eval_stranded_time = 0
    move_times: Counter[int] = Counter()
    pending_reclaims: dict[int, str] = {}

    def zero_fill_reclaimable(order: dict[str, Any], side: str) -> bool:
        if not order["open"] or order["role"] != "ENTRY" or order["side"] != side:
            return False
        if order["filled"] != 0:
            return False
        distance = hotline - order["line_price"] if side == "BUY" else order["line_price"] - hotline
        rank = int(distance / TICK) if distance > 0 and distance % TICK == 0 else None
        return not (rank in range(1, 6) and int(order["slot_count"]) == 3)

    def observe(now: int) -> None:
        nonlocal last, missing_time, stranded_time, eval_missing_time, eval_stranded_time
        elapsed = max(0, now - last)
        if elapsed and hotline is not None:
            evaluated = _overlap(last, now, windows)
            funded = {side: _hot_funded(orders, hotline, side) for side in ("BUY", "SELL")}
            for side in ("BUY", "SELL"):
                target_time[side] += HOT_TARGET * D(elapsed)
                funded_time[side] += funded[side] * D(elapsed)
                eval_target[side] += HOT_TARGET * D(evaluated)
                eval_funded[side] += funded[side] * D(evaluated)
            if any(funded[side] < HOT_TARGET for side in ("BUY", "SELL")):
                missing_time += elapsed
                eval_missing_time += evaluated
                administrative = False
                for side in ("BUY", "SELL"):
                    if funded[side] >= HOT_TARGET:
                        continue
                    reclaimable = any(
                        zero_fill_reclaimable(order, side) for order in orders.values()
                    )
                    if reclaimable or side in pending_reclaims.values():
                        administrative = True
                if administrative:
                    stranded_time += elapsed
                    eval_stranded_time += evaluated
        last = max(last, now)

    terminal_events = {
        "CANCEL_ACK",
        "REJECTED_POST_ONLY",
        "REJECTED_SELF_CROSS",
        "REJECTED_COVERAGE",
        "REJECTED_NEGATIVE_EXIT",
    }
    for row in rows:
        now = int(row["time_us"])
        observe(now)
        event = row["event"]
        if event == "SUBMIT":
            quantity = D(row["quantity"])
            orders[int(row["order_id"])] = {
                "side": row["side"],
                "role": row["role"],
                "line_price": D(row.get("line_price", row["price"])),
                "slot_count": int(row.get("slot_count", 1)),
                "quantity": quantity,
                "remaining": quantity,
                "filled": D(0),
                "open": True,
            }
        elif event == "FILL":
            order = orders[int(row["order_id"])]
            amount = D(row["quantity"])
            order["filled"] += amount
            order["remaining"] -= amount
            if order["remaining"] == 0:
                order["open"] = False
        elif event in terminal_events and int(row.get("order_id", -1)) in orders:
            orders[int(row["order_id"])]["open"] = False
        elif event == "DYNAMIC_GRID_INITIALIZED":
            hotline = D(row["hotline"])
        elif event == "HOTLINE_MOVED":
            hotline = D(row["new_price"])
            move_times[now] += 1
        elif event == "HOTLINE_FINAL_TARGET_MOVED":
            hotline = D(row["new_price"])
            move_times[now] += int(row["jump_ticks"])
        elif event == "HOT_REALLOCATION_CANCEL_REQUESTED":
            pending_reclaims[int(row["order_id"])] = row["side"]
        elif event in {
            "HOT_REALLOCATION_CANCEL_ACKED",
            "HOT_REALLOCATION_CANCEL_TERMINATED_BY_REJECTION",
            "HOT_REALLOCATION_CANCEL_SUPERSEDED_BY_FULL_FILL",
        }:
            pending_reclaims.pop(int(row["order_id"]), None)
    observe(END_US)
    total_target = sum(target_time.values(), D(0))
    eval_target_total = sum(eval_target.values(), D(0))
    return {
        "FULL_DAY_TIME_WEIGHTED": str(
            sum(funded_time.values(), D(0)) / total_target if total_target else D(0)
        ),
        "RANDOM_3H_TIME_WEIGHTED": str(
            sum(eval_funded.values(), D(0)) / eval_target_total if eval_target_total else D(0)
        ),
        "BUY_FULL_DAY_TIME_WEIGHTED": str(
            funded_time["BUY"] / target_time["BUY"] if target_time["BUY"] else D(0)
        ),
        "SELL_FULL_DAY_TIME_WEIGHTED": str(
            funded_time["SELL"] / target_time["SELL"] if target_time["SELL"] else D(0)
        ),
        "HOT_UNDERFUNDED_TIME_PCT": str(D(missing_time) / D(END_US - START_US) * D(100)),
        "RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT": str(
            D(stranded_time) / D(END_US - START_US) * D(100)
        ),
        "RANDOM_3H_HOT_UNDERFUNDED_TIME_PCT": str(
            D(eval_missing_time) / D(10_800_000_000) * D(100)
        ),
        "RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT": str(
            D(eval_stranded_time) / D(10_800_000_000) * D(100)
        ),
        "MULTI_TICK_BOOK_MOVES": sum(count > 1 for count in move_times.values()),
        "TOTAL_TICKS_CROSSED": sum(move_times.values()),
        "INTERMEDIATE_RECONCILES": sum(max(0, count - 1) for count in move_times.values()),
        "METHOD": "POST_HOC_LEDGER_RECONSTRUCTION_OF_FUNDED_ENTRY_RESERVATIONS",
    }


def reconstruct_m030_administrative_capacity(
    rows: list[dict[str, Any]], windows: tuple[tuple[int, int], ...]
) -> dict[str, str]:
    """Rebuild M030's broad administrative-capacity predicate from its ledger."""
    initialized = [row for row in rows if row["event"] == "DYNAMIC_GRID_INITIALIZED"]
    if len(initialized) != 1:
        raise ValueError("M030_ADMIN_RECONSTRUCTION_INITIALIZATION")
    initial = initialized[0]
    slot_base = D(initial["initial_slot_base"])
    mobility_units = D(initial["mobility_slot_units"]) / D(2)
    cash = D(initial["initial_usdt"])
    buy_mobility = mobility_units * slot_base
    sell_mobility = mobility_units
    operational_usdc = D(initial["initial_usdc"]) - sell_mobility
    hotline: D | None = None
    orders: dict[int, dict[str, Any]] = {}
    latest_entries: dict[str, int] = {}
    pending_reclaims: dict[int, str] = {}
    sell_lots: dict[int, dict[str, Any]] = {}
    last = START_US
    administrative_time = 0
    eval_administrative_time = 0

    def desired_cells(side: str) -> list[tuple[D, int]]:
        if hotline is None:
            return []
        sign = D(-1) if side == "BUY" else D(1)
        return [
            (hotline + sign * TICK * D(rank), column)
            for rank in range(1, 6)
            for column in range(1, 4)
        ]

    def desired_quantity(price: D) -> D:
        return max(
            D(1),
            (slot_base * D(3) / price).to_integral_value(rounding=ROUND_HALF_UP),
        )

    def hot_state(side: str) -> tuple[D, D]:
        funded_slots = D(0)
        asset_deficit = D(0)
        for price, column in desired_cells(side):
            order_id = latest_entries.get(f"{side}:P{price}:C{column}")
            order = orders.get(order_id) if order_id is not None else None
            quantity = desired_quantity(price)
            funded_quantity = D(0)
            if (
                order is not None
                and order["role"] == "ENTRY"
                and order["status"] in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
            ):
                funded_quantity = min(order["quantity"] - order["filled"], quantity)
                funded_slots += (
                    D(order["slot_count"])
                    * (order["quantity"] - order["filled"])
                    / order["quantity"]
                )
            missing = max(D(0), quantity - funded_quantity)
            asset_deficit += missing * price if side == "BUY" else missing
        return min(HOT_TARGET, funded_slots), asset_deficit

    def reclaimable_exists(side: str) -> bool:
        for order_id, order in orders.items():
            if (
                order["side"] != side
                or order["role"] != "ENTRY"
                or order["filled"] != 0
                or order["status"] not in {"PENDING", "ACTIVE"}
                or order_id in pending_reclaims
            ):
                continue
            line = order["line_price"]
            distance = hotline - line if side == "BUY" else line - hotline
            rank = int(distance / TICK) if distance > 0 and distance % TICK == 0 else None
            if not (rank in range(1, 6) and order["slot_count"] == 3):
                return True
        return False

    def locked_sell_proceeds() -> D:
        open_returns = {
            int(order["source_order_id"])
            for order in orders.values()
            if order["role"] == "RETURN"
            and order["direction"] == "SELL_FIRST"
            and order["source_order_id"] is not None
            and order["status"] in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
        }
        return sum(
            (
                lot["quantity"] * lot["basis"]
                for source_id, lot in sell_lots.items()
                if not lot["restored"] and source_id not in open_returns
            ),
            D(0),
        )

    def observe(now: int) -> None:
        nonlocal last, administrative_time, eval_administrative_time
        elapsed = max(0, now - last)
        if elapsed and hotline is not None:
            evaluated = _overlap(last, now, windows)
            hot = {side: hot_state(side) for side in ("BUY", "SELL")}
            if any(hot[side][0] < HOT_TARGET for side in ("BUY", "SELL")):
                administrative = False
                for side in ("BUY", "SELL"):
                    funded, deficit = hot[side]
                    if funded >= HOT_TARGET:
                        continue
                    pending = any(value == side for value in pending_reclaims.values())
                    if side == "BUY":
                        available = max(D(0), cash - buy_mobility - locked_sell_proceeds())
                        mobility = buy_mobility
                    else:
                        available = operational_usdc
                        mobility = sell_mobility
                    if reclaimable_exists(side) or pending or available + mobility >= deficit:
                        administrative = True
                if administrative:
                    administrative_time += elapsed
                    eval_administrative_time += evaluated
        last = max(last, now)

    terminal_events = {
        "CANCEL_ACK",
        "REJECTED_POST_ONLY",
        "REJECTED_SELF_CROSS",
        "REJECTED_COVERAGE",
        "REJECTED_NEGATIVE_EXIT",
    }
    for row in rows:
        now = int(row["time_us"])
        observe(now)
        event = row["event"]
        if event == "SUBMIT":
            order_id = int(row["order_id"])
            quantity, price = D(row["quantity"]), D(row["price"])
            layers = [
                {
                    "quantity": D(layer["quantity"]),
                    "mobility": bool(layer["mobility"]),
                }
                for layer in row["asset_cost_layers"]
            ]
            orders[order_id] = {
                "side": row["side"],
                "role": row["role"],
                "direction": row["direction"],
                "source_order_id": row["source_order_id"],
                "quantity": quantity,
                "price": price,
                "filled": D(0),
                "status": "PENDING",
                "cell_id": row["cell_id"],
                "line_price": D(row["line_price"]),
                "slot_count": int(row["slot_count"]),
                "asset_cost_layers": layers,
                "usdt_lock_original": D(row["mobility_usdt_locked"]),
                "usdt_lock": D(row["mobility_usdt_locked"]),
            }
            if row["role"] == "ENTRY":
                latest_entries[row["cell_id"]] = order_id
            if row["side"] == "BUY":
                cash -= quantity * price
                buy_mobility -= D(row["mobility_usdt_locked"])
            elif not (row["role"] == "RETURN" and row["direction"] == "BUY_FIRST"):
                operational_usdc -= sum(
                    (layer["quantity"] for layer in layers if not layer["mobility"]),
                    D(0),
                )
                sell_mobility -= D(row["mobility_usdc_locked"])
        elif event == "ACTIVATED":
            orders[int(row["order_id"])]["status"] = "ACTIVE"
        elif event == "CANCEL_REQUEST":
            orders[int(row["order_id"])]["status"] = "CANCEL_PENDING"
        elif event == "FILL":
            order = orders[int(row["order_id"])]
            amount = D(row["quantity"])
            order["filled"] += amount
            remaining = order["quantity"] - order["filled"]
            if order["side"] == "BUY":
                order["usdt_lock"] = min(order["usdt_lock_original"], remaining * order["price"])
                if order["role"] == "RETURN" and order["direction"] == "SELL_FIRST":
                    operational_usdc += amount
                    if remaining == 0:
                        sell_lots[int(order["source_order_id"])]["restored"] = True
            else:
                cash += amount * order["price"]
                remaining_to_consume = amount
                while remaining_to_consume > 0:
                    layer = order["asset_cost_layers"][0]
                    take = min(layer["quantity"], remaining_to_consume)
                    layer["quantity"] -= take
                    remaining_to_consume -= take
                    if layer["quantity"] == 0:
                        order["asset_cost_layers"].pop(0)
                if order["role"] == "ENTRY" and order["direction"] == "SELL_FIRST":
                    lot = sell_lots.setdefault(
                        int(row["order_id"]),
                        {"quantity": D(0), "basis": order["price"], "restored": False},
                    )
                    lot["quantity"] += amount
            if remaining == 0:
                order["status"] = "FILLED"
        elif event in terminal_events:
            order = orders[int(row["order_id"])]
            remaining = order["quantity"] - order["filled"]
            if order["side"] == "BUY":
                cash += remaining * order["price"]
                buy_mobility += order["usdt_lock"]
            elif not (order["role"] == "RETURN" and order["direction"] == "BUY_FIRST"):
                operational_usdc += sum(
                    (
                        layer["quantity"]
                        for layer in order["asset_cost_layers"]
                        if not layer["mobility"]
                    ),
                    D(0),
                )
                sell_mobility += sum(
                    (
                        layer["quantity"]
                        for layer in order["asset_cost_layers"]
                        if layer["mobility"]
                    ),
                    D(0),
                )
            order["asset_cost_layers"] = []
            order["usdt_lock"] = D(0)
            order["status"] = "CANCELED" if event == "CANCEL_ACK" else "REJECTED"
        elif event == "BUY_MOBILITY_RESERVE_RESTORED":
            buy_mobility += D(row["amount"])
        elif event == "SELL_MOBILITY_RESERVE_RESTORED":
            amount = D(row["quantity"])
            operational_usdc -= amount
            sell_mobility += amount
        elif event == "DYNAMIC_GRID_INITIALIZED":
            hotline = D(row["hotline"])
            slot_base = D(row["initial_slot_base"])
        elif event == "HOTLINE_FINAL_TARGET_MOVED":
            hotline = D(row["new_price"])
        elif event == "SLOT_BASE_ADVANCED":
            slot_base = D(row["slot_base"])
        elif event == "HOT_REALLOCATION_CANCEL_REQUESTED":
            pending_reclaims[int(row["order_id"])] = row["side"]
        elif event in {
            "HOT_REALLOCATION_CANCEL_ACKED",
            "HOT_REALLOCATION_CANCEL_TERMINATED_BY_REJECTION",
            "HOT_REALLOCATION_CANCEL_SUPERSEDED_BY_FULL_FILL",
        }:
            pending_reclaims.pop(int(row["order_id"]), None)
        if min(cash, operational_usdc, buy_mobility, sell_mobility) < 0:
            raise ValueError("M030_ADMIN_RECONSTRUCTION_NEGATIVE_CAPITAL")
    observe(END_US)
    total = D(END_US - START_US)
    evaluated = D(sum(right - left for left, right in windows))
    return {
        "FULL_DAY_TIME_PCT": str(D(administrative_time) / total * D(100)),
        "RANDOM_3H_TIME_PCT": str(D(eval_administrative_time) / evaluated * D(100)),
        "METHOD": "INDEPENDENT_LEDGER_ACCOUNT_AND_HOT_PREDICATE_RECONSTRUCTION",
    }


def normalize_m030_reporting_metrics(
    metrics: dict[str, Any],
    rows: list[dict[str, Any]],
    windows: tuple[tuple[int, int], ...],
) -> dict[str, Any]:
    """Separate literal stranded zero-fill capital from the engine's broad predicate.

    This is a reporting-only normalization.  It does not mutate engine state and it
    does not replay any market event.
    """
    value = dict(metrics)
    literal = reconstruct_m029_hot_coverage(rows, windows)
    broad = reconstruct_m030_administrative_capacity(rows, windows)
    raw_full = str(value["RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"])
    raw_eval = str(value["RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"])
    if D(raw_full) != D(broad["FULL_DAY_TIME_PCT"]):
        raise ValueError("M030_REPORTING_RAW_FULL_ADMINISTRATIVE_MISMATCH")
    if D(raw_eval) != D(broad["RANDOM_3H_TIME_PCT"]):
        raise ValueError("M030_REPORTING_RAW_RANDOM_ADMINISTRATIVE_MISMATCH")
    value.update(
        {
            "RAW_ENGINE_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT": raw_full,
            "RAW_ENGINE_RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT": raw_eval,
            "HOT_INCOMPLETE_WITH_ADMINISTRATIVE_CAPACITY_TIME_PCT": broad["FULL_DAY_TIME_PCT"],
            "RANDOM_3H_HOT_INCOMPLETE_WITH_ADMINISTRATIVE_CAPACITY_TIME_PCT": broad[
                "RANDOM_3H_TIME_PCT"
            ],
            "RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT": literal[
                "RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"
            ],
            "RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT": literal[
                "RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"
            ],
            "M030_REPORTING_CORRECTION": (
                "Official reclaimable-stranded metrics are independently rebuilt from "
                "literal zero-fill reclaimable/pending orders. The preserved raw engine "
                "counter is broader and is relabeled as HOT incomplete with administrative "
                "capacity; neither metric changes execution."
            ),
        }
    )
    return value


def independent_m030_audit(
    rows: list[dict[str, Any]],
    terminal: dict[str, Any],
    metrics: dict[str, Any],
    canonical: dict[int, Any],
    windows: tuple[tuple[int, int], ...],
) -> dict[str, Any]:
    if terminal.get("sha256") != canonical_hash(terminal.get("state")):
        raise ValueError("M030_AUDIT_ORIGINAL_TERMINAL_HASH")
    audit_terminal, audit_metrics = _m026_compatible_audit_view(terminal, metrics)
    base = independent_dynamic_hotline_audit(
        rows,
        audit_terminal,
        audit_metrics,
        canonical,
    )

    def require(condition: bool, reason: str) -> None:
        if not condition:
            raise ValueError(f"M030_AUDIT_{reason}")

    cycle_rows = [row for row in rows if row["event"] == "CYCLE"]
    eval_rows = [
        row
        for row in cycle_rows
        if any(left <= int(row["time_us"]) < right for left, right in windows)
    ]
    eval_slots = sum(int(row["slot_equivalent_weight"]) for row in eval_rows)
    jumps = [row for row in rows if row["event"] == "HOTLINE_FINAL_TARGET_MOVED"]
    requests = [row for row in rows if row["event"] == "HOT_REALLOCATION_CANCEL_REQUESTED"]
    acknowledgements = [row for row in rows if row["event"] == "HOT_REALLOCATION_CANCEL_ACKED"]
    rejected_terminals = [
        row for row in rows if row["event"] == "HOT_REALLOCATION_CANCEL_TERMINATED_BY_REJECTION"
    ]
    full_fill_terminals = [
        row for row in rows if row["event"] == "HOT_REALLOCATION_CANCEL_SUPERSEDED_BY_FULL_FILL"
    ]
    terminals = acknowledgements + rejected_terminals + full_fill_terminals
    allocations = [row for row in rows if row["event"] == "RECLAIMED_CAPITAL_ALLOCATED"]
    profit_floor_blocks = [row for row in rows if row["event"] == "ENTRY_PROFIT_FLOOR_BLOCK"]
    shortfall_events = [row for row in rows if row["event"] == "TRUE_CAPITAL_SHORTFALL"]
    reconstructed = reconstruct_m029_hot_coverage(rows, windows)
    administrative = reconstruct_m030_administrative_capacity(rows, windows)
    extra = terminal["state"]["m026"].get("m030")
    require(extra is not None, "TERMINAL_INSTRUMENTATION")
    actual_epochs = terminal["state"]["m026"]["hotline_epochs"]
    require(len(actual_epochs) == len(jumps) + 1, "JUMP_EPOCH_COUNT")
    for (old, new), jump in zip(pairwise(actual_epochs), jumps, strict=True):
        old_price = D(old["HOTLINE_PRICE"])
        new_price = D(new["HOTLINE_PRICE"])
        require(D(jump["old_price"]) == old_price, "JUMP_OLD_PRICE")
        require(D(jump["new_price"]) == new_price, "JUMP_NEW_PRICE")
        require(int(jump["time_us"]) == int(new["TIME_US"]), "JUMP_TIME")
        require(
            abs(new_price - old_price) == TICK * D(int(jump["jump_ticks"])),
            "JUMP_DISTANCE",
        )

    request_by_id = {int(row["order_id"]): row for row in requests}
    terminal_by_id = {int(row["order_id"]): row for row in terminals}
    submit_by_id = {int(row["order_id"]): row for row in rows if row["event"] == "SUBMIT"}
    physical_orders = {int(row["order_id"]): row for row in terminal["state"]["parent"]["orders"]}
    pending_ids = {int(value) for value in extra["reclaim_requests"]}
    require(len(request_by_id) == len(requests), "DUPLICATE_REQUEST")
    require(len(terminal_by_id) == len(terminals), "DUPLICATE_TERMINAL")
    require(set(terminal_by_id).isdisjoint(pending_ids), "TERMINAL_STILL_PENDING")
    require(set(request_by_id) == set(terminal_by_id) | pending_ids, "REQUEST_LIFECYCLE")
    require(
        all(
            int(terminal_by_id[order_id]["time_us"]) >= int(request_by_id[order_id]["time_us"])
            for order_id in terminal_by_id
        ),
        "TERMINAL_BEFORE_REQUEST",
    )
    base_ack = {
        (int(row["order_id"]), int(row["time_us"])) for row in rows if row["event"] == "CANCEL_ACK"
    }
    base_reject = {
        (int(row["order_id"]), int(row["time_us"]))
        for row in rows
        if row["event"].startswith("REJECTED_")
    }
    fill_times = {
        (int(row["order_id"]), int(row["time_us"])) for row in rows if row["event"] == "FILL"
    }
    for order_id, terminal_row in terminal_by_id.items():
        request = request_by_id[order_id]
        order = physical_orders[order_id]
        submit = submit_by_id[order_id]
        quantity = D(order["quantity"])
        filled = D(order["filled"])
        remaining = quantity - filled
        expected_release = remaining * D(order["price"]) if order["side"] == "BUY" else remaining
        mobility_field = (
            "mobility_usdt_locked" if order["side"] == "BUY" else "mobility_usdc_locked"
        )
        mobility_at_request = D(submit[mobility_field])
        expected_request_reservation = (
            quantity * D(order["price"]) if order["side"] == "BUY" else quantity
        )
        require(D(request["reserved"]) == expected_request_reservation, "REQUEST_RESERVATION")
        require(D(request["mobility_reserved"]) == mobility_at_request, "REQUEST_MOBILITY")
        event = terminal_row["event"]
        identity = (order_id, int(terminal_row["time_us"]))
        if event == "HOT_REALLOCATION_CANCEL_ACKED":
            require(identity in base_ack, "ACK_WITHOUT_PHYSICAL_ACK")
        elif event == "HOT_REALLOCATION_CANCEL_TERMINATED_BY_REJECTION":
            require(identity in base_reject, "REJECTION_WITHOUT_PHYSICAL_REJECTION")
        else:
            require(
                identity in fill_times and remaining == 0,
                "FULL_FILL_WITHOUT_PHYSICAL_FILL",
            )
            require(D(terminal_row["released"]) == 0, "FULL_FILL_RELEASED_CAPITAL")
            continue
        expected_mobility = min(mobility_at_request, expected_release)
        require(D(terminal_row["filled_before_ack"]) == filled, "TERMINAL_FILLED_QUANTITY")
        require(D(terminal_row["released"]) == expected_release, "TERMINAL_RELEASE_QUANTITY")
        require(
            D(terminal_row["mobility_restored"]) == expected_mobility,
            "TERMINAL_MOBILITY_RELEASE",
        )
        require(
            D(terminal_row["operational_released"]) == expected_release - expected_mobility,
            "TERMINAL_OPERATIONAL_RELEASE",
        )
    waits = [int(row["wait_us"]) for row in acknowledgements]
    release_terminals = acknowledgements + rejected_terminals
    zero_fill_terminals = [row for row in release_terminals if D(row["filled_before_ack"]) == 0]
    released = {
        asset: sum((D(row["released"]) for row in zero_fill_terminals if row["side"] == side), D(0))
        for asset, side in (("USDT", "BUY"), ("USDC", "SELL"))
    }
    operational_released = {
        asset: sum(
            (D(row["operational_released"]) for row in zero_fill_terminals if row["side"] == side),
            D(0),
        )
        for asset, side in (("USDT", "BUY"), ("USDC", "SELL"))
    }
    mobility_restored = {
        asset: sum(
            (D(row["mobility_restored"]) for row in zero_fill_terminals if row["side"] == side),
            D(0),
        )
        for asset, side in (("USDT", "BUY"), ("USDC", "SELL"))
    }
    allocated_hot = {
        asset: sum(
            (
                D(row["amount"])
                for row in allocations
                if row["asset"] == asset and row["role"] == "ENTRY" and row["zone"] == "HOT"
            ),
            D(0),
        )
        for asset in ("USDT", "USDC")
    }
    class_counts = Counter(row["category"] for row in zero_fill_terminals)
    terminal_reclaimable = _terminal_reclaimable_capital(terminal)
    terminal_true_shortfall = _terminal_true_capital_shortfall(terminal, terminal_reclaimable)
    reclaimed_pool = {"USDT": D(0), "USDC": D(0)}
    for row in rows:
        if row["event"] in {
            "HOT_REALLOCATION_CANCEL_ACKED",
            "HOT_REALLOCATION_CANCEL_TERMINATED_BY_REJECTION",
        }:
            asset = "USDT" if row["side"] == "BUY" else "USDC"
            reclaimed_pool[asset] += D(row["operational_released"])
        elif row["event"] == "RECLAIMED_CAPITAL_ALLOCATED":
            asset = row["asset"]
            amount = D(row["amount"])
            submit = submit_by_id.get(int(row["order_id"]))
            require(submit is not None, "ALLOCATION_WITHOUT_PHYSICAL_ORDER")
            require(int(submit["time_us"]) == int(row["time_us"]), "ALLOCATION_SUBMIT_TIME")
            require(submit["side"] == ("BUY" if asset == "USDT" else "SELL"), "ALLOCATION_ASSET")
            require(submit["role"] == row["role"], "ALLOCATION_ROLE")
            reservation = D(submit["quantity"])
            if asset == "USDT":
                reservation *= D(submit["price"])
            require(D(0) < amount <= reservation, "ALLOCATION_AMOUNT")
            require(amount <= reclaimed_pool[asset], "ALLOCATION_EXCEEDS_RECLAIMED_POOL")
            reclaimed_pool[asset] -= amount

    require(metrics["M030_EVAL_PHYSICAL_CYCLES"] == len(eval_rows), "EVAL_PHYSICAL")
    require(metrics["M030_EVAL_SLOT_CYCLES"] == eval_slots, "EVAL_SLOT")
    require(metrics["FILLED_ORDER_FORCED_CANCELS"] == 0, "FILLED_CANCEL")
    require(metrics["NEGATIVE_REALIZED_EXITS"] == 0, "NEGATIVE_EXIT")
    require(metrics["COST_BASIS_REWRITES"] == 0, "COST_BASIS")
    require(metrics["OWNED_RETURN_CAPITAL_STOLEN"] == 0, "RETURN_CAPITAL")
    require(all(D(row["filled_at_request"]) == 0 for row in requests), "REQUEST_NOT_ZERO")
    require(metrics["HOT_REALLOCATION_CANCEL_REQUESTS"] == len(requests), "REQUEST_COUNT")
    require(metrics["HOT_REALLOCATION_CANCEL_ACKS"] == len(acknowledgements), "ACK_COUNT")
    require(
        metrics["HOT_REALLOCATION_CANCEL_TERMINALS_WITHOUT_ACK"] == len(rejected_terminals),
        "REJECTED_TERMINAL_COUNT",
    )
    require(
        metrics["HOT_REALLOCATION_CANCEL_SUPERSEDED_BY_FULL_FILL"] == len(full_fill_terminals),
        "FULL_FILL_TERMINAL_COUNT",
    )
    require(metrics["ZERO_FILL_ORDERS_RECLAIMED"] == len(zero_fill_terminals), "ZERO_FILL_COUNT")
    require(
        metrics["ZERO_FILL_RECLAIM_BECAME_PARTIAL_BEFORE_ACK"]
        == len(release_terminals) - len(zero_fill_terminals),
        "PARTIAL_DURING_CANCEL",
    )
    require(D(metrics["ZERO_FILL_USDT_RECLAIMED"]) == released["USDT"], "USDT_RELEASED")
    require(D(metrics["ZERO_FILL_USDC_RECLAIMED"]) == released["USDC"], "USDC_RELEASED")
    require(
        D(metrics["ZERO_FILL_OPERATIONAL_USDT_RECLAIMED"]) == operational_released["USDT"],
        "OPERATIONAL_USDT_RELEASED",
    )
    require(
        D(metrics["ZERO_FILL_OPERATIONAL_USDC_RECLAIMED"]) == operational_released["USDC"],
        "OPERATIONAL_USDC_RELEASED",
    )
    require(
        D(metrics["ZERO_FILL_MOBILITY_USDT_RESTORED"]) == mobility_restored["USDT"],
        "MOBILITY_USDT_RESTORED",
    )
    require(
        D(metrics["ZERO_FILL_MOBILITY_USDC_RESTORED"]) == mobility_restored["USDC"],
        "MOBILITY_USDC_RESTORED",
    )
    require(
        D(metrics["CAPITAL_REALLOCATED_TO_CURRENT_HOT_USDT"]) == allocated_hot["USDT"],
        "USDT_REALLOCATED",
    )
    require(
        D(metrics["CAPITAL_REALLOCATED_TO_CURRENT_HOT_USDC"]) == allocated_hot["USDC"],
        "USDC_REALLOCATED",
    )
    for asset in ("USDT", "USDC"):
        require(
            D(metrics["RECLAIMABLE_CAPITAL_AVAILABLE"][asset]) == terminal_reclaimable[asset],
            f"{asset}_RECLAIMABLE_AVAILABLE",
        )
        require(
            D(metrics["TRUE_CAPITAL_SHORTFALL"][asset]) == terminal_true_shortfall[asset],
            f"CURRENT_{asset}_SHORTFALL",
        )
    for label, category in (
        ("FAR_RECLAIMS", "FAR"),
        ("MID_RECLAIMS", "MID"),
        ("DEMOTED_HOT_RECLAIMS", "DEMOTED_HOT"),
        ("OUTSIDE_RECLAIMS", "OUTSIDE"),
    ):
        require(metrics[label] == class_counts[category], f"{category}_COUNT")
    require(
        metrics["HOT_REALLOCATION_CANCEL_ACK_WAIT_MEAN_US"]
        == (sum(waits) / len(waits) if waits else None),
        "WAIT_MEAN",
    )
    require(
        metrics["HOT_REALLOCATION_CANCEL_ACK_WAIT_MEDIAN_US"] == (median(waits) if waits else None),
        "WAIT_MEDIAN",
    )
    require(metrics["HOT_REALLOCATION_CANCEL_ACK_WAIT_P95_US"] == _p95(waits), "WAIT_P95")
    require(
        D(metrics["HOT_FUNDING_COVERAGE_TIME_WEIGHTED"])
        == D(reconstructed["FULL_DAY_TIME_WEIGHTED"]),
        "FULL_DAY_COVERAGE",
    )
    require(
        D(metrics["HOT_FUNDING_COVERAGE_RANDOM_3H_TIME_WEIGHTED"])
        == D(reconstructed["RANDOM_3H_TIME_WEIGHTED"]),
        "RANDOM_COVERAGE",
    )
    require(
        D(metrics["RANDOM_3H_HOT_UNDERFUNDED_TIME_PCT"])
        == D(reconstructed["RANDOM_3H_HOT_UNDERFUNDED_TIME_PCT"]),
        "RANDOM_UNDERFUNDED",
    )
    require(
        D(metrics["RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"])
        == D(reconstructed["RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"]),
        "RANDOM_STRANDED",
    )
    require(
        D(metrics["RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"])
        == D(reconstructed["RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"]),
        "FULL_DAY_LITERAL_STRANDED",
    )
    require(
        D(metrics["HOT_UNDERFUNDED_TIME_PCT"]) == D(reconstructed["HOT_UNDERFUNDED_TIME_PCT"]),
        "FULL_DAY_UNDERFUNDED",
    )
    for side in ("BUY", "SELL"):
        require(
            D(metrics["HOT_FUNDING_COVERAGE"][side]["FULL_DAY_TIME_WEIGHTED"])
            == D(reconstructed[f"{side}_FULL_DAY_TIME_WEIGHTED"]),
            f"{side}_COVERAGE",
        )
    require(
        metrics["INTERMEDIATE_RECONCILES_AVOIDED"]
        == sum(max(0, int(row["jump_ticks"]) - 1) for row in jumps),
        "JUMP_RECONCILIATION",
    )
    require(
        metrics["MULTI_TICK_BOOK_MOVES"] == sum(int(row["jump_ticks"]) > 1 for row in jumps),
        "MULTI_TICK_MOVES",
    )
    require(
        metrics["TOTAL_TICKS_CROSSED"] == sum(int(row["jump_ticks"]) for row in jumps),
        "TICKS",
    )
    require(extra["reclaim_request_count"] == len(requests), "TERMINAL_REQUEST_COUNT")
    require(extra["reclaim_ack_count"] == len(acknowledgements), "TERMINAL_ACK_COUNT")
    require(
        extra["reclaim_terminal_without_ack"] == len(rejected_terminals),
        "TERMINAL_REJECTED_COUNT",
    )
    require(
        extra["reclaim_full_fill_terminal"] == len(full_fill_terminals),
        "TERMINAL_FULL_FILL_COUNT",
    )
    require(extra["reclaim_ack_waits"] == waits, "TERMINAL_WAITS")
    for asset in ("USDT", "USDC"):
        require(
            D(extra["reclaimed_pool"][asset]) == reclaimed_pool[asset],
            f"TERMINAL_{asset}_RECLAIMED_POOL",
        )
    require(
        extra["hotline_jump_ticks"] == [int(row["jump_ticks"]) for row in jumps],
        "TERMINAL_JUMPS",
    )
    require(extra["adaptations"] == metrics["HOTLINE_ADAPTATIONS"], "ADAPTATIONS")
    total_time = D(END_US - START_US)
    eval_time = D(extra["eval_observed_time_us"])
    require(eval_time == D(10_800_000_000), "EVALUATION_OBSERVED_TIME")
    require(
        D(metrics["HOT_MISSING_SLOT_UNITS_TIME"]) == D(extra["hot_missing_slot_units_time"]),
        "MISSING_SLOT_TIME",
    )
    require(
        metrics["HOT_MISSING_CELLS_TIME_US"] == extra["hot_missing_cells_time_us"],
        "MISSING_CELL_TIME",
    )
    require(
        D(metrics["TRUE_CAPITAL_SHORTFALL_TIME_PCT"])
        == D(extra["true_shortfall_time_us"]) / total_time * D(100),
        "SHORTFALL_TIME",
    )
    require(
        D(metrics["TRUE_CAPITAL_SHORTFALL_TIME_PCT"])
        <= D(reconstructed["HOT_UNDERFUNDED_TIME_PCT"]),
        "SHORTFALL_EXCEEDS_INDEPENDENT_UNDERFUNDED_TIME",
    )
    require(
        D(metrics["RAW_ENGINE_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"])
        == D(extra["reclaimable_stranded_time_us"]) / total_time * D(100),
        "RAW_STRANDED_TIME",
    )
    require(
        D(metrics["RAW_ENGINE_RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"])
        == D(extra["eval_reclaimable_stranded_time_us"]) / eval_time * D(100),
        "RAW_RANDOM_STRANDED_TIME",
    )
    require(
        D(metrics["HOT_INCOMPLETE_WITH_ADMINISTRATIVE_CAPACITY_TIME_PCT"])
        == D(administrative["FULL_DAY_TIME_PCT"]),
        "FULL_DAY_ADMINISTRATIVE_CAPACITY",
    )
    require(
        D(metrics["RANDOM_3H_HOT_INCOMPLETE_WITH_ADMINISTRATIVE_CAPACITY_TIME_PCT"])
        == D(administrative["RANDOM_3H_TIME_PCT"]),
        "RANDOM_ADMINISTRATIVE_CAPACITY",
    )
    require(
        D(metrics["RANDOM_3H_TRUE_CAPITAL_SHORTFALL_TIME_PCT"])
        == D(extra["eval_true_shortfall_time_us"]) / eval_time * D(100),
        "RANDOM_SHORTFALL_TIME",
    )
    require(metrics["TRUE_CAPITAL_SHORTFALL_EVENTS"] == len(shortfall_events), "SHORTFALL_EVENTS")
    require(
        extra["true_shortfall_events"] == len(shortfall_events),
        "TERMINAL_SHORTFALL_EVENTS",
    )
    require(
        not extra["true_shortfall_time_us"] or shortfall_events,
        "SHORTFALL_TIME_WITHOUT_EVENT",
    )
    for row in shortfall_events:
        required = D(row["required"])
        demonstrated = (
            D(row["operational_available"])
            + D(row["reclaimable_capital_available"])
            + D(row["mobility_available"])
        )
        require(required > demonstrated, "SHORTFALL_EVENT_HAS_CAPITAL")
        require(row["cell_id"].startswith(f"{row['side']}:P"), "SHORTFALL_CELL_SIDE")
    require(
        metrics["PHYSICAL_GRID_RECONCILES"] == extra["physical_reconciles"], "PHYSICAL_RECONCILES"
    )
    require(metrics["HOT_SUBMIT_BLOCKS"] == extra["hot_submit_blocks"], "HOT_BLOCKS")
    require(metrics["HOT_SUBMIT_SUCCESS"] == extra["hot_submit_success"], "HOT_SUCCESS")
    require(metrics["HOT_PROFIT_FLOOR_BLOCKS"] == len(profit_floor_blocks), "PROFIT_FLOOR_BLOCKS")
    require(
        extra["profit_floor_blocks"] == len(profit_floor_blocks), "TERMINAL_PROFIT_FLOOR_BLOCKS"
    )
    return {
        **base,
        "status": "PASS_M030_HOTLINE_FIRST_LEDGER_TERMINAL_AND_MASK_AUDIT",
        "random_mask_reconciled": True,
        "hotline_jump_reconciled": True,
        "cancel_ack_reconciled": True,
        "coverage_reconstructed_from_ledger": reconstructed,
        "administrative_capacity_reconstructed_from_ledger": administrative,
        "reclaim_lifecycle_reconciled": True,
        "reclaimed_capital_reconciled": True,
        "protected_economic_positions": True,
    }


__all__ = [
    "independent_m030_audit",
    "normalize_m030_reporting_metrics",
    "reconstruct_m029_hot_coverage",
    "reconstruct_m030_administrative_capacity",
]
