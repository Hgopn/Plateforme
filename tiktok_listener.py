"""Deprecated compatibility entry point.

TikTok ingestion now lives in ``interarcade.worker.tiktok`` and is managed by
the API listener manager. This module intentionally does not create a global
client or connect to a hard-coded backend.
"""

from interarcade.worker.tiktok import TikTokWorker

__all__ = ["TikTokWorker"]

if __name__ == "__main__":
    raise SystemExit(
        "tiktok_listener.py is deprecated; start the InterArcade application "
        "with `python app.py` and use /api/v1/listeners/start."
    )
