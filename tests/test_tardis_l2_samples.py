from __future__ import annotations

import csv
import gzip
import io
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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


def test_symbol_parameterization_preserves_default_and_accepts_fdusd(tmp_path: Path) -> None:
    assert collector.source_url(date(2025, 1, 1)).endswith("/USDCUSDT.csv.gz")
    assert collector.source_url(date(2025, 1, 1), "fdusdusdt").endswith(
        "/FDUSDUSDT.csv.gz"
    )
    payload = row()
    payload["symbol"] = "FDUSDUSDT"
    path = tmp_path / "fdusd.csv.gz"
    path.write_bytes(archive([payload]))
    assert collector.validate_gzip(path, date(2025, 1, 1), "FDUSDUSDT")["rows"] == 1


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


def test_raw_url_has_exact_slice_and_filters() -> None:
    query = parse_qs(urlparse(collector._raw_url(date(2025, 1, 1), 120)).query)
    assert query["offset"] == ["120"]
    assert query["sliceSize"] == ["10"]
    assert query["compression"] == ["gzip"]
    assert all(channel in query["filters"][0] for channel in collector.RAW_CHANNELS)


def test_raw_url_is_symbol_parameterized() -> None:
    query = parse_qs(
        urlparse(collector._raw_url(date(2025, 1, 1), 0, "FDUSDUSDT")).query
    )
    assert "fdusdusdt" in query["filters"][0]


def test_fdusd_raw_scope_is_exact_first_three_hours(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="EXACT_00_TO_03"):
        collector.collect_raw(
            dates=[date(2025, 1, 1)],
            root=tmp_path,
            manifest_path=tmp_path / "m.json",
            symbol="FDUSDUSDT",
            offsets=[180],
        )
    with pytest.raises(ValueError, match="RAW_SYMBOL_OUTSIDE"):
        collector.collect_raw(
            dates=[date(2025, 1, 1)],
            root=tmp_path,
            manifest_path=tmp_path / "m.json",
            symbol="BTCUSDT",
            offsets=range(0, 180, 10),
        )


def test_raw_sidecar_gzip_and_immutability(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = gzip.compress(b'{"timestamp":"2025-01-01T00:00:00Z"}\n')

    class Response:
        status = 200

        def __init__(self) -> None:
            self.headers = {"Content-Length": str(len(payload)), "X-Slice-Size": "10"}

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            return payload

    monkeypatch.setattr(collector, "urlopen", lambda request, timeout: Response())
    result = collector._raw_slice(date(2025, 1, 1), 0, tmp_path / "raw", 1.0)
    path = Path(result["local_path"])
    assert result["status"] == "AVAILABLE"
    assert result["gzip_integrity"] == "PASS"
    before = path.read_bytes()
    second = collector._raw_slice(
        date(2025, 1, 1),
        0,
        tmp_path / "raw",
        1.0,
        result,
    )
    assert second["status"] == "ORIGINAL_PRESENT"
    assert path.read_bytes() == before


def test_raw_orphan_revalidation_preserves_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "raw"
    original = root / "2025-01-01" / "raw" / "0000.ndjson.gz"
    original.parent.mkdir(parents=True)
    original.write_bytes(gzip.compress(b"local\n"))
    remote = gzip.compress(b"different\n")

    class Response:
        status = 200

        def __init__(self) -> None:
            self.headers = {"Content-Length": str(len(remote)), "X-Slice-Size": "10"}

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            return remote

    monkeypatch.setattr(collector, "urlopen", lambda request, timeout: Response())
    result = collector._raw_slice(date(2025, 1, 1), 0, root, 1.0, revalidate_orphans=True)
    assert result["status"] == "INVALID"
    assert Path(result["verification_path"]).read_bytes() == remote
    assert original.read_bytes() != remote


def test_raw_existing_requires_sidecar_provenance(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    original = root / "2025-01-01" / "raw" / "0000.ndjson.gz"
    original.parent.mkdir(parents=True)
    original.write_bytes(gzip.compress(b"local\n"))
    result = collector._raw_slice(
        date(2025, 1, 1),
        0,
        root,
        1.0,
        {
            "status": "AVAILABLE",
            "sha256": collector.hashlib.sha256(original.read_bytes()).hexdigest(),
        },
    )
    assert result["status"] == "INVALID"
    orphan = collector._raw_slice(date(2025, 1, 1), 0, tmp_path / "raw", 1.0)
    assert orphan["status"] == "INVALID"
    changed = collector._raw_slice(
        date(2025, 1, 1), 0, tmp_path / "raw", 1.0, {**result, "sha256": "wrong"}
    )
    assert changed["status"] == "INVALID"


def test_raw_subset_preserves_other_dates_and_checkpoints_each_slice(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"dates": [{"date": "2025-02-01", "rows": 123}]}))
    checkpoints = []
    original_write = collector._write_raw_manifest

    def checkpoint(path, payload, entries):
        original_write(path, payload, entries)
        checkpoints.append(json.loads(path.read_text()))

    monkeypatch.setattr(collector, "_write_raw_manifest", checkpoint)
    monkeypatch.setattr(
        collector,
        "_raw_slice",
        lambda day, offset, *args: {
            "offset": offset,
            "status": "UNAVAILABLE",
            "http_status": 401,
        },
    )
    collector.collect_raw(dates=[date(2025, 1, 1)], manifest_path=manifest, root=tmp_path)
    assert len(checkpoints) == 145
    assert len(checkpoints[0]["dates"][0]["raw_slices"]) == 1
    assert checkpoints[-1]["dates"][1] == {"date": "2025-02-01", "rows": 123}


def test_raw_orphan_recovered_with_http_evidence_then_sidecar_only_reused(tmp_path, monkeypatch):
    root = tmp_path / "raw"
    original = root / "2025-01-01" / "raw" / "0000.ndjson.gz"
    original.parent.mkdir(parents=True)
    payload = gzip.compress(b"original\n")
    original.write_bytes(payload)

    class Response:
        status = 200

        def __init__(self):
            self.headers = {"X-Slice-Size": "10", "Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return payload

    monkeypatch.setattr(collector, "urlopen", lambda *a, **k: Response())
    recovered = collector._raw_slice(date(2025, 1, 1), 0, root, 1, revalidate_orphans=True)
    assert recovered["status"] == "AVAILABLE"
    assert recovered["download_timestamp"] is None
    assert recovered["http_status"] == 200
    assert recovered["gzip_integrity"] == "PASS"
    monkeypatch.setattr(collector, "urlopen", lambda *a, **k: pytest.fail("unexpected GET"))
    reused = collector._raw_slice(date(2025, 1, 1), 0, root, 1)
    assert reused["status"] == "ORIGINAL_PRESENT"
    assert original.read_bytes() == payload


def test_manifest_permission_retry_and_executor_failure_not_masked(tmp_path, monkeypatch):
    calls = []

    def transient(*args):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError("locked")

    monkeypatch.setattr(collector, "_write_raw_manifest", transient)
    monkeypatch.setattr(collector.time, "sleep", lambda seconds: None)
    collector._persist_raw_manifest(tmp_path / "m.json", {}, {})
    assert len(calls) == 2

    def failure(*args):
        raise PermissionError("persistent writer failure")

    monkeypatch.setattr(collector, "_persist_raw_manifest", failure)
    monkeypatch.setattr(
        collector,
        "_raw_slice",
        lambda day, offset, *args: {
            "offset": offset,
            "status": "UNAVAILABLE",
        },
    )
    with pytest.raises(PermissionError, match="persistent writer failure"):
        collector.collect_raw(
            dates=[date(2025, 1, 1)],
            root=tmp_path,
            manifest_path=tmp_path / "m.json",
            concurrency=1,
        )
