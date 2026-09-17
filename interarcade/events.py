"""Versioned InterArcade event contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


EVENT_SCHEMA_VERSION = 1
SUPPORTED_TYPES = {"gift", "like", "comment", "share", "follow"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class InterArcadeEvent:
    tenant_id: str
    session_id: str
    type: str
    actor: str
    payload: dict = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=_now)
    schema_version: int = EVENT_SCHEMA_VERSION
    source: str = "tiktok"

    def __post_init__(self):
        if self.type not in SUPPORTED_TYPES:
            raise ValueError(f"unsupported event type: {self.type}")
        if not self.tenant_id or not self.session_id or not self.actor:
            raise ValueError("tenant_id, session_id and actor are required")

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "type": self.type,
            "actor": self.actor,
            "payload": self.payload,
        }


def event_from_tiktok(tenant_id: str, session_id: str, event_type: str, actor: str, **payload):
    return InterArcadeEvent(
        tenant_id=tenant_id,
        session_id=session_id,
        type=event_type,
        actor=actor,
        payload=payload,
    )
