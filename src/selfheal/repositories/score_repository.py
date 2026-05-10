from __future__ import annotations

import sqlite3
from typing import Optional
from datetime import date
from .base import BaseRepository
from ..models.score import Score

class ScoreRepository(BaseRepository):
    def get_by_date(self, target_date: str) -> Optional[Score]:
        conn = self.get_conn()
        row = conn.execute("SELECT * FROM productivity_scores WHERE date = ?", (target_date,)).fetchone()
        if row:
            return Score.model_validate(dict(row))
        return None

    def save(self, score: Score):
        conn = self.get_conn()
        query = """
            INSERT INTO productivity_scores 
            (date, score, task_completion, time_utilization, goal_alignment, consistency_bonus)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
            score=excluded.score,
            task_completion=excluded.task_completion,
            time_utilization=excluded.time_utilization,
            goal_alignment=excluded.goal_alignment,
            consistency_bonus=excluded.consistency_bonus
        """
        conn.execute(query, (
            score.date, score.score, score.task_completion, 
            score.time_utilization, score.goal_alignment, score.consistency_bonus
        ))
        conn.commit()
