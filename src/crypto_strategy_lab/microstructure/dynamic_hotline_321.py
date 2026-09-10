"""M026 dynamic 3/2/1 pre-aged hotline grid.

This is an offline normalized mechanics probe.  It reuses M024's segmented
public/own FIFO, but owns the moving-grid, variable-order, slot, reserve and
cycle-weight semantics introduced by M026.  It never converts assets, forces a
fill, realizes a negative exit, or changes an old order when the hotline moves.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP
from itertools import pairwise
from statistics import median
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.triangular_pre_aged_queue import (
    M021_TICK_SIZE,
    ZERO,
    Lot,
    QueueOrder,
    TriangularPreAgedQueueProbe,
    _dec,
    _s,
)
from crypto_strategy_lab.microstructure.zonal_ping_pong import D

INITIAL_SLOT_BASE = D("1")
LEVELS_PER_SIDE = 15
ZONE_LEVELS = 5
MOBILITY_SLOT_UNITS_PER_SIDE = D("8")
INITIAL_OPERATIONAL_SLOT_UNITS = D("140")
INITIAL_ARCHITECTURAL_SLOT_UNITS = D("156")
NORMALIZED_BALANCE_QUANTUM = D("0.00000001")
OPEN_STATES = {"PENDING", "ACTIVE", "CANCEL_PENDING"}

ZONE_SHAPES: dict[str, tuple[int, int]] = {
    "HOT": (3, 3),
    "MID": (2, 2),
    "FAR": (1, 1),
}


def zone_for_rank(rank: int) -> str | None:
    if 1 <= rank <= 5:
        return "HOT"
    if 6 <= rank <= 10:
        return "MID"
    if 11 <= rank <= 15:
        return "FAR"
    return None


def quantized_quantity(target_notional: D | str, price: D | str) -> D:
    """Nearest historical whole-USDC step, with an explicit one-unit floor."""
    target, value = _dec(target_notional), _dec(price)
    if target <= ZERO or value <= ZERO:
        raise ValueError("M026_NONPOSITIVE_TARGET_OR_PRICE")
    quantity = (target / value).to_integral_value(rounding=ROUND_HALF_UP)
    return max(D(1), quantity)


class DynamicHotline321Probe(TriangularPreAgedQueueProbe):
    """Fifteen-level moving hotline grid with immutable old-order ownership."""

    normalized_label = (
        "M026 NORMALIZED DYNAMIC HOTLINE 3/2/1 MECHANICS. MIN_NOTIONAL IS "
        "VIRTUALIZED; TRUE L3 RANK AND ENDOGENOUS IMPACT ARE UNKNOWN."
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.hotline: D | None = None
        self.initial_hotline: D | None = None
        self.hotline_epochs: list[dict[str, Any]] = []
        self._hotline_changes = 0
        self._up_moves = 0
        self._down_moves = 0
        self._move_directions: list[str] = []
        self._hotline_change_times: list[int] = []
        self._last_hotline_book_upper: int | None = None
        self.slot_base = INITIAL_SLOT_BASE
        self.initial_slot_bank = ZERO
        self._slot_cycles = 0
        self._slot_cycle_pnl = ZERO
        self._cycle_rows: list[dict[str, Any]] = []
        self._order_meta: dict[int, dict[str, Any]] = {}
        self._cell_latest_entry: dict[str, int] = {}
        self._retired_cells: set[str] = set()
        self._attempted_epoch_cells: set[tuple[int, str]] = set()
        self._funding_blocked_cells: set[str] = set()
        self._mobility_blocked_cells: set[str] = set()
        self._deferred_reason: dict[int, str] = {}
        self._free_usdc_layers: list[dict[str, Any]] = []
        # Quantity-weighted averages are useful for exit-price decisions, but
        # they cannot be the accounting authority: repeating Decimal division
        # can leave a non-zero residual.  Preserve exact aggregate cost both
        # globally and for every SELL reservation, and allocate the final
        # fragment its entire remaining cost.
        self._usdc_cost_basis_total = ZERO
        self._order_asset_cost_remaining: dict[int, D] = {}
        self._order_asset_cost_layers: dict[int, list[dict[str, Any]]] = {}
        self._unallocated_usdc_quantization_dust = ZERO
        self.buy_mobility_reserve = ZERO
        self.sell_mobility_reserve = ZERO
        self.buy_mobility_target = ZERO
        self.sell_mobility_target = ZERO
        self._initial_sell_basis = ZERO
        self._reserve_used_usdt = ZERO
        self._reserve_used_usdc = ZERO
        self._reserve_restored_usdt = ZERO
        self._reserve_restored_usdc = ZERO
        self._reserve_exhaustions = 0
        self._reserve_below_target_us = 0
        self._min_buy_mobility_reserve = ZERO
        self._min_sell_mobility_reserve = ZERO
        self._order_reserve_locked: dict[int, dict[str, D]] = {}
        self._promotion_counts = {
            "FAR_TO_MID": 0,
            "MID_TO_HOT": 0,
            "DIRECT_MULTI_LEVEL": 0,
            "AGED_PRESERVED": 0,
            "NEW_COLUMNS": 0,
            "SLOT_UNITS_ADDED": D(0),
            "FULLY_FUNDED": 0,
            "PARTIALLY_FUNDED": 0,
            "BLOCKED_CAPITAL": 0,
            "BLOCKED_ASSET": 0,
        }
        self._drain_only_orders: set[int] = set()
        self._retired_after_drain = 0
        self._initial_open_entry_orders = 0
        self._zone_order_time_us = {zone: 0 for zone in ZONE_SHAPES}
        self._zone_capital_time = {zone: ZERO for zone in ZONE_SHAPES}
        self._limiter_entity_time_us = {
            key: 0
            for key in (
                "PUBLIC_FIFO_WAIT",
                "OWN_FIFO_WAIT",
                "PRICE_RECOVERY_WAIT",
                "RETURN_PENDING_WAIT",
                "POST_ONLY_BLOCK",
                "CAPITAL_FUNDING_BLOCK",
                "MOBILITY_RESERVE_BLOCK",
                "OUTSIDE_ACTIVE_GRID",
                "PRODUCTIVE_ACTIVE_TIME",
            )
        }

    @property
    def current_epoch_id(self) -> int:
        return len(self.hotline_epochs)

    def _zone_rank(self, side: str, price: D) -> int | None:
        if self.hotline is None:
            return None
        distance = self.hotline - price if side == "BUY" else price - self.hotline
        if distance <= ZERO or distance % M021_TICK_SIZE != ZERO:
            return None
        return int(distance / M021_TICK_SIZE)

    def _zone_for_line(self, side: str, price: D) -> str | None:
        rank = self._zone_rank(side, price)
        return zone_for_rank(rank) if rank is not None else None

    def _target_prices(self, side: str) -> list[D]:
        if self.hotline is None:
            return []
        sign = D(-1) if side == "BUY" else D(1)
        return [self.hotline + sign * D(rank) * M021_TICK_SIZE for rank in range(1, 16)]

    def _add_free_usdc_layer(
        self,
        quantity: D,
        basis: D,
        *,
        mobility: bool,
        source: str,
        cost: D | None = None,
    ) -> None:
        if quantity <= ZERO:
            return
        exact_cost = quantity * basis if cost is None else cost
        for layer in self._free_usdc_layers:
            if layer["basis"] == basis and bool(layer["mobility"]) is mobility:
                layer["quantity"] += quantity
                layer["cost"] = layer["quantity"] * basis
                if layer["source"] != source:
                    layer["source"] = "MIXED"
                return
        self._free_usdc_layers.append(
            {
                "quantity": quantity,
                "basis": basis,
                "cost": exact_cost,
                "mobility": mobility,
                "source": source,
            }
        )

    def _layer_quantity(self, *, mobility: bool | None = None) -> D:
        return sum(
            (
                row["quantity"]
                for row in self._free_usdc_layers
                if mobility is None or bool(row["mobility"]) is mobility
            ),
            ZERO,
        )

    def _sync_usdc_quantization_dust(self) -> None:
        dust = self.free_usdc - self._layer_quantity()
        if dust < ZERO:
            raise ValueError("M026_NEGATIVE_UNALLOCATED_USDC_DUST")
        self._unallocated_usdc_quantization_dust = dust

    def _take_free_usdc(
        self, quantity: D, *, allow_mobility: bool
    ) -> tuple[D, D, D, D, list[dict[str, Any]]]:
        operational = self._layer_quantity(mobility=False)
        mobility = self._layer_quantity(mobility=True)
        if operational + (mobility if allow_mobility else ZERO) < quantity:
            raise ValueError("M026_USDC_OWNERSHIP_INSUFFICIENT")
        remaining = quantity
        cost = ZERO
        cost_layers: list[dict[str, Any]] = []
        mobility_taken = ZERO
        ordered = [False, True] if allow_mobility else [False]
        for category in ordered:
            for layer in list(self._free_usdc_layers):
                if bool(layer["mobility"]) is not category or remaining <= ZERO:
                    continue
                take = min(layer["quantity"], remaining)
                take_cost = take * layer["basis"]
                layer["quantity"] -= take
                layer["cost"] = layer["quantity"] * layer["basis"]
                remaining -= take
                cost += take_cost
                cost_layers.append(
                    {
                        "quantity": take,
                        "basis": layer["basis"],
                        "mobility": category,
                    }
                )
                if category:
                    mobility_taken += take
                if layer["quantity"] == ZERO:
                    self._free_usdc_layers.remove(layer)
        if remaining != ZERO:
            raise ValueError("M026_USDC_LAYER_DRIFT")
        return cost / quantity, mobility_taken, quantity - mobility_taken, cost, cost_layers

    def _reclassify_sell_reserve(self, quantity: D) -> D:
        remaining = min(quantity, self._layer_quantity(mobility=False))
        moved = ZERO
        for layer in list(self._free_usdc_layers):
            if layer["mobility"] or remaining <= ZERO:
                continue
            take = min(layer["quantity"], remaining)
            take_cost = take * layer["basis"]
            layer["quantity"] -= take
            layer["cost"] = layer["quantity"] * layer["basis"]
            self._add_free_usdc_layer(
                take,
                take_cost / take,
                mobility=True,
                source="RESERVE_RESTORED",
                cost=take_cost,
            )
            remaining -= take
            moved += take
            if layer["quantity"] == ZERO and layer in self._free_usdc_layers:
                self._free_usdc_layers.remove(layer)
        self.sell_mobility_reserve += moved
        self._reserve_restored_usdc += moved
        self._sync_usdc_quantization_dust()
        return moved

    def _observe_reserve_minima(self) -> None:
        if not self._initialized:
            return
        self._min_buy_mobility_reserve = min(
            self._min_buy_mobility_reserve, self.buy_mobility_reserve
        )
        self._min_sell_mobility_reserve = min(
            self._min_sell_mobility_reserve, self.sell_mobility_reserve
        )

    def _fund_order(self, order: QueueOrder, *, allow_mobility: bool) -> None:
        locked = {
            "USDT": ZERO,
            "USDC": ZERO,
            "USDT_ORIGINAL": ZERO,
            "USDC_ORIGINAL": ZERO,
        }
        if order.side == "BUY":
            required = order.price * order.quantity
            excluded = (
                order.source_order_id
                if order.role == "RETURN" and order.direction == "SELL_FIRST"
                else None
            )
            other_locked = self._locked_sell_proceeds(excluded)
            operational = max(ZERO, self.cash - self.buy_mobility_reserve - other_locked)
            mobility_needed = max(ZERO, required - operational)
            if order.role == "RETURN" and mobility_needed > ZERO:
                raise ValueError("M026_RETURN_CANNOT_SPEND_MOBILITY_RESERVE")
            if mobility_needed > ZERO and (
                not allow_mobility or mobility_needed > self.buy_mobility_reserve
            ):
                raise ValueError("M026_USDT_OWNERSHIP_INSUFFICIENT")
            self.cash -= required
            self.reserved_usdt += required
            order.reserved_quote = required
            self._order_asset_cost_remaining[order.order_id] = ZERO
            self._order_asset_cost_layers[order.order_id] = []
            if mobility_needed > ZERO:
                self.buy_mobility_reserve -= mobility_needed
                self._reserve_used_usdt += mobility_needed
                locked["USDT"] = mobility_needed
                locked["USDT_ORIGINAL"] = mobility_needed
        elif order.role == "RETURN" and order.direction == "BUY_FIRST":
            if self.inventory_qty < order.quantity:
                raise ValueError("M026_INVENTORY_LOT_UNAVAILABLE")
            self.inventory_qty -= order.quantity
            self.reserved_usdc += order.quantity
            order.reserved_base = order.quantity
            self._order_asset_cost_remaining[order.order_id] = order.quantity * order.asset_basis
            self._order_asset_cost_layers[order.order_id] = [
                {
                    "quantity": order.quantity,
                    "basis": order.asset_basis,
                    "mobility": False,
                }
            ]
        else:
            basis, mobility_qty, _operational_qty, exact_cost, cost_layers = self._take_free_usdc(
                order.quantity, allow_mobility=allow_mobility
            )
            self.free_usdc -= order.quantity
            self.reserved_usdc += order.quantity
            order.reserved_base = order.quantity
            order.asset_basis = basis
            self._order_asset_cost_remaining[order.order_id] = exact_cost
            self._order_asset_cost_layers[order.order_id] = cost_layers
            if mobility_qty > ZERO:
                self.sell_mobility_reserve -= mobility_qty
                self._reserve_used_usdc += mobility_qty
                locked["USDC"] = mobility_qty
                locked["USDC_ORIGINAL"] = mobility_qty
        self._order_reserve_locked[order.order_id] = locked
        self._sync_usdc_quantization_dust()
        self._observe_reserve_minima()

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
        slot_count: int | None = None,
        slot_epoch: int | None = None,
        zone: str | None = None,
        line_price: D | str | None = None,
        allow_mobility: bool = False,
    ) -> QueueOrder:
        now = self.start_us if time_us is None else int(time_us)
        self._check_time(now)
        value = _dec(price)
        if side not in {"BUY", "SELL"} or value <= ZERO:
            raise ValueError("M026_INVALID_ORDER")
        inherited = self._order_meta.get(int(source_order_id or 0), {})
        slots = int(slot_count if slot_count is not None else inherited.get("slot_count", 1))
        epoch = int(slot_epoch if slot_epoch is not None else self.current_epoch_id)
        base = (
            _dec(self.hotline_epochs[epoch - 1]["SLOT_BASE"])
            if 0 < epoch <= len(self.hotline_epochs)
            else self.slot_base
        )
        target = base * D(slots)
        actual = _dec(quantity) if quantity is not None else quantized_quantity(target, value)
        if actual <= ZERO or actual % D(1) != ZERO:
            raise ValueError("M026_HISTORICAL_STEP_SIZE_VIOLATION")
        if side == "SELL" and _dec(asset_basis) > ZERO and value <= _dec(asset_basis):
            raise ValueError("M026_NEGATIVE_EXIT_PROHIBITED")
        if self.open_order_count >= self.max_open_orders:
            raise ValueError("M026_OPEN_ORDER_CAP_EXCEEDED")
        order = QueueOrder(
            self._next_order_id,
            side,
            value,
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
        self._fund_order(order, allow_mobility=allow_mobility)
        self._next_order_id += 1
        self.orders.append(order)
        line = (
            _dec(line_price) if line_price is not None else _dec(inherited.get("line_price", value))
        )
        origin_zone = zone or inherited.get("origin_zone") or self._zone_for_line(side, line)
        self._order_meta[order.order_id] = {
            "slot_count": slots,
            "slot_base": base,
            "slot_epoch": epoch,
            "target_notional": target,
            "actual_notional": value * actual,
            "line_price": line,
            "origin_zone": origin_zone or "OUTSIDE",
            "drain_only": False,
            "quantization_error": value * actual - target,
        }
        if role == "ENTRY":
            self._cell_latest_entry[order.cell_id or ""] = order.order_id
            self._retired_cells.discard(order.cell_id or "")
        self._max_open_orders = max(self._max_open_orders, self.open_order_count)
        self._record(
            "SUBMIT",
            now,
            order_id=order.order_id,
            side=side,
            price=_s(value),
            quantity=_s(actual),
            role=role,
            column=column,
            level=level,
            direction=direction,
            source_order_id=source_order_id,
            capital_source=capital_source,
            active_us=order.active_us,
            cell_id=order.cell_id,
            asset_basis=_s(order.asset_basis),
            slot_count=slots,
            slot_base_epoch=_s(base),
            slot_epoch=epoch,
            target_slot_notional=_s(target),
            actual_order_notional=_s(value * actual),
            quantization_error=_s(value * actual - target),
            line_price=_s(line),
            origin_zone=origin_zone or "OUTSIDE",
            mobility_usdt_locked=_s(self._order_reserve_locked[order.order_id]["USDT"]),
            mobility_usdc_locked=_s(self._order_reserve_locked[order.order_id]["USDC"]),
            asset_cost_reserved=_s(self._order_asset_cost_remaining[order.order_id]),
            asset_cost_layers=[
                {
                    "quantity": _s(row["quantity"]),
                    "basis": _s(row["basis"]),
                    "mobility": bool(row["mobility"]),
                }
                for row in self._order_asset_cost_layers[order.order_id]
            ],
        )
        if activate_immediately:
            self._activate(order, now)
        return order

    add_order = submit_order

    def _release_reservation(self, order: QueueOrder, remaining: D) -> None:
        if remaining <= ZERO:
            return
        locked = self._order_reserve_locked.get(
            order.order_id,
            {
                "USDT": ZERO,
                "USDC": ZERO,
                "USDT_ORIGINAL": ZERO,
                "USDC_ORIGINAL": ZERO,
            },
        )
        # The locked balance already represents the unfilled remainder because
        # each fill debits a fraction of the original allocation.  Returning a
        # second fraction here would under-refund partial cancellations.
        restore_usdt = locked["USDT"]
        restore_usdc = locked["USDC"]
        if order.side == "BUY":
            amount = remaining * order.price
            self.reserved_usdt -= amount
            order.reserved_quote -= amount
            self.cash += amount
            if restore_usdt > ZERO:
                self.buy_mobility_reserve += restore_usdt
                self._reserve_restored_usdt += restore_usdt
        else:
            self.reserved_usdc -= remaining
            order.reserved_base -= remaining
            cost_layers = self._order_asset_cost_layers.get(order.order_id, [])
            if sum((row["quantity"] for row in cost_layers), ZERO) != remaining:
                raise ValueError("M026_ORDER_ASSET_COST_LAYER_QUANTITY_DRIFT")
            if order.role == "RETURN" and order.direction == "BUY_FIRST":
                self.inventory_qty += remaining
            else:
                restore_usdc = sum(
                    (row["quantity"] for row in cost_layers if row["mobility"]), ZERO
                )
                for layer in cost_layers:
                    self._add_free_usdc_layer(
                        layer["quantity"],
                        layer["basis"],
                        mobility=bool(layer["mobility"]),
                        source=("CANCEL_RESERVE" if layer["mobility"] else "CANCEL_RELEASE"),
                        cost=layer["quantity"] * layer["basis"],
                    )
                self.free_usdc += remaining
                if restore_usdc > ZERO:
                    self.sell_mobility_reserve += restore_usdc
                    self._reserve_restored_usdc += restore_usdc
            self._order_asset_cost_remaining[order.order_id] = ZERO
            self._order_asset_cost_layers[order.order_id] = []
        locked["USDT"] -= restore_usdt
        locked["USDC"] -= restore_usdc
        self._sync_usdc_quantization_dust()
        self._observe_reserve_minima()
        for cell_id in tuple(self._funding_blocked_cells | self._mobility_blocked_cells):
            self._attempted_epoch_cells.discard((self.current_epoch_id, cell_id))

    def _record(self, event: str, time_us: int, **fields: Any) -> None:
        super()._record(event, time_us, **fields)

    def _debit_order_reserve_lock(self, order: QueueOrder, amount: D) -> None:
        locked = self._order_reserve_locked.get(order.order_id)
        if locked is None:
            return
        if order.side == "BUY":
            # Mobility quote is the tail of the reservation because operational
            # cash is consumed first.  Remaining reservation therefore gives
            # the exact unconsumed mobility amount without proportional division.
            locked["USDT"] = min(locked.get("USDT_ORIGINAL", ZERO), order.reserved_quote)
        else:
            locked["USDC"] = sum(
                (
                    row["quantity"]
                    for row in self._order_asset_cost_layers[order.order_id]
                    if row["mobility"]
                ),
                ZERO,
            )

    def _consume_order_asset_cost(self, order: QueueOrder, quantity: D) -> D:
        remaining = quantity
        consumed = ZERO
        layers = self._order_asset_cost_layers[order.order_id]
        while remaining > ZERO and layers:
            layer = layers[0]
            take = min(layer["quantity"], remaining)
            consumed += take * layer["basis"]
            layer["quantity"] -= take
            remaining -= take
            if layer["quantity"] == ZERO:
                layers.pop(0)
        if remaining != ZERO:
            raise ValueError("M026_ORDER_ASSET_COST_LAYER_EXHAUSTED")
        self._order_asset_cost_remaining[order.order_id] -= consumed
        return consumed

    def _fill_order(self, order: QueueOrder, quantity: D, now: int, trade_id: str) -> D:
        amount = min(quantity, order.remaining)
        if amount <= ZERO:
            return ZERO
        lot = (
            self._entry_lot_for_fill(order, amount, now)
            if order.role == "ENTRY"
            else next((item for item in self.lots if item.lot_id in order.lot_ids), None)
        )
        if lot is None:
            raise ValueError("M026_RETURN_FILL_LOT_MISSING")
        if order.side == "SELL" and order.asset_basis > ZERO and order.price <= lot.asset_basis:
            raise ValueError("M026_NEGATIVE_EXIT_FILL_PROHIBITED")
        if order.role == "RETURN":
            lot.closed_quantity += amount
            if order.side == "BUY":
                lot.restored_cost += amount * order.price
                lot.stage = "RESTORING"
            else:
                lot.stage = "CLOSING"
        asset_cost_consumed = ZERO
        if order.side == "SELL":
            asset_cost_consumed = self._consume_order_asset_cost(order, amount)
            self._usdc_cost_basis_total -= asset_cost_consumed
            self.realized_disposal_pnl += amount * order.price - asset_cost_consumed
        if order.side == "BUY":
            self.reserved_usdt -= amount * order.price
            order.reserved_quote -= amount * order.price
            if order.role == "ENTRY":
                self.inventory_qty += amount
                self._usdc_cost_basis_total += amount * order.price
            elif order.direction == "SELL_FIRST":
                self.free_usdc += amount
                self._usdc_cost_basis_total += amount * order.price
                self._add_free_usdc_layer(
                    amount,
                    order.price,
                    mobility=False,
                    source=f"SELL_FIRST_RETURN:{order.order_id}",
                )
                self._sync_usdc_quantization_dust()
        else:
            self.reserved_usdc -= amount
            order.reserved_base -= amount
            self.cash += amount * order.price
        order.filled += amount
        self._debit_order_reserve_lock(order, amount)
        self._fill_count += 1
        meta = self._order_meta[order.order_id]
        self._record(
            "FILL",
            now,
            order_id=order.order_id,
            side=order.side,
            price=_s(order.price),
            quantity=_s(amount),
            source_id=trade_id,
            column=order.column,
            slot_count=meta["slot_count"],
            slot_epoch=meta["slot_epoch"],
            line_price=_s(meta["line_price"]),
            asset_cost_consumed=_s(asset_cost_consumed),
        )
        if order.remaining == ZERO:
            self._complete_order(order, now)
        return amount

    def _submit_return(self, source: QueueOrder, now: int, lot: Lot) -> QueueOrder | None:
        side_price = self._return_target(source)
        if side_price is None:
            return None
        side, price = side_price
        conflicts = [
            item
            for item in self.active_orders
            if item.role == "ENTRY"
            and (
                (item.side == side and item.price == price)
                or (side == "BUY" and item.side == "SELL" and item.price <= price)
                or (side == "SELL" and item.side == "BUY" and item.price >= price)
            )
        ]
        if conflicts:
            self._deferred_returns[source.order_id] = lot.lot_id
            self._deferred_reason[source.order_id] = "RETURN_PENDING_WAIT"
            for conflict in conflicts:
                if conflict.filled == ZERO and conflict.status != "CANCEL_PENDING":
                    self.cancel(conflict.order_id, time_us=now)
            self._record(
                "RETURN_WAITING_FOR_FREE_CANCEL",
                now,
                source_order_id=source.order_id,
                conflict_order_ids=[item.order_id for item in conflicts],
            )
            return None
        if self.open_order_count >= self.max_open_orders:
            candidate = self._farthest_youngest_free_entry(side)
            self._deferred_returns[source.order_id] = lot.lot_id
            self._deferred_reason[source.order_id] = "RETURN_PENDING_WAIT"
            if candidate is not None:
                self.cancel(candidate.order_id, time_us=now)
                self._record(
                    "RETURN_WAITING_FOR_HEADROOM_CANCEL",
                    now,
                    source_order_id=source.order_id,
                    conflict_order_ids=[candidate.order_id],
                )
            return None
        source_meta = self._order_meta[source.order_id]
        try:
            returned = self.submit_order(
                side,
                price,
                quantity=lot.quantity,
                time_us=now,
                role="RETURN",
                column=source.column,
                level=source.level,
                direction=source.direction,
                source_order_id=source.order_id,
                cell_id=source.cell_id,
                asset_basis=lot.asset_basis if side == "SELL" else ZERO,
                slot_count=source_meta["slot_count"],
                slot_epoch=source_meta["slot_epoch"],
                zone=source_meta["origin_zone"],
                line_price=source_meta["line_price"],
            )
            returned.lot_ids.append(lot.lot_id)
            self._deferred_returns.pop(source.order_id, None)
            self._deferred_reason.pop(source.order_id, None)
            return returned
        except ValueError as exc:
            self._deferred_returns[source.order_id] = lot.lot_id
            reason = str(exc)
            self._deferred_reason[source.order_id] = (
                "CAPITAL_FUNDING_BLOCK"
                if "USDT" in reason or "CAPITAL" in reason
                else "MOBILITY_RESERVE_BLOCK"
            )
            self._record("RETURN_DEFERRED", now, source_order_id=source.order_id, reason=str(exc))
            return None

    def _complete_order(self, order: QueueOrder, now: int) -> None:
        if order.activation_evaluated_us is not None:
            self._order_waits.setdefault(order.column, []).append(
                now - order.activation_evaluated_us
            )
        order.status = "FILLED"
        self._remove_from_group(order)
        if order.role == "ENTRY":
            lot = next((item for item in self.lots if item.lot_id in order.lot_ids), None)
            if lot is None or lot.quantity != order.quantity:
                raise ValueError("M026_ENTRY_FILL_LOT_MISMATCH")
            lot.stage = "HOLDING" if order.side == "BUY" else "SOLD"
            self._submit_return(order, now, lot)
            return
        lot = next((item for item in self.lots if item.lot_id in order.lot_ids), None)
        if lot is None:
            raise ValueError("M026_RETURN_COMPLETION_LOT_MISSING")
        profit = order.quantity * (order.price - lot.basis)
        if order.direction == "SELL_FIRST":
            profit = order.quantity * (lot.basis - order.price)
            if lot.closed_quantity > ZERO:
                lot.asset_basis = lot.restored_cost / lot.closed_quantity
            lot.stage = "RESTORED"
        else:
            lot.stage = "CLOSED"
        if profit <= ZERO:
            self._record("NON_POSITIVE_CYCLE_BLOCKED", now, order_id=order.order_id)
            return
        source = next(item for item in self.orders if item.order_id == order.source_order_id)
        source_meta = self._order_meta[source.order_id]
        slots = int(source_meta["slot_count"])
        self.realized_pnl += profit
        self.growth_earned += profit
        self._slot_cycle_pnl += profit
        self._cycles += 1
        self._slot_cycles += slots
        self._column_cycle_counts[order.column] = self._column_cycle_counts.get(order.column, 0) + 1
        if order.direction == "BUY_FIRST":
            self._buy_first_cycles += 1
        else:
            self._sell_first_cycles += 1
        wait = now - (order.queue_wait_start_us or now)
        self._column_waits.setdefault(order.column, []).append(wait)
        cycle = {
            "cycle_id": self._cycles,
            "return_order_id": order.order_id,
            "entry_order_id": source.order_id,
            "physical_weight": 1,
            "entry_slot_count": slots,
            "slot_equivalent_weight": slots,
            "entry_slot_base_epoch": _s(source_meta["slot_base"]),
            "entry_slot_epoch": source_meta["slot_epoch"],
            "entry_quantity": _s(source.quantity),
            "roundtrip_quantity": _s(order.quantity),
            "origin_zone": source_meta["origin_zone"],
            "column": source.column,
            "profit": _s(profit),
            "time_us": now,
        }
        self._cycle_rows.append(cycle)
        self._record(
            "CYCLE",
            now,
            **{key: value for key, value in cycle.items() if key != "time_us"},
            queue_wait_us=wait,
            lot_id=lot.lot_id,
            source_order_id=source.order_id,
        )
        self._restore_reserves(now)
        self._recycle_after_cycle(order, now)
        for cell_id in self._funding_blocked_cells | self._mobility_blocked_cells:
            self._attempted_epoch_cells.discard((self.current_epoch_id, cell_id))
        self._funding_blocked_cells.clear()
        self._mobility_blocked_cells.clear()
        self._reconcile_grid(now)

    def _try_profit_funded_growth(self, now: int) -> None:
        return

    def fund_growth_cell(self, *args: Any, **kwargs: Any) -> QueueOrder:
        raise ValueError("M026_GEOMETRY_GROWTH_DISABLED")

    def _restore_reserves(self, now: int) -> None:
        locked = self._locked_sell_proceeds()
        buy_deficit = max(ZERO, self.buy_mobility_target - self.buy_mobility_reserve)
        buy_available = max(ZERO, self.cash - self.buy_mobility_reserve - locked)
        buy_restore = min(buy_deficit, buy_available)
        if buy_restore > ZERO:
            self.buy_mobility_reserve += buy_restore
            self._reserve_restored_usdt += buy_restore
            self._record("BUY_MOBILITY_RESERVE_RESTORED", now, amount=_s(buy_restore))
        sell_deficit = max(ZERO, self.sell_mobility_target - self.sell_mobility_reserve)
        sell_restore = self._reclassify_sell_reserve(sell_deficit)
        if sell_restore > ZERO:
            self._record("SELL_MOBILITY_RESERVE_RESTORED", now, quantity=_s(sell_restore))
        self._observe_reserve_minima()

    def _candidate_slot_base(self) -> D:
        if self.initial_slot_bank <= ZERO:
            return INITIAL_SLOT_BASE
        raw = (
            INITIAL_SLOT_BASE
            * (self.initial_slot_bank + self._slot_cycle_pnl)
            / self.initial_slot_bank
        )
        # The normalized ledger uses an explicit eight-decimal asset balance
        # quantum.  Rounding down is conservative: it cannot create spendable
        # reserve or enlarge an order from sub-quantum profit.
        return raw.quantize(NORMALIZED_BALANCE_QUANTUM, rounding=ROUND_DOWN)

    def _try_advance_slot_base(self, now: int) -> None:
        candidate = self._candidate_slot_base()
        if candidate <= self.slot_base:
            return
        candidate_buy = MOBILITY_SLOT_UNITS_PER_SIDE * candidate
        candidate_sell = MOBILITY_SLOT_UNITS_PER_SIDE * candidate / INITIAL_SLOT_BASE
        self.buy_mobility_target = candidate_buy
        self.sell_mobility_target = candidate_sell
        self._restore_reserves(now)
        if (
            self.buy_mobility_reserve >= candidate_buy
            and self.sell_mobility_reserve >= candidate_sell
        ):
            self.slot_base = candidate
            self._record(
                "SLOT_BASE_ADVANCED",
                now,
                slot_base=_s(candidate),
                bank_for_slot=_s(self.initial_slot_bank + self._slot_cycle_pnl),
            )
        else:
            self._record(
                "SLOT_BASE_GROWTH_DEFERRED",
                now,
                candidate=_s(candidate),
                buy_reserve=_s(self.buy_mobility_reserve),
                sell_reserve=_s(self.sell_mobility_reserve),
            )

    def _append_epoch(self, now: int, *, direction: str) -> None:
        self._try_advance_slot_base(now)
        epoch = {
            "EPOCH_ID": len(self.hotline_epochs) + 1,
            "TIME_US": now,
            "HOTLINE_PRICE": _s(self.hotline or ZERO),
            "BANK_FOR_SLOT": _s(self.initial_slot_bank + self._slot_cycle_pnl),
            "SLOT_BASE": _s(self.slot_base),
            "BUY_RESERVE_TARGET": _s(self.buy_mobility_target),
            "SELL_RESERVE_TARGET": _s(self.sell_mobility_target),
            "DIRECTION": direction,
        }
        self.hotline_epochs.append(epoch)
        self._hotline_change_times.append(now)
        self._record("HOTLINE_EPOCH_CHANGE", now, **epoch)

    def _midpoint_steps(self) -> int:
        if self.hotline is None or self._last_book is None:
            return 0
        bid = self._last_book["bids"][0][0]
        ask = self._last_book["asks"][0][0]
        midpoint = (bid + ask) / D(2)
        steps = 0
        cursor = self.hotline
        half = M021_TICK_SIZE / D(2)
        while midpoint > cursor + half:
            cursor += M021_TICK_SIZE
            steps += 1
        while midpoint < cursor - half:
            cursor -= M021_TICK_SIZE
            steps -= 1
        return steps

    def _update_hotline(self, now: int) -> None:
        if self.hotline is None or self._last_book is None:
            return
        # Exchange timestamps are not unique book identities.  Re-evaluating an
        # already aligned book is idempotent (zero steps), while suppressing a
        # later book with the same native timestamp would miss a causal move.
        self._last_hotline_book_upper = int(self._last_book.get("exchange_upper_us") or 0)
        steps = self._midpoint_steps()
        direction = "UP" if steps > 0 else "DOWN"
        for _ in range(abs(steps)):
            old = self.hotline
            old_zones = {
                (side, price): self._zone_for_line(side, price)
                for side in ("BUY", "SELL")
                for price in self._target_prices(side)
            }
            self.hotline += M021_TICK_SIZE if steps > 0 else -M021_TICK_SIZE
            self._hotline_changes += 1
            if steps > 0:
                self._up_moves += 1
            else:
                self._down_moves += 1
            self._move_directions.append(direction)
            self._append_epoch(now, direction=direction)
            self._record(
                "HOTLINE_MOVED",
                now,
                old_price=_s(old),
                new_price=_s(self.hotline),
                direction=direction,
            )
            self._reconcile_grid(now, old_zones=old_zones)

    def _cell_id(self, side: str, price: D, column: int) -> str:
        return f"{side}:P{price}:C{column}"

    def _cell_is_occupied(self, cell_id: str) -> bool:
        order_id = self._cell_latest_entry.get(cell_id)
        if order_id is None or cell_id in self._retired_cells:
            return False
        entry = next((row for row in self.orders if row.order_id == order_id), None)
        if entry is None:
            return False
        if entry.status in OPEN_STATES:
            return True
        if entry.status == "FILLED":
            lot = next((row for row in self.lots if row.entry_order_id == entry.order_id), None)
            return lot is not None and lot.stage not in {"CLOSED", "RESTORED", "RECYCLED"}
        if entry.status == "CANCELED_PARTIAL":
            lot = next((row for row in self.lots if row.entry_order_id == entry.order_id), None)
            return lot is not None and lot.stage not in {"CLOSED", "RESTORED", "RECYCLED"}
        return False

    def _mark_drain_only(self, order: QueueOrder, now: int) -> None:
        meta = self._order_meta.get(order.order_id)
        if meta is None or meta["drain_only"]:
            return
        meta["drain_only"] = True
        self._drain_only_orders.add(order.order_id)
        self._record("DRAIN_ONLY", now, order_id=order.order_id, cell_id=order.cell_id)

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
        slots = ZONE_SHAPES[zone][1]
        rank = self._zone_rank(side, price) or 1
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
                if (
                    self.buy_mobility_reserve == ZERO
                    if side == "BUY"
                    else self.sell_mobility_reserve == ZERO
                ):
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
            used = locked["USDT"] > ZERO or locked["USDC"] > ZERO
            self._promotion_counts["FULLY_FUNDED"] += 1
            self._promotion_counts["NEW_COLUMNS"] += 1
            self._promotion_counts["SLOT_UNITS_ADDED"] += D(slots)
            if used:
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
            (side, price): self._zone_for_line(side, price)
            for side in ("BUY", "SELL")
            for price in self._target_prices(side)
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
            target_columns = ZONE_SHAPES[zone][0]
            if order.column > target_columns:
                self._mark_drain_only(order, now)
            elif meta["drain_only"]:
                meta["drain_only"] = False
                self._drain_only_orders.discard(order.order_id)
                self._record(
                    "DRAIN_ONLY_REVERSED_BY_REPROMOTION",
                    now,
                    order_id=order.order_id,
                    zone=zone,
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
            if zone is None:
                continue
            old_zone = old_zones.get((side, price)) if old_zones is not None else zone
            if old_zone == "FAR" and zone == "MID":
                self._promotion_counts["FAR_TO_MID"] += 1
            elif old_zone == "MID" and zone == "HOT":
                self._promotion_counts["MID_TO_HOT"] += 1
            elif old_zone not in {zone, None}:
                self._promotion_counts["DIRECT_MULTI_LEVEL"] += 1
            target_columns = ZONE_SHAPES[zone][0]
            promotion = old_zones is not None and old_zone != zone
            for column in range(1, target_columns + 1):
                self._submit_grid_cell(side, price, column, zone, now, promotion=promotion)

    def _manage_rolling_window(self, now: int) -> None:
        if not self._initialized or self._last_book is None:
            return
        self._update_hotline(now)
        self._reconcile_grid(now)

    def receive_book(self, book: Any, *, capture_time_us: int | None = None) -> None:
        """Apply the hotline to the newly received causal book, not the prior book."""
        super().receive_book(book, capture_time_us=capture_time_us)
        logical = int(
            capture_time_us
            if capture_time_us is not None
            else (
                book.get("capture_time_us", book.get("time_us", self.start_us))
                if isinstance(book, dict)
                else getattr(
                    book,
                    "capture_time_us",
                    getattr(book, "time_us", self.start_us),
                )
            )
        )
        self._manage_rolling_window(logical)
        self.validate_invariants()

    def initialize_triangle(self, time_us: int) -> None:
        """Initialize M026's 15-level 3/2/1 grid and segregated mobility reserve."""
        if self._initialized:
            return
        if self._last_book is None:
            raise ValueError("M026_BOOK_REQUIRED_FOR_INITIALIZATION")
        bid = self._last_book["bids"][0][0]
        ask = self._last_book["asks"][0][0]
        self.hotline = ask
        self.initial_hotline = ask
        self._initial_sell_basis = bid
        self.slot_base = INITIAL_SLOT_BASE
        self.buy_mobility_target = MOBILITY_SLOT_UNITS_PER_SIDE * self.slot_base
        self.sell_mobility_target = MOBILITY_SLOT_UNITS_PER_SIDE
        buy_rows: list[tuple[D, int, int, str]] = []
        sell_rows: list[tuple[D, int, int, str]] = []
        for side, rows in (("BUY", buy_rows), ("SELL", sell_rows)):
            for rank, price in enumerate(self._target_prices(side), 1):
                zone = zone_for_rank(rank)
                assert zone is not None
                columns, slots = ZONE_SHAPES[zone]
                for column in range(1, columns + 1):
                    rows.append((price, column, slots, zone))
        operational_usdt = sum(
            (
                price * quantized_quantity(self.slot_base * D(slots), price)
                for price, _column, slots, _zone in buy_rows
            ),
            ZERO,
        )
        operational_usdc = sum(
            (
                quantized_quantity(self.slot_base * D(slots), price)
                for price, _column, slots, _zone in sell_rows
            ),
            ZERO,
        )
        self.initial_usdt = operational_usdt + self.buy_mobility_target
        self.initial_usdc = operational_usdc + self.sell_mobility_target
        self.initial_mark = self.initial_usdt + self.initial_usdc * bid
        self.initial_slot_bank = self.initial_mark
        self.cash = self.initial_usdt
        self.free_usdc = self.initial_usdc
        self._usdc_cost_basis_total = self.initial_usdc * bid
        self.buy_mobility_reserve = self.buy_mobility_target
        self.sell_mobility_reserve = self.sell_mobility_target
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
        for side, rows in (("BUY", buy_rows), ("SELL", sell_rows)):
            for _rank, (price, column, slots, zone) in enumerate(rows, 1):
                level = self._zone_rank(side, price) or 1
                self.submit_order(
                    side,
                    price,
                    time_us=time_us,
                    column=column,
                    level=level,
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
            raise ValueError("M026_INITIAL_ORDER_GEOMETRY_DRIFT")
        self._record(
            "DYNAMIC_GRID_INITIALIZED",
            time_us,
            hotline=_s(self.hotline),
            initial_slot_base=_s(self.slot_base),
            operational_slot_units=_s(INITIAL_OPERATIONAL_SLOT_UNITS),
            mobility_slot_units=_s(D(16)),
            architectural_slot_units=_s(INITIAL_ARCHITECTURAL_SLOT_UNITS),
            initial_usdt=_s(self.initial_usdt),
            initial_usdc=_s(self.initial_usdc),
            initial_mark=_s(self.initial_mark),
            quantization_rule="ROUND_HALF_UP_HISTORICAL_STEP_MIN_ONE",
        )

    def _recycle_after_cycle(self, order: QueueOrder, now: int) -> None:
        source = next((row for row in self.orders if row.order_id == order.source_order_id), None)
        if source is None:
            return
        source_meta = self._order_meta[source.order_id]
        line_price = _dec(source_meta["line_price"])
        zone = self._zone_for_line(source.side, line_price)
        target_columns = ZONE_SHAPES[zone][0] if zone else 0
        cell_id = source.cell_id or ""
        if source_meta["drain_only"] or source.column > target_columns:
            self._retired_cells.add(cell_id)
            self._retired_after_drain += 1
            lot = next((row for row in self.lots if row.lot_id in order.lot_ids), None)
            if lot is not None and lot.stage == "RESTORED":
                lot.stage = "RECYCLED"
            self._record(
                "RETIRED_AFTER_DRAIN",
                now,
                source_order_id=source.order_id,
                cell_id=cell_id,
            )
            return
        slots = ZONE_SHAPES[zone][1]
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
                old_slot_count=source_meta["slot_count"],
                new_slot_count=slots,
                line_price=_s(line_price),
            )
        except ValueError as exc:
            self._retired_cells.add(cell_id)
            self._funding_blocked_cells.add(cell_id)
            self._record(
                "PRINCIPAL_RECYCLE_DEFERRED",
                now,
                source_order_id=source.order_id,
                reason=str(exc),
            )

    def _queue_components(self, order: QueueOrder) -> tuple[D, D]:
        group = self.groups.get((order.side, order.price))
        if group is None:
            return ZERO, ZERO
        public = ZERO
        own = ZERO
        for segment in group.segments:
            public += segment.public_remaining
            for order_id in segment.order_ids:
                if order_id == order.order_id:
                    return public, own
                predecessor = next((row for row in self.orders if row.order_id == order_id), None)
                if predecessor is not None and predecessor.status in OPEN_STATES:
                    own += predecessor.remaining
        return public, own

    def _observe(self, now: int) -> None:
        elapsed = max(0, now - self._last_observation_us)
        if elapsed > 0 and self._initialized:
            if (
                self.buy_mobility_reserve < self.buy_mobility_target
                or self.sell_mobility_reserve < self.sell_mobility_target
            ):
                self._reserve_below_target_us += elapsed
            for order in self.active_orders:
                meta = self._order_meta.get(order.order_id)
                if meta is None:
                    continue
                zone = self._zone_for_line(
                    order.side
                    if order.role == "ENTRY"
                    else ("BUY" if order.direction == "BUY_FIRST" else "SELL"),
                    _dec(meta["line_price"]),
                )
                if zone in self._zone_order_time_us:
                    self._zone_order_time_us[zone] += elapsed
                    self._zone_capital_time[zone] += order.remaining * order.price * D(elapsed)
                category = "PRODUCTIVE_ACTIVE_TIME"
                if zone is None:
                    category = "OUTSIDE_ACTIVE_GRID"
                elif order.role == "RETURN" and order.status != "ACTIVE":
                    category = "RETURN_PENDING_WAIT"
                elif order.status == "ACTIVE":
                    public, own = self._queue_components(order)
                    if public > ZERO:
                        category = "PUBLIC_FIFO_WAIT"
                    elif own > ZERO:
                        category = "OWN_FIFO_WAIT"
                self._limiter_entity_time_us[category] += elapsed
            for reason in self._deferred_reason.values():
                self._limiter_entity_time_us[reason] += elapsed
            self._limiter_entity_time_us["CAPITAL_FUNDING_BLOCK"] += elapsed * len(
                self._funding_blocked_cells - self._mobility_blocked_cells
            )
            self._limiter_entity_time_us["MOBILITY_RESERVE_BLOCK"] += elapsed * len(
                self._mobility_blocked_cells
            )
        super()._observe(now)

    def _marked_inventory(self, mark: D) -> tuple[D, D, D]:
        quantity = self.free_usdc + self.reserved_usdc + self.inventory_qty
        return (
            quantity,
            self._usdc_cost_basis_total,
            quantity * mark - self._usdc_cost_basis_total,
        )

    @staticmethod
    def _run_length(directions: list[str], target: str) -> int:
        best = current = 0
        for direction in directions:
            current = current + 1 if direction == target else 0
            best = max(best, current)
        return best

    def metrics(self) -> dict[str, Any]:
        mark = self._last_book["bids"][0][0] if self._last_book else ZERO
        final_usdt = self.cash + self.reserved_usdt
        final_usdc = self.free_usdc + self.reserved_usdc + self.inventory_qty
        final_total = final_usdt + final_usdc * mark
        inventory_qty, inventory_cost, unrealized = self._marked_inventory(mark)
        zone_physical = {
            zone: sum(row["origin_zone"] == zone for row in self._cycle_rows)
            for zone in ZONE_SHAPES
        }
        zone_slots = {
            zone: sum(
                (
                    int(row["slot_equivalent_weight"])
                    for row in self._cycle_rows
                    if row["origin_zone"] == zone
                ),
                0,
            )
            for zone in ZONE_SHAPES
        }
        columns = sorted({int(row["column"]) for row in self._cycle_rows} | {1, 2, 3})
        column_table = []
        for column in columns:
            waits = list(self._order_waits.get(column, []))
            physical = sum(int(row["column"]) == column for row in self._cycle_rows)
            slots = sum(
                (
                    int(row["slot_equivalent_weight"])
                    for row in self._cycle_rows
                    if int(row["column"]) == column
                ),
                0,
            )
            column_table.append(
                {
                    "COLUMN": column,
                    "PHYSICAL_CYCLES": physical,
                    "SLOT_CYCLES": slots,
                    "ORDERS": sum(order.column == column for order in self.orders),
                    "FILLS": sum(
                        row.get("column") == column for row in self.audit if row["event"] == "FILL"
                    ),
                    "ACTIVATION_TO_FULL_FILL_MEDIAN_US": median(waits) if waits else None,
                    "ACTIVATION_TO_FULL_FILL_P95_US": self._percentile(waits, 0.95),
                    "QUEUE_WAIT_SCOPE": "RESTING_RESIDENCE_TO_FULL_FILL_NOT_CAUSAL_COMPONENT",
                }
            )
        hotline_intervals = [
            later - earlier for earlier, later in pairwise(self._hotline_change_times[1:])
        ]
        slot_bases = [_dec(row["SLOT_BASE"]) for row in self.hotline_epochs]
        quantization = [meta["quantization_error"] for meta in self._order_meta.values()]
        order_events = [row["event"] for row in self.audit]
        post_only = sum(
            order.status in {"REJECTED_POST_ONLY", "SHADOW_REJECTED_POST_ONLY"}
            for order in self.orders
        )
        limiter_total = sum(self._limiter_entity_time_us.values())
        limiter_rows = {
            key: {
                "ENTITY_TIME_US": value,
                "SHARE": _s(D(value) / D(limiter_total)) if limiter_total else "0",
            }
            for key, value in self._limiter_entity_time_us.items()
        }
        main_limiter = (
            max(
                self._limiter_entity_time_us,
                key=self._limiter_entity_time_us.get,
            )
            if limiter_total
            else "INSUFFICIENT_OBSERVATION"
        )
        initial_buy_reserve = MOBILITY_SLOT_UNITS_PER_SIDE * INITIAL_SLOT_BASE
        initial_sell_reserve = MOBILITY_SLOT_UNITS_PER_SIDE
        total_used_eq = self._reserve_used_usdt + self._reserve_used_usdc * mark
        total_restored_eq = self._reserve_restored_usdt + self._reserve_restored_usdc * mark
        zone_table = []
        for zone in ZONE_SHAPES:
            hours = D(self._zone_order_time_us[zone]) / D("3600000000")
            zone_table.append(
                {
                    "ZONE": zone,
                    "PHYSICAL_CYCLES": zone_physical[zone],
                    "SLOT_CYCLES": zone_slots[zone],
                    "ACTIVE_ORDER_HOURS": _s(hours),
                    "PHYSICAL_CYCLES_PER_ACTIVE_ORDER_HOUR": _s(
                        D(zone_physical[zone]) / hours if hours else ZERO
                    ),
                    "SLOT_CYCLES_PER_ACTIVE_ORDER_HOUR": _s(
                        D(zone_slots[zone]) / hours if hours else ZERO
                    ),
                    "CAPITAL_TIME_WEIGHTED": _s(
                        self._zone_capital_time[zone] / D(self.end_us - self.start_us)
                        if self.end_us > self.start_us
                        else ZERO
                    ),
                }
            )
        return {
            "MODEL": "M026",
            "PERIOD": "3H",
            "INITIAL_SLOT_BASE": _s(INITIAL_SLOT_BASE),
            "FINAL_SLOT_BASE": _s(self.slot_base),
            "PHYSICAL_CYCLES": self._cycles,
            "PHYSICAL_CYCLES_PER_HOUR": _s(D(self._cycles) / D(3)),
            "SLOT_EQUIVALENT_CYCLES": self._slot_cycles,
            "SLOT_EQUIVALENT_CYCLES_PER_HOUR": _s(D(self._slot_cycles) / D(3)),
            "PHYSICAL_GATE_GT_12_3333_PASS": self._cycles >= 38,
            "PHYSICAL_GATE_EXACT_RULE": "PHYSICAL_CYCLES >= 38 IN 3H",
            "SLOT_GATE_20_PER_HOUR_PASS": self._slot_cycles >= 60,
            "HOT_PHYSICAL_CYCLES": zone_physical["HOT"],
            "MID_PHYSICAL_CYCLES": zone_physical["MID"],
            "FAR_PHYSICAL_CYCLES": zone_physical["FAR"],
            "HOT_SLOT_CYCLES": zone_slots["HOT"],
            "MID_SLOT_CYCLES": zone_slots["MID"],
            "FAR_SLOT_CYCLES": zone_slots["FAR"],
            "COLUMN_1_CYCLES": next(
                row["PHYSICAL_CYCLES"] for row in column_table if row["COLUMN"] == 1
            ),
            "COLUMN_2_CYCLES": next(
                row["PHYSICAL_CYCLES"] for row in column_table if row["COLUMN"] == 2
            ),
            "COLUMN_3_CYCLES": next(
                row["PHYSICAL_CYCLES"] for row in column_table if row["COLUMN"] == 3
            ),
            "HOTLINE_CHANGES": self._hotline_changes,
            "HOTLINE_EPOCHS": len(self.hotline_epochs),
            "UPWARD_HOTLINE_MOVES": self._up_moves,
            "DOWNWARD_HOTLINE_MOVES": self._down_moves,
            "MAX_CONSECUTIVE_UP_MOVES": self._run_length(self._move_directions, "UP"),
            "MAX_CONSECUTIVE_DOWN_MOVES": self._run_length(self._move_directions, "DOWN"),
            "HOTLINE_CHANGE_INTERVAL_MEAN_US": (
                sum(hotline_intervals) / len(hotline_intervals) if hotline_intervals else None
            ),
            "HOTLINE_CHANGE_INTERVAL_MEDIAN_US": median(hotline_intervals)
            if hotline_intervals
            else None,
            "HOTLINE_CHANGE_INTERVAL_P95_US": self._percentile(hotline_intervals, 0.95),
            "FAR_TO_MID_PROMOTIONS": self._promotion_counts["FAR_TO_MID"],
            "MID_TO_HOT_PROMOTIONS": self._promotion_counts["MID_TO_HOT"],
            "DIRECT_MULTI_LEVEL_PROMOTIONS": self._promotion_counts["DIRECT_MULTI_LEVEL"],
            "AGED_ORDERS_PRESERVED": self._promotion_counts["AGED_PRESERVED"],
            "NEW_COLUMNS_CREATED_ON_PROMOTION": self._promotion_counts["NEW_COLUMNS"],
            "SLOT_UNITS_ADDED_ON_PROMOTION": _s(self._promotion_counts["SLOT_UNITS_ADDED"]),
            "PROMOTIONS_FULLY_FUNDED": self._promotion_counts["FULLY_FUNDED"],
            "PROMOTIONS_PARTIALLY_FUNDED": self._promotion_counts["PARTIALLY_FUNDED"],
            "PROMOTIONS_BLOCKED_BY_CAPITAL": self._promotion_counts["BLOCKED_CAPITAL"],
            "PROMOTIONS_BLOCKED_BY_ASSET": self._promotion_counts["BLOCKED_ASSET"],
            "UNDERFUNDED_PROMOTIONS": self._promotion_counts["BLOCKED_CAPITAL"]
            + self._promotion_counts["BLOCKED_ASSET"],
            "INITIAL_BUY_MOBILITY_RESERVE": _s(initial_buy_reserve),
            "INITIAL_SELL_MOBILITY_RESERVE": _s(initial_sell_reserve),
            "MIN_BUY_MOBILITY_RESERVE": _s(self._min_buy_mobility_reserve),
            "MIN_SELL_MOBILITY_RESERVE": _s(self._min_sell_mobility_reserve),
            "MOBILITY_RESERVE_USED": _s(total_used_eq),
            "TOTAL_RESERVE_USED_USDT": _s(self._reserve_used_usdt),
            "TOTAL_RESERVE_USED_USDC": _s(self._reserve_used_usdc),
            "TOTAL_RESERVE_RESTORED_USDT": _s(self._reserve_restored_usdt),
            "TOTAL_RESERVE_RESTORED_USDC": _s(self._reserve_restored_usdc),
            "TOTAL_RESERVE_RESTORED_USDT_EQ": _s(total_restored_eq),
            "MOBILITY_RESERVE_EXHAUSTION_EVENTS": self._reserve_exhaustions,
            "TIME_RESERVE_BELOW_TARGET_US": self._reserve_below_target_us,
            "HOTLINE_EPOCH_TABLE": list(self.hotline_epochs),
            "MAX_SLOT_BASE": _s(max(slot_bases) if slot_bases else self.slot_base),
            "MIN_SLOT_BASE": _s(min(slot_bases) if slot_bases else self.slot_base),
            "TOTAL_SLOT_BASE_GROWTH_PCT": _s((self.slot_base / INITIAL_SLOT_BASE - D(1)) * D(100)),
            "INITIAL_OPEN_ENTRY_ORDERS": self._initial_open_entry_orders,
            "MAX_SIMULTANEOUS_OPEN_ORDERS": self._max_open_orders,
            "OPEN_ORDERS_AT_CUTOFF": self.open_order_count,
            "ORDERS_CREATED": len(self.orders),
            "ORDERS_CANCELLED": order_events.count("CANCEL_ACK"),
            "DRAIN_ONLY_ORDERS": len(self._drain_only_orders),
            "RETIRED_AFTER_DRAIN": self._retired_after_drain,
            "OWNED_RETURN_ORDERS": sum(order.role == "RETURN" for order in self.orders),
            "POST_ONLY_REJECTIONS": post_only,
            "TOTAL_FILLS": self._fill_count,
            "INITIAL_USDT": _s(self.initial_usdt),
            "INITIAL_USDC": _s(self.initial_usdc),
            "INITIAL_TOTAL": _s(self.initial_mark),
            "INITIAL_TOTAL_MARKED": _s(self.initial_mark),
            "FINAL_USDT": _s(final_usdt),
            "FINAL_USDC": _s(final_usdc),
            "FINAL_TOTAL": _s(final_total),
            "FINAL_TOTAL_MARKED": _s(final_total),
            "REALIZED_CYCLE_PNL": _s(self.realized_pnl),
            "REALIZED_DISPOSAL_PNL": _s(self.realized_disposal_pnl),
            "UNREALIZED_PNL": _s(unrealized),
            "INVENTORY_MARKED_QUANTITY": _s(inventory_qty),
            "INVENTORY_COST_BASIS": _s(inventory_cost),
            "PNL_IDENTITY_RESIDUAL": _s(
                final_total - self.initial_mark - self.realized_disposal_pnl - unrealized
            ),
            "CAPITAL_DUPLICATION": "ZERO_REQUIRED",
            "CYCLE_RECONCILIATION": list(self._cycle_rows),
            "COLUMN_TABLE": column_table,
            "ZONE_TABLE": zone_table,
            "LIMITER_ENTITY_TIME": limiter_rows,
            "DOMINANT_DESCRIPTIVE_ENTITY_TIME_STATE": main_limiter,
            "LIMITER_DENOMINATOR": (
                "SUM_OF_EXPLICIT_ENTITY_STATE_MICROSECONDS; "
                "DEFERRED/BLOCKED CELLS ARE SEPARATE ENTITIES"
            ),
            "QUANTIZATION_RULE": "ROUND_HALF_UP_HISTORICAL_STEP_MIN_ONE",
            "NORMALIZED_BALANCE_QUANTUM": _s(NORMALIZED_BALANCE_QUANTUM),
            "UNALLOCATED_USDC_QUANTIZATION_DUST": _s(self._unallocated_usdc_quantization_dust),
            "QUANTIZATION_ERROR_MIN": _s(min(quantization) if quantization else ZERO),
            "QUANTIZATION_ERROR_MAX": _s(max(quantization) if quantization else ZERO),
            "QUANTIZATION_ERROR_MEAN": _s(
                sum(quantization, ZERO) / D(len(quantization)) if quantization else ZERO
            ),
            "NORMALIZED_NON_EXECUTABLE": True,
            "AUDIT": "PENDING_INDEPENDENT_POST_RUN_REVIEW",
            "MAIN_LIMITER": "UNDETERMINED_DESCRIPTIVE_ENTITY_TIME_ONLY",
            "STATUS": "COMPLETE_PENDING_INDEPENDENT_AUDIT",
        }

    def finish(self, *, time_us: int) -> dict[str, Any]:
        if time_us != self.end_us:
            self._check_time(time_us)
        self._observe(time_us)
        return self.metrics()

    def validate_invariants(self) -> None:
        if getattr(self, "_restoring_m026", False):
            return
        super().validate_invariants()
        if not self._initialized:
            return
        if self._layer_quantity() + self._unallocated_usdc_quantization_dust != self.free_usdc:
            raise ValueError("M026_FREE_USDC_LAYER_DRIFT")
        if self._layer_quantity(mobility=True) != self.sell_mobility_reserve:
            raise ValueError("M026_SELL_MOBILITY_RESERVE_DRIFT")
        if self.buy_mobility_reserve > self.cash - self._locked_sell_proceeds():
            raise ValueError("M026_BUY_MOBILITY_RESERVE_DRIFT")
        if self._slot_cycles != sum(int(row["slot_equivalent_weight"]) for row in self._cycle_rows):
            raise ValueError("M026_SLOT_CYCLE_RECONCILIATION_DRIFT")
        if self._cycles != len(self._cycle_rows):
            raise ValueError("M026_PHYSICAL_CYCLE_RECONCILIATION_DRIFT")
        if self.hotline is not None and self.hotline % M021_TICK_SIZE != ZERO:
            raise ValueError("M026_HOTLINE_TICK_DRIFT")
        for order in self.orders:
            meta = self._order_meta.get(order.order_id)
            if meta is None:
                raise ValueError("M026_ORDER_METADATA_MISSING")
            if order.quantity % D(1) != ZERO:
                raise ValueError("M026_QUANTITY_STEP_DRIFT")
            if order.role == "ENTRY" and _dec(meta["line_price"]) != order.price:
                raise ValueError("M026_ENTRY_PRICE_IDENTITY_DRIFT")
            layers = self._order_asset_cost_layers.get(order.order_id)
            if layers is None:
                raise ValueError("M026_ORDER_ASSET_COST_LAYERS_MISSING")
            if (
                sum((row["quantity"] * row["basis"] for row in layers), ZERO)
                != (self._order_asset_cost_remaining[order.order_id])
            ):
                raise ValueError("M026_ORDER_ASSET_COST_LAYER_DRIFT")
        if any(row["quantity"] * row["basis"] != row["cost"] for row in self._free_usdc_layers):
            raise ValueError("M026_FREE_USDC_COST_LAYER_DRIFT")
        if self._usdc_cost_basis_total < ZERO:
            raise ValueError("M026_NEGATIVE_USDC_COST_BASIS")

    def _m026_state(self) -> dict[str, Any]:
        decimal_keys = {
            "slot_base": self.slot_base,
            "initial_slot_bank": self.initial_slot_bank,
            "slot_cycle_pnl": self._slot_cycle_pnl,
            "buy_mobility_reserve": self.buy_mobility_reserve,
            "sell_mobility_reserve": self.sell_mobility_reserve,
            "buy_mobility_target": self.buy_mobility_target,
            "sell_mobility_target": self.sell_mobility_target,
            "initial_sell_basis": self._initial_sell_basis,
            "reserve_used_usdt": self._reserve_used_usdt,
            "reserve_used_usdc": self._reserve_used_usdc,
            "reserve_restored_usdt": self._reserve_restored_usdt,
            "reserve_restored_usdc": self._reserve_restored_usdc,
            "min_buy_mobility_reserve": self._min_buy_mobility_reserve,
            "min_sell_mobility_reserve": self._min_sell_mobility_reserve,
            "usdc_cost_basis_total": self._usdc_cost_basis_total,
            "unallocated_usdc_quantization_dust": self._unallocated_usdc_quantization_dust,
        }
        return {
            "hotline": None if self.hotline is None else _s(self.hotline),
            "initial_hotline": None if self.initial_hotline is None else _s(self.initial_hotline),
            "decimal": {key: _s(value) for key, value in decimal_keys.items()},
            "hotline_epochs": self.hotline_epochs,
            "hotline_changes": self._hotline_changes,
            "up_moves": self._up_moves,
            "down_moves": self._down_moves,
            "move_directions": self._move_directions,
            "hotline_change_times": self._hotline_change_times,
            "last_hotline_book_upper": self._last_hotline_book_upper,
            "slot_cycles": self._slot_cycles,
            "cycle_rows": self._cycle_rows,
            "order_meta": {
                str(key): {
                    **value,
                    **{
                        name: _s(value[name])
                        for name in (
                            "slot_base",
                            "target_notional",
                            "actual_notional",
                            "line_price",
                            "quantization_error",
                        )
                    },
                }
                for key, value in self._order_meta.items()
            },
            "cell_latest_entry": self._cell_latest_entry,
            "retired_cells": sorted(self._retired_cells),
            "attempted_epoch_cells": [
                [epoch, cell] for epoch, cell in sorted(self._attempted_epoch_cells)
            ],
            "funding_blocked_cells": sorted(self._funding_blocked_cells),
            "mobility_blocked_cells": sorted(self._mobility_blocked_cells),
            "deferred_reason": {str(key): value for key, value in self._deferred_reason.items()},
            "free_usdc_layers": [
                {
                    **row,
                    "quantity": _s(row["quantity"]),
                    "basis": _s(row["basis"]),
                    "cost": _s(row["cost"]),
                }
                for row in self._free_usdc_layers
            ],
            "order_asset_cost_remaining": {
                str(key): _s(value) for key, value in self._order_asset_cost_remaining.items()
            },
            "order_asset_cost_layers": {
                str(key): [
                    {
                        "quantity": _s(row["quantity"]),
                        "basis": _s(row["basis"]),
                        "mobility": bool(row["mobility"]),
                    }
                    for row in layers
                ]
                for key, layers in self._order_asset_cost_layers.items()
            },
            "reserve_exhaustions": self._reserve_exhaustions,
            "reserve_below_target_us": self._reserve_below_target_us,
            "order_reserve_locked": {
                str(key): {name: _s(value) for name, value in row.items()}
                for key, row in self._order_reserve_locked.items()
            },
            "promotion_counts": {
                key: _s(value) if isinstance(value, D) else value
                for key, value in self._promotion_counts.items()
            },
            "drain_only_orders": sorted(self._drain_only_orders),
            "retired_after_drain": self._retired_after_drain,
            "initial_open_entry_orders": self._initial_open_entry_orders,
            "zone_order_time_us": self._zone_order_time_us,
            "zone_capital_time": {key: _s(value) for key, value in self._zone_capital_time.items()},
            "limiter_entity_time_us": self._limiter_entity_time_us,
        }

    def checkpoint(self) -> dict[str, Any]:
        parent_state = super()._state()
        state = {"parent": parent_state, "m026": self._m026_state()}
        return {
            "schema": "M026_DYNAMIC_HOTLINE_321_V1",
            "state": state,
            "sha256": canonical_hash(state),
        }

    def restore(self, checkpoint: dict[str, Any]) -> None:
        if checkpoint.get("schema") != "M026_DYNAMIC_HOTLINE_321_V1":
            raise ValueError("INVALID_M026_CHECKPOINT")
        state = checkpoint.get("state")
        if not isinstance(state, dict) or checkpoint.get("sha256") != canonical_hash(state):
            raise ValueError("M026_CHECKPOINT_HASH_MISMATCH")
        self._restoring_m026 = True
        try:
            parent = state["parent"]
            super().restore(
                {
                    "schema": "M024_TRIANGULAR_PRE_AGED_QUEUE_V1",
                    "state": parent,
                    "sha256": canonical_hash(parent),
                }
            )
            extra = state["m026"]
            self.hotline = None if extra["hotline"] is None else _dec(extra["hotline"])
            self.initial_hotline = (
                None if extra["initial_hotline"] is None else _dec(extra["initial_hotline"])
            )
            decimals = extra["decimal"]
            for target, source in (
                ("slot_base", "slot_base"),
                ("initial_slot_bank", "initial_slot_bank"),
                ("_slot_cycle_pnl", "slot_cycle_pnl"),
                ("buy_mobility_reserve", "buy_mobility_reserve"),
                ("sell_mobility_reserve", "sell_mobility_reserve"),
                ("buy_mobility_target", "buy_mobility_target"),
                ("sell_mobility_target", "sell_mobility_target"),
                ("_initial_sell_basis", "initial_sell_basis"),
                ("_reserve_used_usdt", "reserve_used_usdt"),
                ("_reserve_used_usdc", "reserve_used_usdc"),
                ("_reserve_restored_usdt", "reserve_restored_usdt"),
                ("_reserve_restored_usdc", "reserve_restored_usdc"),
                ("_min_buy_mobility_reserve", "min_buy_mobility_reserve"),
                ("_min_sell_mobility_reserve", "min_sell_mobility_reserve"),
                ("_usdc_cost_basis_total", "usdc_cost_basis_total"),
                (
                    "_unallocated_usdc_quantization_dust",
                    "unallocated_usdc_quantization_dust",
                ),
            ):
                setattr(self, target, _dec(decimals[source]))
            self.hotline_epochs = list(extra["hotline_epochs"])
            self._hotline_changes = int(extra["hotline_changes"])
            self._up_moves = int(extra["up_moves"])
            self._down_moves = int(extra["down_moves"])
            self._move_directions = list(extra["move_directions"])
            self._hotline_change_times = list(extra["hotline_change_times"])
            self._last_hotline_book_upper = extra["last_hotline_book_upper"]
            self._slot_cycles = int(extra["slot_cycles"])
            self._cycle_rows = list(extra["cycle_rows"])
            self._order_meta = {}
            for key, value in extra["order_meta"].items():
                value = dict(value)
                for name in (
                    "slot_base",
                    "target_notional",
                    "actual_notional",
                    "line_price",
                    "quantization_error",
                ):
                    value[name] = _dec(value[name])
                self._order_meta[int(key)] = value
            self._cell_latest_entry = {
                str(key): int(value) for key, value in extra["cell_latest_entry"].items()
            }
            self._retired_cells = set(extra["retired_cells"])
            self._attempted_epoch_cells = {
                (int(epoch), str(cell)) for epoch, cell in extra["attempted_epoch_cells"]
            }
            self._funding_blocked_cells = set(extra["funding_blocked_cells"])
            self._mobility_blocked_cells = set(extra["mobility_blocked_cells"])
            self._deferred_reason = {
                int(key): str(value) for key, value in extra.get("deferred_reason", {}).items()
            }
            self._free_usdc_layers = [
                {
                    **row,
                    "quantity": _dec(row["quantity"]),
                    "basis": _dec(row["basis"]),
                    "cost": _dec(row["cost"]),
                }
                for row in extra["free_usdc_layers"]
            ]
            self._order_asset_cost_remaining = {
                int(key): _dec(value) for key, value in extra["order_asset_cost_remaining"].items()
            }
            self._order_asset_cost_layers = {
                int(key): [
                    {
                        "quantity": _dec(row["quantity"]),
                        "basis": _dec(row["basis"]),
                        "mobility": bool(row["mobility"]),
                    }
                    for row in layers
                ]
                for key, layers in extra["order_asset_cost_layers"].items()
            }
            self._reserve_exhaustions = int(extra["reserve_exhaustions"])
            self._reserve_below_target_us = int(extra["reserve_below_target_us"])
            self._order_reserve_locked = {
                int(key): {name: _dec(value) for name, value in row.items()}
                for key, row in extra["order_reserve_locked"].items()
            }
            self._promotion_counts = dict(extra["promotion_counts"])
            self._promotion_counts["SLOT_UNITS_ADDED"] = _dec(
                self._promotion_counts["SLOT_UNITS_ADDED"]
            )
            self._drain_only_orders = set(extra["drain_only_orders"])
            self._retired_after_drain = int(extra["retired_after_drain"])
            self._initial_open_entry_orders = int(extra["initial_open_entry_orders"])
            self._zone_order_time_us = {
                str(key): int(value) for key, value in extra["zone_order_time_us"].items()
            }
            self._zone_capital_time = {
                str(key): _dec(value) for key, value in extra["zone_capital_time"].items()
            }
            self._limiter_entity_time_us = {
                str(key): int(value) for key, value in extra["limiter_entity_time_us"].items()
            }
        finally:
            self._restoring_m026 = False
        self.validate_invariants()

    @classmethod
    def from_checkpoint(
        cls, checkpoint: dict[str, Any], *, start_us: int, end_us: int
    ) -> DynamicHotline321Probe:
        value = cls(start_us=start_us, end_us=end_us)
        value.restore(checkpoint)
        return value


M026DynamicHotline321 = DynamicHotline321Probe

__all__ = [
    "DynamicHotline321Probe",
    "M026DynamicHotline321",
    "quantized_quantity",
    "zone_for_rank",
]
