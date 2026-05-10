from __future__ import annotations

import logging
from datetime import date

import selfheal.calendar.providers as providers
from selfheal.calendar import list_all_events
from selfheal.daemon.tasks import schedule, sync


def _status(caldav: bool = False, google: bool = False, clickup: bool = False) -> dict[str, bool]:
    return {
        "caldav": caldav,
        "google": google,
        "clickup": clickup,
        "google_credentials": google,
        "google_token": google,
    }


def _event(summary: str, start: str, end: str, provider: str) -> dict[str, object]:
    return {
        "id": f"{provider}-{summary}",
        "summary": summary,
        "start": start,
        "end": end,
        "all_day": False,
        "provider": provider,
    }


def test_list_all_events_with_caldav_configured_only(monkeypatch):
    caldav_event = _event("CalDAV", "2026-05-04T09:00:00", "2026-05-04T10:00:00", "caldav")
    monkeypatch.setattr(providers, "check_auth_status", lambda: _status(caldav=True))
    monkeypatch.setattr(providers, "list_caldav_events", lambda start, end: [caldav_event])
    monkeypatch.setattr(providers, "list_google_events", lambda start, end: (_ for _ in ()).throw(AssertionError("google skipped")))
    monkeypatch.setattr(providers, "list_clickup_events", lambda start, end: (_ for _ in ()).throw(AssertionError("clickup skipped")))

    assert list_all_events(date(2026, 5, 4), date(2026, 5, 4)) == [caldav_event]


def test_list_all_events_with_google_configured_only(monkeypatch):
    google_event = _event("Google", "2026-05-04T11:00:00", "2026-05-04T12:00:00", "google")
    monkeypatch.setattr(providers, "check_auth_status", lambda: _status(google=True))
    monkeypatch.setattr(providers, "list_caldav_events", lambda start, end: (_ for _ in ()).throw(AssertionError("caldav skipped")))
    monkeypatch.setattr(providers, "list_google_events", lambda start, end: [google_event])
    monkeypatch.setattr(providers, "list_clickup_events", lambda start, end: (_ for _ in ()).throw(AssertionError("clickup skipped")))

    assert list_all_events(date(2026, 5, 4), date(2026, 5, 4)) == [google_event]


def test_list_all_events_aggregates_caldav_google_and_clickup(monkeypatch):
    caldav_event = _event("CalDAV", "2026-05-04T09:00:00", "2026-05-04T10:00:00", "caldav")
    google_event = _event("Google", "2026-05-04T11:00:00", "2026-05-04T12:00:00", "google")
    clickup_event = {
        "id": "cu_1",
        "summary": "[ClickUp] Ship release",
        "start": "2026-05-04",
        "end": "2026-05-04",
        "all_day": True,
        "provider": "clickup",
        "source": "clickup",
        "external_id": "cu_1",
    }
    monkeypatch.setattr(providers, "check_auth_status", lambda: _status(caldav=True, google=True, clickup=True))
    monkeypatch.setattr(providers, "list_caldav_events", lambda start, end: [caldav_event])
    monkeypatch.setattr(providers, "list_google_events", lambda start, end: [google_event])
    monkeypatch.setattr(providers, "list_clickup_events", lambda start, end: [clickup_event])

    events = list_all_events(date(2026, 5, 4), date(2026, 5, 4))

    assert [event["summary"] for event in events] == ["[ClickUp] Ship release", "CalDAV", "Google"]


def test_list_all_events_maps_clickup_due_dates_through_aggregation(monkeypatch):
    tasks = [
        {
            "source": "clickup",
            "external_id": "cu_1",
            "name": "All-day task",
            "due_date": "2026-05-04",
            "due_date_time": False,
            "due_datetime": "2026-05-04T08:00:00+00:00",
            "time_estimate": None,
            "description": "A task",
            "external_url": "https://app.clickup.com/t/cu_1",
        }
    ]
    monkeypatch.setattr(providers, "check_auth_status", lambda: _status(clickup=True))
    monkeypatch.setattr("selfheal.calendar.providers.clickup.list_clickup_tasks", lambda: tasks)

    assert list_all_events(date(2026, 5, 4), date(2026, 5, 4)) == [
        {
            "id": "cu_1",
            "summary": "[ClickUp] All-day task",
            "start": "2026-05-04",
            "end": "2026-05-04",
            "all_day": True,
            "description": "A task",
            "provider": "clickup",
            "source": "clickup",
            "external_id": "cu_1",
            "external_url": "https://app.clickup.com/t/cu_1",
        }
    ]


def test_list_all_events_skips_unconfigured_providers(monkeypatch):
    monkeypatch.setattr(providers, "check_auth_status", lambda: _status())
    monkeypatch.setattr(providers, "list_caldav_events", lambda start, end: (_ for _ in ()).throw(AssertionError("caldav skipped")))
    monkeypatch.setattr(providers, "list_google_events", lambda start, end: (_ for _ in ()).throw(AssertionError("google skipped")))
    monkeypatch.setattr(providers, "list_clickup_events", lambda start, end: (_ for _ in ()).throw(AssertionError("clickup skipped")))

    assert list_all_events(date(2026, 5, 4), date(2026, 5, 4)) == []


def test_list_all_events_skips_failed_provider(monkeypatch, caplog):
    google_event = _event("Google", "2026-05-04T11:00:00", "2026-05-04T12:00:00", "google")
    monkeypatch.setattr(providers, "check_auth_status", lambda: _status(caldav=True, google=True))
    monkeypatch.setattr(providers, "list_caldav_events", lambda start, end: (_ for _ in ()).throw(RuntimeError("caldav down")))
    monkeypatch.setattr(providers, "list_google_events", lambda start, end: [google_event])

    with caplog.at_level(logging.ERROR, logger="selfheal.calendar.providers"):
        events = list_all_events(date(2026, 5, 4), date(2026, 5, 4))

    assert events == [google_event]
    assert "Skipping caldav calendar events after provider failure" in caplog.text


def test_list_all_events_dedupes_calendar_provider_duplicates(monkeypatch):
    caldav_event = _event("Standup", "2026-05-04T09:00:00", "2026-05-04T10:00:00", "caldav")
    google_duplicate = _event("Standup", "2026-05-04T09:00:00", "2026-05-04T10:00:00", "google")
    clickup_same_time = {
        "summary": "Standup",
        "start": "2026-05-04T09:00:00",
        "end": "2026-05-04T10:00:00",
        "provider": "clickup",
        "source": "clickup",
    }
    monkeypatch.setattr(providers, "check_auth_status", lambda: _status(caldav=True, google=True, clickup=True))
    monkeypatch.setattr(providers, "list_caldav_events", lambda start, end: [caldav_event, caldav_event.copy()])
    monkeypatch.setattr(providers, "list_google_events", lambda start, end: [google_duplicate])
    monkeypatch.setattr(providers, "list_clickup_events", lambda start, end: [clickup_same_time])

    events = list_all_events(date(2026, 5, 4), date(2026, 5, 4))

    assert events == [caldav_event, clickup_same_time]


def test_daemon_schedule_collects_all_calendar_events(monkeypatch):
    events = [_event("Calendar", "2026-05-04T09:00:00", "2026-05-04T10:00:00", "google")]
    monkeypatch.setattr(schedule, "list_all_events", lambda start, end: events)

    assert schedule.collect_calendar_events(date(2026, 5, 4)) == events


def test_daemon_sync_calendar_task_returns_aggregated_events(monkeypatch):
    events = [_event("Calendar", "2026-05-04T09:00:00", "2026-05-04T10:00:00", "google")]
    monkeypatch.setattr(sync, "list_all_events", lambda start, end: events)

    result = sync.sync_calendar_task()

    assert result == {"provider": "all", "count": 1, "events": events}
