"""Global, exact multi-asset ownership ledger for the draft M032 architecture."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from crypto_strategy_lab.microstructure.multi_stable_models import (
    ZERO,
    D,
    EconomicSlot,
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
        self.turnover_us: list[int] = []
        self.realized_pnl_by_asset: dict[str, D] = {asset: ZERO for asset in self.free}
        self.audit: list[dict[str, object]] = []

    def create_slot(
        self,
        slot_id: str,
        *,
        origin_asset: str,
        usd_equivalent: D,
        now_us: int,
        slot_epoch: int = 1,
    ) -> EconomicSlot:
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
        self.reconcile()
        return reservation

    def activate(self, reservation_id: str, *, now_us: int) -> None:
        reservation = self.reservations[reservation_id]
        slot = self.slots[reservation.slot_id]
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

    def request_cancel(self, reservation_id: str, *, now_us: int) -> None:
        reservation = self.reservations[reservation_id]
        slot = self.slots[reservation.slot_id]
        if slot.filled_qty > ZERO:
            raise ValueError("M032_PARTIAL_OR_FILLED_NOT_RECLAIMABLE")
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

    def acknowledge_cancel(self, reservation_id: str, *, now_us: int) -> D:
        reservation = self.reservations[reservation_id]
        slot = self.slots[reservation.slot_id]
        if reservation.cancel_requested_at_us is None:
            raise ValueError("M032_CANCEL_ACK_WITHOUT_REQUEST")
        if slot.filled_qty > ZERO:
            raise ValueError("M032_PARTIAL_OR_FILLED_NOT_RECLAIMABLE")
        released = reservation.remaining
        self.free[reservation.asset] += released
        reservation.remaining = ZERO
        reservation.cancel_ack_at_us = now_us
        slot.reservation_id = None
        slot.reserved_value = ZERO
        slot.remaining_qty = ZERO
        slot.state = SlotState.FREE
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
        self.reconcile()
        return released

    def apply_fill(self, reservation_id: str, fill: PhysicalFill) -> None:
        if fill.fill_id in self.processed_fill_ids:
            raise ValueError("M032_DUPLICATE_FILL")
        reservation = self.reservations[reservation_id]
        slot = self.slots[reservation.slot_id]
        if fill.from_asset != reservation.asset or fill.input_quantity > reservation.remaining:
            raise ValueError("M032_FILL_EXCEEDS_RESERVATION")
        if fill.fee_quantity < ZERO or fill.output_quantity_net < ZERO:
            raise ValueError("M032_INVALID_FEE_OR_OUTPUT")
        reservation.remaining -= fill.input_quantity
        slot.reserved_value = reservation.remaining
        slot.remaining_qty = reservation.remaining
        slot.filled_qty += fill.input_quantity
        self._asset_totals[fill.from_asset] -= fill.input_quantity
        self._asset_totals.setdefault(fill.to_asset, ZERO)
        self._asset_totals[fill.to_asset] += fill.output_quantity_gross
        if fill.fee_asset == fill.from_asset:
            if reservation.remaining < fill.fee_quantity:
                raise ValueError("M032_FEE_EXCEEDS_REMAINING_RESERVATION")
            reservation.remaining -= fill.fee_quantity
            slot.reserved_value = reservation.remaining
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
        slot.state = SlotState.FILLED if reservation.remaining == ZERO else SlotState.PARTIAL
        self.processed_fill_ids.add(fill.fill_id)
        self.audit.append(
            {
                "event": "FILL",
                "time_us": fill.time_us,
                "fill_id": fill.fill_id,
                "slot_id": slot.slot_id,
                "input": str(fill.input_quantity),
                "output_net": str(fill.output_quantity_net),
                "from": fill.from_asset,
                "to": fill.to_asset,
            }
        )
        if reservation.remaining == ZERO:
            slot.reservation_id = None
            del self.reservations[reservation_id]
        self.reconcile()

    def close_slot(
        self,
        slot_id: str,
        *,
        origin_quantity: D,
        now_us: int,
        cycle_id: str,
    ) -> D:
        slot = self.slots[slot_id]
        final_quantity = self.owned[slot_id].get(slot.origin_asset, ZERO)
        pnl = final_quantity - origin_quantity
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
        self.reconcile()
        return pnl

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
        }


__all__ = ["CapitalReservation", "SlotLedger"]
