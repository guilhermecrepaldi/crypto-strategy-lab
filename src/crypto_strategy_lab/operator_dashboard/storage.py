"""SQLite state authority plus an append-only, redacted local runtime journal."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_strategy_lab.operator_dashboard.security import redact


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class OperatorStore:
    def __init__(self, database_path: Path, journal_path: Path) -> None:
        self.database_path = database_path
        self.journal_path = journal_path
        self._lock = threading.RLock()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def set_metadata(self, key: str, value: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO metadata(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_metadata(self, key: str, default: str = "") -> str:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def append_event(self, event: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        timestamp = utc_now()
        safe_details = redact(details or {})
        encoded = json.dumps(safe_details, sort_keys=True, separators=(",", ":"))
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO events(timestamp,event,details_json) VALUES(?,?,?)",
                (timestamp, event, encoded),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("EVENT_ID_NOT_CREATED")
            event_id = cursor.lastrowid
            record = {
                "id": event_id,
                "timestamp": timestamp,
                "event": event,
                "details": safe_details,
            }
            with self.journal_path.open("a", encoding="utf-8", newline="\n") as journal:
                journal.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        return record

    def events(self, limit: int = 100) -> list[dict[str, Any]]:
        bounded = max(1, min(limit, 500))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT id,timestamp,event,details_json FROM events ORDER BY id DESC LIMIT ?",
                (bounded,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "timestamp": row["timestamp"],
                "event": row["event"],
                "details": json.loads(row["details_json"]),
            }
            for row in rows
        ]

    def add_snapshot(self, payload: dict[str, Any]) -> None:
        safe = redact(payload)
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO snapshots(timestamp,payload_json) VALUES(?,?)",
                (utc_now(), json.dumps(safe, sort_keys=True, separators=(",", ":"))),
            )
            connection.execute(
                "DELETE FROM snapshots WHERE id NOT IN "
                "(SELECT id FROM snapshots ORDER BY id DESC LIMIT 1000)"
            )

    def snapshots(self, limit: int = 120) -> list[dict[str, Any]]:
        bounded = max(1, min(limit, 1000))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT timestamp,payload_json FROM snapshots ORDER BY id DESC LIMIT ?",
                (bounded,),
            ).fetchall()
        return [
            {"timestamp": row["timestamp"], **json.loads(row["payload_json"])}
            for row in reversed(rows)
        ]

    def orders(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM orders ORDER BY timestamp DESC LIMIT 200"
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]
