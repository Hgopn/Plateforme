"""Machine-readable runtime monitor for an agent or a cron job."""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


def fetch(path: str, token: str | None = None):
    url = f"{os.getenv('INTERARCADE_MONITOR_API', 'http://127.0.0.1:15000')}{path}"
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310
            return response.status, json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return 0, {"error": str(exc)}


def log_summary():
    command = [
        "docker", "compose", "--env-file", ".env.integration",
        "-f", "deploy/docker-compose.integration.yml", "logs", "--no-color", "--tail=100", "api", "worker",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)  # nosec B603
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "error": str(exc)}
    lines = result.stdout.splitlines()
    return {
        "available": result.returncode == 0,
        "error_lines": sum('"level": "ERROR"' in line or " ERROR " in line for line in lines),
        "warning_lines": sum('"level": "WARNING"' in line or " WARNING " in line for line in lines),
    }


def once():
    token = os.getenv("INTERARCADE_OBSERVER_TOKEN", "")
    health_status, health = fetch("/health/ready")
    diagnostic_status, diagnostics = fetch("/api/v1/diagnostics", token)
    critical = health_status != 200 or health.get("status") != "ok"
    warnings = []
    if diagnostic_status == 401:
        warnings.append({"code": "observer_token_missing", "cause": "diagnostics token was not supplied", "checks": ["load .env.integration or set INTERARCADE_OBSERVER_TOKEN"]})
    if diagnostic_status == 200:
        worker = diagnostics.get("health", {}).get("worker", {})
        if worker and worker.get("ok") is False:
            critical = True
            warnings.append({"code": "worker_heartbeat_stale", "cause": "worker heartbeat is absent or stale", "checks": ["inspect worker logs", "restart worker", "verify DATABASE_URL"]})
        if diagnostics.get("recent_errors"):
            warnings.append({"code": "persisted_runtime_errors", "cause": "runtime_errors contains recent failures", "checks": ["inspect diagnostics.recent_errors", "correlate component with container logs"]})
    logs = log_summary()
    if logs.get("error_lines"):
        warnings.append({"code": "container_errors", "cause": "recent container logs contain errors", "checks": ["inspect docker compose logs", "compare with persisted errors"]})
    if critical:
        severity = "critical"
    elif warnings:
        severity = "warning"
    else:
        severity = "info"
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "status": "ok" if severity != "critical" else "degraded",
        "health": health,
        "diagnostics": diagnostics,
        "logs": logs,
        "anomalies": warnings,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=30)
    args = parser.parse_args()
    while True:
        result = once()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        if not args.watch:
            return 0 if result["severity"] != "critical" else 1
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
