"""Minimal signed session tokens for the foundation phase."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_token(secret: str, claims: dict, ttl_seconds: int = 3600) -> str:
    payload = dict(claims)
    payload["exp"] = int(time.time()) + ttl_seconds
    encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    return f"{encoded}.{_encode(signature)}"


def verify_token(secret: str, token: str) -> dict | None:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _decode(signature)):
            return None
        claims = json.loads(_decode(encoded))
        if int(claims.get("exp", 0)) < int(time.time()):
            return None
        return claims
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
        return None
