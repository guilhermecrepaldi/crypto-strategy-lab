from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError

import pytest

from crypto_strategy_lab.data import history
from crypto_strategy_lab.data.binance import DatasetIntegrityError
from crypto_strategy_lab.data.history import (
    GapPolicy,
    HistoricalCatalogEntry,
    HistoricalCatalogManifest,
    HistoricalDatasetManifest,
    discover_historical_catalog,
    ingest_history_period,
    load_normalized_history,
    rank_catalog_by_daily_quote_volume,
)
from crypto_strategy_lab.data.history_reporting import build_history_audit
from crypto_strategy_lab.data.universe import select_causal_historical_universe
from crypto_strategy_lab.domain import Candle
from crypto_strategy_lab.ml.historical_workflow import run_historical_smoke


def _candle(symbol: str, open_time: datetime, volume: str) -> Candle:
    return Candle(
        symbol=symbol,
        open_time=open_time,
        close_time=open_time + timedelta(minutes=5) - timedelta(microseconds=1),
        available_at=open_time + timedelta(minutes=5) - timedelta(microseconds=1),
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=Decimal(volume),
        quote_asset_volume=Decimal(volume),
        trade_count=1,
    )


def _write_archive(root: Path, symbol: str, rows: list[str]) -> None:
    directory = root / symbol / "5m"
    directory.mkdir(parents=True)
    filename = f"{symbol}-5m-2021-01.zip"
    path = directory / filename
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(filename.removesuffix(".zip") + ".csv", "\n".join(rows))
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(f"{filename}.CHECKSUM").write_text(f"{checksum}  {filename}\n", encoding="ascii")


def _row(open_time: datetime) -> str:
    opened = int(open_time.timestamp() * 1000)
    closed = int((open_time + timedelta(minutes=5) - timedelta(milliseconds=1)).timestamp() * 1000)
    return f"{opened},1,1,1,1,10,{closed},10,1,5,5,0"


def _write_daily_archive(root: Path, symbol: str, rows: list[tuple[datetime, Decimal]]) -> None:
    directory = root / symbol / "1d"
    directory.mkdir(parents=True)
    filename = f"{symbol}-1d-2022-01.zip"
    path = directory / filename
    payload = []
    for open_time, quote_volume in rows:
        opened = int(open_time.timestamp() * 1000)
        closed = int((open_time + timedelta(days=1) - timedelta(milliseconds=1)).timestamp() * 1000)
        payload.append(f"{opened},1,1,1,1,10,{closed},{quote_volume},1,5,5,0")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(filename.removesuffix(".zip") + ".csv", "\n".join(payload))
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(f"{filename}.CHECKSUM").write_text(f"{checksum}  {filename}\n", encoding="ascii")


def test_ingestion_is_offline_reproducible_and_gap_policy_is_explicit(
    tmp_path: Path, monkeypatch
) -> None:
    start = datetime(2021, 1, 1, tzinfo=UTC)
    end = start + timedelta(minutes=15)
    raw = tmp_path / "raw"
    _write_archive(raw, "BTCUSDT", [_row(start + timedelta(minutes=5 * i)) for i in range(3)])
    normalized = tmp_path / "history.jsonl.gz"
    manifest_path = tmp_path / "manifest.json"
    first = ingest_history_period(
        ["BTCUSDT"],
        start=start,
        end=end,
        raw_root=raw,
        normalized_path=normalized,
        manifest_path=manifest_path,
    )
    second = ingest_history_period(
        ["BTCUSDT"],
        start=start,
        end=end,
        raw_root=raw,
        normalized_path=normalized,
        manifest_path=manifest_path,
    )
    assert first.dataset_hash == second.dataset_hash
    assert first.coverage[0].missing_count == 0
    monkeypatch.setattr(history, "download_verified_archive", lambda *args, **kwargs: pytest.fail())
    assert len(load_normalized_history(normalized)) == 3

    _write_archive(raw, "ETHUSDT", [_row(start), _row(start + timedelta(minutes=10))])
    with pytest.raises(DatasetIntegrityError, match="incomplete symbol coverage"):
        ingest_history_period(
            ["ETHUSDT"],
            start=start,
            end=end,
            raw_root=raw,
            normalized_path=tmp_path / "invalid.jsonl.gz",
            manifest_path=tmp_path / "invalid.json",
            gap_policy=GapPolicy.STOP,
        )
    invalid = ingest_history_period(
        ["ETHUSDT"],
        start=start,
        end=end,
        raw_root=raw,
        normalized_path=tmp_path / "invalid.jsonl.gz",
        manifest_path=tmp_path / "invalid.json",
        gap_policy=GapPolicy.INVALIDATE_EPISODE,
    )
    assert invalid.coverage[0].valid is False
    assert invalid.coverage[0].missing_count == 1


def test_selection_uses_only_complete_pre_episode_history() -> None:
    episode_start = datetime(2022, 1, 1, tzinfo=UTC)
    times = [episode_start - timedelta(minutes=value) for value in (15, 10, 5)]
    volumes = {
        "BTCUSDT": "100",
        "ETHUSDT": "90",
        "BNBUSDT": "80",
        "ADAUSDT": "70",
        "DOGEUSDT": "60",
        "USDCUSDT": "1000",
        "BTCUPUSDT": "900",
    }
    candles = [
        _candle(symbol, candle_time, volume)
        for symbol, volume in volumes.items()
        for candle_time in times
    ]
    candles.append(_candle("NEWUSDT", times[-1], "10000"))
    candles.append(_candle("DOGEUSDT", episode_start, "999999999"))
    candles.append(_candle("DOGEUSDT", episode_start - timedelta(days=1), "999999999"))
    first = select_causal_historical_universe(
        candles, episode_start=episode_start, lookback=timedelta(minutes=15)
    )
    second = select_causal_historical_universe(
        list(reversed(candles)), episode_start=episode_start, lookback=timedelta(minutes=15)
    )
    assert first.selected_symbols == ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"]
    assert first.selection_hash == second.selection_hash
    assert "USDCUSDT" in first.exclusions
    assert "BTCUPUSDT" in first.exclusions
    assert first.exclusions["NEWUSDT"].startswith("asset did not cover")
    assert all(item.last_available_at < episode_start for item in first.ranking)


def test_locked_manifest_is_rejected_before_dataset_is_opened(tmp_path: Path) -> None:
    instant = datetime(2021, 1, 1, tzinfo=UTC)
    manifest = HistoricalDatasetManifest(
        generated_at=instant,
        requested_start=instant,
        requested_end=instant + timedelta(days=1),
        data_available_until=instant,
        gap_policy=GapPolicy.STOP,
        archives=[],
        coverage=[],
        symbols=[],
        candle_count=0,
        archive_bytes=0,
        duplicate_count=0,
        invalid_timestamp_count=0,
        dataset_hash="a" * 64,
        normalized_path=str(tmp_path / "must-not-be-opened.gz"),
        locked_test_accessed=True,
    )
    path = tmp_path / "locked.json"
    path.write_text(json.dumps(manifest.model_dump(mode="json")), encoding="utf-8")
    with pytest.raises(ValueError, match="LOCKED_TEST"):
        build_history_audit(path, episode_start=instant, lookback_days=1)
    with pytest.raises(ValueError, match="LOCKED_TEST"):
        run_historical_smoke(
            path,
            train_start=instant,
            validation_start=instant + timedelta(days=90),
            validation_end=instant + timedelta(days=180),
            durations_days=(30, 90),
            seeds=(11, 29),
            total_timesteps=1,
            artifact_dir=tmp_path / "artifacts",
        )


def test_catalog_uses_historical_archive_evidence_not_current_status(monkeypatch) -> None:
    listing = b"""<?xml version="1.0" encoding="UTF-8"?>
    <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
      <IsTruncated>false</IsTruncated>
      <CommonPrefixes><Prefix>data/spot/monthly/klines/BTCUSDT/</Prefix></CommonPrefixes>
      <CommonPrefixes><Prefix>data/spot/monthly/klines/NEWUSDT/</Prefix></CommonPrefixes>
      <CommonPrefixes><Prefix>data/spot/monthly/klines/USDCUSDT/</Prefix></CommonPrefixes>
      <CommonPrefixes><Prefix>data/spot/monthly/klines/BTCUPUSDT/</Prefix></CommonPrefixes>
    </ListBucketResult>"""

    def fake_read(url: str) -> bytes:
        if "amazonaws.com" in url:
            return listing
        if "BTCUSDT" in url:
            return ("a" * 64 + "  archive.zip\n").encode()
        raise HTTPError(url, 404, "missing historical archive", None, None)

    monkeypatch.setattr(history, "_read_url", fake_read)
    catalog = discover_historical_catalog(
        effective_at=datetime(2022, 2, 1, tzinfo=UTC),
        lookback=timedelta(days=31),
        max_workers=1,
    )
    assert [item.symbol for item in catalog.entries] == ["BTCUSDT"]
    assert catalog.uses_current_exchange_status is False
    assert catalog.exclusions["NEWUSDT"].startswith("no complete")
    assert catalog.exclusions["USDCUSDT"] == "stablecoin base asset"
    assert catalog.exclusions["BTCUPUSDT"] == "leveraged token"


def test_complete_catalog_ranking_excludes_incomplete_daily_history(tmp_path: Path) -> None:
    start = datetime(2022, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=3)
    entries = [
        HistoricalCatalogEntry(symbol=symbol, monthly_archives=[], checksum_sha256=[])
        for symbol in ("BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "NEWUSDT")
    ]
    catalog = HistoricalCatalogManifest(
        generated_at=start,
        effective_at=end,
        lookback_start=start,
        entries=entries,
        exclusions={},
        catalog_hash="b" * 64,
    )
    days = [start + timedelta(days=index) for index in range(3)]
    _write_daily_archive(tmp_path, "BTCUSDT", [(item, Decimal("100")) for item in days])
    _write_daily_archive(tmp_path, "ETHUSDT", [(item, Decimal("90")) for item in days])
    _write_daily_archive(tmp_path, "BNBUSDT", [(item, Decimal("80")) for item in days])
    _write_daily_archive(tmp_path, "ADAUSDT", [(item, Decimal("70")) for item in days])
    _write_daily_archive(tmp_path, "NEWUSDT", [(item, Decimal("1000")) for item in days[1:]])
    audit = rank_catalog_by_daily_quote_volume(catalog, raw_root=tmp_path)
    assert [item.symbol for item in audit.ranking] == [
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "ADAUSDT",
    ]
    assert audit.exclusions["NEWUSDT"].startswith("incomplete daily coverage")
    assert audit.future_rows_used == 0
