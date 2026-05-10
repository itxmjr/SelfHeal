from __future__ import annotations

import sqlite3
from typing import List, Optional, Any
from datetime import date
from .base import BaseRepository
from ..models.task import Task, TaskStatus

class TaskRepository(BaseRepository):
    def get_by_id(self, task_id: int) -> Optional[Task]:
        conn = self.get_conn()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row:
            return Task.model_validate(dict(row))
        return None

    def get_todays_tasks(self, target_date: Optional[str] = None) -> List[Task]:
        if target_date is None:
            target_date = date.today().isoformat()
        
        conn = self.get_conn()
        # Join with daily_logs to get scheduled times for today
        query = """
            SELECT t.*, dl.status, dl.scheduled_start, dl.scheduled_end 
            FROM tasks t
            LEFT JOIN daily_logs dl ON t.id = dl.task_id
            WHERE dl.date = ? OR t.schedule = 'daily'
        """
        rows = conn.execute(query, (target_date,)).fetchall()
        return [Task.model_validate(dict(row)) for row in rows]

    def upsert(self, task: Task) -> int:
        conn = self.get_conn()
        query = """
            INSERT INTO tasks (
                name, emoji, priority, estimated_minutes, schedule, goal_id, depends_on, source, 
                external_id, external_url, external_updated_at, sync_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, external_id) DO UPDATE SET
                name=excluded.name,
                emoji=excluded.emoji,
                priority=excluded.priority,
                estimated_minutes=excluded.estimated_minutes,
                schedule=excluded.schedule,
                goal_id=excluded.goal_id,
                depends_on=excluded.depends_on,
                external_url=excluded.external_url,
                external_updated_at=excluded.external_updated_at,
                sync_hash=excluded.sync_hash
            RETURNING id
        """
        params = (
            task.name, task.emoji, task.priority.value, task.estimated_minutes, task.schedule, 
            task.goal_id, task.depends_on, task.source, task.external_id, task.external_url, 
            task.external_updated_at, task.sync_hash
        )
        row = conn.execute(query, params).fetchone()
        conn.commit()
        return row[0]

    def mark_status(self, task_id: int, status: TaskStatus):
        conn = self.get_conn()
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        conn.commit()
