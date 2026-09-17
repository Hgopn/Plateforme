# InterArcade V2 runtime phase journal

## 2026-09-17 — branch `interarcade-v2-runtime`

- Created from `interarcade-v2-foundation` before runtime changes.
- Added DB-API persistence for tenants, users, licenses, live sessions,
  listeners, event outbox records, and runtime errors.
- Added PostgreSQL support through `psycopg` and SQLite only for local tests.
- Added idempotent `licenses.json` migration via
  `python -m interarcade.migrate_licenses`.
- Removed TikTok client startup from the API process.
- Added standalone worker supervisor via `python -m interarcade.worker`.
- Added worker polling, listener state transitions, reconnect behavior, and
  authenticated HTTP event delivery with retries.
- Added event persistence before Socket.IO publication and duplicate-event
  protection by `event_id`.
- Added optional Redis broker configuration and broker health verification.
- Added structured JSON logging and observer diagnostics.
- Added detailed live/ready healthchecks for API, database, broker, and worker
  listener state.
- Added `AGENTS.md`, anomaly documentation, pytest/ruff/bandit configuration,
  and runtime persistence tests.

## Verification

- 8 `unittest` tests pass.
- Python AST checks pass.
- JavaScript syntax checks pass.
- `git diff --check` passes.
- No public deployment was performed.
