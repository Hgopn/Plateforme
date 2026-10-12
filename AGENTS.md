# InterArcade V2 instructions for AI agents

## Product reference

Read [docs/PRODUCT_VISION.md](/opt/interarcade/docs/PRODUCT_VISION.md) before
changing user-facing behavior. InterArcade is a paid launcher/application for
TikTok Live creators: the website presents and sells the product, while the
installed app handles account, license, game library, TikTok connection, live
sessions, and history. Do not describe it as an AI dashboard or a generic game
website. Keep internal diagnostics/admin tools separate from creator UX.

## Architecture

- `app.py` starts the Flask/Socket.IO API.
- `interarcade/app.py` owns HTTP routes, session tokens, healthchecks, and
  the authenticated internal event ingress.
- `interarcade/database.py` is the persistence boundary. PostgreSQL is the
  production database; SQLite is only a local test adapter.
- `interarcade/worker/service.py` is a separate worker supervisor. It polls
  listener state, starts TikTok clients, retries event delivery, and must not
  be imported as part of the API startup path.
- `interarcade/worker/tiktok.py` contains TikTokLive-specific behavior.
- `interarcade/events.py` defines the versioned `ia:event` contract.
- `interarcade/games/marble.py` defines the server-authoritative Marble rules;
  the browser renders state and never owns the official score.
- PostgreSQL is the only runtime source of truth for licenses and entitlements.
- `interarcade/logging.py` emits structured JSON logs.
- Games are static clients under `games/` and consume authenticated,
  versioned events. They are not authoritative for scores or identity.

## Commands

Use a clean Python 3.11 environment for normal work:

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m pytest
ruff check .
bandit -r interarcade app.py
node --check games/slot/slot.js
node --check games/dark/dark.js
node --check games/marble/marble.js
git diff --check
```

For local persistence tests, use `sqlite:///...`. For runtime, configure
`DATABASE_URL` with PostgreSQL and `REDIS_URL` with Redis.

For the isolated server integration stack:

```bash
./scripts/start.sh
./scripts/status.sh
./scripts/test.sh
python3 scripts/diagnostic.py
./scripts/autocheck.sh
./scripts/monitor.sh
./scripts/test_resilience.sh
./scripts/stop.sh
```

The integration scripts use `.env.integration`, which is generated locally,
permission-restricted, and ignored by Git. The default stack binds API and
PostgreSQL to loopback; the local demo may bind the API temporarily to the
configured private LAN address, while PostgreSQL remains loopback-only. Redis
is optional until multiple API instances or brokered Socket.IO fan-out is
introduced.

`monitor.sh` emits one JSON record by default and can run periodically with
`./scripts/monitor.sh --watch --interval 30`. Severity is `info`, `warning`,
or `critical`; critical means health is unavailable/degraded, while warnings
include stale worker heartbeats, persisted runtime errors, or recent log
errors. `autocheck.sh` returns non-zero on a critical diagnostic or any failed
test/security/syntax check.

For the Marble pilot, also read `docs/MARBLE_PILOT.md`. Do not add client-side
score authority, accept unnormalized TikTok payloads, or start a real TikTok
connection without an explicitly supplied test account and approved runtime
credentials.

## Git rules

- Never work directly on `main` or the stable foundation branch.
- Create a dedicated branch from the requested parent branch before edits.
- Inspect status before and after every change.
- Keep commits focused and explicit.
- Never force-push, reset, or merge branches automatically.
- Never push or deploy without explicit user authorization for that operation.

## Automatically allowed

An agent may automatically:

- inspect source, logs exposed by the diagnostics API, tests, and Git state;
- fix implementation defects inside the requested branch;
- add tests, lint rules, migrations, and documentation;
- run local tests, static analysis, and syntax checks;
- document anomalies in `docs/ANOMALIES.md`.

## Human validation required

Ask for human validation before:

- changing product or commercial rules;
- changing license entitlements or customer data;
- creating, rotating, or exposing secrets;
- destructive database migrations or data deletion;
- public deployment, production restart, or external notifications;
- merging or pushing when not explicitly requested.

## Incident diagnosis

1. Check `/health/live` to distinguish process failure from dependency failure.
2. Check `/health/ready` for database and broker readiness.
3. Query `/api/v1/diagnostics` with the observer token.
4. Inspect structured JSON logs by `component`, `level`, and `message`.
5. Check listener states: `starting`, `running`, `stopping`, `stopped`, `error`.
6. Verify worker and API use the same `DATABASE_URL` and internal event token.
7. Re-run the test suite before attempting a restart.

## Change verification

Before declaring a change safe, run the complete test and static-check command
set above, inspect `git diff --check`, review the changed file list, and verify
that stable branches were not changed.
