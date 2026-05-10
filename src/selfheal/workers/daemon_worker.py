from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from ..config import load_life_model
from ..services.sync_service import SyncService
from ..services.scheduler_service import SchedulerService

logger = logging.getLogger(__name__)

class DaemonWorker:
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.sync_service = SyncService()
        self.scheduler_service = SchedulerService()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Daemon background worker started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self):
        while self._running:
            try:
                self._execute_tasks()
            except Exception as e:
                logger.error(f"Critical error in worker loop: {e}", exc_info=True)
            time.sleep(60)

    def _execute_tasks(self):
        now = datetime.now()
        model = load_life_model()
        if not model:
            return

        if now.hour == 6 and now.minute == 0:
            logger.info("Triggering morning schedule generation")
            self.scheduler_service.generate_daily_schedule()
            self.sync_service.sync_obsidian()

        if now.minute % 30 == 0:
            logger.info("Triggering periodic system sync")
            self.sync_service.sync_all()

        from ..daemon.tasks.notify import check_overdue_tasks, check_task_transitions
        check_overdue_tasks()
        check_task_transitions(now)
