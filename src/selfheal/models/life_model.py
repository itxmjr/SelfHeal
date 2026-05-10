from __future__ import annotations

from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class SleepModel(BaseModel):
    wake: str
    bed: str
    need_hours: float

class Commitment(BaseModel):
    name: str
    hours: float
    days: str # e.g. "Mon-Fri"

class GoalModel(BaseModel):
    name: str
    priority: str
    frequency: str
    preferred_time: Optional[str] = "anytime"

class EnergyModel(BaseModel):
    peak: str
    low: str

class LifeModel(BaseModel):
    version: str = "1.0"
    sleep: SleepModel
    commitments: List[Commitment] = Field(default_factory=list)
    goals: List[GoalModel] = Field(default_factory=list)
    energy: Optional[EnergyModel] = None
    mood_bias: float = 1.0
