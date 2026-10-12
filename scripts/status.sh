#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
set -a
. ./.env.integration
set +a
docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml ps
if ! health="$(curl -fsS "http://${INTERARCADE_BIND_HOST:-127.0.0.1}:15000/health/ready" 2>/dev/null)"; then
  echo '{"status":"unavailable","service":"interarcade-api"}'
  exit 1
fi
printf '%s\n' "$health"
