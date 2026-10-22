# Product MVP Sprint — review report

## Starting point and checkpoint

The sprint started from `interarcade-v2-tiktok-dark-live` at `9f44126`.
`main` remained at `5537068`. The earlier stable baseline was `04dfc83`,
Dark pilot `bda62c3`, and Live Hub `9f44126`. The working tree already had
31 modified or untracked files: Dark Live actions, real TikTok mapping,
connector robustness, tests and related documentation. They were preserved.
A full archive of these 31 files was written before branching to
`/tmp/interarcade-pre-mvp-20261019T161051Z.tar.gz` with mode 600, then copied
with the same SHA-256 to the ignored persistent local path
`.runtime/checkpoints/interarcade-pre-mvp-20261019T161051Z.tar.gz`. The sprint
then moved to `interarcade-v2-product-mvp`. No merge or push occurred.

The initial Dark JS test passed. The host Python tests could not import Flask
because the host Python 3.11 lacks project dependencies; Docker tests were
subsequently run against the pinned dependency environment.

## What was present

- Flask and Socket.IO API, PostgreSQL persistence and signed game-session
  tokens; license keys and per-game entitlements backed by PostgreSQL.
- Multi-source Live Hub with platform-scoped actor identity and normalized
  events; separate TikTok worker and internal ingress.
- Validated Dark levels 1–3, server-controlled movement and progression,
  visual effects and Live actions from the uncommitted pilot work.
- Historical Marble, Slot and Fight code, internal demo, integration stack,
  diagnostics, health checks and regression suites.

## What this sprint added

| Area | Result |
| --- | --- |
| Website | Product homepage, game presentation, platform status, honest download and pricing sections. |
| Launcher | Login and registration, library, Dark detail, TikTok handle setup, Test and Live controls, account and actual entitlement display. |
| Broadcast | Separate resizable Dark window; no launcher navigation or development controls; optional action notice; visible Test mark. |
| Accounts | Salted PBKDF2 password hashes, database-backed revocable cookies, CSRF token, logout, active account check. |
| Rights | Dark Test available to active accounts; real Live requires a persisted Dark entitlement. New accounts receive no invented license. |
| TikTok | Public handle stored as platform-scoped source identity; real source starts only after an explicit Live launch from a licensed account. |
| Desktop | Electron shell, local backend configuration, native Windows/macOS build workflow configured, unsigned preview targets. |
| Operations | Production Docker/Caddy configuration, HTTPS, Redis, private PostgreSQL, additive migration and backup script. |

No visual or rule changes were made to Dark's three levels, map structure,
movement, collisions, camera, server score/progression or TikTok mapping. The
only Dark client changes for the product are accepting a fragment token and
marking/cleaning its broadcast window.

## Screen descriptions

1. **Website `/`:** warm off-white field, text INTERARCADE wordmark, large
   headline on the left and Dark labyrinth artwork on the right. Below are
   three concise steps, four illustrated game tiles, platform compatibility,
   honest installer status and “Tarifs à venir”. Responsive columns collapse
   on mobile.
2. **Connection `/launcher`:** split layout with Dark artwork on a graphite
   panel and a simple email/password form. “Se souvenir de moi” extends the
   revocable cookie from 12 hours to 30 days. Registration uses the same form.
3. **Library:** Dark banner followed by large image-led cards in a three-column
   grid. Dark is available; Marble, Slot and Fight are marked Bientôt and have
   no fake launch controls.
4. **Dark detail:** large visual, short objective and play instructions on the
   left. The right panel shows TikTok configuration, Twitch Bientôt, action
   overlay switch, license state, “Tester sans live” and “Lancer Dark”.
5. **Session controls:** after launch, the launcher remains open. Test mode
   exposes the five normalized action simulations and a stop control. Live
   mode shows the actual TikTok source state and no simulation controls.
6. **Broadcast:** separate, normal, resizable Dark window containing the game
   canvas, level HUD and small optional Live notice. Test mode is marked.
7. **Account:** real email, recorded game rights and “Tarifs à venir”. No
   invented plan, price or usage statistics.

These are implementation descriptions. No browser screenshots or native
Windows/macOS installer review were available on the Linux development host.

## Architecture and migrations

The website and launcher are served by the existing Flask API. Electron loads
the launcher from the configured backend and allows only same-origin Dark
broadcast windows. Game tokens are in the URL fragment. Existing Socket.IO
rooms, Live Hub source records and TikTok worker remain in place. Production
PostgreSQL is the sole entitlement source. `migrations/0001_creator_mvp.sql`
adds three account tables and `live_sessions.mode`; existing sessions default
to `live`. No data or license row is deleted.

Existing `licenses.games_json` can model individual games, bundles or all
games when offers are decided. There are no prices, fake subscriptions or
payment integration. Only Dark has product launch controls today.

## Files

**New product files:** `interarcade/creator_auth.py`,
`templates/site.html`, `templates/launcher.html`,
`templates/broadcast_waiting.html`, `static/product.css`,
`static/launcher.js`, `static/art/{dark,marble,slot,fight}.svg`,
`tests/test_creator_product.py`, `migrations/0001_creator_mvp.sql`,
`docs/PRODUCT_MVP.md`, this report.

**New desktop and production files:** `desktop/{main.js,package.json,
package-lock.json,server.json,configure-server.js}`,
`.github/workflows/desktop-build.yml`, `Dockerfile.production`,
`deploy/{Caddyfile,docker-compose.production.yml,production.env.example}`,
`scripts/backup_production.sh`.

**Existing files extended for the product:** `interarcade/{app.py,config.py,
database.py}`, `games/dark/{dark.js,dark.html,dark.css}`,
`tests/test_dark_client.js`, `templates/demo.html`, `.env.example`,
`.dockerignore`, `deploy/docker-compose.integration.yml`,
`scripts/{test.sh,autocheck.sh}`, `docs/LOCAL_DEVELOPMENT.md`, and the two
Dark Live test guides whose internal demo links moved to `/demo`.

**Pre-existing uncommitted pilot files preserved:** `config/dark_tiktok_mapping.json`,
`games/dark/dark_actions.js`, `interarcade/dark_tiktok_mapping.py`,
`interarcade/games/dark_actions.py`, `tests/test_dark_actions.py`,
`tests/test_tiktok_dark_mapping.py`, `docs/DARK_LIVE_ACTIONS.md`,
`docs/TIKTOK_DARK_LIVE_TEST.md`, plus earlier modifications to worker,
event, logging, demo and foundation tests.

## Verification

| Check | Result |
| --- | --- |
| `./scripts/test.sh` | 61 Python unittest cases passed; integration flow passed; 12 Dark JS cases passed; syntax and diff checks passed. |
| `./scripts/autocheck.sh` | Severity `info`; 61 pytest cases passed; Ruff and Bandit passed; 12 JS cases and diff check passed. |
| `./scripts/test_e2e.sh` | Journey and post-restart verification passed, including Dark, Marble, event isolation and health. |
| Production Compose `config --no-env-resolution --quiet` | Passed without deploying. |
| SVG XML validation | Four valid files. |
| HTTP checks | Site, launcher, internal demo, game page, stylesheet, launcher script, artwork and waiting window returned 200 on private LAN. |
| Stable branch | `main` stayed at `5537068`; no merge or push. |

The three pytest warnings are deprecations inside the pinned `websockets` and
`TikTokLive` dependencies. No real TikTok account was connected during this
sprint. The Electron native windows and installers were not executed on a
Windows or Mac runner.

## Open on a Mac on the same private network

- Website: `http://192.168.1.12:15000/`
- Creator launcher: `http://192.168.1.12:15000/launcher`
- Dark detail after login: `http://192.168.1.12:15000/launcher#dark`
- Internal technical demo: `http://192.168.1.12:15000/demo`
- Game resource: `http://192.168.1.12:15000/games/dark/dark.html`

The game resource alone needs a session token to play. Use the launcher’s
**Tester sans live** button to open the playable, separate broadcast window.
The API readiness endpoint is `http://192.168.1.12:15000/health/ready`.
Port 15001 is loopback-only for Electron on the Lenovo and cannot be opened
from the Mac.

## Real functionality, simulation and next release gates

**Functional now:** account creation/login/logout, persistent browser login,
actual entitlement lookup, TikTok handle storage, Dark Test session and all
five simulated actions, separate browser game window, Dark server progression,
Live source creation and state polling, existing normalized Live Hub pipeline.

**Simulated or unverified:** Test actions originate from the local test source;
Twitch has no connector; payment and downloads are not active. TikTok Live
startup is implemented but not validated here with an approved live account.
Electron builds are configured but unsigned and untested. OVH deployment has
configuration only; no VPS was changed.

**Before an external user:** visually validate the Mac browser flow and a
Windows native build; add the real owner-provided logo/icon; set up HTTPS
backend, DNS, monitoring and tested backups; validate an authorized TikTok
test live; define real entitlement provisioning and pricing; implement account
recovery, email verification and public endpoint rate limiting; sign and test
Windows/Mac installers; address abandoned-session cleanup. Do not use the
Lenovo as a customer server.
