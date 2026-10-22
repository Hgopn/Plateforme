# Runtime anomalies and intentional limits

## Stable baseline — 2026-10-12

- PostgreSQL is the runtime source of truth. SQLite remains a local unit-test
  adapter and must not be used for deployed customer data.
- Redis is optional while the integration stack runs one API instance. It is
  required before horizontal Socket.IO fan-out.
- API and worker run as separate processes and share the same `DATABASE_URL`
  and authenticated internal event token.
- The local demo is bound to loopback by default and is disabled unless
  `INTERARCADE_DEMO_MODE=true`.
- No real TikTok connection is part of automated validation because no approved
  test account or runtime credential is supplied.
- Slot, Dark, Marble, and Fight remain existing static game clients. Marble is
  the only game whose score and winner are persisted as server-authoritative
  state. Fight remains a visual prototype without a TikTok event mapping.
- The retained local PostgreSQL integration volume may contain historical test
  sessions and migrated test licenses. Baseline work does not delete or rewrite
  persisted license/customer data automatically.

## Operational interpretation

An API health status of `degraded` means the HTTP process is alive but its
database, configured broker, or required worker heartbeat failed. A listener in
`starting` means the API accepted the request and the worker has not yet claimed
it. A listener in `error` requires inspecting `/api/v1/diagnostics` with the
observer token.

Expected automated coverage includes API/worker/PostgreSQL recovery, worker and
database outage detection, session-isolated Socket.IO delivery, the launcher
Dark-to-Marble journey, Marble state persistence across restart, and rejection
of events for closed sessions.

The resilience test intentionally produces database connection errors while
PostgreSQL is stopped. `monitor.sh` may report those retained container log
lines as a warning until the API and worker containers are recreated.

## Productization integration — 2026-10-22

The first integration run exposed a PostgreSQL-only failure in the new creator
session lease query: a literal `%` inside `LIKE 'creator:%'` was parsed by
psycopg as an invalid placeholder. The query now binds the pattern as a normal
parameter. A direct PostgreSQL call, the full integration suite and the E2E
restart journey passed after the fix. The earlier worker errors remain in the
integration volume's `runtime_errors` table, so `monitor.sh` can continue to
report a warning even while health and current worker heartbeats are good.
This historical diagnostic data has not been deleted.
