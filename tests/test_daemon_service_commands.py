from __future__ import annotations

import threading
import time
from datetime import date

from selfheal.daemon import client
from selfheal.daemon import service
from selfheal.daemon.service import DaemonServer
from selfheal.db import get_todays_tasks, upsert_task


class ConnectionProxy:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass


def test_daemon_routes_add_task_and_get_tasks(monkeypatch, temp_db):
    monkeypatch.setattr(service, "get_connection", lambda: ConnectionProxy(temp_db))
    server = DaemonServer()

    response = server._process_command({"cmd": "add_task", "name": "Read", "priority": "high", "estimated_minutes": 25})

    assert response["ok"] is True
    task_id = response["data"]["task_id"]
    task = next(task for task in get_todays_tasks(temp_db) if task["id"] == task_id)
    assert task["name"] == "Read"
    assert task["priority"] == "high"
    assert task["estimated_minutes"] == 25

    tasks_response = server._process_command({"cmd": "get_tasks"})
    assert tasks_response["ok"] is True
    assert tasks_response["data"][0]["id"] == task_id


def test_daemon_generate_schedule_command_updates_status(monkeypatch):
    server = DaemonServer()
    calls = []

    def fake_generate(target_date):
        calls.append(target_date)
        return [{"name": "Scheduled"}], True

    monkeypatch.setattr(service, "generate_schedule_task", fake_generate)

    response = server._process_command({"cmd": "generate_schedule", "date": "2026-05-04"})

    assert response == {"ok": True, "data": [{"name": "Scheduled"}]}
    assert calls == [date(2026, 5, 4)]
    assert server._get_status()["last_schedule"] == "2026-05-04"


def test_daemon_toggle_task_updates_clickup_status(monkeypatch, temp_db):
    task_id = upsert_task(temp_db, name="ClickUp", source="clickup", external_id="cu_123")
    monkeypatch.setattr(service, "get_connection", lambda: ConnectionProxy(temp_db))
    status_calls = []
    monkeypatch.setattr(service, "update_clickup_task_status", lambda external_id, status: status_calls.append((external_id, status)))
    server = DaemonServer()

    response = server._process_command({"cmd": "toggle_task", "task_id": task_id})

    assert response["ok"] is True
    assert response["data"]["status"] == "done"
    assert status_calls == [("cu_123", "done")]


def test_daemon_start_loop_responds_to_live_ping(monkeypatch, tmp_path):
    socket_path = tmp_path / "daemon.sock"
    pid_path = tmp_path / "daemon.pid"
    monkeypatch.setattr(service, "DAEMON_SOCKET_PATH", socket_path)
    monkeypatch.setattr(service, "DAEMON_PID_PATH", pid_path)
    monkeypatch.setattr(client, "DAEMON_SOCKET_PATH", socket_path)
    monkeypatch.setattr(DaemonServer, "_run_background_tasks", lambda self, force=False: None)

    server = DaemonServer()
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 3
        while not socket_path.exists() and time.time() < deadline:
            time.sleep(0.01)

        response = client.daemon_send_cmd("ping", timeout=1.0)

        assert response["ok"] is True
        assert "pid" in response["data"]
    finally:
        server.stop()
        thread.join(timeout=2)
