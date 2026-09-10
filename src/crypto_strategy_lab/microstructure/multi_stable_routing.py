"""Explainable marginal scoring and physical 2-4 asset route lifecycle for M032."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise, permutations
from math import prod

from crypto_strategy_lab.microstructure.multi_stable_ledger import SlotLedger
from crypto_strategy_lab.microstructure.multi_stable_models import (
    ZERO,
    D,
    PhysicalFill,
    RouteCandidate,
    RouteLeg,
    RouteProgress,
    ScoreBreakdown,
)


@dataclass(frozen=True)
class MarginalOpportunity:
    candidate_id: str
    priority_class: int
    expected_net_pnl: D
    probability_of_completion: D
    capital: D
    expected_lock_seconds: D
    stablecoin_safety: D
    inventory_risk_penalty: D = ZERO
    lost_fifo_value: D = ZERO


class PairProductivityScorer:
    """Score marginal capital without hiding its economic decomposition."""

    @staticmethod
    def score(opportunity: MarginalOpportunity) -> ScoreBreakdown:
        if opportunity.priority_class < 1:
            raise ValueError("M032_INVALID_PRIORITY_CLASS")
        unit_values = (
            opportunity.probability_of_completion,
            opportunity.stablecoin_safety,
            opportunity.inventory_risk_penalty,
        )
        if any(value < ZERO or value > D(1) for value in unit_values):
            raise ValueError("M032_SCORE_COMPONENT_OUT_OF_RANGE")
        if opportunity.lost_fifo_value < ZERO:
            raise ValueError("M032_NEGATIVE_FIFO_VALUE")
        if opportunity.capital <= ZERO or opportunity.expected_lock_seconds <= ZERO:
            raise ValueError("M032_INVALID_SCORE_DENOMINATOR")
        gross = (
            opportunity.expected_net_pnl
            * opportunity.probability_of_completion
            * opportunity.stablecoin_safety
        )
        penalty = opportunity.inventory_risk_penalty + opportunity.lost_fifo_value
        score = (gross - penalty) / (opportunity.capital * opportunity.expected_lock_seconds)
        return ScoreBreakdown(
            candidate_id=opportunity.candidate_id,
            priority_class=opportunity.priority_class,
            expected_net_pnl=opportunity.expected_net_pnl,
            probability_of_completion=opportunity.probability_of_completion,
            capital=opportunity.capital,
            expected_lock_seconds=opportunity.expected_lock_seconds,
            stablecoin_safety=opportunity.stablecoin_safety,
            inventory_risk_penalty=opportunity.inventory_risk_penalty,
            lost_fifo_value=opportunity.lost_fifo_value,
            score=score,
        )

    def rank(self, opportunities: list[MarginalOpportunity]) -> list[ScoreBreakdown]:
        scored = [self.score(row) for row in opportunities]
        return sorted(scored, key=lambda row: (row.priority_class, -row.score, row.candidate_id))


class RouteEnumerator:
    """Enumerate simple directed cycles with two to four distinct stablecoins."""

    def __init__(self, markets: dict[tuple[str, str], str]) -> None:
        self.markets = dict(markets)

    def enumerate(self, origin_asset: str, assets: set[str]) -> list[RouteCandidate]:
        if origin_asset not in assets or len(assets) > 4:
            raise ValueError("M032_INVALID_STABLECOIN_UNIVERSE")
        candidates: list[RouteCandidate] = []
        others = sorted(assets - {origin_asset})
        for distinct_assets in range(2, min(4, len(assets)) + 1):
            for middle in permutations(others, distinct_assets - 1):
                path = (origin_asset, *middle, origin_asset)
                legs: list[RouteLeg] = []
                for left, right in pairwise(path):
                    symbol = self.markets.get((left, right))
                    if symbol is None:
                        break
                    legs.append(RouteLeg(symbol, left, right, True))
                if len(legs) != distinct_assets:
                    continue
                route_id = "->".join(path)
                candidates.append(RouteCandidate(route_id, origin_asset, tuple(legs)))
        return sorted(candidates, key=lambda row: (len(row.legs), row.route_id))


@dataclass(frozen=True)
class RouteScore:
    route_id: str
    expected_leg_wait_seconds: tuple[D, ...]
    expected_total_cycle_time: D
    probability_all_legs_complete: D
    expected_net_pnl: D
    expected_capital_lock: D
    route_score: D


class RouteScorer:
    @staticmethod
    def score(
        candidate: RouteCandidate,
        *,
        leg_wait_seconds: tuple[D, ...],
        leg_completion_probabilities: tuple[D, ...],
        expected_net_pnl: D,
        capital: D,
    ) -> RouteScore:
        if len(leg_wait_seconds) != len(candidate.legs) or len(leg_completion_probabilities) != len(
            candidate.legs
        ):
            raise ValueError("M032_ROUTE_SCORE_LEG_COUNT_MISMATCH")
        if capital <= ZERO or any(wait <= ZERO for wait in leg_wait_seconds):
            raise ValueError("M032_INVALID_ROUTE_SCORE_DENOMINATOR")
        if any(
            probability < ZERO or probability > D(1) for probability in leg_completion_probabilities
        ):
            raise ValueError("M032_INVALID_ROUTE_PROBABILITY")
        total_time = sum(leg_wait_seconds, ZERO)
        probability = D(str(prod(leg_completion_probabilities)))
        expected_lock = capital * total_time
        score = expected_net_pnl * probability / expected_lock
        return RouteScore(
            route_id=candidate.route_id,
            expected_leg_wait_seconds=leg_wait_seconds,
            expected_total_cycle_time=total_time,
            probability_all_legs_complete=probability,
            expected_net_pnl=expected_net_pnl,
            expected_capital_lock=expected_lock,
            route_score=score,
        )


class CycleManager:
    """Count a cycle only after every route leg has a unique physical fill."""

    def __init__(self, ledger: SlotLedger) -> None:
        self.ledger = ledger
        self.routes: dict[str, RouteProgress] = {}
        self.closed_cycles: list[str] = []

    def start(
        self,
        candidate: RouteCandidate,
        *,
        execution_id: str,
        slot_id: str,
        quantity: D,
        now_us: int,
    ) -> RouteProgress:
        if execution_id in self.routes:
            raise ValueError("M032_DUPLICATE_ROUTE_EXECUTION_ID")
        if self.ledger.slots[slot_id].origin_asset != candidate.origin_asset:
            raise ValueError("M032_ROUTE_SLOT_ORIGIN_MISMATCH")
        progress = RouteProgress(
            execution_id=execution_id,
            candidate=candidate,
            slot_id=slot_id,
            initial_quantity=quantity,
            current_asset=candidate.origin_asset,
            current_quantity=quantity,
            started_at_us=now_us,
            leg_input_remaining=quantity,
        )
        self.routes[execution_id] = progress
        self.ledger.slots[slot_id].route_id = execution_id
        return progress

    def record_fill(self, execution_id: str, reservation_id: str, fill: PhysicalFill) -> bool:
        progress = self.routes[execution_id]
        if progress.next_leg_index >= len(progress.candidate.legs):
            raise ValueError("M032_ROUTE_ALREADY_CLOSED")
        leg = progress.candidate.legs[progress.next_leg_index]
        reservation = self.ledger.reservations[reservation_id]
        if (
            fill.fill_id in progress.completed_fill_ids
            or reservation.slot_id != progress.slot_id
            or fill.symbol != leg.symbol
            or fill.from_asset != progress.current_asset
            or fill.to_asset != leg.to_asset
            or fill.input_quantity > progress.leg_input_remaining
            or fill.time_us < progress.started_at_us
        ):
            raise ValueError("M032_ROUTE_FILL_DOES_NOT_MATCH_NEXT_LEG")
        self.ledger.apply_fill(reservation_id, fill)
        progress.completed_fill_ids.append(fill.fill_id)
        progress.fees_by_asset[fill.fee_asset] = (
            progress.fees_by_asset.get(fill.fee_asset, ZERO) + fill.fee_quantity
        )
        progress.leg_input_remaining -= fill.input_quantity
        progress.leg_output_accumulated += fill.output_quantity_net
        if progress.leg_input_remaining > ZERO:
            return False
        progress.current_asset = fill.to_asset
        progress.current_quantity = progress.leg_output_accumulated
        progress.next_leg_index += 1
        if progress.next_leg_index < len(progress.candidate.legs):
            progress.leg_input_remaining = progress.current_quantity
            progress.leg_output_accumulated = ZERO
            return False
        if progress.current_asset != progress.candidate.origin_asset:
            raise ValueError("M032_COMPLETED_ROUTE_NOT_IN_ORIGIN_ASSET")
        pnl = progress.current_quantity - progress.initial_quantity
        if pnl < ZERO:
            raise ValueError("M032_NEGATIVE_REALIZED_EXIT_PROHIBITED")
        progress.realized_pnl_origin = pnl
        progress.closed_at_us = fill.time_us
        self.ledger.close_slot(
            progress.slot_id,
            origin_quantity=progress.initial_quantity,
            now_us=fill.time_us,
            cycle_id=execution_id,
        )
        self.closed_cycles.append(execution_id)
        return True


__all__ = [
    "CycleManager",
    "MarginalOpportunity",
    "PairProductivityScorer",
    "RouteEnumerator",
    "RouteScore",
    "RouteScorer",
]
