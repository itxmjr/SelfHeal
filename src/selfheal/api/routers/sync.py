from __future__ import annotations

from fastapi import APIRouter
from ...services.sync_service import SyncService
from ...services.scheduler_service import SchedulerService
from ...models.schedule import DailySchedule

router = APIRouter(tags=["sync"])
sync_service = SyncService()
scheduler_service = SchedulerService()

@router.post("/sync")
async def trigger_sync():
    return sync_service.sync_all()

@router.post("/sync/calendar")
async def sync_calendar():
    return {"status": "ok"} # Placeholder for individual sync

@router.post("/sync/clickup")
async def sync_clickup():
    return sync_service.sync_clickup()

@router.post("/sync/obsidian")
async def sync_obsidian():
    return sync_service.sync_obsidian()

@router.post("/schedule/generate", response_model=DailySchedule)
async def generate_schedule():
    return scheduler_service.generate_daily_schedule()

@router.post("/schedule/regenerate")
async def regenerate_schedule():
    return scheduler_service.regenerate_remaining_day()
