import gzip
import json
import zipfile
from concurrent.futures import ProcessPoolExecutor
from urllib.parse import urlencode

import pytest

from crypto_strategy_lab.microstructure.tardis_l2 import (
    CSV_SCHEMA,
    bind_csv_reconstructed_native,
    iter_native_events,
    iter_reconstructed_native_rows,
)
from scripts.validate_tardis_l2_samples import (
    day_start_us,
    file_sha256,
    raw_lines,
    reconcile_trades,
    trade_timestamp_matches,
    validate_day,
    validate_slice_metadata,
    validate_work,
)


def test_process_and_serial_workers_preserve_result_and_order():
    tasks = [
        ({"date": day, "status": "UNAVAILABLE"}, {}, False, False)
        for day in ("2025-01-01", "2025-02-01")
    ]
    expected = [validate_work(task) for task in tasks]
    with ProcessPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(validate_work, tasks)) == expected


def metadata():
    params = {
        "from": "2025-01-01",
        "offset": 0,
        "sliceSize": 10,
        "compression": "gzip",
        "filters": json.dumps(
            [
                {"channel": channel, "symbols": ["usdcusdt"]}
                for channel in ("depth", "depthSnapshot", "trade")
            ]
        ),
    }
    return {
        "offset": 0,
        "http_status": 200,
        "status": "AVAILABLE",
        "response_headers": {"x-slice-size": "10", "x-name": "binance/2025/01/01/00/00"},
        "source_url": "https://api.tardis.dev/v1/data-feeds/binance?" + urlencode(params),
    }


def test_exact_slice_provenance():
    validate_slice_metadata("2025-01-01", metadata())
    wrong = metadata()
    wrong["response_headers"]["x-slice-size"] = "1"
    with pytest.raises(ValueError, match="ten minutes"):
        validate_slice_metadata("2025-01-01", wrong)
    wrong = metadata()
    wrong["source_url"] = wrong["source_url"].replace("2025-01-01", "2025-01-02")
    with pytest.raises(ValueError, match="from"):
        validate_slice_metadata("2025-01-01", wrong)


def test_scope_rejects_week_two():
    with pytest.raises(ValueError, match="scope"):
        day_start_us("2026-01-08")


def test_trade_timestamp_native_precision():
    assert trade_timestamp_matches(1735689600006766, 1735689600006)
    assert not trade_timestamp_matches(1735689600006766, 1735689600007)
    assert trade_timestamp_matches(1767225600037599, 1767225600037599)
    assert not trade_timestamp_matches(1767225600037599, 1767225600037598)


def test_raw_capture_slice_boundary_fails(tmp_path):
    entry = metadata()
    entry["local_path"] = "data/l2/tardis/binance/usdcusdt/2025-01-01/raw/0000.ndjson.gz"
    path = tmp_path / entry["local_path"]
    path.parent.mkdir(parents=True)
    with gzip.open(path, "wt") as stream:
        stream.write("2025-01-01T00:10:00Z {}\n")
    with pytest.raises(ValueError, match="outside"):
        list(raw_lines(tmp_path, "2025-01-01", [entry]))


def native(data, second):
    return f"2025-01-01T00:00:{second:02d}Z " + json.dumps(
        {"stream": "usdcusdt@depth", "data": data}
    )


def test_snapshot_binding_applies_buffer_once_and_skips_stale():
    lines = [
        native(dict(e="depthUpdate", E=1735689601000, U=9, u=11, b=[["1", "3"]], a=[]), 1),
        native(dict(lastUpdateId=10, bids=[["1", "2"]], asks=[["2", "2"]]), 2),
        native(dict(e="depthUpdate", E=1735689603000, U=10, u=11, b=[["1", "99"]], a=[]), 3),
        native(dict(e="depthUpdate", E=1735689604000, U=12, u=12, b=[["1", "4"]], a=[]), 4),
    ]
    rows = list(iter_reconstructed_native_rows(lines))
    assert len(rows) == 3
    assert rows[0]["amount"] == "3"
    assert rows[0]["timestamp"] == rows[0]["local_timestamp"] == "1735689602000000"
    assert rows[2]["amount"] == "4"
    assert bind_csv_reconstructed_native(rows, lines)["normalized_binding_gate"] == "PASS"
    rows[0]["amount"] = "2"
    assert bind_csv_reconstructed_native(rows, lines)["normalized_binding_gate"] == "FAIL"


def test_snapshot_binding_refuses_native_gap():
    lines = [
        native(dict(lastUpdateId=10, bids=[["1", "2"]], asks=[["2", "2"]]), 1),
        native(dict(e="depthUpdate", E=1735689602000, U=12, u=12, b=[], a=[]), 2),
    ]
    result = bind_csv_reconstructed_native([], lines)
    assert result["normalized_binding_gate"] == "FAIL"
    assert "gap" in result["errors"][0]


def trade_fixture(tmp_path):
    relative = "data/raw/binance-microstructure/USDCUSDT/trades/USDCUSDT-trades-2025-01-01.zip"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    contents = "".join(
        f"{100 + i},1,2,2,{1735689600000000 + i * 1000},true,true\n" for i in range(3)
    )
    with zipfile.ZipFile(path, "w") as zipped:
        zipped.writestr("USDCUSDT-trades-2025-01-01.csv", contents)
    archive = dict(
        local_path=relative,
        utc_date="2025-01-01",
        integrity_status="VALID",
        symbol="USDCUSDT",
        size_bytes=path.stat().st_size,
        sha256=file_sha256(path),
        record_count=3,
        first_trade_id=100,
        last_trade_id=102,
    )
    lines = [
        native(dict(e="trade", t=100 + i, T=1735689600000 + i, p="1", q="2", m=True), i + 1)
        for i in range(3)
    ]
    return archive, lines


def test_trade_reconciliation_distinguishes_missing_interior_and_prefix(tmp_path):
    archive, lines = trade_fixture(tmp_path)
    assert reconcile_trades(tmp_path, "2025-01-01", archive, lines)["trade_binding_gate"] == "PASS"
    interior = reconcile_trades(tmp_path, "2025-01-01", archive, [lines[0], lines[2]])
    assert interior["trade_binding_gate"] == "FAIL"
    assert interior["counts"]["missing_interior"] == 1
    prefix = reconcile_trades(tmp_path, "2025-01-01", archive, lines[1:])
    assert prefix["trade_binding_gate"] == "UNKNOWN"
    assert prefix["counts"]["missing_prefix"] == 1


def test_trade_duplicate_and_mutated_source_fail(tmp_path):
    archive, lines = trade_fixture(tmp_path)
    duplicate = reconcile_trades(tmp_path, "2025-01-01", archive, [*lines, lines[-1]])
    assert duplicate["trade_binding_gate"] == "FAIL"
    assert duplicate["counts"]["native_duplicate_ids"] == 1
    archive["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        reconcile_trades(tmp_path, "2025-01-01", archive, lines)


def test_native_event_projection_preserves_trade_capture_and_coverage():
    trade = native(dict(e="trade", s="USDCUSDT", T=1735689600001), 1).replace("@depth", "@trade")
    buffered = native(dict(e="depthUpdate", E=1735689602000, U=10, u=11, b=[["1", "3"]], a=[]), 2)
    snapshot = native(dict(lastUpdateId=10, bids=[["1", "2"], [".9", "1"]], asks=[["2", "2"]]), 3)
    deleted = native(dict(e="depthUpdate", E=1735689604000, U=12, u=12, b=[[".9", "0"]], a=[]), 4)
    events = list(iter_native_events([trade, buffered, snapshot, deleted]))
    assert [event["capture_order"] for event in events] == [1, 3, 4]
    assert events[0]["kind"] == "TRADE"
    assert events[1]["sequence_validated"]
    assert events[1]["native_update_id"] == 11
    assert str(events[1]["bids"][0][1]) == "3"
    assert events[2]["known_bid_floor"] == events[1]["known_bid_floor"]
    assert len(events[1]["bids"]) == 2
    assert len(events[2]["bids"]) == 1


def test_input_binding_ignores_download_retry_metadata(tmp_path, monkeypatch):
    import scripts.validate_tardis_l2_samples as module

    monkeypatch.setattr(module, "validator_identity", lambda root: {"validator": "fixed"})
    relative = "data/l2/tardis/binance/usdcusdt/2025-01-01/incremental_book_L2.csv.gz"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    with gzip.open(path, "wt") as stream:
        stream.write(",".join(CSV_SCHEMA) + "\n")
        for side, price in (("bid", "1"), ("ask", "2")):
            stream.write(
                f"binance,USDCUSDT,1735689600000001,1735689600000001,true,{side},{price},2\n"
            )
    entry = dict(
        date="2025-01-01",
        status="AVAILABLE",
        http_status=200,
        source_url="https://datasets.tardis.dev/v1/binance/incremental_book_L2/2025/01/01/USDCUSDT.csv.gz",
        local_path=relative,
        bytes=path.stat().st_size,
        sha256=file_sha256(path),
        rows=2,
        first_timestamp="1735689600000001",
        last_timestamp="1735689600000001",
    )
    first = validate_day(entry, {}, root=tmp_path, csv_only=True)
    assert first["input_sha256"] == first["cache_key"]
    entry.update(status="ORIGINAL_PRESENT", download_timestamp="new retry")
    second = validate_day(entry, {}, root=tmp_path, csv_only=True, use_cache=False)
    assert second["input_sha256"] == first["input_sha256"]
