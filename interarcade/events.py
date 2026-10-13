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
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.event_id, self.tenant_id, self.session_id, self.actor)
        ):
            raise ValueError("event_id, tenant_id, session_id and actor are required strings")
        if not isinstance(self.payload, dict):
            raise ValueError("event payload must be an object")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("event source must be a non-empty string")
        if self.type in {"gift", "like", "share"}:
            count = self.payload.get("count", 1)
            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 1_000_000:
                raise ValueError("event count must be an integer between 1 and 1000000")
        if self.type == "gift" and "gift" in self.payload and not isinstance(self.payload["gift"], str):
            raise ValueError("gift name must be a string")
        if self.type == "comment" and not isinstance(self.payload.get("comment", ""), str):
            raise ValueError("comment must be a string")

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


def event_from_source(
    source: str,
    tenant_id: str,
    session_id: str,
    event_type: str,
    actor: str,
    event_id: str | None = None,
    **payload,
):
    return InterArcadeEvent(
        tenant_id=tenant_id,
        session_id=session_id,
        type=event_type,
        actor=actor,
        payload=payload,
        event_id=event_id or str(uuid4()),
        source=source,
    )


def event_from_tiktok(
    tenant_id: str,
    session_id: str,
    event_type: str,
    actor: str,
    event_id: str | None = None,
    **payload,
):
    return event_from_source(
        "tiktok",
        tenant_id,
        session_id,
        event_type,
        actor,
        event_id=event_id,
        **payload,
    )
