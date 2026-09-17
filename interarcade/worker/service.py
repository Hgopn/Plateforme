"""Standalone worker supervisor for TikTok listeners."""

from __future__ import annotations

import json
import logging
import os
import signal
import time
import urllib.request

from ..config import Config
from ..database import Database
from ..events import event_from_tiktok
from ..logging import configure_logging
from .tiktok import TikTokWorker


class WorkerService:
    def __init__(self, config=Config):
        self.config = config
        configure_logging(config.LOG_LEVEL)
        self.database = Database(config.DATABASE_URL)
        self.database.initialize()
        self.workers: dict[str, TikTokWorker] = {}
        self.stop_requested = False
        self.logger = logging.getLogger("interarcade.worker")
        self.worker_id = os.getenv("HOSTNAME", "interarcade-worker")

    def _heartbeat(self):
        self.database.heartbeat_worker(self.worker_id, os.getpid())

    def _request_stop(self, *_args):
        self.logger.info("worker shutdown requested")
        self.stop_requested = True

    def _post_event(self, event):
        body = json.dumps(event.to_dict()).encode()
        request = urllib.request.Request(
            f"{self.config.API_URL.rstrip('/')}/api/v1/internal/events",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-InterArcade-Internal-Token": self.config.INTERNAL_EVENT_TOKEN,
            },
            method="POST",
        )
        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
                    if 200 <= response.status < 300:
                        return
            except Exception as exc:
                last_error = exc
                time.sleep(2**attempt)
        raise RuntimeError(f"event delivery failed: {last_error}")

    def _start(self, row):
        tenant_id = row["tenant_id"]
        if tenant_id in self.workers and self.workers[tenant_id].should_run:
            return
        session_id = row["session_id"]

        def emit(event_type, actor, **payload):
            self._post_event(event_from_tiktok(tenant_id, session_id, event_type, actor, **payload))

        def stopped():
            self.database.update_listener(tenant_id, "stopped")
            self.workers.pop(tenant_id, None)

        worker = TikTokWorker(
            row["username"], tenant_id, session_id, emit,
            self.config.TIKTOK_SIGN_API_KEY, on_stopped=stopped,
        )
        self.workers[tenant_id] = worker
        self.database.update_listener(tenant_id, "running")
        worker.start()

    def run_once(self):
        for row in self.database.listeners():
            try:
                if row["status"] in {"starting", "running"}:
                    self._start(row)
                elif row["status"] == "stopping" and row["tenant_id"] in self.workers:
                    self.workers[row["tenant_id"]].stop()
            except Exception as exc:
                self.database.update_listener(row["tenant_id"], "error", str(exc))
                self.database.record_error("worker", str(exc), {"tenant_id": row["tenant_id"]})
                self.logger.exception("listener startup failed")

    def run_forever(self):
        signal.signal(signal.SIGTERM, self._request_stop)
        signal.signal(signal.SIGINT, self._request_stop)
        while not self.stop_requested:
            try:
                self._heartbeat()
                self.run_once()
            except Exception as exc:
                self.logger.exception("worker supervisor iteration failed")
                try:
                    self.database.record_error("worker", str(exc))
                except Exception as record_error:
                    self.logger.warning("could not persist worker error: %s", record_error)
            time.sleep(self.config.WORKER_POLL_SECONDS)
        for worker in list(self.workers.values()):
            worker.stop()
        self.logger.info("worker stopped cleanly")


def main():
    WorkerService().run_forever()


if __name__ == "__main__":
    main()
