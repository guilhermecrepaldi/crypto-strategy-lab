from __future__ import annotations

import csv
import gzip
import io
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import collect_tardis_l2_samples as collector


def archive(rows: list[dict[str, str]], schema: list[str] | None = None) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=schema or collector.EXPECTED_SCHEMA)
    writer.writeheader()
    writer.writerows(rows)
    return gzip.compress(output.getvalue().encode())


def row(day: str = "2025-01-01") -> dict[str, str]:
    stamp = f"{day}T00:00:00.000Z"
    return {
        "exchange": "binance",
        "symbol": "USDCUSDT",
        "timestamp": stamp,
        "local_timestamp": stamp,
        "is_snapshot": "false",
        "side": "bid",
        "price": "1.0",
        "amount": "2.0",
    }


def test_candidate_dates_are_exact_first_of_months() -> None:
    days = collector.candidate_dates()
    assert len(days) == 21
    assert days[0] == date(2025, 1, 1)
    assert days[-1] == date(2026, 9, 1)


def test_sealed_week_and_nonmonthly_dates_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ONLY_AUTHORIZED"):
        collector.collect(dates=[date(2026, 1, 8)], manifest_path=tmp_path / "m.json")


def test_capture_precision_and_regression_are_not_sorted_away(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv.gz"
    first = row()
    first.update(timestamp="1735689600000002", local_timestamp="1735689600000002")
    second = {**first, "local_timestamp": "1735689600000001"}
    path.write_bytes(archive([first, second]))
    result = collector.validate_gzip(path, date(2025, 1, 1))
    assert result["capture_time_regressions"] == 1
    assert result["last_timestamp"] == "1735689600000001"
    assert collector._timestamp("1735689600000002").microsecond == 2


def test_schema_and_scope_validation(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv.gz"
    path.write_bytes(archive([row()]))
    result = collector.validate_gzip(path, date(2025, 1, 1))
    assert result["rows"] == 1
    assert result["gzip_integrity"] == "PASS"
    malformed = io.StringIO(newline="")
    malformed.write(",".join(collector.EXPECTED_SCHEMA[:-1]) + "\n")
    malformed.write(",".join(row().values()) + "\n")
    path.write_bytes(gzip.compress(malformed.getvalue().encode()))
    with pytest.raises(ValueError, match="schema"):
        collector.validate_gzip(path, date(2025, 1, 1))


def test_corrupt_gzip_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.gz"
    path.write_bytes(b"not gzip")
    with pytest.raises((OSError, gzip.BadGzipFile)):
        collector.validate_gzip(path, date(2025, 1, 1))


def test_orphan_original_is_fail_closed_and_immutable(tmp_path: Path) -> None:
    root = tmp_path / "l2"
    original = root / "2025-01-01" / "incremental_book_L2.csv.gz"
    original.parent.mkdir(parents=True)
    payload = b"existing"
    original.write_bytes(payload)
    result = collector.collect(
        dates=[date(2025, 1, 1)],
        root=root,
        manifest_path=tmp_path / "manifest.json",
        download=False,
    )
    assert result["dates"][0]["status"] == "INVALID"
    assert original.read_bytes() == payload


def test_unavailable_is_recorded_without_auth(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Missing:
        def __call__(self, request: object, timeout: float) -> object:
            raise collector.HTTPError(str(request), 404, "missing", {}, None)

    monkeypatch.setattr(collector, "urlopen", Missing())
    result = collector.collect(
        dates=[date(2025, 1, 1)],
        root=tmp_path / "l2",
        manifest_path=tmp_path / "manifest.json",
        concurrency=1,
    )
    assert result["dates"][0]["status"] == "UNAVAILABLE"
    assert result["dates"][0]["http_status"] == 404
    assert (
        json.loads((tmp_path / "manifest.json").read_text())["dates"][0]["status"] == "UNAVAILABLE"
    )
