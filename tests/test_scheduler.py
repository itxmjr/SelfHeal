from __future__ import annotations

from datetime import date

from selfheal.db import get_todays_tasks, mark_task_done, upsert_task
from selfheal.engine import scheduler


def _life_model() -> dict:
    return {
        "sleep": {"wake": "07:00", "bed": "12:00"},
        "energy": {"peak": "09:00-10:00", "low": "10:00-11:00"},
        "commitments": [],
        "goals": [],
    }


def _candidate(name: str, priority: str = "medium", minutes: int = 30, **extra) -> dict:
    return {
        "name": name,
        "priority": priority,
        "estimated_minutes": minutes,
        **extra,
    }


class _ConnectionProxy:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self) -> None:
        pass


def test_generate_schedule_returns_empty_for_empty_candidates():
    result, _ = scheduler.generate_schedule(
        today=date.today(),
        life_model=_life_model(),
        task_candidates=[],
        calendar_events=[],
        use_ai=False,
    )

    assert result == []


def test_generate_schedule_respects_calendar_blockers():
    today = date.today()
    blocked_start = f"{today.isoformat()}T09:00:00"
    blocked_end = f"{today.isoformat()}T10:00:00"

    result, _ = scheduler.generate_schedule(
        today=today,
        life_model=_life_model(),
        task_candidates=[_candidate("Critical", "critical")],
        calendar_events=[{"summary": "Meeting", "start": blocked_start, "end": blocked_end}],
        use_ai=False,
    )

    assert result[0]["start_time"] != "09:00"


def test_generate_schedule_sorts_priority_into_peak_before_low():
    result, _ = scheduler.generate_schedule(
        today=date.today(),
        life_model=_life_model(),
        task_candidates=[_candidate("Low", "low"), _candidate("High", "high")],
        calendar_events=[],
        use_ai=False,
    )

    high = next(item for item in result if item["name"] == "High")
    low = next(item for item in result if item["name"] == "Low")
    assert high["start_time"] == "09:00"
    assert low["start_time"] == "10:00"


def test_generate_schedule_returns_empty_without_life_model():
    result, _ = scheduler.generate_schedule(
        today=date.today(),
        life_model=None,
        task_candidates=[_candidate("Task")],
        calendar_events=[],
        use_ai=False,
    )

    assert result == []


def test_refine_with_ai_returns_err_for_invalid_response(monkeypatch):
    class LLM:
        def chat(self, messages):
            class Response:
                content = "not json"

            return Response()

    monkeypatch.setattr(scheduler, "get_llm_with_fallback", lambda: LLM())

    result = scheduler._refine_with_ai(_life_model(), [], date.today())

    assert result.is_err()
    assert "JSON" in result.error


def test_schedule_item_to_db_preserves_external_identity(temp_db):
    target_date = date.today()
    item = {
        "name": "ClickUp task",
        "priority": "high",
        "estimated_minutes": 45,
        "start_time": "09:00",
        "end_time": "10:00",
        "source": "clickup",
        "external_id": "cu_123",
        "external_url": "https://app.clickup.com/t/cu_123",
    }

    task_id = scheduler.schedule_item_to_db(item, target_date, temp_db)
    temp_db.commit()

    task = next(task for task in get_todays_tasks(temp_db, target_date.isoformat()) if task["id"] == task_id)
    assert task["source"] == "clickup"
    assert task["external_id"] == "cu_123"
    assert task["external_url"] == "https://app.clickup.com/t/cu_123"
    assert task["scheduled_start"] == "09:00"


def test_generate_and_persist_schedule_does_not_duplicate_life_model_goals(monkeypatch, temp_db):
    target_date = date.today()
    life_model = {
        **_life_model(),
        "goals": [
            {
                "name": "Read",
                "priority": "high",
                "frequency": "daily",
                "estimated_minutes": 30,
            }
        ],
    }

    monkeypatch.setattr(scheduler, "get_connection", lambda: _ConnectionProxy(temp_db))

    first_schedule, _ = scheduler.generate_and_persist_schedule(
        today=target_date,
        life_model=life_model,
        calendar_events=[],
        use_ai=False,
    )
    second_schedule, _ = scheduler.generate_and_persist_schedule(
        today=target_date,
        life_model=life_model,
        calendar_events=[],
        use_ai=False,
    )

    rows = temp_db.execute(
        "SELECT id, name, source, external_id FROM tasks WHERE name = ?",
        ("Read",),
    ).fetchall()
    logs = temp_db.execute(
        "SELECT date, task_id, scheduled_start, scheduled_end FROM daily_logs WHERE date = ?",
        (target_date.isoformat(),),
    ).fetchall()

    assert len(rows) == 1
    assert [item["name"] for item in first_schedule] == ["Read"]
    assert [item["name"] for item in second_schedule] == ["Read"]
    assert rows[0]["source"] == "life_model"
    assert rows[0]["external_id"] == "goal:read:daily:anytime"
    assert len(logs) == 1
    assert logs[0]["task_id"] == rows[0]["id"]
    assert logs[0]["scheduled_start"] == "09:00"


def test_regenerate_schedule_reschedules_pending_future_tasks(monkeypatch, temp_db):
    target_date = date.today()
    past_task_id = upsert_task(temp_db, name="Past", priority="high", estimated_minutes=30)
    future_task_id = upsert_task(temp_db, name="Future", priority="high", estimated_minutes=30)
    mark_task_done(temp_db, past_task_id, target_date.isoformat())
    temp_db.execute(
        "INSERT INTO daily_logs (date, task_id, status, scheduled_start, scheduled_end) "
        "VALUES (?, ?, 'pending', '10:00', '11:00')",
        (target_date.isoformat(), future_task_id),
    )
    temp_db.commit()

    monkeypatch.setattr(scheduler, "load_life_model", _life_model)
    monkeypatch.setattr(scheduler, "get_connection", lambda: _ConnectionProxy(temp_db))

    result, _ = scheduler.regenerate_schedule(target_date, calendar_events=[], current_hour=9)

    assert [item["name"] for item in result] == ["Future"]
    tasks = get_todays_tasks(temp_db, target_date.isoformat())
    future_task = next(task for task in tasks if task["id"] == future_task_id)
    past_task = next(task for task in tasks if task["id"] == past_task_id)
    assert future_task["scheduled_start"] == "09:00"
    assert past_task["status"] == "done"


def test_generate_schedule_task_adds_clickup_scheduled_comment(monkeypatch):
    from selfheal.daemon.tasks import schedule as schedule_task

    comments = []
    monkeypatch.setattr(schedule_task, "load_life_model", lambda: _life_model())
    monkeypatch.setattr(schedule_task, "collect_calendar_events", lambda target_date: [])
    monkeypatch.setattr(
        schedule_task,
        "generate_and_persist_schedule",
        lambda **kwargs: ([
            {
                "name": "ClickUp Task",
                "source": "clickup",
                "external_id": "cu_123",
                "start_time": "09:00",
                "end_time": "10:00",
            }
        ], True),
    )
    monkeypatch.setattr(schedule_task, "add_clickup_task_comment", lambda task_id, comment: comments.append((task_id, comment)))
    monkeypatch.setattr(schedule_task, "update_clickup_task_dates", lambda *args: {})

    result, _ = schedule_task.generate_schedule_task(date(2026, 5, 4))

    assert result[0]["external_id"] == "cu_123"
    assert comments == [("cu_123", "Scheduled by SelfHeal: 09:00-10:00")]
