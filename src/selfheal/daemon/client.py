from __future__ import annotations

import json
import socket
from datetime import date
from typing import Any

from ..config import CONFIG_DIR
from ..errors import DaemonError

DAEMON_SOCKET_PATH = CONFIG_DIR / "daemon.sock"


def is_daemon_running() -> bool:
    try:
        daemon_send_cmd("ping", timeout=1.0)
        return True
    except DaemonError:
        return False


def daemon_send_cmd(cmd: str, *, timeout: float = 10.0, **kwargs: Any) -> dict[str, Any]:
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(str(DAEMON_SOCKET_PATH))
        try:
            msg = json.dumps({"cmd": cmd, **kwargs}) + "\n"
            sock.sendall(msg.encode())
            resp = b""
            data: dict[str, Any] | None = None
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                resp += chunk
                try:
                    data = json.loads(resp.decode())
                    break
                except json.JSONDecodeError:
                    continue
            else:
                raise DaemonError("daemon returned no response")
        finally:
            sock.close()
    except (OSError, TimeoutError) as exc:
        raise DaemonError(f"daemon connection failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DaemonError(f"daemon returned invalid JSON: {exc}") from exc

    if not resp:
        raise DaemonError("daemon returned no response")
    if data is None or not isinstance(data, dict) or "ok" not in data:
        raise DaemonError("daemon returned a malformed response")
    if not data.get("ok", False):
        raise DaemonError(str(data.get("error", "daemon command failed")))
    return data


def daemon_send(cmd: str, **kwargs: Any) -> dict[str, Any]:
    try:
        return daemon_send_cmd(cmd, **kwargs)
    except DaemonError as exc:
        return {"ok": False, "error": str(exc)}


def daemon_refresh() -> bool:
    r = daemon_send_cmd("refresh")
    return r.get("ok", False)


def daemon_regenerate() -> bool:
    r = daemon_send_cmd("regenerate")
    return r.get("ok", False)


def daemon_sync_clickup() -> dict[str, Any]:
    return daemon_send_cmd("sync_clickup").get("data", {})


def daemon_sync_calendar() -> dict[str, Any]:
    return daemon_send_cmd("sync_calendar").get("data", {})


def daemon_sync_obsidian() -> dict[str, Any]:
    return daemon_send_cmd("sync_obsidian").get("data", {})


def daemon_sync_all() -> dict[str, Any]:
    return daemon_send_cmd("sync_all").get("data", {})


def daemon_add_task(
    name: str,
    priority: str = "medium",
    emoji: str = "",
    estimated_minutes: int = 30,
    schedule: str = "daily",
) -> int:
    data = daemon_send_cmd(
        "add_task",
        name=name,
        priority=priority,
        emoji=emoji,
        estimated_minutes=estimated_minutes,
        schedule=schedule,
    ).get("data", {})
    return int(data["task_id"])


def daemon_generate_schedule(target_date: date | str | None = None) -> list[dict[str, Any]]:
    date_value = target_date.isoformat() if isinstance(target_date, date) else target_date
    if date_value:
        return daemon_send_cmd("generate_schedule", date=date_value).get("data", [])
    return daemon_send_cmd("generate_schedule").get("data", [])


def daemon_mark_task_done(task_id: int) -> dict[str, Any]:
    return daemon_send_cmd("mark_task_done", task_id=task_id).get("data", {})


def daemon_mark_task_pending(task_id: int) -> dict[str, Any]:
    return daemon_send_cmd("mark_task_pending", task_id=task_id).get("data", {})


def daemon_toggle_task(task_id: int) -> dict[str, Any]:
    return daemon_send_cmd("toggle_task", task_id=task_id).get("data", {})


def daemon_get_status() -> dict[str, Any]:
    return daemon_send_cmd("status").get("data", {})


def daemon_get_score() -> dict[str, Any]:
    return daemon_send_cmd("get_score").get("data", {})


def daemon_get_next() -> dict[str, Any] | None:
    return daemon_send_cmd("get_next").get("data")


def daemon_get_tasks() -> list[dict[str, Any]]:
    return daemon_send_cmd("get_tasks").get("data", [])


def daemon_stop() -> bool:
    r = daemon_send_cmd("quit")
    return r.get("ok", False)
