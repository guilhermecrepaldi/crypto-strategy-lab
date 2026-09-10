from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_strategy_lab.microstructure.hotline_first_reallocation import (
    DEFAULT_EVALUATION_WINDOWS,
)
from scripts.run_hotline_first_reallocation import (
    RANDOM_SEED,
    require_owner_gate,
    selected_hours,
)


def test_random_seed_is_frozen_and_selects_three_unique_eligible_hours() -> None:
    hours = selected_hours(RANDOM_SEED)
    assert hours == (6, 12, 13)
    assert len(set(hours)) == 3
    assert all(hour in range(3, 24) for hour in hours)


def test_evaluation_windows_are_exact() -> None:
    assert DEFAULT_EVALUATION_WINDOWS == (
        (1_735_711_200_000_000, 1_735_714_800_000_000),
        (1_735_732_800_000_000, 1_735_736_400_000_000),
        (1_735_736_400_000_000, 1_735_740_000_000_000),
    )


def test_owner_gate_requires_exact_m030_authority(tmp_path: Path) -> None:
    path = tmp_path / "docs" / "microstructure"
    path.mkdir(parents=True)
    (path / "OWNER_GATED_REPLAY_WINDOW.md").write_text(
        "APPROVED_COMPARISON_DAYS=1\n"
        "EXTENSION_AUTHORIZED=false\n"
        "NEW_REPLAY_AUTHORIZED_NOW=false\n"
        "AUTHORIZED_MODEL=NONE\n"
        "AUTHORIZED_SCENARIO_COUNT=0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="M030_OWNER_GATE_REQUIRED"):
        require_owner_gate(tmp_path)


def test_spec_records_seed_and_windows() -> None:
    spec = json.loads(Path("docs/microstructure/M030_MODEL_SPEC.json").read_bytes())
    assert spec["random_evaluation_seed"] == RANDOM_SEED
    assert spec["random_evaluation_hours_utc"] == [6, 12, 13]
    assert spec["evaluation_mask_affects_decisions"] is False
