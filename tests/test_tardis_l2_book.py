import json

import pytest

from crypto_strategy_lab.microstructure.tardis_l2 import (
    bind_csv_native_deltas,
    iter_native_delta_rows,
    validate_csv_rows,
    validate_raw_lines,
)


def row(local=1, snapshot=False, side="bid", price="1", amount="2", exchange=None):
    return dict(
        exchange="binance",
        symbol="USDCUSDT",
        timestamp=str(exchange or local),
        local_timestamp=str(local),
        is_snapshot=str(snapshot).lower(),
        side=side,
        price=price,
        amount=amount,
    )


def snapshot():
    return [row(snapshot=True), row(snapshot=True, side="ask", price="2")]


def native(data, local=1):
    return f"2026-01-01T00:00:{local:02d}Z " + json.dumps(
        {"stream": "usdcusdt@depth", "data": data}
    )


def snap(last=10, local=1):
    return native(dict(lastUpdateId=last, bids=[["1", "2"]], asks=[["2", "2"]]), local)


def delta(first=11, final=11, local=2, bids=None, asks=None):
    return native(
        dict(e="depthUpdate", E=local * 1000, U=first, u=final, b=bids or [], a=asks or []), local
    )


def test_csv_atomic_batch_prevents_transient_cross():
    result = validate_csv_rows(
        [
            *snapshot(),
            row(2, price="2.5"),
            row(2, side="ask", price="2", amount="0"),
            row(2, side="ask", price="3"),
        ]
    )
    assert result["observable_invariants_pass"]
    assert result["counts"]["crossed_batches"] == 0
    assert result["final_book"]["asks"] == [["3", "2"]]
    assert result["sequence_gate"] == "UNKNOWN"
    assert result["L2_DAY_VALID"] is None


@pytest.mark.parametrize("amount", ["-1", "NaN", "Infinity"])
def test_csv_rejects_invalid_quantity(amount):
    result = validate_csv_rows([*snapshot(), row(2, amount=amount)])
    assert result["L2_DAY_VALID"] is False
    assert result["errors"]


def test_csv_preserves_capture_order_and_reports_time_regressions():
    result = validate_csv_rows([*snapshot(), row(3, amount="3"), row(2, amount="4")])
    assert result["counts"]["local_time_regressions"] == 1
    assert result["final_book"]["bids"] == [["1", "4"]]
    assert result["L2_DAY_VALID"] is False


def test_csv_prefix_skipped_and_resnapshot_clears_old_levels():
    result = validate_csv_rows(
        [
            row(),
            row(2, True),
            row(2, True, "ask", "2"),
            row(3, price="0.5"),
            row(4, True),
            row(4, True, "ask", "3"),
        ]
    )
    assert result["counts"]["prefix_rows_skipped"] == 1
    assert result["resnapshots"] == 1
    assert result["final_book"] == {"bids": [["1", "2"]], "asks": [["3", "2"]]}


def test_csv_cross_is_reported_and_never_repaired():
    result = validate_csv_rows([*snapshot(), row(2, price="3")])
    assert result["counts"]["crossed_batches"] == 1
    assert result["L2_DAY_VALID"] is False
    assert result["final_book"]["bids"][0] == ["3", "2"]


def test_raw_buffered_bridge_and_overlap_absolute_updates():
    result = validate_raw_lines(
        [
            delta(9, 11, 1, bids=[["1", "3"]]),
            snap(10, 2),
            delta(10, 11, 3, bids=[["1", "99"]]),
            delta(11, 12, 4, bids=[["1", "4"]]),
        ]
    )
    assert result["sequence_gate"] == "PASS"
    assert result["counts"]["stale_updates_ignored"] == 1
    assert result["last_update_id"] == 12
    assert result["final_book"]["bids"] == [["1", "4"]]
    assert result["L2_DAY_VALID"] is None  # coverage and CSV binding still unknown


def test_raw_gap_stays_day_invalid_after_resnapshot():
    result = validate_raw_lines([snap(), delta(), delta(13, 13, 3), snap(13, 4), delta(14, 14, 5)])
    assert result["counts"]["sequence_gaps"] == 1
    assert result["current_book_bridged"]
    assert result["L2_DAY_VALID"] is False


def test_raw_disconnect_persists_failure_and_clears_book():
    result = validate_raw_lines([snap(), delta(), "\n", snap(20, 3), delta(21, 21, 4)])
    assert result["counts"]["disconnects"] == 1
    assert result["sequence_gate"] == "FAIL"
    assert result["current_book_bridged"]


def test_raw_atomic_deletes_and_cross_check():
    result = validate_raw_lines([snap(), delta(bids=[["2.5", "1"]], asks=[["2", "0"], ["3", "1"]])])
    assert result["counts"]["crossed_states"] == 0
    assert result["final_book"]["asks"] == [["3", "1"]]


def test_raw_snapshot_without_bridge_is_unknown():
    result = validate_raw_lines([snap()])
    assert result["sequence_gate"] == "UNKNOWN"
    assert not result["current_book_bridged"]


def test_raw_invalid_quantity_fails_closed():
    result = validate_raw_lines([snap(), delta(bids=[["1", "-1"]])])
    assert result["L2_DAY_VALID"] is False
    assert not result["current_book_bridged"]


def test_raw_capture_order_not_sorted():
    result = validate_raw_lines([snap(local=2), delta(local=1)])
    assert result["counts"]["local_time_regressions"] == 1
    assert result["L2_DAY_VALID"] is False


def test_raw_trade_channel_shape_validated_without_altering_depth():
    trade = native(
        dict(e="trade", s="USDCUSDT", t=123, T=2000, E=2000, p="1", q="2", m=True), 2
    ).replace("@depth", "@trade")
    result = validate_raw_lines([snap(), trade, delta(local=3)])
    assert result["sequence_gate"] == "PASS"
    assert result["counts"]["trades"] == 1
    bad = trade.replace('"q": "2"', '"q": "-2"')
    assert validate_raw_lines([snap(), bad, delta(local=3)])["L2_DAY_VALID"] is False


def test_delta_binding_equivalent_decimal_format_and_level_order():
    raw = [snap(), delta(bids=[["1.00", "2.000"]], asks=[["2", "3"]])]
    rows = list(iter_native_delta_rows(raw))
    rows[0]["price"], rows[0]["amount"] = "1", "2"
    result = bind_csv_native_deltas(list(reversed(rows)), raw)
    assert result["delta_binding_gate"] == "PASS"
    assert result["csv_delta_sha256"] == result["native_delta_sha256"]
    assert result["normalized_binding_gate"] == "UNKNOWN"


@pytest.mark.parametrize("change", ["extra", "missing", "modified", "timestamp"])
def test_delta_binding_detects_extra_missing_or_modified_rows(change):
    raw = [delta(bids=[["1", "2"]], asks=[["2", "3"]])]
    rows = list(iter_native_delta_rows(raw))
    if change == "extra":
        rows.append(dict(rows[0]))
    elif change == "missing":
        rows.pop()
    elif change == "modified":
        rows[0]["amount"] = "2.1"
    else:
        rows[0]["local_timestamp"] = str(int(rows[0]["local_timestamp"]) + 1)
    assert bind_csv_native_deltas(rows, raw)["delta_binding_gate"] == "FAIL"


def test_binding_floors_native_nanoseconds_and_does_not_prove_snapshots():
    raw = [delta().replace("00:00:02Z", "00:00:02.123456789Z")]
    assert bind_csv_native_deltas([], raw)["delta_binding_gate"] == "UNKNOWN"
    raw = [delta(bids=[["1", "0"]]).replace("00:00:02Z", "00:00:02.123456789Z")]
    rows = list(iter_native_delta_rows(raw))
    assert rows[0]["local_timestamp"] == "1767225602123456"
    assert bind_csv_native_deltas(rows, raw)["snapshot_binding_gate"] == "UNKNOWN"


@pytest.mark.parametrize(
    "exchange,expected",
    [
        (1735689600037, 1735689600037000),
        (1767225600037599, 1767225600037599),
    ],
)
def test_native_millisecond_and_microsecond_subscriptions(exchange, expected):
    line = native(dict(e="depthUpdate", E=exchange, U=11, u=11, b=[["1", "2"]], a=[]), 2)
    projected = list(iter_native_delta_rows([line]))
    assert projected[0]["timestamp"] == str(expected)
    result = validate_raw_lines([snap(), line])
    assert result["first_timestamp"] == expected
    assert result["last_timestamp"] == expected
    assert bind_csv_native_deltas(projected, [line])["delta_binding_gate"] == "PASS"


def test_exchange_regression_checked_after_unit_normalization():
    first = native(dict(e="depthUpdate", E=1767225600000, U=11, u=11, b=[], a=[]), 2)
    second = native(dict(e="depthUpdate", E=1767225599999999, U=12, u=12, b=[], a=[]), 3)
    result = validate_raw_lines([snap(), first, second])
    assert result["counts"]["exchange_time_regressions"] == 1
