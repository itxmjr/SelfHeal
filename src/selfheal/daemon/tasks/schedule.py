from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ...calendar import add_clickup_task_comment, list_all_events, update_clickup_task_dates
from ...config import load_life_model
from ...engine.scheduler import generate_and_persist_schedule


def collect_calendar_events(target_date: date) -> list[dict[str, Any]]:
    return list_all_events(target_date, target_date)


def generate_schedule_task(target_date: date | None = None) -> tuple[list[dict[str, Any]], bool]:
    """Generate and persist the schedule for a date using explicit calendar events."""
    schedule_date = target_date or date.today()
    model = load_life_model()
    if not model:
        return []

    events = collect_calendar_events(schedule_date)
    schedule, ai_success = generate_and_persist_schedule(
        today=schedule_date,
        life_model=model,
        calendar_events=events,
        use_ai=True,
    )
    annotate_clickup_schedule(schedule)
    return schedule, ai_success


def annotate_clickup_schedule(schedule: list[dict[str, Any]]) -> None:
    today = date.today()
    for item in schedule:
        if item.get("source") != "clickup" or not item.get("external_id"):
            continue
            
        start_str = item.get("start_time")
        end_str = item.get("end_time")
        if not start_str or not end_str:
            continue
            
        try:
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
            
            start_dt = datetime.combine(today, datetime.min.time().replace(hour=start_h, minute=start_m))
            due_dt = datetime.combine(today, datetime.min.time().replace(hour=end_h, minute=end_m))
            
            update_clickup_task_dates(str(item["external_id"]), start_dt, due_dt)
            add_clickup_task_comment(str(item["external_id"]), f"Scheduled by SelfHeal: {start_str}-{end_str}")
        except (ValueError, Exception) as exc:
            from logging import getLogger
            getLogger(__name__).warning("Failed to sync ClickUp dates for task %s: %s", item.get("external_id"), exc)
