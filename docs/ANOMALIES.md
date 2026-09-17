# Runtime anomalies and compatibility notes

## Detected on 2026-09-17

- The provided local Python environment is a Windows virtual environment
  stored under `venv/`; it is not a portable runtime for Linux deployment.
- Flask and Flask-SocketIO are available in that environment, but PostgreSQL,
  Redis, pytest, ruff, and bandit are not installed there. The automated tests
  therefore use the SQLite DB-API fallback and the pinned development tools
  are declared for a clean environment.
- PostgreSQL is required for the integrated runtime. Redis is optional at this
  stage because the API and worker communicate through the authenticated
  internal HTTP ingress and the deployment runs as one API instance. Redis
  becomes appropriate when Socket.IO needs cross-instance fan-out or a broker
  is required for higher availability. SQLite is only a local test adapter
  and must not be used as the production source of truth.
- `licenses.json` remains in the repository for migration compatibility. Run
  `python -m interarcade.migrate_licenses` before disabling the legacy file.
- The worker is intentionally not started by the API process anymore. Both API
  and worker must run as separate processes in a real environment.

## Integration validation on 2026-09-17

- The isolated Docker stack uses a dedicated PostgreSQL 17 container,
  database, user, network, and named volume. The existing EKA PostgreSQL
  container and volume were not accessed or changed.
- Six legacy licenses were imported successfully from `licenses.json`.
- The API, worker, and PostgreSQL healthchecks passed. The worker is running
  and idle because no listener has been requested.
- The simulated API-to-Socket.IO flow passed for Slot, Dark, and Marble.
- A real TikTokLive connection was not attempted: no test account was supplied
  and no public live session is necessary for this validation phase.
- The integration stack binds its host ports to loopback only. Redis was not
  installed because it is not required by the current single-instance flow.
- The simulated Socket.IO flow succeeds, but the local Werkzeug development
  server logs a `400` during some WebSocket close handshakes. This is a
  development-server limitation/noise, not a failed event delivery; a
  production WSGI/Socket.IO server is still required before public use.

## Production-runtime validation on 2026-09-17

- The integration API now runs under Gunicorn with the Gevent WebSocket worker;
  logs confirm WebSocket-capable requests are handled without Werkzeug.
- Controlled API, worker, and PostgreSQL restarts recovered successfully and
  the license count remained unchanged.
- Stopping the worker makes `/health/ready` return `503` after the heartbeat
  timeout; restarting it restores readiness.
- Stopping PostgreSQL makes `/health/ready` return `503` without an unhandled
  `500`; restarting PostgreSQL restores readiness and data access.
- Malformed event payloads and unsupported event schema versions are rejected
  with `400`; duplicate event IDs remain idempotent.
- The monitoring script classifies stale heartbeats, persisted errors, and
  recent container errors with probable causes and recommended checks. Errors
  observed during intentional outage tests are expected test evidence and may
  remain visible in the container log history until containers are recreated.

## Operational interpretation

An API health status of `degraded` means the HTTP process is alive but its
database or configured broker check failed. A listener in `starting` means the
API accepted the request and the worker has not yet claimed it. A listener in
`error` requires inspecting `/api/v1/diagnostics` with the observer token.
