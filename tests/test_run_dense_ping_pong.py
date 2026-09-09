import json
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.zonal_ping_pong import DensePingPongProbe
from scripts import register_dense_ping_pong as registration
from scripts import run_dense_ping_pong as runner


def test_exact_grid_has_200_unique_entries_and_expected_capital() -> None:
    grid = runner.expected_grid()
    entries = [row[1] for row in (*grid["buy"], *grid["sell"])]
    assert len(entries) == len(set(entries)) == 200
    assert grid["buy"][0] == ("B001", "1.0019", "1.0020")
    assert grid["buy"][-1] == ("B100", "0.9920", "0.9921")
    assert grid["sell"][0] == ("S001", "1.0021", "1.0020")
    assert grid["sell"][-1] == ("S100", "1.0120", "1.0119")
    assert sum((D(row[1]) for row in grid["buy"]), D(0)) == D("99.6950")


def test_frozen_design_matches_published_grid() -> None:
    design = json.loads(runner.SPEC.read_bytes())
    grid = json.loads(runner.GRID.read_bytes())
    runner.validate_frozen_design(design, grid)
    registration.validate_registration_design(design, grid)


def test_first_valid_book_freezes_half_up_anchor_and_full_funding() -> None:
    engine = DensePingPongProbe(start_us=runner.START_US, end_us=runner.END_US)
    engine.receive_book(
        {
            "exchange_time_us": runner.START_US + 1,
            "exchange_upper_us": runner.START_US + 1,
            "capture_time_us": runner.START_US + 1,
            "bids": ((D("1.00190000"), D("10")),),
            "asks": ((D("1.00200000"), D("10")),),
            "known_bid_floor": D(".7992"),
            "known_ask_ceiling": D("1.2024"),
        }
    )
    metrics = engine.metrics()
    assert metrics["grid_anchor"] == "1.0020"
    assert metrics["initial_usdt"] == "99.6950"
    assert metrics["initial_marked_equity"] == "199.88500000"
    assert metrics["max_simultaneous_open_orders"] == 200


def test_owner_gate_is_m021_only_and_fails_closed(monkeypatch, tmp_path) -> None:
    gate = tmp_path / "gate.md"
    gate.write_text(
        "APPROVED_COMPARISON_DAYS=1\n"
        "EXTENSION_AUTHORIZED=false\n"
        "NEW_REPLAY_AUTHORIZED_NOW=false\n"
        "AUTHORIZED_MODEL=NONE\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "OWNER_WINDOW", gate)
    with pytest.raises(ValueError, match="M021_OWNER_GATE_REQUIRED"):
        runner.require_owner_gate(tmp_path)


def test_cutoff_is_exactly_five_hours_and_day2_is_absent() -> None:
    assert runner.END_US - runner.START_US == 5 * 3_600_000_000
    design = json.loads(runner.SPEC.read_bytes())
    assert design["day2_authorized"] is False
    assert design["read_after_cutoff_allowed"] is False


def test_wrong_grid_fails_closed() -> None:
    design = json.loads(runner.SPEC.read_bytes())
    grid = json.loads(runner.GRID.read_bytes())
    grid["buy_slots"][0]["entry_price"] = "1.0020"
    with pytest.raises(ValueError, match="M021_GRID_ARTIFACT_MISMATCH"):
        runner.validate_frozen_design(design, grid)
