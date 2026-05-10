from __future__ import annotations
# pyright: reportMissingImports=false

import os
import logging
from datetime import date, datetime
from typing import Any

from selfheal import CalendarError, retry_sync

logger = logging.getLogger(__name__)


@retry_sync(max_attempts=3, base_delay=0.5, max_delay=5.0)
def _get_principal(client):
    try:
        return client.principal()
    except Exception as exc:
        raise CalendarError(f"CalDAV principal lookup failed: {exc}") from exc


@retry_sync(max_attempts=3, base_delay=0.5, max_delay=5.0)
def _get_calendars(principal):
    try:
        return principal.calendars()
    except Exception as exc:
        raise CalendarError(f"CalDAV calendar lookup failed: {exc}") from exc


@retry_sync(max_attempts=3, base_delay=0.5, max_delay=5.0)
def _date_search(calendar, start: datetime, end: datetime):
    try:
        return calendar.date_search(start=start, end=end, expand=True)
    except Exception as exc:
        raise CalendarError(f"CalDAV event search failed: {exc}") from exc


@retry_sync(max_attempts=3, base_delay=0.5, max_delay=5.0)
def _save_event(calendar, ical_str: str):
    try:
        return calendar.save_event(ical_str)
    except Exception as exc:
        raise CalendarError(f"CalDAV event creation failed: {exc}") from exc


def is_caldav_configured() -> bool:
    return bool(
        os.environ.get("SELFHEAL_CALDAV_URL")
        and os.environ.get("SELFHEAL_CALDAV_USERNAME")
        and os.environ.get("SELFHEAL_CALDAV_PASSWORD")
    )


def get_caldav_client():
    if not is_caldav_configured():
        raise CalendarError("CalDAV not configured.")
    import caldav
    dav_client = getattr(caldav, "DAVClient")

    return dav_client(
        url=os.environ.get("SELFHEAL_CALDAV_URL"),
        username=os.environ.get("SELFHEAL_CALDAV_USERNAME"),
        password=os.environ.get("SELFHEAL_CALDAV_PASSWORD"),
    )


def list_caldav_events(start_date: date, end_date: date) -> list[dict[str, Any]]:
    client = get_caldav_client()
    principal = _get_principal(client)
    calendars = _get_calendars(principal)
    
    if not calendars:
        return []

    # Just use the first calendar for now
    calendar = calendars[0]

    # caldav expects datetime objects for date searches
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    events = _date_search(calendar, start_dt, end_dt)
    
    result = []
    for ev in events:
        try:
            vevent = ev.instance.vevent
            summary = str(vevent.summary.value) if hasattr(vevent, "summary") else "Untitled Event"
            
            # Extract start and end times
            if hasattr(vevent, "dtstart"):
                dt_start = vevent.dtstart.value
                all_day = not isinstance(dt_start, datetime)
                start_str = dt_start.isoformat()
            else:
                continue

            if hasattr(vevent, "dtend"):
                end_str = vevent.dtend.value.isoformat()
            else:
                end_str = start_str
                
            location = str(vevent.location.value) if hasattr(vevent, "location") else None
            description = str(vevent.description.value) if hasattr(vevent, "description") else None

            result.append({
                "id": str(vevent.uid.value) if hasattr(vevent, "uid") else "",
                "summary": summary,
                "start": start_str,
                "end": end_str,
                "all_day": all_day,
                "location": location,
                "description": description,
                "provider": "caldav",
            })
        except Exception:
            logger.exception("Skipping malformed CalDAV event")
            continue
            
    # Sort by start time
    result.sort(key=lambda x: x["start"])
    return result


def create_caldav_event(
    summary: str, start: datetime, end: datetime, description: str | None = None
) -> dict[str, Any]:
    client = get_caldav_client()
    principal = _get_principal(client)
    calendars = _get_calendars(principal)
    
    if not calendars:
        raise CalendarError("No CalDAV calendars found")

    calendar = calendars[0]
    
    # Simple iCal event generation
    from uuid import uuid4
    
    tz_str = "Z" if not start.tzinfo else ""
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S") + "Z"
    dtstart = start.strftime("%Y%m%dT%H%M%S") + tz_str
    dtend = end.strftime("%Y%m%dT%H%M%S") + tz_str
    
    ical_data = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SelfHeal//EN",
        "BEGIN:VEVENT",
        f"UID:{uuid4()}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{summary}",
    ]
    
    if description:
        # Simple escaping for description
        desc_escaped = description.replace("\n", "\\n").replace(",", "\\,")
        ical_data.append(f"DESCRIPTION:{desc_escaped}")
        
    ical_data.extend(["END:VEVENT", "END:VCALENDAR"])
    
    ical_str = "\n".join(ical_data)
    
    event = _save_event(calendar, ical_str)
    return {"id": event.url, "summary": summary}
