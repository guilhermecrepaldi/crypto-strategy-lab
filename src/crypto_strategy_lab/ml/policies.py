from __future__ import annotations

import random
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray


class DiscretePolicy(Protocol):
    name: str

    def predict(self, observation: NDArray[np.float32], info: dict[str, Any]) -> int: ...


class CashPolicy:
    name = "cash"

    def predict(self, observation: NDArray[np.float32], info: dict[str, Any]) -> int:
        del observation, info
        return 0


class BuyAndHoldPolicy:
    def __init__(self, action: int) -> None:
        if action not in range(1, 5):
            raise ValueError("buy-and-hold action must identify one cryptoasset")
        self.action = action
        self.name = f"buy-and-hold-{action}"

    def predict(self, observation: NDArray[np.float32], info: dict[str, Any]) -> int:
        del observation, info
        return self.action


class DeterministicSequencePolicy:
    name = "deterministic-sequence"

    def __init__(self, actions: list[int]) -> None:
        self.actions = actions
        self.index = 0

    def predict(self, observation: NDArray[np.float32], info: dict[str, Any]) -> int:
        del observation, info
        if not self.actions:
            return 0
        action = self.actions[self.index % len(self.actions)]
        self.index += 1
        return action


class RandomPolicy:
    name = "random"

    def __init__(self, seed: int) -> None:
        self.random = random.Random(seed)

    def predict(self, observation: NDArray[np.float32], info: dict[str, Any]) -> int:
        del observation
        allowed = [index for index, allowed in enumerate(info.get("action_mask", [])) if allowed]
        return self.random.choice(allowed) if allowed else 0


class MomentumPolicy:
    name = "causal-momentum"

    def predict(self, observation: NDArray[np.float32], info: dict[str, Any]) -> int:
        del observation
        scores = {int(key): float(value) for key, value in info["momentum_by_action"].items()}
        mask = info.get("action_mask", [True] * 5)
        scores = {action: score for action, score in scores.items() if mask[action]}
        if not scores:
            return 0
        best_action, best_score = max(scores.items(), key=lambda item: (item[1], -item[0]))
        return best_action if best_score > 0 else 0


class StableBaselinesPolicy:
    def __init__(self, model: Any, name: str = "stable-baselines-model") -> None:
        self.model = model
        self.name = name

    def predict(self, observation: NDArray[np.float32], info: dict[str, Any]) -> int:
        del info
        action, _state = self.model.predict(observation, deterministic=True)
        return int(action)
