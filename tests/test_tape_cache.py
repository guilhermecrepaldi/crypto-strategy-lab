from __future__ import annotations

import gc
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.data import HistoryManifest
from crypto_strategy_lab.microstructure.market_profile import (
    MarketHour,
    MarketHourlyProfile,
    write_hourly_market_profile,
)
from crypto_strategy_lab.microstructure.replay_workflow import load_or_build_market_profile
from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    SERIAL_TAPE_QUANTUM,
    SerialModelConfig,
    SerialScenarioConfig,
    SerialStrategy,
    SerialTape,
    TickCatalog,
    TickPeriod,
    TickTransition,
    preregistered_corrected_block,
    replay_serial_model,
)
from crypto_strategy_lab.microstructure.tape_cache import (
    load_or_build_tape,
    tape_cache_dir,
)
from crypto_strategy_lab.microstructure.temporal_analysis import analyze_replay_temporally

START = datetime(2026, 1, 1, tzinfo=UTC)


def _manifest(records: int = 4) -> HistoryManifest:
    return HistoryManifest(
        symbol="USDCUSDT",
        kind="trades",
        requested_start=date(2026, 1, 1),
        requested_end=date(2026, 1, 1),
        all_available=False,
        discovered_first_date=date(2026, 1, 1),
        discovered_last_date=date(2026, 1, 1),
        archives=(),
        missing_dates=(),
        cross_archive_gaps=(),
        cross_archive_overlaps=(),
        total_records=records,
        total_size_bytes=1,
        first_timestamp=START,
        last_timestamp=START + timedelta(seconds=4),
        dataset_hash="dataset-hash",
        integrity_status="VALID",
    )


def _tape() -> SerialTape:
    return SerialTape.from_events(
        [
            (START, Decimal("0.99980")),
            (START + timedelta(seconds=1), Decimal("0.99990")),
            (START + timedelta(seconds=2), Decimal("0.99980")),
            (START + timedelta(seconds=3), Decimal("0.99990")),
        ],
        tick_size=SERIAL_TAPE_QUANTUM,
    )


def test_tape_cache_roundtrip_and_idempotent_raw_loader(tmp_path: Path) -> None:
    source = _tape()
    calls = 0

    def raw_loader() -> SerialTape:
        nonlocal calls
        calls += 1
        return source

    first = load_or_build_tape(
        _manifest(),
        start=START,
        end_exclusive=START + timedelta(seconds=4),
        artifact_root=tmp_path,
        raw_loader=raw_loader,
    )
    second = load_or_build_tape(
        _manifest(),
        start=START,
        end_exclusive=START + timedelta(seconds=4),
        artifact_root=tmp_path,
        raw_loader=lambda: pytest.fail("READY cache must not call raw loader"),
    )

    assert calls == 1
    assert first.reused is False
    assert second.reused is True
    assert second.tape.tape_hash == first.manifest.tape_hash
    assert list(second.tape.events) == list(source.events)
    assert list(second.tape.price_ticks) == list(source.price_ticks)
    assert {key: list(value) for key, value in second.tape.occurrences.items()} == {
        key: list(value) for key, value in source.occurrences.items()
    }
    cache = tape_cache_dir(first.manifest.cache_key, tmp_path)
    assert set(path.name for path in cache.glob("*.npy")) == {
        "events.npy",
        "price_ticks.npy",
        "occurrence_prices.npy",
        "occurrence_offsets.npy",
        "occurrence_events.npy",
    }
    for name, expected in {
        "events.npy": "<i8",
        "price_ticks.npy": "<i4",
        "occurrence_prices.npy": "<i4",
        "occurrence_offsets.npy": "<i8",
        "occurrence_events.npy": "<i8",
    }.items():
        assert np.load(cache / name, allow_pickle=False).dtype.str == expected


def test_tape_cache_corruption_fails_closed(tmp_path: Path) -> None:
    result = load_or_build_tape(
        _manifest(),
        start=START,
        end_exclusive=START + timedelta(seconds=4),
        artifact_root=tmp_path,
        raw_loader=_tape,
    )
    cache = tape_cache_dir(result.manifest.cache_key, tmp_path)
    del result
    gc.collect()
    (cache / "price_ticks.npy").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match=r"failed SHA256|unexpected"):
        load_or_build_tape(
            _manifest(),
            start=START,
            end_exclusive=START + timedelta(seconds=4),
            artifact_root=tmp_path,
            raw_loader=lambda: pytest.fail("corrupt READY cache must not rebuild"),
        )


def test_tape_cache_manifest_contains_identity_and_memory_metadata(tmp_path: Path) -> None:
    result = load_or_build_tape(
        _manifest(),
        start=START,
        end_exclusive=START + timedelta(seconds=4),
        artifact_root=tmp_path,
        raw_loader=_tape,
    )
    cache = tape_cache_dir(result.manifest.cache_key, tmp_path)
    manifest = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "READY"
    assert manifest["dataset_hash"] == "dataset-hash"
    assert manifest["quantum"] == "0.00001"
    assert manifest["records"] == 4
    assert manifest["cache_key"] != manifest["tape_hash"]
    assert manifest["memory_footprint_bytes"] > 0
    assert set(manifest["files"]) == {
        "events",
        "price_ticks",
        "occurrence_prices",
        "occurrence_offsets",
        "occurrence_events",
    }


def test_tape_hash_binds_causal_evidence_metadata(tmp_path: Path) -> None:
    result = load_or_build_tape(
        _manifest(),
        start=START,
        end_exclusive=START + timedelta(seconds=4),
        artifact_root=tmp_path,
        raw_loader=_tape,
    )
    cache = tape_cache_dir(result.manifest.cache_key, tmp_path)
    del result
    gc.collect()
    manifest_path = cache / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["observed_tick_evidence_event"] = int(_tape().events[0])
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="tape hash does not bind"):
        load_or_build_tape(
            _manifest(),
            start=START,
            end_exclusive=START + timedelta(seconds=4),
            artifact_root=tmp_path,
            raw_loader=lambda: pytest.fail("tampered READY cache must not rebuild"),
        )


def test_market_profile_cache_reuses_valid_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    end = START + timedelta(hours=1)
    hour = MarketHour(
        start=START,
        end_exclusive=end,
        trade_records=1,
        individual_trades=1,
        base_volume=Decimal("1"),
        quote_volume=Decimal("1"),
        aggressive_buy_base_volume=Decimal("1"),
        aggressive_sell_base_volume=Decimal("0"),
        open_price=Decimal("1"),
        high_price=Decimal("1"),
        low_price=Decimal("1"),
        close_price=Decimal("1"),
        distinct_price_levels=1,
        price_changes=0,
        one_tick_price_changes=0,
        absolute_tick_movement=0,
        range_ticks=0,
    )
    identity = {
        "dataset_hash": "dataset-hash",
        "start": START,
        "end_exclusive": end,
        "tick_size": SERIAL_TAPE_QUANTUM,
        "tick_catalog_hash": None,
        "hours": [hour.model_dump(mode="json")],
    }
    profile = MarketHourlyProfile(
        symbol="USDCUSDT",
        dataset_hash="dataset-hash",
        start=START,
        end_exclusive=end,
        tick_size=SERIAL_TAPE_QUANTUM,
        profile_hash=canonical_hash(identity),
        hours=(hour,),
    )
    write_hourly_market_profile(
        profile, tmp_path / "usdcusdt" / "market-profiles" / profile.profile_hash
    )
    monkeypatch.setattr(
        "crypto_strategy_lab.microstructure.replay_workflow.build_hourly_market_profile",
        lambda *args, **kwargs: pytest.fail("valid profile cache must not rebuild"),
    )
    loaded, _paths, reused = load_or_build_market_profile(
        _manifest(1),
        artifact_root=tmp_path,
        start=START,
        end_exclusive=end,
        tick_size=SERIAL_TAPE_QUANTUM,
        tick_catalog=None,
    )
    assert reused is True
    assert loaded.profile_hash == profile.profile_hash
    profile_path = (
        tmp_path / "usdcusdt" / "market-profiles" / profile.profile_hash / "market-hourly.json"
    )
    profile_path.write_text("{corrupt", encoding="utf-8")
    with pytest.raises(ValueError):
        load_or_build_market_profile(
            _manifest(1),
            artifact_root=tmp_path,
            start=START,
            end_exclusive=end,
            tick_size=SERIAL_TAPE_QUANTUM,
            tick_catalog=None,
        )


def test_mmap_tape_matches_memory_replay_and_temporal_analysis(tmp_path: Path) -> None:
    source = _tape()
    result = load_or_build_tape(
        _manifest(),
        start=START,
        end_exclusive=START + timedelta(seconds=4),
        artifact_root=tmp_path,
        raw_loader=lambda: source,
    )
    config = SerialModelConfig(
        model_id="M001",
        parent_model_id=None,
        strategy=SerialStrategy.STATIC,
        lookback_minutes=1,
    )
    scenario = SerialScenarioConfig(tick_size=SERIAL_TAPE_QUANTUM)
    start = START + timedelta(seconds=1)
    end = START + timedelta(seconds=3, microseconds=1)
    memory_result = replay_serial_model(source, config, scenario, start=start, end_exclusive=end)
    mmap_result = replay_serial_model(result.tape, config, scenario, start=start, end_exclusive=end)
    assert mmap_result == memory_result
    memory_analysis = analyze_replay_temporally(memory_result, source)
    mmap_analysis = analyze_replay_temporally(mmap_result, result.tape)
    assert mmap_analysis == memory_analysis


def test_mmap_preserves_same_timestamp_evidence_and_m006_reselection(tmp_path: Path) -> None:
    transition_start = START + timedelta(seconds=30)
    tick_change = START + timedelta(seconds=90)
    end = START + timedelta(minutes=2)
    catalog = TickCatalog(
        periods=(
            TickPeriod(
                start=datetime(2025, 1, 1, tzinfo=UTC),
                end_exclusive=tick_change,
                tick_size=Decimal("0.0001"),
            ),
            TickPeriod(start=tick_change, tick_size=SERIAL_TAPE_QUANTUM),
        ),
        transitions=(
            TickTransition(
                start=transition_start,
                end_exclusive=tick_change,
                allowed_tick_sizes=(Decimal("0.0001"), SERIAL_TAPE_QUANTUM),
                evidence="fixture rollout",
            ),
        ),
    )
    source = SerialTape.from_events(
        [
            (START - timedelta(seconds=60), Decimal("0.99900")),
            (START - timedelta(seconds=59), Decimal("0.99910")),
            (START + timedelta(seconds=1), Decimal("0.99900")),
            (START + timedelta(seconds=2), Decimal("0.99910")),
            (transition_start, Decimal("0.99900")),
            (transition_start, Decimal("0.99901")),
            (transition_start + timedelta(seconds=1), Decimal("0.99902")),
            (START + timedelta(seconds=61), Decimal("0.99901")),
            (START + timedelta(seconds=62), Decimal("0.99902")),
            (end - timedelta(microseconds=1), Decimal("1.00000")),
        ],
        tick_size=SERIAL_TAPE_QUANTUM,
        tick_catalog=catalog,
    )
    manifest = _manifest(len(source.events)).model_copy(
        update={
            "first_timestamp": START - timedelta(seconds=60),
            "last_timestamp": end - timedelta(microseconds=1),
        }
    )
    cached = load_or_build_tape(
        manifest,
        start=START - timedelta(seconds=60),
        end_exclusive=end,
        artifact_root=tmp_path,
        tick_catalog=catalog,
        raw_loader=lambda: source,
    )
    assert source.observed_tick_evidence_event is not None
    assert source.observed_tick_evidence_event % EVENT_ORDER_SCALE == 1
    assert cached.tape.observed_tick_evidence_event == source.observed_tick_evidence_event

    model = preregistered_corrected_block()[1].model_copy(
        update={"lookback_minutes": 1, "decision_interval_minutes": 1}
    )
    scenario = SerialScenarioConfig(
        tick_size=SERIAL_TAPE_QUANTUM,
        historical_tick_catalog_hash=catalog.catalog_hash,
        historical_tick_source_url=catalog.source_url,
        historical_tick_policy="CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
    )
    memory_result = replay_serial_model(
        source,
        model,
        scenario,
        start=START,
        end_exclusive=end,
        tick_catalog=catalog,
    )
    mmap_result = replay_serial_model(
        cached.tape,
        model,
        scenario,
        start=START,
        end_exclusive=end,
        tick_catalog=catalog,
    )
    assert mmap_result == memory_result
    assert any(
        change.selected_tick_at_selection == SERIAL_TAPE_QUANTUM
        for change in mmap_result.selection_changes
    )
