from pathlib import Path

from crypto_strategy_lab.microstructure.campaign import CAMPAIGN_ID, register_first_block
from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelStatus


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
