from datetime import UTC, datetime
from pathlib import Path

import pytest

from crypto_strategy_lab.microstructure.campaign import (
    CAMPAIGN_ID,
    LEGACY_TICK_ASSUMPTION_REASON,
    register_active_block,
    register_first_block,
)
from crypto_strategy_lab.ml.model_registry import (
    BackendSpec,
    ModelRegistry,
    ModelStatus,
    RunSpec,
    ScenarioSpec,
)


def test_first_block_registration_is_ordered_and_idempotent(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    reports = tmp_path / "reports"

    first = register_first_block(artifact_root=artifacts, report_root=reports)
    second = register_first_block(artifact_root=artifacts, report_root=reports)

    assert [item.model_id for item in first] == ["M001", "M002", "M003", "M004"]
    assert [item.model_hash for item in first] == [item.model_hash for item in second]
    assert all(item.status == ModelStatus.CREATED for item in first)
    assert first[-1].lineage.ancestor_chain == ("M001", "M002", "M003")
    assert first[-1].lineage.references["campaign_id"] == CAMPAIGN_ID

    registry = ModelRegistry(artifact_root=artifacts, report_root=reports)
    assert len(registry.entries()) == 4
    assert len(registry.journal()) == 4
    assert registry.registry_projection_path.exists()
    assert registry.registry_csv_path.exists()


def test_active_block_supersedes_unexecuted_legacy_models_idempotently(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    reports = tmp_path / "reports"

    first = register_active_block(artifact_root=artifacts, report_root=reports)
    second = register_active_block(artifact_root=artifacts, report_root=reports)
    registry = ModelRegistry(artifact_root=artifacts, report_root=reports)

    assert [item.model_id for item in first] == ["M005", "M006", "M007", "M008"]
    assert [item.model_hash for item in first] == [item.model_hash for item in second]
    assert all(
        registry.current_status(f"M{index:03}") == ModelStatus.SUPERSEDED for index in range(1, 5)
    )
    assert all(
        registry.current_status(f"M{index:03}") == ModelStatus.CREATED for index in range(5, 9)
    )
    assert first[-1].lineage.ancestor_chain == ("M005", "M006", "M007")
    assert first[0].lineage.references["supersedes"] == "M001"
    assert first[0].lineage.references["reason"] == LEGACY_TICK_ASSUMPTION_REASON
    assert len(registry.entries()) == 8
    assert len(registry.journal()) == 12


def test_active_registration_preserves_legacy_artifact_bytes(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    reports = tmp_path / "reports"
    legacy = register_first_block(artifact_root=artifacts, report_root=reports)
    before = {
        path: path.read_bytes()
        for item in legacy
        for path in Path(item.artifacts.directory).iterdir()
        if path.is_file()
    }

    register_active_block(artifact_root=artifacts, report_root=reports)

    assert before == {path: path.read_bytes() for path in before}


def test_active_registration_refuses_to_supersede_a_registered_run(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    reports = tmp_path / "reports"
    register_first_block(artifact_root=artifacts, report_root=reports)
    registry = ModelRegistry(artifact_root=artifacts, report_root=reports)
    scenario = registry.append_scenario("M001", ScenarioSpec(scenario={"name": "legacy"}))
    registry.append_run(
        "M001",
        RunSpec(
            scenario_hash=scenario["payload"]["SCENARIO_HASH"],
            dataset_hash="dataset",
            campaign_snapshot_id="snapshot",
            interval={"start": "2026-01-01", "end": "2026-01-02"},
            code_commit="abc123",
            technical_revision="legacy",
            backend=BackendSpec(backend="CPU"),
        ),
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="registered run"):
        register_active_block(artifact_root=artifacts, report_root=reports)

    assert [item.model_id for item in registry.entries()] == ["M001", "M002", "M003", "M004"]
