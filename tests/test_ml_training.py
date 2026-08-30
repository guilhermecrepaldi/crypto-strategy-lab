from __future__ import annotations

from pathlib import Path

import pytest

from crypto_strategy_lab.ml.workflow import run_short_training


@pytest.mark.ml
def test_short_ppo_training_is_reproducible_and_reuses_checkpoint(
    fixture_path: Path, tmp_path: Path
) -> None:
    validation_fixture = fixture_path.parent / "rl_validation_market.json"
    first = run_short_training(
        train_fixture=fixture_path,
        validation_fixture=validation_fixture,
        artifact_dir=tmp_path,
        total_timesteps=16,
        seed=11,
    )
    second = run_short_training(
        train_fixture=fixture_path,
        validation_fixture=validation_fixture,
        artifact_dir=tmp_path,
        total_timesteps=16,
        seed=11,
        require_existing_checkpoint=True,
    )
    assert first.artifact.checkpoint_path.exists()
    assert len(first.artifact.checkpoint_hash) == 64
    assert second.artifact.reused is True
    assert first.artifact.model_id == second.artifact.model_id
    assert first.evaluation.actions == second.evaluation.actions
    assert first.evaluation.final_equity_usdt == second.evaluation.final_equity_usdt
    assert first.evaluation.truncated is True
    assert [result.policy for result in first.baselines] == [
        "cash",
        "buy-and-hold-1",
        "buy-and-hold-2",
        "buy-and-hold-3",
        "buy-and-hold-4",
        "causal-momentum",
        "random",
    ]
