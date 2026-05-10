from __future__ import annotations

from typing import Optional
from pydantic import BaseModel
from datetime import date

class Score(BaseModel):
    date: str
    score: float
    task_completion: float
    time_utilization: float
    goal_alignment: float
    consistency_bonus: float
    mood: Optional[str] = "neutral"
