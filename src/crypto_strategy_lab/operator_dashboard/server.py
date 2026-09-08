"""Loopback-only HTTP server for the CryptoChange operator cockpit."""

from __future__ import annotations

import json
import mimetypes
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import parse_qs, urlparse

from crypto_strategy_lab.operator_dashboard.security import new_token, redact
from crypto_strategy_lab.operator_dashboard.service import OperatorService
from crypto_strategy_lab.operator_dashboard.vault import CredentialVaultUnavailable

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_BODY_BYTES = 32_768


class SingleInstanceError(RuntimeError):
    pass


class SingleInstanceLock:
    """Process-scoped lock backed by a one-byte Windows file lock."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self._file: BinaryIO | None = None

    def acquire(self) -> None:
        if os.name != "nt":
            raise SingleInstanceError("WINDOWS_SINGLE_INSTANCE_LOCK_REQUIRED")
        import msvcrt

        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = self.path.open("a+b")
        except PermissionError as error:
            raise SingleInstanceError("OPERATOR_INSTANCE_ALREADY_RUNNING") from error
        try:
            handle.seek(0)
            if handle.read(1) == b"":
                handle.seek(0)
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
        except PermissionError as error:
            handle.close()
            raise SingleInstanceError("OPERATOR_INSTANCE_ALREADY_RUNNING") from error
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            handle.close()
            raise SingleInstanceError("OPERATOR_INSTANCE_ALREADY_RUNNING") from error
        self._file = handle

    def release(self) -> None:
        if self._file is None:
            return
        import msvcrt

        self._file.seek(0)
        try:
            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self._file.close()
            self._file = None

    def __enter__(self) -> SingleInstanceLock:
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


class OperatorHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        server_address: tuple[str, int],
        service: OperatorService,
        static_root: Path,
    ) -> None:
        if server_address[0] != LOOPBACK_HOST:
            raise ValueError("LOCALHOST_BIND_REQUIRED")
        self.service = service
        self.static_root = static_root.resolve()
        self.sessions: dict[str, str] = {}
        self.sessions_lock = threading.Lock()
        super().__init__(server_address, OperatorRequestHandler)

    @property
    def origin(self) -> str:
        return f"http://{LOOPBACK_HOST}:{self.server_port}"

    def new_session(self) -> tuple[str, str]:
        session_id, csrf = new_token(), new_token()
        with self.sessions_lock:
            self.sessions[session_id] = csrf
            if len(self.sessions) > 32:
                self.sessions.pop(next(iter(self.sessions)))
        return session_id, csrf

    def csrf_for(self, session_id: str) -> str | None:
        with self.sessions_lock:
            return self.sessions.get(session_id)


class OperatorRequestHandler(BaseHTTPRequestHandler):
    server: OperatorHttpServer
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        # Request URLs and headers are never copied into logs. Structured events are
        # written through OperatorStore after redaction.
        return

    def _security_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'",
        )

    def _send_bytes(
        self,
        payload: bytes,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str = "application/json; charset=utf-8",
        cookie: str | None = None,
    ) -> None:
        self.send_response(status)
        self._security_headers(content_type)
        if cookie:
            self.send_header(
                "Set-Cookie",
                f"operator_session={cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200",
            )
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(
        self,
        payload: Any,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        cookie: str | None = None,
    ) -> None:
        encoded = json.dumps(redact(payload), sort_keys=True, separators=(",", ":")).encode()
        self._send_bytes(encoded, status=status, cookie=cookie)

    def _cookies(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for part in self.headers.get("Cookie", "").split(";"):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                values[key] = value
        return values

    def _host_valid(self) -> bool:
        return self.headers.get("Host") == f"{LOOPBACK_HOST}:{self.server.server_port}"

    def _session(self) -> tuple[str | None, str | None]:
        session_id = self._cookies().get("operator_session")
        return session_id, self.server.csrf_for(session_id) if session_id else None

    def _require_read_session(self) -> bool:
        if not self._host_valid():
            self._json({"error": "INVALID_HOST"}, status=HTTPStatus.FORBIDDEN)
            return False
        session_id, csrf = self._session()
        if not session_id or not csrf:
            self._json({"error": "SESSION_REQUIRED"}, status=HTTPStatus.UNAUTHORIZED)
            return False
        return True

    def _require_write_session(self) -> bool:
        if not self._require_read_session():
            return False
        _session_id, expected = self._session()
        if self.headers.get("Origin") != self.server.origin:
            self._json({"error": "LOCAL_ORIGIN_REQUIRED"}, status=HTTPStatus.FORBIDDEN)
            return False
        if not expected or self.headers.get("X-Operator-CSRF") != expected:
            self._json({"error": "CSRF_TOKEN_INVALID"}, status=HTTPStatus.FORBIDDEN)
            return False
        return True

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("INVALID_CONTENT_LENGTH") from error
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("INVALID_BODY_SIZE")
        if self.headers.get_content_type() != "application/json":
            raise ValueError("JSON_CONTENT_TYPE_REQUIRED")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("JSON_OBJECT_REQUIRED")
        return payload

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            if not self._host_valid():
                self._json({"error": "INVALID_HOST"}, status=HTTPStatus.FORBIDDEN)
                return
            self._static("index.html")
            return
        if parsed.path.startswith("/assets/"):
            if not self._host_valid():
                self._json({"error": "INVALID_HOST"}, status=HTTPStatus.FORBIDDEN)
                return
            self._static(parsed.path.removeprefix("/assets/"))
            return
        if parsed.path == "/health":
            if not self._host_valid():
                self._json({"error": "INVALID_HOST"}, status=HTTPStatus.FORBIDDEN)
                return
            self._json(self.server.service.health())
            return
        if parsed.path == "/api/bootstrap":
            if not self._host_valid():
                self._json({"error": "INVALID_HOST"}, status=HTTPStatus.FORBIDDEN)
                return
            session_id, csrf = self.server.new_session()
            self._json(
                {"csrf_token": csrf, "origin": self.server.origin, "live_trading_enabled": False},
                cookie=session_id,
            )
            return
        if not parsed.path.startswith("/api/") or not self._require_read_session():
            if not parsed.path.startswith("/api/"):
                self._json({"error": "NOT_FOUND"}, status=HTTPStatus.NOT_FOUND)
            return
        query = parse_qs(parsed.query)
        routes: dict[str, Any] = {
            "/api/dashboard": self.server.service.dashboard,
            "/api/status": self.server.service.status,
            "/api/capital": self.server.service.capital,
            "/api/reserve": self.server.service.reserve,
            "/api/queues": self.server.service.queues,
            "/api/orders": self.server.service.orders,
            "/api/events": lambda: self.server.service.events(int(query.get("limit", ["100"])[0])),
            "/api/market": self.server.service.market,
            "/api/strategy": self.server.service.strategy,
            "/api/connection": self.server.service.connection,
            "/api/preflight": self.server.service.preflight,
        }
        handler = routes.get(parsed.path)
        if handler is None:
            self._json({"error": "NOT_FOUND"}, status=HTTPStatus.NOT_FOUND)
            return
        try:
            self._json(handler())
        except (ValueError, RuntimeError) as error:
            self._json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)

    def _static(self, relative: str) -> None:
        target = (self.server.static_root / relative).resolve()
        if self.server.static_root not in target.parents or not target.is_file():
            self._json({"error": "NOT_FOUND"}, status=HTTPStatus.NOT_FOUND)
            return
        payload = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send_bytes(payload, content_type=f"{content_type}; charset=utf-8")

    def do_POST(self) -> None:
        self._write_request("POST")

    def do_DELETE(self) -> None:
        self._write_request("DELETE")

    def _write_request(self, method: str) -> None:
        parsed = urlparse(self.path)
        if parsed.query:
            self._json({"error": "QUERY_STRING_FORBIDDEN"}, status=HTTPStatus.BAD_REQUEST)
            return
        if not self._require_write_session():
            return
        try:
            if method == "POST" and parsed.path == "/api/binance/configure":
                body = self._body()
                api_key = body.get("api_key")
                api_secret = body.get("api_secret")
                if not isinstance(api_key, str) or not isinstance(api_secret, str):
                    raise ValueError("API_KEY_AND_SECRET_REQUIRED")
                result = self.server.service.configure_credentials(api_key, api_secret)
            elif method == "POST" and parsed.path == "/api/binance/test":
                result = self.server.service.test_connection()
            elif method == "POST" and parsed.path == "/api/binance/disconnect":
                result = self.server.service.disconnect()
            elif method == "DELETE" and parsed.path == "/api/binance/credentials":
                result = self.server.service.delete_credentials()
            elif method == "POST" and parsed.path == "/api/operator/play":
                body = self._body()
                result = self.server.service.play(str(body.get("mode", "")))
            elif method == "POST" and parsed.path == "/api/operator/stop":
                result = self.server.service.stop()
            elif method == "POST" and parsed.path == "/api/operator/emergency-stop":
                body = self._body()
                result = self.server.service.emergency_stop(str(body.get("confirmation", "")))
            elif method == "POST" and parsed.path == "/api/operator/reconcile":
                result = self.server.service.reconcile()
            elif method == "POST" and parsed.path == "/api/assistant":
                body = self._body()
                result = self.server.service.assistant(str(body.get("question", "")))
            else:
                self._json({"error": "NOT_FOUND"}, status=HTTPStatus.NOT_FOUND)
                return
            self._json(result)
        except PermissionError as error:
            self._json({"error": str(error)}, status=HTTPStatus.FORBIDDEN)
        except (ValueError, RuntimeError, CredentialVaultUnavailable) as error:
            self._json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)


def create_server(
    service: OperatorService,
    *,
    port: int = DEFAULT_PORT,
    static_root: Path | None = None,
) -> OperatorHttpServer:
    assets = static_root or Path(__file__).with_name("static")
    return OperatorHttpServer((LOOPBACK_HOST, port), service, assets)


def serve_dashboard(
    root: Path,
    *,
    port: int = DEFAULT_PORT,
    demo: bool = False,
    open_browser: bool = True,
) -> None:
    lock = SingleInstanceLock(root / "runtime/operator.lock")
    with lock:
        service = OperatorService(root, demo=demo)
        server = create_server(service, port=port)
        url = server.origin
        print(f"CryptoChange operator dashboard: {url}", flush=True)
        print("SHADOW ONLY | LIVE_TRADING_ENABLED=NO | Ctrl+C to stop", flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
            service.close()
