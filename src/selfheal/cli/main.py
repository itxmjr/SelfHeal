from __future__ import annotations

import base64
import json
from datetime import date
from pathlib import Path
from typing import Any

import typer
from rich.panel import Panel
import yaml

from selfheal import __version__
from .core import app, console, _ensure_init
from .calendar import calendar_app
from .daemon import daemon_app
from . import tasks as _tasks

from ..config import DEFAULT_CONFIG, load_config, load_life_model, save_config, CONFIG_PATH, LIFE_MODEL_PATH
from ..interview.runner import run_interview
from ..tui.app import run_tui
from ..calendar import Provider, check_auth_status, list_calendar_events
from ..obsidian import sync_to_obsidian
from ..wallpaper import update_wallpaper_data
from ..db import upsert_task, get_connection
from ..llm import get_llm_client

app.add_typer(calendar_app)
app.add_typer(daemon_app)


def _version_callback(value: bool):
    if value:
        console.print(f"selfheal {__version__}")
        raise typer.Exit()

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the SelfHeal version and exit.",
    ),
):
    """SelfHeal - AI-driven life manager."""
    if ctx.invoked_subcommand is not None:
        return

    _ensure_init()
    model = load_life_model()
    if not model:
        console.print(Panel(
            "[bold]Welcome to SelfHeal![/]\n\n"
            "No life model found. Let's set one up with a 15-minute interview.\n"
            "Run: [bold cyan]selfheal interview[/]",
            border_style="cyan",
        ))
    else:
        run_tui()

@app.command()
def interview():
    """(Re)do the 15-minute life interview."""
    _ensure_init()
    regenerate = load_life_model() is not None
    if regenerate:
        console.print("[yellow]Existing life model found. Updating it...[/]")
    run_interview(regenerate=regenerate)

@app.command(name="config")
def show_config(
    command: str | None = typer.Argument(None, help="Optional action: get or set."),
    path: str | None = typer.Argument(None, help="Dot path such as llm.provider."),
    value: str | None = typer.Argument(None, help="Value for config set."),
):
    """Show, read, or update configuration."""
    _ensure_init()
    if command is None:
        _print_config_status()
        return

    if command == "get":
        if value is not None:
            console.print("[red]Usage: selfheal config get [path][/]")
            raise typer.Exit(1)
        _config_get(path)
        return

    if command == "set":
        if path is None or value is None:
            console.print("[red]Usage: selfheal config set <path> <value>[/]")
            raise typer.Exit(1)
        _config_set(path, value)
        return

    console.print(f"[red]Unknown config command: {command}[/]")
    console.print("Usage: selfheal config [get [path] | set <path> <value>]")
    raise typer.Exit(1)


def _print_config_status():
    console.print(f"Config:     {CONFIG_PATH}")
    console.print(f"Life Model: {LIFE_MODEL_PATH}")
    console.print(f"Life Model exists: {LIFE_MODEL_PATH.exists()}")


def _config_get(path: str | None):
    config = load_config()
    if path is None:
        console.print(yaml.safe_dump(config, default_flow_style=False, sort_keys=False).rstrip())
        return

    try:
        value = _get_config_value(config, path)
    except ValueError as error:
        console.print(f"[red]{error}[/]")
        raise typer.Exit(1) from error

    if isinstance(value, dict):
        console.print(yaml.safe_dump(value, default_flow_style=False, sort_keys=False).rstrip())
    else:
        console.print(str(value))


def _config_set(path: str, raw_value: str):
    try:
        default_value = _get_config_value(DEFAULT_CONFIG, path)
    except ValueError as error:
        console.print(f"[red]{error}[/]")
        raise typer.Exit(1) from error

    if isinstance(default_value, dict):
        console.print(f"[red]Cannot set non-leaf config path: {path}[/]")
        raise typer.Exit(1)

    try:
        value = _convert_config_value(raw_value, default_value)
    except ValueError as error:
        console.print(f"[red]{error}[/]")
        raise typer.Exit(1) from error

    config = load_config()
    _set_config_value(config, path, value)
    save_config(config)
    console.print(f"[green]Set {path} = {value}[/]")


def _get_config_value(config: dict[str, Any], path: str) -> Any:
    current: Any = config
    for part in _split_config_path(path):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(_invalid_config_path_message(path))
        current = current[part]
    return current


def _set_config_value(config: dict[str, Any], path: str, value: Any):
    current: dict[str, Any] = config
    parts = _split_config_path(path)
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            raise ValueError(_invalid_config_path_message(path))
        current = next_value
    current[parts[-1]] = value


def _split_config_path(path: str) -> list[str]:
    parts = path.split(".")
    if not path or any(part == "" for part in parts):
        raise ValueError(_invalid_config_path_message(path))
    return parts


def _invalid_config_path_message(path: str) -> str:
    return f"Invalid config path '{path}'. Valid paths: {', '.join(_valid_config_paths())}"


def _valid_config_paths() -> list[str]:
    paths: list[str] = []

    def walk(prefix: str, value: Any):
        if not isinstance(value, dict):
            paths.append(prefix)
            return
        for key, child in value.items():
            walk(f"{prefix}.{key}" if prefix else key, child)

    walk("", DEFAULT_CONFIG)
    return paths


def _convert_config_value(raw_value: str, default_value: Any) -> Any:
    if isinstance(default_value, bool):
        lowered = raw_value.lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        raise ValueError(f"Expected boolean value for this path, got: {raw_value}")

    if isinstance(default_value, int):
        try:
            return int(raw_value)
        except ValueError as error:
            raise ValueError(f"Expected integer value for this path, got: {raw_value}") from error

    if isinstance(default_value, float):
        try:
            return float(raw_value)
        except ValueError as error:
            raise ValueError(f"Expected numeric value for this path, got: {raw_value}") from error

    return raw_value

@app.command(name="vision")
def vision_cmd(image_path: str):
    """Extract tasks from an image (photo/screenshot)."""
    _ensure_init()
    img_path = Path(image_path).expanduser().resolve()
    if not img_path.exists():
        console.print(f"[red]Image not found: {img_path}[/]")
        raise typer.Exit(1)

    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    console.print("[cyan]Analyzing image with AI...[/]")
    client = get_llm_client()
    prompt = """Extract actionable tasks from this image. 
Return ONLY a JSON list of tasks, where each task has:
- name: string
- emoji: single emoji
- priority: low, medium, or high
- estimated_minutes: integer
Example: [{"name": "Buy milk", "emoji": "🥛", "priority": "medium", "estimated_minutes": 10}]"""

    try:
        resp = client.vision(prompt, img_b64)
        import re
        json_match = re.search(r"\[.*\]", resp.content, re.DOTALL)
        if not json_match:
            console.print(f"[red]Could not parse tasks from AI response.[/]\n{resp.content}")
            return

        parsed_tasks = json.loads(json_match.group(0))
        if not parsed_tasks:
            console.print("[yellow]No tasks identified in image.[/]")
            return

        conn = get_connection()
        for t in parsed_tasks:
            upsert_task(conn, name=t["name"], emoji=t.get("emoji", "📝"),
                        priority=t.get("priority", "medium"),
                        estimated_minutes=t.get("estimated_minutes", 30))
            console.print(f"[green]Extracted:[/] {t.get('emoji', '')} {t['name']}")
        conn.close()
        console.print(f"\n[bold green]Successfully imported {len(parsed_tasks)} tasks from image.[/]")
    except Exception as e:
        console.print(f"[red]Vision error: {e}[/]")

@app.command(name="sync")
def sync_cmd():
    """Manually trigger all background sync tasks."""
    _ensure_init()
    console.print("[cyan]Syncing calendar...[/]")
    status = check_auth_status()
    if status.get("caldav"):
        events = list_calendar_events(Provider.CALDAV, date.today(), date.today())
        console.print(f"[green]Loaded {len(events)} CalDAV calendar event(s).[/]")
    elif status.get("google"):
        events = list_calendar_events(Provider.GOOGLE, date.today(), date.today())
        console.print(f"[green]Loaded {len(events)} Google calendar event(s).[/]")

    console.print("[cyan]Syncing to Obsidian...[/]")
    if sync_to_obsidian():
        console.print("[green]Obsidian sync complete.[/]")
    else:
        console.print("[yellow]Obsidian sync skipped (check vault_path in config).[/]")

    console.print("[cyan]Updating wallpaper data...[/]")
    update_wallpaper_data()
    console.print("[green]All sync operations complete.[/]")

@app.command()
def import_mjr():
    """Import tasks from old mjr tasks.conf."""
    _ensure_init()
    mjr_conf = Path.home() / ".config" / "mjr" / "tasks.conf"
    if not mjr_conf.exists():
        console.print(f"[red]No mjr config found at {mjr_conf}[/]")
        raise typer.Exit(1)

    conn = get_connection()
    count = 0
    with open(mjr_conf) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                schedule = parts[0].strip()
                emoji = parts[1].strip()
                name = parts[2].strip()
                upsert_task(conn, name=name, emoji=emoji, schedule=schedule,
                            priority="medium", estimated_minutes=30)
                count += 1

    conn.close()
    console.print(f"[green]Imported {count} tasks from mjr.[/]")
