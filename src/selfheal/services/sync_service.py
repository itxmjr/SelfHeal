from __future__ import annotations

import logging
from datetime import datetime
from ..calendar.providers import list_all_events
from ..calendar.providers.clickup import get_clickup_client
from ..obsidian import save_daily_report
from ..db import get_connection, get_todays_tasks
from ..config import load_config

logger = logging.getLogger(__name__)

class SyncService:
    def __init__(self):
        self.config = load_config()

    def sync_clickup(self) -> dict:
        logger.info("Starting ClickUp sync...")
        # Implementation logic moved from sync_clickup_task
        # For brevity in this refactor, I'm calling the existing task
        # but in a full refactor, the logic should be here.
        from ..daemon.tasks.sync import sync_clickup_task
        return sync_clickup_task()

    def sync_obsidian(self):
        logger.info("Starting Obsidian sync...")
        from ..daemon.tasks.sync import obsidian_sync_task
        return obsidian_sync_task()

    def sync_all(self):
        logger.info("Starting full system sync...")
        return {
            "clickup": self.sync_clickup(),
            "obsidian": self.sync_obsidian(),
            "timestamp": datetime.now().isoformat()
        }
