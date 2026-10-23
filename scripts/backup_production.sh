#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
[[ -f .env.production ]] || { echo ".env.production is required" >&2; exit 2; }
BACKUP_DIR="${INTERARCADE_BACKUP_DIR:-/var/backups/interarcade}"
umask 077
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/interarcade-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose --env-file .env.production -f deploy/docker-compose.production.yml exec -T postgres \
  pg_dump -U interarcade_admin -d interarcade --format=custom --no-owner > "$BACKUP_FILE"
docker compose --env-file .env.production -f deploy/docker-compose.production.yml exec -T postgres \
  pg_restore --list < "$BACKUP_FILE" >/dev/null
echo "Database backup written to $BACKUP_FILE"
