from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from selfheal import ClickUpError, retry_sync
from selfheal.config import load_config


CLICKUP_API_BASE_URL = "https://api.clickup.com/api/v2"
CLICKUP_TASK_PAGE_SIZE = 100


def is_clickup_configured() -> bool:
    config = load_config()
    return bool(
        config.get("clickup", {}).get("api_token")
        and config.get("clickup", {}).get("list_ids")
    )


def get_clickup_client():
    config = load_config()
    token = config.get("clickup", {}).get("api_token")
    if not token:
        raise ClickUpError("ClickUp API token is not configured.")

    return httpx.Client(
        base_url=CLICKUP_API_BASE_URL,
        headers={"Authorization": token, "Content-Type": "application/json"},
        timeout=30.0,
    )


def _resolve_list_ids(list_ids: list[str] | None = None) -> list[str]:
    if list_ids:
        return list_ids
    config = load_config()
    resolved = config.get("clickup", {}).get("list_ids")
    if not resolved:
        raise ClickUpError("ClickUp list IDs are not configured.")
    return resolved


def _resolve_list_id(list_id: str | None) -> str:
    if list_id:
        return list_id
    config = load_config()
    resolved = config.get("clickup", {}).get("list_ids")
    if not resolved:
        raise ClickUpError("ClickUp list ID is not configured.")
    return resolved[0]


@retry_sync(max_attempts=3, base_delay=1, max_delay=4)
def _clickup_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    client = get_clickup_client()
    try:
        request = getattr(client, method.lower())
        response = request(path, **kwargs)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ClickUpError(f"ClickUp {method.upper()} {path} returned a non-object response.")
        return data
    except ClickUpError:
        raise
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        status_message = f" with status {status}" if status is not None else ""
        raise ClickUpError(f"ClickUp {method.upper()} {path} failed{status_message}: {exc}") from exc
    finally:
        close = getattr(client, "close", None)
        if close:
            close()


def _parse_status(raw_status: Any) -> str | None:
    if isinstance(raw_status, dict):
        status = raw_status.get("status")
        return str(status) if status is not None else None
    if raw_status is None:
        return None
    return str(raw_status)


def _parse_due_datetime(raw_due_date: Any) -> datetime | None:
    if raw_due_date in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(raw_due_date) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError) as exc:
        raise ClickUpError(f"Invalid ClickUp due_date value: {raw_due_date}") from exc


def _parse_due_date(raw_due_date: Any, due_date_time: bool) -> str | None:
    due_dt = _parse_due_datetime(raw_due_date)
    if due_dt is None:
        return None
    if due_date_time:
        return due_dt.isoformat()
    return due_dt.date().isoformat()


def _parse_time_estimate(raw_time_estimate: Any) -> int | None:
    if raw_time_estimate in (None, ""):
        return None
    try:
        return int(raw_time_estimate) // 60000
    except (TypeError, ValueError) as exc:
        raise ClickUpError(f"Invalid ClickUp time_estimate value: {raw_time_estimate}") from exc


def parse_clickup_task(task: dict[str, Any]) -> dict[str, Any]:
    due_date_time = bool(task.get("due_date_time"))
    due_datetime = _parse_due_datetime(task.get("due_date"))
    due_datetime_iso = due_datetime.isoformat() if due_datetime else None

    return {
        "source": "clickup",
        "external_id": str(task.get("id", "")),
        "name": task.get("name", "Untitled Task"),
        "status": _parse_status(task.get("status")),
        "due_date": _parse_due_date(task.get("due_date"), due_date_time),
        "due_date_time": due_date_time,
        "due_datetime": due_datetime_iso,
        "time_estimate": _parse_time_estimate(task.get("time_estimate")),
        "description": task.get("description") or task.get("text_content"),
        "external_url": task.get("url"),
        "custom_fields": task.get("custom_fields", []),
        "raw": task,
    }


def list_clickup_tasks(list_ids: list[str] | None = None, include_closed: bool = False) -> list[dict[str, Any]]:
    resolved_list_ids = _resolve_list_ids(list_ids)
    all_tasks: list[dict[str, Any]] = []
    
    for list_id in resolved_list_ids:
        page = 0
        while True:
            data = _clickup_request(
                "GET",
                f"/list/{list_id}/task",
                params={"include_closed": str(include_closed).lower(), "page": page},
            )
            tasks = data.get("tasks", [])
            if not isinstance(tasks, list):
                raise ClickUpError("ClickUp list tasks response did not include a task list.")
            all_tasks.extend(parse_clickup_task(task) for task in tasks if isinstance(task, dict))
            if not tasks or len(tasks) < CLICKUP_TASK_PAGE_SIZE:
                break
            page += 1
    return all_tasks


def update_clickup_task_status(task_id: str, status: str) -> dict[str, Any]:
    if not task_id:
        raise ClickUpError("ClickUp task ID is required to update status.")
    if not status:
        raise ClickUpError("ClickUp status is required to update a task.")
    return _clickup_request("PUT", f"/task/{task_id}", json={"status": status})


def update_clickup_task_dates(task_id: str, start_dt: datetime | None, due_dt: datetime | None) -> dict[str, Any]:
    if not task_id:
        raise ClickUpError("ClickUp task ID is required to update dates.")
    
    payload: dict[str, Any] = {}
    if start_dt:
        # ClickUp expects milliseconds
        payload["start_date"] = int(start_dt.timestamp() * 1000)
    if due_dt:
        payload["due_date"] = int(due_dt.timestamp() * 1000)
        
    if not payload:
        return {}
        
    return _clickup_request("PUT", f"/task/{task_id}", json=payload)


def add_clickup_task_comment(task_id: str, comment: str) -> dict[str, Any]:
    if not task_id:
        raise ClickUpError("ClickUp task ID is required to add a comment.")
    if not comment:
        raise ClickUpError("ClickUp comment text is required.")
    return _clickup_request("POST", f"/task/{task_id}/comment", json={"comment_text": comment})


def _task_in_range(task: dict[str, Any], start_date: date | None, end_date: date | None) -> bool:
    due_date = task.get("due_date")
    if due_date is None:
        return False
    due_day = datetime.fromisoformat(task["due_datetime"]).date()
    if start_date and due_day < start_date:
        return False
    if end_date and due_day > end_date:
        return False
    return True


def list_clickup_events(start_date: date | None = None, end_date: date | None = None) -> list[dict[str, Any]]:
    events = []
    for task in list_clickup_tasks():
        if not _task_in_range(task, start_date, end_date):
            continue

        start = task["due_datetime"] if task["due_date_time"] else task["due_date"]
        if task["due_date_time"]:
            start_dt = datetime.fromisoformat(task["due_datetime"])
            minutes = task.get("time_estimate") or 60
            end = (start_dt + timedelta(minutes=minutes)).isoformat()
        else:
            end = start

        events.append(
            {
                "id": task["external_id"],
                "summary": f"[ClickUp] {task['name']}",
                "start": start,
                "end": end,
                "all_day": not task["due_date_time"],
                "description": task.get("description"),
                "provider": "clickup",
                "source": "clickup",
                "external_id": task["external_id"],
                "external_url": task.get("external_url"),
            }
        )

    events.sort(key=lambda event: event["start"])
    return events
