"""Narrow Binance observer clients; deliberately no trading or withdrawal methods."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from crypto_strategy_lab.operator_dashboard.vault import BinanceCredentials

BINANCE_API_BASE = "https://api.binance.com"
SYMBOL = "USDCUSDT"


class BinanceConnectionError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.safe_message = message or code


class BinanceObserver(Protocol):
    def public_market(self) -> dict[str, Any]: ...

    def test_connection(self, credentials: BinanceCredentials | None) -> dict[str, Any]: ...

    def open_orders(self, credentials: BinanceCredentials) -> list[dict[str, Any]]: ...


class BinancePublicPrivateObserver:
    def __init__(self, base_url: str = BINANCE_API_BASE, timeout: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        api_key: str | None = None,
    ) -> Any:
        query = urllib.parse.urlencode(params or {})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        headers = {"Accept": "application/json", "User-Agent": "CryptoChange-Local/0.1"}
        if api_key:
            headers["X-MBX-APIKEY"] = api_key
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read(2_000_000))
        except urllib.error.HTTPError as error:
            try:
                payload = json.loads(error.read(32_000))
                binance_code = int(payload.get("code", 0))
            except (ValueError, TypeError, json.JSONDecodeError):
                binance_code = 0
            if binance_code == -1021:
                raise BinanceConnectionError("CLOCK_SKEW") from None
            if binance_code in {-2014, -2015}:
                raise BinanceConnectionError("INVALID_CREDENTIALS") from None
            if error.code in {401, 403}:
                raise BinanceConnectionError("PERMISSION_ERROR") from None
            raise BinanceConnectionError("BINANCE_HTTP_ERROR", f"HTTP_{error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise BinanceConnectionError("NETWORK_ERROR") from None

    def _signed_request(
        self, path: str, credentials: BinanceCredentials, params: dict[str, str] | None = None
    ) -> Any:
        signed = dict(params or {})
        signed["timestamp"] = str(int(time.time() * 1000))
        signed["recvWindow"] = "5000"
        query = urllib.parse.urlencode(signed)
        signed["signature"] = hmac.new(
            credentials.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return self._request(path, params=signed, api_key=credentials.api_key)

    def _server_time(self) -> tuple[int, int, int]:
        started_wall = int(time.time() * 1000)
        started = time.perf_counter()
        payload = self._request("/api/v3/time")
        latency_ms = round((time.perf_counter() - started) * 1000)
        finished_wall = int(time.time() * 1000)
        server_ms = int(payload["serverTime"])
        midpoint = (started_wall + finished_wall) // 2
        return server_ms, server_ms - midpoint, latency_ms

    def public_market(self) -> dict[str, Any]:
        started = time.perf_counter()
        book = self._request("/api/v3/ticker/bookTicker", params={"symbol": SYMBOL})
        depth = self._request("/api/v3/depth", params={"symbol": SYMBOL, "limit": "5"})
        trades = self._request("/api/v3/trades", params={"symbol": SYMBOL, "limit": "100"})
        latency = round((time.perf_counter() - started) * 1000)
        bid = Decimal(str(book["bidPrice"]))
        ask = Decimal(str(book["askPrice"]))
        trade_times = [int(item["time"]) for item in trades] if trades else []
        span = max(1, (max(trade_times) - min(trade_times)) / 1000) if trade_times else 1
        return {
            "symbol": SYMBOL,
            "bid": str(bid),
            "ask": str(ask),
            "spread": str(ask - bid),
            "last_trade": str(trades[-1]["price"]) if trades else None,
            "depth_best_bid": str(depth["bids"][0][0]) if depth.get("bids") else None,
            "depth_best_ask": str(depth["asks"][0][0]) if depth.get("asks") else None,
            "trades_per_second": round(len(trades) / span, 2),
            "connection_latency_ms": latency,
            "last_websocket_event": None,
            "last_rest_heartbeat": int(time.time() * 1000),
            "source": "BINANCE_PUBLIC_REST",
        }

    def test_connection(self, credentials: BinanceCredentials | None) -> dict[str, Any]:
        checks: dict[str, Any] = {"dns_network": "CONNECTING"}
        try:
            server_ms, clock_skew_ms, latency_ms = self._server_time()
            checks.update(
                {
                    "dns_network": "PASS",
                    "server_time": "PASS",
                    "server_time_ms": server_ms,
                    "clock_skew_ms": clock_skew_ms,
                    "latency_ms": latency_ms,
                }
            )
            symbol = self._request("/api/v3/exchangeInfo", params={"symbol": SYMBOL})
            symbols = symbol.get("symbols", [])
            checks["usdcusdt_symbol"] = (
                "PASS" if symbols and symbols[0].get("status") == "TRADING" else "FAIL"
            )
            checks["filters"] = symbols[0].get("filters", []) if symbols else []
            if abs(clock_skew_ms) > 5_000:
                checks.update({"account_auth": "NOT_RUN", "verdict": "CLOCK_SKEW"})
                return checks
            if credentials is None:
                checks.update(
                    {
                        "account_auth": "NOT_CONFIGURED",
                        "spot_access": "UNKNOWN",
                        "trading_permission": "UNKNOWN",
                        "withdraw_permission": "UNKNOWN",
                        "balances": [],
                        "verdict": "PUBLIC_ONLY_PASS",
                    }
                )
                return checks
            account = self._signed_request("/api/v3/account", credentials)
            balances = [
                {
                    "asset": row["asset"],
                    "free": row["free"],
                    "locked": row["locked"],
                }
                for row in account.get("balances", [])
                if row.get("asset") in {"USDC", "USDT"}
            ]
            checks.update(
                {
                    "account_auth": "PASS",
                    "spot_access": "PASS" if account.get("accountType") == "SPOT" else "UNKNOWN",
                    "trading_permission": "YES" if account.get("canTrade") else "NO",
                    "withdraw_permission": "YES" if account.get("canWithdraw") else "NO",
                    "balances": balances,
                    "verdict": "CONNECTED_READ_ONLY",
                }
            )
            return checks
        except BinanceConnectionError as error:
            checks["verdict"] = error.code
            checks.setdefault("account_auth", "FAIL")
            return checks

    def open_orders(self, credentials: BinanceCredentials) -> list[dict[str, Any]]:
        payload = self._signed_request("/api/v3/openOrders", credentials, {"symbol": SYMBOL})
        return [
            {
                "timestamp": row.get("time"),
                "queue": None,
                "side": row.get("side"),
                "type": row.get("type"),
                "price": row.get("price"),
                "quantity": row.get("origQty"),
                "notional": None,
                "filled": row.get("executedQty"),
                "remaining": str(
                    Decimal(str(row.get("origQty", "0")))
                    - Decimal(str(row.get("executedQty", "0")))
                ),
                "status": row.get("status"),
                "maker_taker": None,
                "fee": None,
                "exchange_order_id": str(row.get("orderId")),
            }
            for row in payload
        ]


@dataclass(slots=True)
class DemoBinanceObserver:
    disconnected: bool = False
    tick: int = 0

    def public_market(self) -> dict[str, Any]:
        if self.disconnected:
            raise BinanceConnectionError("NETWORK_ERROR")
        self.tick += 1
        offset = Decimal(self.tick % 4) * Decimal("0.0001")
        bid = Decimal("0.9998") + offset
        ask = bid + Decimal("0.0002")
        return {
            "symbol": SYMBOL,
            "bid": str(bid),
            "ask": str(ask),
            "spread": str(ask - bid),
            "last_trade": str(bid + Decimal("0.0001")),
            "depth_best_bid": str(bid),
            "depth_best_ask": str(ask),
            "trades_per_second": 4.2,
            "connection_latency_ms": 12,
            "last_websocket_event": None,
            "last_rest_heartbeat": int(time.time() * 1000),
            "source": "DEMO_FIXTURE",
        }

    def test_connection(self, credentials: BinanceCredentials | None) -> dict[str, Any]:
        if self.disconnected:
            return {"dns_network": "FAIL", "verdict": "NETWORK_ERROR"}
        return {
            "dns_network": "PASS",
            "server_time": "PASS",
            "server_time_ms": int(time.time() * 1000),
            "clock_skew_ms": 0,
            "latency_ms": 12,
            "account_auth": "PASS" if credentials else "NOT_CONFIGURED",
            "spot_access": "PASS" if credentials else "UNKNOWN",
            "trading_permission": "NO",
            "withdraw_permission": "NO",
            "balances": [
                {"asset": "USDC", "free": "54.20", "locked": "0"},
                {"asset": "USDT", "free": "110.00", "locked": "0"},
            ]
            if credentials
            else [],
            "usdcusdt_symbol": "PASS",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.00010000"},
                {"filterType": "LOT_SIZE", "stepSize": "0.10000000"},
                {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
            ],
            "verdict": "CONNECTED_READ_ONLY" if credentials else "PUBLIC_ONLY_PASS",
        }

    def open_orders(self, credentials: BinanceCredentials) -> list[dict[str, Any]]:
        return []
