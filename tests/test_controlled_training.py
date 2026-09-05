from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import numpy as np
import pytest
import torch
from pydantic import ValidationError

from crypto_strategy_lab.analytics.dashboard import render_learning_dashboard
from crypto_strategy_lab.analytics.learning import SURVIVAL_NO_EDGE, classify_learning_gates
from crypto_strategy_lab.analytics.schemas import ControlledTrainingReport
from crypto_strategy_lab.data.temporal import TemporalMarketData
from crypto_strategy_lab.ml.controlled_workflow import (
    TrainingJobSpec,
    _reconcile_training_progress,
    require_validation_ready,
    summarize_evaluation,
)
from crypto_strategy_lab.ml.environment import CryptoRotationEnv, EnvironmentConfig
from crypto_strategy_lab.ml.evaluation import EvaluationRunner
from crypto_strategy_lab.ml.features import (
    FeaturePipeline,
    FeatureSetSpec,
    FeatureVariant,
    fit_train_normalizer,
)
from crypto_strategy_lab.ml.partitions import PartitionName, TemporalPartition
from crypto_strategy_lab.ml.policies import StableBaselinesPolicy
from crypto_strategy_lab.ml.training import (
    CONTROLLED_CURRICULUM,
    ControlledTrainingResult,
    ResumableCurriculumTrainer,
    StableBaselinesTrainer,
)


def test_training_payload_uses_persisted_state_as_authority(tmp_path) -> None:
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    (artifact_dir / "training-state.json").write_text(
        '{"completed_timesteps": 100000, "status": "COMPLETED", '
        '"checkpoint_records": [], "training_metrics": [], "internal_evaluations": [], '
        '"elapsed_seconds": 2.0, "steps_per_second": 50000.0, '
        '"peak_python_memory_mb": 1.0, "latest_checkpoint": "latest.zip", '
        '"latest_checkpoint_hash": "physical", "configuration_hash": "cfg"}',
        encoding="utf-8",
    )
    result = ControlledTrainingResult(
        run_id="run",
        configuration_hash="stale",
        algorithm="PPO",
        seed=11,
        requested_timesteps=100000,
        completed_timesteps=10,
        status="TIME_LIMIT",
        artifact_dir=artifact_dir,
        latest_checkpoint=artifact_dir / "old.zip",
        checkpoint_hash="stale",
        elapsed_seconds=1.0,
        steps_per_second=10.0,
        peak_python_memory_mb=1.0,
        resumed=True,
        checkpoint_records=[],
        training_metrics=[],
        internal_evaluations=[],
        model=None,
    )
    from crypto_strategy_lab.ml.controlled_workflow import _training_payload

    payload = _training_payload(
        result,
        TrainingJobSpec("PPO", 11, FeatureVariant.BASE_FEATURES, "CONSERVATIVE"),
    )
    assert payload["completed_timesteps"] == 100000
    assert payload["status"] == "COMPLETED"
    assert payload["checkpoint_hash"] == "physical"
    assert payload["latest_checkpoint"] == "latest.zip"


def test_existing_report_is_reconciled_after_each_resumed_job(tmp_path) -> None:
    report = _minimal_report(status="TIME_LIMIT")
    output = tmp_path / "development.json"
    output.write_text(report.model_dump_json(), encoding="utf-8")
    fresh = {
        **report.runs[0],
        "status": "COMPLETED",
        "completed_timesteps": 100_000,
        "checkpoint_hash": "c" * 64,
    }

    _reconcile_training_progress(
        output,
        phase="development",
        dataset_hash=report.dataset_hash,
        fresh_runs=[fresh],
        fresh_baselines=[],
    )

    reconciled = ControlledTrainingReport.model_validate_json(output.read_text())
    assert reconciled.runs[0]["status"] == "COMPLETED"
    assert reconciled.runs[0]["completed_timesteps"] == 100_000
    assert reconciled.runs[0]["checkpoint_hash"] == "c" * 64


def _environment(candles) -> CryptoRotationEnv:
    partition = TemporalPartition(
        name=PartitionName.TRAIN,
        start=min(item.open_time for item in candles),
        end=max(item.close_time for item in candles) + timedelta(microseconds=1),
    )
    market = TemporalMarketData(candles)
    normalizer = fit_train_normalizer(
        FeaturePipeline(market, market.symbols), partition, Decimal("80")
    )
    return CryptoRotationEnv(
        candles,
        partition,
        normalizer,
        EnvironmentConfig(warmup=timedelta(minutes=30), episode_duration=timedelta(minutes=30)),
    )


def test_curriculum_is_frozen_to_30_60_90_days() -> None:
    assert [(item.duration_days, item.starts_at_step) for item in CONTROLLED_CURRICULUM] == [
        (30, 0),
        (60, 25_000),
        (90, 60_000),
    ]


def test_checkpoint_resume_and_idempotent_target(fixture_bundle, tmp_path) -> None:
    candles, _, _ = fixture_bundle
    cache = {30: _environment(candles)}
    trainer = ResumableCurriculumTrainer("DQN")
    kwargs = {
        "env_factory": lambda duration: cache[30],
        "internal_evaluator": lambda model, step: None,
        "dataset_hash": cache[30].dataset_hash,
        "feature_manifest": cache[30].pipeline.manifest(),
        "controls_manifest": cache[30].config.controls.__dict__,
        "seed": 42,
        "artifact_root": tmp_path,
        "checkpoint_interval": 8,
    }
    first = trainer.train_to_target(target_timesteps=16, **kwargs)
    assert first.status == "COMPLETED"
    assert first.completed_timesteps == 16
    assert first.latest_checkpoint.exists()
    resumed = trainer.train_to_target(target_timesteps=32, **kwargs)
    assert resumed.resumed
    assert resumed.completed_timesteps == 32
    same = trainer.train_to_target(target_timesteps=32, **kwargs)
    assert same.resumed
    assert same.checkpoint_hash == resumed.checkpoint_hash
    projected = trainer.train_to_target(target_timesteps=16, **kwargs)
    assert projected.status == "COMPLETED"
    assert projected.completed_timesteps == 16
    assert projected.checkpoint_hash == first.checkpoint_hash


@pytest.mark.parametrize(
    ("algorithm", "target", "expected_updates"),
    [("PPO", 500, 5), ("DQN", 1_004, 1)],
)
def test_controlled_training_completes_learning_unit_before_checkpoint(
    algorithm, target, expected_updates, fixture_bundle, tmp_path
) -> None:
    candles, _, _ = fixture_bundle
    cache = {30: _environment(candles)}
    trainer = ResumableCurriculumTrainer(algorithm)
    kwargs = {
        "env_factory": lambda duration: cache[30],
        "internal_evaluator": lambda model, step: None,
        "dataset_hash": cache[30].dataset_hash,
        "feature_manifest": cache[30].pipeline.manifest(),
        "controls_manifest": cache[30].config.controls.__dict__,
        "seed": 73,
        "artifact_root": tmp_path / algorithm.lower(),
        "checkpoint_interval": target,
    }

    result = trainer.train_to_target(target_timesteps=target, **kwargs)

    assert result.completed_timesteps == target
    assert result.status == "COMPLETED"
    assert result.model._n_updates == expected_updates
    if algorithm == "PPO":
        assert result.model.rollout_buffer.pos == target
    else:
        assert result.model.replay_buffer.size() == target


@pytest.mark.parametrize(
    ("algorithm", "target", "checkpoint_interval"),
    [("PPO", 13, 500), ("PPO", 500, 13), ("DQN", 21, 8)],
)
def test_controlled_training_rejects_partial_learning_units(
    algorithm, target, checkpoint_interval, fixture_bundle, tmp_path
) -> None:
    candles, _, _ = fixture_bundle
    env = _environment(candles)

    with pytest.raises(ValueError, match="complete training units"):
        ResumableCurriculumTrainer(algorithm).train_to_target(
            env_factory=lambda duration: env,
            internal_evaluator=lambda model, step: None,
            dataset_hash=env.dataset_hash,
            feature_manifest=env.pipeline.manifest(),
            controls_manifest=env.config.controls.__dict__,
            seed=73,
            target_timesteps=target,
            artifact_root=tmp_path / algorithm.lower(),
            checkpoint_interval=checkpoint_interval,
        )


def test_same_seed_and_configuration_reproduce_short_training(fixture_bundle, tmp_path) -> None:
    candles, _, _ = fixture_bundle
    environments = [_environment(candles), _environment(candles)]
    outcomes = []
    for index, env in enumerate(environments):
        result = ResumableCurriculumTrainer("DQN").train_to_target(
            env_factory=lambda duration, selected=env: selected,
            internal_evaluator=lambda model, step: None,
            dataset_hash=env.dataset_hash,
            feature_manifest=env.pipeline.manifest(),
            controls_manifest=env.config.controls.__dict__,
            seed=42,
            target_timesteps=16,
            artifact_root=tmp_path / str(index),
            checkpoint_interval=8,
        )
        outcomes.append(
            EvaluationRunner().run(
                env,
                StableBaselinesPolicy(result.model),
                seed=42,
            )
        )
    assert outcomes[0].actions == outcomes[1].actions
    assert outcomes[0].transitions == outcomes[1].transitions


def test_evaluation_is_deterministic_and_does_not_update_weights(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    env = _environment(candles)
    trainer = StableBaselinesTrainer("DQN", profile="controlled")
    first_model = trainer._build(env, 11, trainer._hyperparameters())
    second_model = trainer._build(env, 29, trainer._hyperparameters())
    before = {key: value.detach().clone() for key, value in first_model.policy.state_dict().items()}
    runner = EvaluationRunner()
    first = runner.run(env, StableBaselinesPolicy(first_model), seed=11)
    repeated = runner.run(env, StableBaselinesPolicy(first_model), seed=11)
    second = runner.run(env, StableBaselinesPolicy(second_model), seed=29)
    assert first.actions == repeated.actions
    assert first.transitions == repeated.transitions
    assert first.actions != second.actions
    assert all(
        torch.equal(value, first_model.policy.state_dict()[key]) for key, value in before.items()
    )


def test_learning_gate_classifies_cash_only_survival_without_edge() -> None:
    runs = [
        {
            "ruined": False,
            "turnover": "0",
            "costs_usdt": "0",
            "return_percent": "0",
            "time_in_usdt_ratio": "1",
        }
        for _ in range(3)
    ]
    baselines = [{"policy": "cash", "return_percent": "0"}]
    gates = classify_learning_gates(runs, baselines, technical_complete=True)
    assert gates.technical == "PASS"
    assert gates.survival == "PASS"
    assert gates.value == "FAIL"
    assert gates.classification == SURVIVAL_NO_EDGE


def test_relative_features_are_causal_and_expand_observation(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    market = TemporalMarketData(candles)
    time = min(item.open_time for item in candles) + timedelta(minutes=45)
    base = FeaturePipeline(market, market.symbols)
    relative = FeaturePipeline(
        market,
        market.symbols,
        FeatureSetSpec(variant=FeatureVariant.BASE_PLUS_RELATIVE_STRENGTH),
    )
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
    before = relative.raw_observation(**kwargs)
    changed = [
        item.model_copy(update={"close": item.close * 100, "high": item.high * 100})
        if item.open_time >= time
        else item
        for item in candles
    ]
    after_market = TemporalMarketData(changed)
    after = FeaturePipeline(
        after_market,
        after_market.symbols,
        FeatureSetSpec(variant=FeatureVariant.BASE_PLUS_RELATIVE_STRENGTH),
    ).raw_observation(**kwargs)
    np.testing.assert_array_equal(before, after)
    assert relative.observation_size == base.observation_size + 20
    early = relative.raw_observation(
        **{
            **kwargs,
            "simulated_time": min(item.open_time for item in candles) + timedelta(minutes=5),
        }
    )
    assert early.shape == (relative.observation_size,)


def test_training_report_cannot_hide_a_losing_seed() -> None:
    payload = {
        "phase": "development",
        "dataset_hash": "a" * 64,
        "partitions": {},
        "action_mapping": {
            "0": "USDT",
            "1": "BTCUSDT",
            "2": "ETHUSDT",
            "3": "SHIBUSDT",
            "4": "BNBUSDT",
        },
        "requested_timesteps_per_run": 100_000,
        "seeds": [11, 29],
        "algorithms": ["PPO"],
        "feature_variants": ["BASE_FEATURES"],
        "configuration_variants": ["CONSERVATIVE"],
        "runs": [
            {
                "algorithm": "PPO",
                "seed": 11,
                "feature_variant": "BASE_FEATURES",
                "configuration_variant": "CONSERVATIVE",
            },
            {
                "algorithm": "DQN",
                "seed": 29,
                "feature_variant": "BASE_FEATURES",
                "configuration_variant": "CONSERVATIVE",
            },
        ],
        "internal_train_baselines": [],
        "warning": "test",
    }
    with pytest.raises(ValidationError, match="best-seed filtering"):
        ControlledTrainingReport.model_validate(payload)


def test_validation_stays_closed_until_every_run_is_frozen() -> None:
    report = _minimal_report(status="TIME_LIMIT")
    with pytest.raises(ValueError, match="before every frozen run completes"):
        require_validation_ready(report)


def test_learning_dashboard_is_offline_deterministic_and_real_data_driven() -> None:
    report = _minimal_report(status="COMPLETED")
    first = render_learning_dashboard(report)
    second = render_learning_dashboard(report)
    assert first == second
    assert '<script src="http' not in first and '<link href="http' not in first
    assert "VALIDATION observada" in first
    assert "checkpoint_hash" in first
    assert r"<\/script>" in first


def test_evaluation_summary_has_valid_action_and_position_distributions(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    env = _environment(candles)
    model = StableBaselinesTrainer("DQN", profile="controlled")._build(
        env, 42, StableBaselinesTrainer("DQN", profile="controlled")._hyperparameters()
    )
    result = EvaluationRunner().run(env, StableBaselinesPolicy(model), seed=42)
    summary = summarize_evaluation(result)
    assert sum(summary["action_distribution"]) == pytest.approx(1)
    assert sum(summary["position_distribution"].values()) == pytest.approx(1)
    assert (
        sum(item["steps"] for item in summary["results_by_position"].values()) == summary["steps"]
    )
    assert sum(item["steps"] for item in summary["results_by_regime"].values()) == summary["steps"]


def _minimal_report(*, status: str) -> ControlledTrainingReport:
    return ControlledTrainingReport(
        phase="development",
        dataset_hash="a" * 64,
        partitions={
            "VALIDATION": {"observed": False},
        },
        action_mapping={
            "0": "USDT",
            "1": "BTCUSDT",
            "2": "ETHUSDT",
            "3": "SHIBUSDT",
            "4": "BNBUSDT",
        },
        requested_timesteps_per_run=100_000,
        seeds=[42],
        algorithms=["DQN"],
        feature_variants=["BASE_FEATURES"],
        configuration_variants=["CONSERVATIVE"],
        runs=[
            {
                "algorithm": "DQN",
                "seed": 42,
                "feature_variant": "BASE_FEATURES",
                "configuration_variant": "CONSERVATIVE",
                "status": status,
                "completed_timesteps": 16,
                "checkpoint_hash": "b" * 64,
                "checkpoint_records": [],
                "training_metrics": [],
                "internal_evaluations": [],
                "nan_detected": False,
                "steps_per_second": 1.0,
                "elapsed_seconds": 16.0,
                "peak_python_memory_mb": 1.0,
            }
        ],
        internal_train_baselines=[],
        warning="offline </script> training",
    )
