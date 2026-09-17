"""License lookup kept separate from HTTP and listener concerns."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class License:
    tenant_id: str
    key: str
    games: tuple[str, ...]


class LicenseStore:
    def __init__(self, raw: dict):
        self._by_key: dict[str, License] = {}
        self._by_tenant: dict[str, License] = {}
        for tenant_id, value in raw.items():
            if isinstance(value, dict) and value.get("key"):
                license_item = License(tenant_id, value["key"], tuple(value.get("games", [])))
                self._by_key[license_item.key] = license_item
                self._by_tenant[tenant_id] = license_item
            elif isinstance(value, dict):
                # Legacy key-only entries remain usable during migration.
                license_item = License(tenant_id, tenant_id, tuple(value.get("games", [])))
                self._by_key[tenant_id] = license_item
                self._by_tenant[tenant_id] = license_item

    def authorize(self, tenant_id: str, key: str, game_id: str | None = None) -> License | None:
        item = self._by_key.get(key)
        if item is None or item.tenant_id != tenant_id:
            return None
        if game_id and game_id not in item.games:
            return None
        return item

    def authorize_key(self, key: str, game_id: str | None = None) -> License | None:
        item = self._by_key.get(key)
        if item is None or (game_id and game_id not in item.games):
            return None
        return item

    def games_for(self, tenant_id: str) -> tuple[str, ...]:
        item = self._by_tenant.get(tenant_id)
        return item.games if item else ()
