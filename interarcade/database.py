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
    CREATE TABLE IF NOT EXISTS live_sources (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        platform TEXT NOT NULL,
        account_id TEXT NOT NULL,
        username TEXT NOT NULL,
        status TEXT NOT NULL,
        last_error TEXT,
        started_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (session_id, platform, account_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS live_sources_session_idx ON live_sources (session_id, status)",
    """
    CREATE TABLE IF NOT EXISTS event_outbox (
        event_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        envelope_json TEXT,
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
    """
    CREATE TABLE IF NOT EXISTS marble_rounds (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        round_number INTEGER NOT NULL,
        status TEXT NOT NULL,
        config_json TEXT NOT NULL,
        gift_score INTEGER NOT NULL DEFAULT 0,
        like_score INTEGER NOT NULL DEFAULT 0,
        winner TEXT,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        updated_at TEXT NOT NULL,
        UNIQUE (session_id, round_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dark_runs (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL UNIQUE,
        level INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL,
        player_x INTEGER NOT NULL,
        player_y INTEGER NOT NULL,
        moves INTEGER NOT NULL DEFAULT 0,
        started_at TEXT NOT NULL,
        completed_at TEXT,
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
            if self.backend == "postgresql":
                # API and worker start together. Serialize idempotent DDL because
                # PostgreSQL can still race on catalog rows with IF NOT EXISTS.
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext('interarcade_schema_v2'))")
            for statement in SCHEMA:
                cursor.execute(statement)
            if self.backend == "postgresql":
                cursor.execute("ALTER TABLE event_outbox ADD COLUMN IF NOT EXISTS envelope_json TEXT")
            else:
                cursor.execute("PRAGMA table_info(event_outbox)")
                if "envelope_json" not in {row[1] for row in cursor.fetchall()}:
                    cursor.execute("ALTER TABLE event_outbox ADD COLUMN envelope_json TEXT")
            # Additive migration: keep the legacy table and copy its last state.
            cursor.execute(
                "INSERT INTO live_sources (id, tenant_id, session_id, platform, account_id, username, "
                "status, last_error, started_at, updated_at) "
                "SELECT 'legacy:tiktok:' || tenant_id, tenant_id, session_id, 'tiktok', username, username, "
                "status, last_error, COALESCE(started_at, updated_at), updated_at "
                "FROM listeners WHERE session_id IS NOT NULL ON CONFLICT DO NOTHING"
            )
            if self.backend == "postgresql":
                # PostgreSQL does not auto-increment an ``INTEGER PRIMARY KEY``.
                # Keep the existing table compatible and give new rows a safe id.
                cursor.execute("CREATE SEQUENCE IF NOT EXISTS runtime_errors_id_seq")
                cursor.execute(
                    "SELECT setval('runtime_errors_id_seq', "
                    "COALESCE((SELECT MAX(id) FROM runtime_errors), 0) + 1, false)"
                )
                cursor.execute(
                    "ALTER TABLE runtime_errors ALTER COLUMN id "
                    "SET DEFAULT nextval('runtime_errors_id_seq')"
                )
                cursor.execute(
                    "ALTER SEQUENCE runtime_errors_id_seq OWNED BY runtime_errors.id"
                )

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

    def end_session(self, session_id: str):
        timestamp = now()
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(self._sql("UPDATE live_sessions SET status = 'ended', ended_at = ? WHERE id = ? AND status = 'active'"), (timestamp, session_id))
            cursor.execute(self._sql("UPDATE marble_rounds SET status = 'ended', ended_at = ?, updated_at = ? WHERE session_id = ? AND status = 'active'"), (timestamp, timestamp, session_id))
            cursor.execute(
                self._sql(
                    "UPDATE dark_runs SET status = 'ended', completed_at = ?, updated_at = ? "
                    "WHERE session_id = ? AND status = 'active'"
                ),
                (timestamp, timestamp, session_id),
            )
            cursor.execute(
                self._sql(
                    "UPDATE live_sources SET status = CASE WHEN status = 'simulated' THEN 'stopped' "
                    "ELSE 'stopping' END, updated_at = ? WHERE session_id = ? "
                    "AND status IN ('starting', 'running', 'simulated')"
                ),
                (timestamp, session_id),
            )

    def session(self, session_id: str):
        return self.fetchone("SELECT * FROM live_sessions WHERE id = ?", (session_id,))

    def start_marble_round(self, round_id: str, session_id: str, config: dict, reset: bool = False):
        current = self.marble_round(session_id)
        if current and current["status"] == "active" and not reset:
            return current
        if current and current["status"] == "active" and reset:
            timestamp = now()
            self.execute(
                "UPDATE marble_rounds SET status = 'ended', ended_at = ?, updated_at = ? WHERE id = ? AND status = 'active'",
                (timestamp, timestamp, current["id"]),
            )
        next_number = int(current["round_number"]) + 1 if current else 1
        timestamp = now()
        self.execute(
            "INSERT INTO marble_rounds (id, session_id, round_number, status, config_json, started_at, updated_at) "
            "VALUES (?, ?, ?, 'active', ?, ?, ?)",
            (round_id, session_id, next_number, json.dumps(config), timestamp, timestamp),
        )
        return self.marble_round(session_id)

    def marble_round(self, session_id: str):
        row = self.fetchone(
            "SELECT * FROM marble_rounds WHERE session_id = ? ORDER BY round_number DESC LIMIT 1",
            (session_id,),
        )
        if row:
            row["config"] = json.loads(row.pop("config_json"))
        return row

    def start_dark_run(self, run_id: str, session_id: str, reset: bool = False):
        from .games.dark import initial_state

        current = self.dark_run(session_id)
        if current and not reset:
            return current
        state = initial_state()
        timestamp = now()
        if current:
            self.execute(
                "UPDATE dark_runs SET level = ?, status = ?, player_x = ?, player_y = ?, "
                "moves = ?, started_at = ?, completed_at = NULL, updated_at = ? WHERE session_id = ?",
                (
                    state["level"],
                    state["status"],
                    state["player_x"],
                    state["player_y"],
                    state["moves"],
                    timestamp,
                    timestamp,
                    session_id,
                ),
            )
        else:
            self.execute(
                "INSERT INTO dark_runs (id, session_id, level, status, player_x, player_y, "
                "moves, started_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    session_id,
                    state["level"],
                    state["status"],
                    state["player_x"],
                    state["player_y"],
                    state["moves"],
                    timestamp,
                    timestamp,
                ),
            )
        return self.dark_run(session_id)

    def dark_run(self, session_id: str):
        return self.fetchone("SELECT * FROM dark_runs WHERE session_id = ?", (session_id,))

    def move_dark(self, session_id: str, direction: str):
        from .games.dark import apply_move

        with self.connection() as connection:
            cursor = connection.cursor()
            query = "SELECT * FROM dark_runs WHERE session_id = ?"
            if self.backend == "postgresql":
                query += " FOR UPDATE"
            cursor.execute(self._sql(query), (session_id,))
            current = self._as_dict(cursor, cursor.fetchone())
            if not current:
                return None, None
            next_state, outcome = apply_move(current, direction)
            if next_state != current:
                completed_at = now() if next_state["status"] == "finished" else None
                cursor.execute(
                    self._sql(
                        "UPDATE dark_runs SET level = ?, status = ?, player_x = ?, player_y = ?, "
                        "moves = ?, completed_at = ?, updated_at = ? WHERE session_id = ?"
                    ),
                    (
                        next_state["level"],
                        next_state["status"],
                        next_state["player_x"],
                        next_state["player_y"],
                        next_state["moves"],
                        completed_at,
                        now(),
                        session_id,
                    ),
                )
            return next_state, outcome

    def apply_marble_event(self, event: dict, config: dict):
        """Atomically accept an event and update the current Marble round."""
        from .games.marble import MarbleConfig, apply_event

        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(self._sql(
                "INSERT INTO event_outbox (event_id, tenant_id, session_id, event_type, payload_json, "
                "envelope_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(event_id) DO NOTHING"
            ), (
                event["event_id"], event["tenant_id"], event["session_id"], event["type"],
                json.dumps(event.get("payload") or {}), json.dumps(event), now(),
            ))
            accepted = cursor.rowcount == 1
            query = "SELECT * FROM marble_rounds WHERE session_id = ? ORDER BY round_number DESC LIMIT 1"
            if self.backend == "postgresql":
                query += " FOR UPDATE"
            cursor.execute(self._sql(query), (event["session_id"],))
            row = cursor.fetchone()
            state = self._as_dict(cursor, row)
            if not state:
                return accepted, None
            state["config"] = json.loads(state.pop("config_json"))
            if accepted:
                next_state = apply_event(state, event, MarbleConfig.from_mapping(config))
                ended_at = now() if next_state["status"] == "finished" and state["status"] == "active" else state.get("ended_at")
                cursor.execute(self._sql(
                    "UPDATE marble_rounds SET status = ?, gift_score = ?, like_score = ?, winner = ?, ended_at = ?, updated_at = ? WHERE id = ?"
                ), (next_state["status"], next_state["gift_score"], next_state["like_score"], next_state.get("winner"), ended_at, now(), state["id"]))
                state = next_state
                state["ended_at"] = ended_at
            return accepted, state

    def live_source(self, source_id: str):
        return self.fetchone("SELECT * FROM live_sources WHERE id = ?", (source_id,))

    def live_source_for_session(self, session_id: str, platform: str, account_id: str):
        return self.fetchone(
            "SELECT * FROM live_sources WHERE session_id = ? AND platform = ? AND account_id = ?",
            (session_id, platform, account_id),
        )

    def live_sources(self, session_id: str | None = None):
        if session_id is None:
            return self.fetchall("SELECT * FROM live_sources ORDER BY updated_at DESC, id")
        return self.fetchall(
            "SELECT * FROM live_sources WHERE session_id = ? ORDER BY updated_at DESC, id", (session_id,)
        )

    def save_live_source(
        self, source_id: str, tenant_id: str, session_id: str, platform: str,
        account_id: str, username: str, status: str,
    ):
        timestamp = now()
        self.execute(
            "INSERT INTO live_sources (id, tenant_id, session_id, platform, account_id, username, "
            "status, started_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET tenant_id=excluded.tenant_id, "
            "session_id=excluded.session_id, platform=excluded.platform, "
            "account_id=excluded.account_id, username=excluded.username, status=excluded.status, "
            "last_error=NULL, updated_at=excluded.updated_at",
            (source_id, tenant_id, session_id, platform, account_id, username, status, timestamp, timestamp),
        )
        return self.live_source(source_id)

    def update_live_source(self, source_id: str, status: str, error: str | None = None):
        self.execute(
            "UPDATE live_sources SET status = ?, last_error = ?, updated_at = ? WHERE id = ?",
            (status, error, now(), source_id),
        )

    def save_listener(self, tenant_id: str, username: str, session_id: str, status: str):
        current = self.live_source_for_session(session_id, "tiktok", username)
        return self.save_live_source(
            current["id"] if current else f"legacy:tiktok:{tenant_id}:{session_id}",
            tenant_id, session_id, "tiktok", username, username, status,
        )

    def update_listener(self, tenant_id: str, status: str, error: str | None = None):
        source = next((row for row in self.listeners() if row["tenant_id"] == tenant_id), None)
        if source:
            self.update_live_source(source["id"], status, error)

    def listeners(self):
        return [row for row in self.live_sources() if row["platform"] == "tiktok"]

    def record_event(self, event: dict):
        payload = json.dumps(event.get("payload") or {})
        return self.execute(
            "INSERT INTO event_outbox (event_id, tenant_id, session_id, event_type, payload_json, "
            "envelope_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(event_id) DO NOTHING",
            (event["event_id"], event["tenant_id"], event["session_id"], event["type"], payload, json.dumps(event), now()),
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
