#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
[[ $# -eq 2 && "$1" == "--confirm-restore" && -f "$2" ]] || {
  echo "Usage: $0 --confirm-restore /absolute/path/backup.dump" >&2
  exit 2
}
[[ -f .env.production ]] || { echo ".env.production is required" >&2; exit 2; }
BACKUP_FILE="$(realpath "$2")"
docker compose --env-file .env.production -f deploy/docker-compose.production.yml stop api worker
docker compose --env-file .env.production -f deploy/docker-compose.production.yml exec -T postgres \
  pg_restore -U interarcade_admin -d interarcade --role=interarcade --clean --if-exists --no-owner < "$BACKUP_FILE"
docker compose --env-file .env.production -f deploy/docker-compose.production.yml up -d api worker
echo "Restore completed; verify /health/ready and diagnostics before reopening access."
