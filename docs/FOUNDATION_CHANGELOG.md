# InterArcade V2 foundation journal

This file records the historical foundation phase. Compatibility mechanisms
listed below may have been removed by later baseline work.

## 2026-09-17 — branch `interarcade-v2-foundation`

- Created a dedicated Git branch before source changes.
- Replaced `secret.py` with `app.py` and the `interarcade/` package.
- Added environment-driven configuration and `.env.example` without real secrets.
- Added optional `.env` loading through the pinned `python-dotenv` dependency.
- Added process-local `Tenant`, `Session`, and `Listener` models.
- Isolated TikTok ingestion in `interarcade.worker.tiktok.TikTokWorker`.
- Converted `tiktok_listener.py` into a deprecated compatibility entry point.
- Added signed session tokens for Socket.IO authentication.
- Removed the public `tiktok_event` Socket.IO ingress path.
- Added an authenticated internal HTTP event ingress endpoint.
- Added versioned event schema documentation and model (`schema_version: 1`).
- Added protected listener start/stop API routes requiring `INTERARCADE_ADMIN_TOKEN`.
- Kept the old listener route names as compatibility aliases.
- Updated Slot, Dark, and Marble to read the versioned event payload while accepting legacy payloads during migration.
- Removed `eventlet` from the direct runtime requirements and pinned the Flask/Socket.IO foundation dependencies.
- Added a correctly named `Procfile` and removed the obsolete deployment notes and `Procfile.txt`.

## Verification performed

- Python AST parsing passed for all repository Python files.
- JSON parsing passed for `licenses.json`, `games/manifest.json`, and `games/game_info.json`.
- Domain tests passed for signed tokens, license lookup, and event validation.
- Flask test client verified `/health`, unauthorized internal events, and unauthorized listener control using the local prototype site-packages.
- No public deployment was performed.
