from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, inspect, select

from crypto_strategy_lab.data.binance import DownloadManifest
from crypto_strategy_lab.db.models import (
    AdaptiveStateCheckpoint,
    AuditEvent,
    BaselineResult,
    DatasetManifest,
    DecisionEvent,
    EpisodeStep,
    ExperimentEpisode,
    ExperimentRun,
    RewardComponent,
    SimulatedFill,
    TrainingRun,
)
from crypto_strategy_lab.db.persistence import persist_download_manifest, persist_result
from crypto_strategy_lab.fixtures import load_fixture
from crypto_strategy_lab.ml.persistence import persist_ml_evaluation
from crypto_strategy_lab.ml.workflow import run_short_training
from crypto_strategy_lab.simulation.engine import SimulationEngine


@pytest.mark.integration
def test_migrations_upgrade_clean_database_and_persist_fixture(fixture_path, tmp_path) -> None:
    if os.getenv("CRYPTO_LAB_RUN_DB_TESTS") != "1":
        pytest.skip("set CRYPTO_LAB_RUN_DB_TESTS=1 with the Compose database running")
    database_url = os.getenv(
        "CRYPTO_LAB_DATABASE_URL",
        "postgresql+psycopg://crypto_lab:crypto_lab_local@localhost:54329/crypto_strategy_lab",
    )
    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], check=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert {
        "candle_5m",
        "decision_event",
        "simulated_order",
        "simulated_fill",
        "portfolio_snapshot",
        "news_event",
        "audit_event",
        "feature_set",
        "feature_set_version",
        "normalizer_artifact",
        "model_definition",
        "model_checkpoint",
        "training_run",
        "training_metric",
        "experiment_episode",
        "episode_step",
        "reward_component",
        "baseline_result",
    } <= tables
    candles, provider, _ = load_fixture(fixture_path)
    result = SimulationEngine(candles, provider).run()
    assert persist_result(database_url, result) is True
    assert persist_result(database_url, result) is False
    manifest = DownloadManifest(
        source_url="https://data.binance.vision/fixture.zip",
        local_path=Path("data/fixture.zip"),
        sha256="a" * 64,
        size_bytes=123,
        ingested_at=datetime(2022, 1, 1, tzinfo=UTC),
    )
    assert persist_download_manifest(database_url, manifest) is True
    assert persist_download_manifest(database_url, manifest) is False
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(ExperimentRun)) == 1
        assert connection.scalar(select(func.count()).select_from(DecisionEvent)) == 5
        assert connection.scalar(select(func.count()).select_from(SimulatedFill)) == 4
        assert connection.scalar(select(func.count()).select_from(AdaptiveStateCheckpoint)) == 5
        assert connection.scalar(select(func.count()).select_from(AuditEvent)) == 1
        assert connection.scalar(select(func.count()).select_from(DatasetManifest)) == 1

    workflow = run_short_training(
        train_fixture=fixture_path,
        validation_fixture=fixture_path.parent / "rl_validation_market.json",
        artifact_dir=tmp_path / "models",
        total_timesteps=8,
        seed=13,
    )
    run_id, inserted = persist_ml_evaluation(
        database_url,
        env=workflow.validation_env,
        normalizer=workflow.normalizer,
        evaluation=workflow.evaluation,
        artifact=workflow.artifact,
    )
    assert inserted is True
    assert persist_ml_evaluation(
        database_url,
        env=workflow.validation_env,
        normalizer=workflow.normalizer,
        evaluation=workflow.evaluation,
        artifact=workflow.artifact,
    ) == (run_id, False)
    for baseline in workflow.baselines:
        persist_ml_evaluation(
            database_url,
            env=workflow.validation_env,
            normalizer=workflow.normalizer,
            evaluation=baseline,
            artifact=None,
        )
    expected_reward_components = sum(
        len(transition["reward"]) - 1
        for evaluation in (workflow.evaluation, *workflow.baselines)
        for transition in evaluation.transitions
    )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(TrainingRun)) == 1
        assert connection.scalar(select(func.count()).select_from(ExperimentEpisode)) == 8
        assert connection.scalar(select(func.count()).select_from(EpisodeStep)) == 16
        assert (
            connection.scalar(select(func.count()).select_from(RewardComponent))
            == expected_reward_components
        )
        assert connection.scalar(select(func.count()).select_from(BaselineResult)) == 7
