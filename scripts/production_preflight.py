"""Validate a filled production environment before building or starting services."""

from __future__ import annotations

import sys
import ipaddress
import re
import stat
from pathlib import Path

from dotenv import dotenv_values


def validate(values: dict) -> list[str]:
    issues = []
    domain = (values.get("INTERARCADE_DOMAIN") or "").strip()
    if "example.com" in domain or not re.fullmatch(
        r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain
    ):
        issues.append("INTERARCADE_DOMAIN must be the real DNS hostname")
    if values.get("INTERARCADE_ALLOWED_ORIGINS") != f"https://{domain}":
        issues.append("INTERARCADE_ALLOWED_ORIGINS must match the HTTPS domain")
    try:
        if not ipaddress.ip_address(values.get("INTERARCADE_PUBLIC_IP") or "").is_global:
            issues.append("INTERARCADE_PUBLIC_IP must be the VPS public IP")
    except ValueError:
        issues.append("INTERARCADE_PUBLIC_IP must be a valid public IP")
    email = (values.get("INTERARCADE_TLS_EMAIL") or "").strip()
    if "@" not in email or "example.com" in email:
        issues.append("INTERARCADE_TLS_EMAIL must be a real ACME contact email")
    names = (
        "INTERARCADE_SECRET_KEY", "INTERARCADE_SESSION_SECRET", "INTERARCADE_ADMIN_TOKEN",
        "INTERARCADE_INTERNAL_EVENT_TOKEN", "INTERARCADE_OBSERVER_TOKEN",
        "INTERARCADE_DB_PASSWORD", "INTERARCADE_DB_ADMIN_PASSWORD",
    )
    secrets = []
    for name in names:
        value = values.get(name) or ""
        if len(value) < 32 or "replace" in value.lower() or "change-me" in value.lower():
            issues.append(f"{name} must be a unique random value of at least 32 characters")
        secrets.append(value)
    if len(set(secrets)) != len(secrets):
        issues.append("Production secrets must be distinct")
    if not re.fullmatch(r"[A-Za-z0-9._~-]{32,}", values.get("INTERARCADE_DB_PASSWORD") or ""):
        issues.append("INTERARCADE_DB_PASSWORD must be URL-safe for the database connection string")
    if values.get("INTERARCADE_REQUIRE_WORKER_HEARTBEAT", "").lower() != "true":
        issues.append("INTERARCADE_REQUIRE_WORKER_HEARTBEAT must be true")
    if values.get("INTERARCADE_HSTS_MAX_AGE") not in {"0", "31536000"}:
        issues.append("INTERARCADE_HSTS_MAX_AGE must be 0 or 31536000")
    return issues


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(".env.production")
    if not path.is_file():
        print(f"Missing production environment file: {path}", file=sys.stderr)
        return 2
    issues = validate(dict(dotenv_values(path)))
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        issues.append("Production environment file must have permissions 0600 or stricter")
    for issue in issues:
        print(issue, file=sys.stderr)
    if issues:
        return 2
    print("Production configuration structure is valid. DNS, TLS and credentials still need live verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
