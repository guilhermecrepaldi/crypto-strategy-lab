"""Global, exact multi-asset ownership ledger for the draft M032 architecture."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from crypto_strategy_lab.microstructure.multi_stable_models import (
    ZERO,
    D,
    EconomicSlot,
    InventoryReductionAuthorization,
    PhysicalFill,
    SlotState,
)


@dataclass
class CapitalReservation:
    reservation_id: str
    slot_id: str
    asset: str
    quantity: D
    remaining: D
    created_at_us: int
    cancel_requested_at_us: int | None = None
    cancel_ack_at_us: int | None = None


@dataclass(frozen=True)
class FillAttribution:
    reservation_id: str
    reservation_created_at_us: int
    slot_id: str
    fill: PhysicalFill


class SlotLedger:
    """Own every asset unit in exactly one FREE, RESERVED or OWNED bucket."""

    def __init__(self, balances: dict[str, D | str], *, marks_usd: dict[str, D | str]) -> None:
        self.free = {asset: D(str(value)) for asset, value in balances.items()}
        self._asset_totals = dict(self.free)
        self.marks_usd = {asset: D(str(value)) for asset, value in marks_usd.items()}
        if set(self.free) != set(self.marks_usd):
            raise ValueError("M032_MARK_SET_MISMATCH")
        if any(value < ZERO for value in self.free.values()):
            raise ValueError("M032_NEGATIVE_INITIAL_BALANCE")
        self.slots: dict[str, EconomicSlot] = {}
        self.reservations: dict[str, CapitalReservation] = {}
        self.owned: dict[str, dict[str, D]] = {}
        self.initial_equity = self.marked_equity()
        if self.initial_equity > D("200"):
            raise ValueError("M032_MAX_BANKROLL_EXCEEDED")
        self.processed_fill_ids: set[str] = set()
        self.fill_attribution: dict[str, FillAttribution] = {}
        self.turnover_us: list[int] = []
        self.inventory_reduction_turnover_us: list[int] = []
        self.inventory_reduction_authorizations: dict[
            str, InventoryReductionAuthorization
        ] = {}
        self.processed_inventory_authorization_ids: set[str] = set()
        self.negative_exit_count = 0
        self.negative_exit_cost = ZERO
        self.realized_pnl_by_asset: dict[str, D] = {asset: ZERO for asset in self.free}
        self.audit: list[dict[str, object]] = []
        self.last_event_us = -1

    def _causal(self, now_us: int) -> None:
        if now_us < self.last_event_us:
            raise ValueError("M032_NONCAUSAL_LEDGER_EVENT")

    def _commit_time(self, now_us: int) -> None:
        self.last_event_us = now_us

    def create_slot(
        self,
        slot_id: str,
        *,
        origin_asset: str,
        usd_equivalent: D,
        now_us: int,
        slot_epoch: int = 1,
    ) -> EconomicSlot:
        self._causal(now_us)
        if slot_id in self.slots:
            raise ValueError("M032_DUPLICATE_SLOT_ID")
        if origin_asset not in self.free or usd_equivalent <= ZERO:
            raise ValueError("M032_INVALID_SLOT_ORIGIN")
        slot = EconomicSlot(
            slot_id=slot_id,
            slot_epoch=slot_epoch,
            origin_asset=origin_asset,
            current_asset=origin_asset,
            initial_usd_equivalent=usd_equivalent,
            current_marked_value=usd_equivalent,
            created_at_us=now_us,
        )
        self.slots[slot_id] = slot
        self.owned[slot_id] = {}
        self._commit_time(now_us)
        return slot

    def reserve_free(
        self,
        slot_id: str,
        reservation_id: str,
        *,
        asset: str,
        quantity: D,
        now_us: int,
    ) -> CapitalReservation:
        self._causal(now_us)
        slot = self.slots[slot_id]
        if reservation_id in self.reservations or slot.reservation_id is not None:
            raise ValueError("M032_RESERVATION_ALREADY_OWNED")
        if quantity <= ZERO or self.free.get(asset, ZERO) < quantity:
            raise ValueError("M032_FREE_CAPITAL_INSUFFICIENT")
        self.free[asset] -= quantity
        return self._create_reservation(slot, reservation_id, asset, quantity, now_us)

    def reserve_owned(
        self,
        slot_id: str,
        reservation_id: str,
        *,
        asset: str,
        quantity: D,
        now_us: int,
    ) -> CapitalReservation:
        self._causal(now_us)
        slot = self.slots[slot_id]
        if reservation_id in self.reservations or slot.reservation_id is not None:
            raise ValueError("M032_RESERVATION_ALREADY_OWNED")
        if quantity <= ZERO or self.owned[slot_id].get(asset, ZERO) < quantity:
            raise ValueError("M032_OWNED_CAPITAL_INSUFFICIENT")
        self.owned[slot_id][asset] -= quantity
        return self._create_reservation(slot, reservation_id, asset, quantity, now_us)

    def _create_reservation(
        self,
        slot: EconomicSlot,
        reservation_id: str,
        asset: str,
        quantity: D,
        now_us: int,
    ) -> CapitalReservation:
        reservation = CapitalReservation(
            reservation_id, slot.slot_id, asset, quantity, quantity, now_us
        )
        self.reservations[reservation_id] = reservation
        slot.reservation_id = reservation_id
        slot.current_asset = asset
        slot.reserved_value = quantity
        slot.remaining_qty = quantity
        slot.state = SlotState.RESERVED
        if slot.capital_lock_started_at_us is None:
            slot.capital_lock_started_at_us = now_us
        self.audit.append(
            {
                "event": "RESERVE",
                "time_us": now_us,
                "slot_id": slot.slot_id,
                "reservation_id": reservation_id,
                "asset": asset,
                "quantity": str(quantity),
            }
        )
        self._commit_time(now_us)
        self.reconcile()
        return reservation

    def activate(self, reservation_id: str, *, now_us: int) -> None:
        self._causal(now_us)
        reservation = self.reservations[reservation_id]
        slot = self.slots[reservation.slot_id]
        if slot.state != SlotState.RESERVED or reservation.cancel_requested_at_us is not None:
            raise ValueError("M032_INVALID_ACTIVATION_LIFECYCLE")
        slot.state = SlotState.LIVE
        slot.activated_at_us = now_us
        self.audit.append(
            {
                "event": "ACTIVATE",
                "time_us": now_us,
                "slot_id": slot.slot_id,
                "reservation_id": reservation_id,
            }
        )
        self._commit_time(now_us)

    def request_cancel(self, reservation_id: str, *, now_us: int) -> None:
        self._causal(now_us)
        reservation = self.reservations[reservation_id]
        slot = self.slots[reservation.slot_id]
        if slot.filled_qty > ZERO:
            raise ValueError("M032_PARTIAL_OR_FILLED_NOT_RECLAIMABLE")
        if reservation.cancel_requested_at_us is not None:
            raise ValueError("M032_DUPLICATE_CANCEL_REQUEST")
        reservation.cancel_requested_at_us = now_us
        slot.state = SlotState.CANCEL_PENDING
        self.audit.append(
            {
                "event": "CANCEL_REQUEST",
                "time_us": now_us,
                "reservation_id": reservation_id,
                "slot_id": slot.slot_id,
            }
        )
        self._commit_time(now_us)

    def acknowledge_cancel(self, reservation_id: str, *, now_us: int) -> D:
        self._causal(now_us)
        reservation = self.reservations[reservation_id]
        slot = self.slots[reservation.slot_id]
        if reservation.cancel_requested_at_us is None:
            raise ValueError("M032_CANCEL_ACK_WITHOUT_REQUEST")
        if now_us < reservation.cancel_requested_at_us:
            raise ValueError("M032_CANCEL_ACK_BEFORE_REQUEST")
        released = reservation.remaining
        self.free[reservation.asset] += released
        reservation.remaining = ZERO
        reservation.cancel_ack_at_us = now_us
        slot.reservation_id = None
        slot.reserved_value = ZERO
        slot.remaining_qty = ZERO
        slot.state = SlotState.FILLED if slot.filled_qty > ZERO else SlotState.FREE
        self.audit.append(
            {
                "event": "CANCEL_ACK",
                "time_us": now_us,
                "reservation_id": reservation_id,
                "slot_id": slot.slot_id,
                "released": str(released),
            }
        )
        del self.reservations[reservation_id]
        self._commit_time(now_us)
        self.reconcile()
        return released

    def apply_fill(self, reservation_id: str, fill: PhysicalFill) -> None:
        self._causal(fill.time_us)
        if fill.fill_id in self.processed_fill_ids:
            raise ValueError("M032_DUPLICATE_FILL")
        reservation = self.reservations[reservation_id]
        slot = self.slots[reservation.slot_id]
        if slot.activated_at_us is None:
            raise ValueError("M032_FILL_BEFORE_ACTIVATION")
        if slot.state not in {SlotState.LIVE, SlotState.PARTIAL, SlotState.CANCEL_PENDING}:
            raise ValueError("M032_FILL_BEFORE_ACTIVATION")
        if fill.time_us < reservation.created_at_us or (
            slot.activated_at_us is not None and fill.time_us < slot.activated_at_us
        ):
            raise ValueError("M032_NONCAUSAL_FILL")
        if (
            fill.from_asset != reservation.asset
            or fill.input_quantity <= ZERO
            or fill.input_quantity > reservation.remaining
        ):
            raise ValueError("M032_FILL_EXCEEDS_RESERVATION")
        if (
            fill.output_quantity_gross < ZERO
            or fill.fee_quantity < ZERO
            or fill.output_quantity_net < ZERO
        ):
            raise ValueError("M032_INVALID_FEE_OR_OUTPUT")
        remaining_after_input = reservation.remaining - fill.input_quantity
        if fill.fee_asset == fill.from_asset and remaining_after_input < fill.fee_quantity:
            raise ValueError("M032_FEE_EXCEEDS_REMAINING_RESERVATION")
        if (
            fill.fee_asset not in {fill.from_asset, fill.to_asset}
            and fill.fee_quantity > ZERO
            and self.free.get(fill.fee_asset, ZERO) < fill.fee_quantity
        ):
            raise ValueError("M032_FEE_ASSET_INSUFFICIENT")

        # All failure-prone validation above precedes mutation, preserving atomicity.
        reservation.remaining -= fill.input_quantity
        slot.reserved_value = reservation.remaining
        slot.remaining_qty = reservation.remaining
        slot.filled_qty += fill.input_quantity
        self._asset_totals[fill.from_asset] -= fill.input_quantity
        self._asset_totals.setdefault(fill.to_asset, ZERO)
        self._asset_totals[fill.to_asset] += fill.output_quantity_gross
        if fill.fee_asset == fill.from_asset:
            reservation.remaining -= fill.fee_quantity
            slot.reserved_value = reservation.remaining
            slot.remaining_qty = reservation.remaining
            self._asset_totals[fill.from_asset] -= fill.fee_quantity
        elif fill.fee_asset == fill.to_asset:
            self._asset_totals[fill.to_asset] -= fill.fee_quantity
        elif fill.fee_quantity > ZERO:
            if self.free.get(fill.fee_asset, ZERO) < fill.fee_quantity:
                raise ValueError("M032_FEE_ASSET_INSUFFICIENT")
            self.free[fill.fee_asset] -= fill.fee_quantity
            self._asset_totals[fill.fee_asset] -= fill.fee_quantity
        self.owned[slot.slot_id][fill.to_asset] = (
            self.owned[slot.slot_id].get(fill.to_asset, ZERO) + fill.output_quantity_net
        )
        slot.current_asset = fill.to_asset
        if reservation.cancel_requested_at_us is not None:
            slot.state = SlotState.CANCEL_PENDING
        else:
            slot.state = SlotState.FILLED if reservation.remaining == ZERO else SlotState.PARTIAL
        self.processed_fill_ids.add(fill.fill_id)
        self.fill_attribution[fill.fill_id] = FillAttribution(
            reservation_id=reservation_id,
            reservation_created_at_us=reservation.created_at_us,
            slot_id=slot.slot_id,
            fill=fill,
        )
        self.audit.append(
            {
                "event": "FILL",
                "time_us": fill.time_us,
                "fill_id": fill.fill_id,
                "reservation_id": reservation_id,
                "slot_id": slot.slot_id,
                "input": str(fill.input_quantity),
                "output_net": str(fill.output_quantity_net),
                "from": fill.from_asset,
                "to": fill.to_asset,
            }
        )
        if reservation.remaining == ZERO and reservation.cancel_requested_at_us is None:
            slot.reservation_id = None
            del self.reservations[reservation_id]
        self._commit_time(fill.time_us)
        self.reconcile()

    def close_slot(
        self,
        slot_id: str,
        *,
        origin_quantity: D,
        now_us: int,
        cycle_id: str,
        additional_cost_origin: D = ZERO,
    ) -> D:
        self._causal(now_us)
        slot = self.slots[slot_id]
        if slot.reservation_id is not None:
            raise ValueError("M032_SLOT_CLOSE_WITH_OPEN_RESERVATION")
        final_quantity = self.owned[slot_id].get(slot.origin_asset, ZERO)
        if additional_cost_origin < ZERO:
            raise ValueError("M032_NEGATIVE_ADDITIONAL_COST")
        pnl = final_quantity - origin_quantity - additional_cost_origin
        if pnl < ZERO:
            raise ValueError("M032_NEGATIVE_REALIZED_EXIT_PROHIBITED")
        self.free[slot.origin_asset] += final_quantity
        self.owned[slot_id][slot.origin_asset] = ZERO
        self.realized_pnl_by_asset[slot.origin_asset] += pnl
        slot.realized_pnl += pnl
        slot.cycle_id = cycle_id
        slot.current_asset = slot.origin_asset
        slot.state = SlotState.CLOSED
        if slot.capital_lock_started_at_us is None:
            raise ValueError("M032_SLOT_CLOSE_WITHOUT_CAPITAL_LOCK")
        duration = now_us - slot.capital_lock_started_at_us
        if duration < 0:
            raise ValueError("M032_NONCAUSAL_SLOT_CLOSE")
        slot.capital_lock_duration_us += duration
        self.turnover_us.append(duration)
        slot.capital_lock_started_at_us = None
        self.audit.append(
            {
                "event": "ECONOMIC_CYCLE_CLOSED",
                "time_us": now_us,
                "slot_id": slot_id,
                "cycle_id": cycle_id,
                "realized_pnl": str(pnl),
            }
        )
        self._commit_time(now_us)
        self.reconcile()
        return pnl

    def register_inventory_reduction_authorization(
        self, authorization: InventoryReductionAuthorization, *, now_us: int
    ) -> None:
        """Persist the risk decision before any authorized exit reservation or fill."""
        self._causal(now_us)
        slot = self.slots[authorization.slot_id]
        origin_cost_basis = sum(
            (
                row.fill.input_quantity
                + (
                    row.fill.fee_quantity
                    if row.fill.fee_asset == authorization.origin_asset
                    else ZERO
                )
                for row in self.fill_attribution.values()
                if row.slot_id == authorization.slot_id
                and row.fill.from_asset == authorization.origin_asset
                and row.fill.time_us <= now_us
            ),
            ZERO,
        )
        if (
            now_us != authorization.decided_at_us
            or authorization.authorization_id in self.inventory_reduction_authorizations
            or authorization.authorization_id in self.processed_inventory_authorization_ids
            or slot.slot_epoch != authorization.slot_epoch
            or slot.origin_asset != authorization.origin_asset
            or slot.reservation_id is not None
            or slot.current_asset != authorization.inventory_asset
            or self.owned[slot.slot_id].get(authorization.inventory_asset, ZERO)
            != authorization.quantity
            or origin_cost_basis != authorization.origin_cost_basis
        ):
            raise ValueError("M034_INVALID_INVENTORY_REDUCTION_REGISTRATION")
        self.inventory_reduction_authorizations[authorization.authorization_id] = authorization
        self.audit.append(
            {
                "event": "INVENTORY_REDUCTION_AUTHORIZED",
                "time_us": now_us,
                "slot_id": authorization.slot_id,
                "authorization_id": authorization.authorization_id,
                "exit_reservation_id": authorization.exit_reservation_id,
                "rule_id": authorization.rule_id,
                "rule_hash": authorization.rule_hash,
            }
        )
        self._commit_time(now_us)

    def settle_inventory_reduction(
        self,
        slot_id: str,
        *,
        now_us: int,
        reduction_id: str,
        authorization: InventoryReductionAuthorization,
    ) -> D:
        """Settle a preregistered M034 risk reduction without counting a positive cycle."""
        self._causal(now_us)
        slot = self.slots[slot_id]
        if slot.reservation_id is not None:
            raise ValueError("M034_INVENTORY_REDUCTION_WITH_OPEN_RESERVATION")
        if reduction_id in self.processed_inventory_authorization_ids:
            raise ValueError("M034_DUPLICATE_INVENTORY_REDUCTION")
        if (
            self.inventory_reduction_authorizations.get(reduction_id) != authorization
            or
            authorization.authorization_id != reduction_id
            or authorization.slot_id != slot_id
            or authorization.slot_epoch != slot.slot_epoch
            or not authorization.decided_at_us <= now_us <= authorization.expires_at_us
            or authorization.reason_code != "NEGATIVE_EXIT_RISK_RULE_TRIGGERED"
            or not authorization.rule_id
            or not authorization.rule_hash
        ):
            raise ValueError("M034_INVENTORY_REDUCTION_AUTHORIZATION_MISMATCH")
        exit_fills = [
            row
            for row in self.fill_attribution.values()
            if row.reservation_id == authorization.exit_reservation_id
        ]
        if (
            not exit_fills
            or any(
                row.slot_id != slot_id
                or row.reservation_created_at_us < authorization.decided_at_us
                or row.fill.time_us < authorization.decided_at_us
                or row.fill.time_us > min(now_us, authorization.expires_at_us)
                or row.fill.from_asset != authorization.inventory_asset
                or row.fill.to_asset != authorization.origin_asset
                for row in exit_fills
            )
            or sum((row.fill.input_quantity for row in exit_fills), ZERO)
            != authorization.quantity
            or any(
                quantity != ZERO
                for asset, quantity in self.owned[slot_id].items()
                if asset != slot.origin_asset
            )
            or slot.origin_asset != authorization.origin_asset
        ):
            raise ValueError("M034_INVENTORY_REDUCTION_PHYSICAL_EXIT_UNPROVEN")
        final_quantity = self.owned[slot_id].get(slot.origin_asset, ZERO)
        physical_exit_output = sum(
            (row.fill.output_quantity_net for row in exit_fills), ZERO
        )
        if final_quantity != physical_exit_output:
            raise ValueError("M034_INVENTORY_REDUCTION_ORIGIN_RESIDUAL_MISMATCH")
        external_fee_rows = [
            row
            for row in self.fill_attribution.values()
            if row.slot_id == slot_id
            and row.fill.fee_quantity > ZERO
            and row.fill.fee_asset not in {row.fill.from_asset, row.fill.to_asset}
        ]
        fee_marks = {mark.base_asset: mark for mark in authorization.external_fee_marks}
        try:
            external_fee_cost_origin = sum(
                (
                    row.fill.fee_quantity
                    * fee_marks[row.fill.fee_asset].rate_at(
                        base_asset=row.fill.fee_asset,
                        quote_asset=slot.origin_asset,
                        time_us=authorization.decided_at_us,
                    )
                    for row in external_fee_rows
                ),
                ZERO,
            )
        except (KeyError, ValueError) as exc:
            raise ValueError("M034_EXTERNAL_FEE_MARK_UNPROVEN") from exc
        loss = (
            authorization.origin_cost_basis
            - final_quantity
            + external_fee_cost_origin
        )
        hold_cost = (
            authorization.expected_hold_loss
            + authorization.opportunity_cost_of_lock
            + authorization.tail_risk_increase
        )
        if (
            loss <= ZERO
            or loss > authorization.realized_loss_of_exit
            or hold_cost <= loss
        ):
            raise ValueError("M034_INVENTORY_REDUCTION_INEQUALITY_NOT_SATISFIED")
        if slot.capital_lock_started_at_us is None:
            raise ValueError("M034_INVENTORY_REDUCTION_WITHOUT_CAPITAL_LOCK")
        duration = now_us - slot.capital_lock_started_at_us
        if duration < 0:
            raise ValueError("M034_NONCAUSAL_INVENTORY_REDUCTION")

        self.free[slot.origin_asset] += final_quantity
        self.owned[slot_id][slot.origin_asset] = ZERO
        self.realized_pnl_by_asset[slot.origin_asset] -= loss
        slot.realized_pnl -= loss
        slot.current_asset = slot.origin_asset
        slot.state = SlotState.CLOSED
        slot.capital_lock_duration_us += duration
        slot.capital_lock_started_at_us = None
        self.inventory_reduction_turnover_us.append(duration)
        self.negative_exit_count += 1
        self.negative_exit_cost += loss
        self.processed_inventory_authorization_ids.add(reduction_id)
        del self.inventory_reduction_authorizations[reduction_id]
        self.audit.append(
            {
                "event": "INVENTORY_REDUCTION_SETTLED",
                "time_us": now_us,
                "slot_id": slot_id,
                "reduction_id": reduction_id,
                "rule_id": authorization.rule_id,
                "rule_hash": authorization.rule_hash,
                "trigger_reason_code": authorization.trigger_reason_code,
                "realized_loss": str(loss),
                "external_fee_cost_origin": str(external_fee_cost_origin),
                "counted_as_positive_cycle": False,
            }
        )
        self._commit_time(now_us)
        self.reconcile()
        return -loss

    def marked_equity(self, marks_usd: dict[str, D] | None = None) -> D:
        marks = self.marks_usd if marks_usd is None else marks_usd
        totals = self.asset_totals()
        if not set(totals).issubset(marks):
            raise ValueError("M032_MISSING_MARK")
        return sum((quantity * marks[asset] for asset, quantity in totals.items()), ZERO)

    def asset_totals(self) -> dict[str, D]:
        assets = set(self.free)
        assets.update(res.asset for res in self.reservations.values())
        for bucket in self.owned.values():
            assets.update(bucket)
        return {
            asset: self.free.get(asset, ZERO)
            + sum((r.remaining for r in self.reservations.values() if r.asset == asset), ZERO)
            + sum((bucket.get(asset, ZERO) for bucket in self.owned.values()), ZERO)
            for asset in assets
        }

    def reconcile(self) -> None:
        totals = self.asset_totals()
        if any(quantity < ZERO for quantity in totals.values()):
            raise ValueError("M032_NEGATIVE_ASSET_BUCKET")
        if totals != self._asset_totals:
            raise ValueError("M032_GLOBAL_ASSET_RECONCILIATION_FAILED")
        reservation_slots = [reservation.slot_id for reservation in self.reservations.values()]
        if len(reservation_slots) != len(set(reservation_slots)):
            raise ValueError("M032_SLOT_HAS_MULTIPLE_RESERVATIONS")
        for reservation_id, reservation in self.reservations.items():
            if self.slots[reservation.slot_id].reservation_id != reservation_id:
                raise ValueError("M032_RESERVATION_OWNER_MISMATCH")

    @staticmethod
    def _percentile(values: list[int], percentile: D) -> int | None:
        if not values:
            return None
        ordered = sorted(values)
        index = int(
            ((D(len(ordered)) - D(1)) * percentile).to_integral_value(rounding="ROUND_CEILING")
        )
        return ordered[index]

    def turnover_metrics(self) -> dict[str, int | float | None]:
        return {
            "MEDIAN_SLOT_TURNOVER_US": median(self.turnover_us) if self.turnover_us else None,
            "P90_SLOT_TURNOVER_US": self._percentile(self.turnover_us, D("0.90")),
            "P95_SLOT_TURNOVER_US": self._percentile(self.turnover_us, D("0.95")),
            "COMPLETED_SLOTS": len(self.turnover_us),
            "NEGATIVE_EXIT_COUNT": self.negative_exit_count,
            "NEGATIVE_EXIT_COST": float(self.negative_exit_cost),
        }


__all__ = ["CapitalReservation", "SlotLedger"]
