from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime

class TaskStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"

class TaskPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class TaskBase(BaseModel):
    name: str
    emoji: str = "📌"
    priority: TaskPriority = TaskPriority.MEDIUM
    estimated_minutes: int = 30
    schedule: str = "dynamic"
    goal_id: Optional[int] = None
    depends_on: Optional[str] = None

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    emoji: Optional[str] = None
    estimated_minutes: Optional[int] = None

class Task(TaskBase):
    id: int
    status: TaskStatus = TaskStatus.PENDING
    source: str = "manual"
    external_id: Optional[str] = None
    external_url: Optional[str] = None
    external_updated_at: Optional[datetime] = None
    sync_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

    class Config:
        from_attributes = True
