import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from crypto_strategy_lab.microstructure.data import (
    HistoryManifest,
    manifest_for,
    parse_archive,
)
from crypto_strategy_lab.microstructure.market_profile import build_hourly_market_profile
from crypto_strategy_lab.microstructure.serial_replay import (
    SERIAL_TAPE_QUANTUM,
    USDCUSDT_FINE_GRID_OBSERVED_FROM,
    USDCUSDT_TICK_CATALOG,
    USDCUSDT_TICK_CHANGE,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def test_hourly_market_profile_streams_exact_volume_and_activity(tmp_path: Path) -> None:
    archive = tmp_path / "USDCUSDT-trades-2026-01-01.zip"
    stamp = int(START.timestamp() * 1_000_000)
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "USDCUSDT-trades-2026-01-01.csv",
            f"1,0.9998,2,0,{stamp},true,true\n"
            f"2,0.9999,3,0,{stamp + 1_000_000},false,true\n"
            f"3,1.0000,5,0,{stamp + 3_600_000_000},false,true\n",
        )
    events = parse_archive(archive, "trades")
    item = manifest_for(
        archive,
        events,
        origin="official-fixture",
        period="2026-01-01",
        symbol="USDCUSDT",
        kind="trades",
    )
    manifest = HistoryManifest(
        symbol="USDCUSDT",
        kind="trades",
        requested_start=START.date(),
        requested_end=START.date(),
        all_available=False,
        discovered_first_date=START.date(),
        discovered_last_date=START.date(),
        archives=(item,),
        missing_dates=(),
        cross_archive_gaps=(),
        cross_archive_overlaps=(),
        total_records=3,
        total_size_bytes=item.size_bytes,
        first_timestamp=events[0].timestamp,
        last_timestamp=events[-1].timestamp,
        dataset_hash="dataset",
        integrity_status="VALID",
    )

    profile = build_hourly_market_profile(
        manifest,
        start=START,
        end_exclusive=events[-1].timestamp + timedelta(microseconds=1),
        tick_size=Decimal("0.0001"),
    )

    assert len(profile.hours) == 2
    assert profile.hours[0].trade_records == 2
    assert profile.hours[0].base_volume == Decimal("5")
    assert profile.hours[0].quote_volume == Decimal("4.9993")
    assert profile.hours[0].aggressive_sell_base_volume == Decimal("2")
    assert profile.hours[0].aggressive_buy_base_volume == Decimal("3")
    assert profile.hours[0].range_ticks == 1
    assert profile.hours[0].one_tick_price_changes == 1
    assert profile.hours[1].trade_records == 1


def test_market_profile_uses_historical_tick_and_accepts_rollout_window(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "USDCUSDT-trades-2026-04-14.zip"
    before = USDCUSDT_FINE_GRID_OBSERVED_FROM - timedelta(seconds=1)
    timestamps = (
        int(before.timestamp() * 1_000_000),
        int(USDCUSDT_FINE_GRID_OBSERVED_FROM.timestamp() * 1_000_000),
        int((USDCUSDT_TICK_CHANGE + timedelta(seconds=1)).timestamp() * 1_000_000),
    )
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "USDCUSDT-trades-2026-04-14.csv",
            f"1,0.99950,1,0,{timestamps[0]},true,true\n"
            f"2,0.99949,1,0,{timestamps[1]},false,true\n"
            f"3,0.99948,1,0,{timestamps[2]},false,true\n",
        )
    events = parse_archive(archive, "trades")
    item = manifest_for(
        archive,
        events,
        origin="official-fixture",
        period="2026-04-14",
        symbol="USDCUSDT",
        kind="trades",
    )
    manifest = HistoryManifest(
        symbol="USDCUSDT",
        kind="trades",
        requested_start=before.date(),
        requested_end=before.date(),
        all_available=False,
        discovered_first_date=before.date(),
        discovered_last_date=before.date(),
        archives=(item,),
        missing_dates=(),
        cross_archive_gaps=(),
        cross_archive_overlaps=(),
        total_records=3,
        total_size_bytes=item.size_bytes,
        first_timestamp=events[0].timestamp,
        last_timestamp=events[-1].timestamp,
        dataset_hash="dataset-transition",
        integrity_status="VALID",
    )

    profile = build_hourly_market_profile(
        manifest,
        start=before,
        end_exclusive=events[-1].timestamp + timedelta(microseconds=1),
        tick_size=SERIAL_TAPE_QUANTUM,
        tick_catalog=USDCUSDT_TICK_CATALOG,
    )

    assert profile.tick_catalog_hash == USDCUSDT_TICK_CATALOG.catalog_hash
    assert profile.hours[0].tick_size is None
    assert profile.hours[0].physical_tick_sizes == (
        Decimal("0.00001"),
        Decimal("0.0001"),
    )
    assert profile.hours[0].tick_regime_ambiguous is True
    assert profile.hours[0].one_tick_price_changes is None
    assert profile.hours[0].absolute_tick_movement == 1
    assert profile.hours[1].tick_size == Decimal("0.00001")
