#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml exec -T api \
  python -m unittest discover -s tests -v
docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml exec -T api \
  python -m scripts.test_flow
docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml exec -T api \
  python -c 'from interarcade.config import Config; from interarcade.database import Database; Database(Config.DATABASE_URL).expire_abandoned_sessions(Config.CREATOR_SESSION_LEASE_SECONDS)'
for file in games/*/*.js; do node --check "$file"; done
node --check static/demo.js
node --check static/launcher.js
node --check desktop/main.js
node tests/test_dark_client.js
node tests/test_launcher_client.js
git diff --check
echo "InterArcade integration tests passed"
