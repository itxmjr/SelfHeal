from __future__ import annotations

import logging
from datetime import date, datetime
from enum import Enum
from typing import Any

from .google import (
    GOOGLE_CREDENTIALS_PATH as GOOGLE_CREDENTIALS_PATH,
    GOOGLE_TOKEN_PATH as GOOGLE_TOKEN_PATH,
    get_google_auth_url as get_google_auth_url,
    save_google_token as save_google_token,
    load_google_token as load_google_token,
    is_google_authenticated as is_google_authenticated,
    list_google_events,
    create_google_event,
)
from .caldav import (
    is_caldav_configured as is_caldav_configured,
    list_caldav_events,
    create_caldav_event,
)
from .clickup import (
    add_clickup_task_comment as add_clickup_task_comment,
    is_clickup_configured as is_clickup_configured,
    list_clickup_events,
    list_clickup_tasks as list_clickup_tasks,
    update_clickup_task_status as update_clickup_task_status,
)

logger = logging.getLogger(__name__)


class Provider(str, Enum):
    GOOGLE = "google"
    CALDAV = "caldav"
    CLICKUP = "clickup"


def check_auth_status() -> dict[str, bool]:
    """Check the status of calendar authentication."""
    return {
        "google": is_google_authenticated(),
        "google_credentials": GOOGLE_CREDENTIALS_PATH.exists(),
        "google_token": GOOGLE_TOKEN_PATH.exists(),
        "caldav": is_caldav_configured(),
        "clickup": is_clickup_configured(),
    }


def list_calendar_events(provider: Provider, start_date: date, end_date: date) -> list[dict[str, Any]]:
    """List calendar events from the specified provider."""
    if provider == Provider.GOOGLE:
        if not is_google_authenticated():
            raise RuntimeError("Google Calendar is not authenticated.")
        return list_google_events(start_date, end_date)

    elif provider == Provider.CALDAV:
        if not is_caldav_configured():
            raise RuntimeError("CalDAV is not configured in environment variables.")
        return list_caldav_events(start_date, end_date)

    elif provider == Provider.CLICKUP:
        if not is_clickup_configured():
            raise RuntimeError("ClickUp is not configured in environment variables.")
        return list_clickup_events(start_date, end_date)

    raise ValueError(f"Unknown provider: {provider}")


def list_all_events(start_date: date, end_date: date) -> list[dict[str, Any]]:
    """List events from every configured provider, skipping failed providers."""
    status = check_auth_status()
    events: list[dict[str, Any]] = []

    provider_calls = (
        (Provider.CALDAV, "caldav", list_caldav_events),
        (Provider.GOOGLE, "google", list_google_events),
        (Provider.CLICKUP, "clickup", list_clickup_events),
    )
    for provider, status_key, list_events in provider_calls:
        if not status.get(status_key):
            continue
        try:
            events.extend(list_events(start_date, end_date))
        except Exception:
            logger.exception("Skipping %s calendar events after provider failure", provider.value)

    return _dedupe_events(events)


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda item: str(item.get("start", ""))):
        identity = _event_identity(event)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(event)
    return deduped


def _event_identity(event: dict[str, Any]) -> tuple[str, str, str, str]:
    provider = str(event.get("provider") or event.get("source") or "")
    if provider in {Provider.CALDAV.value, Provider.GOOGLE.value}:
        provider = "calendar"
    return (
        provider,
        str(event.get("summary") or ""),
        str(event.get("start") or ""),
        str(event.get("end") or ""),
    )


def create_calendar_event(
    provider: Provider,
    summary: str,
    start: datetime,
    end: datetime,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a new calendar event."""
    if provider == Provider.GOOGLE:
        if not is_google_authenticated():
            raise RuntimeError("Google Calendar is not authenticated.")
        return create_google_event(summary, start, end, description)

    elif provider == Provider.CALDAV:
        if not is_caldav_configured():
            raise RuntimeError("CalDAV is not configured in environment variables.")
        return create_caldav_event(summary, start, end, description)

    raise ValueError(f"Unknown provider: {provider}")
