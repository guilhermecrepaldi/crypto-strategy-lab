from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from crypto_strategy_lab.data import binance
from crypto_strategy_lab.data.binance import (
    DatasetIntegrityError,
    download_verified_archive,
    epoch_to_utc,
    monthly_kline_url,
    parse_kline_archive,
)


def _archive(path: Path, rows: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("BTCUSDT-5m.csv", "\n".join(rows))
    return path


def test_epoch_parser_detects_milliseconds_and_microseconds() -> None:
    assert epoch_to_utc("1640995200000") == datetime(2022, 1, 1, tzinfo=UTC)
    assert epoch_to_utc("1735689600000000") == datetime(2025, 1, 1, tzinfo=UTC)


def test_parser_uses_decimal_and_rejects_future(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "sample.zip",
        ["1640995200000,47000.1,47100.2,46900.3,47050.4,1.5,1640995499999,70575.6,12,0.8,37640,0"],
    )
    candles = parse_kline_archive(archive, "btcusdt")
    assert str(candles[0].open) == "47000.1"
    with pytest.raises(DatasetIntegrityError, match="future"):
        parse_kline_archive(archive, "BTCUSDT", not_after=datetime(2021, 1, 1, tzinfo=UTC))


def test_parser_rejects_unsafe_zip_layout(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("nested/data.csv", "x")
    with pytest.raises(DatasetIntegrityError):
        parse_kline_archive(archive, "BTCUSDT")


def test_official_monthly_url_is_stable() -> None:
    assert monthly_kline_url("btcusdt", 2021, 12).endswith("/BTCUSDT/5m/BTCUSDT-5m-2021-12.zip")


def test_downloader_is_checksum_verified_and_idempotent(tmp_path: Path, monkeypatch) -> None:
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("BTCUSDT-5m.csv", "fixture")
    payload = archive_bytes.getvalue()
    expected = hashlib.sha256(payload).hexdigest()
    download_calls = 0

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    def fake_urlopen(*args, **kwargs):
        nonlocal download_calls
        del args, kwargs
        download_calls += 1
        return Response(payload)

    monkeypatch.setattr(binance, "_read_url", lambda _url: f"{expected} file.zip".encode())
    monkeypatch.setattr(binance.urllib.request, "urlopen", fake_urlopen)
    url = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/5m/file.zip"
    first = download_verified_archive(url, tmp_path)
    second = download_verified_archive(url, tmp_path)
    assert first.sha256 == second.sha256 == expected
    assert download_calls == 1
