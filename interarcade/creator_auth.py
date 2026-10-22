"""Password hashing and input validation for creator accounts."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
TIKTOK_RE = re.compile(r"^[A-Za-z0-9._]{2,24}$")
PBKDF2_ROUNDS = 600_000


def normalize_email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    email = value.strip().casefold()
    return email if len(email) <= 254 and EMAIL_RE.fullmatch(email) else None


def valid_password(value: object) -> bool:
    return isinstance(value, str) and 12 <= len(value) <= 1024


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def check_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, digest = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or not 100_000 <= int(rounds) <= 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(actual, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def normalize_tiktok(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    username = value.strip().removeprefix("@")
    return username if TIKTOK_RE.fullmatch(username) else None
