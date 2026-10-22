"""Validate a filled production environment before building or starting services."""

from __future__ import annotations

import sys
import ipaddress
from pathlib import Path

from dotenv import dotenv_values


def validate(values: dict) -> list[str]:
    issues = []
    domain = (values.get("INTERARCADE_DOMAIN") or "").strip()
    if not domain or "example.com" in domain or "://" in domain or "/" in domain:
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
        "INTERARCADE_DB_PASSWORD",
    )
    secrets = []
    for name in names:
        value = values.get(name) or ""
        if len(value) < 32 or "replace" in value.lower() or "change-me" in value.lower():
            issues.append(f"{name} must be a unique random value of at least 32 characters")
        secrets.append(value)
    if len(set(secrets)) != len(secrets):
        issues.append("Production secrets must be distinct")
    if values.get("INTERARCADE_REQUIRE_WORKER_HEARTBEAT", "").lower() != "true":
        issues.append("INTERARCADE_REQUIRE_WORKER_HEARTBEAT must be true")
    return issues


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(".env.production")
    if not path.is_file():
        print(f"Missing production environment file: {path}", file=sys.stderr)
        return 2
    issues = validate(dict(dotenv_values(path)))
    for issue in issues:
        print(issue, file=sys.stderr)
    if issues:
        return 2
    print("Production configuration structure is valid. DNS, TLS and credentials still need live verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
