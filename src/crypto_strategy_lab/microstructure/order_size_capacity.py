"""M025 order-size capacity scenarios built on the immutable M024 mechanics."""

from __future__ import annotations

from decimal import Decimal as D
from statistics import median
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.triangular_pre_aged_queue import (
    INITIAL_LEVELS,
    M021_TICK_SIZE,
    ZERO,
    QueueOrder,
    TriangularPreAgedQueueProbe,
    _ceil_tick,
    _dec,
    _floor_tick,
    _s,
)

AUTHORIZED_QUANTITIES = tuple(
    D(value) for value in (10, 50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000)
)


def _public_queue_zero_observations(
    audit: list[dict[str, Any]], order_by_id: dict[int, QueueOrder]
) -> dict[int, int]:
    """Return public-zero times observed before first fill/inactivation.

    Ledger ordinal is authoritative when events share a timestamp.  A public
    cohort depleted after a strict trade-through fill or after CANCEL_ACK is not
    retroactively attributed to the no-longer-observed order.
    """

    first_fill_index: dict[int, int] = {}
    inactive_index: dict[int, int] = {}
    for index, row in enumerate(audit):
        if row["event"] == "FILL":
            first_fill_index.setdefault(int(row["order_id"]), index)
        elif row["event"] == "CANCEL_ACK" or row["event"].startswith("REJECTED_"):
            inactive_index.setdefault(int(row["order_id"]), index)

    public_segments: dict[tuple[str, D], list[dict[str, Any]]] = {}
    relevant_segments: dict[int, tuple[int, ...]] = {}
    observed: dict[int, int] = {}
    for index, row in enumerate(audit):
        if row["event"] == "ACTIVATED":
            key = (row["side"], _dec(row["price"]))
            segments = public_segments.setdefault(key, [])
            cohort = int(row["cohort_activation_us"])
            if not segments or int(segments[-1]["cohort"]) != cohort:
                segments.append(
                    {"cohort": cohort, "remaining": _dec(row["public_barrier_added"])}
                )
            order_id = int(row["order_id"])
            relevant_segments[order_id] = tuple(
                int(segment["cohort"]) for segment in segments
            )
            if sum((segment["remaining"] for segment in segments), ZERO) == ZERO:
                observed[order_id] = int(row["time_us"])
        elif row["event"] == "PUBLIC_QUEUE_CONSUMED":
            key = (row["side"], _dec(row["price"]))
            segments = public_segments[key]
            cohort = int(row["cohort_activation_us"])
            segment = next(item for item in segments if int(item["cohort"]) == cohort)
            segment["remaining"] -= _dec(row["quantity"])
            for order_id, cohorts in relevant_segments.items():
                if order_id in observed:
                    continue
                order = order_by_id[order_id]
                if (order.side, order.price) != key:
                    continue
                observation_end = first_fill_index.get(
                    order_id, inactive_index.get(order_id, len(audit))
                )
                if index > observation_end:
                    continue
                if (
                    sum(
                        (
                            item["remaining"]
                            for item in segments
                            if int(item["cohort"]) in cohorts
                        ),
                        ZERO,
                    )
                    == ZERO
                ):
                    observed[order_id] = int(row["time_us"])
    return observed


class OrderSizeCapacityProbe(TriangularPreAgedQueueProbe):
    """M024 mechanics with one frozen scenario quantity and no growth expansion.

    M024 is not modified: this specialization binds every physical order in one
    scenario to ``order_quantity``.  Canceled partial entries remain owned and
    locked, exactly as M024 did for sub-step partials, but are named accurately
    for arbitrary Q and never count as a complete cycle.
    """

    normalized_label = (
        "M025 NORMALIZED CAPACITY CURVE. MIN_NOTIONAL IS VIRTUALIZED; "
        "QUEUE RANK IS MODELED AND ENDOGENOUS MARKET IMPACT IS ABSENT."
    )

    def __init__(self, *, order_quantity: D | str, **kwargs: Any) -> None:
        quantity = _dec(order_quantity)
        if quantity not in AUTHORIZED_QUANTITIES:
            raise ValueError("M025_UNAUTHORIZED_ORDER_QUANTITY")
        self.order_quantity = quantity
        self.growth_enabled = False
        super().__init__(**kwargs)

    def _record(self, event: str, time_us: int, **fields: Any) -> None:
        if event == "PARTIAL_LOT_SUBSTEP_LOCKED":
            event = "PARTIAL_ENTRY_CANCELED_LOCKED"
            fields.pop("minimum_order_quantity", None)
            fields["required_full_order_quantity"] = _s(self.order_quantity)
            fields["partial_return_created"] = False
            fields["cycle_counted"] = False
        super()._record(event, time_us, **fields)

    def submit_order(
        self,
        side: str,
        price: D | str,
        *,
        quantity: D | str | None = None,
        time_us: int | None = None,
        role: str = "ENTRY",
        column: int = 1,
        level: int = 1,
        direction: str = "BUY_FIRST",
        source_order_id: int | None = None,
        capital_source: str = "OWN",
        activate_immediately: bool = False,
        cell_id: str | None = None,
        asset_basis: D | str = ZERO,
    ) -> QueueOrder:
        actual = self.order_quantity if quantity is None else _dec(quantity)
        if actual != self.order_quantity:
            raise ValueError("M025_ORDER_QUANTITY_MISMATCH")
        now = self.start_us if time_us is None else int(time_us)
        self._check_time(now)
        if side not in {"BUY", "SELL"}:
            raise ValueError("M025_INVALID_ORDER_SIDE")
        if side == "SELL" and _dec(asset_basis) > ZERO and _dec(price) <= _dec(asset_basis):
            raise ValueError("M025_NEGATIVE_EXIT_PROHIBITED")
        if self.open_order_count >= self.max_open_orders:
            raise ValueError("M025_OPEN_ORDER_CAP_EXCEEDED")
        order = QueueOrder(
            self._next_order_id,
            side,
            _dec(price),
            actual,
            now,
            now if activate_immediately else now + self.latency_us,
            role=role,
            column=int(column),
            level=int(level),
            direction=direction,
            source_order_id=source_order_id,
            capital_source=capital_source,
            cell_id=cell_id or f"CELL:{self._next_order_id}",
            asset_basis=_dec(asset_basis),
        )
        self._reserve_for_order(order)
        self._next_order_id += 1
        self.orders.append(order)
        self._max_open_orders = max(self._max_open_orders, self.open_order_count)
        self._record(
            "SUBMIT",
            now,
            order_id=order.order_id,
            side=side,
            price=_s(order.price),
            quantity=_s(order.quantity),
            role=role,
            column=column,
            level=level,
            direction=direction,
            source_order_id=source_order_id,
            capital_source=capital_source,
            active_us=order.active_us,
            cell_id=order.cell_id,
            asset_basis=_s(order.asset_basis),
        )
        if activate_immediately:
            self._activate(order, now)
        return order

    add_order = submit_order

    def initialize_triangle(self, time_us: int) -> None:
        if self._initialized:
            return
        if self._last_book is None:
            raise ValueError("M025_BOOK_REQUIRED_FOR_INITIALIZATION")
        bid = self._last_book["bids"][0][0]
        ask = self._last_book["asks"][0][0]
        buy_prices = [
            _floor_tick(bid - D(index) * M021_TICK_SIZE) for index in range(INITIAL_LEVELS)
        ]
        sell_prices = [
            _ceil_tick(ask + D(index) * M021_TICK_SIZE) for index in range(INITIAL_LEVELS)
        ]
        self.initial_usdt = sum(
            (
                price * self.order_quantity
                for index, price in enumerate(buy_prices, 1)
                for _ in range(2 if index <= 25 else 1)
            ),
            ZERO,
        )
        self.initial_usdc = D(75) * self.order_quantity
        self.initial_mark = self.initial_usdt + self.initial_usdc * bid
        self.cash = self.initial_usdt
        self.free_usdc = ZERO
        self._initialized = True
        for index, price in enumerate(buy_prices, 1):
            for column in range(1, (2 if index <= 25 else 1) + 1):
                self.submit_order(
                    "BUY",
                    price,
                    time_us=time_us,
                    column=column,
                    level=index,
                    direction="BUY_FIRST",
                    cell_id=f"BUY:L{index:02d}:C{column}",
                )
        self.free_usdc = self.initial_usdc
        for index, price in enumerate(sell_prices, 1):
            for column in range(1, (2 if index <= 25 else 1) + 1):
                self.submit_order(
                    "SELL",
                    price,
                    time_us=time_us,
                    column=column,
                    level=index,
                    direction="SELL_FIRST",
                    cell_id=f"SELL:L{index:02d}:C{column}",
                    asset_basis=bid,
                )
        self._record(
            "TRIANGLE_INITIALIZED",
            time_us,
            order_quantity=_s(self.order_quantity),
            initial_usdt=_s(self.initial_usdt),
            initial_usdc=_s(self.initial_usdc),
            growth_enabled=False,
        )

    def _advance_shadow_queues(self, now: int) -> None:
        # Activation is quantity-agnostic in the M024 parent.
        super()._advance_shadow_queues(now)

    def _feed_shadow_queues(
        self,
        price: D,
        quantity: D,
        buyer_maker: bool,
        now: int,
        native_us: int,
        trade_id: str,
    ) -> None:
        # Same causal counterfactual as M024, generalized from 1 to shadow Q.
        for case in self._preaging_cases:
            shadow = case.get("shadow")
            if shadow is None or shadow["status"] != "ACTIVE":
                continue
            if now <= int(shadow["activation_us"]):
                continue
            if native_us <= max(
                int(shadow["active_us"]),
                int(shadow["activation_us"]),
                int(shadow["activation_native_upper_us"]),
            ):
                continue
            side = shadow["side"]
            eligible = (side == "BUY" and buyer_maker and price <= _dec(shadow["price"])) or (
                side == "SELL" and not buyer_maker and price >= _dec(shadow["price"])
            )
            if not eligible:
                continue
            remaining = quantity
            public_debit = own_debit = fill_debit = ZERO
            if price == _dec(shadow["price"]):
                public_debit = min(_dec(shadow["public_remaining"]), remaining)
                shadow["public_remaining"] = _s(_dec(shadow["public_remaining"]) - public_debit)
                remaining -= public_debit
            if remaining > ZERO:
                own_debit = min(_dec(shadow["own_remaining"]), remaining)
                shadow["own_remaining"] = _s(_dec(shadow["own_remaining"]) - own_debit)
                remaining -= own_debit
            shadow_quantity = _dec(shadow["quantity"])
            if remaining > ZERO:
                fill_debit = min(remaining, shadow_quantity - _dec(shadow["filled"]))
                shadow["filled"] = _s(_dec(shadow["filled"]) + fill_debit)
            if public_debit + own_debit + fill_debit > ZERO:
                self._record(
                    "SHADOW_TRADE_APPLIED",
                    now,
                    c2_order_id=case["c2_order_id"],
                    source_id=trade_id,
                    native_time_us=native_us,
                    price=_s(price),
                    original_quantity=_s(quantity),
                    public_debit=_s(public_debit),
                    own_debit=_s(own_debit),
                    fill_debit=_s(fill_debit),
                )
            if _dec(shadow["filled"]) >= shadow_quantity:
                shadow["status"] = "FILLED"
                shadow["fill_us"] = now
                self._record(
                    "SHADOW_FILL",
                    now,
                    c2_order_id=case["c2_order_id"],
                    price=shadow["price"],
                    source_id=trade_id,
                    native_time_us=native_us,
                )
                self._close_preaging_case(case)

    def _try_profit_funded_growth(self, now: int) -> None:
        # M025 measures the pool but freezes physical geometry for every Q.
        return

    def fund_growth_cell(self, *args: Any, **kwargs: Any) -> QueueOrder:
        raise ValueError("M025_GROWTH_EXPANSION_DISABLED")

    def metrics(self) -> dict[str, Any]:
        result = super().metrics()
        orders = self.orders
        fills = [row for row in self.audit if row["event"] == "FILL"]
        entry_orders = [order for order in orders if order.role == "ENTRY"]
        return_orders = [order for order in orders if order.role == "RETURN"]
        full_orders = [order for order in orders if order.status == "FILLED"]
        full_entries = [order for order in entry_orders if order.status == "FILLED"]
        full_returns = [order for order in return_orders if order.status == "FILLED"]
        partial_events = sum(_dec(row["quantity"]) < self.order_quantity for row in fills)
        filled_qty = sum((_dec(row["quantity"]) for row in fills), ZERO)
        two_way_notional = sum((_dec(row["quantity"]) * _dec(row["price"]) for row in fills), ZERO)
        first_fill_by_order: dict[int, int] = {}
        filled_running: dict[int, D] = {}
        full_fill_by_order: dict[int, int] = {}
        for row in fills:
            order_id = int(row["order_id"])
            first_fill_by_order.setdefault(order_id, int(row["time_us"]))
            filled_running[order_id] = filled_running.get(order_id, ZERO) + _dec(row["quantity"])
            if filled_running[order_id] == self.order_quantity:
                full_fill_by_order[order_id] = int(row["time_us"])
        complete_times = [
            full_fill_by_order[order.order_id] - order.submitted_us
            for order in full_orders
            if order.order_id in full_fill_by_order
        ]
        first_times = [
            at - order.submitted_us
            for order in orders
            if (at := first_fill_by_order.get(order.order_id)) is not None
        ]
        first_to_full = [
            full_fill_by_order[order.order_id] - first_fill_by_order[order.order_id]
            for order in full_orders
            if order.order_id in full_fill_by_order and order.order_id in first_fill_by_order
        ]
        cycle_rows = [row for row in self.audit if row["event"] == "CYCLE"]
        cycle_notional = ZERO
        entry_to_return: list[int] = []
        order_by_id = {order.order_id: order for order in orders}
        for row in cycle_rows:
            returned = order_by_id[int(row["order_id"])]
            source = order_by_id[int(returned.source_order_id)]
            cycle_notional += source.price * source.quantity
            if returned.order_id in full_fill_by_order:
                entry_to_return.append(full_fill_by_order[returned.order_id] - source.submitted_us)
        residual_partial_orders = [
            order for order in orders if ZERO < order.filled < order.quantity
        ]
        activated = [order for order in orders if order.activation_evaluated_us is not None]
        activation_rows = {
            int(row["order_id"]): row for row in self.audit if row["event"] == "ACTIVATED"
        }
        public_zero_by_order = _public_queue_zero_observations(self.audit, order_by_id)
        public_waits = [
            public_zero_by_order[order.order_id] - int(order.activation_evaluated_us)
            for order in activated
            if order.order_id in public_zero_by_order
        ]
        public_zero_to_first = [
            first_fill_by_order[order.order_id] - public_zero_by_order[order.order_id]
            for order in activated
            if order.order_id in public_zero_by_order and order.order_id in first_fill_by_order
        ]
        public_zero_to_full = [
            full_fill_by_order[order.order_id] - public_zero_by_order[order.order_id]
            for order in full_orders
            if order.order_id in public_zero_by_order and order.order_id in full_fill_by_order
        ]
        marked_qty, marked_cost, _marked_unrealized = self._marked_inventory(
            self._last_book["bids"][0][0] if self._last_book else ZERO
        )
        initial_equity = self.initial_mark
        cycles_per_hour = D(self._cycles) / D(3)
        completed_notional_per_hour = cycle_notional / D(3)
        completed_roundtrip = self.order_quantity * D(self._cycles)
        partially_filled = len(residual_partial_orders)
        partial_entry_orders = [order for order in residual_partial_orders if order.role == "ENTRY"]
        partial_return_orders = [
            order for order in residual_partial_orders if order.role == "RETURN"
        ]
        public_ahead = [
            _dec(activation_rows[order.order_id]["public_remaining"]) for order in activated
        ]
        own_ahead = [
            order.queue_ahead_at_activation
            - _dec(activation_rows[order.order_id]["public_remaining"])
            for order in activated
        ]
        public_consumption = [row for row in self.audit if row["event"] == "PUBLIC_QUEUE_CONSUMED"]
        order_notionals = [order.price * order.quantity for order in orders]

        def stats(values: list[int | D]) -> dict[str, int | float | D | None]:
            if not values:
                return {"mean": None, "median": None, "p95": None, "max": None}
            return {
                "mean": sum(values) / len(values),
                "median": median(values),
                "p95": self._percentile(values, 0.95),
                "max": max(values),
            }

        time_to_first_stats = stats(first_times)
        first_to_full_stats = stats(first_to_full)
        full_fill_stats = stats(complete_times)
        public_to_first_stats = stats(public_zero_to_first)
        public_to_full_stats = stats(public_zero_to_full)
        public_wait_stats = stats(public_waits)
        public_ahead_stats = stats(public_ahead)
        own_ahead_stats = stats(own_ahead)
        result.update(
            MODEL="M025",
            ORDER_QUANTITY_USDC=_s(self.order_quantity),
            GROWTH_EXPANSION_ENABLED=False,
            NEW_QUEUE_CELLS_FUNDED_BY_PROFIT=0,
            GROWTH_CELLS_FUNDED=0,
            TOTAL_ENTRY_ORDERS_SUBMITTED=len(entry_orders),
            TOTAL_RETURN_ORDERS_SUBMITTED=len(return_orders),
            TOTAL_ORDERS_FULLY_FILLED=len(full_orders),
            ENTRY_COMPLETION_COUNT=len(full_entries),
            RETURN_COMPLETION_COUNT=len(full_returns),
            ORDER_FULL_FILL_RATE=_s(D(len(full_orders)) / D(len(orders)) if orders else ZERO),
            TOTAL_FILL_EVENTS=len(fills),
            TOTAL_FILL_FRAGMENTS=len(fills),
            TOTAL_FILLED_QTY_USDC=_s(filled_qty),
            TWO_WAY_TRADED_USDC=_s(filled_qty),
            TWO_WAY_TRADED_USDC_PER_HOUR=_s(filled_qty / D(3)),
            TWO_WAY_NOTIONAL_USDT=_s(two_way_notional),
            TWO_WAY_NOTIONAL_USDT_PER_HOUR=_s(two_way_notional / D(3)),
            PARTIAL_FILL_EVENTS=partial_events,
            PARTIAL_FILL_EVENT_RATE=_s(D(partial_events) / D(len(fills)) if fills else ZERO),
            FULL_COMPLETION_EVENTS=len(full_orders),
            FULL_FILL_COMPLETION_RATE=_s(D(len(full_orders)) / D(len(orders)) if orders else ZERO),
            PARTIALLY_FILLED_ORDERS=partially_filled,
            PARTIAL_FILL_RATE=_s(D(partially_filled) / D(len(orders)) if orders else ZERO),
            FULL_FILL_RATE=_s(D(len(full_orders)) / D(len(orders)) if orders else ZERO),
            FULL_ENTRY_ORDERS=len(full_entries),
            FULL_RETURN_ORDERS=len(full_returns),
            RESIDUAL_PARTIAL_ORDER_COUNT=len(residual_partial_orders),
            RESIDUAL_PARTIAL_QTY_USDC=_s(
                sum((order.remaining for order in residual_partial_orders), ZERO)
            ),
            CYCLE_CLOSED_NOTIONAL_USDT=_s(cycle_notional),
            CYCLE_CLOSED_NOTIONAL_PER_HOUR_USDT=_s(completed_notional_per_hour),
            COMPLETED_ROUNDTRIP_USDC=_s(completed_roundtrip),
            COMPLETED_ROUNDTRIP_USDC_PER_HOUR=_s(completed_roundtrip / D(3)),
            CYCLES_PER_HOUR_PER_1000_INITIAL_USDT=_s(
                cycles_per_hour * D(1000) / initial_equity if initial_equity > ZERO else ZERO
            ),
            COMPLETED_NOTIONAL_PER_HOUR_PER_1000_INITIAL_USDT=_s(
                completed_notional_per_hour * D(1000) / initial_equity
                if initial_equity > ZERO
                else ZERO
            ),
            ROUNDTRIP_USDC_PER_HOUR_PER_1000_INITIAL_USDT=_s(
                completed_roundtrip / D(3) * D(1000) / initial_equity
                if initial_equity > ZERO
                else ZERO
            ),
            AVG_TIME_TO_FIRST_FILL_US=(
                sum(first_times) / len(first_times) if first_times else None
            ),
            MEDIAN_TIME_TO_FIRST_FILL_US=(median(first_times) if first_times else None),
            AVG_TIME_FIRST_TO_FULL_US=(
                sum(first_to_full) / len(first_to_full) if first_to_full else None
            ),
            MEDIAN_TIME_FIRST_TO_FULL_US=(median(first_to_full) if first_to_full else None),
            AVG_TIME_TO_FULL_FILL_US=(
                sum(complete_times) / len(complete_times) if complete_times else None
            ),
            MEDIAN_TIME_TO_FULL_FILL_US=(median(complete_times) if complete_times else None),
            P95_TIME_TO_FULL_FILL_US=full_fill_stats["p95"],
            MAX_TIME_TO_FULL_FILL_US=full_fill_stats["max"],
            AVG_ENTRY_TO_RETURN_US=(
                sum(entry_to_return) / len(entry_to_return) if entry_to_return else None
            ),
            MEDIAN_ENTRY_TO_RETURN_US=(median(entry_to_return) if entry_to_return else None),
            TIME_TO_FIRST_FILL_US=time_to_first_stats,
            TIME_FIRST_TO_FULL_FILL_US=first_to_full_stats,
            TIME_TO_FULL_FILL_US=full_fill_stats,
            TIME_PUBLIC_QUEUE_ZERO_TO_FIRST_OWN_FILL_US=public_to_first_stats,
            TIME_PUBLIC_QUEUE_ZERO_TO_FULL_OWN_FILL_US=public_to_full_stats,
            TIME_WAITING_PUBLIC_FIFO_US=public_wait_stats,
            CENSORED_OPEN_ORDER_COUNT=sum(
                order.status in {"PENDING", "ACTIVE", "CANCEL_PENDING"} for order in orders
            ),
            ORDERS_OPEN_AT_CUTOFF=sum(
                order.status in {"PENDING", "ACTIVE", "CANCEL_PENDING"} for order in orders
            ),
            UNFILLED_ACTIVE_QTY_AT_CUTOFF_USDC=_s(
                sum(
                    (
                        order.remaining
                        for order in orders
                        if order.status in {"PENDING", "ACTIVE", "CANCEL_PENDING"}
                    ),
                    ZERO,
                )
            ),
            QUEUE_ZERO_REACHED_COUNT=len(public_zero_by_order),
            QUEUE_ZERO_THEN_FILLED_COUNT=len(
                set(public_zero_by_order).intersection(first_fill_by_order)
            ),
            QUEUE_ZERO_CENSORED_WITHOUT_FILL_COUNT=len(
                set(public_zero_by_order).difference(first_fill_by_order)
            ),
            QUEUE_ZERO_NOT_OBSERVED_BEFORE_FIRST_FILL_COUNT=len(
                set(first_fill_by_order).difference(public_zero_by_order)
            ),
            QUEUE_ZERO_TO_FIRST_FILL_DENOMINATOR=len(
                set(public_zero_by_order).intersection(first_fill_by_order)
            ),
            QUEUE_ZERO_ACTIVATED_ORDER_DENOMINATOR=len(activated),
            QUEUE_ZERO_MISSING_REASON=(
                "STRICT_TRADE_THROUGH_OR_CENSORING_BEFORE_OBSERVED_PUBLIC_ZERO"
            ),
            QUEUE_ZERO_TIME_DEFINITION=(
                "RECONSTRUCTED_PUBLIC_SEGMENTS_RELEVANT_AT_ORDER_ACTIVATION_REACH_ZERO"
            ),
            MEDIAN_TIME_TO_QUEUE_ZERO_US=(median(public_waits) if public_waits else None),
            AVG_QUEUE_AHEAD_AT_ACTIVATION_USDC=_s(
                sum(
                    (order.queue_ahead_at_activation for order in activated),
                    ZERO,
                )
                / D(len(activated))
                if activated
                else ZERO
            ),
            PUBLIC_QUEUE_AHEAD_AT_ACTIVATION_USDC=public_ahead_stats,
            OWN_QUANTITY_AHEAD_AT_ACTIVATION_USDC=own_ahead_stats,
            QUEUE_CONSUMPTION_EVENTS=len(public_consumption) + len(fills),
            PUBLIC_QUEUE_QUANTITY_CONSUMED_USDC=_s(
                sum((_dec(row["quantity"]) for row in public_consumption), ZERO)
            ),
            OWN_QUEUE_QUANTITY_CONSUMED_USDC=_s(filled_qty),
            OPEN_INVENTORY_QTY_USDC=_s(marked_qty),
            OPEN_INVENTORY_USDC=_s(marked_qty),
            OPEN_INVENTORY_COST_BASIS_USDT=_s(marked_cost),
            OPEN_INVENTORY_COST_USDT=_s(marked_cost),
            PARTIAL_ENTRY_RESIDUAL_USDC=_s(
                sum((order.filled for order in partial_entry_orders), ZERO)
            ),
            PARTIAL_RETURN_RESIDUAL_USDC=_s(
                sum((order.remaining for order in partial_return_orders), ZERO)
            ),
            CAPITAL_LOCKED_IN_PARTIALS_USDT=_s(
                sum((order.filled * order.price for order in partial_entry_orders), ZERO)
                + sum((order.remaining * order.price for order in partial_return_orders), ZERO)
            ),
            CAPITAL_LOCKED_IN_OPEN_LOTS_USDT=_s(marked_cost),
            RETURN_ON_INITIAL_EQUITY=_s(
                (self.initial_mark + _marked_unrealized + self.realized_disposal_pnl)
                / self.initial_mark
                - D(1)
                if self.initial_mark > ZERO
                else ZERO
            ),
            REALIZED_PNL_PER_HOUR=_s(self.realized_pnl / D(3)),
            REALIZED_DISPOSAL_PNL_PER_HOUR=_s(self.realized_disposal_pnl / D(3)),
            COMPLETED_CYCLE_PNL_PER_HOUR=_s(self.realized_pnl / D(3)),
            PNL_PER_1000_INITIAL_USDT=_s(
                self.realized_pnl * D(1000) / initial_equity if initial_equity > ZERO else ZERO
            ),
            PNL_PER_HOUR_PER_1000_INITIAL_USDT=_s(
                self.realized_pnl / D(3) * D(1000) / initial_equity
                if initial_equity > ZERO
                else ZERO
            ),
            ORDER_NOTIONAL_USDT_MIN=_s(min(order_notionals) if order_notionals else ZERO),
            ORDER_NOTIONAL_USDT_MEDIAN=_s(median(order_notionals) if order_notionals else ZERO),
            ORDER_NOTIONAL_USDT_MAX=_s(max(order_notionals) if order_notionals else ZERO),
            CANCELED_PARTIAL_LOCKED_LOTS=sum(
                lot.stage in {"SUBSTEP_INVENTORY_LOCKED", "SUBSTEP_RETURN_DEBT_LOCKED"}
                for lot in self.lots
            ),
            PARTIAL_LOCK_POLICY="PARTIAL_ENTRY_CANCELED_LOCKED_NO_RETURN_NO_CYCLE",
        )
        return result

    def _state(self) -> dict[str, Any]:
        state = super()._state()
        state["config"] = {
            **state["config"],
            "model_id": "M025",
            "order_quantity_usdc": _s(self.order_quantity),
            "growth_expansion_enabled": False,
        }
        return state

    def checkpoint(self) -> dict[str, Any]:
        state = self._state()
        return {
            "schema": "M025_ORDER_SIZE_CAPACITY_V1",
            "state": state,
            "sha256": canonical_hash(state),
        }

    def restore(self, checkpoint: dict[str, Any]) -> None:
        if checkpoint.get("schema") != "M025_ORDER_SIZE_CAPACITY_V1":
            raise ValueError("INVALID_M025_CHECKPOINT")
        state = checkpoint.get("state")
        if not isinstance(state, dict) or checkpoint.get("sha256") != canonical_hash(state):
            raise ValueError("M025_CHECKPOINT_HASH_MISMATCH")
        config = state.get("config", {})
        if (
            config.get("model_id") != "M025"
            or _dec(config.get("order_quantity_usdc", "0")) != self.order_quantity
            or config.get("growth_expansion_enabled") is not False
        ):
            raise ValueError("M025_CHECKPOINT_SCENARIO_MISMATCH")
        parent = {
            "schema": "M024_TRIANGULAR_PRE_AGED_QUEUE_V1",
            "state": state,
            "sha256": checkpoint["sha256"],
        }
        super().restore(parent)
        # M024's historical restore path predates metrics that subtract the
        # activation queue amount.  Keep M024 immutable and repair the M025
        # in-memory representation at its boundary.
        for order in self.orders:
            order.queue_ahead_at_activation = _dec(order.queue_ahead_at_activation)

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint: dict[str, Any],
        *,
        start_us: int,
        end_us: int,
        order_quantity: D | str,
    ) -> OrderSizeCapacityProbe:
        value = cls(start_us=start_us, end_us=end_us, order_quantity=order_quantity)
        value.restore(checkpoint)
        return value


__all__ = ["AUTHORIZED_QUANTITIES", "OrderSizeCapacityProbe"]
