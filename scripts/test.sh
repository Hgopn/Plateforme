#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml exec -T api \
  python -m unittest discover -s tests -v
docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml exec -T api \
  python scripts/test_flow.py
for file in games/*/*.js; do node --check "$file"; done
git diff --check
echo "InterArcade integration tests passed"
