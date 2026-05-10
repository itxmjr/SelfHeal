from __future__ import annotations

from datetime import date

import typer
from rich.panel import Panel
from rich.table import Table

from .core import app, console, _ensure_init
from ..config import load_life_model
from ..db import get_connection, get_todays_tasks, mark_task_done, mark_task_pending, upsert_task
from ..engine.scheduler import generate_and_persist_schedule, get_next_action
from ..engine.scorer import calculate_score


@app.command()
def today():
    """Show today's AI-generated schedule."""
    _ensure_init()
    model = load_life_model()
    if not model:
        console.print("[red]No life model found. Run 'selfheal interview' first.[/]")
        raise typer.Exit(1)

    schedule = generate_and_persist_schedule(life_model=model, calendar_events=[])
    if not schedule:
        console.print("[yellow]No schedule generated. Check your life model.[/]")
        raise typer.Exit(0)

    today_str = date.today().strftime("%A, %B %d, %Y")

    table = Table(title=f" {today_str} ", show_header=True, header_style="bold cyan")
    table.add_column("Time", style="bold", width=12)
    table.add_column("Task", width=30)
    table.add_column("Priority", width=10)
    table.add_column("Status", width=10)

    for item in schedule:
        time_str = f"{item['start_hour']:02d}:00 - {item['end_hour']:02d}:00"
        task_str = f"{item['emoji']} {item['name']}"
        priority = item["priority"]
        status = item.get("status", "pending")

        if status == "done":
            status_str = "[green]done[/]"
            task_str = f"[dim]{task_str}[/]"
        elif status == "pending":
            status_str = "[yellow]pending[/]"
        else:
            status_str = f"[dim]{status}[/]"

        table.add_row(time_str, task_str, priority, status_str)

    console.print()
    console.print(table)

    score_result = calculate_score()
    sc = "green" if score_result["score"] >= 70 else "yellow" if score_result["score"] >= 40 else "red"
    console.print()
    console.print(Panel(
        f"[bold {sc}]Score: {score_result['score']:.0f}/100[/]\n"
        f"Tasks: {score_result['done']}/{score_result['total']} | Streak: {score_result['streak']} days",
        title="Today",
        border_style=sc,
    ))


@app.command(name="next")
def next_action():
    """What should I do RIGHT NOW?"""
    _ensure_init()
    model = load_life_model()
    if not model:
        console.print("[red]No life model found. Run 'selfheal interview' first.[/]")
        raise typer.Exit(1)

    action = get_next_action()
    if not action:
        console.print("[green]All done for today! Or no schedule yet. Run 'selfheal today' first.[/]")
        raise typer.Exit(0)

    emoji = action.get("emoji", "")
    name = action.get("name", "Unknown")
    priority = action.get("priority", "?")
    sched_start = action.get("scheduled_start", "?")
    sched_end = action.get("scheduled_end", "?")

    console.print(Panel(
        f"[bold]{emoji} {name}[/]\n"
        f"Priority: {priority} | Scheduled: {sched_start} - {sched_end}",
        title="[bold cyan]Do This Now[/]",
        border_style="cyan",
    ))


@app.command(name="done")
def mark_done(task_name: str):
    """Mark a task as done (by name or partial match)."""
    _ensure_init()
    conn = get_connection()
    today_str = date.today().isoformat()
    tasks = get_todays_tasks(conn, today_str)

    match = None
    for t in tasks:
        if task_name.lower() in t["name"].lower():
            match = t
            break

    if not match:
        console.print(f"[red]No matching task found for '{task_name}'[/]")
        conn.close()
        raise typer.Exit(1)

    mark_task_done(conn, match["id"], today_str)
    console.print(f"[green]Done: {match.get('emoji', '')} {match['name']}[/]")
    conn.close()


@app.command(name="add")
def add_task(task_name: str, schedule: str = "daily", priority: str = "medium",
             emoji: str = "", minutes: int = 30):
    """Quick add a task."""
    _ensure_init()
    conn = get_connection()
    task_id = upsert_task(conn, name=task_name, emoji=emoji, schedule=schedule,
                          priority=priority, estimated_minutes=minutes)
    console.print(f"[green]Added: {emoji} {task_name} (id={task_id})[/]")
    conn.close()


@app.command()
def score():
    """Show today's productivity score."""
    _ensure_init()
    result = calculate_score()
    sc = "green" if result["score"] >= 70 else "yellow" if result["score"] >= 40 else "red"

    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Overall Score", f"[bold {sc}]{result['score']:.0f}/100[/]")
    table.add_row("Tasks Done", f"{result['done']}/{result['total']}")
    table.add_row("Task Completion", f"{result['task_completion']:.1f}/40")
    table.add_row("Time Utilization", f"{result['time_utilization']:.1f}/30")
    table.add_row("Goal Alignment", f"{result['goal_alignment']:.1f}/20")
    table.add_row("Consistency Bonus", f"{result['consistency_bonus']:.1f}/10")
    table.add_row("Streak", f"{result['streak']} days")

    console.print(Panel(table, title="[bold]Productivity Score[/]", border_style=sc))


@app.command()
def toggle(task_id: int):
    """Toggle a task done/pending by ID."""
    _ensure_init()
    conn = get_connection()
    today_str = date.today().isoformat()
    tasks = get_todays_tasks(conn, today_str)

    task = None
    for t in tasks:
        if t["id"] == task_id:
            task = t
            break

    if not task:
        console.print(f"[red]Task {task_id} not found in today's tasks.[/]")
        conn.close()
        raise typer.Exit(1)

    if task.get("status") == "done":
        mark_task_pending(conn, task_id, today_str)
        console.print(f"[yellow]Unmarked: {task.get('emoji', '')} {task['name']}[/]")
    else:
        mark_task_done(conn, task_id, today_str)
        console.print(f"[green]Done: {task.get('emoji', '')} {task['name']}[/]")
    conn.close()
