"""Read-only Binance public market data for the USDCUSDT shadow operator.

This module deliberately has no account, order, or configurable-endpoint API.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

BASE_URL = "https://data-api.binance.vision"
SYMBOL = "USDCUSDT"
M034_SYMBOLS = (
    "USDCUSDT",
    "FDUSDUSDT",
    "FDUSDUSDC",
    "USD1USDT",
    "USD1USDC",
    "TUSDUSDT",
    "USDPUSDT",
)
STREAM_URL = (
    "wss://data-stream.binance.vision/stream?"
    "streams=usdcusdt@aggTrade/usdcusdt@bookTicker&timeUnit=MICROSECOND"
)
_HEADERS = {"X-MBX-TIME-UNIT": "MICROSECOND", "Accept": "application/json"}


class PublicMarketError(ValueError):
    """Malformed or disallowed public market data."""


def _strict_int(value: Any, name: str, *, positive: bool = False) -> int:
    if type(value) is not int or (positive and value <= 0):
        raise PublicMarketError(f"{name} must be a {'positive ' if positive else ''}integer")
    return value


def _positive_decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, bool):
        raise PublicMarketError(f"{name} must be a finite positive decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise PublicMarketError(f"{name} must be a finite positive decimal") from None
    if not result.is_finite() or result <= 0:
        raise PublicMarketError(f"{name} must be a finite positive decimal")
    return result


def _symbol(value: str) -> str:
    if type(value) is not str or value.upper() not in M034_SYMBOLS:
        raise PublicMarketError("symbol is not allowlisted")
    return value.upper()


@dataclass(frozen=True)
class MarketTrade:
    aggregate_id: int
    timestamp_us: int
    price: Decimal
    quantity: Decimal
    first_trade_id: int
    last_trade_id: int
    buyer_is_maker: bool


@dataclass(frozen=True)
class MarketMetadata:
    observed_us: int
    tick_size: Decimal
    lot_size: Decimal
    min_notional: Decimal
    status: str = "TRADING"

    def __post_init__(self) -> None:
        _strict_int(self.observed_us, "observed_us", positive=True)
        for name in ("tick_size", "lot_size", "min_notional"):
            value = _positive_decimal(getattr(self, name), name)
            if value % Decimal("0.00001") != 0:
                raise PublicMarketError(f"{name} must be divisible by 0.00001")
        if self.status != "TRADING":
            raise PublicMarketError("status must be TRADING")


@dataclass(frozen=True)
class BookQuote:
    received_us: int
    update_id: int
    bid: Decimal
    ask: Decimal
    bid_quantity: Decimal
    ask_quantity: Decimal


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PublicMarketError("payload must be an object")
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise PublicMarketError("payload data must be an object")
    return data


def parse_trade(payload: dict[str, Any], *, expected_symbol: str = SYMBOL) -> MarketTrade:
    expected = _symbol(expected_symbol)
    data = _unwrap(payload)
    if "e" in data and data["e"] != "aggTrade":
        raise PublicMarketError("unexpected trade event")
    if "s" in data and data["s"] != expected:
        raise PublicMarketError("unexpected symbol")
    aggregate_id = _strict_int(data.get("a"), "aggregate_id", positive=True)
    timestamp = _strict_int(data.get("T", data.get("E")), "timestamp_us", positive=True)
    first_id = _strict_int(data.get("f"), "first_trade_id")
    last_id = _strict_int(data.get("l"), "last_trade_id")
    if first_id > last_id:
        raise PublicMarketError("first_trade_id must not exceed last_trade_id")
    if type(data.get("m")) is not bool:
        raise PublicMarketError("buyer_is_maker must be boolean")
    return MarketTrade(
        aggregate_id,
        timestamp,
        _positive_decimal(data.get("p"), "price"),
        _positive_decimal(data.get("q"), "quantity"),
        first_id,
        last_id,
        data["m"],
    )


def parse_book(
    payload: dict[str, Any], *, received_us: int, expected_symbol: str = SYMBOL
) -> BookQuote:
    expected = _symbol(expected_symbol)
    data = _unwrap(payload)
    if "s" in data and data["s"] != expected:
        raise PublicMarketError("unexpected symbol")
    # Spot bookTicker has no exchange timestamp. Never relabel E/T as local receipt.
    received = _strict_int(received_us, "received_us", positive=True)
    update_id = _strict_int(data.get("u"), "update_id", positive=True)
    bid = _positive_decimal(data.get("b"), "bid")
    ask = _positive_decimal(data.get("a"), "ask")
    if ask < bid:
        raise PublicMarketError("ask must be greater than or equal to bid")
    return BookQuote(
        received,
        update_id,
        bid,
        ask,
        _positive_decimal(data.get("B"), "bid_quantity"),
        _positive_decimal(data.get("A"), "ask_quantity"),
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Any:
        raise PublicMarketError("redirects are not allowed")


class PublicMarketClient:
    def __init__(self) -> None:
        self._pace_lock = threading.Lock()
        self._last_request = 0.0
        self._opener = urllib.request.build_opener(_NoRedirect)
        self.last_response: dict[str, Any] | None = None

    def _request_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if path not in {
            "/api/v3/time",
            "/api/v3/exchangeInfo",
            "/api/v3/aggTrades",
            "/api/v3/depth",
            "/api/v3/executionRules",
            "/api/v3/referencePrice",
        }:
            raise PublicMarketError("endpoint is not allowlisted")
        query = urllib.parse.urlencode(params or {})
        # These two public endpoints are documented but not served by the
        # market-data-only host (observed 404). Fixed endpoint mapping, no
        # configurable host and no authenticated/account fallback.
        base = (
            "https://api.binance.com"
            if path in {"/api/v3/executionRules", "/api/v3/referencePrice"}
            else BASE_URL
        )
        url = base + path + ("?" + query if query else "")
        for attempt in range(4):
            with self._pace_lock:
                delay = 0.08 - (time.monotonic() - self._last_request)
                if delay > 0:
                    time.sleep(delay)
                self._last_request = time.monotonic()
            request = urllib.request.Request(url, headers=_HEADERS, method="GET")
            try:
                sent_us = time.time_ns() // 1000
                monotonic_start = time.perf_counter_ns()
                with self._opener.open(request, timeout=20) as response:
                    raw = response.read()
                    self.last_response = {
                        "url": url,
                        "sent_us": sent_us,
                        "received_us": time.time_ns() // 1000,
                        "rtt_us": (time.perf_counter_ns() - monotonic_start) // 1000,
                        "status": response.status,
                        "headers": dict(response.headers),
                        "body": raw.decode("utf-8"),
                    }
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                if exc.code not in (418, 429) or attempt == 3:
                    raise PublicMarketError(f"public API HTTP {exc.code}") from exc
                retry = exc.headers.get("Retry-After", "0")
                try:
                    wait = max(0.0, float(retry))
                except ValueError:
                    wait = 0.0
                if wait > 30 or exc.code == 418:
                    raise PublicMarketError(
                        f"public API rate limited; retry after {retry} seconds"
                    ) from exc
                if wait:
                    time.sleep(wait)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise PublicMarketError("public API request failed") from exc
        raise AssertionError("unreachable")

    def server_time(self) -> int:
        payload = self._request_json("/api/v3/time")
        if not isinstance(payload, dict):
            raise PublicMarketError("invalid server time response")
        return _strict_int(payload.get("serverTime"), "serverTime", positive=True)

    def exchange_info(self, symbol: str = SYMBOL) -> dict[str, Any]:
        expected = _symbol(symbol)
        payload = self._request_json("/api/v3/exchangeInfo", {"symbol": expected})
        if not isinstance(payload, dict):
            raise PublicMarketError("invalid exchange info response")
        return payload

    def depth_snapshot(self, symbol: str = SYMBOL, *, limit: int = 5000) -> dict[str, Any]:
        expected = _symbol(symbol)
        if type(limit) is not int or limit <= 0 or limit > 5000:
            raise PublicMarketError("limit must be a positive integer no greater than 5000")
        payload = self._request_json("/api/v3/depth", {"symbol": expected, "limit": limit})
        if (
            not isinstance(payload, dict)
            or type(payload.get("lastUpdateId")) is not int
            or payload["lastUpdateId"] <= 0
            or not isinstance(payload.get("bids"), list)
            or not isinstance(payload.get("asks"), list)
        ):
            raise PublicMarketError("invalid depth snapshot response")
        return payload

    def metadata(self, symbol: str = SYMBOL) -> MarketMetadata:
        expected = _symbol(symbol)
        payload = self.exchange_info(expected)
        try:
            symbol_info = payload["symbols"][0]
            if symbol_info["symbol"] != expected:
                raise KeyError
            filters = {item["filterType"]: item for item in symbol_info["filters"]}
            notional_filter = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL")
            if notional_filter is None:
                raise KeyError("NOTIONAL")
            notional = notional_filter["minNotional"]
            return MarketMetadata(
                self.server_time(),
                _positive_decimal(filters["PRICE_FILTER"]["tickSize"], "tick_size"),
                _positive_decimal(filters["LOT_SIZE"]["stepSize"], "lot_size"),
                _positive_decimal(notional, "min_notional"),
                symbol_info["status"],
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise PublicMarketError("invalid exchange info response") from exc

    def agg_trades(
        self,
        *,
        symbol: str = SYMBOL,
        from_id: int | None = None,
        start_us: int | None = None,
        end_us: int | None = None,
    ) -> list[MarketTrade]:
        expected = _symbol(symbol)
        supplied = sum(value is not None for value in (from_id, start_us, end_us))
        if from_id is not None and (supplied != 1 or type(from_id) is not int or from_id < 0):
            raise PublicMarketError("from_id cannot be combined with time bounds")
        if start_us is not None and (type(start_us) is not int or start_us <= 0):
            raise PublicMarketError("start_us must be positive integer")
        if end_us is not None and (type(end_us) is not int or end_us <= 0):
            raise PublicMarketError("end_us must be positive integer")
        if start_us is not None and end_us is not None and start_us > end_us:
            raise PublicMarketError("start_us must not exceed end_us")
        params: dict[str, Any] = {"symbol": expected, "limit": 1000}
        if from_id is not None:
            params["fromId"] = from_id
        else:
            if start_us is not None:
                params["startTime"] = start_us
            if end_us is not None:
                params["endTime"] = end_us
        payload = self._request_json("/api/v3/aggTrades", params)
        if not isinstance(payload, list):
            raise PublicMarketError("invalid aggregate trades response")
        return [parse_trade(item, expected_symbol=expected) for item in payload]


@contextmanager
def connect_market_stream(
    *,
    symbols: tuple[str, ...] = (SYMBOL,),
    depth_interval_ms: int = 1000,
    calibration: bool = False,
    forward_depth: bool = False,
) -> Iterator[Any]:
    from websockets.sync.client import connect

    if type(depth_interval_ms) is not int or depth_interval_ms <= 0:
        raise PublicMarketError("depth_interval_ms must be a positive integer")
    normalized = tuple(_symbol(symbol) for symbol in symbols)
    if not normalized or len(set(normalized)) != len(normalized):
        raise PublicMarketError("symbols must be a non-empty unique allowlisted tuple")
    if calibration:
        if normalized != (SYMBOL,):
            raise PublicMarketError("calibration stream supports USDCUSDT only")
        url = (
            "wss://data-stream.binance.vision/stream?streams="
            "usdcusdt@trade/usdcusdt@bookTicker/usdcusdt@depth@100ms&timeUnit=MICROSECOND"
        )
    elif forward_depth:
        streams = "/".join(
            f"{symbol.lower()}@trade/{symbol.lower()}@depth@{depth_interval_ms}ms"
            for symbol in normalized
        )
        url = f"wss://data-stream.binance.vision/stream?streams={streams}&timeUnit=MICROSECOND"
    elif normalized == (SYMBOL,):
        url = STREAM_URL
    else:
        raise PublicMarketError("multi-symbol stream requires forward_depth=True")
    connection = connect(
        url,
        ping_interval=None,
        ping_timeout=20,
        open_timeout=20,
        max_queue=8192 if forward_depth else 1024,
    )
    try:
        yield connection
    finally:
        connection.close()
