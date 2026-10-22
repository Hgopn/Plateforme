"""Server-side mapping from normalized TikTok events to generic Dark actions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .events import InterArcadeEvent, event_from_source
from .games.dark_actions import ACTION_DURATIONS_MS


@dataclass(frozen=True)
class MappingDecision:
    action_type: str | None
    reason: str


@dataclass(frozen=True)
class DarkTikTokMapping:
    follow_action: str
    like_threshold: int
    like_action: str
    small_max: int
    medium_max: int
    small_action: str
    medium_action: str
    large_action: str
    id_overrides: dict[str, str]
    name_overrides: dict[str, str]

    @classmethod
    def from_path(cls, path: str | Path) -> DarkTikTokMapping:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("unsupported Dark TikTok mapping schema")
        likes, gifts = data.get("likes"), data.get("gifts")
        if not isinstance(likes, dict) or not isinstance(gifts, dict):
            raise ValueError("Dark TikTok mapping requires likes and gifts objects")
        threshold = likes.get("threshold")
        small_max, medium_max = gifts.get("small_max"), gifts.get("medium_max")
        if (isinstance(threshold, bool) or not isinstance(threshold, int) or not 1 <= threshold <= 1_000_000
                or isinstance(small_max, bool) or not isinstance(small_max, int) or small_max < 0
                or isinstance(medium_max, bool) or not isinstance(medium_max, int) or medium_max <= small_max
                or gifts.get("value_basis") != "total_diamonds"):
            raise ValueError("invalid Dark TikTok thresholds or value basis")
        actions = (
            data.get("follow_action"), likes.get("action"), gifts.get("small_action"),
            gifts.get("medium_action"), gifts.get("large_action"),
        )
        if any(not isinstance(action, str) or action not in ACTION_DURATIONS_MS for action in actions):
            raise ValueError("Dark TikTok mapping contains an unknown action")
        id_overrides = gifts.get("id_overrides", {})
        name_overrides = gifts.get("name_overrides", {})
        if any(not isinstance(overrides, dict) for overrides in (id_overrides, name_overrides)):
            raise ValueError("gift overrides must be objects")
        for overrides in (id_overrides, name_overrides):
            if any(not isinstance(key, str) or not key.strip() or not isinstance(value, str)
                   or value not in ACTION_DURATIONS_MS for key, value in overrides.items()):
                raise ValueError("invalid gift override")
        return cls(
            follow_action=data["follow_action"], like_threshold=threshold, like_action=likes["action"],
            small_max=small_max, medium_max=medium_max,
            small_action=gifts["small_action"], medium_action=gifts["medium_action"],
            large_action=gifts["large_action"],
            id_overrides={key.strip(): value for key, value in id_overrides.items()},
            name_overrides={key.strip().casefold(): value for key, value in name_overrides.items()},
        )

    def decide(self, event: InterArcadeEvent, like_threshold_crossed: bool = False) -> MappingDecision:
        if event.source_platform != "tiktok":
            return MappingDecision(None, "unsupported_platform")
        if event.type == "follow":
            return MappingDecision(self.follow_action, "follow")
        if event.type == "like":
            return MappingDecision(self.like_action if like_threshold_crossed else None,
                                   "like_threshold" if like_threshold_crossed else "likes_below_threshold")
        if event.type != "gift":
            return MappingDecision(None, "event_type_not_mapped")
        gift_id = event.payload.get("gift_id")
        gift_name = event.payload.get("gift_name", event.payload.get("gift"))
        if gift_id is not None and str(gift_id) in self.id_overrides:
            return MappingDecision(self.id_overrides[str(gift_id)], "gift_id_override")
        if isinstance(gift_name, str) and gift_name.casefold() in self.name_overrides:
            return MappingDecision(self.name_overrides[gift_name.casefold()], "gift_name_override")
        diamonds = event.payload.get("gift_total_diamonds")
        if isinstance(diamonds, bool) or not isinstance(diamonds, int) or diamonds <= 0:
            return MappingDecision(None, "gift_value_unavailable")
        if diamonds <= self.small_max:
            return MappingDecision(self.small_action, "small_gift")
        if diamonds <= self.medium_max:
            return MappingDecision(self.medium_action, "medium_gift")
        return MappingDecision(self.large_action, "large_gift")


def mapped_action_event(event: InterArcadeEvent, action_type: str) -> InterArcadeEvent:
    """Use a stable derived ID and carry the original event details forward."""
    fields = (
        "gift_id", "gift_name", "gift_diamond_count", "gift_total_diamonds",
        "repeat_count", "repeat_end", "count", "total_likes",
    )
    trigger = {
        "original_event_id": event.event_id,
        "original_event_type": event.type,
        "original_event_value": event.event_value,
        **{key: event.payload[key] for key in fields if key in event.payload},
    }
    if event.type == "like":
        trigger["count"] = event.payload.get("count", 1)
    return event_from_source(
        event.source_platform, event.tenant_id, event.session_id,
        "action", event.actor, event_id=f"dark-action:{event.source_event_id}",
        source_account_id=event.source_account_id, source_username=event.source_username,
        actor_platform_id=event.actor_platform_id, timestamp=event.timestamp,
        action_type=action_type, trigger=trigger,
    )
