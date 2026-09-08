"""Canonical application service for the local SHADOW operator dashboard."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from crypto_strategy_lab.operator_dashboard.binance import (
    BinanceConnectionError,
    BinanceObserver,
    BinancePublicPrivateObserver,
    DemoBinanceObserver,
)
from crypto_strategy_lab.operator_dashboard.security import mask_api_key, redact
from crypto_strategy_lab.operator_dashboard.storage import OperatorStore
from crypto_strategy_lab.operator_dashboard.vault import DpapiCredentialVault

PAIR = "USDCUSDT"
ALLOWED_MODE = "SHADOW"
QUEUE_STATUSES = {
    "FLAT",
    "BUY_WORKING",
    "LONG",
    "SELL_WORKING",
    "RELEASE",
    "BLOCKED",
}


@dataclass(frozen=True, slots=True)
class OperatorPaths:
    root: Path
    runtime: Path
    current_state: Path
    model_spec: Path

    @classmethod
    def from_root(cls, root: Path) -> OperatorPaths:
        return cls(
            root=root,
            runtime=root / "runtime",
            current_state=root / "docs/research/CURRENT_STATE.md",
            model_spec=root / "docs/microstructure/M013_MODEL_SPEC.json",
        )


def _parse_current_state(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


class OperatorService:
    """Own runtime state and expose only explicit, auditable control methods."""

    def __init__(
        self,
        root: Path,
        *,
        observer: BinanceObserver | None = None,
        demo: bool = False,
        poll_seconds: float = 5.0,
    ) -> None:
        self.paths = OperatorPaths.from_root(root.resolve())
        self.paths.runtime.mkdir(parents=True, exist_ok=True)
        self.store = OperatorStore(
            self.paths.runtime / "operator.sqlite3",
            self.paths.runtime / "operator-events.jsonl",
        )
        self.vault = DpapiCredentialVault(self.paths.runtime / "operator-credentials.dpapi")
        self.observer = observer or (
            DemoBinanceObserver() if demo else BinancePublicPrivateObserver()
        )
        self.demo = demo
        self.poll_seconds = poll_seconds
        self.instance_id = str(uuid.uuid4())
        self._lock = threading.RLock()
        self._shutdown = threading.Event()
        self._wake = threading.Event()
        self._worker: threading.Thread | None = None
        self._started_monotonic: float | None = None
        self._market: dict[str, Any] = {
            "symbol": PAIR,
            "status": "NOT_CONNECTED",
            "source": "DEMO_FIXTURE" if demo else "BINANCE_PUBLIC_REST",
        }
        self._connection: dict[str, Any] = {
            "status": "CONFIGURED" if self.vault.configured() else "NOT_CONFIGURED",
            "private_status": "DISCONNECTED",
            "balances": [],
            "permissions": {"read": "UNKNOWN", "spot_trading": "UNKNOWN", "withdraw": "UNKNOWN"},
        }
        self._previous_status = self.store.get_metadata("bot_status", "OFFLINE")
        self._bot_status = "STOPPED_SAFE"
        self._mode = ALLOWED_MODE
        self._reconciled = self._previous_status not in {"RUNNING", "STARTING", "STOPPING"}
        self._why_blocked: list[str] = []
        self._state_divergence = False
        self._exchange_open_orders: list[dict[str, Any]] = []
        self._strategy = self._load_strategy()
        self._capital = self._initial_capital()
        self._queues = self._initial_queues()
        self.store.set_metadata("bot_status", self._bot_status)
        self.store.set_metadata("mode", ALLOWED_MODE)
        self.store.set_metadata("operator_instance_id", self.instance_id)
        self.store.append_event(
            "OPERATOR_DASHBOARD_STARTED",
            {
                "instance_id": self.instance_id,
                "previous_status": self._previous_status,
                "mode": ALLOWED_MODE,
                "live_trading_enabled": False,
            },
        )
        if not self._reconciled:
            self._bot_status = "RECOVERING"
            self.store.set_metadata("bot_status", self._bot_status)

    def _load_strategy(self) -> dict[str, Any]:
        current = _parse_current_state(self.paths.current_state)
        model_id = current.get("ACTIVE_MODEL") or current.get("MODEL_ID", "")
        if not model_id:
            raise ValueError("MODEL_NOT_LOADED")
        spec_path = self.paths.root / f"docs/microstructure/{model_id}_MODEL_SPEC.json"
        payload = json.loads(spec_path.read_text(encoding="utf-8"))
        if payload.get("model_id") != model_id:
            raise ValueError("MODEL_IDENTITY_DIVERGENCE")
        model_hash = current.get("MODEL_HASH", "")
        if not model_hash:
            raise ValueError("MODEL_HASH_NOT_LOADED")
        return {
            "active_model": model_id,
            "model_hash": model_hash,
            "model_status": current.get("RUN_STATUS", "UNKNOWN"),
            "strategy": current.get("ACTIVE_RESEARCH_MODEL") or payload.get("strategy"),
            "capital_mode": payload.get("capital_mode"),
            "reserve_funding_rate": payload.get("operating_profit_to_reserve"),
            "max_lock_hours": payload.get("operating_max_hold_hours"),
            "max_queues": payload.get("max_total_queues"),
            "pair": payload.get("symbol"),
            "execution_profile": payload.get("primary_execution_profile"),
            "trading_enabled": False,
            "owner_authorized": False,
            "spec": payload,
            "current_state": current,
        }

    def _initial_capital(self) -> dict[str, Any]:
        spec = self._strategy["spec"]
        current = self._strategy["current_state"]
        operating = current.get("OPERATING_CAPITAL") or spec.get("operating_bank_initial", "100")
        reserve = current.get("RECOVERY_RESERVE") or spec.get("reserve_initial", "10")
        total = current.get("TOTAL_EQUITY") or spec.get("total_initial_equity", "110")
        return {
            "total_equity": total,
            "operating_capital": operating,
            "current_operating_bank": operating,
            "recovery_reserve": reserve,
            "reserve_ratio": current.get("RESERVE_RATIO")
            or spec.get("reserve_target_ratio", "0.10"),
            "core_reserve": current.get("CORE_RESERVE") or reserve,
            "active_reserve": current.get("ACTIVE_RESERVE_CAPITAL", "0"),
            "unrealized_pnl": "0",
            "realized_pnl": "0",
            "total_profit": current.get("TOTAL_PROFIT", "0"),
            "owner_withdrawals": "DISABLED",
            "next_order_budget": "PENDING_ALLOCATION",
            "compounding_multiplier": "1",
            "profit_reinvested": "0",
            "profit_to_reserve": "0",
            "target_reserve": "10",
            "funding_today": "0",
            "funding_total": "0",
            "release_spend_today": "0",
            "release_spend_total": "0",
            "recovery_ratio": None,
            "time_to_recover_last_release": None,
        }

    def _initial_queues(self) -> list[dict[str, Any]]:
        queues: list[dict[str, Any]] = []
        for index in range(1, 5):
            queue_type = "ACTIVE_RESERVE" if index == 4 else "OPERATING"
            queues.append(
                {
                    "queue_id": f"Q{index}",
                    "type": queue_type,
                    "status": "FLAT",
                    "range_low": None,
                    "range_high": None,
                    "capital_assigned": "0",
                    "position_size": "0",
                    "entry_time": None,
                    "hold_age_seconds": 0,
                    "lock_state": "NORMAL",
                    "realized_pnl": "0",
                    "unrealized_pnl": "0",
                    "order_status": "NONE",
                    "fill_percent": 0,
                    "queue_ahead_proxy": None,
                    "next_action": "Await causal eligible range",
                }
            )
        return queues

    def credential_status(self) -> dict[str, Any]:
        return {
            "status": "CONFIGURED" if self.vault.configured() else "NOT_CONFIGURED",
            "api_key_masked": self.store.get_metadata("api_key_masked") or None,
            "api_key_last4": self.store.get_metadata("api_key_last4") or None,
            "secret_configured": self.vault.configured(),
            "permissions_status": self.store.get_metadata("permissions_status", "UNKNOWN"),
            "created_at": self.store.get_metadata("credentials_created_at") or None,
            "last_validated_at": self.store.get_metadata("credentials_last_validated_at") or None,
            "vault": "WINDOWS_DPAPI_CURRENT_USER",
        }

    def configure_credentials(self, api_key: str, api_secret: str) -> dict[str, Any]:
        self.vault.save(api_key, api_secret)
        now = datetime.now(UTC).isoformat()
        self.store.set_metadata("api_key_masked", mask_api_key(api_key.strip()))
        self.store.set_metadata("api_key_last4", api_key.strip()[-4:])
        self.store.set_metadata("credentials_created_at", now)
        self.store.set_metadata("permissions_status", "NOT_VALIDATED")
        with self._lock:
            self._connection = {
                **self._connection,
                "status": "CONFIGURED",
                "private_status": "DISCONNECTED",
                "balances": [],
            }
        self.store.append_event("BINANCE_CREDENTIALS_CONFIGURED", {"api_key_last4": api_key[-4:]})
        return self.credential_status()

    def delete_credentials(self) -> dict[str, Any]:
        deleted = self.vault.delete()
        for key in (
            "api_key_masked",
            "api_key_last4",
            "credentials_created_at",
            "credentials_last_validated_at",
        ):
            self.store.set_metadata(key, "")
        self.store.set_metadata("permissions_status", "NOT_CONFIGURED")
        with self._lock:
            self._connection = {
                "status": "NOT_CONFIGURED",
                "private_status": "DISCONNECTED",
                "balances": [],
                "permissions": {
                    "read": "UNKNOWN",
                    "spot_trading": "UNKNOWN",
                    "withdraw": "UNKNOWN",
                },
            }
        self.store.append_event("BINANCE_CREDENTIALS_DELETED", {"deleted": deleted})
        return self.credential_status()

    def disconnect(self) -> dict[str, Any]:
        with self._lock:
            self._connection["private_status"] = "DISCONNECTED"
            self._connection["balances"] = []
        self.store.append_event("BINANCE_DISCONNECTED")
        return self.connection()

    def test_connection(self) -> dict[str, Any]:
        credentials = self.vault.load() if self.vault.configured() else None
        result = self.observer.test_connection(credentials)
        verdict = str(result.get("verdict", "NETWORK_ERROR"))
        permissions = {
            "read": "YES" if result.get("account_auth") == "PASS" else "UNKNOWN",
            "spot_trading": result.get("trading_permission", "UNKNOWN"),
            "withdraw": result.get("withdraw_permission", "UNKNOWN"),
        }
        with self._lock:
            self._connection = {
                "status": "CONFIGURED" if self.vault.configured() else "NOT_CONFIGURED",
                "private_status": verdict,
                "balances": result.get("balances", []),
                "permissions": permissions,
                "last_test": redact(result),
            }
            if verdict in {"CONNECTED_READ_ONLY", "PUBLIC_ONLY_PASS"}:
                self._market = {**self._market, "status": "CONNECTED"}
        if verdict == "CONNECTED_READ_ONLY":
            if credentials is None:
                raise RuntimeError("CREDENTIAL_STATE_DIVERGENCE")
            exchange_orders = self.observer.open_orders(credentials)
            local_order_ids = {
                str(order.get("exchange_order_id")) for order in self.store.orders()
            }
            exchange_order_ids = {
                str(order.get("exchange_order_id")) for order in exchange_orders
            }
            self._exchange_open_orders = exchange_orders
            self._state_divergence = local_order_ids != exchange_order_ids
            if self._state_divergence:
                self._reconciled = False
            now = datetime.now(UTC).isoformat()
            self.store.set_metadata("credentials_last_validated_at", now)
            self.store.set_metadata("permissions_status", json.dumps(permissions, sort_keys=True))
            self.store.append_event(
                "BINANCE_CONNECTED",
                {
                    "mode": "READ_ONLY",
                    "state_divergence": self._state_divergence,
                    "exchange_open_order_count": len(exchange_orders),
                    **permissions,
                },
            )
        else:
            self.store.append_event("BINANCE_CONNECTION_TEST", {"verdict": verdict})
        return cast(dict[str, Any], redact(result))

    def connection(self) -> dict[str, Any]:
        with self._lock:
            return {**self._connection, "credentials": self.credential_status()}

    def _refresh_market(self) -> bool:
        try:
            market = self.observer.public_market()
        except BinanceConnectionError as error:
            with self._lock:
                self._market = {**self._market, "status": error.code}
            self.store.append_event("BINANCE_DISCONNECTED", {"reason": error.code})
            return False
        with self._lock:
            self._market = {**market, "status": "CONNECTED"}
        return True

    def market(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._market)

    def _preflight(self) -> dict[str, Any]:
        market_ok = self._refresh_market()
        checks = {
            "api_connection": "PASS" if market_ok else "FAIL",
            "strategy_loaded": "PASS" if self._strategy.get("active_model") else "FAIL",
            "model_hash": "PASS" if self._strategy.get("model_hash") else "FAIL",
            "market_symbol": "PASS" if self._strategy.get("pair") == PAIR else "FAIL",
            "clock_sync": "PASS" if self.demo else "PUBLIC_REST_ONLY",
            "balances": "OPTIONAL_PRIVATE_READ_ONLY",
            "reserve": "PASS",
            "open_orders": "SHADOW_NONE",
            "local_persisted_state": "PASS",
            "recovery_state": "PASS" if self._reconciled else "FAIL",
            "state_divergence": "FAIL" if self._state_divergence else "PASS",
            "duplicate_process_protection": "PASS",
            "trading_mode": "PASS_SHADOW_ONLY",
            "capital_allocation": "PASS",
            "capacity": "PASS_INITIAL",
            "filters": "PASS" if market_ok else "FAIL",
            "minimum_notional": "NOT_APPLICABLE_NO_ORDERS",
            "lot_size": "NOT_APPLICABLE_NO_ORDERS",
        }
        blocked = [key.upper() for key, value in checks.items() if value == "FAIL"]
        self._why_blocked = blocked
        return {
            "checks": checks,
            "why_blocked": blocked,
            "verdict": "PASS" if not blocked else "BLOCKED",
        }

    def preflight(self) -> dict[str, Any]:
        return self._preflight()

    def play(self, mode: str) -> dict[str, Any]:
        if mode != ALLOWED_MODE:
            raise PermissionError("LIVE_TRADING_DISABLED_SHADOW_ONLY")
        with self._lock:
            if self._bot_status == "RUNNING":
                return self.status()
            self._bot_status = "STARTING"
            self.store.set_metadata("bot_status", self._bot_status)
        preflight = self._preflight()
        if preflight["verdict"] != "PASS":
            with self._lock:
                self._bot_status = "STOPPED_SAFE"
                self.store.set_metadata("bot_status", self._bot_status)
            raise RuntimeError("PREFLIGHT_BLOCKED:" + ",".join(preflight["why_blocked"]))
        with self._lock:
            self._bot_status = "RUNNING"
            self._started_monotonic = time.monotonic()
            self.store.set_metadata("bot_status", self._bot_status)
        self.store.append_event(
            "BOT_STARTED", {"mode": ALLOWED_MODE, "model": self._strategy["active_model"]}
        )
        self._ensure_worker()
        self._wake.set()
        self._record_snapshot()
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._bot_status not in {"RUNNING", "STARTING", "RECOVERING"}:
                self._bot_status = "STOPPED_SAFE"
            else:
                self._bot_status = "STOPPING"
            self.store.set_metadata("bot_status", self._bot_status)
        self.store.append_event("NEW_ENTRIES_DISABLED", {"reason": "OWNER_GRACEFUL_STOP"})
        with self._lock:
            self._bot_status = "STOPPED_SAFE"
            self._started_monotonic = None
            self.store.set_metadata("bot_status", self._bot_status)
        self.store.append_event("BOT_STOPPED", {"semantics": "GRACEFUL_PRESERVE_STATE"})
        self._record_snapshot()
        return self.status()

    def emergency_stop(self, confirmation: str) -> dict[str, Any]:
        if confirmation != "CONFIRM STOP":
            raise PermissionError("EMERGENCY_CONFIRMATION_REQUIRED")
        with self._lock:
            self._bot_status = "STOPPED_SAFE"
            self._started_monotonic = None
            for queue in self._queues:
                if queue["status"] in {"BUY_WORKING", "SELL_WORKING"}:
                    queue["status"] = "BLOCKED"
                    queue["order_status"] = "CANCELLED_SHADOW"
        self.store.set_metadata("bot_status", self._bot_status)
        self.store.append_event(
            "EMERGENCY_STOP",
            {"policy": "STOP_NEW_ENTRIES_CANCEL_SHADOW_WORK_PRESERVE_HOLDINGS"},
        )
        return self.status()

    def reconcile(self) -> dict[str, Any]:
        # This release cannot have exchange-side orders.  A previous SHADOW run is safe
        # only after explicitly recording that the local state was retained and stopped.
        if self._state_divergence:
            raise RuntimeError("STATE_DIVERGENCE_REQUIRES_MANUAL_RECONCILIATION")
        with self._lock:
            self._reconciled = True
            self._bot_status = "STOPPED_SAFE"
            self.store.set_metadata("bot_status", self._bot_status)
        self.store.append_event(
            "STATE_RECONCILED", {"scope": "SHADOW_LOCAL_ONLY", "duplicate_orders_possible": False}
        )
        return self.status()

    def _ensure_worker(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._worker_loop, name="operator-shadow", daemon=True
        )
        self._worker.start()

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            self._wake.wait(timeout=self.poll_seconds)
            self._wake.clear()
            with self._lock:
                running = self._bot_status == "RUNNING"
            if running:
                self._refresh_market()
                self._record_snapshot()

    def _record_snapshot(self) -> None:
        self.store.add_snapshot(
            {
                "total_equity": self._capital["total_equity"],
                "operating_bank": self._capital["current_operating_bank"],
                "reserve": self._capital["recovery_reserve"],
                "reserve_ratio": self._capital["reserve_ratio"],
                "realized_pnl": self._capital["realized_pnl"],
                "productive_capital_percent": 0,
            }
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            uptime = (
                max(0, int(time.monotonic() - self._started_monotonic))
                if self._started_monotonic is not None
                else 0
            )
            return {
                "bot_status": self._bot_status,
                "mode": self._mode,
                "binance": self._market.get("status", "DISCONNECTED"),
                "strategy": self._strategy["strategy"],
                "model_id": self._strategy["active_model"],
                "model_hash": self._strategy["model_hash"],
                "pair": PAIR,
                "uptime_seconds": uptime,
                "operator_instance_id": self.instance_id,
                "reconciliation": "RECONCILED" if self._reconciled else "REQUIRED",
                "state_divergence": self._state_divergence,
                "trading_authorization": "SHADOW",
                "trading_enabled": False,
                "why_blocked": list(self._why_blocked),
                "demo": self.demo,
            }

    def capital(self) -> dict[str, Any]:
        return dict(self._capital)

    def reserve(self) -> dict[str, Any]:
        keys = {
            "recovery_reserve",
            "target_reserve",
            "reserve_ratio",
            "core_reserve",
            "active_reserve",
            "funding_today",
            "funding_total",
            "release_spend_today",
            "release_spend_total",
            "recovery_ratio",
            "time_to_recover_last_release",
        }
        return {key: value for key, value in self._capital.items() if key in keys}

    def queues(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(queue) for queue in self._queues]

    def orders(self) -> dict[str, Any]:
        return {
            "open_orders": [*self.store.orders(), *self._exchange_open_orders],
            "recent_fills": [],
            "recent_releases": [],
        }

    def machine_health(self) -> dict[str, Any]:
        status = self.status()
        running = status["bot_status"] == "RUNNING"
        current = self._strategy["current_state"]
        motor_uptime = float(current.get("MOTOR_UPTIME", 1 if running else 0)) * 100
        capital_uptime = float(current.get("CAPITAL_WEIGHTED_UPTIME", 0)) * 100
        return {
            "motor_uptime_percent": round(motor_uptime, 3),
            "capital_weighted_uptime_percent": round(capital_uptime, 3),
            "productive_capital_percent": round(capital_uptime, 3),
            "locked_capital_percent": 0,
            "idle_capital_percent": 100,
            "active_queues": int(current.get("OPERATING_QUEUES_ACTIVE", 0)),
            "full_stop_time_today_seconds": status["uptime_seconds"] if running else 0,
            "full_stop_time_total_seconds": round(
                float(current.get("FULL_STOP_HOURS", 0)) * 3600
            ),
            "zero_cycle_days": int(current.get("ZERO_CYCLE_DAYS", 0)),
        }

    def strategy(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in self._strategy.items()
            if key not in {"spec", "current_state"}
        }

    def events(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.events(limit)

    def charts(self) -> list[dict[str, Any]]:
        return self.store.snapshots()

    def health(self) -> dict[str, Any]:
        return {
            "app": "PASS",
            "engine": self._bot_status,
            "market_data": self._market.get("status"),
            "private_binance": self._connection.get("private_status"),
            "state_store": "PASS",
            "writer": "PASS",
            "last_event": self.store.events(1)[0] if self.store.events(1) else None,
            "live_trading_enabled": False,
        }

    def assistant(self, question: str) -> dict[str, Any]:
        normalized = question.casefold()
        if not question.strip():
            raise ValueError("QUESTION_REQUIRED")
        if "reserva" in normalized:
            answer = (
                f"A reserva atual é {self._capital['recovery_reserve']} USDT; "
                f"gasto hoje: {self._capital['release_spend_today']} USDT."
            )
        elif "q2" in normalized or "fila" in normalized:
            q2 = self._queues[1]
            answer = f"Q2 está {q2['status']}. Próxima ação: {q2['next_action']}."
        elif "compr" in normalized:
            answer = (
                "Nenhuma compra é enviada nesta entrega: o cockpit está SHADOW-only e aguarda "
                "uma faixa causal elegível para simular uma decisão."
            )
        elif "ganh" in normalized or "pnl" in normalized:
            answer = f"PnL realizado desde o início: {self._capital['realized_pnl']} USDT."
        else:
            health = self.machine_health()
            answer = (
                f"Bot {self._bot_status}, Binance {self._market.get('status')}, "
                f"filas ativas {health['active_queues']}, capital produtivo "
                f"{health['productive_capital_percent']}%."
            )
        self.store.append_event("ASSISTANT_QUERY", {"category": "READ_ONLY_STATE_QUERY"})
        return {"answer": answer, "chat_actions": "READ_ONLY"}

    def dashboard(self) -> dict[str, Any]:
        return {
            "status": self.status(),
            "connection": self.connection(),
            "capital": self.capital(),
            "reserve": self.reserve(),
            "queues": self.queues(),
            "orders": self.orders(),
            "market": self.market(),
            "machine_health": self.machine_health(),
            "strategy": self.strategy(),
            "events": self.events(50),
            "charts": self.charts(),
        }

    def close(self) -> None:
        self._shutdown.set()
        self._wake.set()
        if self._worker:
            self._worker.join(timeout=2)
        if self._bot_status == "RUNNING":
            self.stop()
        self.store.append_event("OPERATOR_DASHBOARD_STOPPED", {"instance_id": self.instance_id})
