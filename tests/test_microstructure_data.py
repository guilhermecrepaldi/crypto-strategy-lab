from datetime import UTC
from hashlib import sha256
from zipfile import ZipFile

import pytest

from crypto_strategy_lab.microstructure.data import (
    MicrostructureIntegrityError,
    download_archive,
    parse_archive,
    validate_events,
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
    assert events[0].timestamp.tzinfo is UTC
    assert str(events[0].price) == "10.01"
    assert events[1].timestamp.microsecond == 0


def test_parse_agg_trades_us(tmp_path):
    path = archive(
        tmp_path,
        [
            ["agg", "price", "qty", "first", "last", "time", "maker"],
            ["9", "1.2", "4", "8", "10", "1740000000000000", "false"],
        ],
    )
    event = parse_archive(path, "aggTrades")[0]
    assert event.trade_id == 9 and event.sequence == 10


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
