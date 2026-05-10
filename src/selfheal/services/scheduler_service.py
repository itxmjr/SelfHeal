from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional, Tuple

from ..models.schedule import DailySchedule, ScheduleItem
from ..models.life_model import LifeModel
from ..repositories.task_repository import TaskRepository
from ..engine.scheduler import generate_schedule, persist_schedule

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self, task_repo: Optional[TaskRepository] = None):
        self.task_repo = task_repo or TaskRepository()

    def generate_daily_schedule(self, target_date: Optional[date] = None, 
                               life_model: Optional[LifeModel] = None) -> DailySchedule:
        target_date = target_date or date.today()
        # Logic for orchestration
        # 1. Collect candidates
        # 2. Call engine
        # 3. Persist
        # 4. Return DailySchedule model
        
        from ..daemon.tasks.schedule import generate_schedule_task
        schedule, success = generate_schedule_task(target_date)
        
        items = [ScheduleItem.model_validate(item) for item in schedule]
        return DailySchedule(
            date=target_date.isoformat(),
            items=items,
            ai_success=success
        )

    def regenerate_remaining_day(self):
        from ..engine.scheduler import regenerate_schedule
        return regenerate_schedule()
