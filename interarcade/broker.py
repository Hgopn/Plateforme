"""Broker health abstraction. Socket.IO uses Redis when configured."""

from __future__ import annotations


class Broker:
    def __init__(self, url: str = ""):
        self.url = url
        self.kind = "redis" if url else "local"

    def ping(self):
        if not self.url:
            return True
        try:
            import redis
            return bool(redis.from_url(self.url).ping())
        except Exception:
            return False
