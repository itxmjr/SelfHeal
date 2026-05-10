from __future__ import annotations

from datetime import date
from typing import Any

from ...calendar import add_clickup_task_comment, list_all_events
from ...config import load_life_model
from ...engine.scheduler import generate_and_persist_schedule


def collect_calendar_events(target_date: date) -> list[dict[str, Any]]:
    return list_all_events(target_date, target_date)


def generate_schedule_task(target_date: date | None = None) -> list[dict[str, Any]]:
    """Generate and persist the schedule for a date using explicit calendar events."""
    schedule_date = target_date or date.today()
    model = load_life_model()
    if not model:
        return []

    events = collect_calendar_events(schedule_date)
    schedule = generate_and_persist_schedule(
        today=schedule_date,
        life_model=model,
        calendar_events=events,
        use_ai=False,
    )
    annotate_clickup_schedule(schedule)
    return schedule


def annotate_clickup_schedule(schedule: list[dict[str, Any]]) -> None:
    for item in schedule:
        if item.get("source") != "clickup" or not item.get("external_id"):
            continue
        start = f"{int(item['start_hour']):02d}:00"
        end = f"{int(item['end_hour']):02d}:00"
        add_clickup_task_comment(str(item["external_id"]), f"Scheduled by SelfHeal: {start}-{end}")
