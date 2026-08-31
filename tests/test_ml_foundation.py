from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest
from pydantic import ValidationError
from stable_baselines3.common.env_checker import check_env

from crypto_strategy_lab.data.temporal import TemporalMarketData
from crypto_strategy_lab.ml.controls import TurnoverControlConfig
from crypto_strategy_lab.ml.environment import (
    CryptoRotationEnv,
    EnvironmentConfig,
    replay_episode,
)
from crypto_strategy_lab.ml.features import FeaturePipeline, fit_train_normalizer
from crypto_strategy_lab.ml.partitions import (
    EpisodeSampler,
    PartitionManifest,
    PartitionName,
    TemporalPartition,
)


def _partition(candles, name: PartitionName = PartitionName.TRAIN) -> TemporalPartition:
    return TemporalPartition(
        name=name,
        start=min(item.open_time for item in candles),
        end=max(item.close_time for item in candles) + timedelta(microseconds=1),
    )


def _environment(candles, *, ruin_ratio: Decimal = Decimal("0.20")) -> CryptoRotationEnv:
    partition = _partition(candles)
    market = TemporalMarketData(candles)
    pipeline = FeaturePipeline(market, market.symbols)
    normalizer = fit_train_normalizer(pipeline, partition, Decimal("80"))
    return CryptoRotationEnv(
        candles,
        partition,
        normalizer,
        EnvironmentConfig(
            warmup=timedelta(minutes=30),
            episode_duration=timedelta(minutes=30),
            ruin_ratio=ruin_ratio,
        ),
    )


def test_partitions_reject_overlap_and_sampler_stays_inside_train(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    partition = _partition(candles)
    with pytest.raises(ValidationError, match="overlap"):
        PartitionManifest(partitions=[partition, partition])
    validation = TemporalPartition(
        name=PartitionName.VALIDATION,
        start=partition.end,
        end=partition.end + timedelta(days=1),
    )
    locked = TemporalPartition(
        name=PartitionName.LOCKED_TEST,
        start=validation.end,
        end=validation.end + timedelta(days=1),
    )
    manifest = PartitionManifest(partitions=[locked, partition, validation])
    assert {item.name for item in manifest.partitions} == {
        PartitionName.TRAIN,
        PartitionName.VALIDATION,
        PartitionName.LOCKED_TEST,
    }

    sampler = EpisodeSampler(
        candles,
        partition,
        warmup=timedelta(minutes=30),
        duration=timedelta(minutes=30),
    )
    first = sampler.sample(42)
    assert first == sampler.sample(42)
    assert partition.start <= first.warmup_start < first.start < first.end <= partition.end
    assert {sampler.sample(seed).start for seed in range(20)} == set(sampler.valid_starts)


def test_features_are_causal_and_normalizer_is_train_only(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    partition = _partition(candles)
    market = TemporalMarketData(candles)
    pipeline = FeaturePipeline(market, market.symbols)
    normalizer = fit_train_normalizer(pipeline, partition, Decimal("80"))
    time = partition.start + timedelta(minutes=45)
    kwargs = {
        "simulated_time": time,
        "position_index": 0,
        "equity": Decimal("80"),
        "initial_equity": Decimal("80"),
        "drawdown": Decimal("0"),
        "time_in_position": 0,
        "costs": Decimal("0"),
        "previous_action": 0,
    }
    before = pipeline.raw_observation(**kwargs)
    changed_future = [
        candle.model_copy(
            update={
                "close": candle.close * Decimal("100"),
                "high": candle.high * Decimal("100"),
            }
        )
        if candle.open_time >= time
        else candle
        for candle in candles
    ]
    future_market = TemporalMarketData(changed_future)
    after = FeaturePipeline(future_market, future_market.symbols).raw_observation(**kwargs)
    np.testing.assert_array_equal(before, after)
    assert normalizer.manifest()["fitted_partition"] == PartitionName.TRAIN
    with pytest.raises(ValueError, match="only be fitted on TRAIN"):
        normalizer.fit([before], PartitionName.VALIDATION)
    with pytest.raises(ValueError, match="only be fitted on TRAIN"):
        normalizer.fit([before], PartitionName.LOCKED_TEST)


def test_environment_contract_execution_reward_and_replay(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    env = _environment(candles)
    check_env(env, warn=True, skip_render_check=True)
    observation, info = env.reset(seed=7)
    assert env.action_space.n == 5
    assert env.observation_space.contains(observation)
    assert info["action_mapping"] == {
        "0": "USDT",
        "1": "ADAUSDT",
        "2": "BNBUSDT",
        "3": "BTCUSDT",
        "4": "ETHUSDT",
    }
    episode_start = env.window.start
    _, reward, terminated, truncated, first = env.step(3)
    assert not terminated and not truncated
    fill_time = datetime.fromisoformat(first["fills"][0]["simulated_time"].replace("Z", "+00:00"))
    assert fill_time == episode_start
    reward_parts = first["reward"]
    expected = (
        Decimal(reward_parts["base_reward"])
        - Decimal(reward_parts["drawdown_penalty"])
        - Decimal(reward_parts["turnover_penalty"])
        - Decimal(reward_parts["constraint_violation_penalty"])
        - Decimal(reward_parts["terminal_penalty"])
    )
    assert Decimal(str(reward)) == pytest.approx(expected)
    _, _, terminated, truncated, second = env.step(4)
    assert not terminated and truncated
    assert [fill["side"] for fill in second["fills"]] == ["SELL", "BUY"]

    replay_env = _environment(candles)
    replay = replay_episode(replay_env, actions=[3, 4], seed=7, episode_start=episode_start)
    assert replay == env.transitions


def test_ruin_terminates_with_terminal_penalty(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    env = _environment(candles, ruin_ratio=Decimal("1.10"))
    env.reset(seed=1)
    _, _, terminated, truncated, info = env.step(0)
    assert terminated and not truncated
    assert info["termination_reason"] == "RUIN"
    assert Decimal(info["reward"]["terminal_penalty"]) > 0


def test_turnover_controls_mask_rotation_and_repeat_is_hold(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    env = _environment(candles)
    env.config = EnvironmentConfig(
        warmup=timedelta(minutes=30),
        episode_duration=timedelta(minutes=30),
        controls=TurnoverControlConfig(enabled=True, minimum_hold_steps=4),
    )
    env.reset(seed=7)
    _, _, _, _, bought = env.step(3)
    assert len(bought["fills"]) == 1
    _, _, _, truncated, blocked = env.step(4)
    assert truncated
    assert blocked["requested_action"] == 4
    assert blocked["effective_action"] == 3
    assert blocked["avoided_operation_reason"] == "MINIMUM_HOLD"
    assert blocked["fills"] == []

    repeated = _environment(candles)
    repeated.reset(seed=7)
    repeated.step(3)
    _, _, _, _, same = repeated.step(3)
    assert same["fills"] == []
    assert same["avoided_operation_reason"] == "REPEATED_CURRENT_POSITION"
