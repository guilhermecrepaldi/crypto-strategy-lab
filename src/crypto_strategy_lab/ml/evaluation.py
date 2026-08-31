from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from crypto_strategy_lab.ml.environment import CryptoRotationEnv
from crypto_strategy_lab.ml.policies import (
    BuyAndHoldPolicy,
    CashPolicy,
    DiscretePolicy,
    MomentumPolicy,
    RandomPolicy,
)


@dataclass(frozen=True)
class EvaluationResult:
    policy: str
    seed: int
    episode_start: str
    episode_end: str
    actions: list[int]
    transitions: list[dict[str, Any]]
    final_equity_usdt: Decimal
    total_reward: Decimal
    terminated: bool
    truncated: bool


class EvaluationRunner:
    def run(
        self,
        env: CryptoRotationEnv,
        policy: DiscretePolicy,
        *,
        seed: int,
        episode_start: str | None = None,
    ) -> EvaluationResult:
        options = {"episode_start": episode_start} if episode_start else None
        observation, info = env.reset(seed=seed, options=options)
        actions: list[int] = []
        total_reward = Decimal("0")
        terminated = truncated = False
        while not (terminated or truncated):
            action = policy.predict(observation, info)
            actions.append(action)
            observation, reward, terminated, truncated, info = env.step(action)
            total_reward += Decimal(str(reward))
        return EvaluationResult(
            policy=policy.name,
            seed=seed,
            episode_start=str(info["episode_start"]),
            episode_end=str(info["episode_end"]),
            actions=actions,
            transitions=env.transitions.copy(),
            final_equity_usdt=Decimal(str(info["equity_usdt"])),
            total_reward=total_reward,
            terminated=terminated,
            truncated=truncated,
        )

    def baselines(self, env_factory: Any, *, seed: int) -> list[EvaluationResult]:
        policies: list[DiscretePolicy] = [
            CashPolicy(),
            *(BuyAndHoldPolicy(action) for action in range(1, 5)),
            MomentumPolicy(),
            RandomPolicy(seed),
        ]
        return [self.run(env_factory(), policy, seed=seed) for policy in policies]


def evaluate_action_sequence(
    env: CryptoRotationEnv,
    actions: list[int],
    *,
    seed: int,
    episode_start: str,
) -> EvaluationResult:
    observation, info = env.reset(seed=seed, options={"episode_start": episode_start})
    del observation
    total_reward = Decimal("0")
    terminated = truncated = False
    executed: list[int] = []
    for action in actions:
        _, reward, terminated, truncated, info = env.step(action)
        total_reward += Decimal(str(reward))
        executed.append(action)
        if terminated or truncated:
            break
    return EvaluationResult(
        policy="costless-action-replay",
        seed=seed,
        episode_start=str(info["episode_start"]),
        episode_end=str(info["episode_end"]),
        actions=executed,
        transitions=env.transitions.copy(),
        final_equity_usdt=Decimal(str(info["equity_usdt"])),
        total_reward=total_reward,
        terminated=terminated,
        truncated=truncated,
    )
