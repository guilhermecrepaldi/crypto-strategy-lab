from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from numpy.typing import NDArray

from crypto_strategy_lab.data.binance import validate_candle_sequence
from crypto_strategy_lab.data.temporal import TemporalMarketData
from crypto_strategy_lab.domain import Candle, Fill, canonical_hash
from crypto_strategy_lab.ml.features import FeatureNormalizer, FeaturePipeline
from crypto_strategy_lab.ml.partitions import EpisodeSampler, EpisodeWindow, TemporalPartition
from crypto_strategy_lab.ml.reward import RewardConfig, calculate_reward
from crypto_strategy_lab.simulation.portfolio import (
    ExecutionCosts,
    ExecutionRejected,
    SpotPortfolio,
)


@dataclass(frozen=True)
class EnvironmentConfig:
    initial_capital: Decimal = Decimal("80")
    max_exposure: Decimal = Decimal("0.75")
    reserve_ratio: Decimal = Decimal("0.25")
    ruin_ratio: Decimal = Decimal("0.20")
    warmup: timedelta = timedelta(minutes=30)
    episode_duration: timedelta = timedelta(minutes=30)
    costs: ExecutionCosts = field(default_factory=ExecutionCosts)
    reward: RewardConfig = field(default_factory=RewardConfig)


class CryptoRotationEnv(gym.Env[NDArray[np.float32], int]):
    metadata: dict[str, list[str]] = {"render_modes": []}  # noqa: RUF012

    def __init__(
        self,
        candles: list[Candle],
        partition: TemporalPartition,
        normalizer: FeatureNormalizer,
        config: EnvironmentConfig | None = None,
    ) -> None:
        super().__init__()
        gaps = validate_candle_sequence(candles)
        if gaps:
            raise ValueError("RL environment refuses datasets with gaps")
        self.config = config or EnvironmentConfig()
        self.partition = partition
        self.market = TemporalMarketData(candles)
        self.symbols = self.market.symbols
        if len(self.symbols) != 4:
            raise ValueError("Discrete(5) baseline requires four assets plus USDT")
        self.action_symbols: tuple[str | None, ...] = (None, *self.symbols)
        self.pipeline = FeaturePipeline(self.market, self.symbols)
        self.normalizer = normalizer
        self.sampler = EpisodeSampler(
            candles,
            partition,
            warmup=self.config.warmup,
            duration=self.config.episode_duration,
        )
        self.action_space = spaces.Discrete(5)
        self.observation_space = spaces.Box(
            low=-10.0,
            high=10.0,
            shape=(self.pipeline.observation_size,),
            dtype=np.float32,
        )
        self.dataset_hash = canonical_hash([item.model_dump(mode="json") for item in candles])
        self.window: EpisodeWindow | None = None
        self.portfolio: SpotPortfolio | None = None
        self.simulated_time: datetime | None = None
        self.previous_equity = self.config.initial_capital
        self.previous_action = 0
        self.time_in_position = 0
        self.transitions: list[dict[str, Any]] = []

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[NDArray[np.float32], dict[str, Any]]:
        super().reset(seed=seed)
        episode_seed = int(self.np_random.integers(0, 2**31 - 1)) if seed is None else seed
        explicit_start = (options or {}).get("episode_start")
        if isinstance(explicit_start, str):
            explicit_start = datetime.fromisoformat(explicit_start.replace("Z", "+00:00"))
        self.window = (
            self.sampler.explicit(explicit_start, episode_seed)
            if isinstance(explicit_start, datetime)
            else self.sampler.sample(episode_seed)
        )
        self.portfolio = SpotPortfolio(
            self.config.initial_capital,
            max_exposure=self.config.max_exposure,
            reserve_ratio=self.config.reserve_ratio,
        )
        self.simulated_time = self.window.start
        self.previous_equity = self.config.initial_capital
        self.previous_action = 0
        self.time_in_position = 0
        self.transitions = []
        observation = self._observation()
        return observation, self._base_info()

    def step(self, action: int) -> tuple[NDArray[np.float32], float, bool, bool, dict[str, Any]]:
        if not self.action_space.contains(action):
            raise ValueError(f"action {action} is outside Discrete(5)")
        portfolio, current_time, window = self._state()
        prices = self._prices_at(current_time, field="open")
        fills: list[Fill] = []
        failures: list[str] = []
        constraint_violated = False
        current_action = self._current_action()
        target_symbol = self.action_symbols[action]
        try:
            if action == current_action:
                pass
            elif target_symbol is None and portfolio.state.asset_symbol:
                fills.append(
                    portfolio.sell(
                        symbol=portfolio.state.asset_symbol,
                        market_price=prices[portfolio.state.asset_symbol],
                        simulated_time=current_time,
                        costs=self.config.costs,
                    )
                )
            elif target_symbol is not None and portfolio.state.asset_symbol is None:
                fills.append(
                    portfolio.buy(
                        symbol=target_symbol,
                        market_price=prices[target_symbol],
                        allocation_percent=self.config.max_exposure * Decimal("100"),
                        simulated_time=current_time,
                        costs=self.config.costs,
                        marks=prices,
                    )
                )
            elif target_symbol is not None and portfolio.state.asset_symbol:
                rotation = portfolio.rotate(
                    from_symbol=portfolio.state.asset_symbol,
                    to_symbol=target_symbol,
                    prices=prices,
                    allocation_percent=self.config.max_exposure * Decimal("100"),
                    simulated_time=current_time,
                    costs=self.config.costs,
                )
                fills.extend(rotation.fills)
                failures.extend(rotation.failures)
        except (ExecutionRejected, KeyError) as error:
            failures.append(str(error))
            constraint_violated = True

        next_time = current_time + timedelta(minutes=15)
        marks = self._prices_at(next_time - timedelta(minutes=5), field="close")
        snapshot = portfolio.snapshot(marks)
        equity = Decimal(str(snapshot["equity_usdt"]))
        turnover = sum((fill.quote_value for fill in fills), Decimal("0")) / self.previous_equity
        ruined = equity <= self.config.initial_capital * self.config.ruin_ratio
        reward = calculate_reward(
            previous_equity=self.previous_equity,
            equity=equity,
            drawdown=Decimal(str(snapshot["drawdown"])),
            turnover=turnover,
            constraint_violated=constraint_violated,
            ruined=ruined,
            config=self.config.reward,
        )
        self.simulated_time = next_time
        self.previous_equity = equity
        self.time_in_position = self.time_in_position + 1 if action == current_action else 0
        self.previous_action = action
        terminated = ruined
        truncated = next_time >= window.end
        info = self._base_info()
        info.update(
            {
                "action": action,
                "target_symbol": target_symbol or "USDT",
                "fills": [item.model_dump(mode="json") for item in fills],
                "failures": failures,
                "costs_usdt": str(sum((fill.fee for fill in fills), Decimal("0"))),
                "turnover": str(turnover),
                "equity_usdt": str(equity),
                "drawdown": str(snapshot["drawdown"]),
                "portfolio": {key: str(value) for key, value in snapshot.items()},
                "reward": reward.as_dict(),
                "termination_reason": "RUIN" if terminated else "TIME_LIMIT" if truncated else None,
                "terminated": terminated,
                "truncated": truncated,
            }
        )
        observation = self._observation()
        info["observation_hash"] = canonical_hash(observation.tolist())
        self.transitions.append(info.copy())
        return observation, float(reward.total), terminated, truncated, info

    def checkpoint(self) -> dict[str, Any]:
        _, current_time, window = self._state()
        return {
            "dataset_hash": self.dataset_hash,
            "partition": self.partition.name,
            "window": window.model_dump(mode="json"),
            "simulated_time": current_time.isoformat(),
            "actions": [item["action"] for item in self.transitions],
            "transition_hash": canonical_hash(self.transitions),
        }

    def _state(self) -> tuple[SpotPortfolio, datetime, EpisodeWindow]:
        if self.portfolio is None or self.simulated_time is None or self.window is None:
            raise RuntimeError("reset must be called before step")
        return self.portfolio, self.simulated_time, self.window

    def _current_action(self) -> int:
        portfolio, _, _ = self._state()
        if portfolio.state.asset_symbol is None:
            return 0
        return self.action_symbols.index(portfolio.state.asset_symbol)

    def _prices_at(self, open_time: datetime, *, field: str) -> dict[str, Decimal]:
        prices: dict[str, Decimal] = {}
        for candle in self.market.all_5m():
            if candle.open_time == open_time:
                prices[candle.symbol] = getattr(candle, field)
        if set(prices) != set(self.symbols):
            raise ExecutionRejected(f"missing complete price event at {open_time.isoformat()}")
        return prices

    def _observation(self) -> NDArray[np.float32]:
        portfolio, current_time, _ = self._state()
        previous_marks = self._prices_at(current_time - timedelta(minutes=5), field="close")
        snapshot = portfolio.snapshot(previous_marks)
        raw = self.pipeline.raw_observation(
            simulated_time=current_time,
            position_index=self._current_action(),
            equity=Decimal(str(snapshot["equity_usdt"])),
            initial_equity=self.config.initial_capital,
            drawdown=Decimal(str(snapshot["drawdown"])),
            time_in_position=self.time_in_position,
            costs=portfolio.state.fees,
            previous_action=self.previous_action,
        )
        return self.normalizer.transform(raw)

    def _base_info(self) -> dict[str, Any]:
        portfolio, current_time, window = self._state()
        return {
            "simulated_time": current_time.isoformat(),
            "available_data_until": (current_time - timedelta(microseconds=1)).isoformat(),
            "partition": self.partition.name,
            "episode_start": window.start.isoformat(),
            "episode_end": window.end.isoformat(),
            "seed": window.seed,
            "action_mapping": {
                str(index): symbol or "USDT" for index, symbol in enumerate(self.action_symbols)
            },
            "position": portfolio.state.asset_symbol or "USDT",
            "momentum_by_action": self._momentum(),
        }

    def _momentum(self) -> dict[int, float]:
        _, current_time, _ = self._state()
        scores: dict[int, float] = {0: 0.0}
        for index, symbol in enumerate(self.symbols, start=1):
            visible = self.market.visible_candles(
                symbol,
                simulated_time=current_time,
                available_until=current_time - timedelta(microseconds=1),
                lookback=timedelta(minutes=20),
            )
            scores[index] = (
                float(visible[-1].close / visible[0].close - 1) if len(visible) >= 2 else 0.0
            )
        return scores


def replay_episode(
    env: CryptoRotationEnv,
    *,
    actions: list[int],
    seed: int,
    episode_start: datetime,
) -> list[dict[str, Any]]:
    env.reset(seed=seed, options={"episode_start": episode_start})
    for action in actions:
        _, _, terminated, truncated, _ = env.step(action)
        if terminated or truncated:
            break
    return env.transitions.copy()
