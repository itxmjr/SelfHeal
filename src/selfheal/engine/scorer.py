from __future__ import annotations

from datetime import date

from ..config import load_config
from ..db import get_connection, get_todays_tasks, save_score, get_score, get_streak


def calculate_score(today: date | None = None) -> dict:
    today = today or date.today()
    conn = get_connection()
    config = load_config()
    weights = config["scoring"]["weights"]
    streak_threshold = config["scoring"]["streak_threshold"]

    tasks = get_todays_tasks(conn, today.isoformat())

    if not tasks:
        conn.close()
        return {"score": 0, "task_completion": 0, "time_utilization": 0,
                "goal_alignment": 0, "consistency_bonus": 0}

    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "done")

    task_completion = (done / total * weights["task_completion"]) if total > 0 else 0

    on_time = 0
    scheduled_count = 0
    for t in tasks:
        if t.get("status") == "done" and t.get("scheduled_end") and t.get("actual_end"):
            scheduled_count += 1
            if t["actual_end"] <= t["scheduled_end"]:
                on_time += 1
    time_utilization = (on_time / scheduled_count * weights["time_utilization"]) if scheduled_count > 0 else (done / total * weights["time_utilization"] * 0.7) if total > 0 else 0

    goal_tasks = [t for t in tasks if t.get("goal_id")]
    goal_done = sum(1 for t in goal_tasks if t.get("status") == "done")
    goal_alignment = (goal_done / len(goal_tasks) * weights["goal_alignment"]) if goal_tasks else (done / total * weights["goal_alignment"] * 0.5)

    streak = get_streak(conn, streak_threshold)
    consistency_bonus = min(streak * 2, weights["consistency_bonus"])

    score = min(100, task_completion + time_utilization + goal_alignment + consistency_bonus)

    save_score(conn, today.isoformat(), score, task_completion, time_utilization, goal_alignment, consistency_bonus)
    conn.close()

    return {
        "score": round(score, 1),
        "task_completion": round(task_completion, 1),
        "time_utilization": round(time_utilization, 1),
        "goal_alignment": round(goal_alignment, 1),
        "consistency_bonus": round(consistency_bonus, 1),
        "done": done,
        "total": total,
        "streak": streak,
    }


def get_today_score(today: date | None = None) -> dict | None:
    today = today or date.today()
    conn = get_connection()
    result = get_score(conn, today.isoformat())
    conn.close()
    return result
