"""Single deferred exit path for the running Archive Console (uvicorn) process."""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_shutdown_lock = threading.Lock()
_shutdown_started = False


def request_shutdown(reason: str) -> None:
    """
    Schedule termination of this process shortly after the caller returns.
    Used by POST /api/shutdown (BackgroundTasks) and must not block the HTTP response.
    Idempotent.
    """
    global _shutdown_started
    with _shutdown_lock:
        if _shutdown_started:
            return
        _shutdown_started = True
    logger.warning("Archive Console process shutdown scheduled (%s)", reason)

    def _deferred() -> None:
        time.sleep(0.4)
        _exit_process()

    threading.Thread(
        target=_deferred, name="archive_console_shutdown", daemon=True
    ).start()


def _exit_process() -> None:
    """Hard exit so the port is released; ASGI lifespan finally hooks may not run."""
    os._exit(0)
