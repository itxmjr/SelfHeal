from __future__ import annotations

import json
import logging
import re
import sqlite3
import datetime as dt
from datetime import date
from typing import Any

import yaml

from ..config import load_life_model
from ..db import get_connection, get_todays_tasks, upsert_task
from ..llm import get_llm_with_fallback
from ..result import Result
from .life_model import get_available_hours, get_goals_for_today
from .scheduler_prompts import SCHEDULER_PROMPT

logger = logging.getLogger(__name__)


def get_schedule_task_candidates(
    conn: sqlite3.Connection,
    life_model: dict[str, Any] | None,
    today: date,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_identities: set[tuple[str, Any] | tuple[str, str, str]] = set()

    for task in get_todays_tasks(conn, today.isoformat()):
        if task.get("status") == "done":
            continue
        task_candidate = _candidate_from_task(task)
        identity = _candidate_identity(task_candidate)
        if identity in seen_identities:
            continue
        if identity is not None:
            seen_identities.add(identity)
        candidates.append(task_candidate)

    for goal in get_goals_for_today(life_model, today):
        goal_candidate = _candidate_from_goal(goal)
        identity = _candidate_identity(goal_candidate)
        if identity in seen_identities:
            continue
        if identity is not None:
            seen_identities.add(identity)
        candidates.append(goal_candidate)

    return candidates


def _build_continuous_blocks(hours: list[dict], today: date) -> list[dict]:
    blocks = []
    if not hours: return blocks
    current_start = None
    current_end = None
    current_status = None
    
    for h in sorted(hours, key=lambda x: x["hour"]):
        if h["status"] in ("committed",):
            continue
            
        slot_start = dt.datetime.combine(today, dt.time(h["hour"], 0))
        slot_end = slot_start + dt.timedelta(hours=1)
        
        if current_status == h["status"] and current_end == slot_start:
            current_end = slot_end
        else:
            if current_start is not None:
                blocks.append({"start": current_start, "end": current_end, "status": current_status})
            current_start = slot_start
            current_end = slot_end
            current_status = h["status"]
            
    if current_start is not None:
         blocks.append({"start": current_start, "end": current_end, "status": current_status})
    return blocks

def _allocate_task(blocks: list[dict], needed_minutes: int, preferred_statuses: list[str]) -> tuple[str, str] | tuple[None, None]:
    for status in preferred_statuses:
        for i, block in enumerate(blocks):
            if block["status"] == status:
                block_mins = int((block["end"] - block["start"]).total_seconds() / 60)
                if block_mins >= needed_minutes:
                    allocated_start = block["start"]
                    allocated_end = allocated_start + dt.timedelta(minutes=needed_minutes)
                    
                    block["start"] = allocated_end
                    if block["start"] >= block["end"]:
                        blocks.pop(i)
                    return allocated_start.strftime("%H:%M"), allocated_end.strftime("%H:%M")
    
    # Fallback to any block that fits
    for i, block in enumerate(blocks):
        block_mins = int((block["end"] - block["start"]).total_seconds() / 60)
        if block_mins >= needed_minutes:
            allocated_start = block["start"]
            allocated_end = allocated_start + dt.timedelta(minutes=needed_minutes)
            
            block["start"] = allocated_end
            if block["start"] >= block["end"]:
                blocks.pop(i)
            return allocated_start.strftime("%H:%M"), allocated_end.strftime("%H:%M")
            
    return None, None

def generate_schedule(
    *,
    today: date,
    life_model: dict[str, Any] | None,
    task_candidates: list[dict[str, Any]],
    calendar_events: list[dict[str, Any]] | None,
    use_ai: bool,
) -> tuple[list[dict[str, Any]], bool]:
    if not life_model or not task_candidates:
        return [], False

    hours = get_available_hours(life_model, calendar_events=calendar_events)
    blocks = _build_continuous_blocks(hours, today)

    schedule: list[dict[str, Any]] = []
    sorted_candidates = sorted(
        task_candidates,
        key=lambda task: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
            task.get("priority", "medium"), 2
        ),
    )

    for candidate in sorted_candidates:
        estimated_minutes = candidate.get("estimated_minutes") or candidate.get("time_estimate") or 30
        
        priority = candidate.get("priority", "medium")
        if priority in ("critical", "high"):
            preferred_statuses = ["peak", "free", "low"]
        else:
            preferred_statuses = ["low", "free", "peak"]
            
        start_time, end_time = _allocate_task(blocks, estimated_minutes, preferred_statuses)
        if start_time and end_time:
            schedule.append(_make_item(candidate, start_time, end_time))

    schedule.sort(key=lambda item: item["start_time"])

    ai_success = False
    if use_ai:
        refinement = _refine_with_ai(life_model, schedule, today)
        if refinement.is_ok():
            schedule = refinement.value
            ai_success = True
        else:
            logger.warning("AI schedule refinement failed; using heuristic schedule: %s", refinement.error)

    return schedule, ai_success


def schedule_item_to_db(
    schedule_item: dict[str, Any],
    target_date: date,
    conn: sqlite3.Connection,
) -> int:
    task_id = _resolve_existing_task_id(conn, schedule_item)

    if task_id is None:
        task_id = upsert_task(
            conn,
            name=schedule_item["name"],
            emoji=schedule_item.get("emoji", ""),
            schedule=schedule_item.get("schedule", "dynamic"),
            priority=schedule_item.get("priority", "medium"),
            goal_id=schedule_item.get("goal_id"),
            depends_on=schedule_item.get("depends_on", ""),
            estimated_minutes=schedule_item.get("estimated_minutes", 30),
            source=schedule_item.get("source", "manual"),
            external_id=schedule_item.get("external_id"),
            external_url=schedule_item.get("external_url"),
            external_updated_at=schedule_item.get("external_updated_at"),
            sync_hash=schedule_item.get("sync_hash"),
        )
    else:
        _update_task_from_schedule_item(conn, task_id, schedule_item)

    conn.execute(
        "INSERT INTO daily_logs (date, task_id, status, scheduled_start, scheduled_end) "
        "VALUES (?, ?, 'pending', ?, ?) "
        "ON CONFLICT(date, task_id) DO UPDATE SET scheduled_start=?, scheduled_end=?",
        (
            target_date.isoformat(),
            task_id,
            schedule_item.get("start_time", "09:00"),
            schedule_item.get("end_time", "09:30"),
            schedule_item.get("start_time", "09:00"),
            schedule_item.get("end_time", "09:30"),
        ),
    )
    return task_id


def persist_schedule(
    schedule: list[dict[str, Any]],
    target_date: date,
    conn: sqlite3.Connection,
) -> list[int]:
    task_ids = [schedule_item_to_db(item, target_date, conn) for item in schedule]
    conn.commit()
    return task_ids


def generate_and_persist_schedule(
    *,
    today: date | None = None,
    life_model: dict[str, Any] | None = None,
    task_candidates: list[dict[str, Any]] | None = None,
    calendar_events: list[dict[str, Any]] | None = None,
    use_ai: bool = True,
) -> tuple[list[dict[str, Any]], bool]:
    target_date = today or date.today()
    model = life_model if life_model is not None else load_life_model()
    if not model:
        return [], False

    conn = get_connection()
    try:
        candidates = task_candidates
        if candidates is None:
            candidates = get_schedule_task_candidates(conn, model, target_date)
        schedule, ai_success = generate_schedule(
            today=target_date,
            life_model=model,
            task_candidates=candidates,
            calendar_events=calendar_events or [],
            use_ai=use_ai,
        )
        persist_schedule(schedule, target_date, conn)
        return schedule, ai_success
    finally:
        conn.close()


def _refine_with_ai(
    model: dict[str, Any],
    heuristic_schedule: list[dict[str, Any]],
    today: date,
) -> Result[list[dict[str, Any]], str]:
    try:
        llm = get_llm_with_fallback(task_type="scheduling")
        prompt = SCHEDULER_PROMPT.format(
            life_model=yaml.dump(model),
            heuristic_schedule=json.dumps(heuristic_schedule, indent=2),
            today=today.isoformat(),
        )

        response = llm.chat([{"role": "system", "content": prompt}])
        match = re.search(r"\[.*\]", response.content, re.DOTALL)
        if not match:
            return Result.err("AI response did not contain a JSON schedule list")

        parsed = json.loads(match.group(0))
        if not isinstance(parsed, list):
            return Result.err("AI response JSON was not a schedule list")
        return Result.ok(parsed)
    except Exception as exc:
        logger.exception("AI schedule refinement failed")
        return Result.err(str(exc))


def _candidate_from_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.get("id"),
        "task_id": task.get("id"),
        "name": task.get("name", "Task"),
        "emoji": task.get("emoji", ""),
        "priority": task.get("priority", "medium"),
        "estimated_minutes": task.get("estimated_minutes") or task.get("time_estimate") or 30,
        "schedule": task.get("schedule", "dynamic"),
        "goal_id": task.get("goal_id"),
        "depends_on": task.get("depends_on", ""),
        "source": task.get("source", "manual"),
        "external_id": task.get("external_id"),
        "external_url": task.get("external_url"),
        "external_updated_at": task.get("external_updated_at"),
        "sync_hash": task.get("sync_hash"),
        "preferred_time": task.get("preferred_time"),
    }


def _candidate_from_goal(goal: dict[str, Any]) -> dict[str, Any]:
    source = goal.get("source") or "life_model"
    return {
        **goal,
        "source": source,
        "external_id": goal.get("external_id") or _life_model_goal_external_id(goal),
    }


def _candidate_identity(candidate: dict[str, Any]) -> tuple[str, str, str] | tuple[str, Any] | None:
    source = candidate.get("source")
    external_id = candidate.get("external_id")
    if source and external_id:
        return ("external", str(source), str(external_id))

    task_id = candidate.get("task_id") or candidate.get("id")
    if task_id is not None:
        return ("task", task_id)

    return None


def _life_model_goal_external_id(goal: dict[str, Any]) -> str:
    name = _normalize_identity_part(goal.get("name", "Task"))
    frequency = _normalize_identity_part(goal.get("frequency", "daily"))
    preferred_time = _normalize_identity_part(goal.get("preferred_time", "anytime"))
    return f"goal:{name}:{frequency}:{preferred_time}"


def _normalize_identity_part(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
    return normalized or "none"


def _resolve_existing_task_id(conn: sqlite3.Connection, schedule_item: dict[str, Any]) -> int | None:
    task_id = schedule_item.get("task_id") or schedule_item.get("id")
    if task_id is not None:
        row = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row:
            return int(row["id"])

    source = schedule_item.get("source")
    external_id = schedule_item.get("external_id")
    if source and external_id:
        row = conn.execute(
            "SELECT id FROM tasks WHERE source = ? AND external_id = ?",
            (source, external_id),
        ).fetchone()
        if row:
            return int(row["id"])

    return None


def _update_task_from_schedule_item(
    conn: sqlite3.Connection,
    task_id: int,
    schedule_item: dict[str, Any],
) -> None:
    conn.execute(
        "UPDATE tasks SET name=?, emoji=?, schedule=?, priority=?, goal_id=?, depends_on=?, "
        "estimated_minutes=?, source=?, external_id=?, external_url=?, external_updated_at=?, sync_hash=? "
        "WHERE id=?",
        (
            schedule_item["name"],
            schedule_item.get("emoji", ""),
            schedule_item.get("schedule", "dynamic"),
            schedule_item.get("priority", "medium"),
            schedule_item.get("goal_id"),
            schedule_item.get("depends_on", ""),
            schedule_item.get("estimated_minutes", 30),
            schedule_item.get("source", "manual"),
            schedule_item.get("external_id"),
            schedule_item.get("external_url"),
            schedule_item.get("external_updated_at"),
            schedule_item.get("sync_hash"),
            task_id,
        ),
    )


def _make_item(candidate: dict[str, Any], start_time: str, end_time: str) -> dict[str, Any]:
    emojis = {
        "Fitness": "🏃", "Learn AI": "🤖", "Job Applications": "💼",
        "Code Practice": "💻", "Reading": "📖", "Study": "📚",
    }
    estimated_minutes = candidate.get("estimated_minutes") or candidate.get("time_estimate") or 30
    item = {
        "name": candidate.get("name", "Task"),
        "emoji": candidate.get("emoji", emojis.get(candidate.get("name", ""), "📌")),
        "priority": candidate.get("priority", "medium"),
        "start_time": start_time,
        "end_time": end_time,
        "estimated_minutes": estimated_minutes,
        "status": "pending",
        "schedule": candidate.get("schedule", "dynamic"),
        "goal_id": candidate.get("goal_id"),
        "depends_on": candidate.get("depends_on", ""),
        "source": candidate.get("source", "manual"),
    }

    for key in ("id", "task_id", "external_id", "external_url", "external_updated_at", "sync_hash"):
        if candidate.get(key) is not None:
            item[key] = candidate[key]

    return item


def get_next_action() -> dict[str, Any] | None:
    model = load_life_model()
    if not model:
        return None

    now = date.today()
    conn = get_connection()
    tasks = get_todays_tasks(conn, now.isoformat())
    conn.close()

    import datetime as dt
    current_hour = dt.datetime.now().hour

    pending = [t for t in tasks if t.get("status") == "pending"]
    if not pending:
        return None

    current_task = None
    for t in pending:
        start = t.get("scheduled_start")
        if start:
            try:
                sh = int(start.split(":")[0])
                if sh <= current_hour:
                    current_task = t
                    break
            except (ValueError, IndexError):
                pass

    if current_task:
        return current_task

    return pending[0]


def regenerate_schedule(
    today: date | None = None,
    calendar_events: list[dict[str, Any]] | None = None,
    current_hour: int | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    target_date = today or date.today()
    model = load_life_model()
    if not model:
        return [], False

    conn = get_connection()
    try:
        tasks = get_todays_tasks(conn, target_date.isoformat())

        if current_hour is None:
            import datetime as dt
            current_hour = dt.datetime.now().hour
        remaining = [
            t for t in tasks
            if t.get("status") == "pending"
            and (t.get("scheduled_start") is None or int(t["scheduled_start"].split(":")[0]) >= current_hour)
        ]

        if not remaining:
            return [], False

        task_candidates = [_candidate_from_task(task) for task in remaining]
        sleep = model.get("sleep", {})
        future_model = {
            **model,
            "sleep": {
                **sleep,
                "wake": f"{current_hour:02d}:00",
            },
        }

        new_schedule, ai_success = generate_schedule(
            today=target_date,
            life_model=future_model,
            task_candidates=task_candidates,
            calendar_events=calendar_events or [],
            use_ai=False,
        )
        persist_schedule(new_schedule, target_date, conn)
        return new_schedule, ai_success
    finally:
        conn.close()
