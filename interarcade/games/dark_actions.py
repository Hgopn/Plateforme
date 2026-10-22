"""Provider-neutral, bounded live actions for Dark."""

from __future__ import annotations

from ..events import InterArcadeEvent


# Durations are server-owned. A connector supplies an action key, never an
# arbitrary duration or platform-specific game instruction.
ACTION_DURATIONS_MS = {
    "LIGHT_BOOST": 8_000,
    "LIGHT_REDUCE": 8_000,
    "REVEAL_MAP": 5_000,
    "PLAYER_HELP": 7_000,
    "PLAYER_HINDER": 7_000,
}


def action_from_event(event: InterArcadeEvent) -> dict:
    """Build the versioned game action while preserving Live Hub identity."""
    if event.type != "action":
        raise ValueError("Dark actions require an InterArcade action event")
    action_type = event.payload.get("action_type")
    if not isinstance(action_type, str) or action_type not in ACTION_DURATIONS_MS:
        raise ValueError("unsupported Dark action")
    envelope = event.to_dict()
    action = {
        "schema_version": 1,
        "game_id": "dark",
        "action_type": action_type,
        "duration_ms": ACTION_DURATIONS_MS[action_type],
        **{
            key: envelope[key] for key in (
                "event_id", "source_event_id", "timestamp", "tenant_id", "session_id",
                "source_platform", "source_account_id", "source_username",
                "actor_id", "actor_platform_id", "actor_username",
            )
        },
    }
    trigger = event.payload.get("trigger")
    if isinstance(trigger, dict):
        action["trigger"] = trigger
    return action
