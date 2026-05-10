from __future__ import annotations

from typing import List, Optional
from ..repositories.task_repository import TaskRepository
from ..models.task import Task, TaskCreate, TaskUpdate, TaskStatus
from ..calendar import update_clickup_task_status

class TaskService:
    def __init__(self, repository: Optional[TaskRepository] = None):
        self.repo = repository or TaskRepository()

    def get_todays_tasks(self) -> List[Task]:
        return self.repo.get_todays_tasks()

    def create_task(self, data: TaskCreate) -> int:
        pass

    def toggle_task(self, task_id: int) -> Task:
        task = self.repo.get_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        new_status = TaskStatus.PENDING if task.status == TaskStatus.DONE else TaskStatus.DONE
        self.repo.mark_status(task_id, new_status)
        
        if task.source == "clickup" and task.external_id:
            clickup_status = "done" if new_status == TaskStatus.DONE else "to do"
            update_clickup_task_status(str(task.external_id), clickup_status)
            
        return self.repo.get_by_id(task_id)
