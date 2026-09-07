import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from crypto_strategy_lab.microstructure.campaign import register_active_block
from crypto_strategy_lab.microstructure.data import HistoryManifest
from crypto_strategy_lab.microstructure.market_profile import MarketHour, MarketHourlyProfile
from crypto_strategy_lab.microstructure.replay_workflow import run_full_replay_campaign
from crypto_strategy_lab.microstructure.serial_replay import SERIAL_TAPE_QUANTUM, SerialTape
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
        tick_size=SERIAL_TAPE_QUANTUM,
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
        tick_size=SERIAL_TAPE_QUANTUM,
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
    register_active_block(artifact_root=artifacts, report_root=reports)
    registry_before_replay = ModelRegistry(artifact_root=artifacts, report_root=reports)
    registry_before_replay.transition("M006", ModelStatus.RUNNING, reason="partial replay started")
    registry_before_replay.transition(
        "M006", ModelStatus.INCONCLUSIVE, reason="partial replay interrupted"
    )
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
        registry.current_status(f"M{index:03}") == ModelStatus.EVALUATED for index in range(5, 9)
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
        assert event["payload"]["metrics"]["initial_capital"] == "100"
        assert event["payload"]["metrics"]["currency"] == "USDT"
        assert event["payload"]["metrics"]["capital_mode"] == "COMPOUNDING"
    runs = [item for item in registry.journal() if item["event_type"] == "RUN_REGISTERED"]
    assert {item["payload"]["model_id"] for item in runs} == {
        f"M{index:03}" for index in range(5, 9)
    }
    for event in runs:
        payload = event["payload"]
        assert payload["initial_capital"] == "100"
        assert payload["currency"] == "USDT"
        assert payload["capital_mode"] == "COMPOUNDING"
        manifest_payload = json.loads(
            (Path(payload["artifact_directory"]) / "run-manifest.json").read_text()
        )
        assert manifest_payload["initial_capital"] == "100"
        assert manifest_payload["currency"] == "USDT"
        assert manifest_payload["capital_mode"] == "COMPOUNDING"
    scoreboard = (reports / "usdcusdt" / "model-registry.csv").read_text()
    assert "initial_capital" in scoreboard
    assert "currency" in scoreboard
    assert "capital_mode" in scoreboard
    assert (reports / "usdcusdt" / "market-productivity-regime.json").exists()
    dashboard_path = reports / "usdcusdt" / "temporal-productivity.html"
    assert dashboard_path.exists()
    dashboard = dashboard_path.read_text()
    assert "Compounding: 100" in dashboard
    assert '"initial_capital": "100"' in dashboard.replace("&quot;", '"')
    assert any(item.get("kind") == "MARKET_PRODUCTIVITY_REGIME" for item in records)
    assert not (artifacts / "usdcusdt" / "models" / ".full-replay.lock").exists()
    assert any(
        item["event_type"] == "STATUS_CHANGED"
        and item["payload"].get("from") == ModelStatus.INCONCLUSIVE.value
        and item["payload"].get("to") == ModelStatus.RUNNING.value
        for item in registry.journal()
    )
    registry.transition("M005", ModelStatus.INCONCLUSIVE, reason="completed scientific autopsy")
    run_count = len([item for item in registry.journal() if item["event_type"] == "RUN_REGISTERED"])
    again = run_full_replay_campaign(
        manifest_path, artifact_root=artifacts, report_root=reports, model_ids=("M005",)
    )
    assert any(item.get("action") == "SKIPPED_COMPLETED_INCONCLUSIVE" for item in again)
    assert (
        len([item for item in registry.journal() if item["event_type"] == "RUN_REGISTERED"])
        == run_count
    )
