from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from crypto_strategy_lab.data.temporal import TemporalMarketData
from crypto_strategy_lab.fixtures import load_fixture
from crypto_strategy_lab.ml.environment import CryptoRotationEnv, EnvironmentConfig
from crypto_strategy_lab.ml.evaluation import EvaluationResult, EvaluationRunner
from crypto_strategy_lab.ml.features import FeatureNormalizer, FeaturePipeline, fit_train_normalizer
from crypto_strategy_lab.ml.partitions import PartitionName, TemporalPartition
from crypto_strategy_lab.ml.policies import StableBaselinesPolicy
from crypto_strategy_lab.ml.training import StableBaselinesTrainer, TrainingArtifact


@dataclass(frozen=True)
class MLWorkflowResult:
    artifact: TrainingArtifact
    evaluation: EvaluationResult
    baselines: list[EvaluationResult]
    train_env: CryptoRotationEnv
    validation_env: CryptoRotationEnv
    normalizer: FeatureNormalizer


def run_short_training(
    *,
    train_fixture: Path,
    validation_fixture: Path,
    artifact_dir: Path,
    total_timesteps: int,
    seed: int,
    algorithm: str = "PPO",
    require_existing_checkpoint: bool = False,
) -> MLWorkflowResult:
    train_candles, _, _ = load_fixture(train_fixture)
    validation_candles, _, _ = load_fixture(validation_fixture)
    train_partition = _partition(train_candles, PartitionName.TRAIN)
    validation_partition = _partition(validation_candles, PartitionName.VALIDATION)
    config = EnvironmentConfig(
        warmup=timedelta(minutes=30),
        episode_duration=timedelta(minutes=30),
    )
    train_market = TemporalMarketData(train_candles)
    pipeline = FeaturePipeline(train_market, train_market.symbols)
    normalizer = fit_train_normalizer(pipeline, train_partition, config.initial_capital)
    train_env = CryptoRotationEnv(train_candles, train_partition, normalizer, config)
    trainer = StableBaselinesTrainer("DQN" if algorithm.upper() == "DQN" else "PPO")
    artifact = (
        trainer.load_existing(
            train_env,
            total_timesteps=total_timesteps,
            seed=seed,
            artifact_dir=artifact_dir,
        )
        if require_existing_checkpoint
        else trainer.train(
            train_env,
            total_timesteps=total_timesteps,
            seed=seed,
            artifact_dir=artifact_dir,
        )
    )
    validation_env = CryptoRotationEnv(validation_candles, validation_partition, normalizer, config)
    runner = EvaluationRunner()
    evaluation = runner.run(
        validation_env,
        StableBaselinesPolicy(artifact.model),
        seed=seed,
    )
    baselines = runner.baselines(
        lambda: CryptoRotationEnv(validation_candles, validation_partition, normalizer, config),
        seed=seed,
    )
    return MLWorkflowResult(
        artifact=artifact,
        evaluation=evaluation,
        baselines=baselines,
        train_env=train_env,
        validation_env=validation_env,
        normalizer=normalizer,
    )


def workflow_payload(result: MLWorkflowResult) -> dict[str, Any]:
    return {
        "training": {
            "algorithm": result.artifact.algorithm,
            "seed": result.artifact.seed,
            "timesteps": result.artifact.total_timesteps,
            "model_id": result.artifact.model_id,
            "checkpoint_path": str(result.artifact.checkpoint_path),
            "checkpoint_hash": result.artifact.checkpoint_hash,
            "hyperparameters": result.artifact.hyperparameters,
            "partition": result.train_env.partition.model_dump(mode="json"),
            "dataset_hash": result.train_env.dataset_hash,
            "normalizer": result.normalizer.manifest(),
        },
        "evaluation": _evaluation_payload(result.evaluation),
        "baselines": [_evaluation_payload(item) for item in result.baselines],
        "claims": {
            "profitability_evidence": False,
            "locked_test_used": False,
            "live_trading_authorized": False,
        },
    }


def _evaluation_payload(result: EvaluationResult) -> dict[str, Any]:
    return {
        "policy": result.policy,
        "seed": result.seed,
        "episode_start": result.episode_start,
        "episode_end": result.episode_end,
        "actions": result.actions,
        "final_equity_usdt": str(result.final_equity_usdt),
        "total_reward": str(result.total_reward),
        "terminated": result.terminated,
        "truncated": result.truncated,
        "transitions": result.transitions,
    }


def _partition(candles: list[Any], name: PartitionName) -> TemporalPartition:
    return TemporalPartition(
        name=name,
        start=min(item.open_time for item in candles),
        end=max(item.close_time for item in candles) + timedelta(microseconds=1),
    )
