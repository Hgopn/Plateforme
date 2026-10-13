"""InterArcade V2 Flask application factory."""

from __future__ import annotations

import logging
import secrets
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

from .auth import issue_token, verify_token
from .broker import Broker
from .config import Config
from .database import Database
from .events import event_from_source
from .logging import configure_logging


socketio = SocketIO()
SUPPORTED_GAMES = ("slot", "dark", "marble", "fight")


def _bearer_token():
    value = request.headers.get("Authorization", "")
    return value[7:].strip() if value.lower().startswith("bearer ") else ""


def create_app(config_class=Config):
    if not config_class.SESSION_SECRET:
        raise RuntimeError("INTERARCADE_SESSION_SECRET is required")
    configure_logging(config_class.LOG_LEVEL)
    logger = logging.getLogger("interarcade.api")
    project_dir = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=str(project_dir / "templates"),
        static_folder=str(project_dir / "static"),
    )
    app.config.from_object(config_class)
    database = Database(config_class.DATABASE_URL)
    database.initialize()
    broker = Broker(config_class.BROKER_URL)
    origins = config_class.origins()
    if origins:
        CORS(app, origins=origins)
    socketio.init_app(
        app,
        cors_allowed_origins=origins or None,
        message_queue=config_class.BROKER_URL or None,
    )

    app.extensions["database"] = database
    app.extensions["broker"] = broker

    def publish_event(event):
        socketio.emit("ia:event", event.to_dict(), to=f"session:{event.session_id}")

    def publish_marble_state(session_id, state):
        if not state:
            return
        session = database.session(session_id)
        if session:
            socketio.emit(
                "ia:game_state",
                {"schema_version": 1, "game_id": "marble", "session_id": session_id, "state": state},
                to=f"session:{session_id}",
            )

    def publish_dark_state(session_id, state, outcome=None):
        if not state:
            return
        from .games.dark import public_state

        socketio.emit(
            "ia:game_state",
            {
                "schema_version": 1,
                "game_id": "dark",
                "session_id": session_id,
                "state": public_state(state),
                "outcome": outcome,
            },
            to=f"session:{session_id}",
        )

    def process_event(event):
        session = database.session(event.session_id)
        if not session:
            return False, None, "session_not_found"
        if session["tenant_id"] != event.tenant_id:
            return False, None, "session_tenant_mismatch"
        if session.get("status") != "active":
            return False, None, "session_inactive"
        marble_state = None
        if session.get("game_id") == "marble":
            round_state = database.marble_round(event.session_id)
            if round_state and round_state["status"] == "active":
                accepted, marble_state = database.apply_marble_event(event.to_dict(), round_state["config"])
            else:
                accepted = database.record_event(event.to_dict())
        else:
            accepted = database.record_event(event.to_dict())
        if accepted:
            publish_event(event)
            publish_marble_state(event.session_id, marble_state)
        return bool(accepted), marble_state, None if accepted else "duplicate_event"

    def authorize_request(data, game_id=None):
        token = _bearer_token() or (data or {}).get("license_key", "")
        if config_class.ADMIN_TOKEN and secrets.compare_digest(token, config_class.ADMIN_TOKEN):
            return {"games": list(SUPPORTED_GAMES)}
        tenant_id = (data or {}).get("tenant_id") or (data or {}).get("username")
        item = database.license_for(tenant_id or "", token)
        return item if item and (not game_id or game_id in item["games"]) else None

    def authorize_admin():
        token = _bearer_token()
        return bool(config_class.ADMIN_TOKEN) and secrets.compare_digest(token, config_class.ADMIN_TOKEN)

    @app.get("/health")
    def health():
        database_ok = False
        try:
            database_ok = database.ping()
        except Exception as exc:
            logger.error("database healthcheck failed", exc_info=exc, extra={"component": "database"})
        broker_ok = broker.ping()
        workers = []
        heartbeat = {"ok": False, "worker_id": None, "pid": None, "updated_at": None}
        if database_ok:
            try:
                workers = database.listeners()
                heartbeat = database.worker_heartbeat(config_class.WORKER_HEARTBEAT_TIMEOUT_SECONDS)
            except Exception as exc:
                database_ok = False
                logger.error("database detail healthcheck failed", exc_info=exc, extra={"component": "database"})
        worker_ok = all(row.get("status") != "error" for row in workers)
        if config_class.REQUIRE_WORKER_HEARTBEAT:
            worker_ok = worker_ok and heartbeat["ok"]
        return jsonify({
            "status": "ok" if database_ok and broker_ok and worker_ok else "degraded",
            "service": "interarcade-api",
            "version": config_class.GIT_VERSION,
            "checks": {"database": database_ok, "broker": broker_ok, "worker": worker_ok},
            "worker": {"heartbeat": heartbeat},
        }), (200 if database_ok and broker_ok and worker_ok else 503)

    @app.get("/health/live")
    def health_live():
        return jsonify({"status": "ok", "service": "interarcade-api"})

    @app.get("/health/ready")
    def health_ready():
        response = health()
        return response

    @app.get("/")
    def demo_index():
        if not config_class.DEMO_MODE:
            return jsonify({"error": "demo_disabled"}), 404
        return render_template("demo.html", demo_username=config_class.DEMO_USERNAME)

    @app.get("/games/manifest.json")
    def games_manifest():
        return jsonify({"schema_version": 1, "games": list(SUPPORTED_GAMES)})

    @app.get("/games/<path:filename>")
    def serve_game_file(filename):
        return send_from_directory(Path(app.config["GAMES_DIR"]), filename)

    @app.post("/api/v1/sessions")
    def create_session():
        data = request.get_json(silent=True) or {}
        tenant_id = (data.get("tenant_id") or data.get("username") or "").strip()
        game_id = (data.get("game_id") or "").strip()
        if not tenant_id or game_id not in SUPPORTED_GAMES:
            return jsonify({"error": "invalid_session_request"}), 400
        license_item = authorize_request(data, game_id=game_id)
        if not license_item:
            return jsonify({"error": "unauthorized"}), 401
        username = data.get("username") or tenant_id
        session_id = secrets.token_urlsafe(18)
        database.upsert_tenant(tenant_id, username)
        database.upsert_user(f"user:{tenant_id}:{username}", tenant_id, username, role="viewer")
        database.save_session(session_id, tenant_id, game_id)
        token = issue_token(app.config["SESSION_SECRET"], {"tenant_id": tenant_id, "session_id": session_id})
        return jsonify({"session_id": session_id, "token": token, "tenant_id": tenant_id}), 201

    def authorized_session(session_id):
        claims = verify_token(app.config["SESSION_SECRET"], _bearer_token())
        if not claims or claims.get("session_id") != session_id:
            return None
        session = database.session(session_id)
        return session if session and claims.get("tenant_id") == session["tenant_id"] else None

    @app.post("/api/v1/sessions/<session_id>/games/marble/start")
    def start_marble_round(session_id):
        session = authorized_session(session_id)
        if not session or session.get("status") != "active" or session.get("game_id") != "marble":
            return jsonify({"error": "unauthorized_or_wrong_game"}), 401
        data = request.get_json(silent=True) or {}
        from .games.marble import MarbleConfig

        config = MarbleConfig.from_mapping(data.get("config")).to_dict()
        round_state = database.start_marble_round(secrets.token_urlsafe(18), session_id, config, reset=bool(data.get("reset")))
        publish_marble_state(session_id, round_state)
        return jsonify({"schema_version": 1, "game_id": "marble", "session_id": session_id, "state": round_state}), 201

    @app.get("/api/v1/sessions/<session_id>/games/marble/state")
    def marble_state(session_id):
        session = authorized_session(session_id)
        if not session or session.get("game_id") != "marble":
            return jsonify({"error": "unauthorized_or_wrong_game"}), 401
        return jsonify({"schema_version": 1, "game_id": "marble", "session_id": session_id, "state": database.marble_round(session_id)})

    @app.post("/api/v1/sessions/<session_id>/games/dark/start")
    def start_dark_run(session_id):
        session = authorized_session(session_id)
        if not session or session.get("status") != "active" or session.get("game_id") != "dark":
            return jsonify({"error": "unauthorized_or_wrong_game"}), 401
        state = database.start_dark_run(secrets.token_urlsafe(18), session_id)
        from .games.dark import public_state

        publish_dark_state(session_id, state)
        return jsonify({
            "schema_version": 1,
            "game_id": "dark",
            "session_id": session_id,
            "state": public_state(state),
        }), 201

    @app.get("/api/v1/sessions/<session_id>/games/dark/state")
    def dark_state(session_id):
        session = authorized_session(session_id)
        if not session or session.get("game_id") != "dark":
            return jsonify({"error": "unauthorized_or_wrong_game"}), 401
        from .games.dark import public_state

        return jsonify({
            "schema_version": 1,
            "game_id": "dark",
            "session_id": session_id,
            "state": public_state(database.dark_run(session_id)),
        })

    @app.post("/api/v1/sessions/<session_id>/games/dark/move")
    def move_dark(session_id):
        session = authorized_session(session_id)
        if not session or session.get("status") != "active" or session.get("game_id") != "dark":
            return jsonify({"error": "unauthorized_or_wrong_game"}), 401
        direction = (request.get_json(silent=True) or {}).get("direction")
        if not isinstance(direction, str):
            return jsonify({"error": "invalid_direction"}), 400
        try:
            state, outcome = database.move_dark(session_id, direction)
        except ValueError:
            return jsonify({"error": "invalid_direction"}), 400
        if not state:
            return jsonify({"error": "dark_not_started"}), 409
        from .games.dark import public_state

        publish_dark_state(session_id, state, outcome)
        return jsonify({
            "schema_version": 1,
            "game_id": "dark",
            "session_id": session_id,
            "state": public_state(state),
            "outcome": outcome,
        })

    @app.post("/api/v1/sessions/<session_id>/games/dark/reset")
    def reset_dark(session_id):
        session = authorized_session(session_id)
        if not session or session.get("status") != "active" or session.get("game_id") != "dark":
            return jsonify({"error": "unauthorized_or_wrong_game"}), 401
        state = database.start_dark_run(secrets.token_urlsafe(18), session_id, reset=True)
        from .games.dark import public_state

        outcome = {"moved": False, "collision": False, "transition": {"type": "reset"}}
        publish_dark_state(session_id, state, outcome)
        return jsonify({
            "schema_version": 1,
            "game_id": "dark",
            "session_id": session_id,
            "state": public_state(state),
            "outcome": outcome,
        })

    @app.post("/api/v1/sessions/<session_id>/end")
    def end_session(session_id):
        if not authorized_session(session_id):
            return jsonify({"error": "unauthorized"}), 401
        database.end_session(session_id)
        for listener in database.listeners():
            if listener.get("session_id") == session_id and listener.get("status") in {"starting", "running"}:
                database.update_listener(listener["tenant_id"], "stopping")
        return jsonify({"session_id": session_id, "status": "ended"}), 200

    @app.get("/api/v1/listeners")
    def listener_status():
        if not authorize_admin():
            return jsonify({"error": "unauthorized"}), 401
        return jsonify({"listeners": database.listeners()})

    @app.post("/api/v1/listeners/start")
    def start_listener():
        data = request.get_json(silent=True) or {}
        tenant_id = (data.get("tenant_id") or data.get("username") or "").strip()
        username = (data.get("username") or tenant_id).strip()
        session_id = (data.get("session_id") or "").strip()
        session = database.session(session_id) if session_id else None
        if not authorize_admin() or not tenant_id or not username:
            return jsonify({"error": "unauthorized_or_missing_identity"}), 401
        if not session or session["tenant_id"] != tenant_id or session["status"] != "active":
            return jsonify({"error": "active_session_not_found"}), 404
        current = next((row for row in database.listeners() if row["tenant_id"] == tenant_id), None)
        if current and current["status"] in {"running", "starting"}:
            return jsonify({"status": "already_running", "tenant_id": tenant_id}), 200
        database.save_listener(tenant_id, username, session_id, "starting")
        return jsonify({"status": "started", "tenant_id": tenant_id, "session_id": session_id}), 202

    @app.post("/api/v1/listeners/stop")
    def stop_listener():
        data = request.get_json(silent=True) or {}
        tenant_id = (data.get("tenant_id") or data.get("username") or "").strip()
        listener = next((row for row in database.listeners() if row["tenant_id"] == tenant_id), None)
        if not authorize_admin() or not tenant_id or not listener:
            return jsonify({"error": "unauthorized_or_not_found"}), 404
        database.update_listener(tenant_id, "stopping")
        return jsonify({"status": "stopping", "tenant_id": tenant_id}), 202

    @app.post("/api/v1/internal/events")
    def internal_event():
        token = request.headers.get("X-InterArcade-Internal-Token", "")
        if not config_class.INTERNAL_EVENT_TOKEN or not secrets.compare_digest(
            token, config_class.INTERNAL_EVENT_TOKEN
        ):
            return jsonify({"error": "unauthorized"}), 401
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict) or data.get("schema_version", 1) != 1:
            return jsonify({"error": "unsupported_event_schema"}), 400
        required = ("tenant_id", "session_id", "type", "actor")
        if any(not isinstance(data.get(key), str) or not data.get(key).strip() for key in required):
            return jsonify({"error": "invalid_event"}), 400
        payload = data.get("payload", {})
        if not isinstance(payload, dict):
            return jsonify({"error": "invalid_event_payload"}), 400
        try:
            event = event_from_source(
                data.get("source", "tiktok"),
                data["tenant_id"],
                data["session_id"],
                data["type"],
                data["actor"],
                event_id=data.get("event_id"),
                **payload,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        accepted, _, rejection = process_event(event)
        if rejection == "session_not_found":
            return jsonify({"error": rejection}), 404
        if rejection in {"session_tenant_mismatch", "session_inactive"}:
            return jsonify({"error": rejection}), 409
        response = event.to_dict()
        response["accepted"] = accepted
        return jsonify(response), (202 if accepted else 200)

    @app.get("/api/v1/demo/status")
    def demo_status():
        if not config_class.DEMO_MODE:
            return jsonify({"error": "demo_disabled"}), 404
        health_response, _ = health()
        health_data = health_response.get_json()
        return jsonify({
            "version": config_class.GIT_VERSION,
            "health": {
                "api": health_data["status"] == "ok",
                "worker": health_data["checks"]["worker"],
                "database": health_data["checks"]["database"],
            },
        })

    @app.post("/api/v1/demo/session")
    def demo_session():
        if not config_class.DEMO_MODE:
            return jsonify({"error": "demo_disabled"}), 404
        data = request.get_json(silent=True) or {}
        game_id = (data.get("game_id") or "").strip()
        if game_id not in SUPPORTED_GAMES:
            return jsonify({"error": "invalid_game"}), 400
        tenant_id = config_class.DEMO_TENANT_ID
        username = config_class.DEMO_USERNAME
        session_id = secrets.token_urlsafe(18)
        database.upsert_tenant(tenant_id, username)
        database.upsert_user(f"demo:{tenant_id}:{username}", tenant_id, username, role="viewer")
        database.save_session(session_id, tenant_id, game_id)
        token = issue_token(app.config["SESSION_SECRET"], {"tenant_id": tenant_id, "session_id": session_id})
        return jsonify({"session_id": session_id, "token": token, "tenant_id": tenant_id, "username": username}), 201

    @app.post("/api/v1/demo/events")
    def demo_event():
        if not config_class.DEMO_MODE:
            return jsonify({"error": "demo_disabled"}), 404
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        session = database.session(session_id) if isinstance(session_id, str) else None
        if not session or session["tenant_id"] != config_class.DEMO_TENANT_ID:
            return jsonify({"error": "invalid_demo_session"}), 400
        payload = data.get("payload", {})
        required = (data.get("type"), data.get("actor"))
        if not all(isinstance(value, str) and value.strip() for value in required) or not isinstance(payload, dict):
            return jsonify({"error": "invalid_event"}), 400
        try:
            event = event_from_source(
                "test",
                config_class.DEMO_TENANT_ID,
                session_id,
                data["type"],
                data["actor"],
                **payload,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        accepted, _, rejection = process_event(event)
        if rejection:
            status = 404 if rejection == "session_not_found" else 409
            return jsonify({"error": rejection}), status
        response = event.to_dict()
        response["accepted"] = accepted
        return jsonify(response), 202

    @app.get("/api/v1/diagnostics")
    def diagnostics():
        token = _bearer_token()
        allowed = config_class.OBSERVER_TOKEN or config_class.ADMIN_TOKEN
        if not allowed or not secrets.compare_digest(token, allowed):
            return jsonify({"error": "unauthorized"}), 401
        try:
            database_health = database.ping()
            worker_health = database.worker_heartbeat(config_class.WORKER_HEARTBEAT_TIMEOUT_SECONDS) if database_health else {"ok": False}
            listeners = database.listeners() if database_health else []
            sessions = database.session_summary() if database_health else {}
            recent_errors = database.recent_errors() if database_health else []
        except Exception as exc:
            logger.error("diagnostics database check failed", exc_info=exc, extra={"component": "database"})
            database_health = False
            worker_health = {"ok": False, "error": "database_unavailable"}
            listeners, sessions, recent_errors = [], {}, []
        return jsonify({
            "service": "interarcade-api",
            "version": config_class.GIT_VERSION,
            "health": {
                "database": database_health,
                "broker": broker.ping(),
                "worker": worker_health,
            },
            "listeners": listeners,
            "sessions": sessions,
            "recent_errors": recent_errors,
        })

    @socketio.on("connect")
    def socket_connect(auth=None):
        auth = auth or {}
        claims = verify_token(app.config["SESSION_SECRET"], auth.get("token", ""))
        session_id = claims.get("session_id") if claims else None
        session = database.session(session_id) if session_id else None
        if (
            not claims
            or not session
            or session["status"] != "active"
            or claims.get("tenant_id") != session["tenant_id"]
        ):
            return False
        from flask_socketio import join_room

        join_room(f"session:{session_id}")
        emit("ia:ready", {"schema_version": 1, "tenant_id": session["tenant_id"], "session_id": session_id})

    return app
