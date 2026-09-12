"""M035 pair-isolated market state with one exact shared-capital authority.

This module contains the deterministic conformance model.  It deliberately does
not provide a historical replay runner: M035 may consume tape only after two
aligned physical Binance pair datasets have passed the preregistered data gate.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from enum import IntEnum, StrEnum
from typing import Final

from crypto_strategy_lab.microstructure.multi_stable_queue import CausalQueueEstimator

D = Decimal
ZERO: Final = D("0")
INITIAL_BANK_USDT: Final = D("200")


class CapitalState(StrEnum):
    RESERVED_PAIR_A = "RESERVED_PAIR_A"
    RESERVED_PAIR_B = "RESERVED_PAIR_B"
    INVENTORY_PAIR_A = "INVENTORY_PAIR_A"
    INVENTORY_PAIR_B = "INVENTORY_PAIR_B"
    RETURN_PAIR_A = "RETURN_PAIR_A"
    RETURN_PAIR_B = "RETURN_PAIR_B"
    CANCEL_PENDING = "CANCEL_PENDING"


class AllocationPriority(IntEnum):
    OWNED_RETURN = 1
    RISK_OBLIGATION = 2
    NEW_ENTRY = 3


class OrderStatus(StrEnum):
    UNFUNDED = "UNFUNDED"
    ACTIVE = "ACTIVE"
    PARTIAL = "PARTIAL"
    PARTIAL_FILLED = "PARTIAL_FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    FILLED = "FILLED"


def _pair_state(pair_id: str, *, inventory: bool = False, returning: bool = False) -> CapitalState:
    if pair_id not in {"PAIR_A", "PAIR_B"}:
        raise ValueError("M035_UNKNOWN_PAIR")
    suffix = "A" if pair_id == "PAIR_A" else "B"
    if returning:
        return CapitalState(f"RETURN_PAIR_{suffix}")
    if inventory:
        return CapitalState(f"INVENTORY_PAIR_{suffix}")
    return CapitalState(f"RESERVED_PAIR_{suffix}")


@dataclass(frozen=True)
class AllocationCandidate:
    candidate_id: str
    pair_id: str
    requested_usdt: D
    priority: AllocationPriority
    marginal_productivity: D
    fifo_value: D
    expected_lock_seconds: D
    expected_net_edge: D
    allow_partial: bool = True
    existing_capital_id: str | None = None

    def __post_init__(self) -> None:
        if (
            not self.candidate_id
            or self.pair_id not in {"PAIR_A", "PAIR_B"}
            or self.requested_usdt <= ZERO
            or self.fifo_value < ZERO
            or self.expected_lock_seconds <= ZERO
        ):
            raise ValueError("M035_INVALID_ALLOCATION_CANDIDATE")
        if self.priority == AllocationPriority.NEW_ENTRY and (
            self.marginal_productivity <= ZERO or self.expected_net_edge <= ZERO
        ):
            raise ValueError("M035_INELIGIBLE_NEW_ENTRY")
        if self.priority == AllocationPriority.OWNED_RETURN and not self.existing_capital_id:
            raise ValueError("M035_OWNED_RETURN_CAPITAL_ID_REQUIRED")


@dataclass(frozen=True)
class AllocationGrant:
    candidate_id: str
    capital_id: str
    pair_id: str
    amount_usdt: D
    priority: AllocationPriority


@dataclass
class CapitalPosition:
    capital_id: str
    pair_id: str
    state: CapitalState
    cost_basis_usdt: D
    marked_value_usdt: D
    asset: str
    quantity: D
    created_at_us: int
    source_candidate_id: str
    source_capital_ids: tuple[str, ...] = ()
    source_cycles: tuple[str, ...] = ()
    attributable_costs_usdt: D = ZERO
    returned_proceeds_usdt: D = ZERO
    returned_quantity: D = ZERO
    returned_cost_basis_usdt: D = ZERO
    returned_attributable_costs_usdt: D = ZERO
    pending_cycle_id: str | None = None
    cancel_requested_at_us: int | None = None


@dataclass
class DustLot:
    capital_id: str
    pair_id: str
    asset: str
    quantity: D
    cost_basis_usdt: D
    source_cycles: tuple[str, ...]
    created_at_us: int


@dataclass(frozen=True)
class DustConsumption:
    asset: str
    quantity: D
    cost_basis_usdt: D
    source_cycles: tuple[str, ...]
    source_capital_ids: tuple[str, ...]


@dataclass(frozen=True)
class RiskExitAuthorization:
    authorization_id: str
    capital_id: str
    pair_id: str
    decided_at_us: int
    expires_at_us: int
    rule_hash: str
    quantity: D
    expected_hold_loss_usdt: D
    opportunity_cost_usdt: D
    tail_risk_usdt: D
    loss_if_exit_now_usdt: D

    def __post_init__(self) -> None:
        if (
            not self.authorization_id
            or not self.capital_id
            or self.pair_id not in {"PAIR_A", "PAIR_B"}
            or self.decided_at_us < 0
            or self.expires_at_us < self.decided_at_us
            or not self.rule_hash
            or min(
                self.expected_hold_loss_usdt,
                self.opportunity_cost_usdt,
                self.tail_risk_usdt,
                self.loss_if_exit_now_usdt,
            )
            < ZERO
            or self.quantity <= ZERO
            or self.expected_hold_loss_usdt
            + self.opportunity_cost_usdt
            + self.tail_risk_usdt
            <= self.loss_if_exit_now_usdt
        ):
            raise ValueError("M035_INVALID_RISK_EXIT_AUTHORIZATION")


class DustLedger:
    """Exact owned residual lots; this subledger never rounds value away."""

    def __init__(self) -> None:
        self.lots: list[DustLot] = []

    def add(self, lot: DustLot) -> None:
        if (
            not lot.capital_id
            or lot.pair_id not in {"PAIR_A", "PAIR_B"}
            or not lot.asset
            or lot.quantity <= ZERO
            or lot.cost_basis_usdt < ZERO
            or any(row.capital_id == lot.capital_id for row in self.lots)
        ):
            raise ValueError("M035_INVALID_DUST_LOT")
        self.lots.append(lot)

    def quantity(self, asset: str, *, pair_id: str | None = None) -> D:
        return sum(
            (
                row.quantity
                for row in self.lots
                if row.asset == asset and (pair_id is None or row.pair_id == pair_id)
            ),
            ZERO,
        )

    def cost_basis(self, asset: str, *, pair_id: str | None = None) -> D:
        return sum(
            (
                row.cost_basis_usdt
                for row in self.lots
                if row.asset == asset and (pair_id is None or row.pair_id == pair_id)
            ),
            ZERO,
        )

    def marked_value(self, marks_usdt: dict[str, D]) -> D:
        missing = {row.asset for row in self.lots if row.asset not in marks_usdt}
        if missing:
            raise ValueError("M035_DUST_MARK_MISSING")
        return sum((row.quantity * marks_usdt[row.asset] for row in self.lots), ZERO)

    def tradeable_quantity(
        self,
        asset: str,
        *,
        step_size: D,
        minimum_quantity: D,
        pair_id: str | None = None,
    ) -> D:
        if step_size <= ZERO or minimum_quantity <= ZERO:
            raise ValueError("M035_INVALID_DUST_RULE")
        available = self.quantity(asset, pair_id=pair_id)
        tradeable = (available / step_size).to_integral_value(rounding=ROUND_FLOOR) * step_size
        return tradeable if tradeable >= minimum_quantity else ZERO

    def consume(
        self,
        asset: str,
        *,
        quantity: D,
        pair_id: str,
        now_us: int,
    ) -> DustConsumption:
        if quantity <= ZERO or self.quantity(asset, pair_id=pair_id) < quantity:
            raise ValueError("M035_DUST_INSUFFICIENT")
        remaining = quantity
        cost_basis = ZERO
        cycles: list[str] = []
        capital_ids: list[str] = []
        for lot in sorted(self.lots, key=lambda row: (row.created_at_us, row.capital_id)):
            if remaining == ZERO:
                break
            if lot.asset != asset or lot.pair_id != pair_id:
                continue
            if now_us < lot.created_at_us:
                raise ValueError("M035_NONCAUSAL_DUST_CONSUMPTION")
            taken = min(lot.quantity, remaining)
            fraction = taken / lot.quantity
            taken_cost = lot.cost_basis_usdt * fraction
            lot.quantity -= taken
            lot.cost_basis_usdt -= taken_cost
            remaining -= taken
            cost_basis += taken_cost
            cycles.extend(lot.source_cycles)
            capital_ids.append(lot.capital_id)
        self.lots = [row for row in self.lots if row.quantity > ZERO]
        if remaining != ZERO:
            raise ValueError("M035_DUST_CONSUMPTION_RESIDUAL")
        return DustConsumption(
            asset=asset,
            quantity=quantity,
            cost_basis_usdt=cost_basis,
            source_cycles=tuple(dict.fromkeys(cycles)),
            source_capital_ids=tuple(dict.fromkeys(capital_ids)),
        )

    def assert_unique_ownership(self) -> None:
        ids = [row.capital_id for row in self.lots]
        if len(ids) != len(set(ids)):
            raise ValueError("M035_DUPLICATE_DUST_CAPITAL_ID")


class GlobalCapitalLedger:
    """The only M035 authority allowed to own the shared physical bank."""

    def __init__(self, initial_bank_usdt: D = INITIAL_BANK_USDT) -> None:
        if initial_bank_usdt != INITIAL_BANK_USDT:
            raise ValueError("M035_INITIAL_BANK_MUST_EQUAL_200")
        self.initial_bank_usdt = initial_bank_usdt
        self.free_usdt = initial_bank_usdt
        self.positions: dict[str, CapitalPosition] = {}
        self.dust = DustLedger()
        self.cycles = CycleAttributionLedger()
        self.realized_pnl_usdt = ZERO
        self.external_costs_usdt = ZERO
        self.asset_marks_usdt: dict[str, D] = {"USDT": D("1")}
        self.risk_exit_authorizations: dict[str, RiskExitAuthorization] = {}
        self.consumed_risk_exit_authorizations: set[str] = set()
        self.audit: list[dict[str, object]] = []
        self._sequence = 0
        self._last_event_us = -1

    def _causal(self, now_us: int) -> None:
        if now_us < self._last_event_us:
            raise ValueError("M035_NONCAUSAL_CAPITAL_EVENT")

    def _commit(self, now_us: int) -> None:
        self._last_event_us = now_us

    def reserve(self, candidate: AllocationCandidate, *, amount_usdt: D, now_us: int) -> str:
        self._causal(now_us)
        if amount_usdt <= ZERO or amount_usdt > candidate.requested_usdt:
            raise ValueError("M035_INVALID_GRANT_AMOUNT")
        if amount_usdt > self.free_usdt:
            raise ValueError("M035_GLOBAL_CAPITAL_INSUFFICIENT")
        self._sequence += 1
        capital_id = f"M035-CAP-{self._sequence:06d}"
        self.free_usdt -= amount_usdt
        self.positions[capital_id] = CapitalPosition(
            capital_id=capital_id,
            pair_id=candidate.pair_id,
            state=_pair_state(candidate.pair_id),
            cost_basis_usdt=amount_usdt,
            marked_value_usdt=amount_usdt,
            asset="USDT",
            quantity=amount_usdt,
            created_at_us=now_us,
            source_candidate_id=candidate.candidate_id,
        )
        self.audit.append(
            {
                "event": "CAPITAL_RESERVED",
                "time_us": now_us,
                "capital_id": capital_id,
                "pair_id": candidate.pair_id,
                "amount_usdt": str(amount_usdt),
            }
        )
        self._commit(now_us)
        self.reconcile()
        return capital_id

    def request_cancel(self, capital_id: str, *, now_us: int) -> None:
        self._causal(now_us)
        position = self.positions[capital_id]
        if position.state not in {
            CapitalState.RESERVED_PAIR_A,
            CapitalState.RESERVED_PAIR_B,
        }:
            raise ValueError("M035_CAPITAL_NOT_CANCELABLE")
        position.state = CapitalState.CANCEL_PENDING
        position.cancel_requested_at_us = now_us
        self.audit.append(
            {"event": "CANCEL_REQUEST", "time_us": now_us, "capital_id": capital_id}
        )
        self._commit(now_us)
        self.reconcile()

    def acknowledge_cancel(self, capital_id: str, *, now_us: int) -> D:
        self._causal(now_us)
        position = self.positions[capital_id]
        if (
            position.state != CapitalState.CANCEL_PENDING
            or position.cancel_requested_at_us is None
            or now_us < position.cancel_requested_at_us
            or position.asset != "USDT"
        ):
            raise ValueError("M035_CANCEL_ACK_INVALID")
        released = position.marked_value_usdt
        self.free_usdt += released
        del self.positions[capital_id]
        self.audit.append(
            {
                "event": "CANCEL_ACK",
                "time_us": now_us,
                "capital_id": capital_id,
                "released_usdt": str(released),
            }
        )
        self._commit(now_us)
        self.reconcile()
        return released

    def record_entry_fill(
        self,
        capital_id: str,
        *,
        asset: str,
        quantity_net: D,
        causal_mark_usdt: D,
        attributable_cost_usdt: D,
        now_us: int,
        input_usdt: D | None = None,
    ) -> str:
        self._causal(now_us)
        position = self.positions[capital_id]
        if position.state not in {
            CapitalState.RESERVED_PAIR_A,
            CapitalState.RESERVED_PAIR_B,
            CapitalState.CANCEL_PENDING,
        }:
            raise ValueError("M035_ENTRY_FILL_INVALID_STATE")
        consumed_usdt = position.cost_basis_usdt if input_usdt is None else input_usdt
        if (
            quantity_net <= ZERO
            or causal_mark_usdt <= ZERO
            or attributable_cost_usdt < ZERO
            or consumed_usdt <= ZERO
            or consumed_usdt > position.cost_basis_usdt
        ):
            raise ValueError("M035_INVALID_ENTRY_FILL")
        if attributable_cost_usdt > self.free_usdt:
            raise ValueError("M035_ATTRIBUTABLE_COST_CAPITAL_INSUFFICIENT")
        inventory_mark = quantity_net * causal_mark_usdt
        if inventory_mark < ZERO:
            raise ValueError("M035_ENTRY_COST_EXCEEDS_MARKED_INVENTORY")
        remaining_usdt = position.cost_basis_usdt - consumed_usdt
        if remaining_usdt > ZERO:
            self._sequence += 1
            inventory_capital_id = f"M035-CAP-{self._sequence:06d}"
            inventory_position = CapitalPosition(
                capital_id=inventory_capital_id,
                pair_id=position.pair_id,
                state=_pair_state(position.pair_id, inventory=True),
                cost_basis_usdt=consumed_usdt,
                marked_value_usdt=inventory_mark,
                asset=asset,
                quantity=quantity_net,
                created_at_us=now_us,
                source_candidate_id=position.source_candidate_id,
                source_capital_ids=(capital_id,),
                attributable_costs_usdt=attributable_cost_usdt,
            )
            position.cost_basis_usdt = remaining_usdt
            position.marked_value_usdt = remaining_usdt
            position.quantity = remaining_usdt
            self.positions[inventory_capital_id] = inventory_position
        else:
            inventory_capital_id = capital_id
            position.state = _pair_state(position.pair_id, inventory=True)
            position.asset = asset
            position.quantity = quantity_net
            position.marked_value_usdt = inventory_mark
            position.attributable_costs_usdt += attributable_cost_usdt
        self.free_usdt -= attributable_cost_usdt
        self.external_costs_usdt += attributable_cost_usdt
        self.asset_marks_usdt[asset] = causal_mark_usdt
        self.audit.append(
            {
                "event": "ENTRY_FILL",
                "time_us": now_us,
                "capital_id": capital_id,
                "inventory_capital_id": inventory_capital_id,
                "asset": asset,
                "quantity_net": str(quantity_net),
                "input_usdt": str(consumed_usdt),
                "remaining_reserved_usdt": str(remaining_usdt),
            }
        )
        self._commit(now_us)
        self.reconcile()
        return inventory_capital_id

    def reserve_owned_return(self, capital_id: str, *, now_us: int) -> None:
        self._causal(now_us)
        position = self.positions[capital_id]
        if position.state not in {
            CapitalState.INVENTORY_PAIR_A,
            CapitalState.INVENTORY_PAIR_B,
        }:
            raise ValueError("M035_RETURN_REQUIRES_OWNED_INVENTORY")
        position.state = _pair_state(position.pair_id, returning=True)
        self.audit.append(
            {"event": "OWNED_RETURN_RESERVED", "time_us": now_us, "capital_id": capital_id}
        )
        self._commit(now_us)
        self.reconcile()

    def register_risk_exit_authorization(
        self, authorization: RiskExitAuthorization, *, now_us: int
    ) -> None:
        self._causal(now_us)
        position = self.positions[authorization.capital_id]
        if (
            now_us != authorization.decided_at_us
            or authorization.authorization_id in self.risk_exit_authorizations
            or authorization.authorization_id in self.consumed_risk_exit_authorizations
            or position.pair_id != authorization.pair_id
            or position.state not in {
                CapitalState.INVENTORY_PAIR_A,
                CapitalState.INVENTORY_PAIR_B,
                CapitalState.RETURN_PAIR_A,
                CapitalState.RETURN_PAIR_B,
            }
        ):
            raise ValueError("M035_RISK_EXIT_AUTHORIZATION_REJECTED")
        self.risk_exit_authorizations[authorization.authorization_id] = authorization
        self.audit.append(
            {
                "event": "RISK_EXIT_AUTHORIZED",
                "time_us": now_us,
                "authorization_id": authorization.authorization_id,
                "capital_id": authorization.capital_id,
                "rule_hash": authorization.rule_hash,
            }
        )
        self._commit(now_us)

    def settle_return(
        self,
        capital_id: str,
        *,
        cycle_id: str,
        sold_quantity: D,
        net_proceeds_usdt: D,
        residual_mark_usdt: D,
        now_us: int,
        risk_exit_authorization_id: str | None = None,
        return_order_complete: bool = True,
    ) -> D:
        self._causal(now_us)
        position = self.positions[capital_id]
        if position.state not in {CapitalState.RETURN_PAIR_A, CapitalState.RETURN_PAIR_B}:
            raise ValueError("M035_SETTLEMENT_REQUIRES_RETURN_RESERVATION")
        if (
            sold_quantity <= ZERO
            or sold_quantity > position.quantity
            or net_proceeds_usdt < ZERO
            or residual_mark_usdt < ZERO
        ):
            raise ValueError("M035_INVALID_RETURN_SETTLEMENT")
        quantity_before_fill = position.quantity
        sold_cost_basis = position.cost_basis_usdt * sold_quantity / quantity_before_fill
        residual_quantity = quantity_before_fill - sold_quantity
        residual_cost_basis = position.cost_basis_usdt - sold_cost_basis
        sold_attributable_cost = (
            position.attributable_costs_usdt * sold_quantity / quantity_before_fill
        )
        residual_attributable_cost = (
            position.attributable_costs_usdt - sold_attributable_cost
        )
        if position.pending_cycle_id not in {None, cycle_id}:
            raise ValueError("M035_RETURN_CYCLE_ID_CHANGED_MID_ORDER")
        if cycle_id in self.cycles.cycles:
            raise ValueError("M035_INVALID_OR_DUPLICATE_CYCLE")
        cumulative_proceeds = position.returned_proceeds_usdt + net_proceeds_usdt
        cumulative_sold_quantity = position.returned_quantity + sold_quantity
        cumulative_cost_basis = position.returned_cost_basis_usdt + sold_cost_basis
        cumulative_attributable_costs = (
            position.returned_attributable_costs_usdt + sold_attributable_cost
        )
        realized = cumulative_proceeds - cumulative_cost_basis - cumulative_attributable_costs
        authorization: RiskExitAuthorization | None = None
        if realized < ZERO:
            if risk_exit_authorization_id is None:
                raise ValueError("M035_NEGATIVE_ORDINARY_CYCLE_PROHIBITED")
            authorization = self.risk_exit_authorizations.get(risk_exit_authorization_id)
            if (
                authorization is None
                or authorization.capital_id != capital_id
                or authorization.pair_id != position.pair_id
                or not authorization.decided_at_us <= now_us <= authorization.expires_at_us
                or risk_exit_authorization_id in self.consumed_risk_exit_authorizations
                or -realized > authorization.loss_if_exit_now_usdt
                or (return_order_complete and cumulative_sold_quantity != authorization.quantity)
            ):
                raise ValueError("M035_RISK_EXIT_AUTHORIZATION_NOT_APPLICABLE")
        if return_order_complete and residual_quantity > ZERO and residual_mark_usdt <= ZERO:
            raise ValueError("M035_RESIDUAL_MARK_REQUIRED")
        self.free_usdt += net_proceeds_usdt
        if not return_order_complete:
            position.quantity = residual_quantity
            position.cost_basis_usdt = residual_cost_basis
            position.attributable_costs_usdt = residual_attributable_cost
            position.marked_value_usdt = (
                residual_quantity * self.asset_marks_usdt[position.asset]
            )
            position.returned_proceeds_usdt = cumulative_proceeds
            position.returned_quantity = cumulative_sold_quantity
            position.returned_cost_basis_usdt = cumulative_cost_basis
            position.returned_attributable_costs_usdt = cumulative_attributable_costs
            position.pending_cycle_id = cycle_id
            self.audit.append(
                {
                    "event": "RETURN_PARTIAL_FILL_SETTLED",
                    "time_us": now_us,
                    "capital_id": capital_id,
                    "cycle_id": cycle_id,
                    "sold_quantity": str(sold_quantity),
                    "net_proceeds_usdt": str(net_proceeds_usdt),
                    "remaining_quantity": str(residual_quantity),
                }
            )
            self._commit(now_us)
            self.reconcile()
            return net_proceeds_usdt - sold_cost_basis - sold_attributable_cost
        cycle = CycleRecord(
            cycle_id=cycle_id,
            pair_id=position.pair_id,
            proceeds_usdt=cumulative_proceeds,
            original_cost_basis_usdt=cumulative_cost_basis,
            fees_usdt=ZERO,
            execution_cost_usdt=ZERO,
            adverse_selection_usdt=ZERO,
            attributable_costs_usdt=cumulative_attributable_costs,
            risk_exit=authorization is not None,
        )
        self.cycles.record(cycle)
        self.realized_pnl_usdt += realized
        if authorization is not None:
            self.consumed_risk_exit_authorizations.add(authorization.authorization_id)
        del self.positions[capital_id]
        if residual_quantity > ZERO:
            self.dust.add(
                DustLot(
                    capital_id=capital_id,
                    pair_id=position.pair_id,
                    asset=position.asset,
                    quantity=residual_quantity,
                    cost_basis_usdt=residual_cost_basis + residual_attributable_cost,
                    source_cycles=tuple(dict.fromkeys((*position.source_cycles, cycle_id))),
                    created_at_us=now_us,
                )
            )
        self.audit.append(
            {
                "event": "RETURN_SETTLED",
                "time_us": now_us,
                "capital_id": capital_id,
                "cycle_id": cycle_id,
                "realized_pnl_usdt": str(realized),
                "dust_quantity": str(residual_quantity),
                "dust_mark_usdt": str(residual_mark_usdt),
                "risk_exit_authorization_id": risk_exit_authorization_id,
            }
        )
        self._commit(now_us)
        self.reconcile()
        return realized

    def reserve_aggregated_dust(
        self,
        *,
        pair_id: str,
        asset: str,
        quantity: D,
        mark_usdt: D,
        now_us: int,
    ) -> str:
        self._causal(now_us)
        if mark_usdt <= ZERO:
            raise ValueError("M035_INVALID_DUST_MARK")
        consumed = self.dust.consume(asset, quantity=quantity, pair_id=pair_id, now_us=now_us)
        self._sequence += 1
        capital_id = f"M035-CAP-{self._sequence:06d}"
        self.positions[capital_id] = CapitalPosition(
            capital_id=capital_id,
            pair_id=pair_id,
            state=_pair_state(pair_id, returning=True),
            cost_basis_usdt=consumed.cost_basis_usdt,
            marked_value_usdt=quantity * mark_usdt,
            asset=asset,
            quantity=quantity,
            created_at_us=now_us,
            source_candidate_id="DUST_AGGREGATION",
            source_capital_ids=consumed.source_capital_ids,
            source_cycles=consumed.source_cycles,
        )
        self.audit.append(
            {
                "event": "DUST_AGGREGATED_FOR_RETURN",
                "time_us": now_us,
                "capital_id": capital_id,
                "asset": asset,
                "quantity": str(quantity),
            }
        )
        self._commit(now_us)
        self.reconcile()
        return capital_id

    def update_mark(self, capital_id: str, *, mark_usdt: D, now_us: int) -> None:
        self._causal(now_us)
        if mark_usdt <= ZERO:
            raise ValueError("M035_INVALID_CAUSAL_MARK")
        position = self.positions[capital_id]
        if position.asset != "USDT":
            position.marked_value_usdt = position.quantity * mark_usdt
            if position.marked_value_usdt < ZERO:
                raise ValueError("M035_MARK_BELOW_ATTRIBUTABLE_COST")
        self._commit(now_us)
        self.reconcile()

    def update_asset_mark(self, asset: str, *, mark_usdt: D, now_us: int) -> None:
        self._causal(now_us)
        if not asset or mark_usdt <= ZERO:
            raise ValueError("M035_INVALID_CAUSAL_MARK")
        for position in self.positions.values():
            if position.asset == asset:
                position.marked_value_usdt = position.quantity * mark_usdt
        self.asset_marks_usdt[asset] = mark_usdt
        self.audit.append(
            {
                "event": "CAUSAL_ASSET_MARK",
                "time_us": now_us,
                "asset": asset,
                "mark_usdt": str(mark_usdt),
            }
        )
        self._commit(now_us)
        self.reconcile()

    @property
    def committed_usdt(self) -> D:
        return sum((row.marked_value_usdt for row in self.positions.values()), ZERO)

    def marked_equity(self, marks_usdt: dict[str, D] | None = None) -> D:
        marks = dict(self.asset_marks_usdt)
        if marks_usdt is not None:
            marks.update(marks_usdt)
        return self.free_usdt + self.committed_usdt + self.dust.marked_value(marks)

    def zero_loss_economic_pass(self, marks_usdt: dict[str, D] | None = None) -> bool:
        return (
            self.cycles.zero_loss_economic_pass
            and self.marked_equity(marks_usdt) >= self.initial_bank_usdt
        )

    def owner_of(self, capital_id: str) -> str | None:
        if capital_id in self.positions:
            return self.positions[capital_id].pair_id
        lot = next((row for row in self.dust.lots if row.capital_id == capital_id), None)
        return None if lot is None else lot.pair_id

    def reconcile(self) -> None:
        if self.free_usdt < ZERO:
            raise ValueError("M035_NEGATIVE_FREE_CAPITAL")
        position_ids = set(self.positions)
        dust_ids = {row.capital_id for row in self.dust.lots}
        if position_ids & dust_ids:
            raise ValueError("M035_DOUBLE_CAPITAL_OWNERSHIP")
        if any(
            row.marked_value_usdt < ZERO or row.cost_basis_usdt < ZERO
            for row in self.positions.values()
        ):
            raise ValueError("M035_NEGATIVE_CAPITAL_BUCKET")
        self.dust.assert_unique_ownership()


class ParallelPairCapitalAllocator:
    """Allocate simultaneous pair requests from the single global free balance."""

    def __init__(self, ledger: GlobalCapitalLedger) -> None:
        self.ledger = ledger

    @staticmethod
    def _ranking(candidate: AllocationCandidate) -> tuple[object, ...]:
        return (
            int(candidate.priority),
            -candidate.marginal_productivity,
            -candidate.fifo_value,
            candidate.expected_lock_seconds,
            -candidate.expected_net_edge,
            candidate.candidate_id,
        )

    def allocate(
        self, candidates: Iterable[AllocationCandidate], *, now_us: int
    ) -> tuple[AllocationGrant, ...]:
        grants: list[AllocationGrant] = []
        for candidate in sorted(candidates, key=self._ranking):
            if candidate.priority == AllocationPriority.OWNED_RETURN:
                assert candidate.existing_capital_id is not None
                position = self.ledger.positions[candidate.existing_capital_id]
                if position.pair_id != candidate.pair_id:
                    raise ValueError("M035_OWNED_RETURN_PAIR_MISMATCH")
                self.ledger.reserve_owned_return(
                    candidate.existing_capital_id, now_us=now_us
                )
                grants.append(
                    AllocationGrant(
                        candidate_id=candidate.candidate_id,
                        capital_id=candidate.existing_capital_id,
                        pair_id=candidate.pair_id,
                        amount_usdt=position.marked_value_usdt,
                        priority=candidate.priority,
                    )
                )
                continue
            available = self.ledger.free_usdt
            if available <= ZERO:
                break
            amount = min(candidate.requested_usdt, available)
            if amount < candidate.requested_usdt and not candidate.allow_partial:
                continue
            capital_id = self.ledger.reserve(candidate, amount_usdt=amount, now_us=now_us)
            grants.append(
                AllocationGrant(
                    candidate_id=candidate.candidate_id,
                    capital_id=capital_id,
                    pair_id=candidate.pair_id,
                    amount_usdt=amount,
                    priority=candidate.priority,
                )
            )
        self.ledger.reconcile()
        return tuple(grants)


@dataclass
class PairOrder:
    order_id: str
    pair_id: str
    side: str
    rank: int
    column: int
    price: D
    quantity: D
    submitted_at_us: int
    status: OrderStatus = OrderStatus.ACTIVE
    replacement_price: D | None = None
    filled_quantity: D = ZERO
    capital_id: str | None = None
    inventory_capital_ids: list[str] = field(default_factory=list)
    role: str = "ENTRY"
    cycle_id: str | None = None
    risk_exit_authorization_id: str | None = None
    net_proceeds_usdt: D = ZERO


@dataclass
class PairState:
    pair_id: str
    symbol: str
    pair_asset: str
    tick_size: D
    hotline: D | None = None
    bid: D | None = None
    ask: D | None = None
    orders: dict[str, PairOrder] = field(default_factory=dict)
    hotline_history: list[tuple[int, D]] = field(default_factory=list)
    event_log: list[dict[str, object]] = field(default_factory=list)
    cycle_history: list[str] = field(default_factory=list)
    realized_pnl: D = ZERO
    inventory_quantity: D = ZERO
    dust_quantity: D = ZERO


class PairEngine:
    """One pair-local hotline/grid/queue authority; no global bank is stored here."""

    def __init__(
        self,
        *,
        pair_id: str,
        symbol: str,
        pair_asset: str,
        tick_size: D,
        capital_ledger: GlobalCapitalLedger | None = None,
    ) -> None:
        if pair_id not in {"PAIR_A", "PAIR_B"} or tick_size <= ZERO:
            raise ValueError("M035_INVALID_PAIR_ENGINE")
        self.state = PairState(pair_id, symbol, pair_asset, tick_size)
        self.queue = CausalQueueEstimator()
        self.capital_ledger = capital_ledger
        self._last_event_us = -1
        self._sequence = 0

    def _target_price(self, *, side: str, rank: int, hotline: D | None = None) -> D:
        center = self.state.hotline if hotline is None else hotline
        if center is None or side not in {"BUY", "SELL"} or not 1 <= rank <= 7:
            raise ValueError("M035_INVALID_GRID_TARGET")
        direction = D("-1") if side == "BUY" else D("1")
        return center + direction * D(rank) * self.state.tick_size

    def _new_order(
        self,
        *,
        side: str,
        rank: int,
        column: int,
        price: D,
        now_us: int,
        role: str = "ENTRY",
        capital_id: str | None = None,
        cycle_id: str | None = None,
        risk_exit_authorization_id: str | None = None,
    ) -> PairOrder:
        self._sequence += 1
        order = PairOrder(
            order_id=f"{self.state.pair_id}-O-{self._sequence:05d}",
            pair_id=self.state.pair_id,
            side=side,
            rank=rank,
            column=column,
            price=price,
            quantity=D("1"),
            submitted_at_us=now_us,
            status=(
                OrderStatus.UNFUNDED
                if self.capital_ledger is not None and capital_id is None
                else OrderStatus.ACTIVE
            ),
            capital_id=capital_id,
            role=role,
            cycle_id=cycle_id,
            risk_exit_authorization_id=risk_exit_authorization_id,
        )
        self.state.orders[order.order_id] = order
        if order.status == OrderStatus.ACTIVE:
            self.queue.activate(
                book=self.state.symbol,
                side=side,
                price=price,
                order_id=order.order_id,
                column=column,
                quantity=order.quantity,
                observed_public_queue=ZERO,
                now_us=now_us,
            )
        return order

    def initialize_grid(self, *, now_us: int) -> None:
        if self.state.hotline is None:
            raise ValueError("M035_HOTLINE_REQUIRED")
        if self.state.orders:
            raise ValueError("M035_GRID_ALREADY_INITIALIZED")
        for side in ("BUY", "SELL"):
            for rank in range(1, 8):
                for column in (1, 2):
                    self._new_order(
                        side=side,
                        rank=rank,
                        column=column,
                        price=self._target_price(side=side, rank=rank),
                        now_us=now_us,
                    )

    def receive_book(
        self,
        *,
        bid: D,
        ask: D,
        now_us: int,
        reason: str = "CAUSAL_BOOK_MIDPOINT",
    ) -> None:
        if now_us < self._last_event_us:
            raise ValueError("M035_NONCAUSAL_PAIR_EVENT")
        if bid <= ZERO or ask <= bid:
            raise ValueError("M035_INVALID_BOOK")
        if self.capital_ledger is not None:
            self.capital_ledger.update_asset_mark(
                self.state.pair_asset, mark_usdt=bid, now_us=now_us
            )
        midpoint = (bid + ask) / D("2")
        target = (midpoint / self.state.tick_size).to_integral_value(
            rounding=ROUND_HALF_UP
        ) * self.state.tick_size
        old = self.state.hotline
        self.state.bid = bid
        self.state.ask = ask
        self.state.hotline = target
        if not self.state.hotline_history or self.state.hotline_history[-1][1] != target:
            self.state.hotline_history.append((now_us, target))
        if old is not None and old != target:
            affected = self._reconcile_for_hotline(now_us=now_us, old_hotline=old)
            self.state.event_log.append(
                {
                    "timestamp": now_us,
                    "pair": self.state.pair_id,
                    "old_hotline": str(old),
                    "new_hotline": str(target),
                    "reason": reason,
                    "affected_grid_levels": affected,
                }
            )
        self._last_event_us = now_us

    def _reconcile_for_hotline(self, *, now_us: int, old_hotline: D) -> list[str]:
        affected: list[str] = []
        for order in sorted(self.state.orders.values(), key=lambda row: row.order_id):
            if order.role == "RETURN":
                continue
            if order.status == OrderStatus.UNFUNDED:
                order.price = self._target_price(side=order.side, rank=order.rank)
                continue
            if order.status == OrderStatus.CANCEL_PENDING and order.column == 2:
                order.replacement_price = self._target_price(
                    side=order.side, rank=order.rank
                )
                affected.append(f"{order.side}:R{order.rank}:C{order.column}")
                continue
            if order.status not in {OrderStatus.ACTIVE, OrderStatus.PARTIAL}:
                continue
            target = self._target_price(side=order.side, rank=order.rank)
            if target == order.price:
                continue
            affected.append(f"{order.side}:R{order.rank}:C{order.column}")
            if order.column == 1:
                continue
            if order.capital_id is not None and self.capital_ledger is not None:
                self.capital_ledger.request_cancel(order.capital_id, now_us=now_us)
            order.replacement_price = target
            order.status = OrderStatus.CANCEL_PENDING
        return affected

    def acknowledge_grid_cancel(self, order_id: str, *, now_us: int) -> PairOrder | None:
        if now_us < self._last_event_us:
            raise ValueError("M035_NONCAUSAL_PAIR_EVENT")
        order = self.state.orders[order_id]
        if order.status != OrderStatus.CANCEL_PENDING or order.replacement_price is None:
            raise ValueError("M035_GRID_CANCEL_ACK_INVALID")
        queue_probe = deepcopy(self.queue)
        if order.filled_quantity > ZERO:
            queue_probe.cancel_ack_after_racing_fill(order_id, now_us=now_us)
            if order.capital_id is not None and self.capital_ledger is not None:
                pending = self.capital_ledger.positions.get(order.capital_id)
                if pending is not None and pending.state == CapitalState.CANCEL_PENDING:
                    self.capital_ledger.acknowledge_cancel(order.capital_id, now_us=now_us)
            self.queue.cancel_ack_after_racing_fill(order_id, now_us=now_us)
            order.status = OrderStatus.PARTIAL_FILLED
            self._last_event_us = now_us
            return None
        queue_probe.cancel_ack(order_id, now_us=now_us)
        if order.capital_id is not None and self.capital_ledger is not None:
            self.capital_ledger.acknowledge_cancel(order.capital_id, now_us=now_us)
        self.queue.cancel_ack(order_id, now_us=now_us)
        order.status = OrderStatus.CANCELLED
        replacement = self._new_order(
            side=order.side,
            rank=order.rank,
            column=order.column,
            price=order.replacement_price,
            now_us=now_us,
        )
        self._last_event_us = now_us
        return replacement

    def bind_order_capital(self, order_id: str, capital_id: str, *, now_us: int) -> None:
        if self.capital_ledger is None:
            raise ValueError("M035_PAIR_ENGINE_HAS_NO_GLOBAL_LEDGER")
        if now_us < self._last_event_us:
            raise ValueError("M035_NONCAUSAL_PAIR_EVENT")
        order = self.state.orders[order_id]
        position = self.capital_ledger.positions[capital_id]
        if (
            position.pair_id != self.state.pair_id
            or position.asset != "USDT"
            or position.state
            not in {CapitalState.RESERVED_PAIR_A, CapitalState.RESERVED_PAIR_B}
            or order.side != "BUY"
            or order.role != "ENTRY"
            or position.cost_basis_usdt < order.price * order.quantity
        ):
            raise ValueError("M035_ORDER_CAPITAL_OWNER_MISMATCH")
        if order.capital_id is not None or any(
            row.capital_id == capital_id
            and row.order_id != order_id
            and row.status
            in {
                OrderStatus.UNFUNDED,
                OrderStatus.ACTIVE,
                OrderStatus.PARTIAL,
                OrderStatus.CANCEL_PENDING,
            }
            for row in self.state.orders.values()
        ):
            raise ValueError("M035_ORDER_ALREADY_FUNDED")
        queue_probe = deepcopy(self.queue)
        queue_probe.activate(
            book=self.state.symbol,
            side=order.side,
            price=order.price,
            order_id=order.order_id,
            column=order.column,
            quantity=order.quantity,
            observed_public_queue=ZERO,
            now_us=now_us,
        )
        self.queue.activate(
            book=self.state.symbol,
            side=order.side,
            price=order.price,
            order_id=order.order_id,
            column=order.column,
            quantity=order.quantity,
            observed_public_queue=ZERO,
            now_us=now_us,
        )
        order.capital_id = capital_id
        order.status = OrderStatus.ACTIVE
        self._last_event_us = now_us

    def submit_owned_return(
        self,
        capital_id: str,
        *,
        cycle_id: str,
        price: D,
        quantity: D,
        now_us: int,
        risk_exit_authorization_id: str | None = None,
    ) -> PairOrder:
        if self.capital_ledger is None:
            raise ValueError("M035_PAIR_ENGINE_HAS_NO_GLOBAL_LEDGER")
        if now_us < self._last_event_us or price <= ZERO or quantity <= ZERO:
            raise ValueError("M035_INVALID_RETURN_ORDER")
        position = self.capital_ledger.positions[capital_id]
        if (
            position.pair_id != self.state.pair_id
            or position.asset != self.state.pair_asset
            or quantity > position.quantity
            or position.state
            not in {
                CapitalState.INVENTORY_PAIR_A,
                CapitalState.INVENTORY_PAIR_B,
                CapitalState.RETURN_PAIR_A,
                CapitalState.RETURN_PAIR_B,
            }
            or any(
                row.capital_id == capital_id
                and row.role == "RETURN"
                and row.status
                in {OrderStatus.ACTIVE, OrderStatus.PARTIAL, OrderStatus.CANCEL_PENDING}
                for row in self.state.orders.values()
            )
        ):
            raise ValueError("M035_RETURN_ORDER_INVENTORY_MISMATCH")
        group = self.queue.groups.get((self.state.symbol, "SELL", price))
        occupied_columns = (
            {row.column for row in group.own_orders if row.remaining > ZERO}
            if group is not None
            else set()
        )
        available_columns = [column for column in (1, 2) if column not in occupied_columns]
        if not available_columns:
            raise ValueError("M035_RETURN_QUEUE_FULL")
        column = available_columns[0]
        self._sequence += 1
        order = PairOrder(
            order_id=f"{self.state.pair_id}-O-{self._sequence:05d}",
            pair_id=self.state.pair_id,
            side="SELL",
            rank=0,
            column=column,
            price=price,
            quantity=quantity,
            submitted_at_us=now_us,
            capital_id=capital_id,
            role="RETURN",
            cycle_id=cycle_id,
            risk_exit_authorization_id=risk_exit_authorization_id,
        )
        queue_probe = deepcopy(self.queue)
        queue_probe.activate(
            book=self.state.symbol,
            side="SELL",
            price=price,
            order_id=order.order_id,
            column=column,
            quantity=quantity,
            observed_public_queue=ZERO,
            now_us=now_us,
        )
        if position.state in {
            CapitalState.INVENTORY_PAIR_A,
            CapitalState.INVENTORY_PAIR_B,
        }:
            self.capital_ledger.reserve_owned_return(capital_id, now_us=now_us)
        self.state.orders[order.order_id] = order
        self.queue.activate(
            book=self.state.symbol,
            side="SELL",
            price=price,
            order_id=order.order_id,
            column=column,
            quantity=quantity,
            observed_public_queue=ZERO,
            now_us=now_us,
        )
        self._last_event_us = now_us
        return order

    @staticmethod
    def c1_should_move(
        *,
        new_value: D,
        current_value: D,
        lost_fifo_value: D,
        cancel_cost: D,
        reentry_cost: D,
    ) -> bool:
        if min(lost_fifo_value, cancel_cost, reentry_cost) < ZERO:
            raise ValueError("M035_NEGATIVE_SWITCHING_COST")
        return new_value - current_value > lost_fifo_value + cancel_cost + reentry_cost

    def request_c1_move(
        self,
        order_id: str,
        *,
        replacement_price: D,
        new_value: D,
        current_value: D,
        lost_fifo_value: D,
        cancel_cost: D,
        reentry_cost: D,
        now_us: int,
    ) -> bool:
        if now_us < self._last_event_us:
            raise ValueError("M035_NONCAUSAL_PAIR_EVENT")
        order = self.state.orders[order_id]
        if order.column != 1 or order.status != OrderStatus.ACTIVE:
            raise ValueError("M035_NOT_ACTIVE_C1")
        if not self.c1_should_move(
            new_value=new_value,
            current_value=current_value,
            lost_fifo_value=lost_fifo_value,
            cancel_cost=cancel_cost,
            reentry_cost=reentry_cost,
        ):
            return False
        order.replacement_price = replacement_price
        if order.capital_id is not None and self.capital_ledger is not None:
            self.capital_ledger.request_cancel(order.capital_id, now_us=now_us)
        order.status = OrderStatus.CANCEL_PENDING
        self._last_event_us = now_us
        return True

    def consume_public_trade(
        self,
        *,
        trade_id: str,
        side: str,
        price: D,
        quantity: D,
        now_us: int,
        source: str,
        fee_rate: D = ZERO,
        attributable_cost_usdt: D = ZERO,
    ) -> dict[str, D]:
        if now_us < self._last_event_us:
            raise ValueError("M035_NONCAUSAL_PAIR_EVENT")
        if source != "PUBLIC_TRADE":
            raise ValueError("M035_SELF_FILL_PROHIBITED")
        if not ZERO <= fee_rate < D("1") or attributable_cost_usdt < ZERO:
            raise ValueError("M035_INVALID_FILL_COST")
        if self.capital_ledger is None:
            raise ValueError("M035_PHYSICAL_FILL_REQUIRES_GLOBAL_LEDGER")
        simulated_queue = deepcopy(self.queue)
        planned_fills = simulated_queue.consume_compatible_flow(
            event_id=f"{self.state.symbol}:{trade_id}",
            book=self.state.symbol,
            side=side,
            price=price,
            quantity=quantity,
            now_us=now_us,
        )
        if attributable_cost_usdt * D(len(planned_fills)) > self.capital_ledger.free_usdt:
            raise ValueError("M035_ATTRIBUTABLE_COST_CAPITAL_INSUFFICIENT")
        for order_id, amount in planned_fills.items():
            order = self.state.orders[order_id]
            if order.capital_id is None:
                raise ValueError("M035_PHYSICAL_FILL_WITHOUT_CAPITAL")
            position = self.capital_ledger.positions.get(order.capital_id)
            if position is None or position.pair_id != self.state.pair_id:
                raise ValueError("M035_PHYSICAL_FILL_CAPITAL_MISMATCH")
            if order.role == "ENTRY":
                if (
                    order.side != "BUY"
                    or position.asset != "USDT"
                    or position.state
                    not in {
                        CapitalState.RESERVED_PAIR_A,
                        CapitalState.RESERVED_PAIR_B,
                        CapitalState.CANCEL_PENDING,
                    }
                    or amount * price > position.cost_basis_usdt
                ):
                    raise ValueError("M035_ENTRY_FILL_NOT_FUNDED")
            elif (
                order.role != "RETURN"
                or order.side != "SELL"
                or position.asset != self.state.pair_asset
                or position.state
                not in {CapitalState.RETURN_PAIR_A, CapitalState.RETURN_PAIR_B}
                or amount > position.quantity
            ):
                raise ValueError("M035_RETURN_FILL_NOT_FUNDED")
        ledger_probe = deepcopy(self.capital_ledger)
        for order_id, amount in planned_fills.items():
            order = self.state.orders[order_id]
            assert order.capital_id is not None
            if order.role == "ENTRY":
                ledger_probe.record_entry_fill(
                    order.capital_id,
                    asset=self.state.pair_asset,
                    quantity_net=amount * (D("1") - fee_rate),
                    causal_mark_usdt=price,
                    attributable_cost_usdt=attributable_cost_usdt,
                    input_usdt=amount * price,
                    now_us=now_us,
                )
            else:
                assert order.cycle_id is not None
                order_complete = order.filled_quantity + amount == order.quantity
                probe_position = ledger_probe.positions[order.capital_id]
                residual_mark = (
                    ledger_probe.asset_marks_usdt[probe_position.asset]
                    if order_complete and probe_position.quantity > amount
                    else ZERO
                )
                ledger_probe.settle_return(
                    order.capital_id,
                    cycle_id=order.cycle_id,
                    sold_quantity=amount,
                    net_proceeds_usdt=(
                        amount * price * (D("1") - fee_rate) - attributable_cost_usdt
                    ),
                    residual_mark_usdt=residual_mark,
                    now_us=now_us,
                    risk_exit_authorization_id=order.risk_exit_authorization_id,
                    return_order_complete=order_complete,
                )
        fills = self.queue.consume_compatible_flow(
            event_id=f"{self.state.symbol}:{trade_id}",
            book=self.state.symbol,
            side=side,
            price=price,
            quantity=quantity,
            now_us=now_us,
        )
        for order_id, amount in fills.items():
            order = self.state.orders[order_id]
            was_cancel_pending = order.status == OrderStatus.CANCEL_PENDING
            order.filled_quantity += amount
            if order.filled_quantity == order.quantity and not was_cancel_pending:
                order.status = OrderStatus.FILLED
            elif not was_cancel_pending:
                order.status = OrderStatus.PARTIAL
            assert order.capital_id is not None
            if order.role == "ENTRY":
                net_inventory = amount * (D("1") - fee_rate)
                inventory_id = self.capital_ledger.record_entry_fill(
                    order.capital_id,
                    asset=self.state.pair_asset,
                    quantity_net=net_inventory,
                    causal_mark_usdt=price,
                    attributable_cost_usdt=attributable_cost_usdt,
                    input_usdt=amount * price,
                    now_us=now_us,
                )
                order.inventory_capital_ids.append(inventory_id)
                self.state.inventory_quantity += net_inventory
            else:
                fill_proceeds = (
                    amount * price * (D("1") - fee_rate) - attributable_cost_usdt
                )
                order.net_proceeds_usdt += fill_proceeds
                assert order.cycle_id is not None
                order_complete = order.filled_quantity == order.quantity
                live_position = self.capital_ledger.positions[order.capital_id]
                residual_mark = (
                    self.capital_ledger.asset_marks_usdt[live_position.asset]
                    if order_complete and live_position.quantity > amount
                    else ZERO
                )
                self._settle_owned_return(
                    order.capital_id,
                    cycle_id=order.cycle_id,
                    sold_quantity=amount,
                    net_proceeds_usdt=fill_proceeds,
                    residual_mark_usdt=residual_mark,
                    now_us=now_us,
                    risk_exit_authorization_id=order.risk_exit_authorization_id,
                    return_order_complete=order_complete,
                )
        self._last_event_us = now_us
        return fills

    def _settle_owned_return(
        self,
        capital_id: str,
        *,
        cycle_id: str,
        sold_quantity: D,
        net_proceeds_usdt: D,
        residual_mark_usdt: D,
        now_us: int,
        risk_exit_authorization_id: str | None = None,
        return_order_complete: bool = True,
    ) -> D:
        if self.capital_ledger is None:
            raise ValueError("M035_PAIR_ENGINE_HAS_NO_GLOBAL_LEDGER")
        position = self.capital_ledger.positions[capital_id]
        if position.pair_id != self.state.pair_id:
            raise ValueError("M035_ORDER_CAPITAL_OWNER_MISMATCH")
        if sold_quantity > self.state.inventory_quantity:
            raise ValueError("M035_NEGATIVE_PAIR_INVENTORY")
        realized = self.capital_ledger.settle_return(
            capital_id,
            cycle_id=cycle_id,
            sold_quantity=sold_quantity,
            net_proceeds_usdt=net_proceeds_usdt,
            residual_mark_usdt=residual_mark_usdt,
            now_us=now_us,
            risk_exit_authorization_id=risk_exit_authorization_id,
            return_order_complete=return_order_complete,
        )
        self.state.inventory_quantity -= sold_quantity
        if self.state.inventory_quantity < ZERO:
            raise ValueError("M035_NEGATIVE_PAIR_INVENTORY")
        self.state.dust_quantity = self.capital_ledger.dust.quantity(
            self.state.pair_asset, pair_id=self.state.pair_id
        )
        if return_order_complete:
            self.state.cycle_history.append(cycle_id)
            self.state.realized_pnl += realized
        self._last_event_us = now_us
        return realized

    def hotline_at(self, time_us: int) -> D | None:
        rows = [
            value for observed_at, value in self.state.hotline_history if observed_at <= time_us
        ]
        return rows[-1] if rows else None


@dataclass(frozen=True)
class CycleRecord:
    cycle_id: str
    pair_id: str
    proceeds_usdt: D
    original_cost_basis_usdt: D
    fees_usdt: D
    execution_cost_usdt: D
    adverse_selection_usdt: D
    attributable_costs_usdt: D = ZERO
    risk_exit: bool = False

    @property
    def net_pnl_usdt(self) -> D:
        return (
            self.proceeds_usdt
            - self.original_cost_basis_usdt
            - self.fees_usdt
            - self.execution_cost_usdt
            - self.adverse_selection_usdt
            - self.attributable_costs_usdt
        )


class CycleAttributionLedger:
    """Cycle-local zero-loss classification; aggregate profit never cross-subsidizes."""

    def __init__(self) -> None:
        self.cycles: dict[str, CycleRecord] = {}

    def record(self, cycle: CycleRecord) -> None:
        if cycle.cycle_id in self.cycles or cycle.pair_id not in {"PAIR_A", "PAIR_B"}:
            raise ValueError("M035_INVALID_OR_DUPLICATE_CYCLE")
        self.cycles[cycle.cycle_id] = cycle

    @property
    def negative_closed_cycles(self) -> int:
        return sum(row.net_pnl_usdt < ZERO for row in self.cycles.values())

    @property
    def negative_risk_exits(self) -> int:
        return sum(row.risk_exit and row.net_pnl_usdt < ZERO for row in self.cycles.values())

    @property
    def aggregate_pnl_usdt(self) -> D:
        return sum((row.net_pnl_usdt for row in self.cycles.values()), ZERO)

    @property
    def zero_loss_cycle_pass(self) -> bool:
        return self.negative_closed_cycles == 0

    @property
    def zero_loss_economic_pass(self) -> bool:
        return self.zero_loss_cycle_pass and self.negative_risk_exits == 0


__all__ = [
    "AllocationCandidate",
    "AllocationGrant",
    "AllocationPriority",
    "CapitalPosition",
    "CapitalState",
    "CycleAttributionLedger",
    "CycleRecord",
    "DustConsumption",
    "DustLedger",
    "DustLot",
    "GlobalCapitalLedger",
    "OrderStatus",
    "PairEngine",
    "PairOrder",
    "PairState",
    "ParallelPairCapitalAllocator",
    "RiskExitAuthorization",
]
