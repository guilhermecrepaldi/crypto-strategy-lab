from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_strategy_lab.simulation.portfolio import ExecutionCosts


@dataclass(frozen=True)
class TurnoverControlConfig:
    """Versioned execution gates. Every gate is causal and may be disabled explicitly."""

    version: str = "turnover-controls-v1"
    enabled: bool = False
    action_masking: bool = True
    minimum_hold_steps: int = 0
    cooldown_steps: int = 0
    minimum_edge_after_costs: Decimal = Decimal("0")
    minimum_notional_usdt: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.minimum_hold_steps < 0 or self.cooldown_steps < 0:
            raise ValueError("hold and cooldown steps cannot be negative")
        if self.minimum_edge_after_costs < 0 or self.minimum_notional_usdt < 0:
            raise ValueError("edge and notional controls cannot be negative")


def estimated_rotation_cost_rate(costs: ExecutionCosts) -> Decimal:
    """Conservative sell+buy rate, expressed as a fraction rather than bps."""

    return costs.fee_rate * Decimal("2") + costs.spread_rate + costs.slippage_rate * Decimal("2")
