from __future__ import annotations

import json
import logging
import os
import selectors
import socket
import threading
from datetime import date, datetime, timedelta
from typing import Any

from ..calendar import update_clickup_task_status
from ..config import CONFIG_DIR, load_life_model
from ..db import (
    get_connection,
    get_score,
    get_todays_tasks,
    mark_task_done,
    mark_task_pending,
    save_score,
    upsert_task,
)
from ..engine.scorer import calculate_score
from .tasks.notify import check_overdue_tasks, check_task_transitions
from .tasks.schedule import generate_schedule_task
from .tasks.sync import (
    obsidian_sync_task,
    sync_all_task,
    sync_calendar_task,
    sync_clickup_task,
    update_wallpaper_task,
)

DAEMON_SOCKET_PATH = CONFIG_DIR / "daemon.sock"
DAEMON_PID_PATH = CONFIG_DIR / "daemon.pid"
NOTIFY_INTERVAL_MINUTES = 15
SCHEDULE_HOUR = 6
CALENDAR_SYNC_MINUTES = 30
CLICKUP_SYNC_MINUTES = 30
WALLPAPER_UPDATE_MINUTES = 10

logger = logging.getLogger(__name__)


class DaemonServer:
    def __init__(self):
        self._running = True
        self._socket_path = DAEMON_SOCKET_PATH
        self._selector = selectors.DefaultSelector()
        self._clients: list[socket.socket] = []
        self._started_at = datetime.now()
        self._last_schedule_generated: str | None = None
        self._last_schedule_ai_success: bool | None = None
        self._last_calendar_sync: datetime | None = None
        self._last_clickup_sync: datetime | None = None
        self._last_wallpaper_update: datetime | None = None
        self._last_notify_check: datetime | None = None

    def start(self) -> None:
        self._ensure_single_instance()
        self._bind_socket()
        self._selector.register(self._server_sock, selectors.EVENT_READ, self._accept)
        self._mark_running()
        self._run_loop()

    def stop(self) -> None:
        self._running = False
        self._cleanup()

    def _ensure_single_instance(self) -> None:
        if DAEMON_PID_PATH.exists():
            try:
                pid = int(DAEMON_PID_PATH.read_text().strip())
                os.kill(pid, 0)
                raise RuntimeError(f"Daemon already running as PID {pid}")
            except (ValueError, ProcessLookupError, OSError):
                DAEMON_PID_PATH.unlink(missing_ok=True)
        DAEMON_PID_PATH.write_text(str(os.getpid()))

    def _bind_socket(self) -> None:
        self._socket_path.unlink(missing_ok=True)
        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(str(self._socket_path))
        self._server_sock.listen(32)
        self._server_sock.setblocking(False)

    def _mark_running(self) -> None:
        self._pid_file = DAEMON_PID_PATH

    def _accept(self, sock: socket.socket, mask: Any) -> None:
        conn, _ = sock.accept()
        conn.setblocking(False)
        self._selector.register(conn, selectors.EVENT_READ, self._handle)

    def _handle(self, conn: socket.socket, mask: Any) -> None:
        try:
            data = conn.recv(4096)
            if not data:
                self._selector.unregister(conn)
                conn.close()
                return
            msg = json.loads(data.decode())
            resp = self._process_command(msg)
            conn.sendall((json.dumps(resp) + "\n").encode())
        except (json.JSONDecodeError, ConnectionResetError, BrokenPipeError):
            self._selector.unregister(conn)
            conn.close()

    def _process_command(self, msg: dict) -> dict:
        try:
            cmd = msg.get("cmd", "")
            if cmd == "ping":
                return {"ok": True, "data": {"pid": os.getpid(), "uptime": self._uptime()}}
            if cmd == "status":
                return {"ok": True, "data": self._get_status()}
            if cmd == "refresh":
                self._run_background_tasks(force=True)
                return {"ok": True, "data": "refreshed"}
            if cmd == "sync_clickup":
                data = sync_clickup_task()
                self._last_clickup_sync = datetime.now()
                return {"ok": True, "data": data}
            if cmd == "sync_calendar":
                data = sync_calendar_task()
                self._last_calendar_sync = datetime.now()
                return {"ok": True, "data": data}
            if cmd == "sync_obsidian":
                data = obsidian_sync_task()
                return {"ok": True, "data": data}
            if cmd == "sync_all":
                data = self._sync_all()
                return {"ok": True, "data": data}
            if cmd in ("generate_schedule", "regenerate"):
                target_date = self._date_from_message(msg)
                schedule, ai_success = generate_schedule_task(target_date)
                self._last_schedule_generated = target_date.isoformat()
                self._last_schedule_ai_success = ai_success
                data: Any = schedule if cmd == "generate_schedule" else "schedule regenerated"
                return {"ok": True, "data": data}
            if cmd == "add_task":
                task_id = self._add_task(msg)
                return {"ok": True, "data": {"task_id": task_id}}
            if cmd == "toggle_task":
                task = self._toggle_task(int(msg["task_id"]))
                return {"ok": True, "data": task}
            if cmd == "mark_task_done":
                task = self._mark_task_status(int(msg["task_id"]), "done")
                return {"ok": True, "data": task}
            if cmd == "mark_task_pending":
                task = self._mark_task_status(int(msg["task_id"]), "pending")
                return {"ok": True, "data": task}
            if cmd == "quit":
                threading.Thread(target=self.stop, daemon=True).start()
                return {"ok": True, "data": "stopping"}
            if cmd == "get_score":
                score = calculate_score()
                return {"ok": True, "data": score}
            if cmd == "get_next":
                from ..engine.scheduler import get_next_action
                action = get_next_action()
                return {"ok": True, "data": action}
            if cmd == "get_tasks":
                conn = get_connection()
                tasks = get_todays_tasks(conn, msg.get("date"))
                conn.close()
                return {"ok": True, "data": tasks}
            return {"ok": False, "error": f"unknown command: {cmd}"}
        except Exception as exc:
            logger.exception("Daemon command failed: %s", msg.get("cmd", ""))
            return {"ok": False, "error": str(exc)}

    def _get_status(self) -> dict:
        return {
            "pid": os.getpid(),
            "uptime": self._uptime(),
            "started_at": self._started_at.isoformat(),
            "last_schedule": self._last_schedule_generated,
            "last_schedule_ai_success": getattr(self, "_last_schedule_ai_success", None),
            "last_calendar_sync": self._format_time(self._last_calendar_sync),
            "last_clickup_sync": self._format_time(self._last_clickup_sync),
            "last_wallpaper_update": self._format_time(self._last_wallpaper_update),
            "socket": str(self._socket_path),
            "daemon_connected": True,
        }

    def _uptime(self) -> str:
        elapsed = datetime.now() - self._started_at
        return str(timedelta(seconds=int(elapsed.total_seconds())))

    def _run_loop(self) -> None:
        while self._running:
            for key, mask in self._selector.select(timeout=1.0):
                callback = key.data
                callback(key.fileobj, mask)
            self._run_background_tasks()

    def _run_background_tasks(self, force: bool = False) -> None:
        now = datetime.now()
        model = load_life_model()

        self._run_daemon_task("morning schedule generation", self._check_morning_generation, model, now, force)
        self._run_daemon_task("overdue notification check", self._check_notify, model, now, force)
        self._run_daemon_task("calendar sync", self._check_calendar_sync, model, now, force)
        self._run_daemon_task("clickup sync", self._check_clickup_sync, model, now, force)
        self._run_daemon_task("wallpaper update", self._check_wallpaper_update, model, now, force)
        self._run_daemon_task("score save", self._check_score_save, model, now, force)
        self._run_daemon_task("obsidian sync", self._check_obsidian_sync, model, now, force)
        self._run_daemon_task("task transition check", self._check_task_transitions, model, now, force)

    def _run_daemon_task(self, name: str, func, *args) -> None:
        try:
            func(*args)
        except Exception:
            logger.exception("Daemon task failed: %s", name)

    def _check_morning_generation(self, model, now: datetime, force: bool) -> None:
        today_str = date.today().isoformat()
        should_generate = (
            force or
            self._last_schedule_generated != today_str or
            now.hour >= SCHEDULE_HOUR and self._last_schedule_generated != today_str
        )
        if should_generate and model:
            _, ai_success = generate_schedule_task()
            self._last_schedule_generated = today_str
            self._last_schedule_ai_success = ai_success

    def _check_notify(self, model, now: datetime, force: bool) -> None:
        if not model:
            return
        if force or self._last_notify_check is None or \
           (now - self._last_notify_check) >= timedelta(minutes=NOTIFY_INTERVAL_MINUTES):
            self._last_notify_check = now
            check_overdue_tasks()

    def _check_calendar_sync(self, model, now: datetime, force: bool) -> None:
        if force or self._last_calendar_sync is None or \
           (now - self._last_calendar_sync) >= timedelta(minutes=CALENDAR_SYNC_MINUTES):
            sync_calendar_task()
            self._last_calendar_sync = now

    def _check_clickup_sync(self, model, now: datetime, force: bool) -> None:
        if force or self._last_clickup_sync is None or \
           (now - self._last_clickup_sync) >= timedelta(minutes=CLICKUP_SYNC_MINUTES):
            sync_clickup_task()
            self._last_clickup_sync = now

    def _check_wallpaper_update(self, model, now: datetime, force: bool) -> None:
        if force or self._last_wallpaper_update is None or \
           (now - self._last_wallpaper_update) >= timedelta(minutes=WALLPAPER_UPDATE_MINUTES):
            update_wallpaper_task()
            self._last_wallpaper_update = now

    def _check_score_save(self, model, now: datetime, force: bool) -> None:
        if not model:
            return
        today_str = date.today().isoformat()
        conn = get_connection()
        existing = get_score(conn, today_str)
        conn.close()
        if existing is None or force:
            score = calculate_score()
            conn2 = get_connection()
            save_score(
                conn2, today_str,
                score["score"], score["task_completion"],
                score["time_utilization"], score["goal_alignment"],
                score["consistency_bonus"],
            )
            conn2.close()

    def _check_obsidian_sync(self, model, now: datetime, force: bool) -> None:
        if force or (now.minute % 30 == 0 and now.second < 2):
            obsidian_sync_task()

    def _check_task_transitions(self, model, now: datetime, force: bool) -> None:
        check_task_transitions(now, force)

    def _sync_all(self) -> dict[str, Any]:
        data = sync_all_task()
        now = datetime.now()
        self._last_calendar_sync = now
        self._last_clickup_sync = now
        self._last_wallpaper_update = now
        return data

    def _add_task(self, msg: dict[str, Any]) -> int:
        name = str(msg.get("name") or "").strip()
        if not name:
            raise ValueError("task name is required")
        conn = get_connection()
        try:
            return upsert_task(
                conn,
                name=name,
                priority=msg.get("priority", "medium"),
                emoji=msg.get("emoji", ""),
                estimated_minutes=int(msg.get("estimated_minutes", 30)),
                schedule=msg.get("schedule", "daily"),
            )
        finally:
            conn.close()

    def _toggle_task(self, task_id: int) -> dict[str, Any]:
        conn = get_connection()
        try:
            task = self._task_by_id(conn, task_id)
            new_status = "pending" if task.get("status") == "done" else "done"
        finally:
            conn.close()
        return self._mark_task_status(task_id, new_status)

    def _mark_task_status(self, task_id: int, status: str) -> dict[str, Any]:
        if status not in {"done", "pending"}:
            raise ValueError("status must be done or pending")

        conn = get_connection()
        try:
            task = self._task_by_id(conn, task_id)
            if status == "done":
                mark_task_done(conn, task_id)
            else:
                mark_task_pending(conn, task_id)
            updated = self._task_by_id(conn, task_id)
        finally:
            conn.close()

        if task.get("source") == "clickup" and task.get("external_id"):
            clickup_status = "done" if status == "done" else "to do"
            update_clickup_task_status(str(task["external_id"]), clickup_status)
        return updated

    def _task_by_id(self, conn, task_id: int) -> dict[str, Any]:
        task = next((task for task in get_todays_tasks(conn) if task.get("id") == task_id), None)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        return task

    def _date_from_message(self, msg: dict[str, Any]) -> date:
        raw = msg.get("date")
        if not raw:
            return date.today()
        return date.fromisoformat(str(raw))

    def _cleanup(self) -> None:
        self._socket_path.unlink(missing_ok=True)
        DAEMON_PID_PATH.unlink(missing_ok=True)
        try:
            self._selector.close()
        except Exception:
            logger.exception("Failed to close daemon selector during cleanup")
        try:
            self._server_sock.close()
        except Exception:
            logger.exception("Failed to close daemon socket during cleanup")

    @staticmethod
    def _format_time(value: datetime | None) -> str | None:
        return value.isoformat() if value else None
