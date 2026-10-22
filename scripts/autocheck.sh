#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

[[ -f .env.integration ]] || { echo '{"status":"critical","error":".env.integration missing"}'; exit 2; }
set -a
. ./.env.integration
set +a

python3 scripts/monitor.py
DEMO_API_URL="http://${INTERARCADE_BIND_HOST:-127.0.0.1}:15000"
curl -fsS "$DEMO_API_URL/health/live" >/dev/null
curl -fsS "$DEMO_API_URL/health/ready" >/dev/null
docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml exec -T api python -m pytest -q
docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml exec -T api \
  python -c 'from interarcade.config import Config; from interarcade.database import Database; Database(Config.DATABASE_URL).expire_abandoned_sessions(Config.CREATOR_SESSION_LEASE_SECONDS)'
docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml exec -T api ruff check .
docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml exec -T api bandit -q -r interarcade app.py scripts
command -v node >/dev/null || { echo '{"status":"critical","error":"node is required for game syntax checks"}'; exit 2; }
for game in slot dark marble fight; do
  node --check "games/$game/$game.js"
done
node --check games/dark/dark_actions.js
node --check static/demo.js
node --check static/launcher.js
node --check desktop/main.js
node tests/test_dark_client.js
node tests/test_launcher_client.js
git diff --check
echo '{"status":"ok","checks":"monitor,health,pytest,ruff,bandit,javascript,git-diff"}'
