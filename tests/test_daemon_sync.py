from __future__ import annotations

from selfheal.daemon.tasks import sync


class ConnectionProxy:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass


def test_sync_clickup_upserts_tasks_and_writes_sync_log(monkeypatch, temp_db):
    monkeypatch.setattr(sync, "is_clickup_configured", lambda: True)
    monkeypatch.setattr(sync, "get_connection", lambda: ConnectionProxy(temp_db))
    monkeypatch.setattr(
        sync,
        "list_clickup_tasks",
        lambda: [
            {
                "external_id": "cu_123",
                "name": "ClickUp Task",
                "time_estimate": 45,
                "external_url": "https://app.clickup.com/t/cu_123",
                "status": "to do",
                "raw": {"date_updated": "1770000000000"},
            }
        ],
    )

    result = sync.sync_clickup_task()

    assert result["configured"] is True
    assert result["count"] == 1
    task = temp_db.execute("SELECT * FROM tasks WHERE source='clickup' AND external_id='cu_123'").fetchone()
    assert task["name"] == "ClickUp Task"
    assert task["estimated_minutes"] == 45
    assert task["external_url"] == "https://app.clickup.com/t/cu_123"
    assert task["sync_hash"]
    log = temp_db.execute("SELECT * FROM sync_log WHERE source='clickup'").fetchone()
    assert log["action"] == "upsert_task"
    assert log["status"] == "ok"


def test_sync_clickup_skips_when_not_configured(monkeypatch):
    monkeypatch.setattr(sync, "is_clickup_configured", lambda: False)

    assert sync.sync_clickup_task() == {"configured": False, "count": 0, "task_ids": []}


def test_sync_calendar_task_returns_events(monkeypatch):
    events = [{"summary": "Meeting"}]
    monkeypatch.setattr(sync, "list_all_events", lambda start, end: events)

    result = sync.sync_calendar_task()

    assert result["provider"] == "all"
    assert result["count"] == 1
    assert result["events"] == events
