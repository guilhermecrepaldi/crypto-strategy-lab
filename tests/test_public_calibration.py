from decimal import Decimal

import pytest

from crypto_strategy_lab.microstructure.public_calibration import (
    BookGap,
    LocalDepth,
    WeightedBookSamples,
    quantiles,
    validate_bookticker_sequence,
    validate_public_trade,
    weighted_quantiles,
)
from crypto_strategy_lab.microstructure.public_market import (
    PublicMarketClient,
    PublicMarketError,
    parse_book,
    parse_trade,
)


def snapshot(update_id=100):
    return {"lastUpdateId": update_id, "bids": [["0.9999", "1000"]], "asks": [["1", "2000"]]}


def delta(first, last, bids=None):
    return {"s": "USDCUSDT", "e": "depthUpdate", "U": first, "u": last, "b": bids or [], "a": []}


def test_book_bridge_duplicates_gap_resnapshot():
    book = LocalDepth()
    book.snapshot(snapshot())
    assert not book.valid
    assert not book.apply(delta(99, 100))
    assert book.apply(delta(100, 102, [["0.9999", "500"]]))
    assert book.valid and book.bids[Decimal("0.9999")] == 500
    assert not book.apply(delta(100, 102))
    with pytest.raises(BookGap, match="GAP"):
        book.apply(delta(104, 105))
    assert not book.valid and book.update_id is None
    book.snapshot(snapshot(110))
    assert book.apply(delta(110, 111)) and book.valid


def test_absolute_quantities_and_removal():
    book = LocalDepth()
    book.snapshot(snapshot())
    book.apply(delta(101, 101, [["0.9999", "400"], ["0.9998", "99"]]))
    book.apply(delta(102, 102, [["0.9999", "0"]]))
    assert book.bids == {Decimal("0.9998"): Decimal(99)}


def test_book_ticker_local_receipt_no_exchange_time():
    quote = parse_book(
        {"s": "USDCUSDT", "u": 123, "b": "0.9999", "a": "1", "B": "100", "A": "200"},
        received_us=123456,
    )
    assert quote.received_us == 123456


def test_aggressor_required_boolean():
    payload = {"a": 1, "T": 123456, "f": 1, "l": 3, "p": "1", "q": "2", "m": True}
    assert parse_trade(payload).buyer_is_maker is True
    payload["m"] = "true"
    with pytest.raises(PublicMarketError):
        parse_trade(payload)


def test_current_notional_does_not_require_legacy_filter(monkeypatch):
    client = PublicMarketClient()
    monkeypatch.setattr(client, "server_time", lambda: 123456)
    monkeypatch.setattr(
        client,
        "_request_json",
        lambda *args: {
            "symbols": [
                {
                    "symbol": "USDCUSDT",
                    "status": "TRADING",
                    "filters": [
                        {"filterType": "PRICE_FILTER", "tickSize": "0.00001"},
                        {"filterType": "LOT_SIZE", "stepSize": "1"},
                        {"filterType": "NOTIONAL", "minNotional": "5"},
                    ],
                }
            ]
        },
    )
    assert client.metadata().min_notional == 5


@pytest.mark.parametrize("path", ["/api/v3/order", "/api/v3/account", "/api/v3/myTrades"])
def test_private_and_order_paths_fail_closed(path):
    with pytest.raises(PublicMarketError, match="allowlisted"):
        PublicMarketClient()._request_json(path)


def test_quantile_nearest_rank_and_empty():
    assert quantiles([])["p50"] is None
    assert quantiles(list(range(1, 101)))["p99"] == "99"


def test_weighted_quantile_nearest_rank_is_deterministic():
    assert weighted_quantiles(["1", "2", "3"], [1, 1, 8])["p50"] == "3"
    assert weighted_quantiles([], [])["n"] == 0


def test_public_trade_identity_and_regression_validation():
    row = {"e": "trade", "s": "USDCUSDT", "t": 10, "T": 123456, "p": "1.0", "q": "2.0", "m": True}
    assert validate_public_trade(row) == 10
    with pytest.raises(ValueError, match="REGRESSION"):
        validate_public_trade({**row, "t": 9}, last_trade_id=10)
    with pytest.raises(ValueError, match="SYMBOL"):
        validate_public_trade({**row, "s": "OTHER"})


def test_bookticker_regression_is_recorded_not_silently_reordered():
    assert validate_bookticker_sequence(10, 11) == (10, True)
    assert validate_bookticker_sequence(12, 11) == (12, False)


def test_joint_sample_weights_are_nonoverlapping_and_reset_on_gap():
    samples = WeightedBookSamples()
    samples.observe(100, {"queue": "20"})
    samples.observe(300, {"queue": "40"})
    samples.close(400)
    samples.observe(900, {"queue": "80"})
    samples.close(1000)
    assert [row["duration_ns"] for row in samples.rows] == [200, 100, 100]
    assert sum(row["duration_ns"] for row in samples.rows) == 400
