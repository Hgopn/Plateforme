"""Exercise the local launcher journey before and after a runtime restart."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import socketio


API = os.getenv("INTERARCADE_FLOW_API", "http://api:5000").rstrip("/")
OBSERVER_TOKEN = os.environ["INTERARCADE_OBSERVER_TOKEN"]
STATE_FILE = Path(".runtime/e2e-state.json")


def request(path: str, method: str = "GET", data: dict | None = None, headers: dict | None = None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310
            raw = response.read()
            content_type = response.headers.get_content_type()
            return response.status, json.loads(raw) if content_type == "application/json" else raw.decode()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw else {}


def create_demo_session(game_id: str) -> dict:
    status, session = request("/api/v1/demo/session", "POST", {"game_id": game_id})
    if status != 201:
        raise RuntimeError(f"could not create {game_id} demo session: {status} {session}")
    return session


def auth(session: dict) -> dict:
    return {"Authorization": f"Bearer {session['token']}"}


def close_session(session: dict):
    status, result = request(
        f"/api/v1/sessions/{session['session_id']}/end",
        "POST",
        {},
        auth(session),
    )
    if status != 200 or result.get("status") != "ended":
        raise RuntimeError(f"session did not close: {status} {result}")


def journey():
    status, launcher = request("/")
    if status != 200 or "InterArcade" not in launcher:
        raise RuntimeError("launcher did not load")
    for asset in (
        "/games/dark/dark.html",
        "/games/marble/marble.html",
        "/games/vendor/socket.io-4.7.5.min.js",
    ):
        status, _ = request(asset)
        if status != 200:
            raise RuntimeError(f"launcher asset did not load: {asset} ({status})")

    dark = create_demo_session("dark")
    status, dark_started = request(
        f"/api/v1/sessions/{dark['session_id']}/games/dark/start",
        "POST",
        {},
        auth(dark),
    )
    if status != 201 or dark_started.get("state", {}).get("map", {}).get("width") != 10:
        raise RuntimeError(f"Dark level one did not start: {status} {dark_started}")
    status, collision = request(
        f"/api/v1/sessions/{dark['session_id']}/games/dark/move",
        "POST",
        {"direction": "up"},
        auth(dark),
    )
    if status != 200 or not collision.get("outcome", {}).get("collision"):
        raise RuntimeError(f"Dark collision was not enforced: {status} {collision}")
    dark_events = []
    dark_ready = threading.Event()
    dark_socket = socketio.Client()

    @dark_socket.event
    def connect():
        dark_ready.set()

    @dark_socket.on("ia:event")
    def dark_event(data):
        dark_events.append(data)

    dark_socket.connect(API, auth={"token": dark["token"]}, transports=["websocket"])
    if not dark_ready.wait(5):
        raise RuntimeError("Dark Socket.IO connection did not become ready")
    status, _ = request(
        "/api/v1/demo/events",
        "POST",
        {"session_id": dark["session_id"], "type": "gift", "actor": "e2e-viewer", "payload": {"gift": "Rose", "count": 1}},
    )
    for _ in range(50):
        if dark_events:
            break
        time.sleep(0.05)
    if status != 202 or len(dark_events) != 1:
        raise RuntimeError(f"Dark did not receive its simulated event: {status} {dark_events}")
    if dark_events[0].get("source") != "test":
        raise RuntimeError(f"Dark did not receive a normalized Test event: {dark_events}")
    dark_socket.disconnect()
    close_session(dark)
    status, closed_dark = request(
        f"/api/v1/sessions/{dark['session_id']}/games/dark/state",
        headers=auth(dark),
    )
    if status != 200 or closed_dark.get("state", {}).get("status") != "ended":
        raise RuntimeError(f"Dark run stayed active after session closure: {status} {closed_dark}")

    marble = create_demo_session("marble")
    status, started = request(
        f"/api/v1/sessions/{marble['session_id']}/games/marble/start",
        "POST",
        {"config": {"gift_target": 2, "like_target": 10, "like_unit": 1}},
        auth(marble),
    )
    if status != 201 or started.get("state", {}).get("status") != "active":
        raise RuntimeError(f"Marble round did not start: {status} {started}")

    marble_states = []
    marble_socket = socketio.Client()

    @marble_socket.on("ia:game_state")
    def marble_state(data):
        marble_states.append(data)

    marble_socket.connect(API, auth={"token": marble["token"]}, transports=["websocket"])
    status, _ = request(
        "/api/v1/demo/events",
        "POST",
        {"session_id": marble["session_id"], "type": "gift", "actor": "e2e-viewer", "payload": {"gift": "Rose", "count": 2}},
    )
    for _ in range(50):
        if any(message.get("state", {}).get("status") == "finished" for message in marble_states):
            break
        time.sleep(0.05)
    marble_socket.disconnect()
    state_status, state = request(
        f"/api/v1/sessions/{marble['session_id']}/games/marble/state",
        headers=auth(marble),
    )
    round_state = state.get("state", {})
    if status != 202 or state_status != 200 or round_state.get("winner") != "GIFTS":
        raise RuntimeError(f"Marble did not persist the simulated result: {state_status} {state}")
    close_session(marble)

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({"dark": dark, "marble": marble, "winner": round_state["winner"]}),
        encoding="utf-8",
    )
    STATE_FILE.chmod(0o600)
    print(json.dumps({
        "status": "ok",
        "phase": "journey",
        "dark_level": dark_started["state"]["level"],
        "dark_collision": True,
        "dark_events": len(dark_events),
        "marble_winner": round_state["winner"],
    }))


def verify():
    saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    marble = saved["marble"]
    status, health = request("/health/ready")
    if status != 200 or health.get("status") != "ok":
        raise RuntimeError(f"runtime did not recover after restart: {status} {health}")
    status, state = request(
        f"/api/v1/sessions/{marble['session_id']}/games/marble/state",
        headers=auth(marble),
    )
    if status != 200 or state.get("state", {}).get("winner") != saved["winner"]:
        raise RuntimeError(f"Marble state was not preserved across restart: {status} {state}")
    status, rejected = request(
        "/api/v1/demo/events",
        "POST",
        {"session_id": marble["session_id"], "type": "gift", "actor": "late-viewer", "payload": {"gift": "Rose", "count": 1}},
    )
    if status != 409 or rejected.get("error") != "session_inactive":
        raise RuntimeError(f"closed session accepted an event after restart: {status} {rejected}")
    status, diagnostics = request(
        "/api/v1/diagnostics",
        headers={"Authorization": f"Bearer {OBSERVER_TOKEN}"},
    )
    if status != 200 or not diagnostics.get("health", {}).get("worker", {}).get("ok"):
        raise RuntimeError(f"diagnostics are not healthy after restart: {status} {diagnostics}")
    print(json.dumps({
        "status": "ok",
        "phase": "post-restart",
        "health": health["status"],
        "marble_winner": state["state"]["winner"],
        "closed_event_rejected": True,
        "diagnostics": "healthy",
    }))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("journey", "verify"))
    args = parser.parse_args()
    journey() if args.phase == "journey" else verify()


if __name__ == "__main__":
    main()
