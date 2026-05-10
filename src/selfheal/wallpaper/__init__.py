from __future__ import annotations

import json
from datetime import date

from ..config import WALLPAPER_DATA_PATH, load_life_model
from ..db import get_connection, get_todays_tasks
from ..engine.scorer import calculate_score


def update_wallpaper_data() -> None:
    model = load_life_model()
    if not model:
        return

    conn = get_connection()
    tasks = get_todays_tasks(conn)
    conn.close()

    score = calculate_score()
    sc = score.get("score", 0)

    done = sum(1 for t in tasks if t.get("status") == "done")
    total = max(len(tasks), 1)

    pending = [t for t in tasks if t.get("status") == "pending" and not t.get("is_blocked")]
    next_task = pending[0] if pending else None

    blocks = []
    for t in tasks:
        start = t.get("scheduled_start", "")
        end = t.get("scheduled_end", "")
        blocks.append({
            "name": f"{t.get('emoji', '')} {t.get('name', '')}".strip(),
            "start": start,
            "end": end,
            "status": t.get("status", "pending"),
            "priority": t.get("priority", "medium"),
            "blocked": t.get("is_blocked", False),
        })

    data = {
        "date": date.today().isoformat(),
        "score": sc,
        "score_color": "green" if sc >= 70 else "yellow" if sc >= 40 else "red",
        "tasks_done": done,
        "tasks_total": total,
        "streak": score.get("streak", 0),
        "mood": "On Track" if sc >= 70 else "Recovering" if sc >= 40 else "Needs Focus",
        "next": {
            "name": f"{next_task.get('emoji', '')} {next_task.get('name', '')}".strip() if next_task else "All clear",
            "start": next_task.get("scheduled_start", "") if next_task else "",
            "end": next_task.get("scheduled_end", "") if next_task else "",
        } if next_task else {"name": "All clear", "start": "", "end": ""},
        "schedule": blocks,
        "model": {
            "sleep_wake": model.get("sleep", {}).get("wake", "07:00"),
            "sleep_bed": model.get("sleep", {}).get("bed", "23:00"),
            "energy_peak": model.get("energy", {}).get("peak", ""),
            "energy_low": model.get("energy", {}).get("low", ""),
        },
    }

    WALLPAPER_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WALLPAPER_DATA_PATH, "w") as f:
        json.dump(data, f, indent=2)


def read_wallpaper_data() -> dict | None:
    if not WALLPAPER_DATA_PATH.exists():
        return None
    try:
        with open(WALLPAPER_DATA_PATH) as f:
            d = json.load(f)
            if d.get("date") != date.today().isoformat():
                return None
            return d
    except (json.JSONDecodeError, IOError):
        return None


__all__ = ["update_wallpaper_data", "read_wallpaper_data"]