from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zipfile import ZipFile

import pytest

from crypto_strategy_lab.microstructure.data import (
    MicrostructureIntegrityError,
    download_history_range,
    manifest_from_archive,
    reconcile_history_manifest,
    slice_history_manifest,
    verify_history_manifest,
)
from crypto_strategy_lab.microstructure.serial_replay import load_serial_tape


def _archive(path, rows):
    with ZipFile(path, "w") as archive:
        archive.writestr("trades.csv", "\n".join(",".join(row) for row in rows))
    return path


def _trade(trade_id: int, stamp: datetime) -> list[str]:
    return [
        str(trade_id),
        "1",
        "1",
        "1",
        str(int(stamp.timestamp() * 1000)),
        "false",
    ]


def _daily_manifest(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    day_one = _archive(
        source / "USDCUSDT-trades-2024-01-01.zip",
        [_trade(1, datetime(2024, 1, 1, tzinfo=UTC))],
    )
    day_three = _archive(
        source / "USDCUSDT-trades-2024-01-03.zip",
        [_trade(3, datetime(2024, 1, 3, tzinfo=UTC))],
    )
    entries = [
        (f"data/spot/daily/trades/USDCUSDT/{path.name}", f"fixture://{path.name}")
        for path in (day_one, day_three)
    ]
    by_name = {path.name: path for path in (day_one, day_three)}
    monkeypatch.setattr(
        "crypto_strategy_lab.microstructure.data.list_daily_archives",
        lambda _symbol, _kind: entries,
    )

    def copy_archive(url, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(by_name[url.rsplit("/", 1)[-1]].read_bytes())
        return destination

    monkeypatch.setattr("crypto_strategy_lab.microstructure.data.download_archive", copy_archive)
    return download_history_range(
        "USDCUSDT",
        tmp_path / "daily",
        start=date(2024, 1, 1),
        end=date(2024, 1, 3),
        kind="trades",
    )


def test_reconcile_month_authority_has_complete_coverage_without_double_count(
    tmp_path, monkeypatch
):
    daily = _daily_manifest(tmp_path, monkeypatch)
    monthly_source = _archive(
        tmp_path / "USDCUSDT-trades-2024-01.zip",
        [_trade(i, datetime(2024, 1, i, tzinfo=UTC)) for i in (1, 2, 3)],
    )
    monkeypatch.setattr(
        "crypto_strategy_lab.microstructure.data.list_monthly_archives",
        lambda _symbol, _kind: [
            (
                "data/spot/monthly/trades/USDCUSDT/USDCUSDT-trades-2024-01.zip",
                "fixture://USDCUSDT-trades-2024-01.zip",
            )
        ],
    )

    def copy_monthly(_url, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(monthly_source.read_bytes())
        return destination

    monkeypatch.setattr("crypto_strategy_lab.microstructure.data.download_archive", copy_monthly)
    monkeypatch.setattr(
        "crypto_strategy_lab.microstructure.data.parse_archive",
        lambda *_args, **_kwargs: pytest.fail("monthly reconciliation must stream"),
    )
    reconciled = reconcile_history_manifest(daily, tmp_path / "monthly")

    assert len(reconciled.archives) == 1
    assert reconciled.archives[0].cadence == "monthly"
    assert reconciled.missing_dates == ()
    assert reconciled.total_records == 3
    assert reconciled.integrity_status == "VALID"
    verify_history_manifest(reconciled)

    sliced = slice_history_manifest(reconciled, start=date(2024, 1, 2), end=date(2024, 1, 2))
    assert len(sliced.archives) == 1
    assert sliced.total_records == 3
    verify_history_manifest(sliced)

    # Older callers may still pass a mixed manifest; the monthly archive remains
    # authoritative at load time and the daily overlap is not counted twice.
    mixed = reconciled.model_copy(
        update={
            "archives": (daily.archives[0], *reconciled.archives),
            "integrity_status": "VALID",
            "invalidity_reasons": (),
        }
    )
    tape = load_serial_tape(
        mixed,
        tick_size=Decimal("0.01"),
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end_exclusive=datetime(2024, 1, 3, tzinfo=UTC) + timedelta(microseconds=1),
    )
    assert len(tape.events) == 3


def test_reconcile_fails_explicitly_when_monthly_archive_missing(tmp_path, monkeypatch):
    daily = _daily_manifest(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "crypto_strategy_lab.microstructure.data.list_monthly_archives",
        lambda _symbol, _kind: [],
    )
    with pytest.raises(MicrostructureIntegrityError, match="monthly trades archive is missing"):
        reconcile_history_manifest(daily, tmp_path / "monthly")


def test_reconcile_fails_explicitly_when_monthly_archive_corrupt(tmp_path, monkeypatch):
    daily = _daily_manifest(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "crypto_strategy_lab.microstructure.data.list_monthly_archives",
        lambda _symbol, _kind: [
            (
                "data/spot/monthly/trades/USDCUSDT/USDCUSDT-trades-2024-01.zip",
                "fixture://monthly",
            )
        ],
    )

    def corrupt(_url, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"not a zip")
        return destination

    monkeypatch.setattr("crypto_strategy_lab.microstructure.data.download_archive", corrupt)
    with pytest.raises(MicrostructureIntegrityError, match="absent or corrupt"):
        reconcile_history_manifest(daily, tmp_path / "monthly")


def test_streaming_manifest_detects_gap_duplicate_and_off_period(tmp_path):
    malformed = _archive(
        tmp_path / "USDCUSDT-trades-2024-01-01.zip",
        [
            _trade(1, datetime(2024, 1, 1, tzinfo=UTC)),
            _trade(3, datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC)),
            _trade(3, datetime(2024, 1, 1, 0, 0, 2, tzinfo=UTC)),
        ],
    )
    manifest = manifest_from_archive(
        malformed,
        origin="fixture://daily",
        period="2024-01-01",
        symbol="USDCUSDT",
        kind="trades",
    )
    assert manifest.gaps == [(1, 3)]
    assert manifest.duplicates == [3]
    assert manifest.integrity_status == "INVALID"

    off_period = _archive(
        tmp_path / "USDCUSDT-trades-2024-01.zip",
        [_trade(1, datetime(2024, 2, 1, tzinfo=UTC))],
    )
    with pytest.raises(MicrostructureIntegrityError, match="outside"):
        manifest_from_archive(
            off_period,
            origin="fixture://monthly",
            period="2024-01",
            symbol="USDCUSDT",
            kind="trades",
            cadence="monthly",
        )
