# InterArcade V2 product MVP

For the current productization flow, packaging and VPS procedures, see
[PRODUCTIZATION.md](PRODUCTIZATION.md). The build status below records the
earlier MVP checkpoint.

## Scope and architecture

The website at `/` introduces InterArcade. The creator launcher at `/launcher`
handles account access, the game library, Dark configuration and sessions. The
legacy technical demo stays at `/demo` only when `INTERARCADE_DEMO_MODE=true`.
The production API and worker remain separate processes. Games continue to use
the versioned `ia:event` and `ia:action` contracts, not TikTok-specific logic.

```
TikTok / future live sources -> worker -> Live Hub -> normalized actions
                                                 -> Dark game window
Creator launcher -> account and license API -> PostgreSQL
Desktop shell -> creator launcher and separate Dark BrowserWindow
Website -> registration entry point and product information
```

Dark is the only available game in the product UI. Marble, Slot and Fight are
listed as upcoming despite their historical prototype files. Twitch is shown
as upcoming. The Live Hub already models sources using the pair
`(platform, source_account_id)` so identical TikTok and Twitch names never
become one identity. A live session may already hold multiple source records;
the product UI configures TikTok alone until another connector is real.

The `licenses.games_json` field remains the authority for game access. It can
represent a single game, a bundle or all games without adding a commercial
price or plan. New accounts receive **no** entitlement automatically. Dark
can be tested without a license, while a real TikTok session requires an
enabled Dark license. Provisioning and pricing remain an administrative and
commercial decision.

## Local run and Mac browser review

1. Start the integration stack with `./scripts/start.sh` on the development
   host. Keep the API bound to loopback normally. For a private LAN review,
   set `INTERARCADE_BIND_HOST` to the host's private address in
   `.env.integration`, then restart with `./scripts/start.sh`.
2. Open `http://<host>:15000/` for the website and
   `http://<host>:15000/launcher` for the creator app.
3. Create an account with an email and a password of at least 12 characters.
   The launcher opens directly to the library. Select Dark, then
   **Tester sans live**. Allow the separate pop-up window. Use the action
   selector in the launcher to simulate a viewer action. Returning to the
   library closes that window and ends the test session.
4. Enter a real `@pseudo` to configure TikTok. This merely stores the public
   username; it does not start a connection. A licensed account can select
   **Lancer Dark**, which starts a Live Hub TikTok source and opens Dark. The
   worker attempts to connect to that account. Do not use this flow for a
   validation run without an explicitly authorized test account and runtime
   credentials. The launcher shows the source's actual starting, running or
   error state.

The legacy demo is at `http://<host>:15000/demo` when demo mode is enabled.
Its tools are separate from the creator app. Do not use demo mode in public
production.

## Account and session security

Passwords use PBKDF2-HMAC-SHA256 with unique random salt and 600,000 rounds.
Browser logins are opaque random tokens in an HttpOnly, SameSite=Strict cookie;
the database stores only token hashes and expiration. The launcher receives a
separate CSRF token for mutations. Logout revokes the login in PostgreSQL.
`INTERARCADE_COOKIE_SECURE=true` is required behind production HTTPS. The
game receives a limited, signed game-session token in the URL fragment, which
does not enter server access logs or Referer headers. Game sessions are
server-side records and Dark movement remains server-authoritative.

Account registration creates an active account and an isolated tenant. The
account screen reports entitlements from enabled licenses in PostgreSQL.
Password reset, self-service billing and recovery email are not implemented.
Before accepting external users, add email verification, password reset and
login/registration rate limiting, and validate support and privacy procedures.

## Database migration

`migrations/0001_creator_mvp.sql` is an additive PostgreSQL migration. It adds
`creator_accounts`, `creator_logins`, `creator_platform_accounts` and the
`live_sessions.mode` column. Existing live sessions default to `live`. The
API's idempotent `Database.initialize()` applies the same additions for local
SQLite tests and controlled deployments. Back up PostgreSQL before running
the migration. No license or customer row is rewritten or deleted.

## Desktop shell

Electron was selected because Dark and the launcher are existing web clients
with Socket.IO, and Electron can open an independent resizeable native window
without changing their game code. The main process denies arbitrary window
origins, requires HTTPS for remote servers, disables Node integration in web
pages and uses Chromium sandboxing. The launcher window remains open while
Dark is captured through a second window. No fixed aspect ratio or streaming
software integration is imposed.

`desktop/server.json` points to the loopback-only port 15001 of the local
integration API for development, even when port 15000 is temporarily shared
on the private LAN for Mac browser review.
A production build must replace this URL with the approved HTTPS backend via
`INTERARCADE_SERVER_URL=https://... npm run configure:server` or the build
workflow's `server_url` input.
From a machine with Node 22, run `cd desktop && npm ci && npm start` for a
development shell. `desktop/package.json` provides `dist:win` and `dist:mac`.
The manual GitHub Actions workflow is configured to build unsigned previews on native Windows
and macOS runners. No Windows installer, Mac DMG, signing or notarization has
been validated on this Linux host. The real InterArcade logo and icon are
required before a distributable release; the UI uses a text wordmark meanwhile.

## OVH or equivalent VPS preparation

`deploy/docker-compose.production.yml` defines Caddy, API, worker, PostgreSQL
and Redis. Only Caddy exposes ports 80 and 443; PostgreSQL has no host port.
Caddy obtains HTTPS for `INTERARCADE_DOMAIN`, forwards WebSockets and adds
response security headers. The API uses one gevent WebSocket worker; Redis is
configured for brokered Socket.IO delivery as the installation grows.
`.env.production` is ignored by Git. Copy values from
`deploy/production.env.example`, use independent random secrets, and set the
real domain. Keep the API and worker on the same database and internal-event
token. Check `/health/live`, `/health/ready` and diagnostics after any rollout.

Use `scripts/backup_production.sh` with `INTERARCADE_BACKUP_DIR` on encrypted
storage, schedule it externally, and periodically test a restore. Run the SQL
migration against a backup or staging copy before production rollout. Monitor
worker heartbeats and structured JSON logs. Public deployment, production
restart, data migration against customer data and release distribution remain
outside this sprint and need approval.

## Known release gaps

- No real installer has been built or signed; the download section says so.
- No public production backend exists. The Lenovo development host is for
  private review only.
- TikTok Live connection still depends on the worker, network availability,
  an active creator live and its runtime credentials. It has not been tested
  with a real account in this sprint.
- Twitch, password reset, email verification, billing, subscription checkout,
  updates and Mac notarization are future work.
- The launcher currently opens one Dark source. The Live Hub data model permits
  multiple platform sources, and the next connector can be added without
  changing Dark's event contract.
