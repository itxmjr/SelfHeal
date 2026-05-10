from __future__ import annotations

import httpx
import logging
from datetime import date
from typing import Any, List, Optional

from ..errors import DaemonError

API_BASE_URL = "http://127.0.0.1:8282"
logger = logging.getLogger(__name__)

def is_daemon_running() -> bool:
    try:
        daemon_request("GET", "/system/status", timeout=1.0)
        return True
    except Exception:
        return False

def daemon_request(method: str, path: str, timeout: float = 10.0, **kwargs: Any) -> Any:
    """Core helper for making HTTP requests to the daemon."""
    try:
        with httpx.Client(base_url=API_BASE_URL, timeout=timeout) as client:
            resp = client.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise DaemonError(f"Daemon connection failed: {exc}")

def daemon_get_status() -> dict:
    return daemon_request("GET", "/status")

def daemon_get_tasks() -> List[dict]:
    return daemon_request("GET", "/tasks")

def daemon_get_score() -> dict:
    return daemon_request("GET", "/score")

def daemon_get_next() -> Optional[dict]:
    return daemon_request("GET", "/tasks/next")

def daemon_add_task(name: str, **kwargs) -> int:
    payload = {"name": name, **kwargs}
    res = daemon_request("POST", "/tasks", json=payload)
    return res.get("task_id")

def daemon_toggle_task(task_id: int) -> dict:
    return daemon_request("POST", f"/tasks/{task_id}/toggle")

def daemon_sync_calendar() -> dict:
    return daemon_request("POST", "/sync/calendar")

def daemon_sync_clickup() -> dict:
    return daemon_request("POST", "/sync/clickup")

def daemon_sync_obsidian() -> dict:
    return daemon_request("POST", "/sync/obsidian")

def daemon_sync_all() -> dict:
    return daemon_request("POST", "/sync")

def daemon_generate_schedule(target_date: Optional[date] = None) -> List[dict]:
    payload = {"date": target_date.isoformat()} if target_date else {}
    res = daemon_request("POST", "/schedule/generate", json=payload)
    return res.get("items", [])

def daemon_regenerate() -> dict:
    return daemon_request("POST", "/schedule/regenerate")
