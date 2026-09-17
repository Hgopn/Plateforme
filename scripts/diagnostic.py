"""Return a compact JSON runtime state for a future EKA observer."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def get(path: str, token: str | None = None):
    request = urllib.request.Request(f"{os.getenv('INTERARCADE_API_URL', 'http://127.0.0.1:15000')}{path}")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310
            return response.status, json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return 0, {"error": str(exc)}


def main():
    status, health = get("/health/ready")
    _, diagnostics = get("/api/v1/diagnostics", os.getenv("INTERARCADE_OBSERVER_TOKEN", ""))
    output = {
        "status": "ok" if status == 200 and health.get("status") == "ok" else "degraded",
        "api": health,
        "diagnostics": diagnostics,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if output["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
