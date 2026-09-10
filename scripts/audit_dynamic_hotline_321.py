"""Independent terminal/ledger audit for M026."""

from __future__ import annotations

from decimal import ROUND_HALF_UP
from decimal import Decimal as D
from itertools import pairwise
from typing import Any

from crypto_strategy_lab.domain import canonical_hash


def independent_dynamic_hotline_audit(
    rows: list[dict[str, Any]],
    terminal: dict[str, Any],
    metrics: dict[str, Any],
    canonical: dict[str, Any],
) -> dict[str, Any]:
    def require(condition: bool, reason: str) -> None:
        if not condition:
            raise ValueError(f"M026_AUDIT_{reason}")

    state = terminal.get("state")
    require(isinstance(state, dict), "TERMINAL_STATE")
    require(terminal.get("schema") == "M026_DYNAMIC_HOTLINE_321_V1", "SCHEMA")
    require(terminal.get("sha256") == canonical_hash(state), "TERMINAL_HASH")
    parent, extra = state["parent"], state["m026"]
    require(canonical_hash(parent["audit"]) == canonical_hash(rows), "LEDGER_BINDING")
    orders = {int(row["order_id"]): row for row in parent["orders"]}
    require(len(orders) == len(parent["orders"]), "DUPLICATE_ORDER_ID")
    submits = {int(row["order_id"]): row for row in rows if row["event"] == "SUBMIT"}
    require(set(submits) == set(orders), "SUBMIT_COVERAGE")
    for order_id, order in orders.items():
        submit = submits[order_id]
        require(D(order["quantity"]) == D(submit["quantity"]), "ORDER_RESIZED")
        require(D(order["price"]) == D(submit["price"]), "ORDER_REPRICED")
        require(order["submitted_us"] == submit["time_us"], "ORDER_AGE_RESET")
        require(D(order["quantity"]) % 1 == 0 and D(order["quantity"]) >= 1, "STEP_SIZE")
        meta = extra["order_meta"][str(order_id)]
        require(int(meta["slot_count"]) == int(submit["slot_count"]), "META_SLOT_BINDING")
        require(int(meta["slot_epoch"]) == int(submit["slot_epoch"]), "META_EPOCH_BINDING")
        require(D(meta["slot_base"]) == D(submit["slot_base_epoch"]), "META_BASE_BINDING")
        require(
            D(meta["target_notional"]) == D(submit["target_slot_notional"]), "META_TARGET_BINDING"
        )
        actual_notional = D(submit["price"]) * D(submit["quantity"])
        require(D(meta["actual_notional"]) == actual_notional, "META_ACTUAL_BINDING")
        require(D(submit["actual_order_notional"]) == actual_notional, "SUBMIT_ACTUAL_BINDING")
        error = actual_notional - D(submit["target_slot_notional"])
        require(D(meta["quantization_error"]) == error, "META_QUANTIZATION_ERROR")
        require(D(submit["quantization_error"]) == error, "SUBMIT_QUANTIZATION_ERROR")
        if submit["role"] == "ENTRY":
            expected_quantity = max(
                D(1),
                (D(submit["target_slot_notional"]) / D(submit["price"])).to_integral_value(
                    rounding=ROUND_HALF_UP
                ),
            )
            require(D(submit["quantity"]) == expected_quantity, "QUANTIZATION_POLICY")
        else:
            source_id = int(submit["source_order_id"])
            require(source_id in submits, "RETURN_SOURCE_SUBMIT_MISSING")
            require(
                D(submit["quantity"]) == D(submits[source_id]["quantity"]),
                "RETURN_QUANTITY_NOT_PRESERVED",
            )
        require(meta["origin_zone"] == submit["origin_zone"], "META_ZONE_BINDING")
        require(D(meta["line_price"]) == D(submit["line_price"]), "META_LINE_BINDING")
    trade_rows = [row for row in rows if row["event"] == "TRADE"]
    trades = {str(row["trade_id"]): row for row in trade_rows}
    require(len(trades) == len(trade_rows), "DUPLICATE_TRADE")
    canonical_by_id = {str(key): value for key, value in canonical.items()}
    require(set(trades) == set(canonical_by_id), "CANONICAL_TRADE_COVERAGE")
    for trade_id, row in trades.items():
        source = canonical_by_id[trade_id]
        require(D(row["price"]) == source.price, "CANONICAL_TRADE_PRICE")
        require(D(row["original_quantity"]) == source.quantity, "CANONICAL_TRADE_QUANTITY")
        require(row["buyer_maker"] is source.buyer_maker, "CANONICAL_TRADE_SIDE")
        require(int(row["native_time_us"]) == source.time_us, "CANONICAL_TRADE_TIME")
    lifecycle: dict[int, dict[str, Any]] = {}
    queue_groups: dict[tuple[str, D], list[dict[str, Any]]] = {}
    fill_by_trade: dict[str, D] = {}
    reconstructed_fills = 0
    for row in rows:
        event = row["event"]
        if event == "SUBMIT":
            order_id = int(row["order_id"])
            require(order_id not in lifecycle, "DUPLICATE_SUBMIT")
            lifecycle[order_id] = {
                "status": "PENDING",
                "quantity": D(row["quantity"]),
                "filled": D(0),
                "cancel_us": None,
            }
        elif event == "ACTIVATED":
            order_id = int(row["order_id"])
            require(order_id in lifecycle, "ACTIVATION_UNKNOWN_ORDER")
            require(
                lifecycle[order_id]["status"] in {"PENDING", "CANCEL_PENDING"}, "ACTIVATION_STATE"
            )
            if lifecycle[order_id]["status"] == "PENDING":
                lifecycle[order_id]["status"] = "ACTIVE"
            saved = orders[order_id]
            key = (saved["side"], D(saved["price"]))
            segments = queue_groups.setdefault(key, [])
            activation_us = int(row["cohort_activation_us"])
            if segments and segments[-1]["activation_us"] == activation_us:
                segment = segments[-1]
            else:
                segment = {
                    "activation_us": activation_us,
                    "native_book_upper_us": int(row["native_book_upper_us"] or 0),
                    "barrier": D(0),
                    "public_remaining": D(0),
                    "order_ids": [],
                }
                segments.append(segment)
            barrier = D(row["public_barrier_added"])
            require(barrier >= 0, "NEGATIVE_PUBLIC_BARRIER")
            segment["barrier"] += barrier
            segment["public_remaining"] += barrier
            segment["order_ids"].append(order_id)
            require(
                sum((item["public_remaining"] for item in segments), D(0))
                == D(row["public_remaining"]),
                "ACTIVATION_PUBLIC_QUEUE_TOTAL",
            )
        elif event == "CANCEL_REQUEST":
            order_id = int(row["order_id"])
            require(order_id in lifecycle, "CANCEL_UNKNOWN_ORDER")
            require(lifecycle[order_id]["status"] in {"PENDING", "ACTIVE"}, "CANCEL_STATE")
            require(lifecycle[order_id]["filled"] == 0, "PARTIAL_CANCEL")
            lifecycle[order_id]["status"] = "CANCEL_PENDING"
            lifecycle[order_id]["cancel_us"] = int(row["effective_us"])
        elif event == "CANCEL_ACK":
            order_id = int(row["order_id"])
            require(order_id in lifecycle, "CANCEL_ACK_UNKNOWN_ORDER")
            require(lifecycle[order_id]["status"] == "CANCEL_PENDING", "CANCEL_ACK_STATE")
            require(int(row["time_us"]) >= lifecycle[order_id]["cancel_us"], "EARLY_CANCEL_ACK")
            lifecycle[order_id]["status"] = (
                "CANCELED_PARTIAL" if lifecycle[order_id]["filled"] > 0 else "CANCELED"
            )
        elif event.startswith("REJECTED_"):
            order_id = int(row["order_id"])
            require(order_id in lifecycle, "REJECTION_UNKNOWN_ORDER")
            require(
                lifecycle[order_id]["status"] in {"PENDING", "CANCEL_PENDING"}, "REJECTION_STATE"
            )
            lifecycle[order_id]["status"] = event
        elif event == "FILL":
            order_id = int(row["order_id"])
            require(order_id in lifecycle, "FILL_UNKNOWN_ORDER")
            require(lifecycle[order_id]["status"] in {"ACTIVE", "CANCEL_PENDING"}, "FILL_STATE")
            trade_id = str(row["source_id"])
            require(trade_id in trades, "FILL_UNKNOWN_TRADE")
            saved = orders[order_id]
            trade = trades[trade_id]
            source = canonical_by_id[trade_id]
            require(row["side"] == saved["side"], "FILL_SIDE_BINDING")
            require(D(row["price"]) == D(saved["price"]), "FILL_PRICE_BINDING")
            require(int(row["time_us"]) == int(trade["time_us"]), "FILL_LOGICAL_TIME")
            require(
                source.time_us
                > max(
                    int(saved["active_us"]),
                    int(saved["activation_evaluated_us"] or 0),
                    int(saved["activation_native_upper_us"] or 0),
                ),
                "FILL_BEFORE_NATIVE_ELIGIBILITY",
            )
            require(
                (
                    saved["side"] == "BUY"
                    and source.buyer_maker
                    and source.price <= D(saved["price"])
                )
                or (
                    saved["side"] == "SELL"
                    and not source.buyer_maker
                    and source.price >= D(saved["price"])
                ),
                "FILL_TRADE_DIRECTION_OR_PRIORITY",
            )
            key = (saved["side"], D(saved["price"]))
            segments = queue_groups.get(key, [])
            first_eligible: int | None = None
            exact = source.price == D(saved["price"])
            for segment in segments:
                if source.time_us <= max(
                    int(segment["activation_us"]),
                    int(segment["native_book_upper_us"]),
                ):
                    continue
                if exact and segment["public_remaining"] > 0:
                    break
                for candidate_id in segment["order_ids"]:
                    candidate = lifecycle[candidate_id]
                    if (
                        candidate["status"] in {"ACTIVE", "CANCEL_PENDING"}
                        and candidate["filled"] < candidate["quantity"]
                    ):
                        first_eligible = candidate_id
                        break
                if first_eligible is not None:
                    break
            require(first_eligible == order_id, "OWN_FIFO_OR_PUBLIC_BARRIER")
            amount = D(row["quantity"])
            require(amount > 0, "NONPOSITIVE_FILL")
            lifecycle[order_id]["filled"] += amount
            require(
                lifecycle[order_id]["filled"] <= lifecycle[order_id]["quantity"],
                "ORDER_OVERFILL",
            )
            fill_by_trade[trade_id] = fill_by_trade.get(trade_id, D(0)) + amount
            reconstructed_fills += 1
            if lifecycle[order_id]["filled"] == lifecycle[order_id]["quantity"]:
                lifecycle[order_id]["status"] = "FILLED"
        elif event == "PUBLIC_QUEUE_CONSUMED":
            key = (str(row["side"]), D(row["price"]))
            segments = queue_groups.get(key)
            require(segments is not None, "PUBLIC_QUEUE_GROUP_MISSING")
            cohort = int(row["cohort_activation_us"])
            segment = next((item for item in segments if item["activation_us"] == cohort), None)
            require(segment is not None, "PUBLIC_QUEUE_COHORT_MISSING")
            trade_id = str(row["source_id"])
            require(trade_id in trades, "PUBLIC_QUEUE_UNKNOWN_TRADE")
            source = canonical_by_id[trade_id]
            require(source.price == key[1], "PUBLIC_QUEUE_NONEXACT_TRADE")
            amount = D(row["quantity"])
            require(D(0) < amount <= segment["public_remaining"], "PUBLIC_QUEUE_OVERCONSUMED")
            segment["public_remaining"] -= amount
    require(set(lifecycle) == set(orders), "LIFECYCLE_ORDER_COVERAGE")
    for trade_id, amount in fill_by_trade.items():
        require(amount <= D(trades[trade_id]["original_quantity"]), "TRADE_FILL_OVERUSE")
    public_by_trade: dict[str, D] = {}
    for row in rows:
        if row["event"] != "PUBLIC_QUEUE_CONSUMED":
            continue
        trade_id = str(row["source_id"])
        require(trade_id in trades, "PUBLIC_QUEUE_UNKNOWN_TRADE")
        public_by_trade[trade_id] = public_by_trade.get(trade_id, D(0)) + D(row["quantity"])
    for trade_id, trade in trades.items():
        reconstructed = fill_by_trade.get(trade_id, D(0)) + public_by_trade.get(trade_id, D(0))
        require(reconstructed == D(trade["consumed_quantity"]), "TRADE_CONSUMPTION_RECONSTRUCTION")
    require(reconstructed_fills == int(parent["fill_count"]), "STATE_FILL_COUNTER")
    require(reconstructed_fills == int(metrics["TOTAL_FILLS"]), "METRIC_FILL_COUNTER")
    for order_id, actual in lifecycle.items():
        saved = orders[order_id]
        require(D(saved["filled"]) == actual["filled"], "TERMINAL_FILLED_BINDING")
        require(saved["status"] == actual["status"], "TERMINAL_STATUS_BINDING")
    saved_groups = {(str(group["side"]), D(group["price"])): group for group in parent["groups"]}
    require(set(saved_groups) == set(queue_groups), "TERMINAL_QUEUE_GROUP_SET")
    for key, segments in queue_groups.items():
        saved_segments = saved_groups[key]["segments"]
        require(len(saved_segments) == len(segments), "TERMINAL_QUEUE_SEGMENT_COUNT")
        for reconstructed, saved in zip(segments, saved_segments, strict=True):
            live_ids = [
                order_id
                for order_id in reconstructed["order_ids"]
                if lifecycle[order_id]["status"] in {"ACTIVE", "CANCEL_PENDING"}
            ]
            require(saved["order_ids"] == live_ids, "TERMINAL_OWN_FIFO_MEMBERSHIP")
            require(
                D(saved["public_remaining"]) == reconstructed["public_remaining"],
                "TERMINAL_PUBLIC_REMAINING",
            )
            require(
                D(saved["public_barrier"]) == reconstructed["barrier"],
                "TERMINAL_PUBLIC_BARRIER",
            )

    cash = D(metrics["INITIAL_USDT"])
    free_usdc = D(metrics["INITIAL_USDC"])
    reserved_quote = reserved_base = inventory = D(0)
    buy_reserve = D(metrics["INITIAL_BUY_MOBILITY_RESERVE"])
    sell_reserve = D(metrics["INITIAL_SELL_MOBILITY_RESERVE"])
    min_buy_reserve, min_sell_reserve = buy_reserve, sell_reserve
    account_orders: dict[int, dict[str, Any]] = {}
    disposal_pnl = D(0)
    usdc_cost_basis_total = D(metrics["INITIAL_USDC"]) * D(extra["decimal"]["initial_sell_basis"])
    for row in rows:
        event = row["event"]
        if event == "SUBMIT":
            order_id = int(row["order_id"])
            quantity, price = D(row["quantity"]), D(row["price"])
            usdt_lock = D(row["mobility_usdt_locked"])
            usdc_lock = D(row["mobility_usdc_locked"])
            account_orders[order_id] = {
                "side": row["side"],
                "role": row["role"],
                "direction": row["direction"],
                "quantity": quantity,
                "price": price,
                "filled": D(0),
                "asset_basis": D(row["asset_basis"]),
                "asset_cost_remaining": D(row["asset_cost_reserved"]),
                "asset_cost_layers": [
                    {
                        "quantity": D(layer["quantity"]),
                        "basis": D(layer["basis"]),
                        "mobility": bool(layer["mobility"]),
                    }
                    for layer in row["asset_cost_layers"]
                ],
                "usdt_lock_original": usdt_lock,
                "usdc_lock_original": usdc_lock,
                "usdt_lock": usdt_lock,
                "usdc_lock": usdc_lock,
            }
            if row["side"] == "BUY":
                cash -= quantity * price
                reserved_quote += quantity * price
                buy_reserve -= usdt_lock
            elif row["role"] == "RETURN" and row["direction"] == "BUY_FIRST":
                inventory -= quantity
                reserved_base += quantity
            else:
                free_usdc -= quantity
                reserved_base += quantity
                sell_reserve -= usdc_lock
        elif event == "FILL":
            order = account_orders[int(row["order_id"])]
            amount = D(row["quantity"])
            order["filled"] += amount
            if order["side"] == "BUY":
                reserved_quote -= amount * order["price"]
                order["usdt_lock"] = min(
                    order["usdt_lock_original"],
                    (order["quantity"] - order["filled"]) * order["price"],
                )
                usdc_cost_basis_total += amount * order["price"]
                if order["role"] == "ENTRY":
                    inventory += amount
                else:
                    free_usdc += amount
            else:
                remaining_cost_quantity = amount
                expected_cost = D(0)
                while remaining_cost_quantity > 0 and order["asset_cost_layers"]:
                    layer = order["asset_cost_layers"][0]
                    take = min(layer["quantity"], remaining_cost_quantity)
                    expected_cost += take * layer["basis"]
                    layer["quantity"] -= take
                    remaining_cost_quantity -= take
                    if layer["quantity"] == 0:
                        order["asset_cost_layers"].pop(0)
                require(remaining_cost_quantity == 0, "SELL_FILL_ASSET_COST_LAYER_EXHAUSTED")
                order["usdc_lock"] = sum(
                    (
                        layer["quantity"]
                        for layer in order["asset_cost_layers"]
                        if layer["mobility"]
                    ),
                    D(0),
                )
                require(
                    D(row["asset_cost_consumed"]) == expected_cost,
                    "SELL_FILL_ASSET_COST_ALLOCATION",
                )
                order["asset_cost_remaining"] -= expected_cost
                usdc_cost_basis_total -= expected_cost
                reserved_base -= amount
                cash += amount * order["price"]
                disposal_pnl += amount * order["price"] - expected_cost
        elif event == "CANCEL_ACK" or event.startswith("REJECTED_"):
            order = account_orders[int(row["order_id"])]
            remaining = order["quantity"] - order["filled"]
            if order["side"] == "BUY":
                reserved_quote -= remaining * order["price"]
                cash += remaining * order["price"]
                buy_reserve += order["usdt_lock"]
            else:
                reserved_base -= remaining
                if order["role"] == "RETURN" and order["direction"] == "BUY_FIRST":
                    inventory += remaining
                else:
                    free_usdc += remaining
                    sell_reserve += order["usdc_lock"]
                order["asset_cost_remaining"] = D(0)
                order["asset_cost_layers"] = []
            order["usdt_lock"] = order["usdc_lock"] = D(0)
        elif event == "BUY_MOBILITY_RESERVE_RESTORED":
            buy_reserve += D(row["amount"])
        elif event == "SELL_MOBILITY_RESERVE_RESTORED":
            sell_reserve += D(row["quantity"])
        min_buy_reserve = min(min_buy_reserve, buy_reserve)
        min_sell_reserve = min(min_sell_reserve, sell_reserve)
        require(
            min(cash, free_usdc, reserved_quote, reserved_base, inventory) >= 0,
            "NEGATIVE_RECONSTRUCTED_CAPITAL",
        )
        require(min(buy_reserve, sell_reserve) >= 0, "NEGATIVE_RECONSTRUCTED_RESERVE")
    for field, actual in {
        "cash": cash,
        "free_usdc": free_usdc,
        "reserved_usdt": reserved_quote,
        "reserved_usdc": reserved_base,
        "inventory_qty": inventory,
    }.items():
        require(D(parent[field]) == actual, f"CAPITAL_RECONSTRUCTION:{field}")
    require(
        D(extra["decimal"]["buy_mobility_reserve"]) == buy_reserve,
        "BUY_RESERVE_RECONSTRUCTION",
    )
    require(
        D(extra["decimal"]["sell_mobility_reserve"]) == sell_reserve,
        "SELL_RESERVE_RECONSTRUCTION",
    )
    require(D(metrics["NORMALIZED_BALANCE_QUANTUM"]) == D("0.00000001"), "BALANCE_QUANTUM")
    require(
        D(metrics["UNALLOCATED_USDC_QUANTIZATION_DUST"])
        == D(extra["decimal"]["unallocated_usdc_quantization_dust"]),
        "USDC_DUST_BINDING",
    )
    require(D(metrics["UNALLOCATED_USDC_QUANTIZATION_DUST"]) >= 0, "NEGATIVE_USDC_DUST")
    require(D(metrics["MIN_BUY_MOBILITY_RESERVE"]) == min_buy_reserve, "BUY_RESERVE_MIN")
    require(D(metrics["MIN_SELL_MOBILITY_RESERVE"]) == min_sell_reserve, "SELL_RESERVE_MIN")
    require(D(parent["realized_disposal_pnl"]) == disposal_pnl, "DISPOSAL_PNL_RECONSTRUCTION")
    require(
        D(extra["decimal"]["usdc_cost_basis_total"]) == usdc_cost_basis_total,
        "USDC_COST_BASIS_RECONSTRUCTION",
    )
    saved_order_costs = {
        int(key): D(value) for key, value in extra["order_asset_cost_remaining"].items()
    }
    require(
        saved_order_costs
        == {order_id: row["asset_cost_remaining"] for order_id, row in account_orders.items()},
        "ORDER_ASSET_COST_RECONSTRUCTION",
    )
    saved_order_cost_layers = {
        int(key): [
            {
                "quantity": D(row["quantity"]),
                "basis": D(row["basis"]),
                "mobility": bool(row["mobility"]),
            }
            for row in layers
        ]
        for key, layers in extra["order_asset_cost_layers"].items()
    }
    require(
        saved_order_cost_layers
        == {order_id: row["asset_cost_layers"] for order_id, row in account_orders.items()},
        "ORDER_ASSET_COST_LAYER_RECONSTRUCTION",
    )
    final_usdt = cash + reserved_quote
    final_usdc = free_usdc + reserved_base + inventory
    mark = D(parent["last_book"]["bids"][0][0])
    final_total = final_usdt + final_usdc * mark
    initial_total = D(parent["initial_mark"])
    reconstructed_unrealized = final_total - initial_total - disposal_pnl
    for field, expected in {
        "INITIAL_USDT": D(parent["initial_usdt"]),
        "INITIAL_USDC": D(parent["initial_usdc"]),
        "INITIAL_TOTAL": initial_total,
        "INITIAL_TOTAL_MARKED": initial_total,
        "FINAL_USDT": final_usdt,
        "FINAL_USDC": final_usdc,
        "FINAL_TOTAL": final_total,
        "FINAL_TOTAL_MARKED": final_total,
        "REALIZED_DISPOSAL_PNL": disposal_pnl,
        "UNREALIZED_PNL": reconstructed_unrealized,
        "PNL_IDENTITY_RESIDUAL": D(0),
    }.items():
        require(D(metrics[field]) == expected, f"FINANCIAL_METRIC:{field}")
    for group in parent["groups"]:
        own_ids = [oid for segment in group["segments"] for oid in segment["order_ids"]]
        require(len(own_ids) == len(set(own_ids)), "DUPLICATE_QUEUE_MEMBERSHIP")
        ordered = sorted(
            own_ids,
            key=lambda oid: (
                orders[oid]["activation_evaluated_us"] or 0,
                orders[oid]["submitted_us"],
                oid,
            ),
        )
        require(own_ids == ordered, "OWN_FIFO_ORDER")
        require(
            all(D(segment["public_remaining"]) >= 0 for segment in group["segments"]),
            "PUBLIC_QUEUE_NEGATIVE",
        )
    require(
        all(D(row["consumed_quantity"]) <= D(row["original_quantity"]) for row in trade_rows),
        "TRADE_BUDGET",
    )
    cycles = [row for row in rows if row["event"] == "CYCLE"]
    require(len(cycles) == int(metrics["PHYSICAL_CYCLES"]), "PHYSICAL_CYCLE_COUNT")
    slot_sum = sum(int(row["slot_equivalent_weight"]) for row in cycles)
    require(slot_sum == int(metrics["SLOT_EQUIVALENT_CYCLES"]), "SLOT_CYCLE_COUNT")
    require(all(D(row["profit"]) > 0 for row in cycles), "NONPOSITIVE_CYCLE")
    require(all(row["physical_weight"] == 1 for row in cycles), "PHYSICAL_WEIGHT")
    require(
        all(row["slot_equivalent_weight"] == row["entry_slot_count"] for row in cycles),
        "SLOT_WEIGHT",
    )
    cycle_return_ids: set[int] = set()
    reconstructed_cycle_pnl = D(0)
    order_meta = {int(key): value for key, value in extra["order_meta"].items()}
    for row in cycles:
        return_id = int(row["return_order_id"])
        entry_id = int(row["entry_order_id"])
        require(return_id not in cycle_return_ids, "DUPLICATE_RETURN_CYCLE")
        require(return_id in orders and entry_id in orders, "CYCLE_UNKNOWN_ORDER")
        require(orders[return_id]["role"] == "RETURN", "CYCLE_NONRETURN_ORDER")
        require(orders[return_id]["source_order_id"] == entry_id, "CYCLE_SOURCE_BINDING")
        require(lifecycle[return_id]["status"] == "FILLED", "CYCLE_RETURN_NOT_FILLED")
        require(lifecycle[entry_id]["status"] == "FILLED", "CYCLE_ENTRY_NOT_FILLED")
        require(D(row["roundtrip_quantity"]) == D(orders[return_id]["quantity"]), "CYCLE_QUANTITY")
        require(D(row["entry_quantity"]) == D(orders[entry_id]["quantity"]), "ENTRY_QUANTITY")
        entry, returned = orders[entry_id], orders[return_id]
        expected_profit = D(returned["quantity"]) * (
            D(returned["price"]) - D(entry["price"])
            if entry["direction"] == "BUY_FIRST"
            else D(entry["price"]) - D(returned["price"])
        )
        require(D(row["profit"]) == expected_profit, "CYCLE_PROFIT_DERIVATION")
        expected_slots = int(order_meta[entry_id]["slot_count"])
        require(int(row["entry_slot_count"]) == expected_slots, "ENTRY_SLOT_DERIVATION")
        require(int(row["slot_equivalent_weight"]) == expected_slots, "SLOT_WEIGHT_DERIVATION")
        require(row["origin_zone"] == order_meta[entry_id]["origin_zone"], "CYCLE_ZONE_DERIVATION")
        require(
            int(row["entry_slot_epoch"]) == int(order_meta[entry_id]["slot_epoch"]),
            "CYCLE_EPOCH_DERIVATION",
        )
        require(int(row["column"]) == int(entry["column"]), "CYCLE_COLUMN_DERIVATION")
        reconstructed_cycle_pnl += expected_profit
        cycle_return_ids.add(return_id)
    require(int(parent["cycles"]) == len(cycles), "STATE_CYCLE_COUNTER")
    require(D(parent["realized_pnl"]) == reconstructed_cycle_pnl, "CYCLE_PNL_STATE")
    require(D(metrics["REALIZED_CYCLE_PNL"]) == reconstructed_cycle_pnl, "CYCLE_PNL_METRIC")
    epochs = extra["hotline_epochs"]
    require(len(epochs) == int(metrics["HOTLINE_EPOCHS"]), "EPOCH_COUNT")
    for old, new in pairwise(epochs):
        require(
            abs(D(new["HOTLINE_PRICE"]) - D(old["HOTLINE_PRICE"])) == D("0.0001"),
            "HOTLINE_NONUNIT_MOVE",
        )
    require(int(metrics["HOTLINE_CHANGES"]) == max(0, len(epochs) - 1), "HOTLINE_CHANGE_COUNT")
    require(int(metrics["INITIAL_OPEN_ENTRY_ORDERS"]) == 60, "INITIAL_GEOMETRY")
    require(int(metrics["MAX_SIMULTANEOUS_OPEN_ORDERS"]) <= 200, "OPEN_ORDER_CAP")
    require(D(metrics["PNL_IDENTITY_RESIDUAL"]) == 0, "PNL_IDENTITY")
    require(D(metrics["FINAL_USDC"]) >= 0 and D(metrics["FINAL_USDT"]) >= 0, "NEGATIVE_CAPITAL")
    require(D(metrics["MIN_BUY_MOBILITY_RESERVE"]) >= 0, "NEGATIVE_BUY_RESERVE")
    require(D(metrics["MIN_SELL_MOBILITY_RESERVE"]) >= 0, "NEGATIVE_SELL_RESERVE")
    require(extra["slot_cycles"] == slot_sum, "STATE_SLOT_COUNTER")
    require(
        sum((D(order["reserved_quote"]) for order in orders.values()), D(0))
        == D(parent["reserved_usdt"]),
        "QUOTE_RESERVATION_LEDGER",
    )
    require(
        sum((D(order["reserved_base"]) for order in orders.values()), D(0))
        == D(parent["reserved_usdc"]),
        "BASE_RESERVATION_LEDGER",
    )
    return {
        "status": "PASS_M026_INDEPENDENT_LEDGER_AND_TERMINAL_AUDIT",
        "orders_reconciled": len(orders),
        "trades_reconciled": len(trade_rows),
        "physical_cycles_reconciled": len(cycles),
        "slot_cycles_reconciled": slot_sum,
        "hotline_epochs_reconciled": len(epochs),
        "capital_identity_reconciled": True,
        "old_order_price_size_age_immutable": True,
        "segmented_fifo_reconciled": True,
        "trade_quantity_not_reused": True,
    }
