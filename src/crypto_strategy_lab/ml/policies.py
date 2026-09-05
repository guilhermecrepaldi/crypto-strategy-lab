from __future__ import annotations

import random
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from crypto_strategy_lab.data.temporal import TemporalMarketData


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


class CostAwareMomentum24hPolicy:
    """Auditable 24-hour momentum rotation using only fully closed 5m candles."""

    name = "cost-aware-momentum-24h-v1"
    lookback = timedelta(hours=24)
    candle_interval = timedelta(minutes=5)
    required_candles = 289

    def __init__(
        self,
        market: TemporalMarketData,
        *,
        hurdle: Decimal = Decimal("0.0056"),
        decision_hours: tuple[int, ...] = (0, 4, 8, 12, 16, 20),
    ) -> None:
        if hurdle <= 0:
            raise ValueError("momentum hurdle must be positive")
        if not decision_hours or any(hour not in range(24) for hour in decision_hours):
            raise ValueError("decision hours must be valid UTC hours")
        self.market = market
        self.hurdle = hurdle
        self.decision_hours = tuple(sorted(set(decision_hours)))
        self.decisions: list[dict[str, Any]] = []

    def predict(self, observation: NDArray[np.float32], info: dict[str, Any]) -> int:
        del observation
        simulated_time = datetime.fromisoformat(str(info["simulated_time"]).replace("Z", "+00:00"))
        current_action = self._current_action(info)
        if not self._is_decision_time(simulated_time):
            return current_action

        available_until = datetime.fromisoformat(
            str(info["available_data_until"]).replace("Z", "+00:00")
        )
        mask = [bool(value) for value in info.get("action_mask", [True] * 5)]
        scores, unavailable = self._scores(info, simulated_time, available_until)
        if unavailable:
            requested = 0 if current_action != 0 and mask[0] else current_action
            self._record(simulated_time, current_action, requested, scores, unavailable)
            return requested

        btc_momentum = scores[1]
        if current_action != 0 and (
            btc_momentum < -self.hurdle or scores[current_action] < -self.hurdle
        ):
            requested = 0 if mask[0] else current_action
            self._record(simulated_time, current_action, requested, scores, None)
            return requested

        eligible = {
            action: score
            for action, score in scores.items()
            if action != 0 and mask[action] and score > self.hurdle
        }
        if current_action == 0:
            requested = (
                max(eligible, key=lambda action: (eligible[action], -action))
                if btc_momentum > self.hurdle and eligible
                else 0
            )
        elif btc_momentum > self.hurdle and eligible:
            candidate = max(eligible, key=lambda action: (eligible[action], -action))
            requested = (
                candidate
                if candidate != current_action
                and scores[candidate] - scores[current_action] > self.hurdle
                else current_action
            )
        else:
            requested = current_action
        self._record(simulated_time, current_action, requested, scores, None)
        return requested

    def _scores(
        self,
        info: dict[str, Any],
        simulated_time: datetime,
        available_until: datetime,
    ) -> tuple[dict[int, Decimal], str | None]:
        mapping = {int(key): str(value) for key, value in info["action_mapping"].items()}
        expected_start = simulated_time - self.candle_interval - self.lookback
        expected_times = [
            expected_start + index * self.candle_interval for index in range(self.required_candles)
        ]
        scores: dict[int, Decimal] = {0: Decimal("0")}
        for action in range(1, 5):
            symbol = mapping[action]
            candles = self.market.visible_candles(
                symbol,
                simulated_time=simulated_time,
                available_until=available_until,
                lookback=self.lookback + self.candle_interval,
            )
            selected = [item for item in candles if item.open_time in set(expected_times)]
            if len(selected) != self.required_candles:
                return scores, f"INCOMPLETE_24H_WINDOW:{symbol}"
            selected.sort(key=lambda item: item.open_time)
            if [item.open_time for item in selected] != expected_times:
                return scores, f"NON_CONTIGUOUS_24H_WINDOW:{symbol}"
            if any(
                item.close_time >= simulated_time
                or item.available_at >= simulated_time
                or not item.close.is_finite()
                or item.close <= 0
                for item in selected
            ):
                return scores, f"INVALID_24H_WINDOW:{symbol}"
            scores[action] = selected[-1].close / selected[0].close - 1
        return scores, None

    def _current_action(self, info: dict[str, Any]) -> int:
        position = str(info["position"])
        mapping = {int(key): str(value) for key, value in info["action_mapping"].items()}
        return next((action for action, symbol in mapping.items() if symbol == position), 0)

    def _is_decision_time(self, value: datetime) -> bool:
        return (
            value.hour in self.decision_hours
            and value.minute == 0
            and value.second == 0
            and value.microsecond == 0
        )

    def _record(
        self,
        simulated_time: datetime,
        current_action: int,
        requested_action: int,
        scores: dict[int, Decimal],
        unavailable_reason: str | None,
    ) -> None:
        self.decisions.append(
            {
                "simulated_time": simulated_time.isoformat(),
                "current_action": current_action,
                "requested_action": requested_action,
                "momentum_by_action": {
                    str(action): str(value) for action, value in sorted(scores.items())
                },
                "unavailable_reason": unavailable_reason,
            }
        )


class StableBaselinesPolicy:
    def __init__(self, model: Any, name: str = "stable-baselines-model") -> None:
        self.model = model
        self.name = name

    def predict(self, observation: NDArray[np.float32], info: dict[str, Any]) -> int:
        del info
        action, _state = self.model.predict(observation, deterministic=True)
        return int(action)
