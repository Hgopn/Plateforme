"""InterArcade V2 Flask application factory."""

from __future__ import annotations

import secrets
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

from .auth import issue_token, verify_token
from .config import Config
from .events import event_from_tiktok
from .licenses import LicenseStore
from .models import Listener, RuntimeRegistry, Session, Tenant, utc_now
from .worker.tiktok import TikTokWorker


socketio = SocketIO()


def _bearer_token():
    value = request.headers.get("Authorization", "")
    return value[7:].strip() if value.lower().startswith("bearer ") else ""


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    origins = config_class.origins()
    allowed_origins = origins or ["http://localhost:5000"]
    CORS(app, origins=allowed_origins)
    socketio.init_app(app, cors_allowed_origins=allowed_origins)

    licenses = LicenseStore(config_class.load_licenses())
    registry = RuntimeRegistry()
    app.extensions["licenses"] = licenses
    app.extensions["registry"] = registry

    def publish_event(event):
        socketio.emit("ia:event", event.to_dict(), to=f"tenant:{event.tenant_id}")

    def authorize_request(data, game_id=None):
        token = _bearer_token() or (data or {}).get("license_key", "")
        if config_class.ADMIN_TOKEN and secrets.compare_digest(token, config_class.ADMIN_TOKEN):
            return Tenant(data.get("tenant_id") or data.get("username"), data.get("username") or data.get("tenant_id"), games=[])
        tenant_id = (data or {}).get("tenant_id") or (data or {}).get("username")
        return licenses.authorize(tenant_id or "", token, game_id=game_id)

    def authorize_admin():
        token = _bearer_token()
        return bool(config_class.ADMIN_TOKEN) and secrets.compare_digest(token, config_class.ADMIN_TOKEN)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "interarcade-api", "version": 2})

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
        tenant = Tenant(tenant_id, username, games=list(getattr(license_item, "games", [])))
        registry.tenants[tenant_id] = tenant
        registry.sessions[session_id] = Session(session_id, tenant_id, username, game_id=game_id)
        token = issue_token(app.config["SESSION_SECRET"], {"tenant_id": tenant_id, "session_id": session_id})
        return jsonify({"session_id": session_id, "token": token, "tenant_id": tenant_id}), 201

    @app.get("/api/v1/listeners")
    def listener_status():
        token = _bearer_token()
        if not config_class.ADMIN_TOKEN or not secrets.compare_digest(token, config_class.ADMIN_TOKEN):
            return jsonify({"error": "unauthorized"}), 401
        return jsonify({"listeners": [listener.__dict__ | {"worker": None} for listener in registry.list_listeners()]})

    @app.post("/api/v1/listeners/start")
    @app.post("/start_listener")
    def start_listener():
        data = request.get_json(silent=True) or {}
        tenant_id = (data.get("tenant_id") or data.get("username") or "").strip()
        username = (data.get("username") or tenant_id).strip()
        if not authorize_admin() or not tenant_id or not username:
            return jsonify({"error": "unauthorized_or_missing_identity"}), 401
        current = registry.get_listener(tenant_id)
        if current and current.status == "running":
            return jsonify({"status": "already_running", "tenant_id": tenant_id}), 200
        session_id = data.get("session_id") or secrets.token_urlsafe(18)
        event_sink = lambda event_type, actor, **payload: publish_event(
            event_from_tiktok(tenant_id, session_id, event_type, actor, **payload)
        )
        worker = TikTokWorker(username, tenant_id, session_id, event_sink, config_class.TIKTOK_SIGN_API_KEY)
        listener = Listener(tenant_id, username, status="running", started_at=utc_now(), worker=worker)
        registry.put_listener(listener)
        worker.start()
        return jsonify({"status": "started", "tenant_id": tenant_id, "session_id": session_id}), 202

    @app.post("/api/v1/listeners/stop")
    @app.post("/stop_listener")
    def stop_listener():
        data = request.get_json(silent=True) or {}
        tenant_id = (data.get("tenant_id") or data.get("username") or "").strip()
        listener = registry.get_listener(tenant_id)
        if not authorize_admin() or not tenant_id or not listener:
            return jsonify({"error": "unauthorized_or_not_found"}), 404
        listener.worker.stop()
        listener.status = "stopping"
        return jsonify({"status": "stopping", "tenant_id": tenant_id}), 202

    @app.post("/api/v1/internal/events")
    def internal_event():
        token = request.headers.get("X-InterArcade-Internal-Token", "")
        if not config_class.INTERNAL_EVENT_TOKEN or not secrets.compare_digest(
            token, config_class.INTERNAL_EVENT_TOKEN
        ):
            return jsonify({"error": "unauthorized"}), 401
        data = request.get_json(silent=True) or {}
        required = ("tenant_id", "session_id", "type", "actor")
        if any(not data.get(key) for key in required):
            return jsonify({"error": "invalid_event"}), 400
        try:
            event = event_from_tiktok(
                data["tenant_id"],
                data["session_id"],
                data["type"],
                data["actor"],
                **(data.get("payload") or {}),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        publish_event(event)
        return jsonify(event.to_dict()), 202

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
    socketio.run(app, host=app.config["HOST"], port=app.config["PORT"])
