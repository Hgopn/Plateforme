"""Validate API -> Socket.IO using the existing Slot/Dark/Marble clients' contract."""

from __future__ import annotations

import json
import os
import threading
import urllib.request
from uuid import uuid4

import socketio


API = os.getenv("INTERARCADE_FLOW_API", "http://api:5000")
INTERNAL_TOKEN = os.environ["INTERARCADE_INTERNAL_EVENT_TOKEN"]


def post(path, data, headers=None):
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
        return json.loads(response.read())


def main():
    sessions = {}
    for game_id in ("slot", "dark", "marble"):
        sessions[game_id] = post(
            "/api/v1/sessions",
            {"tenant_id": "songmicon", "username": "songmicon", "game_id": game_id, "license_key": "IA-SONGMI-PRO"},
        )

    received = []
    ready = threading.Event()
    client = socketio.Client()

    @client.event
    def connect():
        ready.set()

    @client.on("ia:event")
    def on_event(data):
        received.append(data)

    client.connect(API, auth={"token": sessions["slot"]["token"]}, transports=["websocket"])
    if not ready.wait(5):
        raise RuntimeError("Socket.IO did not connect")
    event = post(
        "/api/v1/internal/events",
        {
            "event_id": f"integration-simulated-gift-{uuid4()}",
            "tenant_id": "songmicon",
            "session_id": sessions["slot"]["session_id"],
            "type": "gift",
            "actor": "integration-viewer",
            "payload": {"gift": "Rose", "count": 1},
        },
        {"X-InterArcade-Internal-Token": INTERNAL_TOKEN},
    )
    if event["schema_version"] != 1:
        raise RuntimeError(f"unexpected event schema: {event}")
    for _ in range(50):
        if received:
            break
        ready.wait(0.1)
    client.disconnect()
    if not received or received[0]["payload"]["gift"] != "Rose":
        raise RuntimeError(f"unexpected received events: {received}")
    for game_id in ("slot", "dark", "marble"):
        with urllib.request.urlopen(f"{API}/games/{game_id}/{game_id}.html", timeout=10) as response:  # nosec B310
            if response.status != 200:
                raise RuntimeError(f"game page failed: {game_id}")
    print(json.dumps({"status": "ok", "games": list(sessions), "events_received": len(received)}))


if __name__ == "__main__":
    main()
