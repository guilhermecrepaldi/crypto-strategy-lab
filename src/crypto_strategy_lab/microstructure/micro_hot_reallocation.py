"""M027 controlled FAR14/FAR15 to two-column micro-hot reallocation.

Both scenarios reuse the M026 execution kernel.  The control keeps M026's
coarse geometry; the treatment replaces exactly two one-slot FAR lines per
side with two one-slot orders at a legal half-coarse-tick price.
"""

from __future__ import annotations

from statistics import median
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.dynamic_hotline_321 import (
    INITIAL_ARCHITECTURAL_SLOT_UNITS,
    INITIAL_OPERATIONAL_SLOT_UNITS,
    INITIAL_SLOT_BASE,
    MOBILITY_SLOT_UNITS_PER_SIDE,
    OPEN_STATES,
    DynamicHotline321Probe,
    quantized_quantity,
    zone_for_rank,
)
from crypto_strategy_lab.microstructure.triangular_pre_aged_queue import (
    ZERO,
    QueueOrder,
    TriangularPreAgedQueueProbe,
    _dec,
    _s,
)
from crypto_strategy_lab.microstructure.zonal_ping_pong import D

FINE_TICK_SIZE = D("0.00001")
COARSE_GRID_SPACING = D("0.0001")
MICRO_OFFSET = D("0.00005")
SCENARIOS = {"CONTROL", "TREATMENT"}
M027_SHAPES = {
    "MICRO": (2, 1),
    "HOT": (3, 3),
    "MID": (2, 2),
    "FAR": (1, 1),
}


def validate_micro_offset_for_tick(observed_tick: D | str) -> None:
    tick = _dec(observed_tick)
    if tick <= ZERO or MICRO_OFFSET % tick != ZERO:
        raise ValueError("BLOCKED_FINE_TICK_DATASET_NOT_VALIDATED")


class MicroHotReallocationProbe(DynamicHotline321Probe):
    """One source-bound A/B kernel with scenario-dependent geometry only."""

    normalized_label = (
        "M027 NORMALIZED MICRO-HOT REALLOCATION MECHANICS. MIN_NOTIONAL IS "
        "VIRTUALIZED; TRUE L3 RANK AND ENDOGENOUS IMPACT ARE UNKNOWN."
    )

    def __init__(self, *, scenario: str, **kwargs: Any) -> None:
        if scenario not in SCENARIOS:
            raise ValueError("M027_INVALID_SCENARIO")
        self.scenario = scenario
        self.treatment = scenario == "TREATMENT"
        self._distance_order_time_us: dict[str, int] = {}
        self._micro_limiter_time_us = {
            "PUBLIC_FIFO_WAIT": 0,
            "OWN_FIFO_WAIT": 0,
            "PRICE_RECOVERY_WAIT": 0,
        }
        self._micro_unique_trade_ids: set[str] = set()
        self._restoring_m027 = False
        super().__init__(**kwargs)
        self._zone_order_time_us.setdefault("MICRO", 0)
        self._zone_capital_time.setdefault("MICRO", ZERO)

    def _shape(self, zone: str) -> tuple[int, int]:
        if zone == "MICRO" and not self.treatment:
            raise ValueError("M027_CONTROL_MICRO_FORBIDDEN")
        return M027_SHAPES[zone]

    def _geometry(self, side: str) -> list[tuple[D, str, int, int, int]]:
        if self.hotline is None:
            return []
        sign = D(-1) if side == "BUY" else D(1)
        rows: list[tuple[D, str, int, int, int]] = []
        if self.treatment:
            rows.append((self.hotline + sign * MICRO_OFFSET, "MICRO", 0, 2, 1))
            ranks = range(1, 14)
        else:
            ranks = range(1, 16)
        for rank in ranks:
            zone = zone_for_rank(rank)
            assert zone is not None
            columns, slots = self._shape(zone)
            rows.append(
                (self.hotline + sign * D(rank) * COARSE_GRID_SPACING, zone, rank, columns, slots)
            )
        return rows

    def _target_prices(self, side: str) -> list[D]:
        return [row[0] for row in self._geometry(side)]

    def _zone_rank(self, side: str, price: D) -> int | None:
        if self.hotline is None:
            return None
        distance = self.hotline - price if side == "BUY" else price - self.hotline
        if distance <= ZERO or distance % COARSE_GRID_SPACING != ZERO:
            return None
        return int(distance / COARSE_GRID_SPACING)

    def _zone_for_line(self, side: str, price: D) -> str | None:
        if self.hotline is None:
            return None
        distance = self.hotline - price if side == "BUY" else price - self.hotline
        if self.treatment and distance == MICRO_OFFSET:
            return "MICRO"
        rank = self._zone_rank(side, price)
        if rank is None or (self.treatment and rank > 13):
            return None
        return zone_for_rank(rank)

    def submit_order(self, side: str, price: D | str, **kwargs: Any) -> QueueOrder:
        if _dec(price) % FINE_TICK_SIZE != ZERO:
            raise ValueError("M027_FINE_TICK_VIOLATION")
        return super().submit_order(side, price, **kwargs)

    def _submit_grid_cell(
        self,
        side: str,
        price: D,
        column: int,
        zone: str,
        now: int,
        *,
        promotion: bool,
    ) -> QueueOrder | None:
        cell_id = self._cell_id(side, price, column)
        key = (self.current_epoch_id, cell_id)
        if key in self._attempted_epoch_cells or self._cell_is_occupied(cell_id):
            return None
        self._attempted_epoch_cells.add(key)
        slots = self._shape(zone)[1]
        rank = self._zone_rank(side, price) or 0
        try:
            order = self.submit_order(
                side,
                price,
                time_us=now,
                role="ENTRY",
                column=column,
                level=rank,
                direction="BUY_FIRST" if side == "BUY" else "SELL_FIRST",
                cell_id=cell_id,
                asset_basis=self._initial_sell_basis if side == "SELL" else ZERO,
                slot_count=slots,
                slot_epoch=self.current_epoch_id,
                zone=zone,
                line_price=price,
                allow_mobility=promotion,
                capital_source="MOBILITY" if promotion else "OWN",
            )
        except ValueError as exc:
            reason = str(exc)
            self._promotion_counts["BLOCKED_ASSET" if "USDC" in reason else "BLOCKED_CAPITAL"] += 1
            self._funding_blocked_cells.add(cell_id)
            if promotion:
                self._mobility_blocked_cells.add(cell_id)
                reserve = self.buy_mobility_reserve if side == "BUY" else self.sell_mobility_reserve
                if reserve == ZERO:
                    self._reserve_exhaustions += 1
                    self._record("MOBILITY_RESERVE_EXHAUSTED", now, side=side)
            self._record(
                "UNDERFUNDED_HOTLINE_PROMOTION",
                now,
                side=side,
                price=_s(price),
                column=column,
                zone=zone,
                reason=reason,
                missing_target_slot_units=slots,
            )
            return None
        if promotion:
            locked = self._order_reserve_locked[order.order_id]
            self._promotion_counts["FULLY_FUNDED"] += 1
            self._promotion_counts["NEW_COLUMNS"] += 1
            self._promotion_counts["SLOT_UNITS_ADDED"] += D(slots)
            if locked["USDT"] > ZERO or locked["USDC"] > ZERO:
                self._record(
                    "MOBILITY_RESERVE_USED",
                    now,
                    order_id=order.order_id,
                    usdt=_s(locked["USDT"]),
                    usdc=_s(locked["USDC"]),
                )
        self._funding_blocked_cells.discard(cell_id)
        self._mobility_blocked_cells.discard(cell_id)
        return order

    def _reconcile_grid(
        self, now: int, *, old_zones: dict[tuple[str, D], str | None] | None = None
    ) -> None:
        if not self._initialized or self.hotline is None:
            return
        desired = {
            (side, price): zone
            for side in ("BUY", "SELL")
            for price, zone, _rank, _columns, _slots in self._geometry(side)
        }
        for order in list(self.active_orders):
            if order.role != "ENTRY":
                continue
            meta = self._order_meta[order.order_id]
            line_key = (order.side, _dec(meta["line_price"]))
            zone = desired.get(line_key)
            if zone is None:
                self._mark_drain_only(order, now)
                if order.filled == ZERO and order.status != "CANCEL_PENDING":
                    self.cancel(order.order_id, time_us=now)
                    self._record("OUTSIDE_GRID_CANCEL_REQUESTED", now, order_id=order.order_id)
                continue
            target_columns = self._shape(zone)[0]
            if order.column > target_columns:
                self._mark_drain_only(order, now)
            elif meta["drain_only"]:
                meta["drain_only"] = False
                self._drain_only_orders.discard(order.order_id)
                self._record(
                    "DRAIN_ONLY_REVERSED_BY_REPROMOTION", now, order_id=order.order_id, zone=zone
                )
            elif old_zones is not None:
                self._promotion_counts["AGED_PRESERVED"] += 1
                self._record(
                    "AGED_ORDER_PRESERVED",
                    now,
                    order_id=order.order_id,
                    old_zone=old_zones.get(line_key),
                    new_zone=zone,
                )
        for (side, price), zone in desired.items():
            old_zone = old_zones.get((side, price)) if old_zones is not None else zone
            if old_zone == "FAR" and zone == "MID":
                self._promotion_counts["FAR_TO_MID"] += 1
            elif old_zone == "MID" and zone == "HOT":
                self._promotion_counts["MID_TO_HOT"] += 1
            elif old_zone not in {zone, None}:
                self._promotion_counts["DIRECT_MULTI_LEVEL"] += 1
            promotion = old_zones is not None and old_zone != zone
            for column in range(1, self._shape(zone)[0] + 1):
                self._submit_grid_cell(side, price, column, zone, now, promotion=promotion)

    def initialize_triangle(self, time_us: int) -> None:
        if self._initialized:
            return
        if self._last_book is None:
            raise ValueError("M027_BOOK_REQUIRED_FOR_INITIALIZATION")
        bid, ask = self._last_book["bids"][0][0], self._last_book["asks"][0][0]
        if bid % FINE_TICK_SIZE != ZERO or ask % FINE_TICK_SIZE != ZERO:
            raise ValueError("M027_FINE_TICK_BOOK_REQUIRED")
        self.hotline = self.initial_hotline = ask
        self._initial_sell_basis = bid
        self.slot_base = INITIAL_SLOT_BASE
        self.buy_mobility_target = MOBILITY_SLOT_UNITS_PER_SIDE * self.slot_base
        self.sell_mobility_target = MOBILITY_SLOT_UNITS_PER_SIDE
        rows: dict[str, list[tuple[D, int, int, str, int]]] = {"BUY": [], "SELL": []}
        for side in rows:
            for price, zone, rank, columns, slots in self._geometry(side):
                for column in range(1, columns + 1):
                    rows[side].append((price, column, slots, zone, rank))
        operational_usdt = sum(
            (
                price * quantized_quantity(self.slot_base * D(slots), price)
                for price, _column, slots, _zone, _rank in rows["BUY"]
            ),
            ZERO,
        )
        operational_usdc = sum(
            (
                quantized_quantity(self.slot_base * D(slots), price)
                for price, _column, slots, _zone, _rank in rows["SELL"]
            ),
            ZERO,
        )
        self.initial_usdt = operational_usdt + self.buy_mobility_target
        self.initial_usdc = operational_usdc + self.sell_mobility_target
        self.initial_mark = self.initial_usdt + self.initial_usdc * bid
        self.initial_slot_bank = self.initial_mark
        self.cash, self.free_usdc = self.initial_usdt, self.initial_usdc
        self._usdc_cost_basis_total = self.initial_usdc * bid
        self.buy_mobility_reserve, self.sell_mobility_reserve = (
            self.buy_mobility_target,
            self.sell_mobility_target,
        )
        self._min_buy_mobility_reserve = self.buy_mobility_reserve
        self._min_sell_mobility_reserve = self.sell_mobility_reserve
        self._add_free_usdc_layer(
            operational_usdc, bid, mobility=False, source="INITIAL_OPERATIONAL_USDC"
        )
        self._add_free_usdc_layer(
            self.sell_mobility_target, bid, mobility=True, source="INITIAL_SELL_MOBILITY"
        )
        self._sync_usdc_quantization_dust()
        self._initialized = True
        self._append_epoch(time_us, direction="INITIAL")
        for side in ("BUY", "SELL"):
            for price, column, slots, zone, rank in rows[side]:
                self.submit_order(
                    side,
                    price,
                    time_us=time_us,
                    column=column,
                    level=rank,
                    direction="BUY_FIRST" if side == "BUY" else "SELL_FIRST",
                    cell_id=self._cell_id(side, price, column),
                    asset_basis=bid if side == "SELL" else ZERO,
                    slot_count=slots,
                    slot_epoch=self.current_epoch_id,
                    zone=zone,
                    line_price=price,
                )
        self._initial_open_entry_orders = self.open_order_count
        if self._initial_open_entry_orders != 60:
            raise ValueError("M027_INITIAL_ORDER_GEOMETRY_DRIFT")
        if sum(self._order_meta[o.order_id]["slot_count"] for o in self.orders) != 140:
            raise ValueError("M027_OPERATIONAL_SLOT_GEOMETRY_DRIFT")
        self._record(
            "M027_GRID_INITIALIZED",
            time_us,
            scenario=self.scenario,
            hotline=_s(self.hotline),
            operational_slot_units=_s(INITIAL_OPERATIONAL_SLOT_UNITS),
            mobility_slot_units="16",
            architectural_slot_units=_s(INITIAL_ARCHITECTURAL_SLOT_UNITS),
            initial_usdt=_s(self.initial_usdt),
            initial_usdc=_s(self.initial_usdc),
            initial_mark=_s(self.initial_mark),
        )

    def _recycle_after_cycle(self, order: QueueOrder, now: int) -> None:
        source = next((row for row in self.orders if row.order_id == order.source_order_id), None)
        if source is None:
            return
        meta = self._order_meta[source.order_id]
        line_price = _dec(meta["line_price"])
        zone = self._zone_for_line(source.side, line_price)
        columns = self._shape(zone)[0] if zone else 0
        cell_id = source.cell_id or ""
        if meta["drain_only"] or source.column > columns:
            self._retired_cells.add(cell_id)
            self._retired_after_drain += 1
            lot = next((row for row in self.lots if row.lot_id in order.lot_ids), None)
            if lot is not None and lot.stage == "RESTORED":
                lot.stage = "RECYCLED"
            self._record(
                "RETIRED_AFTER_DRAIN", now, source_order_id=source.order_id, cell_id=cell_id
            )
            return
        slots = self._shape(zone)[1]
        level = self._zone_rank(source.side, line_price) or source.level
        try:
            recycled = self.submit_order(
                source.side,
                line_price,
                time_us=now,
                role="ENTRY",
                column=source.column,
                level=level,
                direction=source.direction,
                cell_id=cell_id,
                slot_count=slots,
                slot_epoch=self.current_epoch_id,
                zone=zone,
                line_price=line_price,
                allow_mobility=True,
                capital_source="RECYCLE",
            )
            lot = next((row for row in self.lots if row.lot_id in order.lot_ids), None)
            if lot is not None and lot.stage == "RESTORED":
                lot.stage = "RECYCLED"
            self._record(
                "PRINCIPAL_RECYCLED",
                now,
                order_id=recycled.order_id,
                source_order_id=order.order_id,
                old_slot_count=meta["slot_count"],
                new_slot_count=slots,
                line_price=_s(line_price),
            )
        except ValueError as exc:
            self._retired_cells.add(cell_id)
            self._funding_blocked_cells.add(cell_id)
            self._record(
                "PRINCIPAL_RECYCLE_DEFERRED", now, source_order_id=source.order_id, reason=str(exc)
            )

    @staticmethod
    def _distance_label(meta: dict[str, Any]) -> str:
        if meta["origin_zone"] == "MICRO":
            return "MICRO"
        rank = int(meta.get("origin_level", meta.get("level", 0)) or 0)
        if rank == 0:
            rank = int(meta.get("submitted_level", 0) or 0)
        if 1 <= rank <= 5:
            return f"RANK{rank}"
        if 6 <= rank <= 10:
            return "MID"
        if 11 <= rank <= 15:
            return f"FAR{rank}"
        return meta["origin_zone"]

    def _order_distance_label(self, order: QueueOrder) -> str:
        meta = self._order_meta[order.order_id]
        if meta["origin_zone"] == "MICRO":
            return "MICRO"
        rank = order.level
        if 1 <= rank <= 5:
            return f"RANK{rank}"
        if 6 <= rank <= 10:
            return "MID"
        if 11 <= rank <= 15:
            return f"FAR{rank}"
        return str(meta["origin_zone"])

    def _observe(self, now: int) -> None:
        elapsed = max(0, now - self._last_observation_us)
        if elapsed > 0 and self._initialized:
            for order in self.active_orders:
                label = self._order_distance_label(order)
                self._distance_order_time_us[label] = (
                    self._distance_order_time_us.get(label, 0) + elapsed
                )
                if self.treatment and self._order_meta[order.order_id]["origin_zone"] == "MICRO":
                    if order.status != "ACTIVE":
                        continue
                    public, own = self._queue_components(order)
                    if public > ZERO:
                        category = "PUBLIC_FIFO_WAIT"
                    elif own > ZERO:
                        category = "OWN_FIFO_WAIT"
                    elif order.role == "RETURN":
                        category = "PRICE_RECOVERY_WAIT"
                    else:
                        category = None
                    if category is not None:
                        self._micro_limiter_time_us[category] += elapsed
        super()._observe(now)

    def receive_trade(self, trade: Any, *, capture_time_us: int | None = None) -> D:
        if self.treatment and self.hotline is not None:
            price = _dec(trade.price)
            micro_only = (
                trade.buyer_maker
                and self.hotline - COARSE_GRID_SPACING < price <= self.hotline - MICRO_OFFSET
            ) or (
                not trade.buyer_maker
                and self.hotline + MICRO_OFFSET <= price < self.hotline + COARSE_GRID_SPACING
            )
            if micro_only:
                trade_id = str(trade.trade_id)
                if trade_id not in self._micro_unique_trade_ids:
                    self._micro_unique_trade_ids.add(trade_id)
                    self._record(
                        "MICRO_UNIQUE_PRICE_TOUCH",
                        int(capture_time_us if capture_time_us is not None else trade.time_us),
                        trade_id=trade_id,
                        price=_s(price),
                        hotline=_s(self.hotline),
                    )
        return super().receive_trade(trade, capture_time_us=capture_time_us)

    @staticmethod
    def _percentile_value(values: list[int], quantile: float) -> int | None:
        if not values:
            return None
        ordered = sorted(values)
        return ordered[int((len(ordered) - 1) * quantile)]

    def metrics(self) -> dict[str, Any]:
        result = super().metrics()
        labels = [
            "MICRO",
            "RANK1",
            "RANK2",
            "RANK3",
            "RANK4",
            "RANK5",
            "MID",
            "FAR11",
            "FAR12",
            "FAR13",
            "FAR14",
            "FAR15",
        ]
        order_by_id = {row.order_id: row for row in self.orders}
        cycle_labels: dict[int, str] = {}
        for cycle in self._cycle_rows:
            source = order_by_id[int(cycle["entry_order_id"])]
            cycle_labels[int(cycle["cycle_id"])] = self._order_distance_label(source)
        fill_rows = [row for row in self.audit if row["event"] == "FILL"]
        activation = {row.order_id: row.activation_evaluated_us for row in self.orders}
        final_fill_time: dict[int, int] = {}
        for row in fill_rows:
            final_fill_time[int(row["order_id"])] = int(row["time_us"])
        distance_table = []
        for label in labels:
            source_ids = {o.order_id for o in self.orders if self._order_distance_label(o) == label}
            cycles = [
                row for row in self._cycle_rows if cycle_labels[int(row["cycle_id"])] == label
            ]
            waits = [
                final_fill_time[o.order_id] - int(activation[o.order_id])
                for o in self.orders
                if o.order_id in source_ids
                and o.status == "FILLED"
                and activation[o.order_id] is not None
                and o.order_id in final_fill_time
            ]
            distance_table.append(
                {
                    "DISTANCE": label,
                    "PHYSICAL_CYCLES": len(cycles),
                    "SLOT_CYCLES": sum(int(row["slot_equivalent_weight"]) for row in cycles),
                    "FILLS": sum(int(row["order_id"]) in source_ids for row in fill_rows),
                    "ORDER_HOURS": _s(
                        D(self._distance_order_time_us.get(label, 0)) / D("3600000000")
                    ),
                    "MEDIAN_FILL_WAIT_US": median(waits) if waits else None,
                }
            )
        by_label = {row["DISTANCE"]: row for row in distance_table}
        micro_orders = [
            o for o in self.orders if self._order_meta[o.order_id]["origin_zone"] == "MICRO"
        ]
        micro_cycles = [
            row for row in self._cycle_rows if cycle_labels[int(row["cycle_id"])] == "MICRO"
        ]
        micro_waits = [
            final_fill_time[o.order_id] - int(o.activation_evaluated_us)
            for o in micro_orders
            if o.status == "FILLED"
            and o.activation_evaluated_us is not None
            and o.order_id in final_fill_time
        ]
        entry_fill_sources: dict[int, set[str]] = {}
        for row in fill_rows:
            entry_fill_sources.setdefault(int(row["order_id"]), set()).add(str(row["source_id"]))
        unique_micro_cycles = sum(
            bool(
                entry_fill_sources.get(int(row["entry_order_id"]), set())
                & self._micro_unique_trade_ids
            )
            for row in micro_cycles
        )
        result.update(
            {
                "MODEL": "M027",
                "SCENARIO": self.scenario,
                "VALIDATED_TICK_SIZE": _s(FINE_TICK_SIZE),
                "COARSE_GRID_SPACING": _s(COARSE_GRID_SPACING),
                "MICRO_OFFSET": _s(MICRO_OFFSET),
                "MICRO_HOT_PHYSICAL_CYCLES": len(micro_cycles),
                "MICRO_HOT_SLOT_CYCLES": sum(
                    int(row["slot_equivalent_weight"]) for row in micro_cycles
                ),
                "MICRO_C1_CYCLES": sum(int(row["column"]) == 1 for row in micro_cycles),
                "MICRO_C2_CYCLES": sum(int(row["column"]) == 2 for row in micro_cycles),
                "MICRO_ORDERS_CREATED": len(micro_orders),
                "MICRO_FULL_FILLS": sum(o.status == "FILLED" for o in micro_orders),
                "MICRO_PARTIAL_FILLS": sum(
                    o.filled > ZERO and o.status != "FILLED" for o in micro_orders
                ),
                "MICRO_OPEN_AT_CUTOFF": sum(o.status in OPEN_STATES for o in micro_orders),
                "MICRO_MEDIAN_ACTIVATION_TO_FILL_US": median(micro_waits) if micro_waits else None,
                "MICRO_P95_ACTIVATION_TO_FILL_US": self._percentile_value(micro_waits, 0.95),
                "MICRO_PUBLIC_FIFO_WAIT_US": self._micro_limiter_time_us["PUBLIC_FIFO_WAIT"],
                "MICRO_OWN_FIFO_WAIT_US": self._micro_limiter_time_us["OWN_FIFO_WAIT"],
                "MICRO_PRICE_RECOVERY_WAIT_US": self._micro_limiter_time_us["PRICE_RECOVERY_WAIT"],
                "MICRO_UNIQUE_PRICE_TOUCHES": len(self._micro_unique_trade_ids),
                "MICRO_CYCLES_WITHOUT_CONTROL_EQUIVALENT_TOUCH": unique_micro_cycles,
                "HOT_RANK1_CYCLES": by_label["RANK1"]["PHYSICAL_CYCLES"],
                "FAR14_CYCLES": by_label["FAR14"]["PHYSICAL_CYCLES"],
                "FAR15_CYCLES": by_label["FAR15"]["PHYSICAL_CYCLES"],
                "FAR14_15_CONTROL_PRODUCTIVITY": {
                    "PHYSICAL_CYCLES": by_label["FAR14"]["PHYSICAL_CYCLES"]
                    + by_label["FAR15"]["PHYSICAL_CYCLES"],
                    "FILLS": by_label["FAR14"]["FILLS"] + by_label["FAR15"]["FILLS"],
                    "ORDER_HOURS": _s(
                        D(
                            self._distance_order_time_us.get("FAR14", 0)
                            + self._distance_order_time_us.get("FAR15", 0)
                        )
                        / D("3600000000")
                    ),
                },
                "DISTANCE_TABLE": distance_table,
            }
        )
        return result

    def validate_invariants(self) -> None:
        if self._restoring_m027:
            return
        TriangularPreAgedQueueProbe.validate_invariants(self)
        if not self._initialized:
            return
        if self.hotline is None or self.hotline % FINE_TICK_SIZE != ZERO:
            raise ValueError("M027_HOTLINE_FINE_TICK_DRIFT")
        if self._layer_quantity() + self._unallocated_usdc_quantization_dust != self.free_usdc:
            raise ValueError("M027_FREE_USDC_LAYER_DRIFT")
        if self._layer_quantity(mobility=True) != self.sell_mobility_reserve:
            raise ValueError("M027_SELL_MOBILITY_RESERVE_DRIFT")
        if self.buy_mobility_reserve > self.cash - self._locked_sell_proceeds():
            raise ValueError("M027_BUY_MOBILITY_RESERVE_DRIFT")
        if self._slot_cycles != sum(int(row["slot_equivalent_weight"]) for row in self._cycle_rows):
            raise ValueError("M027_SLOT_CYCLE_RECONCILIATION_DRIFT")
        if self._cycles != len(self._cycle_rows):
            raise ValueError("M027_PHYSICAL_CYCLE_RECONCILIATION_DRIFT")
        for order in self.orders:
            meta = self._order_meta.get(order.order_id)
            if meta is None or order.price % FINE_TICK_SIZE != ZERO:
                raise ValueError("M027_ORDER_METADATA_OR_TICK_DRIFT")
            if order.quantity % D(1) != ZERO:
                raise ValueError("M027_QUANTITY_STEP_DRIFT")
            if meta["origin_zone"] == "MICRO" and (
                not self.treatment or order.column not in {1, 2} or int(meta["slot_count"]) != 1
            ):
                raise ValueError("M027_MICRO_GEOMETRY_DRIFT")
            if order.role == "ENTRY" and _dec(meta["line_price"]) != order.price:
                raise ValueError("M027_ENTRY_PRICE_IDENTITY_DRIFT")
            layers = self._order_asset_cost_layers.get(order.order_id)
            if (
                layers is None
                or sum((row["quantity"] * row["basis"] for row in layers), ZERO)
                != self._order_asset_cost_remaining[order.order_id]
            ):
                raise ValueError("M027_ORDER_ASSET_COST_LAYER_DRIFT")
        if any(row["quantity"] * row["basis"] != row["cost"] for row in self._free_usdc_layers):
            raise ValueError("M027_FREE_USDC_COST_LAYER_DRIFT")
        if self._usdc_cost_basis_total < ZERO:
            raise ValueError("M027_NEGATIVE_USDC_COST_BASIS")

    def checkpoint(self) -> dict[str, Any]:
        parent = super().checkpoint()
        state = {
            "scenario": self.scenario,
            "parent": parent,
            "distance_order_time_us": self._distance_order_time_us,
            "micro_limiter_time_us": self._micro_limiter_time_us,
            "micro_unique_trade_ids": sorted(self._micro_unique_trade_ids),
        }
        return {
            "schema": "M027_MICRO_HOT_REALLOCATION_V1",
            "state": state,
            "sha256": canonical_hash(state),
        }

    def restore(self, checkpoint: dict[str, Any]) -> None:
        if checkpoint.get("schema") != "M027_MICRO_HOT_REALLOCATION_V1":
            raise ValueError("INVALID_M027_CHECKPOINT")
        state = checkpoint.get("state")
        if not isinstance(state, dict) or checkpoint.get("sha256") != canonical_hash(state):
            raise ValueError("M027_CHECKPOINT_HASH_MISMATCH")
        if state["scenario"] != self.scenario:
            raise ValueError("M027_CHECKPOINT_SCENARIO_MISMATCH")
        self._restoring_m027 = True
        try:
            super().restore(state["parent"])
            self._distance_order_time_us = {
                str(k): int(v) for k, v in state["distance_order_time_us"].items()
            }
            self._micro_limiter_time_us = {
                str(k): int(v) for k, v in state["micro_limiter_time_us"].items()
            }
            self._micro_unique_trade_ids = set(state["micro_unique_trade_ids"])
        finally:
            self._restoring_m027 = False
        self.validate_invariants()

    @classmethod
    def from_checkpoint(
        cls, checkpoint: dict[str, Any], *, start_us: int, end_us: int
    ) -> MicroHotReallocationProbe:
        scenario = checkpoint["state"]["scenario"]
        value = cls(scenario=scenario, start_us=start_us, end_us=end_us)
        value.restore(checkpoint)
        return value


M027MicroHotReallocation = MicroHotReallocationProbe

__all__ = [
    "COARSE_GRID_SPACING",
    "FINE_TICK_SIZE",
    "MICRO_OFFSET",
    "M027MicroHotReallocation",
    "MicroHotReallocationProbe",
    "validate_micro_offset_for_tick",
]
