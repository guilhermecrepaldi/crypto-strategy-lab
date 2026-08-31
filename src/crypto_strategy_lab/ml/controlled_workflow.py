from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import mean, median
from typing import Any, Literal, cast

import numpy as np

from crypto_strategy_lab.analytics.learning import classify_learning_gates
from crypto_strategy_lab.analytics.schemas import (
    ControlledTrainingReport,
    ControlledValidationReport,
)
from crypto_strategy_lab.data.history import HistoricalDatasetManifest, load_normalized_history
from crypto_strategy_lab.data.temporal import TemporalMarketData
from crypto_strategy_lab.domain import Candle, canonical_hash
from crypto_strategy_lab.ml.controls import TurnoverControlConfig
from crypto_strategy_lab.ml.environment import CryptoRotationEnv, EnvironmentConfig
from crypto_strategy_lab.ml.evaluation import EvaluationResult, EvaluationRunner
from crypto_strategy_lab.ml.features import (
    FeatureNormalizer,
    FeaturePipeline,
    FeatureSetSpec,
    FeatureVariant,
    fit_train_normalizer,
)
from crypto_strategy_lab.ml.partitions import PartitionName, TemporalPartition
from crypto_strategy_lab.ml.policies import (
    BuyAndHoldPolicy,
    CashPolicy,
    DiscretePolicy,
    MomentumPolicy,
    RandomPolicy,
    StableBaselinesPolicy,
)
from crypto_strategy_lab.ml.reward import RewardConfig
from crypto_strategy_lab.ml.training import (
    ControlledTrainingResult,
    ResumableCurriculumTrainer,
    StableBaselinesTrainer,
)

TRAIN_START = datetime.fromisoformat("2022-01-01T00:00:00+00:00")
INTERNAL_START = datetime.fromisoformat("2022-03-02T00:00:00+00:00")
TRAIN_END = datetime.fromisoformat("2022-04-01T00:00:00+00:00")
VALIDATION_START = TRAIN_END
VALIDATION_END = datetime.fromisoformat("2022-07-01T00:00:00+00:00")


@dataclass(frozen=True)
class TrainingJobSpec:
    algorithm: Literal["PPO", "DQN"]
    seed: int
    feature_variant: FeatureVariant
    configuration_variant: Literal["CONSERVATIVE", "ABLATION_NO_CONTROLS"]


def run_controlled_training(
    manifest_path: Path,
    *,
    phase: Literal["sanity", "development", "candidate"],
    artifact_root: Path,
    output: Path,
    max_seconds_per_run: int | None = None,
) -> ControlledTrainingReport:
    manifest = HistoricalDatasetManifest.model_validate_json(manifest_path.read_text())
    if manifest.locked_test_accessed:
        raise ValueError("LOCKED_TEST is forbidden")
    candles = load_normalized_history(Path(manifest.normalized_path))
    _validate_coverage(candles)
    jobs, target = _jobs_for_phase(phase, artifact_root)
    contexts: dict[FeatureVariant, _TrainingContext] = {}
    runs: list[dict[str, Any]] = []
    baselines: list[dict[str, Any]] = []
    for job in jobs:
        if job.feature_variant not in contexts:
            contexts[job.feature_variant] = _build_context(
                candles, manifest.dataset_hash, job.feature_variant
            )
        context = contexts[job.feature_variant]
        config = _environment_config(job.configuration_variant)
        env_cache: dict[int, CryptoRotationEnv] = {}

        def env_factory(
            duration_days: int,
            *,
            cache: dict[int, CryptoRotationEnv] = env_cache,
            job_context: _TrainingContext = context,
            env_config: EnvironmentConfig = config,
        ) -> CryptoRotationEnv:
            if duration_days not in cache:
                partition = (
                    job_context.full_train if duration_days == 90 else job_context.update_train
                )
                cache[duration_days] = CryptoRotationEnv(
                    candles,
                    partition,
                    job_context.normalizer,
                    replace(env_config, episode_duration=timedelta(days=duration_days)),
                    dataset_hash=manifest.dataset_hash,
                    feature_spec=job_context.feature_spec,
                )
            return cache[duration_days]

        internal_env = CryptoRotationEnv(
            candles,
            context.internal_train,
            context.normalizer,
            replace(config, episode_duration=timedelta(days=30)),
            dataset_hash=manifest.dataset_hash,
            feature_spec=context.feature_spec,
        )

        def internal_evaluator(
            model: Any,
            step: int,
            *,
            evaluation_env: CryptoRotationEnv = internal_env,
            training_job: TrainingJobSpec = job,
        ) -> dict[str, Any]:
            result = EvaluationRunner().run(
                evaluation_env,
                StableBaselinesPolicy(model, f"{training_job.algorithm.lower()}-checkpoint"),
                seed=training_job.seed,
                episode_start=INTERNAL_START.isoformat(),
            )
            return {"checkpoint_step": step, **summarize_evaluation(result)}

        trainer = ResumableCurriculumTrainer(job.algorithm)
        trained = trainer.train_to_target(
            env_factory=env_factory,
            internal_evaluator=internal_evaluator,
            dataset_hash=manifest.dataset_hash,
            feature_manifest=context.feature_spec.__dict__,
            controls_manifest={
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in config.controls.__dict__.items()
            },
            seed=job.seed,
            target_timesteps=target,
            artifact_root=artifact_root
            / job.configuration_variant.lower()
            / job.feature_variant.lower(),
            max_seconds=max_seconds_per_run,
        )
        runs.append(_training_payload(trained, job))
        key = (job.feature_variant, job.configuration_variant, job.seed)
        if not any(item["baseline_key"] == str(key) for item in baselines):
            baselines.extend(
                _baselines(
                    internal_env,
                    job.seed,
                    job.feature_variant,
                    job.configuration_variant,
                    INTERNAL_START,
                )
            )
    report = ControlledTrainingReport(
        phase=phase,
        dataset_hash=manifest.dataset_hash,
        partitions={
            "TRAIN": {"start": TRAIN_START.isoformat(), "end": TRAIN_END.isoformat()},
            "TRAIN_UPDATE_PRE_FREEZE": {
                "start": TRAIN_START.isoformat(),
                "end": INTERNAL_START.isoformat(),
            },
            "TRAIN_INTERNAL_EVALUATION": {
                "start": INTERNAL_START.isoformat(),
                "end": TRAIN_END.isoformat(),
                "used_after_stage_2": False,
            },
            "VALIDATION": {
                "start": VALIDATION_START.isoformat(),
                "end": VALIDATION_END.isoformat(),
                "observed": False,
            },
        },
        action_mapping={
            "0": "USDT",
            "1": "BTCUSDT",
            "2": "ETHUSDT",
            "3": "SHIBUSDT",
            "4": "BNBUSDT",
        },
        requested_timesteps_per_run=target,
        seeds=sorted({item.seed for item in jobs}),
        algorithms=sorted({item.algorithm for item in jobs}),
        feature_variants=sorted({item.feature_variant for item in jobs}),
        configuration_variants=sorted({item.configuration_variant for item in jobs}),
        runs=runs,
        internal_train_baselines=baselines,
        warning=(
            "Historical simulation only. Internal evaluation is TRAIN-only; VALIDATION and "
            "LOCKED_TEST were not observed. No profitability claim."
        ),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def run_controlled_validation(
    manifest_path: Path,
    *,
    training_report_path: Path,
    output: Path,
) -> ControlledValidationReport:
    manifest = HistoricalDatasetManifest.model_validate_json(manifest_path.read_text())
    training = ControlledTrainingReport.model_validate_json(training_report_path.read_text())
    if manifest.locked_test_accessed or training.locked_test_accessed:
        raise ValueError("LOCKED_TEST is forbidden")
    require_validation_ready(training)
    candles = load_normalized_history(Path(manifest.normalized_path))
    _validate_coverage(candles)
    contexts: dict[FeatureVariant, _TrainingContext] = {}
    runs: list[dict[str, Any]] = []
    baselines: list[dict[str, Any]] = []
    for trained in training.runs:
        feature = FeatureVariant(trained["feature_variant"])
        if feature not in contexts:
            contexts[feature] = _build_context(candles, manifest.dataset_hash, feature)
        context = contexts[feature]
        config = _environment_config(trained["configuration_variant"])
        env = CryptoRotationEnv(
            candles,
            TemporalPartition(
                name=PartitionName.VALIDATION,
                start=VALIDATION_START,
                end=VALIDATION_END,
                observed=True,
            ),
            context.normalizer,
            replace(config, episode_duration=timedelta(days=90)),
            dataset_hash=manifest.dataset_hash,
            feature_spec=context.feature_spec,
        )
        algorithm = trained["algorithm"]
        trainer = StableBaselinesTrainer(algorithm, profile="controlled")
        model = trainer._load(Path(trained["latest_checkpoint"]), env)
        evaluation = EvaluationRunner().run(
            env,
            StableBaselinesPolicy(model, f"{algorithm.lower()}-frozen"),
            seed=int(trained["seed"]),
            episode_start=VALIDATION_START.isoformat(),
        )
        payload = summarize_evaluation(evaluation)
        payload.update(
            {
                "algorithm": algorithm,
                "feature_variant": feature,
                "configuration_variant": trained["configuration_variant"],
                "checkpoint_hash": trained["checkpoint_hash"],
            }
        )
        runs.append(payload)
        baseline_key = str((feature, trained["configuration_variant"], trained["seed"]))
        if not any(item["baseline_key"] == baseline_key for item in baselines):
            baselines.extend(
                _baselines(
                    env,
                    int(trained["seed"]),
                    feature,
                    trained["configuration_variant"],
                    VALIDATION_START,
                )
            )
    frozen_identity = {
        "dataset_hash": training.dataset_hash,
        "phase": training.phase,
        "runs": [
            {
                "algorithm": item["algorithm"],
                "seed": item["seed"],
                "feature_variant": item["feature_variant"],
                "configuration_variant": item["configuration_variant"],
                "checkpoint_hash": item["checkpoint_hash"],
            }
            for item in training.runs
        ],
    }
    report = ControlledValidationReport(
        source_training_phase=cast(Literal["development", "candidate"], training.phase),
        dataset_hash=training.dataset_hash,
        frozen_configuration_hash=canonical_hash(frozen_identity),
        partition={
            "name": "VALIDATION",
            "start": VALIDATION_START.isoformat(),
            "end": VALIDATION_END.isoformat(),
            "observed": True,
            "weights_updated": False,
        },
        runs=runs,
        baselines=baselines,
        distributions=_validation_distributions(runs),
        gates=classify_learning_gates(
            runs,
            baselines,
            technical_complete=all(not item["nan_detected"] for item in training.runs),
        ),
        warning=(
            "VALIDATION has now been observed for this frozen policy version. It may not be "
            "used to update weights, features, reward, controls or hyperparameters."
        ),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    validation_partition = {
        **dict(training.partitions.get("VALIDATION", {})),
        "observed": True,
        "observed_for_frozen_configuration_hash": report.frozen_configuration_hash,
    }
    observed_training = training.model_copy(
        update={
            "validation_observed": True,
            "partitions": {**training.partitions, "VALIDATION": validation_partition},
        }
    )
    training_report_path.write_text(
        json.dumps(observed_training.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def require_validation_ready(training: ControlledTrainingReport) -> None:
    if training.phase not in {"development", "candidate"}:
        raise ValueError("VALIDATION requires a frozen development or candidate phase")
    if any(item["status"] != "COMPLETED" for item in training.runs):
        raise ValueError("VALIDATION cannot be observed before every frozen run completes")
    if training.validation_observed:
        raise ValueError("VALIDATION is already observed for this policy version")


@dataclass(frozen=True)
class _TrainingContext:
    feature_spec: FeatureSetSpec
    normalizer: FeatureNormalizer
    update_train: TemporalPartition
    full_train: TemporalPartition
    internal_train: TemporalPartition


def _build_context(
    candles: list[Candle], dataset_hash: str, variant: FeatureVariant
) -> _TrainingContext:
    del dataset_hash
    update = TemporalPartition(name=PartitionName.TRAIN, start=TRAIN_START, end=INTERNAL_START)
    full = TemporalPartition(name=PartitionName.TRAIN, start=TRAIN_START, end=TRAIN_END)
    internal = TemporalPartition(name=PartitionName.TRAIN, start=INTERNAL_START, end=TRAIN_END)
    spec = FeatureSetSpec(variant=variant)
    market = TemporalMarketData(candles)
    symbols = ("BTCUSDT", "ETHUSDT", "SHIBUSDT", "BNBUSDT")
    normalizer = fit_train_normalizer(FeaturePipeline(market, symbols, spec), update, Decimal("80"))
    return _TrainingContext(spec, normalizer, update, full, internal)


def _environment_config(
    variant: Literal["CONSERVATIVE", "ABLATION_NO_CONTROLS"],
) -> EnvironmentConfig:
    if variant == "ABLATION_NO_CONTROLS":
        return EnvironmentConfig(
            warmup=timedelta(days=31),
            reward=RewardConfig(
                turnover_coefficient=Decimal("0"),
                rotation_coefficient=Decimal("0"),
                ruin_penalty=Decimal("0"),
            ),
        )
    return EnvironmentConfig(
        warmup=timedelta(days=31),
        controls=TurnoverControlConfig(
            enabled=True,
            minimum_hold_steps=4,
            cooldown_steps=4,
            minimum_edge_after_costs=Decimal("0.001"),
            minimum_notional_usdt=Decimal("10"),
        ),
        reward=RewardConfig(
            turnover_coefficient=Decimal("0.005"),
            rotation_coefficient=Decimal("0"),
            ruin_penalty=Decimal("0"),
        ),
    )


def _jobs_for_phase(phase: str, artifact_root: Path) -> tuple[list[TrainingJobSpec], int]:
    del artifact_root
    algorithms: tuple[Literal["PPO", "DQN"], ...] = ("PPO", "DQN")
    if phase == "sanity":
        configurations: tuple[Literal["CONSERVATIVE", "ABLATION_NO_CONTROLS"], ...] = (
            "CONSERVATIVE",
            "ABLATION_NO_CONTROLS",
        )
        jobs = [
            TrainingJobSpec(algorithm, 42, FeatureVariant.BASE_FEATURES, config)
            for algorithm in algorithms
            for config in configurations
        ]
        return jobs, 10_000
    if phase == "development":
        return (
            [
                TrainingJobSpec(algorithm, seed, feature, "CONSERVATIVE")
                for algorithm in algorithms
                for seed in (11, 29, 42)
                for feature in FeatureVariant
            ],
            100_000,
        )
    if phase == "candidate":
        selected = _selected_features_from_development()
        return (
            [
                TrainingJobSpec(algorithm, seed, selected[algorithm], "CONSERVATIVE")
                for algorithm in algorithms
                for seed in (11, 29, 42, 73, 101)
            ],
            300_000,
        )
    raise ValueError("phase must be sanity, development or candidate")


def _selected_features_from_development() -> dict[str, FeatureVariant]:
    report_path = Path("reports/controlled-training-development.json")
    if not report_path.exists():
        raise ValueError("candidate requires a complete development report")
    report = ControlledTrainingReport.model_validate_json(report_path.read_text())
    if report.phase != "development":
        raise ValueError("candidate selection requires a development report")
    if any(item["status"] != "COMPLETED" or item["nan_detected"] for item in report.runs):
        raise ValueError("candidate requires structurally complete development runs")
    selected: dict[str, FeatureVariant] = {}
    for algorithm in ("PPO", "DQN"):
        scores: dict[FeatureVariant, list[Decimal]] = {item: [] for item in FeatureVariant}
        for run in report.runs:
            if run["algorithm"] != algorithm or not run["internal_evaluations"]:
                continue
            feature = FeatureVariant(run["feature_variant"])
            scores[feature].append(Decimal(str(run["internal_evaluations"][-1]["return_percent"])))
        selected[algorithm] = max(
            FeatureVariant,
            key=lambda item: (median(scores[item]) if scores[item] else Decimal("-Infinity"), item),
        )
    return selected


def summarize_evaluation(result: EvaluationResult) -> dict[str, Any]:
    transitions = result.transitions
    initial = Decimal("80")
    action_counts = [result.actions.count(index) for index in range(5)]
    costs = sum((Decimal(str(item["costs_usdt"])) for item in transitions), Decimal(0))
    turnover = sum((Decimal(str(item["turnover"])) for item in transitions), Decimal(0))
    rewards = [Decimal(str(item["reward"]["total"])) for item in transitions]
    positions = [str(item["position"]) for item in transitions]
    ordered_positions = ["USDT", "BTCUSDT", "ETHUSDT", "SHIBUSDT", "BNBUSDT"]
    return_percent = (result.final_equity_usdt / initial - 1) * 100
    reward_average = mean(rewards)
    hacking_flags: list[str] = []
    if reward_average > 0 and return_percent < 0:
        hacking_flags.append("POSITIVE_REWARD_WITH_NEGATIVE_NET_RETURN")
    if sum(bool(item["fills"]) for item in transitions) / len(transitions) > 0.5:
        hacking_flags.append("EXCESSIVE_OPERATION_RATE")
    return {
        "policy": result.policy,
        "seed": result.seed,
        "final_equity_usdt": str(result.final_equity_usdt),
        "return_percent": str(return_percent),
        "reward_mean": str(reward_average),
        "reward_median": str(median(rewards)),
        "max_drawdown": str(max(Decimal(str(item["drawdown"])) for item in transitions)),
        "turnover": str(turnover),
        "operations": sum(bool(item["fills"]) for item in transitions),
        "rotations": sum(len(item["fills"]) == 2 for item in transitions),
        "costs_usdt": str(costs),
        "time_in_usdt_ratio": str(Decimal(positions.count("USDT")) / Decimal(len(positions))),
        "action_counts": action_counts,
        "action_distribution": [count / len(result.actions) for count in action_counts],
        "position_distribution": {
            position: positions.count(position) / len(positions) for position in ordered_positions
        },
        "position_duration_mean_steps": str(_mean_position_duration(positions)),
        "results_by_position": _grouped_transition_results(
            transitions, lambda item: str(item["position"])
        ),
        "results_by_regime": _grouped_transition_results(
            transitions,
            lambda item: (
                "BTC_POSITIVE"
                if float(item["momentum_by_action"][1]) > 0
                else "BTC_NEGATIVE"
                if float(item["momentum_by_action"][1]) < 0
                else "BTC_FLAT"
            ),
        ),
        "reward_hacking_flags": hacking_flags,
        "ruined": result.terminated,
        "steps": len(transitions),
        "transition_hash": canonical_hash(transitions),
    }


def _grouped_transition_results(
    transitions: list[dict[str, Any]], key: Callable[[dict[str, Any]], str]
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for transition in transitions:
        groups.setdefault(str(key(transition)), []).append(transition)
    return {
        name: {
            "steps": len(items),
            "base_reward_mean": str(
                mean(Decimal(str(item["reward"]["base_reward"])) for item in items)
            ),
            "net_reward_mean": str(mean(Decimal(str(item["reward"]["total"])) for item in items)),
            "turnover": str(sum((Decimal(str(item["turnover"])) for item in items), Decimal(0))),
            "costs_usdt": str(
                sum((Decimal(str(item["costs_usdt"])) for item in items), Decimal(0))
            ),
        }
        for name, items in sorted(groups.items())
    }


def _baselines(
    env: CryptoRotationEnv,
    seed: int,
    feature: FeatureVariant,
    configuration: str,
    episode_start: datetime,
) -> list[dict[str, Any]]:
    runner = EvaluationRunner()
    policies: list[DiscretePolicy] = [
        CashPolicy(),
        *(BuyAndHoldPolicy(action) for action in range(1, 5)),
        MomentumPolicy(),
        RandomPolicy(seed),
    ]
    values: list[dict[str, Any]] = []
    baseline_key = str((feature, configuration, seed))
    for policy in policies:
        result = runner.run(env, policy, seed=seed, episode_start=episode_start.isoformat())
        payload = summarize_evaluation(result)
        payload.update(
            {
                "baseline_key": baseline_key,
                "feature_variant": feature,
                "configuration_variant": configuration,
            }
        )
        values.append(payload)
    untrained = StableBaselinesTrainer("PPO", profile="controlled")
    model = untrained._build(env, seed, untrained._hyperparameters())
    result = runner.run(
        env,
        StableBaselinesPolicy(model, "untrained-ppo"),
        seed=seed,
        episode_start=episode_start.isoformat(),
    )
    payload = summarize_evaluation(result)
    payload.update(
        {
            "baseline_key": baseline_key,
            "feature_variant": feature,
            "configuration_variant": configuration,
        }
    )
    values.append(payload)
    return values


def _training_payload(result: ControlledTrainingResult, job: TrainingJobSpec) -> dict[str, Any]:
    payload = {
        "run_id": result.run_id,
        "configuration_hash": result.configuration_hash,
        "algorithm": result.algorithm,
        "seed": result.seed,
        "requested_timesteps": result.requested_timesteps,
        "completed_timesteps": result.completed_timesteps,
        "status": result.status,
        "checkpoint_hash": result.checkpoint_hash,
        "elapsed_seconds": result.elapsed_seconds,
        "steps_per_second": result.steps_per_second,
        "peak_python_memory_mb": result.peak_python_memory_mb,
        "resumed": result.resumed,
        "checkpoint_records": result.checkpoint_records,
        "training_metrics": result.training_metrics,
        "internal_evaluations": result.internal_evaluations,
    }
    payload.update(
        {
            "artifact_dir": str(result.artifact_dir),
            "latest_checkpoint": str(result.latest_checkpoint),
            "feature_variant": job.feature_variant,
            "configuration_variant": job.configuration_variant,
            "resume_command": (
                "uv run crypto-lab controlled-train --phase "
                f"{_phase_for_target(result.requested_timesteps)}"
            ),
            "nan_detected": _contains_nan(result.training_metrics),
        }
    )
    return payload


def _contains_nan(metrics: list[dict[str, Any]]) -> bool:
    for metric in metrics:
        for value in metric.values():
            if isinstance(value, float) and not np.isfinite(value):
                return True
    return False


def _validation_distributions(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted({(item["algorithm"], item["feature_variant"]) for item in runs})
    result: list[dict[str, Any]] = []
    for algorithm, feature in keys:
        group = [
            item
            for item in runs
            if item["algorithm"] == algorithm and item["feature_variant"] == feature
        ]
        values = np.asarray([float(item["return_percent"]) for item in group])
        rng = np.random.default_rng(20220101)
        bootstrap = np.asarray(
            [
                float(np.median(rng.choice(values, size=len(values), replace=True)))
                for _ in range(2_000)
            ]
        )
        result.append(
            {
                "algorithm": algorithm,
                "feature_variant": feature,
                "seed_count": len(group),
                "return_percent": {
                    "mean": float(np.mean(values)),
                    "median": float(np.median(values)),
                    "min": float(np.min(values)),
                    "max": float(np.max(values)),
                    "p05": float(np.percentile(values, 5)),
                    "p25": float(np.percentile(values, 25)),
                    "p75": float(np.percentile(values, 75)),
                    "p95": float(np.percentile(values, 95)),
                    "bootstrap_median_ci95": [
                        float(np.percentile(bootstrap, 2.5)),
                        float(np.percentile(bootstrap, 97.5)),
                    ],
                },
                "survival_rate": sum(not item["ruined"] for item in group) / len(group),
                "ruin_probability": sum(item["ruined"] for item in group) / len(group),
                "turnover_median": str(median(Decimal(str(item["turnover"])) for item in group)),
                "costs_median_usdt": str(
                    median(Decimal(str(item["costs_usdt"])) for item in group)
                ),
                "max_drawdown_median": str(
                    median(Decimal(str(item["max_drawdown"])) for item in group)
                ),
                "time_in_usdt_median": str(
                    median(Decimal(str(item["time_in_usdt_ratio"])) for item in group)
                ),
            }
        )
    return result


def _phase_for_target(target: int) -> str:
    return {10_000: "sanity", 100_000: "development", 300_000: "candidate"}[target]


def _mean_position_duration(positions: list[str]) -> float:
    durations: list[int] = []
    current = positions[0]
    count = 1
    for position in positions[1:]:
        if position == current:
            count += 1
        else:
            if current != "USDT":
                durations.append(count)
            current, count = position, 1
    if current != "USDT":
        durations.append(count)
    return mean(durations) if durations else 0.0


def _validate_coverage(candles: list[Candle]) -> None:
    start = min(item.open_time for item in candles)
    end = max(item.close_time for item in candles)
    if start > datetime.fromisoformat(
        "2021-12-01T00:00:00+00:00"
    ) or end < VALIDATION_END - timedelta(minutes=5):
        raise ValueError("dataset lacks the declared warmup/TRAIN/VALIDATION coverage")
    if {item.symbol for item in candles} != {"BTCUSDT", "ETHUSDT", "SHIBUSDT", "BNBUSDT"}:
        raise ValueError(
            "controlled training requires the historically selected four-symbol universe"
        )
