from __future__ import annotations

import asyncio
from typing import Any

import pytest
from textual.widgets import TabbedContent

from selfheal.db import get_todays_tasks, upsert_task
from selfheal.tui import app as tui_app
from selfheal.tui.app import SelfHealApp
from selfheal.tui.screens.modals import AddTaskModal, ConfigModal, HelpModal, VisionImportModal
from selfheal.tui.widgets.task_table import TaskTable


class FakeTaskTable:
    def __init__(self, task_id):
        self._task_id = task_id

    def selected_task_id(self):
        return self._task_id


class ConnectionProxy:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass


def make_app() -> Any:
    app: Any = object.__new__(SelfHealApp)
    app._daemon_status = {}
    app._calendar_events = []
    app.notifications = []
    app.notify = lambda message, **kwargs: app.notifications.append((message, kwargs))
    app.refresh_count = 0
    app.refresh_all = lambda: setattr(app, "refresh_count", app.refresh_count + 1)
    return app


def test_tui_regenerate_uses_daemon_when_connected(monkeypatch):
    app = make_app()
    app._daemon_connected = True
    calls = []
    monkeypatch.setattr(tui_app, "daemon_generate_schedule", lambda target_date: calls.append(target_date) or [{"name": "Task"}])
    monkeypatch.setattr(tui_app, "daemon_get_status", lambda: {"pid": 1, "last_schedule": "today"})

    SelfHealApp.action_regenerate(app)

    assert calls
    assert app.refresh_count == 1
    assert "Generated 1 schedule block(s) via daemon" in app.notifications[-1][0]


def test_tui_regenerate_offline_does_not_call_scheduler(monkeypatch):
    app = make_app()
    app._daemon_connected = False
    monkeypatch.setattr(tui_app, "daemon_generate_schedule", lambda target_date: (_ for _ in ()).throw(AssertionError("should not call daemon")))

    SelfHealApp.action_regenerate(app)

    assert app.refresh_count == 1
    assert "Start the daemon" in app.notifications[0][0]


def test_tui_toggle_connected_uses_daemon(monkeypatch):
    app = make_app()
    app._daemon_connected = True
    app._current_task_table = lambda: FakeTaskTable(7)
    app._load_tasks = lambda: [{"id": 7, "name": "Read", "status": "pending", "is_blocked": False}]
    calls = []
    monkeypatch.setattr(tui_app, "daemon_toggle_task", lambda task_id: calls.append(task_id) or {"id": task_id, "status": "done"})

    SelfHealApp.action_toggle_selected(app)

    assert calls == [7]
    assert app.refresh_count == 1
    assert "Marked done" in app.notifications[-1][0]


def test_tui_toggle_offline_warns_without_local_db_mutation(monkeypatch, temp_db):
    task_id = upsert_task(temp_db, name="Offline")
    app = make_app()
    app._daemon_connected = False
    app._current_task_table = lambda: FakeTaskTable(task_id)
    app._load_tasks = lambda: get_todays_tasks(temp_db)
    monkeypatch.setattr(tui_app, "get_connection", lambda: ConnectionProxy(temp_db))

    SelfHealApp.action_toggle_selected(app)

    task = next(task for task in get_todays_tasks(temp_db) if task["id"] == task_id)
    assert task["status"] == "pending"
    assert app.refresh_count == 1
    assert "start daemon to toggle tasks" in app.notifications[-1][0]


def test_sync_calendar_connected_uses_daemon_without_provider_calls(monkeypatch):
    app = make_app()
    app._daemon_connected = True
    daemon_events = [{"summary": "Daemon Meeting", "start": "2026-05-04T09:00:00", "end": "2026-05-04T10:00:00"}]
    monkeypatch.setattr(tui_app, "daemon_sync_all", lambda: {"calendar": {"provider": "caldav", "count": 1, "events": daemon_events}})
    monkeypatch.setattr(tui_app, "daemon_get_status", lambda: {"pid": 1, "last_calendar_sync": "now"})
    monkeypatch.setattr(tui_app, "check_auth_status", lambda: (_ for _ in ()).throw(AssertionError("provider status should not be called")))
    monkeypatch.setattr(tui_app, "list_calendar_events", lambda *args: (_ for _ in ()).throw(AssertionError("provider events should not be called")))

    SelfHealApp._sync_calendar(app)

    assert app._daemon_connected is True
    assert app._calendar_events == daemon_events
    assert app._daemon_status == {"pid": 1, "last_calendar_sync": "now"}


def test_sync_calendar_daemon_failure_falls_back_to_local_provider(monkeypatch):
    app = make_app()
    app._daemon_connected = True
    local_events = [{"summary": "Local Meeting", "start": "2026-05-04T11:00:00", "end": "2026-05-04T12:00:00"}]
    monkeypatch.setattr(tui_app, "daemon_sync_all", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(tui_app, "daemon_get_status", lambda: (_ for _ in ()).throw(AssertionError("status should not be fetched after failed sync")))
    monkeypatch.setattr(tui_app, "check_auth_status", lambda: {"caldav": True, "google": False})
    provider_calls = []

    def fake_events(provider, start, end):
        provider_calls.append((provider, start, end))
        return local_events

    monkeypatch.setattr(tui_app, "list_calendar_events", fake_events)

    SelfHealApp._sync_calendar(app)

    assert app._daemon_connected is False
    assert app._calendar_events == local_events
    assert len(provider_calls) == 1
    assert "Daemon calendar sync failed" in app.notifications[0][0]


def test_sync_calendar_offline_uses_local_provider(monkeypatch):
    app = make_app()
    app._daemon_connected = False
    local_events = [{"summary": "Offline Meeting", "start": "2026-05-04T13:00:00", "end": "2026-05-04T14:00:00"}]
    monkeypatch.setattr(tui_app, "daemon_sync_all", lambda: (_ for _ in ()).throw(AssertionError("daemon should not be called")))
    monkeypatch.setattr(tui_app, "check_auth_status", lambda: {"caldav": False, "google": True})
    provider_calls = []

    def fake_events(provider, start, end):
        provider_calls.append((provider, start, end))
        return local_events

    monkeypatch.setattr(tui_app, "list_calendar_events", fake_events)

    SelfHealApp._sync_calendar(app)

    assert app._calendar_events == local_events
    assert len(provider_calls) == 1




def test_tui_action_prev_next_tab():
    app = make_app()
    class FakeTabs:
        active = "tab-dashboard"
    fake_tabs = FakeTabs()
    app.query_one = lambda cls: fake_tabs if cls == TabbedContent else None
    
    SelfHealApp.action_next_tab(app)
    assert fake_tabs.active == "tab-tasks"
    
    SelfHealApp.action_next_tab(app)
    assert fake_tabs.active == "tab-schedule"
    
    SelfHealApp.action_prev_tab(app)
    assert fake_tabs.active == "tab-tasks"
    
    SelfHealApp.action_prev_tab(app)
    assert fake_tabs.active == "tab-dashboard"
    
    SelfHealApp.action_prev_tab(app)
    assert fake_tabs.active == "tab-history"

def test_tui_action_open_link(monkeypatch):
    app = make_app()
    app._current_task_table = lambda: FakeTaskTable(2)
    app._load_tasks = lambda: [
        {"id": 1, "name": "Local Task"},
        {"id": 2, "name": "ClickUp Task", "external_url": "https://app.clickup.com/t/123"}
    ]
    
    opened_urls = []
    monkeypatch.setattr(tui_app.webbrowser, "open", lambda url: opened_urls.append(url))
    
    SelfHealApp.action_open_link(app)
    
    assert len(opened_urls) == 1
    assert opened_urls[0] == "https://app.clickup.com/t/123"
    assert "Opened https://app.clickup.com/t/123" in app.notifications[-1][0]

def test_tui_sync_buttons(monkeypatch):
    app = make_app()
    app._daemon_connected = True
    
    calls = []
    monkeypatch.setattr(tui_app, "daemon_sync_calendar", lambda: calls.append("calendar"))
    monkeypatch.setattr(tui_app, "daemon_sync_clickup", lambda: calls.append("clickup"))
    monkeypatch.setattr(tui_app, "daemon_sync_obsidian", lambda: calls.append("obsidian"))
    
    class FakeEvent:
        class FakeButton:
            def __init__(self, id):
                self.id = id
        def __init__(self, id):
            self.button = self.FakeButton(id)
            
    SelfHealApp.on_button_pressed(app, FakeEvent("btn-sync-calendar"))
    assert "calendar" in calls
    assert "Synced Calendar via daemon" in app.notifications[-1][0]
    
    SelfHealApp.on_button_pressed(app, FakeEvent("btn-sync-clickup"))
    assert "clickup" in calls
    assert "Synced ClickUp via daemon" in app.notifications[-1][0]
    
    SelfHealApp.on_button_pressed(app, FakeEvent("btn-sync-obsidian"))
    assert "obsidian" in calls
    assert "Synced Obsidian via daemon" in app.notifications[-1][0]

def test_tui_action_add_task_connected(monkeypatch):
    app = make_app()
    app._daemon_connected = True
    
    calls = []
    monkeypatch.setattr(tui_app, "daemon_add_task", lambda **kwargs: calls.append(kwargs))
    
    def fake_push_screen(screen, callback=None):
        if callback:
            callback({
                "name": "New Task",
                "emoji": "🚀",
                "priority": "high",
                "estimated_minutes": 45,
                "schedule": "daily"
            })
    app.push_screen = fake_push_screen
    
    SelfHealApp.action_add_task(app)
    
    assert len(calls) == 1
    assert calls[0]["name"] == "New Task"
    assert calls[0]["priority"] == "high"
    assert app.refresh_count == 1
    assert "Added task via daemon" in app.notifications[-1][0]

def test_tui_action_add_task_offline_warns_without_local_db_mutation(monkeypatch, temp_db):
    app = make_app()
    app._daemon_connected = False
    
    monkeypatch.setattr(tui_app, "get_connection", lambda: ConnectionProxy(temp_db))
    
    def fake_push_screen(screen, callback=None):
        if callback:
            callback({
                "name": "Local Task",
                "emoji": "📝",
                "priority": "low",
                "estimated_minutes": 15,
                "schedule": "weekly"
            })
    app.push_screen = fake_push_screen
    
    SelfHealApp.action_add_task(app)
    
    tasks = get_todays_tasks(temp_db)
    assert not any(t["name"] == "Local Task" for t in tasks)
    assert app.refresh_count == 1
    assert "start daemon to add tasks" in app.notifications[-1][0]


def test_tui_vision_import_offline_warns_without_worker():
    app = make_app()
    app._daemon_connected = False
    app.run_worker = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("worker should not run"))

    SelfHealApp.action_vision_import(app)

    assert "start daemon to import vision tasks" in app.notifications[-1][0]

def test_tui_vision_import_connected(monkeypatch, tmp_path):
    app = make_app()
    app._daemon_connected = True
    
    img_path = tmp_path / "test.jpg"
    img_path.write_bytes(b"fake image data")
    
    class FakeLLMClient:
        def vision(self, prompt, img_b64):
            class Resp:
                content = '[{"name": "Vision Task", "emoji": "👁️", "priority": "high", "estimated_minutes": 20}]'
            return Resp()
            
    monkeypatch.setattr(tui_app, "get_llm_client", lambda: FakeLLMClient())
    
    calls = []
    monkeypatch.setattr(tui_app, "daemon_add_task", lambda **kwargs: calls.append(kwargs))
    
    app.call_from_thread = lambda func, *args, **kwargs: func(*args, **kwargs)
    
    asyncio.run(SelfHealApp._do_vision_import(app, img_path))
    
    assert len(calls) == 1
    assert calls[0]["name"] == "Vision Task"
    assert app.refresh_count == 1
    assert "Successfully imported 1 tasks via daemon" in app.notifications[-1][0]

def test_tui_task_table_clickup_rendering():
    table = TaskTable()
    table.add_columns = lambda *args: None
    table.clear = lambda columns: None
    
    rows = []
    table.add_row = lambda *args, **kwargs: rows.append(args)
    
    tasks = [
        {
            "id": 1,
            "name": "Local Task",
            "source": "local"
        },
        {
            "id": 2,
            "name": "ClickUp Task",
            "source": "clickup",
            "external_url": "https://app.clickup.com/t/123",
            "due_date": "2026-05-05"
        }
    ]
    
    table.set_tasks(tasks)
    
    assert len(rows) == 2
    assert "[dim]local[/]" in rows[0][8]
    assert "[magenta]ClickUp[/]" in rows[1][8]
    assert "🔗" in rows[1][8]
    assert "Due: 2026-05-05" in rows[1][8]

def test_tui_modals_exist():
    assert AddTaskModal() is not None
    assert VisionImportModal() is not None
    assert ConfigModal() is not None
    assert HelpModal() is not None


def test_tui_action_show_config_saves_path_value(monkeypatch):
    app = make_app()
    saved = []
    monkeypatch.setattr(tui_app, "set_config_path", lambda path, value: saved.append((path, value)) or value)

    def fake_push_screen(screen, callback=None):
        if callback:
            callback({"path": "llm.provider", "value": "ollama"})

    app.push_screen = fake_push_screen

    SelfHealApp.action_show_config(app)

    assert saved == [("llm.provider", "ollama")]
    assert "Set llm.provider = ollama" in app.notifications[-1][0]
