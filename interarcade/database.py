"""Small DB-API persistence layer for PostgreSQL and local SQLite tests."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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
    CREATE TABLE IF NOT EXISTS creator_accounts (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS creator_logins (
        token_hash TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        csrf_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS creator_logins_account_idx ON creator_logins (account_id)",
    """
    CREATE TABLE IF NOT EXISTS auth_rate_limits (
        key_hash TEXT PRIMARY KEY,
        window_start TEXT NOT NULL,
        attempts INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS auth_rate_limits_window_idx ON auth_rate_limits (window_start)",
    """
    CREATE TABLE IF NOT EXISTS creator_platform_accounts (
        account_id TEXT NOT NULL,
        platform TEXT NOT NULL,
        source_account_id TEXT NOT NULL,
        username TEXT NOT NULL,
        configured_at TEXT NOT NULL,
        PRIMARY KEY (account_id, platform, source_account_id)
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
    """
    CREATE TABLE IF NOT EXISTS dark_live_like_progress (
        session_id TEXT NOT NULL,
        source_platform TEXT NOT NULL,
        source_account_id TEXT NOT NULL,
        total_count INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (session_id, source_platform, source_account_id)
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
                cursor.execute("ALTER TABLE live_sessions ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'live'")
                cursor.execute("ALTER TABLE live_sessions ADD COLUMN IF NOT EXISTS last_seen_at TEXT")
            else:
                cursor.execute("PRAGMA table_info(event_outbox)")
                if "envelope_json" not in {row[1] for row in cursor.fetchall()}:
                    cursor.execute("ALTER TABLE event_outbox ADD COLUMN envelope_json TEXT")
                cursor.execute("PRAGMA table_info(live_sessions)")
                if "mode" not in {row[1] for row in cursor.fetchall()}:
                    cursor.execute("ALTER TABLE live_sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'live'")
                cursor.execute("PRAGMA table_info(live_sessions)")
                if "last_seen_at" not in {row[1] for row in cursor.fetchall()}:
                    cursor.execute("ALTER TABLE live_sessions ADD COLUMN last_seen_at TEXT")
            cursor.execute("UPDATE live_sessions SET last_seen_at = started_at WHERE last_seen_at IS NULL")
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

    def entitled_games(self, tenant_id: str):
        rows = self.fetchall(
            "SELECT games_json FROM licenses WHERE tenant_id = ? AND enabled = 1", (tenant_id,)
        )
        return sorted({game for row in rows for game in json.loads(row["games_json"])})

    def create_creator_account(self, account_id: str, tenant_id: str, email: str, password_hash: str):
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(self._sql(
                "INSERT INTO tenants (id, username, created_at) VALUES (?, ?, ?)"
            ), (tenant_id, f"creator-{account_id}", now()))
            cursor.execute(self._sql(
                "INSERT INTO creator_accounts (id, tenant_id, email, password_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(email) DO NOTHING"
            ), (account_id, tenant_id, email, password_hash, now()))
            if cursor.rowcount != 1:
                raise ValueError("email_already_registered")
            cursor.execute(self._sql(
                "INSERT INTO users (id, tenant_id, username, role, created_at) "
                "VALUES (?, ?, ?, 'owner', ?)"
            ), (account_id, tenant_id, email, now()))

    def creator_account_by_email(self, email: str):
        return self.fetchone("SELECT * FROM creator_accounts WHERE email = ?", (email,))

    def creator_account(self, account_id: str):
        return self.fetchone("SELECT * FROM creator_accounts WHERE id = ?", (account_id,))

    def save_creator_login(self, token_hash: str, account_id: str, csrf_hash: str, expires_at: str):
        self.execute(
            "INSERT INTO creator_logins (token_hash, account_id, csrf_hash, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (token_hash, account_id, csrf_hash, expires_at, now()),
        )

    def creator_login(self, token_hash: str):
        return self.fetchone(
            "SELECT * FROM creator_logins WHERE token_hash = ? AND revoked_at IS NULL",
            (token_hash,),
        )

    def revoke_creator_login(self, token_hash: str):
        self.execute("UPDATE creator_logins SET revoked_at = ? WHERE token_hash = ?", (now(), token_hash))

    def consume_auth_limit(self, key_hash: str, limit: int, window_seconds: int) -> bool:
        """Count an authentication attempt atomically across API processes."""
        timestamp = datetime.now(timezone.utc)
        start = timestamp.isoformat()
        cutoff = (timestamp - timedelta(seconds=window_seconds)).isoformat()
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(self._sql(
                "INSERT INTO auth_rate_limits (key_hash, window_start, attempts) VALUES (?, ?, 1) "
                "ON CONFLICT(key_hash) DO UPDATE SET "
                "attempts = CASE WHEN auth_rate_limits.window_start <= ? THEN 1 "
                "ELSE auth_rate_limits.attempts + 1 END, "
                "window_start = CASE WHEN auth_rate_limits.window_start <= ? THEN excluded.window_start "
                "ELSE auth_rate_limits.window_start END RETURNING attempts"
            ), (key_hash, start, cutoff, cutoff))
            attempts = cursor.fetchone()[0]
            # Bound persisted keys even when public clients rotate addresses.
            cursor.execute(self._sql("DELETE FROM auth_rate_limits WHERE window_start < ?"),
                           ((timestamp - timedelta(days=1)).isoformat(),))
            return attempts <= limit

    def configure_creator_platform(self, account_id: str, platform: str, username: str):
        source_account_id = username.casefold()
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(self._sql(
                "DELETE FROM creator_platform_accounts WHERE account_id = ? AND platform = ?"
            ), (account_id, platform))
            cursor.execute(self._sql(
                "INSERT INTO creator_platform_accounts "
                "(account_id, platform, source_account_id, username, configured_at) "
                "VALUES (?, ?, ?, ?, ?)"
            ), (account_id, platform, source_account_id, username, now()))

    def creator_platforms(self, account_id: str):
        return self.fetchall(
            "SELECT platform, source_account_id, username FROM creator_platform_accounts "
            "WHERE account_id = ? ORDER BY platform, source_account_id", (account_id,)
        )

    def save_session(self, session_id: str, tenant_id: str, game_id: str | None, mode: str = "live"):
        self.execute(
            "INSERT INTO live_sessions (id, tenant_id, game_id, status, mode, started_at, last_seen_at) "
            "VALUES (?, ?, ?, 'active', ?, ?, ?) ON CONFLICT(id) DO NOTHING",
            (session_id, tenant_id, game_id, mode, now(), now()),
        )

    def launch_creator_dark_session(self, account_id: str, tenant_id: str, mode: str,
                                    session_id: str, source_id: str):
        """Serialize launches per tenant and bind the TikTok source in the same transaction."""
        timestamp = now()
        with self.connection() as connection:
            cursor = connection.cursor()
            if self.backend == "sqlite":
                cursor.execute("BEGIN IMMEDIATE")
            else:
                cursor.execute(self._sql("SELECT pg_advisory_xact_lock(hashtext(?))"), (tenant_id,))
            cursor.execute(self._sql(
                "SELECT * FROM live_sessions WHERE tenant_id = ? AND status = 'active' "
                "ORDER BY started_at DESC LIMIT 1"
            ), (tenant_id,))
            existing = self._as_dict(cursor, cursor.fetchone())
            if existing:
                if existing["game_id"] != "dark" or existing["mode"] != mode:
                    raise ValueError("session_already_active")
                cursor.execute(self._sql(
                    "UPDATE live_sessions SET last_seen_at = ? WHERE id = ?"
                ), (timestamp, existing["id"]))
                return existing["id"], False
            if mode == "live":
                cursor.execute(self._sql(
                    "SELECT games_json FROM licenses WHERE tenant_id = ? AND enabled = 1"
                ), (tenant_id,))
                if not any("dark" in json.loads(row[0]) for row in cursor.fetchall()):
                    raise ValueError("license_required")
                cursor.execute(self._sql(
                    "SELECT source_account_id, username FROM creator_platform_accounts "
                    "WHERE account_id = ? AND platform = 'tiktok' LIMIT 1"
                ), (account_id,))
                platform = cursor.fetchone()
                if not platform:
                    raise ValueError("tiktok_not_configured")
            cursor.execute(self._sql(
                "INSERT INTO live_sessions "
                "(id, tenant_id, game_id, status, mode, started_at, last_seen_at) "
                "VALUES (?, ?, 'dark', 'active', ?, ?, ?)"
            ), (session_id, tenant_id, mode, timestamp, timestamp))
            if mode == "live":
                cursor.execute(self._sql(
                    "INSERT INTO live_sources (id, tenant_id, session_id, platform, account_id, "
                    "username, status, started_at, updated_at) "
                    "VALUES (?, ?, ?, 'tiktok', ?, ?, 'starting', ?, ?)"
                ), (source_id, tenant_id, session_id, platform[0], platform[1], timestamp, timestamp))
        return session_id, True

    def touch_creator_session(self, session_id: str):
        return self.execute(
            "UPDATE live_sessions SET last_seen_at = ? WHERE id = ? AND status = 'active'",
            (now(), session_id),
        ) > 0

    def active_creator_session(self, tenant_id: str):
        return self.fetchone(
            "SELECT * FROM live_sessions WHERE tenant_id = ? AND game_id = 'dark' "
            "AND status = 'active' ORDER BY started_at DESC LIMIT 1", (tenant_id,),
        )

    def expire_abandoned_sessions(self, lease_seconds: int = 120,
                                  max_seconds: int = 8 * 3600):
        """End expired creator sessions and their sources."""
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=lease_seconds)).isoformat()
        oldest = (datetime.now(timezone.utc) - timedelta(seconds=max_seconds)).isoformat()
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(self._sql(
                "SELECT id FROM live_sessions WHERE status = 'active' "
                "AND (last_seen_at < ? OR started_at < ?) AND tenant_id LIKE ?"
            ), (cutoff, oldest, "creator:%"))
            ids = [row[0] for row in cursor.fetchall()]
            for session_id in ids:
                timestamp = now()
                cursor.execute(self._sql(
                    "UPDATE live_sessions SET status = 'ended', ended_at = ? "
                    "WHERE id = ? AND status = 'active'"
                ), (timestamp, session_id))
                cursor.execute(self._sql(
                    "UPDATE dark_runs SET status = 'ended', completed_at = ?, updated_at = ? "
                    "WHERE session_id = ? AND status = 'active'"
                ), (timestamp, timestamp, session_id))
                cursor.execute(self._sql(
                    "UPDATE live_sources SET status = 'stopping', updated_at = ? "
                    "WHERE session_id = ? AND status NOT IN ('stopped', 'stopping')"
                ), (timestamp, session_id))
        return ids

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
                    "AND status NOT IN ('stopped', 'stopping')"
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

    def update_live_source_runtime(self, source_id: str, status: str):
        """Ignore late connector callbacks after a session has begun stopping."""
        return self.execute(
            "UPDATE live_sources SET status = ?, last_error = NULL, updated_at = ? "
            "WHERE id = ? AND status NOT IN ('stopping', 'stopped') AND EXISTS "
            "(SELECT 1 FROM live_sessions WHERE id = live_sources.session_id AND status = 'active')",
            (status, now(), source_id),
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

    def record_dark_tiktok_event(self, event, like_threshold: int, build_action):
        """Atomically deduplicate a source event, count likes and store its mapped action."""
        envelope = event.to_dict()
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(self._sql(
                "INSERT INTO event_outbox (event_id, tenant_id, session_id, event_type, payload_json, "
                "envelope_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(event_id) DO NOTHING"
            ), (
                event.event_id, event.tenant_id, event.session_id, event.type,
                json.dumps(event.payload), json.dumps(envelope), now(),
            ))
            if cursor.rowcount != 1:
                return False, None, None, None
            crossed = False
            like_total = None
            if event.type == "like":
                count = event.payload.get("count", 1)
                cursor.execute(self._sql(
                    "INSERT INTO dark_live_like_progress (session_id, source_platform, source_account_id, "
                    "total_count, updated_at) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(session_id, source_platform, source_account_id) DO UPDATE "
                    "SET total_count = dark_live_like_progress.total_count + excluded.total_count, "
                    "updated_at = excluded.updated_at"
                ), (event.session_id, event.source_platform, event.source_account_id, count, now()))
                cursor.execute(self._sql(
                    "SELECT total_count FROM dark_live_like_progress WHERE session_id = ? "
                    "AND source_platform = ? AND source_account_id = ?"
                ), (event.session_id, event.source_platform, event.source_account_id))
                like_total = cursor.fetchone()[0]
                crossed = like_total // like_threshold > (like_total - count) // like_threshold
            action_event, decision = build_action(event, crossed)
            if action_event:
                action_envelope = action_event.to_dict()
                cursor.execute(self._sql(
                    "INSERT INTO event_outbox (event_id, tenant_id, session_id, event_type, payload_json, "
                    "envelope_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(event_id) DO NOTHING"
                ), (
                    action_event.event_id, action_event.tenant_id, action_event.session_id,
                    action_event.type, json.dumps(action_event.payload), json.dumps(action_envelope), now(),
                ))
                if cursor.rowcount != 1:
                    raise RuntimeError("mapped Dark action ID conflicts with an existing event")
            return True, action_event, decision, like_total

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
