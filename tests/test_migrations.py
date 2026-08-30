from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, inspect, select

from crypto_strategy_lab.data.binance import DownloadManifest
from crypto_strategy_lab.db.models import (
    AdaptiveStateCheckpoint,
    AuditEvent,
    DatasetManifest,
    DecisionEvent,
    ExperimentRun,
    SimulatedFill,
)
from crypto_strategy_lab.db.persistence import persist_download_manifest, persist_result
from crypto_strategy_lab.fixtures import load_fixture
from crypto_strategy_lab.simulation.engine import SimulationEngine


@pytest.mark.integration
def test_migrations_upgrade_clean_database_and_persist_fixture(fixture_path) -> None:
    if os.getenv("CRYPTO_LAB_RUN_DB_TESTS") != "1":
        pytest.skip("set CRYPTO_LAB_RUN_DB_TESTS=1 with the Compose database running")
    database_url = os.getenv(
        "CRYPTO_LAB_DATABASE_URL",
        "postgresql+psycopg://crypto_lab:crypto_lab_local@localhost:54329/crypto_strategy_lab",
    )
    subprocess.run(["uv", "run", "alembic", "downgrade", "base"], check=True)
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
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
