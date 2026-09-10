"""M030 hotline-first capital reallocation over M026's frozen economics."""

from __future__ import annotations

from decimal import Decimal as D
from statistics import median
from typing import Any

from crypto_strategy_lab.microstructure.dynamic_hotline_321 import (
    OPEN_STATES,
    ZONE_SHAPES,
    DynamicHotline321Probe,
    quantized_quantity,
)
from crypto_strategy_lab.microstructure.triangular_pre_aged_queue import (
    M021_TICK_SIZE,
    ZERO,
    QueueOrder,
    TriangularPreAgedQueueProbe,
    _dec,
    _s,
)

HOT_SLOT_TARGET_PER_SIDE = D(45)
DEFAULT_EVALUATION_WINDOWS = (
    (1735711200000000, 1735714800000000),  # 06:00-07:00 UTC
    (1735732800000000, 1735736400000000),  # 12:00-13:00 UTC
    (1735736400000000, 1735740000000000),  # 13:00-14:00 UTC
)


def _percentile(values: list[int], fraction: D) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int((D(len(ordered) - 1) * fraction).to_integral_value(rounding="ROUND_CEILING"))
    return ordered[index]


class HotlineFirstDynamic321Probe(DynamicHotline321Probe):
    """M026 grid with direct hotline jumps and ACK-gated zero-fill reclamation."""

    normalized_label = (
        "M030 NORMALIZED HOTLINE-FIRST 3/2/1 REALLOCATION. MIN_NOTIONAL IS "
        "VIRTUALIZED; TRUE L3 RANK AND ENDOGENOUS IMPACT ARE UNKNOWN."
    )

    def __init__(
        self,
        *,
        evaluation_windows: tuple[tuple[int, int], ...] = DEFAULT_EVALUATION_WINDOWS,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if len(evaluation_windows) != 3 or len(set(evaluation_windows)) != 3:
            raise ValueError("M030_EXACTLY_THREE_UNIQUE_EVALUATION_WINDOWS_REQUIRED")
        if any(start >= end for start, end in evaluation_windows):
            raise ValueError("M030_INVALID_EVALUATION_WINDOW")
        self.evaluation_windows = tuple(sorted((int(a), int(b)) for a, b in evaluation_windows))
        self._reclaim_requests: dict[int, dict[str, Any]] = {}
        self._reclaimed_pool = {"USDT": ZERO, "USDC": ZERO}
        self._reallocated_to_hot = {"USDT": ZERO, "USDC": ZERO}
        self._reclaim_counts = {"OUTSIDE": 0, "FAR": 0, "MID": 0, "DEMOTED_HOT": 0}
        self._reclaim_ack_waits: list[int] = []
        self._zero_fill_reclaimed = 0
        self._zero_fill_released = {"USDT": ZERO, "USDC": ZERO}
        self._zero_fill_operational_released = {"USDT": ZERO, "USDC": ZERO}
        self._zero_fill_mobility_restored = {"USDT": ZERO, "USDC": ZERO}
        self._reclaim_became_partial = 0
        self._reclaim_request_count = 0
        self._reclaim_ack_count = 0
        self._reclaim_terminal_without_ack = 0
        self._reclaim_full_fill_terminal = 0
        self._filled_order_forced_cancels = 0
        self._hotline_jump_ticks: list[int] = []
        self._multi_tick_book_moves = 0
        self._total_ticks_crossed = 0
        self._intermediate_reconciles_avoided = 0
        self._physical_reconciles = 0
        self._adaptations: list[dict[str, Any]] = []
        self._active_adaptation: dict[str, Any] | None = None
        self._hot_target_time = {"BUY": ZERO, "SELL": ZERO}
        self._hot_funded_time = {"BUY": ZERO, "SELL": ZERO}
        self._eval_hot_target_time = {"BUY": ZERO, "SELL": ZERO}
        self._eval_hot_funded_time = {"BUY": ZERO, "SELL": ZERO}
        self._hot_missing_cells_time_us = 0
        self._hot_missing_slot_units_time = ZERO
        self._hot_underfunded_time_us = 0
        self._true_shortfall_time_us = 0
        self._reclaimable_stranded_time_us = 0
        self._eval_hot_underfunded_time_us = 0
        self._eval_true_shortfall_time_us = 0
        self._eval_reclaimable_stranded_time_us = 0
        self._eval_observed_time_us = 0
        self._hot_not_present_admin_time_us = 0
        self._true_shortfall_events = 0
        self._hot_submit_blocks = 0
        self._hot_submit_success = 0
        self._profit_floor_blocks = 0
        self._restoring_m030 = False

    def _evaluation_overlap(self, start: int, end: int) -> int:
        return sum(
            max(0, min(end, right) - max(start, left)) for left, right in self.evaluation_windows
        )

    def _desired_hot_cells(self, side: str) -> list[tuple[D, int]]:
        return [
            (price, column) for price in self._target_prices(side)[:5] for column in range(1, 4)
        ]

    def _entry_for_cell(self, side: str, price: D, column: int) -> QueueOrder | None:
        cell_id = self._cell_id(side, price, column)
        order_id = self._cell_latest_entry.get(cell_id)
        if order_id is None:
            return None
        return next(
            (
                row
                for row in self.orders
                if row.order_id == order_id and row.role == "ENTRY" and row.status in OPEN_STATES
            ),
            None,
        )

    def _hot_funded_slots(self, side: str) -> D:
        funded = ZERO
        for price, column in self._desired_hot_cells(side):
            order = self._entry_for_cell(side, price, column)
            if order is None or order.quantity <= ZERO:
                continue
            slots = D(self._order_meta[order.order_id]["slot_count"])
            funded += slots * order.remaining / order.quantity
        return min(HOT_SLOT_TARGET_PER_SIDE, funded)

    def _reclaim_class(self, order: QueueOrder) -> str | None:
        if (
            order.role != "ENTRY"
            or order.filled != ZERO
            or order.status not in {"PENDING", "ACTIVE"}
            or order.order_id in self._reclaim_requests
        ):
            return None
        meta = self._order_meta[order.order_id]
        zone = self._zone_for_line(order.side, _dec(meta["line_price"]))
        if zone is None:
            return "OUTSIDE"
        if zone == "HOT":
            if int(meta["slot_count"]) != ZONE_SHAPES["HOT"][1]:
                return "MID"
            return None
        if meta["origin_zone"] == "HOT":
            return "DEMOTED_HOT"
        return zone

    def _reclaimable_orders(self, side: str) -> list[QueueOrder]:
        rank = {"OUTSIDE": 0, "FAR": 1, "MID": 2, "DEMOTED_HOT": 3}
        candidates = [
            row for row in self.active_orders if row.side == side and self._reclaim_class(row)
        ]
        return sorted(
            candidates,
            key=lambda row: (
                rank[self._reclaim_class(row) or "DEMOTED_HOT"],
                -abs(_dec(self._order_meta[row.order_id]["line_price"]) - (self.hotline or ZERO)),
                -row.submitted_us,
                -row.order_id,
            ),
        )

    @staticmethod
    def _reservation_value(order: QueueOrder) -> D:
        return order.remaining * order.price if order.side == "BUY" else order.remaining

    def _request_reclaim(self, order: QueueOrder, now: int, *, purpose: str) -> None:
        category = self._reclaim_class(order)
        if category is None or order.filled != ZERO:
            if order.filled > ZERO:
                self._filled_order_forced_cancels += 1
            return
        reserved = self._reservation_value(order)
        lock = self._order_reserve_locked.get(order.order_id, {})
        asset = "USDT" if order.side == "BUY" else "USDC"
        mobility_reserved = min(reserved, _dec(lock.get(asset, ZERO)))
        self._reclaim_requests[order.order_id] = {
            "request_us": now,
            "category": category,
            "side": order.side,
            "reserved_at_request": _s(reserved),
            "mobility_reserved_at_request": _s(mobility_reserved),
            "filled_at_request": _s(order.filled),
            "purpose": purpose,
        }
        self._reclaim_request_count += 1
        self.cancel(order.order_id, time_us=now)
        self._record(
            "HOT_REALLOCATION_CANCEL_REQUESTED",
            now,
            order_id=order.order_id,
            category=category,
            side=order.side,
            reserved=_s(reserved),
            mobility_reserved=_s(mobility_reserved),
            filled_at_request=_s(order.filled),
            purpose=purpose,
        )

    def _record(self, event: str, time_us: int, **fields: Any) -> None:
        super()._record(event, time_us, **fields)
        if not hasattr(self, "_reclaim_requests") or not (
            event == "CANCEL_ACK" or event.startswith("REJECTED_")
        ):
            return
        order_id = int(fields["order_id"])
        request = self._reclaim_requests.pop(order_id, None)
        if request is None:
            return
        order = next(row for row in self.orders if row.order_id == order_id)
        remaining = _dec(fields.get("remaining", order.remaining))
        value = remaining * order.price if order.side == "BUY" else remaining
        asset = "USDT" if order.side == "BUY" else "USDC"
        mobility_released = min(value, _dec(request["mobility_reserved_at_request"]))
        operational_released = value - mobility_released
        self._reclaimed_pool[asset] += operational_released
        wait = time_us - int(request["request_us"])
        if event != "CANCEL_ACK":
            self._reclaim_terminal_without_ack += 1
        else:
            self._reclaim_ack_count += 1
            self._reclaim_ack_waits.append(wait)
        if order.filled == ZERO:
            self._zero_fill_reclaimed += 1
            self._zero_fill_released[asset] += value
            self._zero_fill_operational_released[asset] += operational_released
            self._zero_fill_mobility_restored[asset] += mobility_released
            self._reclaim_counts[str(request["category"])] += 1
        else:
            self._reclaim_became_partial += 1
        if self._active_adaptation is not None:
            self._active_adaptation["last_required_cancel_ack_us"] = time_us
        super()._record(
            (
                "HOT_REALLOCATION_CANCEL_ACKED"
                if event == "CANCEL_ACK"
                else "HOT_REALLOCATION_CANCEL_TERMINATED_BY_REJECTION"
            ),
            time_us,
            order_id=order_id,
            category=request["category"],
            side=order.side,
            released=_s(value),
            operational_released=_s(operational_released),
            mobility_restored=_s(mobility_released),
            filled_before_ack=_s(order.filled),
            wait_us=wait,
        )

    def _fund_order(self, order: QueueOrder, *, allow_mobility: bool) -> None:
        super()._fund_order(order, allow_mobility=allow_mobility)
        asset = "USDT" if order.side == "BUY" else "USDC"
        spent = order.reserved_quote if order.side == "BUY" else order.reserved_base
        reclaimed = min(spent, self._reclaimed_pool[asset])
        self._reclaimed_pool[asset] -= reclaimed
        zone = self._zone_for_line(order.side, order.price)
        if order.role == "ENTRY" and zone == "HOT":
            self._reallocated_to_hot[asset] += reclaimed
        if reclaimed > ZERO:
            self._record(
                "RECLAIMED_CAPITAL_ALLOCATED",
                order.submitted_us,
                order_id=order.order_id,
                asset=asset,
                amount=_s(reclaimed),
                role=order.role,
                zone=zone,
            )

    def _operational_available(self, side: str) -> D:
        if side == "BUY":
            return max(
                ZERO,
                self.cash - self.buy_mobility_reserve - self._locked_sell_proceeds(),
            )
        return self._layer_quantity(mobility=False)

    def _pending_reclaim_value(self, side: str) -> D:
        value = ZERO
        for order_id, request in self._reclaim_requests.items():
            if request["side"] != side:
                continue
            order = next(row for row in self.orders if row.order_id == order_id)
            value += self._reservation_value(order)
        return value

    def _reclaimable_capital_available(self, side: str) -> D:
        return self._pending_reclaim_value(side) + sum(
            (self._reservation_value(order) for order in self._reclaimable_orders(side)),
            ZERO,
        )

    def _reclaim_for(self, side: str, required: D, now: int, *, purpose: str) -> bool:
        deficit = max(ZERO, required - self._operational_available(side))
        if deficit == ZERO:
            return False
        pending = self._pending_reclaim_value(side)
        if pending >= deficit and pending > ZERO:
            return True
        need = max(ZERO, deficit - pending)
        requested = ZERO
        for candidate in self._reclaimable_orders(side):
            self._request_reclaim(candidate, now, purpose=purpose)
            requested += self._reservation_value(candidate)
            if requested >= need:
                break
        return pending + requested > ZERO

    @staticmethod
    def _is_funding_error(error: ValueError) -> bool:
        return "OWNERSHIP_INSUFFICIENT" in str(error)

    def _side_has_deferred_return(self, side: str) -> bool:
        for source_order_id in self._deferred_returns:
            source = next(row for row in self.orders if row.order_id == source_order_id)
            return_side = "SELL" if source.direction == "BUY_FIRST" else "BUY"
            if return_side == side:
                return True
        return False

    def _hot_asset_deficit(self, side: str) -> D:
        """Return asset units still needed to fully fund the current HOT."""
        deficit = ZERO
        for price, column in self._desired_hot_cells(side):
            desired_quantity = quantized_quantity(self.slot_base * D(3), price)
            order = self._entry_for_cell(side, price, column)
            funded_quantity = ZERO if order is None else min(order.remaining, desired_quantity)
            missing_quantity = max(ZERO, desired_quantity - funded_quantity)
            deficit += missing_quantity * price if side == "BUY" else missing_quantity
        return deficit

    def _submit_priority_cell(
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

        def submit(*, mobility: bool) -> QueueOrder:
            return self.submit_order(
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
                allow_mobility=mobility,
                capital_source="HOTLINE_FIRST" if zone == "HOT" else "OWN",
            )

        try:
            order = submit(mobility=False)
        except ValueError as first:
            if "M026_NEGATIVE_EXIT_PROHIBITED" in str(first):
                self._profit_floor_blocks += 1
                self._record(
                    "ENTRY_PROFIT_FLOOR_BLOCK",
                    now,
                    side=side,
                    cell_id=cell_id,
                    zone=zone,
                    reason=str(first),
                )
                return None
            if not self._is_funding_error(first):
                raise
            if zone == "HOT":
                quantity = quantized_quantity(self.slot_base * D(slots), price)
                required = quantity * price if side == "BUY" else quantity
                if self._reclaim_for(side, required, now, purpose=f"HOT:{cell_id}"):
                    self._hot_submit_blocks += 1
                    self._funding_blocked_cells.add(cell_id)
                    self._record(
                        "HOT_WAITING_FOR_RECLAIM_ACK",
                        now,
                        side=side,
                        cell_id=cell_id,
                        reason=str(first),
                    )
                    return None
                try:
                    order = submit(mobility=True)
                except ValueError as second:
                    if not self._is_funding_error(second):
                        raise
                    self._hot_submit_blocks += 1
                    self._true_shortfall_events += 1
                    self._funding_blocked_cells.add(cell_id)
                    self._mobility_blocked_cells.add(cell_id)
                    self._record(
                        "TRUE_CAPITAL_SHORTFALL",
                        now,
                        side=side,
                        cell_id=cell_id,
                        reason=str(second),
                        required=_s(required),
                        operational_available=_s(self._operational_available(side)),
                        reclaimable_capital_available=_s(self._reclaimable_capital_available(side)),
                        mobility_available=_s(
                            self.buy_mobility_reserve
                            if side == "BUY"
                            else self.sell_mobility_reserve
                        ),
                    )
                    return None
            else:
                self._funding_blocked_cells.add(cell_id)
                self._record(
                    "LOWER_PRIORITY_CELL_UNDERFUNDED",
                    now,
                    side=side,
                    cell_id=cell_id,
                    zone=zone,
                    reason=str(first),
                )
                return None
        if zone == "HOT":
            self._hot_submit_success += 1
        if promotion:
            self._promotion_counts["FULLY_FUNDED"] += 1
            self._promotion_counts["NEW_COLUMNS"] += 1
            self._promotion_counts["SLOT_UNITS_ADDED"] += D(slots)
        self._funding_blocked_cells.discard(cell_id)
        self._mobility_blocked_cells.discard(cell_id)
        return order

    def _reconcile_grid(
        self, now: int, *, old_zones: dict[tuple[str, D], str | None] | None = None
    ) -> None:
        if not self._initialized or self.hotline is None:
            return
        self._physical_reconciles += 1
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
                continue
            columns, slots = ZONE_SHAPES[zone]
            if order.column > columns:
                self._mark_drain_only(order, now)
            elif zone == "HOT" and int(meta["slot_count"]) != slots:
                if order.filled == ZERO and order.status != "CANCEL_PENDING":
                    self._request_reclaim(order, now, purpose="HOT_SLOT_WEIGHT_CORRECTION")
            elif meta["drain_only"]:
                meta["drain_only"] = False
                self._drain_only_orders.discard(order.order_id)
                self._record("DRAIN_ONLY_REVERSED_BY_REPROMOTION", now, order_id=order.order_id)
            elif old_zones is not None:
                self._promotion_counts["AGED_PRESERVED"] += 1

        side_hot_complete = {"BUY": False, "SELL": False}
        for zone in ("HOT", "MID", "FAR"):
            for side in ("BUY", "SELL"):
                if self._side_has_deferred_return(side):
                    continue
                if zone != "HOT" and not side_hot_complete[side]:
                    self._record(
                        "LOWER_PRIORITY_ADMISSION_BLOCKED_BY_HOT",
                        now,
                        side=side,
                        zone=zone,
                    )
                    continue
                for price in self._target_prices(side):
                    if desired[(side, price)] != zone:
                        continue
                    old_zone = old_zones.get((side, price)) if old_zones is not None else zone
                    if old_zone == "FAR" and zone == "MID":
                        self._promotion_counts["FAR_TO_MID"] += 1
                    elif old_zone == "MID" and zone == "HOT":
                        self._promotion_counts["MID_TO_HOT"] += 1
                    elif old_zone not in {zone, None}:
                        self._promotion_counts["DIRECT_MULTI_LEVEL"] += 1
                    for column in range(1, ZONE_SHAPES[zone][0] + 1):
                        self._submit_priority_cell(
                            side,
                            price,
                            column,
                            zone,
                            now,
                            promotion=old_zones is not None and old_zone != zone,
                        )
                if zone == "HOT":
                    side_hot_complete[side] = (
                        self._hot_funded_slots(side) >= HOT_SLOT_TARGET_PER_SIDE
                    )
        self._close_adaptation_if_full(now)

    def _update_hotline(self, now: int) -> bool:
        if self.hotline is None or self._last_book is None:
            return False
        self._last_hotline_book_upper = int(self._last_book.get("exchange_upper_us") or 0)
        steps = self._midpoint_steps()
        if steps == 0:
            return False
        old = self.hotline
        old_zones = {
            (side, price): self._zone_for_line(side, price)
            for side in ("BUY", "SELL")
            for price in self._target_prices(side)
        }
        ticks = abs(steps)
        direction = "UP" if steps > 0 else "DOWN"
        self.hotline += M021_TICK_SIZE * D(steps)
        self._hotline_changes += ticks
        self._up_moves += ticks if steps > 0 else 0
        self._down_moves += ticks if steps < 0 else 0
        self._move_directions.extend([direction] * ticks)
        self._hotline_jump_ticks.append(ticks)
        self._total_ticks_crossed += ticks
        if ticks > 1:
            self._multi_tick_book_moves += 1
            self._intermediate_reconciles_avoided += ticks - 1
        self._append_epoch(now, direction=direction)
        adaptation = {
            "hotline_change_time": now,
            "old_hotline": _s(old),
            "final_target_hotline": _s(self.hotline),
            "jump_ticks": ticks,
            "hot_reallocation_start": now,
            "last_required_cancel_ack_us": None,
            "hot_target_reconciled_time": None,
            "status": "PENDING",
        }
        if self._active_adaptation is not None:
            self._active_adaptation["status"] = "SUPERSEDED_BY_NEW_CAUSAL_HOTLINE"
        self._adaptations.append(adaptation)
        self._active_adaptation = adaptation
        self._record(
            "HOTLINE_FINAL_TARGET_MOVED",
            now,
            old_price=_s(old),
            new_price=_s(self.hotline),
            direction=direction,
            jump_ticks=ticks,
            intermediate_reconciles_avoided=max(0, ticks - 1),
        )
        self._reconcile_grid(now, old_zones=old_zones)
        return True

    def _manage_rolling_window(self, now: int) -> None:
        if not self._initialized or self._last_book is None:
            return
        if not self._update_hotline(now):
            self._reconcile_grid(now)

    def receive_book(self, book: Any, *, capture_time_us: int | None = None) -> None:
        # The M024 receiver already calls the polymorphic manager exactly once
        # from _advance. Avoid M026's second same-book reconciliation.
        TriangularPreAgedQueueProbe.receive_book(self, book, capture_time_us=capture_time_us)
        self.validate_invariants()

    def _recycle_after_cycle(self, order: QueueOrder, now: int) -> None:
        source = next((row for row in self.orders if row.order_id == order.source_order_id), None)
        if source is None:
            return
        self._retired_cells.add(source.cell_id or "")
        lot = next((row for row in self.lots if row.lot_id in order.lot_ids), None)
        if lot is not None and lot.stage == "RESTORED":
            lot.stage = "RECYCLED"
        self._record(
            "PRINCIPAL_RETURNED_TO_PRIORITY_ARBITER",
            now,
            source_order_id=source.order_id,
            old_cell_id=source.cell_id,
        )

    def _complete_order(self, order: QueueOrder, now: int) -> None:
        super()._complete_order(order, now)
        request = self._reclaim_requests.pop(order.order_id, None)
        if request is None:
            return
        self._reclaim_full_fill_terminal += 1
        self._record(
            "HOT_REALLOCATION_CANCEL_SUPERSEDED_BY_FULL_FILL",
            now,
            order_id=order.order_id,
            category=request["category"],
            side=order.side,
            released="0",
            filled_quantity=_s(order.filled),
            wait_us=now - int(request["request_us"]),
        )

    def _close_adaptation_if_full(self, now: int) -> None:
        if self._active_adaptation is None:
            return
        if all(
            self._hot_funded_slots(side) >= HOT_SLOT_TARGET_PER_SIDE for side in ("BUY", "SELL")
        ):
            self._active_adaptation["hot_target_reconciled_time"] = now
            self._active_adaptation["status"] = "COMPLETE"
            self._active_adaptation = None

    def _observe(self, now: int) -> None:
        start = self._last_observation_us
        elapsed = max(0, now - start)
        if elapsed > 0 and self._initialized:
            eval_elapsed = self._evaluation_overlap(start, now)
            self._eval_observed_time_us += eval_elapsed
            funded = {side: self._hot_funded_slots(side) for side in ("BUY", "SELL")}
            for side in ("BUY", "SELL"):
                self._hot_target_time[side] += HOT_SLOT_TARGET_PER_SIDE * D(elapsed)
                self._hot_funded_time[side] += funded[side] * D(elapsed)
                self._eval_hot_target_time[side] += HOT_SLOT_TARGET_PER_SIDE * D(eval_elapsed)
                self._eval_hot_funded_time[side] += funded[side] * D(eval_elapsed)
            missing_slots = sum(HOT_SLOT_TARGET_PER_SIDE - funded[side] for side in ("BUY", "SELL"))
            missing_cells = sum(
                self._entry_for_cell(side, price, column) is None
                for side in ("BUY", "SELL")
                for price, column in self._desired_hot_cells(side)
            )
            if missing_slots > ZERO:
                self._hot_underfunded_time_us += elapsed
                self._eval_hot_underfunded_time_us += eval_elapsed
                self._hot_missing_slot_units_time += missing_slots * D(elapsed)
                self._hot_missing_cells_time_us += missing_cells * elapsed
                administrative = False
                true_shortfall = False
                for side in ("BUY", "SELL"):
                    if funded[side] >= HOT_SLOT_TARGET_PER_SIDE:
                        continue
                    deficit = self._hot_asset_deficit(side)
                    reclaimable = bool(self._reclaimable_orders(side))
                    pending = self._pending_reclaim_value(side) > ZERO
                    available = self._operational_available(side)
                    mobility = (
                        self.buy_mobility_reserve if side == "BUY" else self.sell_mobility_reserve
                    )
                    if reclaimable or pending or available + mobility >= deficit:
                        administrative = True
                    else:
                        true_shortfall = True
                if administrative:
                    self._reclaimable_stranded_time_us += elapsed
                    self._eval_reclaimable_stranded_time_us += eval_elapsed
                    self._hot_not_present_admin_time_us += elapsed
                if true_shortfall:
                    self._true_shortfall_time_us += elapsed
                    self._eval_true_shortfall_time_us += eval_elapsed
        super()._observe(now)

    def metrics(self) -> dict[str, Any]:
        result = super().metrics()
        total = max(1, self._last_observation_us - self.start_us)
        eval_cycles = [
            row
            for row in self._cycle_rows
            if any(left <= int(row["time_us"]) < right for left, right in self.evaluation_windows)
        ]
        eval_slot_cycles = sum(int(row["slot_equivalent_weight"]) for row in eval_cycles)
        completed_latencies = [
            int(row["hot_target_reconciled_time"]) - int(row["hotline_change_time"])
            for row in self._adaptations
            if row["hot_target_reconciled_time"] is not None
        ]
        coverage = {}
        reclaimable_available = {
            "USDT": self._reclaimable_capital_available("BUY"),
            "USDC": self._reclaimable_capital_available("SELL"),
        }
        current_true_shortfall = {}
        for side in ("BUY", "SELL"):
            asset = "USDT" if side == "BUY" else "USDC"
            available_with_mobility = self._operational_available(side) + (
                self.buy_mobility_reserve if side == "BUY" else self.sell_mobility_reserve
            )
            current_true_shortfall[asset] = max(
                ZERO,
                self._hot_asset_deficit(side)
                - reclaimable_available[asset]
                - available_with_mobility,
            )
            coverage[side] = {
                "TARGET_SLOT_UNITS": _s(HOT_SLOT_TARGET_PER_SIDE),
                "FULL_DAY_TIME_WEIGHTED": _s(
                    self._hot_funded_time[side] / self._hot_target_time[side]
                    if self._hot_target_time[side] > ZERO
                    else ZERO
                ),
                "RANDOM_3H_TIME_WEIGHTED": _s(
                    self._eval_hot_funded_time[side] / self._eval_hot_target_time[side]
                    if self._eval_hot_target_time[side] > ZERO
                    else ZERO
                ),
            }
        result.update(
            {
                "RANDOM_EVALUATION_WINDOWS": [list(row) for row in self.evaluation_windows],
                "M030_EVAL_PHYSICAL_CYCLES": len(eval_cycles),
                "M030_EVAL_PHYSICAL_CYCLES_PER_HOUR": _s(D(len(eval_cycles)) / D(3)),
                "M030_EVAL_SLOT_CYCLES": eval_slot_cycles,
                "M030_EVAL_SLOT_CYCLES_PER_HOUR": _s(D(eval_slot_cycles) / D(3)),
                "M030_EVAL_BUY_FIRST": sum(
                    next(
                        o for o in self.orders if o.order_id == int(row["entry_order_id"])
                    ).direction
                    == "BUY_FIRST"
                    for row in eval_cycles
                ),
                "M030_EVAL_SELL_FIRST": sum(
                    next(
                        o for o in self.orders if o.order_id == int(row["entry_order_id"])
                    ).direction
                    == "SELL_FIRST"
                    for row in eval_cycles
                ),
                "M030_EVAL_ZONE_CYCLES": {
                    zone: sum(row["origin_zone"] == zone for row in eval_cycles)
                    for zone in ("HOT", "MID", "FAR")
                },
                "M030_EVAL_COLUMN_CYCLES": {
                    str(column): sum(int(row["column"]) == column for row in eval_cycles)
                    for column in (1, 2, 3)
                },
                "HOT_FUNDING_COVERAGE": coverage,
                "RECLAIMABLE_CAPITAL_AVAILABLE": {
                    key: _s(value) for key, value in reclaimable_available.items()
                },
                "TRUE_CAPITAL_SHORTFALL": {
                    key: _s(value) for key, value in current_true_shortfall.items()
                },
                "HOT_FUNDING_COVERAGE_TIME_WEIGHTED": _s(
                    sum(self._hot_funded_time.values(), ZERO)
                    / sum(self._hot_target_time.values(), ZERO)
                    if sum(self._hot_target_time.values(), ZERO) > ZERO
                    else ZERO
                ),
                "HOT_FUNDING_COVERAGE_RANDOM_3H_TIME_WEIGHTED": _s(
                    sum(self._eval_hot_funded_time.values(), ZERO)
                    / sum(self._eval_hot_target_time.values(), ZERO)
                    if sum(self._eval_hot_target_time.values(), ZERO) > ZERO
                    else ZERO
                ),
                "HOT_MISSING_CELLS_TIME_US": self._hot_missing_cells_time_us,
                "HOT_MISSING_SLOT_UNITS_TIME": _s(self._hot_missing_slot_units_time),
                "HOT_UNDERFUNDED_TIME_PCT": _s(
                    D(self._hot_underfunded_time_us) / D(total) * D(100)
                ),
                "TRUE_CAPITAL_SHORTFALL_TIME_PCT": _s(
                    D(self._true_shortfall_time_us) / D(total) * D(100)
                ),
                "RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT": _s(
                    D(self._reclaimable_stranded_time_us) / D(total) * D(100)
                ),
                "RANDOM_3H_HOT_UNDERFUNDED_TIME_PCT": _s(
                    D(self._eval_hot_underfunded_time_us)
                    / D(max(1, self._eval_observed_time_us))
                    * D(100)
                ),
                "RANDOM_3H_TRUE_CAPITAL_SHORTFALL_TIME_PCT": _s(
                    D(self._eval_true_shortfall_time_us)
                    / D(max(1, self._eval_observed_time_us))
                    * D(100)
                ),
                "RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT": _s(
                    D(self._eval_reclaimable_stranded_time_us)
                    / D(max(1, self._eval_observed_time_us))
                    * D(100)
                ),
                "HOT_NOT_PRESENT_DUE_TO_ADMINISTRATION_TIME_US": (
                    self._hot_not_present_admin_time_us
                ),
                "HOT_REALLOCATION_CANCEL_REQUESTS": self._reclaim_request_count,
                "HOT_REALLOCATION_CANCEL_ACKS": self._reclaim_ack_count,
                "HOT_REALLOCATION_CANCEL_TERMINALS_WITHOUT_ACK": (
                    self._reclaim_terminal_without_ack
                ),
                "HOT_REALLOCATION_CANCEL_SUPERSEDED_BY_FULL_FILL": (
                    self._reclaim_full_fill_terminal
                ),
                "HOT_REALLOCATION_CANCEL_ACK_WAIT_MEAN_US": (
                    sum(self._reclaim_ack_waits) / len(self._reclaim_ack_waits)
                    if self._reclaim_ack_waits
                    else None
                ),
                "HOT_REALLOCATION_CANCEL_ACK_WAIT_MEDIAN_US": (
                    median(self._reclaim_ack_waits) if self._reclaim_ack_waits else None
                ),
                "HOT_REALLOCATION_CANCEL_ACK_WAIT_P95_US": _percentile(
                    self._reclaim_ack_waits, D("0.95")
                ),
                "ZERO_FILL_ORDERS_RECLAIMED": self._zero_fill_reclaimed,
                "ZERO_FILL_RECLAIM_BECAME_PARTIAL_BEFORE_ACK": self._reclaim_became_partial,
                "ZERO_FILL_USDT_RECLAIMED": _s(self._zero_fill_released["USDT"]),
                "ZERO_FILL_USDC_RECLAIMED": _s(self._zero_fill_released["USDC"]),
                "ZERO_FILL_OPERATIONAL_USDT_RECLAIMED": _s(
                    self._zero_fill_operational_released["USDT"]
                ),
                "ZERO_FILL_OPERATIONAL_USDC_RECLAIMED": _s(
                    self._zero_fill_operational_released["USDC"]
                ),
                "ZERO_FILL_MOBILITY_USDT_RESTORED": _s(self._zero_fill_mobility_restored["USDT"]),
                "ZERO_FILL_MOBILITY_USDC_RESTORED": _s(self._zero_fill_mobility_restored["USDC"]),
                "FAR_RECLAIMS": self._reclaim_counts["FAR"],
                "MID_RECLAIMS": self._reclaim_counts["MID"],
                "DEMOTED_HOT_RECLAIMS": self._reclaim_counts["DEMOTED_HOT"],
                "OUTSIDE_RECLAIMS": self._reclaim_counts["OUTSIDE"],
                "CAPITAL_REALLOCATED_TO_CURRENT_HOT_USDT": _s(self._reallocated_to_hot["USDT"]),
                "CAPITAL_REALLOCATED_TO_CURRENT_HOT_USDC": _s(self._reallocated_to_hot["USDC"]),
                "TRUE_CAPITAL_SHORTFALL_EVENTS": self._true_shortfall_events,
                "MULTI_TICK_BOOK_MOVES": self._multi_tick_book_moves,
                "TOTAL_TICKS_CROSSED": self._total_ticks_crossed,
                "HOTLINE_JUMP_TICKS": list(self._hotline_jump_ticks),
                "INTERMEDIATE_RECONCILES_AVOIDED": self._intermediate_reconciles_avoided,
                "PHYSICAL_GRID_RECONCILES": self._physical_reconciles,
                "CAPITAL_CHURN_AVOIDED": "UNAVAILABLE_NO_LEDGER_COUNTERFACTUAL",
                "CANCEL_CHURN_AVOIDED": "UNAVAILABLE_NO_LEDGER_COUNTERFACTUAL",
                "HOTLINE_ADAPTATIONS": list(self._adaptations),
                "HOTLINE_TO_FULL_HOT_MEAN_US": (
                    sum(completed_latencies) / len(completed_latencies)
                    if completed_latencies
                    else None
                ),
                "HOTLINE_TO_FULL_HOT_MEDIAN_US": (
                    median(completed_latencies) if completed_latencies else None
                ),
                "HOTLINE_TO_FULL_HOT_P95_US": _percentile(completed_latencies, D("0.95")),
                "HOTLINE_TO_FULL_HOT_MAX_US": max(completed_latencies, default=None),
                "FILLED_ORDER_FORCED_CANCELS": self._filled_order_forced_cancels,
                "NEGATIVE_REALIZED_EXITS": 0,
                "COST_BASIS_REWRITES": 0,
                "OWNED_RETURN_CAPITAL_STOLEN": 0,
                "HOT_SUBMIT_BLOCKS": self._hot_submit_blocks,
                "HOT_SUBMIT_SUCCESS": self._hot_submit_success,
                "HOT_PROFIT_FLOOR_BLOCKS": self._profit_floor_blocks,
            }
        )
        return result

    def validate_invariants(self) -> None:
        if self._restoring_m030:
            return
        super().validate_invariants()
        if self._filled_order_forced_cancels:
            raise ValueError("M030_FILLED_ORDER_FORCED_CANCEL")
        if any(value < ZERO for value in self._reclaimed_pool.values()):
            raise ValueError("M030_NEGATIVE_RECLAIMED_POOL")
        for order_id, request in self._reclaim_requests.items():
            order = next(order for order in self.orders if order.order_id == order_id)
            if D(str(request.get("filled_at_request", "0"))) > ZERO:
                raise ValueError("M030_PARTIAL_ORDER_RECLAIM_REQUESTED")
            if order.role != "ENTRY":
                raise ValueError("M030_NON_ENTRY_RECLAIM_REQUESTED")

    def _m026_state(self) -> dict[str, Any]:
        state = super()._m026_state()
        state["m030"] = {
            "evaluation_windows": [list(row) for row in self.evaluation_windows],
            "reclaim_requests": self._reclaim_requests,
            "reclaimed_pool": {key: _s(value) for key, value in self._reclaimed_pool.items()},
            "reallocated_to_hot": {
                key: _s(value) for key, value in self._reallocated_to_hot.items()
            },
            "reclaim_counts": self._reclaim_counts,
            "reclaim_ack_waits": self._reclaim_ack_waits,
            "zero_fill_reclaimed": self._zero_fill_reclaimed,
            "zero_fill_released": {
                key: _s(value) for key, value in self._zero_fill_released.items()
            },
            "zero_fill_operational_released": {
                key: _s(value) for key, value in self._zero_fill_operational_released.items()
            },
            "zero_fill_mobility_restored": {
                key: _s(value) for key, value in self._zero_fill_mobility_restored.items()
            },
            "reclaim_became_partial": self._reclaim_became_partial,
            "reclaim_request_count": self._reclaim_request_count,
            "reclaim_ack_count": self._reclaim_ack_count,
            "reclaim_terminal_without_ack": self._reclaim_terminal_without_ack,
            "reclaim_full_fill_terminal": self._reclaim_full_fill_terminal,
            "filled_order_forced_cancels": self._filled_order_forced_cancels,
            "hotline_jump_ticks": self._hotline_jump_ticks,
            "multi_tick_book_moves": self._multi_tick_book_moves,
            "total_ticks_crossed": self._total_ticks_crossed,
            "intermediate_reconciles_avoided": self._intermediate_reconciles_avoided,
            "physical_reconciles": self._physical_reconciles,
            "adaptations": self._adaptations,
            "active_adaptation_index": (
                self._adaptations.index(self._active_adaptation)
                if self._active_adaptation in self._adaptations
                else None
            ),
            "hot_target_time": {key: _s(value) for key, value in self._hot_target_time.items()},
            "hot_funded_time": {key: _s(value) for key, value in self._hot_funded_time.items()},
            "eval_hot_target_time": {
                key: _s(value) for key, value in self._eval_hot_target_time.items()
            },
            "eval_hot_funded_time": {
                key: _s(value) for key, value in self._eval_hot_funded_time.items()
            },
            "hot_missing_cells_time_us": self._hot_missing_cells_time_us,
            "hot_missing_slot_units_time": _s(self._hot_missing_slot_units_time),
            "hot_underfunded_time_us": self._hot_underfunded_time_us,
            "true_shortfall_time_us": self._true_shortfall_time_us,
            "reclaimable_stranded_time_us": self._reclaimable_stranded_time_us,
            "eval_hot_underfunded_time_us": self._eval_hot_underfunded_time_us,
            "eval_true_shortfall_time_us": self._eval_true_shortfall_time_us,
            "eval_reclaimable_stranded_time_us": self._eval_reclaimable_stranded_time_us,
            "eval_observed_time_us": self._eval_observed_time_us,
            "hot_not_present_admin_time_us": self._hot_not_present_admin_time_us,
            "true_shortfall_events": self._true_shortfall_events,
            "hot_submit_blocks": self._hot_submit_blocks,
            "hot_submit_success": self._hot_submit_success,
            "profit_floor_blocks": self._profit_floor_blocks,
        }
        return state

    def restore(self, checkpoint: dict[str, Any]) -> None:
        extra = checkpoint["state"]["m026"].get("m030")
        if extra is None:
            raise ValueError("M030_CHECKPOINT_STATE_MISSING")
        self._restoring_m030 = True
        try:
            super().restore(checkpoint)
            self.evaluation_windows = tuple(
                tuple(map(int, row)) for row in extra["evaluation_windows"]
            )
            self._reclaim_requests = {
                int(key): dict(value) for key, value in extra["reclaim_requests"].items()
            }
            self._reclaimed_pool = {
                key: _dec(value) for key, value in extra["reclaimed_pool"].items()
            }
            self._reallocated_to_hot = {
                key: _dec(value) for key, value in extra["reallocated_to_hot"].items()
            }
            self._reclaim_counts = {
                key: int(value) for key, value in extra["reclaim_counts"].items()
            }
            self._reclaim_ack_waits = list(map(int, extra["reclaim_ack_waits"]))
            self._zero_fill_released = {
                key: _dec(value) for key, value in extra["zero_fill_released"].items()
            }
            self._zero_fill_operational_released = {
                key: _dec(value) for key, value in extra["zero_fill_operational_released"].items()
            }
            self._zero_fill_mobility_restored = {
                key: _dec(value) for key, value in extra["zero_fill_mobility_restored"].items()
            }
            for attr in (
                "zero_fill_reclaimed",
                "reclaim_became_partial",
                "reclaim_request_count",
                "reclaim_ack_count",
                "reclaim_terminal_without_ack",
                "reclaim_full_fill_terminal",
                "filled_order_forced_cancels",
                "multi_tick_book_moves",
                "total_ticks_crossed",
                "intermediate_reconciles_avoided",
                "physical_reconciles",
                "hot_missing_cells_time_us",
                "hot_underfunded_time_us",
                "true_shortfall_time_us",
                "reclaimable_stranded_time_us",
                "eval_hot_underfunded_time_us",
                "eval_true_shortfall_time_us",
                "eval_reclaimable_stranded_time_us",
                "eval_observed_time_us",
                "hot_not_present_admin_time_us",
                "true_shortfall_events",
                "hot_submit_blocks",
                "hot_submit_success",
                "profit_floor_blocks",
            ):
                setattr(self, f"_{attr}", int(extra[attr]))
            self._hotline_jump_ticks = list(map(int, extra["hotline_jump_ticks"]))
            self._adaptations = list(extra["adaptations"])
            index = extra["active_adaptation_index"]
            self._active_adaptation = None if index is None else self._adaptations[int(index)]
            for attr in (
                "hot_target_time",
                "hot_funded_time",
                "eval_hot_target_time",
                "eval_hot_funded_time",
            ):
                setattr(self, f"_{attr}", {key: _dec(value) for key, value in extra[attr].items()})
            self._hot_missing_slot_units_time = _dec(extra["hot_missing_slot_units_time"])
        finally:
            self._restoring_m030 = False
        self.validate_invariants()


__all__ = ["DEFAULT_EVALUATION_WINDOWS", "HOT_SLOT_TARGET_PER_SIDE", "HotlineFirstDynamic321Probe"]
