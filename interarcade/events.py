"""Versioned, provider-neutral InterArcade event contract."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import quote
from uuid import uuid4


EVENT_SCHEMA_VERSION = 1
SUPPORTED_TYPES = {"gift", "like", "comment", "share", "follow", "action"}
COUNT_TYPES = {"gift", "like", "share"}
PLATFORM_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def actor_identity(platform: str, platform_user_id: str) -> str:
    """A platform user key; usernames remain display text, never merge keys."""
    return f"{platform}:{quote(platform_user_id, safe='')}"


def scoped_event_id(session_id: str, platform: str, account_id: str, source_event_id: str) -> str:
    """Prevent identical provider IDs from colliding across sources or sessions."""
    return ":".join((
        "ia", quote(session_id, safe=""), platform,
        quote(account_id, safe=""), quote(source_event_id, safe=""),
    ))


@dataclass(frozen=True)
class InterArcadeEvent:
    tenant_id: str
    session_id: str
    type: str
    actor: str
    source_platform: str
    source_account_id: str
    source_username: str
    actor_platform_id: str
    source_event_id: str
    event_id: str
    payload: dict = field(default_factory=dict)
    event_value: int | float | None = None
    timestamp: str = field(default_factory=_now)
    schema_version: int = EVENT_SCHEMA_VERSION

    def __post_init__(self):
        if self.type not in SUPPORTED_TYPES:
            raise ValueError(f"unsupported event type: {self.type}")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.event_id, self.source_event_id, self.tenant_id, self.session_id,
                self.actor, self.source_account_id, self.source_username, self.actor_platform_id,
            )
        ):
            raise ValueError("event and source identity fields must be non-empty strings")
        if not isinstance(self.source_platform, str) or not PLATFORM_PATTERN.fullmatch(self.source_platform):
            raise ValueError("source_platform must be a lowercase platform key")
        if self.event_id != scoped_event_id(
            self.session_id, self.source_platform, self.source_account_id, self.source_event_id
        ):
            raise ValueError("event_id does not match its source identity")
        try:
            parsed_timestamp = datetime.fromisoformat(self.timestamp)
        except (TypeError, ValueError) as exc:
            raise ValueError("timestamp must be an ISO 8601 datetime") from exc
        if parsed_timestamp.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        if not isinstance(self.payload, dict):
            raise ValueError("event payload must be an object")
        if self.type in COUNT_TYPES:
            count = self.payload.get("count", 1)
            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 1_000_000:
                raise ValueError("event count must be an integer between 1 and 1000000")
            if self.event_value != count:
                raise ValueError("event_value must match the normalized event count")
        if self.type == "gift" and "gift" in self.payload and not isinstance(self.payload["gift"], str):
            raise ValueError("gift name must be a string")
        if self.type == "comment" and not isinstance(self.payload.get("comment", ""), str):
            raise ValueError("comment must be a string")
        if self.event_value is not None and (
            isinstance(self.event_value, bool)
            or not isinstance(self.event_value, (int, float))
            or not math.isfinite(self.event_value)
            or self.event_value < 0
        ):
            raise ValueError("event_value must be a non-negative finite number")

    @property
    def source(self) -> str:
        """Legacy alias retained for existing clients and tests."""
        return self.source_platform

    @property
    def actor_id(self) -> str:
        return actor_identity(self.source_platform, self.actor_platform_id)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "source_event_id": self.source_event_id,
            "timestamp": self.timestamp,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "source_platform": self.source_platform,
            "source_account_id": self.source_account_id,
            "source_username": self.source_username,
            "event_type": self.type,
            "event_value": self.event_value,
            "actor_id": self.actor_id,
            "actor_platform_id": self.actor_platform_id,
            "actor_username": self.actor,
            # Additive V1 aliases keep existing Slot, Dark, Marble and tools working.
            "source": self.source_platform,
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
    *,
    source_account_id: str | None = None,
    source_username: str | None = None,
    actor_platform_id: str | None = None,
    timestamp: str | None = None,
    event_value: int | float | None = None,
    **payload,
) -> InterArcadeEvent:
    account_id = source_account_id if source_account_id is not None else tenant_id
    username = source_username if source_username is not None else account_id
    platform_actor_id = actor_platform_id if actor_platform_id is not None else actor
    if not isinstance(source, str) or not PLATFORM_PATTERN.fullmatch(source):
        raise ValueError("source_platform must be a lowercase platform key")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id must be a non-empty string")
    if not isinstance(account_id, str) or not account_id.strip():
        raise ValueError("source_account_id must be a non-empty string")
    if event_id is not None and (not isinstance(event_id, str) or not event_id.strip()):
        raise ValueError("source_event_id must be a non-empty string")
    raw_id = event_id if event_id is not None else str(uuid4())
    if event_value is None and event_type in COUNT_TYPES:
        event_value = payload.get("count", 1)
    return InterArcadeEvent(
        tenant_id=tenant_id,
        session_id=session_id,
        type=event_type,
        actor=actor,
        source_platform=source,
        source_account_id=account_id,
        source_username=username,
        actor_platform_id=platform_actor_id,
        source_event_id=raw_id,
        event_id=scoped_event_id(session_id, source, account_id, raw_id),
        payload=payload,
        event_value=event_value,
        timestamp=timestamp or _now(),
    )


def event_from_tiktok(
    tenant_id: str,
    session_id: str,
    event_type: str,
    actor: str,
    event_id: str | None = None,
    **kwargs,
) -> InterArcadeEvent:
    return event_from_source("tiktok", tenant_id, session_id, event_type, actor, event_id=event_id, **kwargs)
