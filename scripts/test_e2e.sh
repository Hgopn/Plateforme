#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
[[ -f .env.integration ]] || { echo ".env.integration is required" >&2; exit 2; }

COMPOSE=(docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml)
set -a
. ./.env.integration
set +a
HEALTH_URL="http://${INTERARCADE_BIND_HOST:-127.0.0.1}:15000"

wait_ready() {
  for _ in $(seq 1 40); do
    if curl -fsS "$HEALTH_URL/health/ready" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  return 1
}

"${COMPOSE[@]}" exec -T api python -m scripts.test_e2e journey
"${COMPOSE[@]}" restart api worker >/dev/null
wait_ready
"${COMPOSE[@]}" exec -T api python -m scripts.test_e2e verify
python3 scripts/diagnostic.py
