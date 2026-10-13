# Local foundation workflow

1. Copy `.env.example` to `.env` and replace every `replace-with-...` value.
2. Install the pinned dependencies from `requirements.txt` in a fresh Python 3.11 environment.
3. Start the API with `python app.py` and the worker with `python -m interarcade.worker`.
4. Provision licenses in PostgreSQL through an approved administrative process.
5. Create a game session with `POST /api/v1/sessions` using a tenant and license key.
6. Open a game with the returned `session_id` and `token` query parameters.
7. Start or stop a TikTok listener with `Authorization: Bearer <INTERARCADE_ADMIN_TOKEN>`.

The Live Hub source model and local multi-source simulation are documented in
[LIVE_HUB.md](LIVE_HUB.md). Simulated sources require Demo mode and never
connect to TikTok or Twitch.

The existing game pages remain static files under `/games/<game>/<game>.html`.
Socket.IO accepts only signed tokens for active persisted sessions. Connections
join a session-specific room so simultaneous games from one tenant are isolated.

## Local browser demo

The integration environment can enable a local-only demonstration catalogue at
`http://127.0.0.1:15000/`. It provides the four existing games in a vertical
frame, runtime status, and demo-only simulated events. The demo endpoints are
disabled when `INTERARCADE_DEMO_MODE=false`. Keep `INTERARCADE_BIND_HOST` on a
loopback address unless a temporary private-network test is explicitly needed.
