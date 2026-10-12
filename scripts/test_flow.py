"""Validate API -> Socket.IO using the existing Slot/Dark/Marble clients' contract."""

from __future__ import annotations

import json
import os
import threading
import urllib.request
from uuid import uuid4

import socketio

from interarcade.config import Config
from interarcade.database import Database


API = os.getenv("INTERARCADE_FLOW_API", "http://api:5000")
INTERNAL_TOKEN = os.environ["INTERARCADE_INTERNAL_EVENT_TOKEN"]
ADMIN_TOKEN = os.environ["INTERARCADE_ADMIN_TOKEN"]


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
    for game_id in ("slot", "dark", "marble", "fight"):
        sessions[game_id] = post(
            "/api/v1/sessions",
            {"tenant_id": "integration-test", "username": "integration-test", "game_id": game_id},
            {"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )

    received = []
    received_by_dark = []
    ready = threading.Event()
    client = socketio.Client()
    dark_client = socketio.Client()

    @client.event
    def connect():
        ready.set()

    @client.on("ia:event")
    def on_event(data):
        received.append(data)

    @dark_client.on("ia:event")
    def on_dark_event(data):
        received_by_dark.append(data)

    client.connect(API, auth={"token": sessions["slot"]["token"]}, transports=["websocket"])
    dark_client.connect(API, auth={"token": sessions["dark"]["token"]}, transports=["websocket"])
    if not ready.wait(5):
        raise RuntimeError("Socket.IO did not connect")
    event = post(
        "/api/v1/internal/events",
        {
            "event_id": f"integration-simulated-gift-{uuid4()}",
            "tenant_id": "integration-test",
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
    dark_client.disconnect()
    if not received or received[0]["payload"]["gift"] != "Rose":
        raise RuntimeError(f"unexpected received events: {received}")
    if received_by_dark:
        raise RuntimeError(f"event leaked into another session: {received_by_dark}")
    for game_id in ("slot", "dark", "marble", "fight"):
        with urllib.request.urlopen(f"{API}/games/{game_id}/{game_id}.html", timeout=10) as response:  # nosec B310
            if response.status != 200:
                raise RuntimeError(f"game page failed: {game_id}")
    for session in sessions.values():
        post(
            f"/api/v1/sessions/{session['session_id']}/end",
            {},
            {"Authorization": f"Bearer {session['token']}"},
        )

    # Exercise PostgreSQL's runtime error id default, then remove the probe so
    # diagnostics stay clean after the integration suite.
    database = Database(Config.DATABASE_URL)
    database.initialize()
    marker = f"integration-probe-{uuid4()}"
    database.record_error("integration-test", marker)
    if not any(row["message"] == marker for row in database.recent_errors(100)):
        raise RuntimeError("runtime error persistence probe was not stored")
    database.execute("DELETE FROM runtime_errors WHERE component = ? AND message = ?", ("integration-test", marker))
    print(json.dumps({
        "status": "ok",
        "games": list(sessions),
        "events_received": len(received),
        "session_isolation": True,
        "postgres_runtime_errors": True,
    }))


if __name__ == "__main__":
    main()
