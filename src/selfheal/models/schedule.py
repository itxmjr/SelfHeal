from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel
from .task import TaskPriority

class ScheduleItem(BaseModel):
    name: str
    emoji: str
    priority: TaskPriority
    start_time: str # HH:MM
    end_time: str   # HH:MM
    estimated_minutes: int
    status: str = "pending"
    reasoning: Optional[str] = None
    task_id: Optional[int] = None
    external_id: Optional[str] = None
    source: str = "manual"

class DailySchedule(BaseModel):
    date: str
    items: List[ScheduleItem]
    ai_success: bool = False
