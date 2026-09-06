from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from crypto_strategy_lab.microstructure.campaign import register_first_block
from crypto_strategy_lab.microstructure.data import HistoryManifest
from crypto_strategy_lab.microstructure.market_profile import MarketHour, MarketHourlyProfile
from crypto_strategy_lab.microstructure.replay_workflow import run_full_replay_campaign
from crypto_strategy_lab.microstructure.serial_replay import SerialTape
from crypto_strategy_lab.ml.model_registry import (
    REQUIRED_EVALUATION_FILES,
    ModelRegistry,
    ModelStatus,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def test_full_replay_writes_complete_evidence_and_never_economic_stops(
    tmp_path: Path, monkeypatch: object
) -> None:
    end = START + timedelta(hours=6)
    tape = SerialTape.from_events(
        [
            (START - timedelta(minutes=2), Decimal("0.9998")),
            (START - timedelta(minutes=1), Decimal("0.9999")),
            (START + timedelta(seconds=1), Decimal("0.9998")),
            (START + timedelta(seconds=2), Decimal("0.9999")),
            (START + timedelta(hours=3), Decimal("0.9998")),
            (START + timedelta(hours=3, seconds=1), Decimal("0.9999")),
            (end - timedelta(microseconds=1), Decimal("1.0000")),
        ],
        tick_size=Decimal("0.0001"),
    )
    manifest = HistoryManifest(
        symbol="USDCUSDT",
        kind="trades",
        requested_start=date(2025, 12, 31),
        requested_end=date(2026, 1, 1),
        all_available=False,
        discovered_first_date=date(2025, 12, 31),
        discovered_last_date=date(2026, 1, 1),
        archives=(),
        missing_dates=(),
        cross_archive_gaps=(),
        cross_archive_overlaps=(),
        total_records=len(tape.events),
        total_size_bytes=1,
        first_timestamp=START - timedelta(days=1),
        last_timestamp=end - timedelta(microseconds=1),
        dataset_hash="dataset-hash",
        integrity_status="VALID",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    market_profile = MarketHourlyProfile(
        symbol="USDCUSDT",
        dataset_hash=manifest.dataset_hash,
        start=START,
        end_exclusive=end,
        tick_size=Decimal("0.0001"),
        profile_hash="profile-hash",
        hours=tuple(
            MarketHour(
                start=START + timedelta(hours=hour),
                end_exclusive=START + timedelta(hours=hour + 1),
                trade_records=2,
                individual_trades=2,
                base_volume=Decimal("2"),
                quote_volume=Decimal("2"),
                aggressive_buy_base_volume=Decimal("1"),
                aggressive_sell_base_volume=Decimal("1"),
                open_price=Decimal("0.9998"),
                high_price=Decimal("0.9999"),
                low_price=Decimal("0.9998"),
                close_price=Decimal("0.9999"),
                distinct_price_levels=2,
                price_changes=1,
                one_tick_price_changes=1,
                absolute_tick_movement=1,
                range_ticks=1,
            )
            for hour in range(6)
        ),
    )
    artifacts = tmp_path / "artifacts"
    reports = tmp_path / "reports"
    register_first_block(artifact_root=artifacts, report_root=reports)
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "crypto_strategy_lab.microstructure.replay_workflow.load_serial_tape",
        lambda *args, **kwargs: tape,
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "crypto_strategy_lab.microstructure.replay_workflow.build_hourly_market_profile",
        lambda *args, **kwargs: market_profile,
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "crypto_strategy_lab.microstructure.replay_workflow._git_head", lambda: "abc123"
    )

    records = run_full_replay_campaign(manifest_path, artifact_root=artifacts, report_root=reports)
    registry = ModelRegistry(artifact_root=artifacts, report_root=reports)

    assert all(
        registry.current_status(f"M{index:03}") == ModelStatus.EVALUATED for index in range(1, 5)
    )
    evaluations = [
        item for item in registry.journal() if item["event_type"] == "EVALUATION_RECORDED"
    ]
    assert len(evaluations) == 4
    for event in evaluations:
        directory = Path(event["payload"]["artifact_directory"])
        assert all((directory / name).exists() for name in REQUIRED_EVALUATION_FILES)
        assert event["payload"]["decision"]["early_stop"] is False
        assert event["payload"]["decision"]["full_replay_completed"] is True
    assert (reports / "usdcusdt" / "market-productivity-regime.json").exists()
    assert (reports / "usdcusdt" / "temporal-productivity.html").exists()
    assert any(item.get("kind") == "MARKET_PRODUCTIVITY_REGIME" for item in records)
    assert not (artifacts / "usdcusdt" / "models" / ".full-replay.lock").exists()
