"""Small in-memory domain models used by the foundation phase."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Tenant:
    tenant_id: str
    username: str
    enabled: bool = True
    games: list[str] = field(default_factory=list)


@dataclass
class Session:
    session_id: str
    tenant_id: str
    username: str
    game_id: Optional[str] = None
    status: str = "active"
    created_at: str = field(default_factory=utc_now)


@dataclass
class Listener:
    tenant_id: str
    username: str
    status: str = "stopped"
    started_at: Optional[str] = None
    last_error: Optional[str] = None
    worker: object = None


class RuntimeRegistry:
    """Process-local registry until a persistent store/broker is introduced."""

    def __init__(self):
        self._lock = RLock()
        self.tenants: dict[str, Tenant] = {}
        self.sessions: dict[str, Session] = {}
        self.listeners: dict[str, Listener] = {}

    def get_listener(self, tenant_id: str) -> Optional[Listener]:
        with self._lock:
            return self.listeners.get(tenant_id)

    def put_listener(self, listener: Listener) -> Listener:
        with self._lock:
            self.listeners[listener.tenant_id] = listener
            return listener

    def list_listeners(self) -> list[Listener]:
        with self._lock:
            return list(self.listeners.values())
