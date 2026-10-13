"""Validate API -> Socket.IO using the existing Slot/Dark/Marble clients' contract."""

from __future__ import annotations

import json
import os
import threading
import urllib.request
from collections import deque
from uuid import uuid4

import socketio

from interarcade.config import Config
from interarcade.database import Database
from interarcade.games.dark import LEVELS


API = os.getenv("INTERARCADE_FLOW_API", "http://api:5000")
INTERNAL_TOKEN = os.environ["INTERARCADE_INTERNAL_EVENT_TOKEN"]
ADMIN_TOKEN = os.environ["INTERARCADE_ADMIN_TOKEN"]


def path_to_exit(state):
    tiles = state["map"]["tiles"]
    start = (state["player"]["x"], state["player"]["y"])
    target = (state["map"]["exit"]["x"], state["map"]["exit"]["y"])
    directions = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
    queue = deque([start])
    previous = {start: None}
    while queue and target not in previous:
        x, y = queue.popleft()
        for direction, (dx, dy) in directions.items():
            candidate = (x + dx, y + dy)
            if candidate in previous or tiles[candidate[1]][candidate[0]] == "#":
                continue
            previous[candidate] = ((x, y), direction)
            queue.append(candidate)
    if target not in previous:
        raise RuntimeError(f"Dark level {state['level']} has no route to its exit")
    path = []
    current = target
    while current != start:
        current, direction = previous[current]
        path.append(direction)
    return list(reversed(path))


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

    dark_base = f"/api/v1/sessions/{sessions['dark']['session_id']}/games/dark"
    dark_headers = {"Authorization": f"Bearer {sessions['dark']['token']}"}
    dark_started = post(f"{dark_base}/start", {}, dark_headers)
    if dark_started["state"]["map"]["width"] != 10:
        raise RuntimeError(f"Dark level one did not load: {dark_started}")
    dark_collision = post(f"{dark_base}/move", {"direction": "up"}, dark_headers)
    if not dark_collision["outcome"]["collision"]:
        raise RuntimeError(f"Dark wall collision was not enforced: {dark_collision}")
    dark_state = dark_started["state"]
    for number, expected_size in ((1, 10), (2, 15), (3, 20)):
        if dark_state["level"] != number or dark_state["map"]["width"] != expected_size:
            raise RuntimeError(f"Dark level {number} did not load: {dark_state}")
        if dark_state["map"]["tiles"] != list(LEVELS[number].tiles):
            raise RuntimeError(f"Dark level {number} is not the current authored map")
        for direction in path_to_exit(dark_state):
            result = post(f"{dark_base}/move", {"direction": direction}, dark_headers)
            dark_state = result["state"]
        transition = result["outcome"]["transition"]
        if not transition or transition["completed_level"] != number:
            raise RuntimeError(f"Dark level {number} did not complete: {result}")
    if dark_state["status"] != "finished":
        raise RuntimeError(f"Dark campaign did not finish: {dark_state}")
    dark_reset = post(f"{dark_base}/reset", {}, dark_headers)
    if dark_reset["state"]["level"] != 1 or dark_reset["state"]["moves"] != 0 or dark_reset["state"]["status"] != "active":
        raise RuntimeError(f"Dark reset failed: {dark_reset}")
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
        "dark_levels_completed": 3,
        "postgres_runtime_errors": True,
    }))


if __name__ == "__main__":
    main()
