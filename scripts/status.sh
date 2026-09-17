#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml ps
curl -fsS http://127.0.0.1:15000/health/ready || true
printf '\n'
