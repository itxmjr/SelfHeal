from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import typer
from rich.table import Table

from .core import console, _ensure_init
from ..calendar import (
    Provider,
    check_auth_status,
    create_calendar_event,
    get_google_auth_url,
    GOOGLE_CREDENTIALS_PATH,
    list_calendar_events,
    save_google_token,
)
from ..calendar.providers.google import GOOGLE_CALENDAR_SCOPES
from ..config import load_life_model
from ..db import get_connection, get_todays_tasks

calendar_app = typer.Typer(name="calendar", help="Google Calendar and CalDAV integration.")

@calendar_app.command(name="auth")
def calendar_auth():
    """Get Google OAuth authorization URL and save credentials."""
    _ensure_init()
    if not GOOGLE_CREDENTIALS_PATH.exists():
        console.print(f"[red]Missing credentials file: {GOOGLE_CREDENTIALS_PATH}[/]")
        console.print("Download from: https://console.cloud.google.com/apis/credentials")
        console.print("Select 'OAuth 2.0 Client ID' > 'Desktop app' > download JSON")
        console.print(f"Rename to: {GOOGLE_CREDENTIALS_PATH}")
        raise typer.Exit(1)

    url = get_google_auth_url()
    console.print(f"[bold cyan]Open this URL to authorize:[/]\n{url}\n")
    console.print("After authorizing, paste the redirect URL here:")
    redirect = typer.prompt("Redirect URL")
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(str(GOOGLE_CREDENTIALS_PATH), scopes=GOOGLE_CALENDAR_SCOPES)
    flow.fetch_token(code=redirect)
    save_google_token(json.loads(flow.credentials.to_json()))
    console.print("[green]Google Calendar authenticated successfully![/]")

@calendar_app.command(name="status")
def calendar_status():
    """Check calendar authentication status."""
    status = check_auth_status()
    table = Table(show_header=False, box=None, title="Calendar Status")
    table.add_column("Service", style="bold")
    table.add_column("Status")
    table.add_row("Google Calendar", "[green]Authenticated[/]" if status["google"] else "[red]Not authenticated[/]")
    table.add_row("Google Credentials File", "[green]Present[/]" if status["google_credentials"] else "[red]Missing[/]")
    table.add_row("Google Token File", "[green]Present[/]" if status["google_token"] else "[yellow]No token yet[/]")
    table.add_row("CalDAV", "[green]Configured[/]" if status["caldav"] else "[yellow]Not configured[/]")
    console.print(table)

@calendar_app.command(name="sync")
def calendar_sync(
    days: int = typer.Option(7, "--days", "-d", help="Days to sync"),
    provider: str = typer.Option("google", "--provider", "-p", help="Provider: google or caldav"),
):
    """Sync calendar events and show what's scheduled."""
    _ensure_init()
    prov = Provider(provider.lower())
    today = date.today()
    try:
        events = list_calendar_events(prov, today, today + timedelta(days=days))
    except RuntimeError as e:
        console.print(f"[red]Calendar error: {e}[/]")
        raise typer.Exit(1)
    if not events:
        console.print("[yellow]No events found in calendar.[/]")
        return

    table = Table(title=f" Calendar Events ({prov.value}) ", show_header=True, header_style="bold cyan")
    table.add_column("Date", width=12)
    table.add_column("Time", width=12)
    table.add_column("Event", width=30)
    table.add_column("Location", width=20)

    for ev in events:
        start = ev["start"]
        if ev["all_day"]:
            time_str = "[dim]all day[/]"
            date_str = start[:10]
        else:
            try:
                dt = datetime.fromisoformat(start)
                date_str = dt.strftime("%a %b %d")
                time_str = dt.strftime("%H:%M")
            except (ValueError, TypeError):
                date_str = start[:10]
                time_str = start[11:16] if len(start) > 10 else ""

        table.add_row(date_str, time_str, ev["summary"], ev.get("location", "") or "")

    console.print(table)
    console.print(f"[dim]{len(events)} event(s) found[/]")

@calendar_app.command(name="push")
def calendar_push(
    provider: str = typer.Option("google", "--provider", "-p", help="Provider: google or caldav"),
    day_offset: int = typer.Option(0, "--day", "-d", help="Day offset (0=today, 1=tomorrow, etc.)"),
):
    """Push today's scheduled tasks to calendar as events."""
    _ensure_init()
    model = load_life_model()
    if not model:
        console.print("[red]No life model. Run 'selfheal interview' first.[/]")
        raise typer.Exit(1)

    from datetime import timedelta as td

    target_date = date.today() + td(days=day_offset)
    conn = get_connection()
    tasks = get_todays_tasks(conn, target_date.isoformat())
    conn.close()

    prov = Provider(provider.lower())
    pushed = 0
    for t in tasks:
        start_str = t.get("scheduled_start")
        end_str = t.get("scheduled_end")
        if not start_str or not end_str:
            continue

        try:
            start_dt = datetime.strptime(f"{target_date.isoformat()} {start_str}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{target_date.isoformat()} {end_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        summary = f"{t.get('emoji', '')} {t.get('name', '')}".strip()
        if t.get("status") == "done":
            summary = f"[done] {summary}"

        try:
            create_calendar_event(
                prov, summary=summary,
                start=start_dt, end=end_dt,
                description=f"Priority: {t.get('priority', 'medium')} | SelfHeal Task",
            )
            pushed += 1
        except RuntimeError as e:
            console.print(f"[red]Calendar error: {e}[/]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[yellow]Skipped {summary}: {e}[/]")

    console.print(f"[green]Pushed {pushed} task(s) to calendar.[/]")
