import os
from datetime import date
from unittest.mock import MagicMock, patch

import httpx

from selfheal import ClickUpError
from selfheal.calendar.providers import Provider, check_auth_status, list_calendar_events
from selfheal.calendar.providers.clickup import (
    add_clickup_task_comment,
    get_clickup_client,
    is_clickup_configured,
    list_clickup_events,
    list_clickup_tasks,
    parse_clickup_task,
    update_clickup_task_status,
)


class FakeResponse:
    def __init__(self, data=None, status_code=200):
        self.data = data or {}
        self.status_code = status_code

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.clickup.com/api/v2/test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("failed", request=request, response=response)


def test_is_clickup_configured_requires_token_and_list_id():
    with patch.dict(os.environ, {}, clear=True):
        assert is_clickup_configured() is False

    with patch.dict(os.environ, {"SELFHEAL_CLICKUP_API_TOKEN": "pk_test"}, clear=True):
        assert is_clickup_configured() is False

    env = {
        "SELFHEAL_CLICKUP_API_TOKEN": "pk_test",
        "SELFHEAL_CLICKUP_LIST_ID": "list_123",
    }
    with patch.dict(os.environ, env, clear=True):
        assert is_clickup_configured() is True


def test_get_clickup_client_sets_authorization_header():
    with patch.dict(os.environ, {"SELFHEAL_CLICKUP_API_TOKEN": "pk_test"}, clear=True):
        with patch("selfheal.calendar.providers.clickup.httpx.Client") as client_class:
            get_clickup_client()

    client_class.assert_called_once()
    assert client_class.call_args.kwargs["headers"]["Authorization"] == "pk_test"


def test_parse_clickup_task_converts_ms_fields():
    task = parse_clickup_task(
        {
            "id": "cu_123",
            "name": "Write report",
            "status": {"status": "in progress", "color": "#ff0000"},
            "due_date": 1770000000000,
            "due_date_time": True,
            "time_estimate": 5400000,
            "description": "Quarterly report",
            "url": "https://app.clickup.com/t/123",
            "custom_fields": [{"name": "Energy", "value": "high"}],
        }
    )

    assert task["source"] == "clickup"
    assert task["external_id"] == "cu_123"
    assert task["name"] == "Write report"
    assert task["status"] == "in progress"
    assert task["due_date"] == "2026-02-02T02:40:00+00:00"
    assert task["due_date_time"] is True
    assert task["due_datetime"] == "2026-02-02T02:40:00+00:00"
    assert task["time_estimate"] == 90
    assert task["description"] == "Quarterly report"
    assert task["external_url"] == "https://app.clickup.com/t/123"
    assert task["custom_fields"] == [{"name": "Energy", "value": "high"}]


def test_parse_clickup_task_preserves_due_date_without_time():
    task = parse_clickup_task({"id": "cu_123", "name": "Write report", "due_date": 1770000000000})

    assert task["due_date"] == "2026-02-02"
    assert task["due_date_time"] is False
    assert task["due_datetime"] == "2026-02-02T02:40:00+00:00"


def test_list_clickup_tasks_parses_response_and_include_closed_param():
    client = MagicMock()
    client.get.return_value = FakeResponse(
        {
            "tasks": [
                {
                    "id": "cu_123",
                    "name": "Write report",
                    "status": {"status": "to do"},
                    "due_date": 1770000000000,
                    "time_estimate": 5400000,
                    "url": "https://app.clickup.com/t/123",
                }
            ]
        }
    )

    with patch("selfheal.calendar.providers.clickup.get_clickup_client", return_value=client):
        tasks = list_clickup_tasks("list_123", include_closed=True)

    client.get.assert_called_once_with(
        "/list/list_123/task",
        params={"include_closed": "true", "page": 0},
    )
    assert tasks[0]["external_id"] == "cu_123"
    assert tasks[0]["time_estimate"] == 90


def test_list_clickup_tasks_fetches_all_pages():
    client = MagicMock()
    first_page = [{"id": f"cu_{idx}", "name": f"Task {idx}"} for idx in range(100)]
    client.get.side_effect = [
        FakeResponse({"tasks": first_page}),
        FakeResponse({"tasks": [{"id": "cu_100", "name": "Task 100"}]}),
    ]

    with patch("selfheal.calendar.providers.clickup.get_clickup_client", return_value=client):
        tasks = list_clickup_tasks("list_123", include_closed=True)

    assert len(tasks) == 101
    assert tasks[-1]["external_id"] == "cu_100"
    assert client.get.call_args_list[0].kwargs["params"] == {"include_closed": "true", "page": 0}
    assert client.get.call_args_list[1].kwargs["params"] == {"include_closed": "true", "page": 1}


def test_list_clickup_tasks_retries_transient_429_and_succeeds():
    client = MagicMock()
    client.get.side_effect = [
        FakeResponse(status_code=429),
        FakeResponse(status_code=429),
        FakeResponse({"tasks": []}),
    ]

    with patch("selfheal.calendar.providers.clickup.get_clickup_client", return_value=client):
        with patch("time.sleep") as sleep:
            assert list_clickup_tasks("list_123") == []

    assert client.get.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]


def test_list_clickup_tasks_raises_after_retry_exhaustion():
    client = MagicMock()
    client.get.return_value = FakeResponse(status_code=429)

    with patch("selfheal.calendar.providers.clickup.get_clickup_client", return_value=client):
        with patch("time.sleep") as sleep:
            try:
                list_clickup_tasks("list_123")
            except ClickUpError as exc:
                assert "status 429" in str(exc)
            else:
                raise AssertionError("list_clickup_tasks did not raise ClickUpError")

    assert client.get.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]


def test_update_clickup_task_status_sends_status_payload():
    client = MagicMock()
    client.put.return_value = FakeResponse({"id": "cu_123", "status": {"status": "done"}})

    with patch("selfheal.calendar.providers.clickup.get_clickup_client", return_value=client):
        result = update_clickup_task_status("cu_123", "done")

    client.put.assert_called_once_with("/task/cu_123", json={"status": "done"})
    assert result["id"] == "cu_123"


def test_add_clickup_task_comment_sends_comment_payload():
    client = MagicMock()
    client.post.return_value = FakeResponse({"id": "comment_123"})

    with patch("selfheal.calendar.providers.clickup.get_clickup_client", return_value=client):
        result = add_clickup_task_comment("cu_123", "Scheduled for 09:00")

    client.post.assert_called_once_with(
        "/task/cu_123/comment",
        json={"comment_text": "Scheduled for 09:00"},
    )
    assert result["id"] == "comment_123"


def test_list_clickup_events_maps_due_tasks_to_calendar_events():
    tasks = [
        {
            "source": "clickup",
            "external_id": "cu_1",
            "name": "All-day task",
            "status": "to do",
            "due_date": "2026-02-27",
            "due_date_time": False,
            "due_datetime": "2026-02-27T08:00:00+00:00",
            "time_estimate": None,
            "description": "A task",
            "external_url": "https://app.clickup.com/t/cu_1",
        },
        {
            "source": "clickup",
            "external_id": "cu_2",
            "name": "Timed task",
            "status": "to do",
            "due_date": "2026-02-28T08:00:00+00:00",
            "due_date_time": True,
            "due_datetime": "2026-02-28T08:00:00+00:00",
            "time_estimate": 30,
            "description": None,
            "external_url": "https://app.clickup.com/t/cu_2",
        },
    ]

    with patch("selfheal.calendar.providers.clickup.list_clickup_tasks", return_value=tasks):
        events = list_clickup_events(date(2026, 2, 27), date(2026, 2, 28))

    assert events == [
        {
            "id": "cu_1",
            "summary": "[ClickUp] All-day task",
            "start": "2026-02-27",
            "end": "2026-02-27",
            "all_day": True,
            "description": "A task",
            "provider": "clickup",
            "source": "clickup",
            "external_id": "cu_1",
            "external_url": "https://app.clickup.com/t/cu_1",
        },
        {
            "id": "cu_2",
            "summary": "[ClickUp] Timed task",
            "start": "2026-02-28T08:00:00+00:00",
            "end": "2026-02-28T08:30:00+00:00",
            "all_day": False,
            "description": None,
            "provider": "clickup",
            "source": "clickup",
            "external_id": "cu_2",
            "external_url": "https://app.clickup.com/t/cu_2",
        },
    ]


def test_provider_clickup_auth_status_and_event_dispatch():
    with patch("selfheal.calendar.providers.is_google_authenticated", return_value=False):
        with patch("selfheal.calendar.providers.is_caldav_configured", return_value=False):
            with patch("selfheal.calendar.providers.is_clickup_configured", return_value=True):
                status = check_auth_status()

    assert status["clickup"] is True
    assert status["google"] is False
    assert status["caldav"] is False

    with patch("selfheal.calendar.providers.is_clickup_configured", return_value=True):
        with patch("selfheal.calendar.providers.list_clickup_events", return_value=[{"id": "cu_1"}]) as events:
            assert list_calendar_events(Provider.CLICKUP, date(2026, 2, 27), date(2026, 2, 27)) == [{"id": "cu_1"}]

    events.assert_called_once_with(date(2026, 2, 27), date(2026, 2, 27))
