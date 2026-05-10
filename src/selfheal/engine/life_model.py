from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any


from ..config import load_life_model


def get_available_hours(
    model: dict[str, Any] | None = None,
    calendar_events: list[dict] | None = None,
) -> list[dict]:
    model = model or load_life_model()
    if not model:
        return []

    sleep = model.get("sleep", {})
    wake = _parse_time(sleep.get("wake", "07:00"))
    bed = _parse_time(sleep.get("bed", "23:00"))

    hours = []
    current = wake
    while current < bed:
        hour_num = current.hour
        status = "free"
        task_name = None

        for commit in model.get("commitments", []):
            if _is_commitment_now(commit, hour_num):
                status = "committed"
                task_name = commit["name"]
                break

        if calendar_events and status == "free":
            for ev in calendar_events:
                ev_start = ev.get("start", "")
                ev_end = ev.get("end", "")
                if not ev_start:
                    continue
                try:
                    ev_start_dt = _parse_calendar_dt(ev_start)
                    ev_end_dt = _parse_calendar_dt(ev_end) if ev_end else ev_start_dt + timedelta(hours=1)
                    ev_date = ev_start_dt.date()
                    if ev_date == date.today() and ev_start_dt.hour <= hour_num < ev_end_dt.hour:
                        status = "committed"
                        task_name = f"[Cal] {ev.get('summary', 'Calendar')}"
                        break
                except (ValueError, IndexError):
                    continue

        energy = model.get("energy", {})
        if status == "free":
            if _in_range(hour_num, energy.get("peak", "")):
                status = "peak"
            elif _in_range(hour_num, energy.get("low", "")):
                status = "low"

        hours.append({
            "hour": hour_num,
            "status": status,
            "task": task_name,
            "label": f"{hour_num:02d}:00",
        })
        current = (datetime.combine(date.today(), current) + timedelta(hours=1)).time()

    return hours


def get_free_hours(model: dict[str, Any] | None = None) -> list[dict]:
    return [h for h in get_available_hours(model) if h["status"] in ("free", "peak", "low")]


def get_goals_for_today(model: dict[str, Any] | None = None, today: date | None = None) -> list[dict]:
    model = model or load_life_model()
    if not model:
        return []

    today = today or date.today()
    day_name = today.strftime("%a").lower()[:3]
    goals = []

    for goal in model.get("goals", []):
        freq = goal.get("frequency", "daily")
        if freq == "daily":
            goals.append(goal)
        elif "x/week" in freq:
            n = int(freq.split("x")[0])
            goals.append({**goal, "_weekly_target": n})
        elif freq == "weekdays" and day_name not in ("sat", "sun"):
            goals.append(goal)
        elif freq == "weekends" and day_name in ("sat", "sun"):
            goals.append(goal)

    return goals


def _parse_time(t: str) -> time:
    try:
        parts = t.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return time(7, 0)


def _is_commitment_now(commit: dict, hour: int) -> bool:
    hours_str = commit.get("hours", "")
    if not hours_str:
        return False
    try:
        start_str, end_str = hours_str.split("-")
        start_h = int(start_str.split(":")[0])
        end_h = int(end_str.split(":")[0])
        return start_h <= hour < end_h
    except (ValueError, IndexError):
        return False


def _in_range(hour: int, time_range: str) -> bool:
    if not time_range:
        return False
    try:
        start_str, end_str = time_range.split("-")
        start_h = int(start_str.split(":")[0])
        end_h = int(end_str.split(":")[0])
        return start_h <= hour < end_h
    except (ValueError, IndexError):
        return False


def _parse_calendar_dt(val: str) -> datetime:
    if "T" in val:
        if "+" in val or val.endswith("Z"):
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        return datetime.fromisoformat(val)
    return datetime.strptime(val, "%Y-%m-%d")
