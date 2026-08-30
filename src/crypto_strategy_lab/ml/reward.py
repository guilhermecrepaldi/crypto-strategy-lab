from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RewardConfig:
    version: str = "log-equity-v1"
    drawdown_coefficient: Decimal = Decimal("0.01")
    turnover_coefficient: Decimal = Decimal("0.001")
    constraint_violation_penalty: Decimal = Decimal("0.01")
    ruin_penalty: Decimal = Decimal("0.10")


@dataclass(frozen=True)
class RewardBreakdown:
    base_reward: Decimal
    drawdown_penalty: Decimal
    turnover_penalty: Decimal
    constraint_violation_penalty: Decimal
    terminal_penalty: Decimal

    @property
    def total(self) -> Decimal:
        return (
            self.base_reward
            - self.drawdown_penalty
            - self.turnover_penalty
            - self.constraint_violation_penalty
            - self.terminal_penalty
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "base_reward": str(self.base_reward),
            "drawdown_penalty": str(self.drawdown_penalty),
            "turnover_penalty": str(self.turnover_penalty),
            "constraint_violation_penalty": str(self.constraint_violation_penalty),
            "terminal_penalty": str(self.terminal_penalty),
            "total": str(self.total),
        }


def calculate_reward(
    *,
    previous_equity: Decimal,
    equity: Decimal,
    drawdown: Decimal,
    turnover: Decimal,
    constraint_violated: bool,
    ruined: bool,
    config: RewardConfig,
) -> RewardBreakdown:
    base = Decimal("0") if previous_equity <= 0 or equity <= 0 else (equity / previous_equity).ln()
    return RewardBreakdown(
        base_reward=base,
        drawdown_penalty=drawdown * config.drawdown_coefficient,
        turnover_penalty=turnover * config.turnover_coefficient,
        constraint_violation_penalty=(
            config.constraint_violation_penalty if constraint_violated else Decimal("0")
        ),
        terminal_penalty=config.ruin_penalty if ruined else Decimal("0"),
    )
