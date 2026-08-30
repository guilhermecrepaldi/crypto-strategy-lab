from __future__ import annotations

from pathlib import Path

import pytest

from crypto_strategy_lab.fixtures import load_fixture


@pytest.fixture
def fixture_path() -> Path:
    return Path(__file__).parents[1] / "fixtures" / "short_market.json"


@pytest.fixture
def fixture_bundle(fixture_path: Path):  # type annotation omitted for concise test fixture
    return load_fixture(fixture_path)
