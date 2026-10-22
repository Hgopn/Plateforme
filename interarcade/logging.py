"""Structured JSON logging without an additional logging dependency."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "component"):
            payload["component"] = record.component
        for name in (
            "event_id", "original_event_id", "session_id", "source_platform", "source_account_id",
            "event_type", "action_type", "gift_id", "gift_name", "repeat_count",
            "like_total", "reason",
            "room_id", "previous_room_id", "sdk_live_status", "error_type", "retry_seconds",
        ):
            if hasattr(record, name):
                payload[name] = getattr(record, name)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO"):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
