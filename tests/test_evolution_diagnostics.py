from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_strategy_lab.microstructure.evolution_diagnostics import (
    EvolutionDiagnosticError,
    _aggregate,
    _diagnose_model,
    _RunEvidence,
    _selection_points,
    _validate_existing,
    _validate_pair,
    _validate_protections,
    _write_artifact,
)
from crypto_strategy_lab.microstructure.serial_replay import (
    SerialModelConfig,
    SerialStrategy,
    SerialTape,
)
from crypto_strategy_lab.microstructure.tape_cache import TapeCacheFile, TapeCacheManifest

START = datetime(2026, 1, 1, tzinfo=UTC)


def _evidence(tmp_path: Path, model_id: str) -> _RunEvidence:
    events = [
        (START - timedelta(hours=1), Decimal("0.9998")),
        (START - timedelta(hours=1) + timedelta(seconds=1), Decimal("0.9999")),
        (START - timedelta(hours=1) + timedelta(seconds=2), Decimal("1.0000")),
        (START + timedelta(hours=1), Decimal("0.9998")),
        (START + timedelta(hours=1, seconds=1), Decimal("0.9999")),
        (START + timedelta(hours=2), Decimal("0.9998")),
        (START + timedelta(days=2), Decimal("0.9999")),
        (START + timedelta(days=2, seconds=1), Decimal("1.0000")),
    ]
    tape = SerialTape.from_events(events, tick_size=Decimal("0.0001"))
    event_values = [int(value) for value in tape.events]
    cycles = [
        {
            "entry_event": event_values[3],
            "exit_event": event_values[4],
            "entry_timestamp": (START + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "exit_timestamp": (START + timedelta(hours=1, seconds=1))
            .isoformat()
            .replace("+00:00", "Z"),
            "low": "0.9998",
            "high": "0.9999",
            "quantity": "100",
            "buy_fee_quote": "0",
            "sell_fee_quote": "0",
            "tick_at_selection": "0.0001",
        },
        {
            "entry_event": event_values[5],
            "exit_event": event_values[6],
            "entry_timestamp": (START + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "exit_timestamp": (START + timedelta(days=2)).isoformat().replace("+00:00", "Z"),
            "low": "0.9998",
            "high": "0.9999",
            "quantity": "0.01",
            "buy_fee_quote": "0",
            "sell_fee_quote": "0",
            "tick_at_selection": "0.0001",
        },
    ]
    replay = {
        "model_id": model_id,
        "model_hash": f"{model_id.lower():0<64}"[:64],
        "scenario_hash": "s" * 64,
        "initial_quote": "100",
        "final_cash": "100.010001",
        "final_inventory": "0",
        "final_marked_equity": "100.010001",
        "open_cycle_censored": False,
        "cycles": cycles,
        "selection_changes": [],
        "active_low": "0.9998",
        "active_high": "0.9999",
        "open_entry_event": event_values[5],
        "open_entry_timestamp": (START + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
    }
    manifest = TapeCacheManifest(
        dataset_hash="d" * 64,
        tick_catalog_hash=None,
        tick_source_policy="fixture",
        tick_source_url=None,
        start=START - timedelta(hours=1),
        end_exclusive=START + timedelta(days=2, seconds=2),
        quantum="0.0001",
        records=len(events),
        observed_tick_evidence_event=None,
        last_event=event_values[-1],
        last_price_tick=10000,
        files={"events": TapeCacheFile(sha256="0" * 64, size=0, dtype="<i8", shape=(len(events),))},
        total_size_bytes=0,
        build_time_seconds=0,
        cache_key="c" * 64,
        tape_hash="a" * 64,
        memory_footprint_bytes=0,
        content_hash="b" * 64,
    )
    run_manifest = {
        "MODEL_HASH": replay["model_hash"],
        "RUN_HASH": "r" * 64,
        "SCENARIO_HASH": replay["scenario_hash"],
        "model_id": model_id,
        "dataset_hash": manifest.dataset_hash,
        "campaign_snapshot_id": "p" * 64,
        "interval": {
            "start": START.isoformat(),
            "end_exclusive": manifest.end_exclusive.isoformat(),
        },
        "run": {"tape_cache": {"cache_key": manifest.cache_key, "tape_hash": manifest.tape_hash}},
    }
    model = SerialModelConfig(
        model_id=model_id,
        parent_model_id=None,
        strategy=SerialStrategy.STATIC,
        distances=(1, 2),
        lookback_minutes=1_440,
    )
    return _RunEvidence(
        model_id=model_id,
        model_hash=replay["model_hash"],
        run_hash=run_manifest["RUN_HASH"],
        evaluation_hash="e" * 64,
        model=model,
        replay=replay,
        run_manifest=run_manifest,
        evaluation={"run_hash": run_manifest["RUN_HASH"]},
        tape=tape,
        tape_manifest=manifest,
    )


def test_diagnostic_reconciles_cycles_and_separates_long_holds(tmp_path: Path) -> None:
    data = _diagnose_model(_evidence(tmp_path, "M007"))

    assert data["summary"]["completed_cycles"] == 2
    assert data["summary"]["long_hold_count"] == 1
    assert data["long_holds"]["terminal_censored"] == []
    assert abs(Decimal(data["summary"]["terminal"]["log_reconciliation_error"])) < Decimal("1e-20")
    assert data["long_holds"]["completed"][0]["alternative_low"] == "0.9998"
    bucket = data["aggregates"]["exit_month"]["2026-01"]
    assert bucket["cycles"] == 2
    assert "log_return" in bucket
    assert "rounding_residual_drag" in bucket
    assert "full_capital_gross_edge" in bucket
    assert data["aggregates"]["level"]["0.9998->0.9999"]["cycles"] == 2


def test_selection_history_allows_none_transitions_and_caches_event_ids(
    tmp_path: Path,
) -> None:
    evidence = _evidence(tmp_path, "M007")
    tape_events = [int(value) for value in evidence.tape.events]
    start_event = tape_events[0] + 3_600 * 1_000_000 * 4096
    evidence.replay["selection_changes"] = [
        {
            "event": start_event,
            "previous_low": None,
            "previous_high": None,
            "selected_low": "0.9998",
            "selected_high": "0.9999",
            "selected_tick_at_selection": "0.0001",
        },
        {
            "event": tape_events[4],
            "previous_low": "0.9998",
            "previous_high": "0.9999",
            "selected_low": None,
            "selected_high": None,
            "selected_tick_at_selection": None,
        },
        {
            "event": tape_events[5],
            "previous_low": None,
            "previous_high": None,
            "selected_low": "0.9998",
            "selected_high": "0.9999",
            "selected_tick_at_selection": "0.0001",
        },
    ]
    history = _selection_points(evidence, [])

    assert history.at(start_event)[1] == (9_998, 1)
    assert history.at(tape_events[4])[1] is None
    assert history.at(tape_events[5])[1] == (9_998, 1)


def test_aggregate_sums_decimal_diagnostics() -> None:
    target: dict[str, dict[str, dict[str, Decimal | int]]] = {}
    for _ in range(2):
        _aggregate(
            target,
            "low",
            "0.9998",
            {
                "realized": "1.2",
                "log_return": "0.01",
                "rounding_residual_drag": "0.02",
                "full_capital_gross_edge": "1.22",
            },
        )
    assert target["low"]["0.9998"] == {
        "cycles": 2,
        "realized": Decimal("2.4"),
        "log_return": Decimal("0.02"),
        "rounding_residual_drag": Decimal("0.04"),
        "full_capital_gross_edge": Decimal("2.44"),
    }


def test_terminal_censored_position_is_not_in_completed_hold_cohort(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path, "M007")
    evidence.replay.update(
        {
            "open_cycle_censored": True,
            "final_cash": "100.000003",
            "final_inventory": "0.01",
            "open_entry_price": "0.9998",
            "open_buy_fee_quote": "0",
            "final_marked_equity": "100.010003",
        }
    )
    data = _diagnose_model(evidence)

    assert len(data["long_holds"]["completed"]) == 1
    assert len(data["long_holds"]["terminal_censored"]) == 1
    assert data["cohorts"]["LONG_HOLD"]["count"] == 1
    terminal = data["long_holds"]["terminal_censored"][0]
    assert terminal["completed_duration_seconds"] is None
    assert terminal["observed_censor_age_seconds"] is None
    assert terminal["causal_entry"]["alternative_low"] == "0.9998"
    assert terminal["causal_entry"]["prior_high_age_seconds"] is not None
    assert terminal["causal_entry"]["canonical_lookback_cycles"] >= 0
    assert terminal["causal_entry"]["canonical_lookback_score"] is not None
    assert terminal["causal_entry"]["selection_tick_regime"] == "0.0001"


def test_diagnostic_artifact_is_idempotent_and_corruption_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "diagnostic"
    _write_artifact(root, "a" * 64, {"status": "READY"}, {"entries.csv": b"ok\n"})
    assert _validate_existing(root, "a" * 64)["status"] == "READY"
    (root / "entries.csv").write_bytes(b"corrupt\n")
    with pytest.raises(EvolutionDiagnosticError, match="corruption"):
        _validate_existing(root, "a" * 64)


def test_pair_identity_and_partition_protections_are_fail_closed(tmp_path: Path) -> None:
    parent = _evidence(tmp_path, "M007")
    challenger = _evidence(tmp_path, "M009")
    _validate_pair(parent, challenger)
    challenger.run_manifest["dataset_hash"] = "x" * 64  # type: ignore[index]
    with pytest.raises(EvolutionDiagnosticError, match="dataset_hash"):
        _validate_pair(parent, challenger)
    with pytest.raises(EvolutionDiagnosticError, match="protected partition"):
        _validate_protections(
            {
                "run": {
                    "validation_accessed": False,
                    "locked_test_accessed": False,
                    "binance_live_accessed": True,
                    "testnet_accessed": False,
                }
            }
        )
    with pytest.raises(EvolutionDiagnosticError, match="missing"):
        _validate_protections({"run": {"validation_accessed": False}})
    _validate_protections(
        {
            "run": {
                "validation_accessed": False,
                "locked_test_accessed": False,
                "live_accessed": False,
                "testnet_accessed": False,
            }
        }
    )
