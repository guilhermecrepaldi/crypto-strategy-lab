from datetime import UTC, date, datetime
from hashlib import sha256
from zipfile import ZipFile

import pytest

from crypto_strategy_lab.microstructure.data import (
    ArchiveTrade,
    MicrostructureIntegrityError,
    download_archive,
    download_history_range,
    iter_archive,
    manifest_for,
    parse_archive,
    slice_history_manifest,
    timestamp_unit_for_archive,
    validate_events,
    verify_history_manifest,
)


def archive(tmp_path, rows):
    path = tmp_path / "trades.zip"
    with ZipFile(path, "w") as z:
        z.writestr("x.csv", "\n".join(",".join(row) for row in rows))
    return path


def test_parse_trades_ms_and_us(tmp_path):
    path = archive(
        tmp_path,
        [
            ["id", "price", "qty", "quote", "time", "isBuyerMaker"],
            ["1", "10.01", "2", "20.02", "1700000000000", "true"],
            ["2", "10.02", "3", "30.06", "1740000000000000", "false"],
        ],
    )
    events = parse_archive(path)
    records = list(iter_archive(path))
    assert all(isinstance(record, ArchiveTrade) for record in records)
    assert [record.trade_id for record in records] == [event.trade_id for event in events]
    assert [record.sequence for record in records] == [event.sequence for event in events]
    assert [record.timestamp for record in records] == [event.timestamp for event in events]
    assert [record.timestamp_unit for record in records] == ["milliseconds", "microseconds"]
    assert [record.individual_trade_count for record in records] == [1, 1]
    assert events[0].timestamp.tzinfo is UTC
    assert str(events[0].price) == "10.01"
    assert events[1].timestamp.microsecond == 0


def test_parse_agg_trades_us(tmp_path):
    path = archive(
        tmp_path,
        [
            ["aggTradeId", "price", "qty", "first", "last", "time", "maker"],
            ["9", "1.2", "4", "8", "10", "1740000000000000", "false"],
        ],
    )
    event = parse_archive(path, "aggTrades")[0]
    record = next(iter_archive(path, "aggTrades"))
    assert event.trade_id == 9 and event.sequence == 10
    assert record.individual_trade_count == 3
    assert record.timestamp_unit == "microseconds"


def test_manifest_is_symbol_generic_and_records_archive_timestamp_unit(tmp_path):
    path = archive(
        tmp_path,
        [["1", "1.2", "4", "8", "10", "1740000000000000", "false"]],
    )
    events = parse_archive(path, "aggTrades")

    manifest = manifest_for(
        path,
        events,
        origin="fixture://usdcusdt",
        period="2025-02-19",
        symbol="usdcusdt",
        kind="aggTrades",
    )

    assert manifest.symbol == "USDCUSDT"
    assert manifest.timestamp_unit == "microseconds"
    assert timestamp_unit_for_archive(path, "aggTrades") == "microseconds"
    assert "fdusd" not in manifest.schema_version.lower()


def test_ids_duplicates_and_gaps(tmp_path):
    rows = [[str(i), "1", "1", "1", str(i), "false"] for i in (1, 3, 3)]
    events = parse_archive(archive(tmp_path, rows))
    gaps, duplicates = validate_events(events)
    assert gaps == [(1, 3)] and duplicates == [3]
    with pytest.raises(MicrostructureIntegrityError):
        validate_events(list(reversed(events)))


def test_download_checksum_and_idempotency(tmp_path, monkeypatch):
    data = b"archive"
    checksum = sha256(data).hexdigest()
    calls = []

    class Response:
        def __init__(self, value):
            self.value = value

        def read(self):
            calls.append(1)
            return self.value

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def opener(request, *, timeout):
        assert timeout == 120
        value = (checksum + "  x\n").encode() if request.full_url.endswith("CHECKSUM") else data
        return Response(value)

    monkeypatch.setattr("urllib.request.urlopen", opener)
    dest = tmp_path / "x.zip"
    assert download_archive("https://example/x.zip", dest) == dest
    assert download_archive("https://example/x.zip", dest) == dest
    assert len(calls) == 3


def test_checksum_mismatch(tmp_path, monkeypatch):
    class Response:
        def __init__(self, value):
            self.value = value

        def read(self):
            return self.value

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def opener(request, *, timeout):
        assert timeout == 120
        value = ("0" * 64 + "  x\n").encode() if request.full_url.endswith("CHECKSUM") else b"bad"
        return Response(value)

    monkeypatch.setattr("urllib.request.urlopen", opener)
    with pytest.raises(MicrostructureIntegrityError):
        download_archive("https://example/x.zip", tmp_path / "x.zip")


def test_strict_rows_and_archive_day_are_validated(tmp_path):
    malformed = archive(
        tmp_path,
        [["1", "1", "1", "1", "1704067200000", "maybe"]],
    )
    with pytest.raises(MicrostructureIntegrityError, match="invalid row"):
        parse_archive(malformed)
    with pytest.raises(MicrostructureIntegrityError, match="invalid row"):
        list(iter_archive(malformed))

    valid = archive(
        tmp_path,
        [["1", "1", "1", "1", "1704067200000", "false"]],
    )
    events = parse_archive(valid)
    with pytest.raises(MicrostructureIntegrityError, match="outside"):
        manifest_for(
            valid,
            events,
            origin="https://data.binance.vision/x.zip",
            period="2024-01-02",
            kind="trades",
        )


def test_history_range_reports_missing_days_and_cross_archive_gaps(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    day_one = archive(
        source,
        [["1", "1", "1", "1", "1", "1704067200000", "false"]],
    )
    day_one = day_one.rename(source / "FDUSDUSDC-aggTrades-2024-01-01.zip")
    day_three = archive(
        source,
        [["3", "1", "1", "3", "3", "1704240000000", "false"]],
    )
    day_three = day_three.rename(source / "FDUSDUSDC-aggTrades-2024-01-03.zip")
    entries = [
        (
            f"data/spot/daily/aggTrades/FDUSDUSDC/{path.name}",
            f"https://data.binance.vision/{path.name}",
        )
        for path in (day_one, day_three)
    ]
    by_name = {item.name: item for item in (day_one, day_three)}

    monkeypatch.setattr(
        "crypto_strategy_lab.microstructure.data.list_daily_archives",
        lambda _symbol, _kind: entries,
    )

    def copy_archive(url, destination):
        destination.write_bytes(by_name[url.rsplit("/", 1)[-1]].read_bytes())
        return destination

    monkeypatch.setattr("crypto_strategy_lab.microstructure.data.download_archive", copy_archive)
    result = download_history_range(
        "FDUSDUSDC",
        tmp_path / "downloaded",
        start=date(2024, 1, 1),
        end=date(2024, 1, 3),
        max_workers=2,
    )

    assert result.missing_dates == (date(2024, 1, 2),)
    assert result.missing_date_ranges == ((date(2024, 1, 2), date(2024, 1, 2)),)
    assert result.cross_archive_gaps == ((1, 3),)
    assert result.invalidity_reasons == ("missing_requested_dates", "cross_archive_id_gaps")
    assert result.integrity_status == "INVALID"
    assert result.total_records == 2

    valid_day = slice_history_manifest(
        result,
        start=date(2024, 1, 1),
        end=date(2024, 1, 1),
    )
    assert valid_day.integrity_status == "VALID"
    assert valid_day.invalidity_reasons == ()
    assert len(valid_day.archives) == 1
    verify_history_manifest(valid_day)


def test_history_range_is_reproducible_for_same_archives(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    timestamps = (
        int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000),
        int(datetime(2024, 1, 2, tzinfo=UTC).timestamp() * 1000),
    )
    paths = []
    for offset, stamp in enumerate(timestamps, start=1):
        path = archive(
            source,
            [
                [
                    str(offset),
                    "1",
                    "1",
                    str(offset),
                    str(offset),
                    str(stamp),
                    "false",
                ]
            ],
        ).rename(source / f"FDUSDUSDC-aggTrades-2024-01-0{offset}.zip")
        paths.append(path)
    entries = [
        (f"prefix/{path.name}", f"https://data.binance.vision/{path.name}") for path in paths
    ]
    by_name = {item.name: item for item in paths}
    monkeypatch.setattr(
        "crypto_strategy_lab.microstructure.data.list_daily_archives",
        lambda _symbol, _kind: entries,
    )

    def copy_archive(url, destination):
        destination.write_bytes(by_name[url.rsplit("/", 1)[-1]].read_bytes())
        return destination

    monkeypatch.setattr("crypto_strategy_lab.microstructure.data.download_archive", copy_archive)
    kwargs = {
        "start": date(2024, 1, 1),
        "end": date(2024, 1, 2),
        "max_workers": 2,
    }
    first = download_history_range("FDUSDUSDC", tmp_path / "a", **kwargs)
    second = download_history_range("FDUSDUSDC", tmp_path / "b", **kwargs)

    assert first.dataset_hash == second.dataset_hash
    assert first.integrity_status == second.integrity_status == "VALID"
    assert first.archives[0].timestamp_unit == "milliseconds"
    verify_history_manifest(first)
