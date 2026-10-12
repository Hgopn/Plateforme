#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }
command -v openssl >/dev/null || { echo "openssl is required" >&2; exit 1; }

if [[ ! -f .env.integration ]]; then
  umask 077
  {
    echo "INTERARCADE_DB_PASSWORD=$(openssl rand -hex 32)"
    echo "INTERARCADE_SECRET_KEY=$(openssl rand -hex 32)"
    echo "INTERARCADE_SESSION_SECRET=$(openssl rand -hex 32)"
    echo "INTERARCADE_ADMIN_TOKEN=$(openssl rand -hex 32)"
    echo "INTERARCADE_INTERNAL_EVENT_TOKEN=$(openssl rand -hex 32)"
    echo "INTERARCADE_OBSERVER_TOKEN=$(openssl rand -hex 32)"
    echo "INTERARCADE_ALLOWED_ORIGINS=http://127.0.0.1:15000,http://localhost:15000,http://api:5000"
    echo "EULER_API_KEY="
    echo "REDIS_URL="
    echo "INTERARCADE_LOG_LEVEL=INFO"
  } > .env.integration
  echo "Created .env.integration with mode 600"
fi

set -a
. ./.env.integration
set +a
INTERARCADE_HEALTH_URL="http://${INTERARCADE_BIND_HOST:-127.0.0.1}:15000"
export INTERARCADE_GIT_VERSION="${INTERARCADE_GIT_VERSION:-$(git rev-parse --short HEAD 2>/dev/null || echo working-tree)}"
docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml up -d --build

for attempt in $(seq 1 40); do
  if curl -fsS "$INTERARCADE_HEALTH_URL/health/ready" >/dev/null 2>/dev/null; then
    break
  fi
  [[ "$attempt" == 40 ]] && { docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml ps; exit 1; }
  sleep 2
done

echo "InterArcade integration stack is ready on ${INTERARCADE_HEALTH_URL}"
