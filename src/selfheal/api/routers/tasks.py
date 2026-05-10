from __future__ import annotations

from fastapi import APIRouter, HTTPException, Body
from typing import List
from ...services.task_service import TaskService
from ...models.task import Task, TaskCreate, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])
service = TaskService()

@router.get("", response_model=List[Task])
async def get_tasks():
    return service.get_todays_tasks()

@router.post("")
async def create_task(task: TaskCreate):
    return {"task_id": service.create_task(task)}

@router.post("/{task_id}/toggle")
async def toggle_task(task_id: int):
    try:
        return service.toggle_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/next")
async def get_next():
    from ...engine.scheduler import get_next_action
    return get_next_action()
