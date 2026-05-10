from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from textual.widgets import DataTable, Static


class TimelineTable(DataTable):
    def on_mount(self):
        self.add_columns("Time", "Block", "Task", "Priority", "Blocked By")

    def set_tasks(self, tasks: list[dict]):
        self.clear(columns=False)
        now_time = datetime.now().strftime("%H:%M")

        scheduled: list[dict] = []
        unscheduled: list[dict] = []

        for t in tasks:
            if t.get("scheduled_start"):
                scheduled.append(t)
            else:
                unscheduled.append(t)
                
        scheduled.sort(key=lambda x: x["scheduled_start"])

        for t in scheduled:
            self._add_task_row(t, t["scheduled_start"], t.get("scheduled_end"), now_time)

        for t in unscheduled:
            self._add_task_row(t, None, None, now_time)

    def _add_task_row(self, t: dict, start_time: str | None, end_time: str | None, now_time: str):
        status = t.get("status", "pending")
        is_blocked = t.get("is_blocked")
        is_done = status == "done"

        task_id = str(t.get("id", ""))
        name = f"{t.get('emoji', '')} {t.get('name', '')}".strip()

        priority = t.get("priority", "medium")
        p_color = {"critical": "red", "high": "yellow", "medium": "cyan", "low": "dim"}.get(priority, "cyan")
        priority_text = f"[{p_color}]{priority}[/]"

        depends_on_names = t.get("depends_on_names", "")
        blocked_text = f"[yellow]{depends_on_names}[/]" if depends_on_names else ("[red]unmet deps[/]" if is_blocked else "[dim]-[/]")

        time_str = f"{start_time}-{end_time}" if start_time and end_time else "--:--"
        key = f"{start_time}_{task_id}" if start_time is not None else f"xx_{task_id}"

        is_current = start_time is not None and end_time is not None and not is_done and not is_blocked and start_time <= now_time < end_time

        if is_current:
            block_cell = "[bold white on dark_green]█[/]"
            name_cell = f"[bold]{name}[/]"
        elif is_done:
            block_cell = "[dim]▌[/]"
            name_cell = f"[dim]{name}[/]"
        elif is_blocked:
            block_cell = "[dim]·[/]"
            name_cell = f"[dim]{name}[/]"
        else:
            block_cell = "[cyan]█[/]"
            name_cell = name

        self.add_row(time_str, block_cell, name_cell, priority_text, blocked_text, key=key)


class DependencyChain(Static):
    def __init__(self, tasks: list[dict] | None = None, *, id: str | None = None):
        super().__init__(id=id)
        self.tasks = tasks or []

    def update_tasks(self, tasks: list[dict]):
        self.tasks = tasks
        self.refresh()

    def render(self) -> str:
        if not self.tasks:
            return "[dim]No tasks today[/]"

        lines = ["[bold]Dependency Chain[/]\n"]

        for t in self.tasks:
            status = t.get("status", "pending")
            is_done = status == "done"
            is_blocked = t.get("is_blocked")
            name = f"{t.get('emoji', '')} {t.get('name', '')}".strip()

            if is_done:
                icon = "[green]✓[/]"
                name = f"[dim]{name}[/]"
            elif is_blocked:
                icon = "[red]⊘[/]"
            else:
                icon = "[yellow]○[/]"

            lines.append(f"{icon} {name}")
            deps = t.get("depends_on_names", "")
            if deps:
                lines.append(f"    [dim]∋ {deps}[/]")

        return "\n".join(lines)