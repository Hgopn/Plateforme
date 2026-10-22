#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
[[ -f .env.production ]] || { echo ".env.production is required" >&2; exit 2; }
BACKUP_DIR="${INTERARCADE_BACKUP_DIR:-/var/backups/interarcade}"
mkdir -p "$BACKUP_DIR"
umask 077
BACKUP_FILE="$BACKUP_DIR/interarcade-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose --env-file .env.production -f deploy/docker-compose.production.yml exec -T postgres \
  pg_dump -U interarcade -d interarcade --format=custom --no-owner > "$BACKUP_FILE"
echo "Database backup written to $BACKUP_FILE"
