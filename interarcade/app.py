"""InterArcade V2 Flask application factory."""

from __future__ import annotations

import secrets
import logging
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

from .auth import issue_token, verify_token
from .broker import Broker
from .config import Config
from .database import Database
from .events import event_from_tiktok
from .logging import configure_logging
from .licenses import LicenseStore
from .models import RuntimeRegistry, Session, Tenant


socketio = SocketIO()


def _bearer_token():
    value = request.headers.get("Authorization", "")
    return value[7:].strip() if value.lower().startswith("bearer ") else ""


def create_app(config_class=Config):
    configure_logging(config_class.LOG_LEVEL)
    logger = logging.getLogger("interarcade.api")
    app = Flask(__name__)
    app.config.from_object(config_class)
    database = Database(config_class.DATABASE_URL)
    database.initialize()
    broker = Broker(config_class.BROKER_URL)
    origins = config_class.origins()
    allowed_origins = origins or ["http://localhost:5000"]
    CORS(app, origins=allowed_origins)
    socketio.init_app(
        app,
        cors_allowed_origins=allowed_origins,
        message_queue=config_class.BROKER_URL or None,
    )

    licenses = LicenseStore(config_class.load_licenses())
    registry = RuntimeRegistry()
    app.extensions["licenses"] = licenses
    app.extensions["registry"] = registry
    app.extensions["database"] = database
    app.extensions["broker"] = broker

    def publish_event(event):
        socketio.emit("ia:event", event.to_dict(), to=f"tenant:{event.tenant_id}")

    def authorize_request(data, game_id=None):
        token = _bearer_token() or (data or {}).get("license_key", "")
        if config_class.ADMIN_TOKEN and secrets.compare_digest(token, config_class.ADMIN_TOKEN):
            return Tenant(data.get("tenant_id") or data.get("username"), data.get("username") or data.get("tenant_id"), games=[])
        tenant_id = (data or {}).get("tenant_id") or (data or {}).get("username")
        item = database.license_for(tenant_id or "", token)
        if item and (not game_id or game_id in item["games"]):
            return item
        return licenses.authorize(tenant_id or "", token, game_id=game_id)

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
        }), (200 if database_ok and worker_ok else 503)

    @app.get("/health/live")
    def health_live():
        return jsonify({"status": "ok", "service": "interarcade-api"})

    @app.get("/health/ready")
    def health_ready():
        response = health()
        return response

    @app.get("/games/manifest.json")
    def games_manifest():
        return jsonify({"schema_version": 1, "games": ["slot", "dark", "marble", "fight"]})

    @app.get("/games/<path:filename>")
    def serve_game_file(filename):
        return send_from_directory(Path(app.config["GAMES_DIR"]), filename)

    @app.post("/api/v1/sessions")
    def create_session():
        data = request.get_json(silent=True) or {}
        tenant_id = (data.get("tenant_id") or data.get("username") or "").strip()
        game_id = (data.get("game_id") or "").strip() or None
        license_item = authorize_request(data, game_id=game_id)
        if not license_item:
            return jsonify({"error": "unauthorized"}), 401
        username = data.get("username") or tenant_id
        session_id = secrets.token_urlsafe(18)
        games = license_item.get("games", []) if isinstance(license_item, dict) else list(getattr(license_item, "games", []))
        tenant = Tenant(tenant_id, username, games=list(games))
        registry.tenants[tenant_id] = tenant
        registry.sessions[session_id] = Session(session_id, tenant_id, username, game_id=game_id)
        database.upsert_tenant(tenant_id, username)
        database.upsert_user(f"user:{tenant_id}:{username}", tenant_id, username, role="viewer")
        database.save_session(session_id, tenant_id, game_id)
        token = issue_token(app.config["SESSION_SECRET"], {"tenant_id": tenant_id, "session_id": session_id})
        return jsonify({"session_id": session_id, "token": token, "tenant_id": tenant_id}), 201

    @app.get("/api/v1/listeners")
    def listener_status():
        if not authorize_admin():
            return jsonify({"error": "unauthorized"}), 401
        return jsonify({"listeners": database.listeners()})

    @app.post("/api/v1/listeners/start")
    @app.post("/start_listener")
    def start_listener():
        data = request.get_json(silent=True) or {}
        tenant_id = (data.get("tenant_id") or data.get("username") or "").strip()
        username = (data.get("username") or tenant_id).strip()
        if not authorize_admin() or not tenant_id or not username:
            return jsonify({"error": "unauthorized_or_missing_identity"}), 401
        if not database.fetchone("SELECT id FROM tenants WHERE id = ? AND enabled = 1", (tenant_id,)):
            return jsonify({"error": "tenant_not_found"}), 404
        current = next((row for row in database.listeners() if row["tenant_id"] == tenant_id), None)
        if current and current["status"] in {"running", "starting"}:
            return jsonify({"status": "already_running", "tenant_id": tenant_id}), 200
        session_id = data.get("session_id") or secrets.token_urlsafe(18)
        database.upsert_tenant(tenant_id, username)
        database.save_session(session_id, tenant_id, data.get("game_id"))
        database.save_listener(tenant_id, username, session_id, "starting")
        return jsonify({"status": "started", "tenant_id": tenant_id, "session_id": session_id}), 202

    @app.post("/api/v1/listeners/stop")
    @app.post("/stop_listener")
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
            event = event_from_tiktok(
                data["tenant_id"],
                data["session_id"],
                data["type"],
                data["actor"],
                event_id=data.get("event_id"),
                **payload,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if database.record_event(event.to_dict()):
            publish_event(event)
        return jsonify(event.to_dict()), 202

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
        tenant_id = claims.get("tenant_id") if claims else None
        if not tenant_id and config_class.LEGACY_SOCKET_QUERY_AUTH:
            tenant_id = request.args.get("username", "").strip() or None
        if not tenant_id:
            return False
        from flask_socketio import join_room

        join_room(f"tenant:{tenant_id}")
        emit("ia:ready", {"schema_version": 1, "tenant_id": tenant_id})

    return app


app = create_app()


if __name__ == "__main__":
    # The integration stack is intentionally local-only. Public deployments
    # must use a production WSGI/Socket.IO server instead of Werkzeug.
    socketio.run(
        app,
        host=app.config["HOST"],
        port=app.config["PORT"],
        allow_unsafe_werkzeug=True,
    )
