"""Independent geometry and inherited-ledger audit for M027."""

from __future__ import annotations

from decimal import Decimal as D
from statistics import median
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from scripts.audit_dynamic_hotline_321 import independent_dynamic_hotline_audit


def independent_micro_hot_audit(
    rows: list[dict[str, Any]],
    terminal: dict[str, Any],
    metrics: dict[str, Any],
    canonical: dict[int, Any],
    *,
    scenario: str,
) -> dict[str, Any]:
    def require(condition: bool, reason: str) -> None:
        if not condition:
            raise ValueError(f"M027_AUDIT_{reason}")

    state = terminal.get("state")
    require(terminal.get("schema") == "M027_MICRO_HOT_REALLOCATION_V1", "SCHEMA")
    require(isinstance(state, dict) and terminal.get("sha256") == canonical_hash(state), "HASH")
    require(state["scenario"] == scenario, "SCENARIO")
    parent = state["parent"]
    inherited = independent_dynamic_hotline_audit(rows, parent, metrics, canonical)
    submits = [row for row in rows if row["event"] == "SUBMIT"]
    initial_time = min(int(row["time_us"]) for row in submits)
    initial = [row for row in submits if int(row["time_us"]) == initial_time]
    require(len(initial) == 60, "INITIAL_ORDER_COUNT")
    require(sum(int(row["slot_count"]) for row in initial) == 140, "INITIAL_SLOT_UNITS")
    require(all(D(row["price"]) % D("0.00001") == 0 for row in submits), "FINE_TICK")
    micro = [row for row in submits if row["origin_zone"] == "MICRO"]
    initial_far_14_15 = [
        row for row in initial if row["origin_zone"] == "FAR" and int(row["level"]) in {14, 15}
    ]
    if scenario == "CONTROL":
        require(not micro, "CONTROL_HAS_MICRO")
        require(len(initial_far_14_15) == 4, "CONTROL_FAR14_15_MISSING")
    else:
        initial_micro = [row for row in initial if row["origin_zone"] == "MICRO"]
        require(len(initial_micro) == 4, "TREATMENT_INITIAL_MICRO_COUNT")
        require(not initial_far_14_15, "TREATMENT_HAS_FAR14_15")
        require(
            all(int(row["column"]) in {1, 2} and int(row["slot_count"]) == 1 for row in micro),
            "MICRO_SHAPE",
        )
        require(
            {(row["side"], row["price"]) for row in initial_micro}
            == {
                ("BUY", str(D(parent["state"]["m026"]["initial_hotline"]) - D("0.00005"))),
                ("SELL", str(D(parent["state"]["m026"]["initial_hotline"]) + D("0.00005"))),
            },
            "MICRO_OFFSET",
        )

    orders = {int(row["order_id"]): row for row in parent["state"]["parent"]["orders"]}
    submit_by_id = {int(row["order_id"]): row for row in submits}
    cycles = [row for row in rows if row["event"] == "CYCLE"]
    fills = [row for row in rows if row["event"] == "FILL"]
    activations = {
        int(row["order_id"]): int(row["time_us"]) for row in rows if row["event"] == "ACTIVATED"
    }

    def distance(order_id: int) -> str:
        submit = submit_by_id[order_id]
        if submit["origin_zone"] == "MICRO":
            return "MICRO"
        rank = int(submit["level"])
        if 1 <= rank <= 5:
            return f"RANK{rank}"
        if 6 <= rank <= 10:
            return "MID"
        if 11 <= rank <= 15:
            return f"FAR{rank}"
        return str(submit["origin_zone"])

    cycle_distance = {int(row["cycle_id"]): distance(int(row["entry_order_id"])) for row in cycles}
    require(len(cycles) == int(metrics["PHYSICAL_CYCLES"]), "PHYSICAL_CYCLES_METRIC")
    require(
        sum(int(row["slot_equivalent_weight"]) for row in cycles)
        == int(metrics["SLOT_EQUIVALENT_CYCLES"]),
        "SLOT_CYCLES_METRIC",
    )
    metric_distances = {row["DISTANCE"]: row for row in metrics["DISTANCE_TABLE"]}
    terminal_times = state["distance_order_time_us"]
    fill_ids = [int(row["order_id"]) for row in fills]
    last_fill = {int(row["order_id"]): int(row["time_us"]) for row in fills}
    for label, reported in metric_distances.items():
        label_cycles = [row for row in cycles if cycle_distance[int(row["cycle_id"])] == label]
        label_order_ids = {order_id for order_id in orders if distance(order_id) == label}
        waits = [
            last_fill[order_id] - activations[order_id]
            for order_id in label_order_ids
            if orders[order_id]["status"] == "FILLED"
            and order_id in activations
            and order_id in last_fill
        ]
        require(len(label_cycles) == int(reported["PHYSICAL_CYCLES"]), "DISTANCE_CYCLES")
        require(
            sum(int(row["slot_equivalent_weight"]) for row in label_cycles)
            == int(reported["SLOT_CYCLES"]),
            "DISTANCE_SLOT_CYCLES",
        )
        require(
            sum(order_id in label_order_ids for order_id in fill_ids) == int(reported["FILLS"]),
            "DISTANCE_FILLS",
        )
        require(
            D(reported["ORDER_HOURS"]) == D(terminal_times.get(label, 0)) / D("3600000000"),
            "DISTANCE_ORDER_TIME",
        )
        require(
            reported["MEDIAN_FILL_WAIT_US"] == (median(waits) if waits else None),
            "DISTANCE_FILL_WAIT",
        )

    micro_ids = {int(row["order_id"]) for row in micro}
    micro_cycles = [row for row in cycles if cycle_distance[int(row["cycle_id"])] == "MICRO"]
    require(
        int(metrics["MICRO_HOT_PHYSICAL_CYCLES"]) == len(micro_cycles),
        "MICRO_CYCLES_METRIC",
    )
    require(
        int(metrics["MICRO_C1_CYCLES"]) == sum(int(row["column"]) == 1 for row in micro_cycles),
        "MICRO_C1_METRIC",
    )
    require(
        int(metrics["MICRO_C2_CYCLES"]) == sum(int(row["column"]) == 2 for row in micro_cycles),
        "MICRO_C2_METRIC",
    )
    require(int(metrics["MICRO_ORDERS_CREATED"]) == len(micro_ids), "MICRO_CREATED")
    require(
        int(metrics["MICRO_FULL_FILLS"])
        == sum(orders[order_id]["status"] == "FILLED" for order_id in micro_ids),
        "MICRO_FULL_FILLS",
    )
    require(
        int(metrics["MICRO_PARTIAL_FILLS"])
        == sum(
            D(orders[order_id]["filled"]) > 0 and orders[order_id]["status"] != "FILLED"
            for order_id in micro_ids
        ),
        "MICRO_PARTIAL_FILLS",
    )
    require(
        int(metrics["MICRO_OPEN_AT_CUTOFF"])
        == sum(
            orders[order_id]["status"] in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
            for order_id in micro_ids
        ),
        "MICRO_OPEN",
    )
    touches = [row for row in rows if row["event"] == "MICRO_UNIQUE_PRICE_TOUCH"]
    touch_ids = {str(row["trade_id"]) for row in touches}
    require(len(touch_ids) == len(touches), "DUPLICATE_MICRO_TOUCH")
    require(touch_ids <= {str(key) for key in canonical}, "NONCANONICAL_MICRO_TOUCH")
    expected_touches: dict[str, dict[str, Any]] = {}
    hotline: D | None = None
    for row in rows:
        if row["event"] == "M027_GRID_INITIALIZED":
            hotline = D(row["hotline"])
        elif row["event"] == "HOTLINE_MOVED":
            hotline = D(row["new_price"])
        elif row["event"] == "TRADE" and hotline is not None and scenario == "TREATMENT":
            price = D(row["price"])
            micro_only = (
                bool(row["buyer_maker"]) and hotline - D("0.0001") < price <= hotline - D("0.00005")
            ) or (
                not bool(row["buyer_maker"])
                and hotline + D("0.00005") <= price < hotline + D("0.0001")
            )
            if micro_only:
                expected_touches[str(row["trade_id"])] = {
                    "time_us": int(row["time_us"]),
                    "price": price,
                    "hotline": hotline,
                }
    require(touch_ids == set(expected_touches), "MICRO_TOUCH_SET")
    for touch in touches:
        expected = expected_touches[str(touch["trade_id"])]
        require(int(touch["time_us"]) == expected["time_us"], "MICRO_TOUCH_TIME")
        require(D(touch["price"]) == expected["price"], "MICRO_TOUCH_PRICE")
        require(D(touch["hotline"]) == expected["hotline"], "MICRO_TOUCH_HOTLINE")
    require(int(metrics["MICRO_UNIQUE_PRICE_TOUCHES"]) == len(touches), "MICRO_TOUCH_METRIC")
    entry_fill_sources: dict[int, set[str]] = {}
    for row in fills:
        entry_fill_sources.setdefault(int(row["order_id"]), set()).add(str(row["source_id"]))
    reconstructed_unique_cycles = sum(
        bool(entry_fill_sources.get(int(row["entry_order_id"]), set()) & touch_ids)
        for row in micro_cycles
    )
    require(
        int(metrics["MICRO_CYCLES_WITHOUT_CONTROL_EQUIVALENT_TOUCH"])
        == reconstructed_unique_cycles,
        "MICRO_UNIQUE_CYCLES",
    )
    limiter = state["micro_limiter_time_us"]
    for metric_key, state_key in (
        ("MICRO_PUBLIC_FIFO_WAIT_US", "PUBLIC_FIFO_WAIT"),
        ("MICRO_OWN_FIFO_WAIT_US", "OWN_FIFO_WAIT"),
        ("MICRO_PRICE_RECOVERY_WAIT_US", "PRICE_RECOVERY_WAIT"),
    ):
        require(int(metrics[metric_key]) == int(limiter[state_key]), "MICRO_LIMITER_METRIC")
    return {
        **inherited,
        "status": "PASS_M027_INDEPENDENT_GEOMETRY_LEDGER_AND_TERMINAL_AUDIT",
        "scenario": scenario,
        "fine_tick_validated": True,
        "initial_orders_reconciled": len(initial),
        "initial_slot_units_reconciled": 140,
        "micro_orders_reconciled": len(micro),
        "far14_15_initial_orders": len(initial_far_14_15),
        "distance_metrics_reconstructed": True,
        "micro_metrics_reconstructed": True,
        "micro_touches_reconstructed": len(touches),
    }


__all__ = ["independent_micro_hot_audit"]
