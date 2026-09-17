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
    PORT = int(os.getenv("PORT", "5000"))
    HOST = os.getenv("HOST", "0.0.0.0")
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
