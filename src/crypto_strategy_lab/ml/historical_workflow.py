from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import mean
from typing import Any

from crypto_strategy_lab.data.history import HistoricalDatasetManifest, load_normalized_history
from crypto_strategy_lab.data.temporal import TemporalMarketData
from crypto_strategy_lab.ml.environment import CryptoRotationEnv, EnvironmentConfig
from crypto_strategy_lab.ml.evaluation import EvaluationResult, EvaluationRunner
from crypto_strategy_lab.ml.features import FeaturePipeline, fit_train_normalizer
from crypto_strategy_lab.ml.partitions import PartitionName, TemporalPartition
from crypto_strategy_lab.ml.policies import (
    BuyAndHoldPolicy,
    CashPolicy,
    DiscretePolicy,
    MomentumPolicy,
    RandomPolicy,
    StableBaselinesPolicy,
)
from crypto_strategy_lab.ml.training import StableBaselinesTrainer


@dataclass(frozen=True)
class SmokeRunSummary:
    duration_days: int
    policy: str
    seed: int
    final_equity_usdt: Decimal
    return_percent: Decimal
    max_drawdown: Decimal
    turnover: Decimal
    fees_usdt: Decimal
    spread_usdt: Decimal
    slippage_usdt: Decimal
    costs_usdt: Decimal
    time_in_usdt_ratio: Decimal
    steps: int
    terminated: bool
    truncated: bool

    def payload(self) -> dict[str, Any]:
        return {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in self.__dict__.items()
        }


def run_historical_smoke(
    manifest_path: Path,
    *,
    train_start: datetime,
    validation_start: datetime,
    validation_end: datetime,
    durations_days: tuple[int, ...],
    seeds: tuple[int, ...],
    total_timesteps: int,
    artifact_dir: Path,
) -> dict[str, Any]:
    manifest = HistoricalDatasetManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if manifest.locked_test_accessed:
        raise ValueError("LOCKED_TEST datasets are forbidden in smoke workflow")
    if not seeds:
        raise ValueError("at least one predeclared seed is required")
    if not durations_days or any(value not in {30, 90} for value in durations_days):
        raise ValueError("historical smoke durations are restricted to 30 or 90 days")
    max_duration = timedelta(days=max(durations_days))
    train_end = train_start + max_duration
    if train_end > validation_start or validation_start + max_duration > validation_end:
        raise ValueError("TRAIN and VALIDATION lack isolated coverage for requested duration")
    candles = load_normalized_history(Path(manifest.normalized_path))
    if min(item.open_time for item in candles) > train_start - timedelta(minutes=30):
        raise ValueError("dataset lacks causal warmup before TRAIN")
    train_partition = TemporalPartition(
        name=PartitionName.TRAIN,
        start=train_start,
        end=train_end,
    )
    validation_partition = TemporalPartition(
        name=PartitionName.VALIDATION,
        start=validation_start,
        end=validation_end,
    )
    market = TemporalMarketData(candles)
    pipeline = FeaturePipeline(market, market.symbols)
    normalizer = fit_train_normalizer(pipeline, train_partition, Decimal("80"))
    runner = EvaluationRunner()
    summaries: list[SmokeRunSummary] = []
    for duration_days in durations_days:
        config = EnvironmentConfig(
            warmup=timedelta(minutes=30),
            episode_duration=timedelta(days=duration_days),
        )
        train_env = CryptoRotationEnv(
            candles,
            train_partition,
            normalizer,
            config,
            dataset_hash=manifest.dataset_hash,
        )
        validation_env = CryptoRotationEnv(
            candles,
            validation_partition,
            normalizer,
            config,
            dataset_hash=manifest.dataset_hash,
        )
        for seed in seeds:
            for algorithm in ("PPO", "DQN"):
                trainer = StableBaselinesTrainer(algorithm)
                artifact = trainer.train(
                    train_env,
                    total_timesteps=total_timesteps,
                    seed=seed,
                    artifact_dir=artifact_dir,
                )
                evaluation = runner.run(
                    validation_env,
                    StableBaselinesPolicy(artifact.model, algorithm.lower()),
                    seed=seed,
                    episode_start=validation_start.isoformat(),
                )
                summaries.append(_summarize(evaluation, duration_days))
            policies: list[DiscretePolicy] = [
                CashPolicy(),
                *(BuyAndHoldPolicy(action) for action in range(1, 5)),
                MomentumPolicy(),
                RandomPolicy(seed),
            ]
            for policy in policies:
                evaluation = runner.run(
                    validation_env,
                    policy,
                    seed=seed,
                    episode_start=validation_start.isoformat(),
                )
                policy_name = (
                    f"buy-and-hold-{validation_env.action_symbols[policy.action]}"
                    if isinstance(policy, BuyAndHoldPolicy)
                    else None
                )
                summaries.append(_summarize(evaluation, duration_days, policy_name=policy_name))
    distributions = _distributions(summaries)
    return {
        "schema_version": "historical-smoke-v1",
        "dataset_hash": manifest.dataset_hash,
        "symbols": manifest.symbols,
        "train_partition": train_partition.model_dump(mode="json"),
        "validation_partition": validation_partition.model_dump(mode="json"),
        "durations_days": list(durations_days),
        "seeds": list(seeds),
        "training_timesteps": total_timesteps,
        "costs": EnvironmentConfig().costs.__dict__,
        "runs": [item.payload() for item in summaries],
        "distributions": distributions,
        "selection_rule": "all seeds and policies reported; no best-seed selection",
        "locked_test_accessed": False,
    }


def _summarize(
    result: EvaluationResult, duration_days: int, *, policy_name: str | None = None
) -> SmokeRunSummary:
    transitions = result.transitions
    initial = Decimal("80")
    return SmokeRunSummary(
        duration_days=duration_days,
        policy=policy_name or result.policy,
        seed=result.seed,
        final_equity_usdt=result.final_equity_usdt,
        return_percent=(result.final_equity_usdt / initial - 1) * 100,
        max_drawdown=max(Decimal(str(item["drawdown"])) for item in transitions),
        turnover=sum((Decimal(str(item["turnover"])) for item in transitions), Decimal("0")),
        fees_usdt=sum((Decimal(str(item["fee_usdt"])) for item in transitions), Decimal("0")),
        spread_usdt=sum(
            (Decimal(str(item["spread_cost_usdt"])) for item in transitions), Decimal("0")
        ),
        slippage_usdt=sum(
            (Decimal(str(item["slippage_cost_usdt"])) for item in transitions), Decimal("0")
        ),
        costs_usdt=sum((Decimal(str(item["costs_usdt"])) for item in transitions), Decimal("0")),
        time_in_usdt_ratio=Decimal(sum(1 for item in transitions if item["position"] == "USDT"))
        / Decimal(len(transitions)),
        steps=len(transitions),
        terminated=result.terminated,
        truncated=result.truncated,
    )


def _distributions(summaries: list[SmokeRunSummary]) -> list[dict[str, Any]]:
    keys = sorted({(item.duration_days, item.policy) for item in summaries})
    result: list[dict[str, Any]] = []
    for duration, policy in keys:
        runs = [
            item for item in summaries if item.duration_days == duration and item.policy == policy
        ]
        result.append(
            {
                "duration_days": duration,
                "policy": policy,
                "seed_count": len(runs),
                "return_percent": _stats([item.return_percent for item in runs]),
                "final_equity_usdt": _stats([item.final_equity_usdt for item in runs]),
                "max_drawdown": _stats([item.max_drawdown for item in runs]),
                "turnover": _stats([item.turnover for item in runs]),
                "fees_usdt": _stats([item.fees_usdt for item in runs]),
                "spread_usdt": _stats([item.spread_usdt for item in runs]),
                "slippage_usdt": _stats([item.slippage_usdt for item in runs]),
                "costs_usdt": _stats([item.costs_usdt for item in runs]),
                "time_in_usdt_ratio": _stats([item.time_in_usdt_ratio for item in runs]),
                "steps": _stats([Decimal(item.steps) for item in runs]),
                "terminated_count": sum(item.terminated for item in runs),
                "truncated_count": sum(item.truncated for item in runs),
            }
        )
    return result


def _stats(values: list[Decimal]) -> dict[str, str]:
    return {
        "min": str(min(values)),
        "mean": str(mean(values)),
        "max": str(max(values)),
    }
