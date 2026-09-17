#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
COMPOSE=(docker compose --env-file .env.integration -f deploy/docker-compose.integration.yml)

wait_ready() {
  for _ in $(seq 1 40); do
    if curl -fsS http://127.0.0.1:15000/health/ready >/dev/null; then return 0; fi
    sleep 1
  done
  return 1
}

before="$("${COMPOSE[@]}" exec -T postgres psql -U interarcade -d interarcade -Atc 'SELECT COUNT(*) FROM licenses')"

"${COMPOSE[@]}" restart api >/dev/null
wait_ready
"${COMPOSE[@]}" restart worker >/dev/null
wait_ready

"${COMPOSE[@]}" stop worker >/dev/null
sleep 17
if curl -fsS http://127.0.0.1:15000/health/ready >/dev/null; then
  echo "worker outage was not detected" >&2
  exit 1
fi
"${COMPOSE[@]}" start worker >/dev/null
wait_ready

"${COMPOSE[@]}" stop postgres >/dev/null
sleep 2
if curl -fsS http://127.0.0.1:15000/health/ready >/dev/null; then
  echo "database outage was not detected" >&2
  exit 1
fi
"${COMPOSE[@]}" start postgres >/dev/null
for _ in $(seq 1 40); do
  if "${COMPOSE[@]}" exec -T postgres pg_isready -U interarcade -d interarcade >/dev/null 2>&1; then break; fi
  sleep 1
done
wait_ready

after="$("${COMPOSE[@]}" exec -T postgres psql -U interarcade -d interarcade -Atc 'SELECT COUNT(*) FROM licenses')"
[[ "$before" == "$after" ]] || { echo "license count changed across restart: $before -> $after" >&2; exit 1; }
echo '{"status":"ok","checks":["api_restart","worker_restart","worker_outage","database_outage","data_integrity"]}'
