from __future__ import annotations
# pyright: reportMissingImports=false

import json
from datetime import date, datetime, timedelta
from typing import Any

from ...config import CONFIG_DIR
from selfheal import CalendarError, retry_sync

GOOGLE_CREDENTIALS_PATH = CONFIG_DIR / "google_credentials.json"
GOOGLE_TOKEN_PATH = CONFIG_DIR / "google_token.json"
GOOGLE_CALENDAR_SCOPES: list[str] = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


@retry_sync(max_attempts=3, base_delay=0.5, max_delay=5.0)
def _refresh_google_credentials(creds) -> None:
    from google.auth.transport.requests import Request

    try:
        creds.refresh(Request())
    except Exception as exc:
        raise CalendarError(f"Google credential refresh failed: {exc}") from exc


@retry_sync(max_attempts=3, base_delay=0.5, max_delay=5.0)
def _execute_google_request(request) -> dict[str, Any]:
    try:
        return request.execute()
    except Exception as exc:
        raise CalendarError(f"Google Calendar request failed: {exc}") from exc


def get_google_auth_url() -> str:
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(
        str(GOOGLE_CREDENTIALS_PATH), scopes=GOOGLE_CALENDAR_SCOPES
    )
    return flow.authorization_url(access_type="offline")[0]


def save_google_token(token: dict[str, Any]) -> None:
    GOOGLE_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GOOGLE_TOKEN_PATH, "w") as f:
        json.dump(token, f)


def load_google_token() -> dict[str, Any] | None:
    if not GOOGLE_TOKEN_PATH.exists():
        return None
    with open(GOOGLE_TOKEN_PATH) as f:
        return json.load(f)


def is_google_authenticated() -> bool:
    if not GOOGLE_TOKEN_PATH.exists():
        return False
    token = load_google_token()
    if not token:
        return False
    expiry = token.get("expiry")
    if expiry:
        expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if datetime.now().astimezone() >= expiry_dt - timedelta(minutes=5):
            return False
    return True


def get_google_calendar_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = None

    if GOOGLE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_info(
            load_google_token(), scopes=GOOGLE_CALENDAR_SCOPES
        )
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            _refresh_google_credentials(creds)
            save_google_token(json.loads(creds.to_json()))
        else:
            raise CalendarError("Google Calendar not authenticated.")

    return build("calendar", "v3", credentials=creds)


def list_google_events(start_date: date, end_date: date) -> list[dict[str, Any]]:
    service = get_google_calendar_service()

    time_min = datetime.combine(start_date, datetime.min.time()).isoformat() + "Z"
    time_max = datetime.combine(end_date, datetime.max.time()).isoformat() + "Z"

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        
    )
    events_result = _execute_google_request(events_result)
    items = events_result.get("items", [])
    
    result = []
    for item in items:
        start = item["start"].get("dateTime", item["start"].get("date"))
        end = item["end"].get("dateTime", item["end"].get("date"))
        all_day = "date" in item["start"]
        
        result.append({
            "id": item["id"],
            "summary": item.get("summary", "Untitled Event"),
            "start": start,
            "end": end,
            "all_day": all_day,
            "location": item.get("location"),
            "description": item.get("description"),
            "provider": "google",
        })
    return result


def create_google_event(
    summary: str, start: datetime, end: datetime, description: str | None = None
) -> dict[str, Any]:
    service = get_google_calendar_service()
    event = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": str(start.astimezone().tzinfo) if start.tzinfo else "UTC",
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": str(end.astimezone().tzinfo) if end.tzinfo else "UTC",
        },
    }
    return _execute_google_request(service.events().insert(calendarId="primary", body=event))
