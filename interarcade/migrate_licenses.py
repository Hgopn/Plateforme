"""Import legacy licenses.json into the persistent database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Config
from .database import Database


def migrate(database_url: str, licenses_file: str) -> int:
    database = Database(database_url)
    database.initialize()
    raw = json.loads(Path(licenses_file).read_text(encoding="utf-8"))
    migrated = 0
    for tenant_id, value in raw.items():
        if not isinstance(value, dict):
            continue
        key = value.get("key") or tenant_id
        games = list(value.get("games", []))
        database.upsert_tenant(tenant_id, tenant_id)
        database.upsert_user(f"owner:{tenant_id}", tenant_id, tenant_id, role="owner")
        database.upsert_license(f"license:{tenant_id}", tenant_id, key, games)
        migrated += 1
    return migrated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=Config.DATABASE_URL)
    parser.add_argument("--licenses-file", default=str(Config.LICENSES_FILE))
    args = parser.parse_args()
    print(f"Migrated {migrate(args.database_url, args.licenses_file)} licenses")


if __name__ == "__main__":
    main()
