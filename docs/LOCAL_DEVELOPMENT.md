# Local foundation workflow

1. Copy `.env.example` to `.env` and replace every `replace-with-...` value.
2. Install the pinned dependencies from `requirements.txt` in a fresh Python 3.11 environment.
3. Start the API with `python app.py`.
4. Create a game session with `POST /api/v1/sessions` using a tenant and license key.
5. Open a game with the returned `token` query parameter.
6. Start or stop a TikTok listener with `Authorization: Bearer <INTERARCADE_ADMIN_TOKEN>`.

The existing game pages remain static files under `/games/<game>/<game>.html`.
The legacy `?username=` Socket.IO query authentication is disabled by default;
set `INTERARCADE_LEGACY_SOCKET_QUERY_AUTH=true` only for a temporary local
migration test.
