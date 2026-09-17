"""Small DB-API persistence layer for PostgreSQL and local SQLite tests."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS tenants (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        username TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'viewer',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS licenses (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        license_key TEXT NOT NULL UNIQUE,
        games_json TEXT NOT NULL DEFAULT '[]',
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS live_sessions (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        game_id TEXT,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS listeners (
        tenant_id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        session_id TEXT,
        status TEXT NOT NULL,
        last_error TEXT,
        started_at TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS event_outbox (
        event_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'accepted',
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_errors (
        id INTEGER PRIMARY KEY,
        component TEXT NOT NULL,
        message TEXT NOT NULL,
        context_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS worker_heartbeats (
        id INTEGER PRIMARY KEY,
        worker_id TEXT NOT NULL,
        pid INTEGER,
        updated_at TEXT NOT NULL
    )
    """,
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, url: str):
        self.url = url
        parsed = urlparse(url)
        if parsed.scheme in {"sqlite", ""}:
            self.backend = "sqlite"
            if url in {"sqlite:///:memory:", ":memory:"}:
                self.path = ":memory:"
            else:
                self.path = parsed.path or url.removeprefix("sqlite:///")
        elif parsed.scheme in {"postgresql", "postgres"}:
            self.backend = "postgresql"
            self.path = None
        else:
            raise ValueError(f"unsupported database URL: {url}")

    def _connect(self):
        if self.backend == "sqlite":
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            return connection
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is required for PostgreSQL DATABASE_URL") from exc
        return psycopg.connect(self.url)

    @contextmanager
    def connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _sql(self, query: str) -> str:
        return query.replace("?", "%s") if self.backend == "postgresql" else query

    @staticmethod
    def _as_dict(cursor, row):
        if row is None:
            return None
        if isinstance(row, dict):
            return row
        return dict(zip((column[0] for column in cursor.description), row))

    def execute(self, query: str, params=()):
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(self._sql(query), params)
            return cursor.rowcount

    def fetchone(self, query: str, params=()):
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(self._sql(query), params)
            row = cursor.fetchone()
            return self._as_dict(cursor, row)

    def fetchall(self, query: str, params=()):
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(self._sql(query), params)
            rows = cursor.fetchall()
            return [self._as_dict(cursor, row) for row in rows]

    def initialize(self):
        with self.connection() as connection:
            cursor = connection.cursor()
            for statement in SCHEMA:
                cursor.execute(statement)

    def ping(self):
        return self.fetchone("SELECT 1") is not None

    def record_error(self, component: str, message: str, context: dict | None = None):
        self.execute(
            "INSERT INTO runtime_errors (component, message, context_json, created_at) VALUES (?, ?, ?, ?)",
            (component, message[:2000], json.dumps(context or {}), now()),
        )

    def recent_errors(self, limit: int = 20):
        return self.fetchall(
            "SELECT component, message, context_json, created_at FROM runtime_errors ORDER BY id DESC LIMIT ?",
            (max(1, min(limit, 100)),),
        )

    def upsert_tenant(self, tenant_id: str, username: str):
        timestamp = now()
        if self.backend == "postgresql":
            query = """INSERT INTO tenants (id, username, created_at) VALUES (?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET username = EXCLUDED.username, enabled = 1"""
        else:
            query = """INSERT INTO tenants (id, username, created_at) VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET username=excluded.username, enabled=1"""
        self.execute(query, (tenant_id, username, timestamp))

    def upsert_license(self, license_id: str, tenant_id: str, key: str, games: list[str]):
        timestamp = now()
        if self.backend == "postgresql":
            query = """INSERT INTO licenses (id, tenant_id, license_key, games_json, created_at)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET tenant_id=EXCLUDED.tenant_id,
                license_key=EXCLUDED.license_key, games_json=EXCLUDED.games_json, enabled=1"""
        else:
            query = """INSERT INTO licenses (id, tenant_id, license_key, games_json, created_at)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET tenant_id=excluded.tenant_id,
                license_key=excluded.license_key, games_json=excluded.games_json, enabled=1"""
        self.execute(query, (license_id, tenant_id, key, json.dumps(games), timestamp))

    def upsert_user(self, user_id: str, tenant_id: str, username: str, role: str = "owner"):
        self.execute(
            "INSERT INTO users (id, tenant_id, username, role, created_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET tenant_id=excluded.tenant_id, username=excluded.username, role=excluded.role",
            (user_id, tenant_id, username, role, now()),
        )

    def license_for(self, tenant_id: str, key: str):
        row = self.fetchone(
            "SELECT tenant_id, license_key, games_json FROM licenses WHERE tenant_id = ? AND license_key = ? AND enabled = 1",
            (tenant_id, key),
        )
        if not row:
            return None
        row["games"] = json.loads(row.pop("games_json"))
        return row

    def save_session(self, session_id: str, tenant_id: str, game_id: str | None):
        self.execute(
            "INSERT INTO live_sessions (id, tenant_id, game_id, status, started_at) VALUES (?, ?, ?, 'active', ?) ON CONFLICT(id) DO NOTHING",
            (session_id, tenant_id, game_id, now()),
        )

    def save_listener(self, tenant_id: str, username: str, session_id: str, status: str):
        timestamp = now()
        if self.backend == "postgresql":
            query = """INSERT INTO listeners (tenant_id, username, session_id, status, started_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (tenant_id) DO UPDATE SET username=EXCLUDED.username,
                session_id=EXCLUDED.session_id, status=EXCLUDED.status, updated_at=EXCLUDED.updated_at"""
        else:
            query = """INSERT INTO listeners (tenant_id, username, session_id, status, started_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(tenant_id) DO UPDATE SET username=excluded.username,
                session_id=excluded.session_id, status=excluded.status, updated_at=excluded.updated_at"""
        self.execute(query, (tenant_id, username, session_id, status, timestamp, timestamp))

    def update_listener(self, tenant_id: str, status: str, error: str | None = None):
        self.execute(
            "UPDATE listeners SET status = ?, last_error = ?, updated_at = ? WHERE tenant_id = ?",
            (status, error, now(), tenant_id),
        )

    def listeners(self):
        rows = self.fetchall("SELECT * FROM listeners ORDER BY tenant_id")
        return rows

    def record_event(self, event: dict):
        payload = json.dumps(event.get("payload") or {})
        return self.execute(
            "INSERT INTO event_outbox (event_id, tenant_id, session_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(event_id) DO NOTHING",
            (event["event_id"], event["tenant_id"], event["session_id"], event["type"], payload, now()),
        )

    def heartbeat_worker(self, worker_id: str, pid: int | None = None):
        timestamp = now()
        self.execute(
            "INSERT INTO worker_heartbeats (id, worker_id, pid, updated_at) VALUES (1, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET worker_id=excluded.worker_id, pid=excluded.pid, updated_at=excluded.updated_at",
            (worker_id, pid, timestamp),
        )

    def worker_heartbeat(self, timeout_seconds: float):
        row = self.fetchone("SELECT worker_id, pid, updated_at FROM worker_heartbeats WHERE id = 1")
        if not row:
            return {"ok": False, "worker_id": None, "pid": None, "updated_at": None}
        try:
            updated = datetime.fromisoformat(row["updated_at"])
            age = max(0.0, (datetime.now(timezone.utc) - updated).total_seconds())
        except (TypeError, ValueError):
            age = float("inf")
        return {**row, "age_seconds": age, "ok": age <= timeout_seconds}

    def session_summary(self):
        rows = self.fetchall("SELECT status, COUNT(*) AS count FROM live_sessions GROUP BY status")
        return {row["status"]: row["count"] for row in rows}
