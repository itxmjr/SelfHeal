from __future__ import annotations

import logging
import os
import signal
from datetime import datetime
from typing import Optional

import uvicorn
from ..api.app import create_app
from ..workers.daemon_worker import DaemonWorker
from ..config import CONFIG_DIR

DAEMON_PID_PATH = CONFIG_DIR / "daemon.pid"
logger = logging.getLogger(__name__)

class DaemonServer:
    """Orchestrates the FastAPI web server and background worker."""
    def __init__(self):
        self.app = create_app()
        self.worker = DaemonWorker()
        self._started_at = datetime.now()

    def start(self, host: str = "127.0.0.1", port: int = 8282) -> None:
        self._ensure_single_instance()
        self.worker.start()
        
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

        logger.info("Starting SelfHeal Daemon on %s:%s", host, port)
        try:
            uvicorn.run(self.app, host=host, port=port, log_level="info")
        finally:
            self.stop()

    def stop(self) -> None:
        logger.info("Stopping SelfHeal Daemon...")
        self.worker.stop()
        if DAEMON_PID_PATH.exists():
            DAEMON_PID_PATH.unlink()

    def _ensure_single_instance(self) -> None:
        if DAEMON_PID_PATH.exists():
            try:
                pid = int(DAEMON_PID_PATH.read_text().strip())
                os.kill(pid, 0)
                raise RuntimeError(f"Daemon already running as PID {pid}")
            except (ValueError, ProcessLookupError, OSError):
                DAEMON_PID_PATH.unlink(missing_ok=True)
        DAEMON_PID_PATH.write_text(str(os.getpid()))

    def _handle_exit(self, signum, frame):
        self.stop()
        os._exit(0)
