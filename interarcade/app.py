"""InterArcade V2 Flask application factory."""

from __future__ import annotations

import logging
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

from .auth import issue_token, verify_token
from .broker import Broker
from .config import Config
from .creator_auth import check_password, hash_password, normalize_email, normalize_tiktok, valid_password
from .database import Database
from .dark_tiktok_mapping import DarkTikTokMapping, mapped_action_event
from .events import PLATFORM_PATTERN, event_from_source
from .logging import configure_logging


socketio = SocketIO()
SUPPORTED_GAMES = ("slot", "dark", "marble", "fight")
ACTIVE_SOURCE_STATUSES = {"starting", "running", "connecting", "connected", "offline", "reconnecting"}
RESERVED_EVENT_FIELDS = {
    "source", "tenant_id", "session_id", "event_type", "type", "actor", "event_id",
    "source_account_id", "source_username", "actor_platform_id", "timestamp", "event_value",
}


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
    dark_tiktok_mapping = DarkTikTokMapping.from_path(config_class.DARK_TIKTOK_MAPPING_PATH)
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
    app.extensions["dark_tiktok_mapping"] = dark_tiktok_mapping
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

    @app.after_request
    def secure_response(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        game_asset = request.path.startswith("/games/")
        frame_ancestors = "'self'" if game_asset else "'none'"
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN" if game_asset else "DENY")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'none'; object-src 'none'; "
            f"frame-ancestors {frame_ancestors}; "
            "form-action 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self' ws: wss:; frame-src 'self'",
        )
        if request.path.startswith("/api/v1/creator/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def login_token():
        return request.cookies.get("ia_creator", "")

    def csrf_for(token):
        return hmac.new(app.config["SESSION_SECRET"].encode(), token.encode(), hashlib.sha256).hexdigest()

    def current_creator():
        token = login_token()
        if not token:
            return None
        login = database.creator_login(hashlib.sha256(token.encode()).hexdigest())
        if not login or login["expires_at"] <= datetime.now(timezone.utc).isoformat():
            return None
        account = database.creator_account(login["account_id"])
        if not account or not account["enabled"]:
            return None
        return account, login

    def creator_or_error(mutation=False):
        creator = current_creator()
        if not creator:
            return None
        if mutation:
            supplied = request.headers.get("X-CSRF-Token", "")
            actual = hashlib.sha256(supplied.encode()).hexdigest()
            if not supplied or not secrets.compare_digest(actual, creator[1]["csrf_hash"]):
                return None
        return creator[0]

    def same_site_request():
        origin = request.headers.get("Origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        expected_scheme = "https" if config_class.COOKIE_SECURE else request.scheme
        return parsed.scheme == expected_scheme and parsed.netloc == request.host

    def auth_limit(scope, subject, limit):
        key = hmac.new(app.config["SESSION_SECRET"].encode(),
                       f"{scope}:{subject}".encode(), hashlib.sha256).hexdigest()
        return database.consume_auth_limit(key, limit, 15 * 60)

    def auth_attempt_allowed(action, email=None):
        client_ip = (request.headers.get("X-InterArcade-Client-IP")
                     if config_class.TRUST_PROXY_CLIENT_IP else None) or request.remote_addr or "unknown"
        if not auth_limit(f"{action}:ip", client_ip, 30 if action == "login" else 10):
            return False
        return not email or auth_limit(f"{action}:email", email, 10 if action == "login" else 5)

    def auth_throttled():
        response = jsonify({"error": "too_many_attempts"})
        response.headers["Retry-After"] = "900"
        return response, 429

    def set_creator_cookie(response, account_id, remember):
        token = secrets.token_urlsafe(32)
        age = 30 * 86400 if remember else 12 * 3600
        expires = (datetime.now(timezone.utc) + timedelta(seconds=age)).isoformat()
        csrf = csrf_for(token)
        database.save_creator_login(
            hashlib.sha256(token.encode()).hexdigest(), account_id,
            hashlib.sha256(csrf.encode()).hexdigest(), expires,
        )
        response.set_cookie(
            "ia_creator", token, max_age=age, httponly=True, secure=bool(config_class.COOKIE_SECURE),
            samesite="Strict", path="/",
        )
        return response, csrf

    def creator_summary(account):
        return {
            "email": account["email"], "tenant_id": account["tenant_id"],
            "active": bool(account["enabled"]),
            "entitled_games": database.entitled_games(account["tenant_id"]),
            "platforms": database.creator_platforms(account["id"]),
        }

    def publish_event(event):
        socketio.emit("ia:event", event.to_dict(), to=f"session:{event.session_id}")

    def publish_dark_action(action):
        socketio.emit("ia:action", action, to=f"session:{action['session_id']}")

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

    def process_event(event, require_source=False):
        session = database.session(event.session_id)
        if not session:
            return False, None, "session_not_found"
        if session["tenant_id"] != event.tenant_id:
            return False, None, "session_tenant_mismatch"
        if session.get("status") != "active":
            return False, None, "session_inactive"
        if require_source:
            source = database.live_source_for_session(
                event.session_id, event.source_platform, event.source_account_id
            )
            if not source or source["tenant_id"] != event.tenant_id or source["status"] not in {
                "starting", "connecting", "connected", "running", "reconnecting", "simulated"
            }:
                return False, None, "source_inactive"
        dark_action = None
        if event.type == "action":
            if session.get("game_id") != "dark":
                return False, None, "action_requires_dark_session"
            run = database.dark_run(event.session_id)
            if not run or run["status"] != "active":
                return False, None, "dark_run_inactive"
            from .games.dark_actions import action_from_event

            try:
                dark_action = action_from_event(event)
            except ValueError:
                return False, None, "invalid_dark_action"
        if session.get("game_id") == "dark" and event.source_platform == "tiktok" and event.type != "action":
            run = database.dark_run(event.session_id)
            if run and run["status"] == "active":
                if config_class.TIKTOK_DARK_TRACE:
                    logger.info("tiktok_event_received", extra={
                        "component": "dark_live", "event_id": event.event_id,
                        "source_platform": event.source_platform,
                        "session_id": event.session_id, "source_account_id": event.source_account_id,
                        "event_type": event.type, "gift_id": event.payload.get("gift_id"),
                        "gift_name": event.payload.get("gift_name"),
                        "repeat_count": event.payload.get("repeat_count"),
                    })

                def build_action(source_event, threshold_crossed):
                    decision = dark_tiktok_mapping.decide(source_event, threshold_crossed)
                    action_event = mapped_action_event(source_event, decision.action_type) \
                        if decision.action_type else None
                    return action_event, decision

                accepted, mapped_event, decision, like_total = database.record_dark_tiktok_event(
                    event, dark_tiktok_mapping.like_threshold, build_action
                )
                if accepted:
                    publish_event(event)
                    action = None
                    if mapped_event:
                        publish_event(mapped_event)
                        from .games.dark_actions import action_from_event

                        action = action_from_event(mapped_event)
                        publish_dark_action(action)
                    if config_class.TIKTOK_DARK_TRACE:
                        logger.info("tiktok_dark_mapping", extra={
                            "component": "dark_live", "event_id": event.event_id,
                            "source_platform": event.source_platform,
                            "event_type": event.type, "action_type": decision.action_type,
                            "reason": decision.reason, "like_total": like_total,
                            "gift_id": event.payload.get("gift_id"),
                            "gift_name": event.payload.get("gift_name"),
                        })
                        if action:
                            logger.info("dark_action_delivered", extra={
                                "component": "dark_live", "event_id": action["event_id"],
                                "source_platform": event.source_platform,
                                "original_event_id": event.event_id,
                                "session_id": event.session_id, "action_type": action["action_type"],
                            })
                elif config_class.TIKTOK_DARK_TRACE:
                    logger.info("tiktok_event_duplicate", extra={
                        "component": "dark_live", "event_id": event.event_id,
                        "source_platform": event.source_platform,
                        "session_id": event.session_id, "event_type": event.type,
                    })
                return bool(accepted), action if accepted else None, None if accepted else "duplicate_event"
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
            if dark_action:
                publish_dark_action(dark_action)
            publish_marble_state(event.session_id, marble_state)
        return bool(accepted), dark_action or marble_state, None if accepted else "duplicate_event"

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
            logger.error("database healthcheck failed", extra={"component": "database", "error_type": type(exc).__name__})
        broker_ok = broker.ping()
        workers = []
        heartbeat = {"ok": False, "worker_id": None, "pid": None, "updated_at": None}
        if database_ok:
            try:
                workers = database.live_sources()
                heartbeat = database.worker_heartbeat(config_class.WORKER_HEARTBEAT_TIMEOUT_SECONDS)
            except Exception as exc:
                database_ok = False
                logger.error("database detail healthcheck failed", extra={"component": "database", "error_type": type(exc).__name__})
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
    def site_index():
        return render_template("site.html")

    @app.get("/launcher")
    def launcher_index():
        return render_template("launcher.html")

    @app.get("/broadcast/waiting")
    def broadcast_waiting():
        return render_template("broadcast_waiting.html")

    @app.get("/demo")
    def demo_index():
        if not config_class.DEMO_MODE:
            return jsonify({"error": "demo_disabled"}), 404
        return render_template("demo.html", demo_username=config_class.DEMO_USERNAME)

    @app.post("/api/v1/creator/register")
    def creator_register():
        if not same_site_request():
            return jsonify({"error": "origin_rejected"}), 403
        data = request.get_json(silent=True)
        data = data if isinstance(data, dict) else {}
        email = normalize_email(data.get("email"))
        password = data.get("password")
        if not auth_attempt_allowed("register", email):
            return auth_throttled()
        if not email or not valid_password(password):
            return jsonify({"error": "invalid_registration"}), 400
        account_id = secrets.token_urlsafe(18)
        tenant_id = f"creator:{account_id}"
        try:
            database.create_creator_account(account_id, tenant_id, email, hash_password(password))
        except ValueError:
            return jsonify({"error": "email_already_registered"}), 409
        account = database.creator_account(account_id)
        response = jsonify(creator_summary(account))
        response, csrf = set_creator_cookie(response, account_id, data.get("remember") is True)
        response.set_data(json.dumps({**creator_summary(account), "csrf_token": csrf}))
        return response, 201

    @app.post("/api/v1/creator/login")
    def creator_login():
        if not same_site_request():
            return jsonify({"error": "origin_rejected"}), 403
        data = request.get_json(silent=True)
        data = data if isinstance(data, dict) else {}
        email = normalize_email(data.get("email"))
        password = data.get("password")
        if not auth_attempt_allowed("login", email):
            return auth_throttled()
        account = database.creator_account_by_email(email) if email else None
        # Run the same password work for unknown and disabled accounts.
        dummy_hash = "pbkdf2_sha256$600000$00000000000000000000000000000000$" + "00" * 32
        password_ok = check_password(password, account["password_hash"] if account else dummy_hash) \
            if valid_password(password) else False
        if not account or not account["enabled"] or not password_ok:
            return jsonify({"error": "invalid_credentials"}), 401
        response = jsonify(creator_summary(account))
        response, csrf = set_creator_cookie(response, account["id"], data.get("remember") is True)
        response.set_data(json.dumps({**creator_summary(account), "csrf_token": csrf}))
        return response

    @app.get("/api/v1/creator/me")
    def creator_me():
        creator = current_creator()
        if not creator:
            return jsonify({"error": "unauthorized"}), 401
        return jsonify({**creator_summary(creator[0]), "csrf_token": csrf_for(login_token())})

    @app.post("/api/v1/creator/logout")
    def creator_logout():
        account = creator_or_error(mutation=True)
        if not account:
            return jsonify({"error": "unauthorized"}), 401
        database.revoke_creator_login(hashlib.sha256(login_token().encode()).hexdigest())
        response = jsonify({"status": "signed_out"})
        response.delete_cookie("ia_creator", path="/")
        return response

    @app.post("/api/v1/creator/platforms/tiktok")
    def configure_creator_tiktok():
        account = creator_or_error(mutation=True)
        if not account:
            return jsonify({"error": "unauthorized"}), 401
        data = request.get_json(silent=True)
        data = data if isinstance(data, dict) else {}
        username = normalize_tiktok(data.get("username"))
        if not username:
            return jsonify({"error": "invalid_tiktok_username"}), 400
        database.configure_creator_platform(account["id"], "tiktok", username)
        return jsonify({"platform": "tiktok", "username": username, "status": "configured"})

    @app.post("/api/v1/creator/sessions")
    def create_creator_session():
        account = creator_or_error(mutation=True)
        if not account:
            return jsonify({"error": "unauthorized"}), 401
        data = request.get_json(silent=True)
        data = data if isinstance(data, dict) else {}
        mode = data.get("mode")
        if data.get("game_id") != "dark" or mode not in {"test", "live"}:
            return jsonify({"error": "game_unavailable"}), 400
        database.expire_abandoned_sessions(config_class.CREATOR_SESSION_LEASE_SECONDS)
        try:
            session_id, created = database.launch_creator_dark_session(
                account["id"], account["tenant_id"], mode,
                secrets.token_urlsafe(18), secrets.token_urlsafe(18),
            )
        except ValueError as exc:
            code = str(exc)
            return jsonify({"error": code}), (403 if code == "license_required" else 409)
        return jsonify(creator_session_launch(account, session_id, mode)), (201 if created else 200)

    def creator_session_launch(account, session_id, mode):
        return {
            "session_id": session_id, "mode": mode,
            "token": issue_token(
                app.config["SESSION_SECRET"],
                {"tenant_id": account["tenant_id"], "session_id": session_id},
                ttl_seconds=8 * 3600,
            ),
        }

    def owned_creator_session(session_id, account):
        session = database.session(session_id)
        return session if session and session["tenant_id"] == account["tenant_id"] else None

    @app.get("/api/v1/creator/sessions/active")
    def active_creator_session():
        account = creator_or_error()
        if not account:
            return jsonify({"error": "unauthorized"}), 401
        database.expire_abandoned_sessions(config_class.CREATOR_SESSION_LEASE_SECONDS)
        session = database.active_creator_session(account["tenant_id"])
        if not session:
            return jsonify({"session": None})
        database.touch_creator_session(session["id"])
        return jsonify({"session": creator_session_launch(account, session["id"], session["mode"])})

    @app.get("/api/v1/creator/sessions/<session_id>")
    def creator_session_status(session_id):
        account = creator_or_error()
        if not account:
            return jsonify({"error": "unauthorized"}), 401
        session = owned_creator_session(session_id, account)
        if not session:
            return jsonify({"error": "session_not_found"}), 404
        if session["status"] == "active":
            database.touch_creator_session(session_id)
        worker_lost = (
            session["mode"] == "live" and config_class.REQUIRE_WORKER_HEARTBEAT
            and not database.worker_heartbeat(config_class.WORKER_HEARTBEAT_TIMEOUT_SECONDS)["ok"]
        )
        return jsonify({
            "session_id": session_id, "status": session["status"], "mode": session["mode"],
            "sources": [
                {"platform": source["platform"], "username": source["username"],
                 "status": ("lost" if worker_lost and source["status"] not in {"stopped", "stopping"}
                            else source["status"])}
                for source in database.live_sources(session_id)
            ],
        })

    @app.post("/api/v1/creator/sessions/<session_id>/end")
    def end_creator_session(session_id):
        account = creator_or_error(mutation=True)
        if not account:
            return jsonify({"error": "unauthorized"}), 401
        session = owned_creator_session(session_id, account)
        if not session:
            return jsonify({"error": "session_not_found"}), 404
        database.end_session(session_id)
        return jsonify({"session_id": session_id, "status": "ended"})

    @app.post("/api/v1/creator/sessions/<session_id>/actions")
    def creator_test_action(session_id):
        account = creator_or_error(mutation=True)
        if not account:
            return jsonify({"error": "unauthorized"}), 401
        session = owned_creator_session(session_id, account)
        if not session or session["mode"] != "test" or session["status"] != "active":
            return jsonify({"error": "test_session_required"}), 409
        run = database.dark_run(session_id)
        if not run or run["status"] != "active":
            return jsonify({"error": "dark_run_inactive"}), 409
        data = request.get_json(silent=True)
        data = data if isinstance(data, dict) else {}
        from .games.dark_actions import ACTION_DURATIONS_MS

        action_type = data.get("action_type")
        actor = data.get("actor_username", "Spectateur test")
        if not isinstance(action_type, str) or action_type not in ACTION_DURATIONS_MS \
                or not isinstance(actor, str) \
                or not actor.strip() or len(actor) > 40:
            return jsonify({"error": "invalid_action"}), 400
        event = event_from_source(
            "test", account["tenant_id"], session_id, "action", actor.strip(),
            source_account_id="local", source_username="Mode Test", actor_platform_id=actor.strip(),
            action_type=action_type,
        )
        accepted, action, rejection = process_event(event)
        if rejection:
            return jsonify({"error": rejection}), 409
        return jsonify({**action, "accepted": accepted}), 202

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
        return jsonify({"session_id": session_id, "status": "ended"}), 200

    @app.get("/api/v1/sessions/<session_id>/sources")
    def session_sources(session_id):
        if not authorized_session(session_id):
            return jsonify({"error": "unauthorized"}), 401
        return jsonify({"sources": [
            {
                "id": row["id"], "platform": row["platform"],
                "source_account_id": row["account_id"], "source_username": row["username"],
                "status": row["status"],
            }
            for row in database.live_sources(session_id)
        ]})

    @app.post("/api/v1/sessions/<session_id>/sources")
    def attach_source(session_id):
        if not authorize_admin():
            return jsonify({"error": "unauthorized"}), 401
        session = database.session(session_id)
        if not session or session["status"] != "active":
            return jsonify({"error": "active_session_not_found"}), 404
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"error": "invalid_source"}), 400
        platform = data.get("source_platform")
        account_id = data.get("source_account_id")
        username = data.get("source_username")
        if (
            not isinstance(platform, str) or not PLATFORM_PATTERN.fullmatch(platform)
            or not isinstance(account_id, str) or not account_id.strip()
            or not isinstance(username, str) or not username.strip()
        ):
            return jsonify({"error": "invalid_source"}), 400
        simulated = data.get("simulated") is True
        if simulated and not config_class.DEMO_MODE:
            return jsonify({"error": "simulation_disabled"}), 403
        if not simulated and platform != "tiktok":
            return jsonify({"error": "connector_unavailable"}), 501
        current = database.live_source_for_session(session_id, platform, account_id)
        if current and current["status"] in ACTIVE_SOURCE_STATUSES | {"simulated"}:
            return jsonify(current), 200
        source = database.save_live_source(
            current["id"] if current else secrets.token_urlsafe(18),
            session["tenant_id"], session_id, platform, account_id, username,
            "simulated" if simulated else "starting",
        )
        return jsonify(source), 202

    @app.post("/api/v1/sources/<source_id>/stop")
    def stop_source(source_id):
        if not authorize_admin():
            return jsonify({"error": "unauthorized"}), 401
        source = database.live_source(source_id)
        if not source:
            return jsonify({"error": "source_not_found"}), 404
        if source["status"] in {"stopped", "error"}:
            return jsonify({"id": source_id, "status": source["status"]}), 200
        status = "stopped" if source["status"] == "simulated" else "stopping"
        database.update_live_source(source_id, status)
        return jsonify({"id": source_id, "status": status}), 202

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
        current = next(
            (row for row in database.listeners() if row["tenant_id"] == tenant_id
             and row["status"] in ACTIVE_SOURCE_STATUSES), None
        )
        if current:
            if current["session_id"] != session_id:
                return jsonify({"error": "listener_already_bound"}), 409
            return jsonify({"status": "already_running", "tenant_id": tenant_id}), 200
        database.save_listener(tenant_id, username, session_id, "starting")
        return jsonify({"status": "started", "tenant_id": tenant_id, "session_id": session_id}), 202

    @app.post("/api/v1/listeners/stop")
    def stop_listener():
        data = request.get_json(silent=True) or {}
        tenant_id = (data.get("tenant_id") or data.get("username") or "").strip()
        listener = next(
            (row for row in database.listeners() if row["tenant_id"] == tenant_id
             and row["status"] in ACTIVE_SOURCE_STATUSES), None
        )
        if not authorize_admin() or not tenant_id or not listener:
            return jsonify({"error": "unauthorized_or_not_found"}), 404
        database.update_live_source(listener["id"], "stopping")
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
        source_platform = data.get("source_platform", data.get("source", "tiktok"))
        event_type = data.get("event_type", data.get("type"))
        actor = data.get("actor_username", data.get("actor"))
        if (
            ("source" in data and data["source"] != source_platform)
            or ("type" in data and data["type"] != event_type)
            or ("actor" in data and data["actor"] != actor)
        ):
            return jsonify({"error": "conflicting_event_fields"}), 400
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (data.get("tenant_id"), data.get("session_id"), event_type, actor)
        ):
            return jsonify({"error": "invalid_event"}), 400
        if any(
            key in data and (not isinstance(data[key], str) or not data[key].strip())
            for key in ("source_account_id", "source_username", "actor_platform_id", "source_event_id")
        ):
            return jsonify({"error": "invalid_source_identity"}), 400
        payload = data.get("payload", {})
        if not isinstance(payload, dict):
            return jsonify({"error": "invalid_event_payload"}), 400
        if set(payload) & RESERVED_EVENT_FIELDS:
            return jsonify({"error": "reserved_payload_field"}), 400
        try:
            event = event_from_source(
                source_platform,
                data["tenant_id"],
                data["session_id"],
                event_type,
                actor,
                event_id=data.get("source_event_id", data.get("event_id")),
                source_account_id=data.get("source_account_id"),
                source_username=data.get("source_username"),
                actor_platform_id=data.get("actor_platform_id"),
                timestamp=data.get("timestamp"),
                event_value=data.get("event_value"),
                **payload,
            )
            if "source_event_id" in data and "event_id" in data and data["event_id"] != event.event_id:
                return jsonify({"error": "invalid_scoped_event_id"}), 400
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        accepted, _, rejection = process_event(event, require_source="source_account_id" in data)
        if rejection == "session_not_found":
            return jsonify({"error": rejection}), 404
        if rejection == "invalid_dark_action":
            return jsonify({"error": rejection}), 400
        if rejection in {"session_tenant_mismatch", "session_inactive", "source_inactive"}:
            return jsonify({"error": rejection}), 409
        if rejection in {"action_requires_dark_session", "dark_run_inactive"}:
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
        if set(payload) & RESERVED_EVENT_FIELDS:
            return jsonify({"error": "reserved_payload_field"}), 400
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

    @app.post("/api/v1/demo/dark/actions")
    def demo_dark_action():
        """Local launcher control; never starts a platform connector."""
        if not config_class.DEMO_MODE:
            return jsonify({"error": "demo_disabled"}), 404
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "invalid_action"}), 400
        session_id = data.get("session_id")
        session = authorized_session(session_id) if isinstance(session_id, str) else None
        if not session or session["tenant_id"] != config_class.DEMO_TENANT_ID \
                or session["game_id"] != "dark" or session["status"] != "active":
            return jsonify({"error": "unauthorized_or_inactive_dark_session"}), 401
        run = database.dark_run(session_id)
        if not run or run["status"] != "active":
            return jsonify({"error": "dark_run_inactive"}), 409
        from .games.dark_actions import ACTION_DURATIONS_MS

        action_type = data.get("action_type")
        platform = data.get("source_platform", "test")
        account_id = data.get("source_account_id", "local" if platform == "test" else f"demo-{platform}")
        source_username = data.get("source_username", "Mode Test" if platform == "test" else account_id)
        actor = data.get("actor_username", "demo-viewer")
        actor_id = data.get("actor_platform_id", actor)
        if not isinstance(action_type, str) or action_type not in ACTION_DURATIONS_MS or (
            not isinstance(platform, str) or not PLATFORM_PATTERN.fullmatch(platform)
            or any(not isinstance(value, str) or not value.strip()
                   for value in (account_id, source_username, actor, actor_id))
        ):
            return jsonify({"error": "invalid_action"}), 400
        if platform != "test":
            source = database.live_source_for_session(session_id, platform, account_id)
            if source and source["status"] not in {"simulated", "stopped"}:
                return jsonify({"error": "source_is_not_simulated"}), 409
            if not source or source["status"] == "stopped":
                database.save_live_source(
                    source["id"] if source else secrets.token_urlsafe(18),
                    session["tenant_id"], session_id, platform, account_id,
                    source_username, "simulated",
                )
        event = event_from_source(
            platform, session["tenant_id"], session_id, "action", actor,
            source_account_id=account_id, source_username=source_username,
            actor_platform_id=actor_id, action_type=action_type,
        )
        accepted, action, rejection = process_event(event, require_source=platform != "test")
        if rejection:
            return jsonify({"error": rejection}), 409
        return jsonify({**action, "accepted": accepted}), 202

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
            live_sources = database.live_sources() if database_health else []
            sessions = database.session_summary() if database_health else {}
            recent_errors = database.recent_errors() if database_health else []
        except Exception as exc:
            logger.error("diagnostics database check failed", extra={"component": "database", "error_type": type(exc).__name__})
            database_health = False
            worker_health = {"ok": False, "error": "database_unavailable"}
            listeners, live_sources, sessions, recent_errors = [], [], {}, []
        return jsonify({
            "service": "interarcade-api",
            "version": config_class.GIT_VERSION,
            "health": {
                "database": database_health,
                "broker": broker.ping(),
                "worker": worker_health,
            },
            "listeners": listeners,
            "live_sources": live_sources,
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
