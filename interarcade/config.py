"""Environment-driven configuration for InterArcade."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.getenv("INTERARCADE_SECRET_KEY", "dev-only-change-me")
    SESSION_SECRET = os.getenv("INTERARCADE_SESSION_SECRET", SECRET_KEY)
    INTERNAL_EVENT_TOKEN = os.getenv("INTERARCADE_INTERNAL_EVENT_TOKEN", "")
    ADMIN_TOKEN = os.getenv("INTERARCADE_ADMIN_TOKEN", "")
    TIKTOK_SIGN_API_KEY = os.getenv("EULER_API_KEY", "")
    LISTENER_BACKEND_URL = os.getenv("INTERARCADE_LISTENER_BACKEND_URL", "")
    API_URL = os.getenv("INTERARCADE_API_URL", "http://127.0.0.1:5000")
    WORKER_POLL_SECONDS = float(os.getenv("INTERARCADE_WORKER_POLL_SECONDS", "2"))
    WORKER_HEARTBEAT_TIMEOUT_SECONDS = float(os.getenv("INTERARCADE_WORKER_HEARTBEAT_TIMEOUT_SECONDS", "15"))
    REQUIRE_WORKER_HEARTBEAT = _bool("INTERARCADE_REQUIRE_WORKER_HEARTBEAT", False)
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/interarcade-dev.db")
    BROKER_URL = os.getenv("REDIS_URL", "")
    LOG_LEVEL = os.getenv("INTERARCADE_LOG_LEVEL", "INFO")
    OBSERVER_TOKEN = os.getenv("INTERARCADE_OBSERVER_TOKEN", "")
    GIT_VERSION = os.getenv("INTERARCADE_GIT_VERSION", "unknown")
    PORT = int(os.getenv("PORT", "5000"))
    HOST = os.getenv("HOST", "127.0.0.1")
    ALLOWED_ORIGINS = os.getenv("INTERARCADE_ALLOWED_ORIGINS", "").strip()
    LEGACY_SOCKET_QUERY_AUTH = _bool("INTERARCADE_LEGACY_SOCKET_QUERY_AUTH", False)
    LICENSES_FILE = Path(
        os.getenv("INTERARCADE_LICENSES_FILE", str(BASE_DIR / "licenses.json"))
    )
    GAMES_DIR = Path(os.getenv("INTERARCADE_GAMES_DIR", str(BASE_DIR / "games")))

    @classmethod
    def origins(cls):
        if not cls.ALLOWED_ORIGINS:
            return []
        return [origin.strip() for origin in cls.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @classmethod
    def load_licenses(cls) -> dict:
        try:
            return json.loads(cls.LICENSES_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
