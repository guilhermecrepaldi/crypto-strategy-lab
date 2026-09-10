"""Deterministic policy shell for M032's adaptive multi-stable capital manager."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR

from crypto_strategy_lab.microstructure.multi_stable_ledger import SlotLedger
from crypto_strategy_lab.microstructure.multi_stable_models import (
    ZERO,
    ColumnRole,
    D,
    EconomicSlot,
    ScoreBreakdown,
    SlotState,
    StablecoinEvidence,
    SymbolRule,
)
from crypto_strategy_lab.microstructure.multi_stable_routing import (
    MarginalOpportunity,
    PairProductivityScorer,
)

MAX_RANK = 7
MAX_COLUMNS = 2


def zone_for_rank(rank: int) -> str:
    if rank in {1, 2, 3}:
        return "HOT"
    if rank in {4, 5}:
        return "MID"
    if rank in {6, 7}:
        return "FAR"
    raise ValueError("M032_RANK_OUT_OF_RANGE")


def column_role(column: int) -> ColumnRole:
    if column == 1:
        return ColumnRole.PERSISTENT_QUEUE
    if column == 2:
        return ColumnRole.OPPORTUNITY
    raise ValueError("M032_COLUMN_OUT_OF_RANGE")


def priority_class(*, obligation: bool, rank: int, column: int, old_zero_fill: bool) -> int:
    if obligation:
        return 1
    if old_zero_fill:
        return 8
    zone = zone_for_rank(rank)
    return {
        ("HOT", 1): 2,
        ("HOT", 2): 3,
        ("MID", 1): 4,
        ("MID", 2): 5,
        ("FAR", 1): 6,
        ("FAR", 2): 7,
    }[(zone, column)]


@dataclass(frozen=True)
class PegGuard:
    max_deviation: D
    max_spread: D
    min_depth_usd: D

    def allows_entry(
        self,
        *,
        peg_deviation: D,
        spread: D,
        depth_usd: D,
        data_gap: bool,
    ) -> bool:
        return (
            not data_gap
            and abs(peg_deviation) <= self.max_deviation
            and spread <= self.max_spread
            and depth_usd >= self.min_depth_usd
        )


@dataclass
class BookState:
    symbol: str
    hotline: D
    tick_size: D
    updated_at_us: int
    crossed_ticks: int = 0
    reconciliations: int = 0


class StablecoinUniverse:
    def __init__(self, evidence: list[StablecoinEvidence], *, minimum_safety: D) -> None:
        if len(evidence) > 4:
            raise ValueError("M032_MAX_FOUR_STABLECOINS")
        self.evidence = {row.asset: row for row in evidence}
        if len(self.evidence) != len(evidence):
            raise ValueError("M032_DUPLICATE_STABLECOIN")
        self.minimum_safety = minimum_safety

    @property
    def eligible_assets(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                asset
                for asset, evidence in self.evidence.items()
                if evidence.safety_score >= self.minimum_safety
            )
        )


class AdaptiveColumnAllocator:
    """Select cells by immutable priority class, then explainable marginal score."""

    def __init__(self, scorer: PairProductivityScorer | None = None) -> None:
        self.scorer = scorer or PairProductivityScorer()

    def choose(
        self, opportunities: list[MarginalOpportunity], *, available_capital: D
    ) -> list[ScoreBreakdown]:
        selected: list[ScoreBreakdown] = []
        left = available_capital
        for row in self.scorer.rank(opportunities):
            if row.score <= ZERO or row.capital > left:
                continue
            selected.append(row)
            left -= row.capital
        return selected


class AdaptiveCapitalOrderManager:
    """Coordinate geometry, safety and ACK-gated reclaim without matching trades."""

    def __init__(
        self,
        *,
        ledger: SlotLedger,
        rules: dict[str, SymbolRule],
        universe: StablecoinUniverse,
        peg_guard: PegGuard,
    ) -> None:
        self.ledger = ledger
        self.rules = dict(rules)
        self.universe = universe
        self.peg_guard = peg_guard
        self.books: dict[str, BookState] = {}
        self.reclaim_reasons: list[dict[str, object]] = []

    def update_hotline(self, symbol: str, *, midpoint: D, now_us: int) -> BookState:
        rule = self.rules[symbol]
        target = (midpoint / rule.tick_size).to_integral_value(
            rounding=ROUND_FLOOR
        ) * rule.tick_size
        current = self.books.get(symbol)
        if current is None:
            current = BookState(symbol, target, rule.tick_size, now_us, 0, 1)
            self.books[symbol] = current
            return current
        if now_us < current.updated_at_us:
            raise ValueError("M032_NONCAUSAL_HOTLINE_UPDATE")
        crossed = int(abs(target - current.hotline) / rule.tick_size)
        if crossed:
            current.hotline = target
            current.crossed_ticks += crossed
            current.reconciliations += 1
        current.updated_at_us = now_us
        return current

    def configure_slot_cell(
        self,
        slot_id: str,
        *,
        symbol: str,
        side: str,
        price: D,
        rank: int,
        column: int,
        quantity: D,
        now_us: int,
    ) -> EconomicSlot:
        rule = self.rules[symbol]
        rule.validate_order(price=price, quantity=quantity, time_us=now_us)
        slot = self.ledger.slots[slot_id]
        slot.book = symbol
        slot.side = side
        slot.price = price
        slot.band_rank = rank
        slot.column = column
        column_role(column)
        zone_for_rank(rank)
        return slot

    @staticmethod
    def c1_value_of_queue_position(
        *,
        expected_net_pnl: D,
        fill_probability_5m: D,
        expected_clear_seconds: D | None,
    ) -> D:
        if expected_clear_seconds is None or expected_clear_seconds <= ZERO:
            return ZERO
        return expected_net_pnl * fill_probability_5m / expected_clear_seconds

    def reclaimable(
        self,
        slot_id: str,
        *,
        alternative_score: D,
        queue_position_value: D,
        reason: str,
        now_us: int,
    ) -> bool:
        slot = self.ledger.slots[slot_id]
        if slot.state in {SlotState.PARTIAL, SlotState.FILLED, SlotState.RETURN}:
            return False
        if slot.filled_qty > ZERO:
            return False
        if slot.column == 1 and alternative_score <= queue_position_value:
            return False
        allowed = reason in {
            "OLD_FREE_OUTSIDE_ACTIVE_REGION",
            "LOW_MARGINAL_SCORE",
            "BETTER_ROUTE_AVAILABLE",
            "C2_OPPORTUNITY_EXPIRED",
        }
        if allowed:
            self.reclaim_reasons.append(
                {
                    "slot_id": slot_id,
                    "reason": reason,
                    "time_us": now_us,
                    "alternative_score": str(alternative_score),
                    "queue_position_value": str(queue_position_value),
                }
            )
        return allowed


__all__ = [
    "MAX_COLUMNS",
    "MAX_RANK",
    "AdaptiveCapitalOrderManager",
    "AdaptiveColumnAllocator",
    "BookState",
    "PegGuard",
    "StablecoinUniverse",
    "column_role",
    "priority_class",
    "zone_for_rank",
]
