"""Server-authoritative Marble round rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarbleConfig:
    gift_target: int = 50
    like_target: int = 500
    like_unit: int = 15
    lion_multiplier: int = 4

    @classmethod
    def from_mapping(cls, values: dict | None = None):
        values = values or {}

        def integer(name, default, minimum, maximum):
            try:
                value = int(values.get(name, default))
            except (TypeError, ValueError):
                value = default
            return max(minimum, min(maximum, value))

        return cls(
            gift_target=integer("gift_target", cls.gift_target, 1, 1_000_000),
            like_target=integer("like_target", cls.like_target, 1, 1_000_000),
            like_unit=integer("like_unit", cls.like_unit, 1, 10_000),
            lion_multiplier=integer("lion_multiplier", cls.lion_multiplier, 1, 20),
        )

    def to_dict(self):
        return {
            "gift_target": self.gift_target,
            "like_target": self.like_target,
            "like_unit": self.like_unit,
            "lion_multiplier": self.lion_multiplier,
        }


def apply_event(state: dict, event: dict, config: MarbleConfig):
    """Return the next state; a finished round is immutable."""
    if state["status"] != "active":
        return state
    gift_score = int(state["gift_score"])
    like_score = int(state["like_score"])
    payload = event.get("payload") or {}
    if event["type"] == "gift":
        count = max(1, int(payload.get("count", 1)))
        gift_name = str(payload.get("gift", "")).lower()
        multiplier = config.lion_multiplier if any(name in gift_name for name in ("lion", "unicorn")) else 1
        gift_score += count * multiplier
    elif event["type"] == "like":
        count = max(1, int(payload.get("count", 1)))
        like_score += max(1, count // config.like_unit)
    else:
        return state
    winner = None
    if gift_score >= config.gift_target:
        winner = "GIFTS"
    if like_score >= config.like_target and winner is None:
        winner = "LIKES"
    return {
        **state,
        "gift_score": gift_score,
        "like_score": like_score,
        "status": "finished" if winner else "active",
        "winner": winner,
    }
