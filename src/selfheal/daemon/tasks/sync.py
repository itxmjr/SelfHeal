from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from typing import Any

from ...calendar import (
    is_clickup_configured,
    list_all_events,
    list_clickup_tasks,
)
from ...db import get_connection, upsert_task

logger = logging.getLogger(__name__)


def sync_calendar_task() -> dict[str, Any]:
    """Sync calendar events in the background."""
    events = list_all_events(date.today(), date.today())
    logger.info("Synced %s aggregated calendar event(s)", len(events))
    return {"provider": "all", "count": len(events), "events": events}


def sync_clickup_task() -> dict[str, Any]:
    """List ClickUp tasks and upsert them into SQLite."""
    if not is_clickup_configured():
        return {"configured": False, "count": 0, "task_ids": []}

    clickup_tasks = list_clickup_tasks()
    conn = get_connection()
    task_ids: list[int] = []
    try:
        for task in clickup_tasks:
            external_id = task.get("external_id")
            if not external_id:
                continue
            task_id = _upsert_clickup_task(conn, task)
            task_ids.append(task_id)
            _log_sync(conn, "clickup", "upsert_task", str(external_id), "ok", None)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        _log_sync(conn, "clickup", "upsert_task", None, "error", str(exc))
        conn.commit()
        raise
    finally:
        conn.close()

    logger.info("Synced %s ClickUp task(s)", len(task_ids))
    return {"configured": True, "count": len(task_ids), "task_ids": task_ids}


def update_wallpaper_task() -> dict[str, Any]:
    """Update wallpaper data json for external engines."""
    try:
        from ...wallpaper import update_wallpaper_data
        update_wallpaper_data()
        return {"updated": True}
    except Exception:
        logger.exception("Wallpaper update task failed")
        return {"updated": False}


def obsidian_sync_task() -> dict[str, Any]:
    """Sync today's report to obsidian."""
    try:
        from ...obsidian import sync_to_obsidian
        sync_to_obsidian()
        return {"synced": True}
    except Exception:
        logger.exception("Obsidian sync task failed")
        return {"synced": False}


def sync_all_task() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, task in (
        ("calendar", sync_calendar_task),
        ("clickup", sync_clickup_task),
        ("wallpaper", update_wallpaper_task),
        ("obsidian", obsidian_sync_task),
    ):
        try:
            results[name] = task()
        except Exception as exc:
            logger.exception("%s sync failed", name)
            results[name] = {"ok": False, "error": str(exc)}
    return results


def _upsert_clickup_task(conn, task: dict[str, Any]) -> int:
    external_id = str(task["external_id"])
    raw_value = task.get("raw")
    raw = raw_value if isinstance(raw_value, dict) else {}
    external_updated_at = _parse_clickup_timestamp(raw.get("date_updated"))
    sync_hash = _task_sync_hash(task)
    estimated_minutes = task.get("time_estimate") or 30

    existing = conn.execute(
        "SELECT id FROM tasks WHERE source = ? AND external_id = ?",
        ("clickup", external_id),
    ).fetchone()
    if existing:
        task_id = int(existing["id"])
        conn.execute(
            "UPDATE tasks SET name=?, estimated_minutes=?, source='clickup', external_id=?, "
            "external_url=?, external_updated_at=?, sync_hash=?, is_active=1 WHERE id=?",
            (
                task.get("name", "Untitled Task"),
                estimated_minutes,
                external_id,
                task.get("external_url"),
                external_updated_at,
                sync_hash,
                task_id,
            ),
        )
        return task_id

    return upsert_task(
        conn,
        name=task.get("name", "Untitled Task"),
        schedule="daily",
        priority="medium",
        estimated_minutes=estimated_minutes,
        source="clickup",
        external_id=external_id,
        external_url=task.get("external_url"),
        external_updated_at=external_updated_at,
        sync_hash=sync_hash,
    )


def _log_sync(conn, source: str, action: str, external_id: str | None, status: str, error: str | None) -> None:
    conn.execute(
        "INSERT INTO sync_log (source, action, external_id, status, error) VALUES (?, ?, ?, ?, ?)",
        (source, action, external_id, status, error),
    )


def _parse_clickup_timestamp(raw_value: Any) -> str | None:
    if raw_value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(raw_value) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(raw_value)


def _task_sync_hash(task: dict[str, Any]) -> str:
    payload = {
        "name": task.get("name"),
        "status": task.get("status"),
        "time_estimate": task.get("time_estimate"),
        "external_url": task.get("external_url"),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
