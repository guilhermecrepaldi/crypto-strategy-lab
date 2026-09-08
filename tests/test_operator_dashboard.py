from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from crypto_strategy_lab.operator_dashboard.binance import DemoBinanceObserver
from crypto_strategy_lab.operator_dashboard.security import REDACTED, redact
from crypto_strategy_lab.operator_dashboard.server import (
    LOOPBACK_HOST,
    SingleInstanceError,
    SingleInstanceLock,
    create_server,
)
from crypto_strategy_lab.operator_dashboard.service import OperatorService
from crypto_strategy_lab.operator_dashboard.storage import OperatorStore
from crypto_strategy_lab.operator_dashboard.vault import DpapiCredentialVault


def _operator_root(tmp_path: Path) -> Path:
    state_dir = tmp_path / "docs/research"
    spec_dir = tmp_path / "docs/microstructure"
    state_dir.mkdir(parents=True)
    spec_dir.mkdir(parents=True)
    (state_dir / "CURRENT_STATE.md").write_text(
        "\n".join(
            (
                "# CURRENT STATE",
                "ACTIVE_MODEL=M013",
                "MODEL_HASH=test-model-hash",
                "RUN_STATUS=NOT_STARTED",
            )
        ),
        encoding="utf-8",
    )
    (spec_dir / "M013_MODEL_SPEC.json").write_text(
        json.dumps(
            {
                "model_id": "M013",
                "strategy": "CONTINUOUS_MULTI_QUEUE_RECOVERY",
                "capital_mode": "COMPOUNDING",
                "operating_bank_initial": "100",
                "reserve_initial": "10",
                "total_initial_equity": "110",
                "operating_profit_to_reserve": "0.10",
                "reserve_target_ratio": "0.10",
                "operating_max_hold_hours": "24",
                "max_total_queues": 4,
                "symbol": "USDCUSDT",
                "primary_execution_profile": "B_REALISTIC_CONSERVATIVE",
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def service(tmp_path: Path) -> OperatorService:
    instance = OperatorService(
        _operator_root(tmp_path), observer=DemoBinanceObserver(), demo=True, poll_seconds=0.01
    )
    yield instance
    instance.close()


def test_shadow_play_stop_and_no_live_authorization(service: OperatorService) -> None:
    assert service.status()["trading_enabled"] is False
    assert service.preflight()["verdict"] == "PASS"
    assert service.play("SHADOW")["bot_status"] == "RUNNING"
    with pytest.raises(PermissionError, match="SHADOW_ONLY"):
        service.play("LIVE")
    stopped = service.stop()
    assert stopped["bot_status"] == "STOPPED_SAFE"
    assert service.events(5)[0]["event"] == "BOT_STOPPED"


def test_dashboard_accepts_four_independent_queue_records(service: OperatorService) -> None:
    queues = service.queues()
    assert [queue["queue_id"] for queue in queues] == ["Q1", "Q2", "Q3", "Q4"]
    assert [queue["type"] for queue in queues] == [
        "OPERATING",
        "OPERATING",
        "OPERATING",
        "ACTIVE_RESERVE",
    ]
    assert all(queue["status"] == "FLAT" for queue in queues)
    assert service.strategy()["active_model"] == "M013"
    assert service.strategy()["model_hash"] == "test-model-hash"


def test_crash_recovery_never_restarts_and_blocks_play(tmp_path: Path) -> None:
    root = _operator_root(tmp_path)
    store = OperatorStore(root / "runtime/operator.sqlite3", root / "runtime/operator-events.jsonl")
    store.set_metadata("bot_status", "RUNNING")
    recovered = OperatorService(root, observer=DemoBinanceObserver(), demo=True)
    try:
        assert recovered.status()["bot_status"] == "RECOVERING"
        assert recovered.status()["reconciliation"] == "REQUIRED"
        with pytest.raises(RuntimeError, match="RECOVERY_STATE"):
            recovered.play("SHADOW")
        assert recovered.reconcile()["bot_status"] == "STOPPED_SAFE"
        assert recovered.play("SHADOW")["bot_status"] == "RUNNING"
    finally:
        recovered.close()


def test_redaction_covers_credentials_authorization_and_signatures() -> None:
    known = "do-not-leak-value"
    payload = {
        "BINANCE_API_KEY": known,
        "nested": {
            "Authorization": f"Bearer {known}",
            "message": f"signature=abcdef&safe=yes api_secret={known}",
        },
    }
    result = redact(payload, (known,))
    encoded = json.dumps(result)
    assert known not in encoded
    assert "abcdef" not in encoded
    assert encoded.count(REDACTED) >= 3


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows file lock authority")
def test_duplicate_operator_instance_is_blocked(tmp_path: Path) -> None:
    first = SingleInstanceLock(tmp_path / "operator.lock")
    second = SingleInstanceLock(tmp_path / "operator.lock")
    first.acquire()
    try:
        with pytest.raises(SingleInstanceError, match="ALREADY_RUNNING"):
            second.acquire()
    finally:
        first.release()


@pytest.mark.skipif(__import__("os").name != "nt", reason="DPAPI is a Windows authority")
def test_dpapi_vault_roundtrip_ciphertext_and_delete(tmp_path: Path) -> None:
    path = tmp_path / "operator-credentials.dpapi"
    vault = DpapiCredentialVault(path)
    key = "demo-public-key-1234"
    sensitive = "local-fixture-private-value-9876"
    vault.save(key, sensitive)
    assert sensitive.encode() not in path.read_bytes()
    assert key.encode() not in path.read_bytes()
    assert vault.load().api_key == key
    assert vault.load().api_secret == sensitive
    assert vault.delete() is True
    assert vault.configured() is False


class _DivergentDemoObserver(DemoBinanceObserver):
    def open_orders(self, _credentials: Any) -> list[dict[str, Any]]:
        return [{"exchange_order_id": "external-123", "status": "NEW"}]


@pytest.mark.skipif(__import__("os").name != "nt", reason="DPAPI is a Windows authority")
def test_private_state_divergence_blocks_play(tmp_path: Path) -> None:
    operator = OperatorService(
        _operator_root(tmp_path), observer=_DivergentDemoObserver(), demo=True
    )
    try:
        operator.configure_credentials("test-public-key-1234", "test-private-value-5678")
        assert operator.test_connection()["verdict"] == "CONNECTED_READ_ONLY"
        assert operator.status()["state_divergence"] is True
        preflight = operator.preflight()
        assert "STATE_DIVERGENCE" in preflight["why_blocked"]
        with pytest.raises(RuntimeError, match="STATE_DIVERGENCE"):
            operator.play("SHADOW")
    finally:
        operator.delete_credentials()
        operator.close()


class _Client:
    def __init__(self, origin: str) -> None:
        self.origin = origin
        self.cookie = ""
        self.csrf = ""

    def request(
        self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any], Any]:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Accept": "application/json"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        if method != "GET":
            headers["Origin"] = self.origin
            headers["X-Operator-CSRF"] = self.csrf
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.origin + path, data=data, headers=headers, method=method
        )
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        payload = json.loads(response.read())
        return response.status, payload, response.headers

    def bootstrap(self) -> None:
        status, payload, headers = self.request("/api/bootstrap")
        assert status == 200
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = payload["csrf_token"]


@pytest.fixture
def http_operator(service: OperatorService) -> tuple[_Client, Any]:
    server = create_server(service, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = _Client(server.origin)
    client.bootstrap()
    yield client, server
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_http_is_loopback_csrf_protected_and_has_strict_headers(
    http_operator: tuple[_Client, Any],
) -> None:
    client, server = http_operator
    assert server.server_address[0] == LOOPBACK_HOST
    status, payload, headers = client.request("/api/status")
    assert status == 200
    assert payload["mode"] == "SHADOW"
    assert "unsafe-inline" not in headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]

    csrf = client.csrf
    client.csrf = "wrong"
    status, payload, _headers = client.request("/api/operator/stop", method="POST")
    assert status == 403
    assert payload["error"] == "CSRF_TOKEN_INVALID"
    client.csrf = csrf


@pytest.mark.skipif(__import__("os").name != "nt", reason="DPAPI is a Windows authority")
def test_secret_never_appears_in_get_response_or_journal(
    http_operator: tuple[_Client, Any], service: OperatorService
) -> None:
    client, _server = http_operator
    key = "browser-fixture-key-ABCD"
    sensitive = "browser-fixture-private-value-QWER"
    status, payload, _headers = client.request(
        "/api/binance/configure",
        method="POST",
        body={"api_key": key, "api_secret": sensitive},
    )
    assert status == 200
    assert payload["secret_configured"] is True
    for path in ("/api/dashboard", "/api/status", "/api/connection", "/health"):
        status, payload, _headers = client.request(path)
        assert status == 200
        encoded = json.dumps(payload)
        assert key not in encoded
        assert sensitive not in encoded
    assert key not in service.store.journal_path.read_text(encoding="utf-8")
    assert sensitive not in service.store.journal_path.read_text(encoding="utf-8")

    status, payload, _headers = client.request("/api/binance/credentials", method="DELETE")
    assert status == 200
    assert payload["secret_configured"] is False


def test_live_withdraw_and_unknown_routes_fail_closed(http_operator: tuple[_Client, Any]) -> None:
    client, _server = http_operator
    status, payload, _headers = client.request(
        "/api/operator/play", method="POST", body={"mode": "LIVE"}
    )
    assert status == 403
    assert "SHADOW_ONLY" in payload["error"]
    for method in ("GET", "POST", "DELETE"):
        status, _payload, _headers = client.request("/api/withdraw", method=method)
        assert status == 404


def test_frontend_has_no_secret_storage_or_unsafe_dom_sinks() -> None:
    static = Path("src/crypto_strategy_lab/operator_dashboard/static")
    source = "\n".join(path.read_text(encoding="utf-8") for path in static.iterdir())
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert ".innerHTML" not in source
    assert "insertAdjacentHTML" not in source
    assert "unsafe-inline" not in source
    assert "https://" not in source


def test_order_and_withdraw_transports_do_not_exist() -> None:
    module = Path("src/crypto_strategy_lab/operator_dashboard/binance.py").read_text(
        encoding="utf-8"
    )
    assert '"/api/v3/order"' not in module
    assert '"/sapi/v1/capital/withdraw/apply"' not in module
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    assert "/runtime/" in gitignore
    assert "*.dpapi" in gitignore
