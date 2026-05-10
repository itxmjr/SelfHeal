from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from textual.widgets import DataTable, Static


class TimelineTable(DataTable):
    def on_mount(self):
        self.add_columns("Hour", "Block", "Task", "Priority", "Blocked By")

    def set_tasks(self, tasks: list[dict]):
        self.clear(columns=False)
        now_hour = datetime.now().hour

        slots: dict[int, list[dict]] = defaultdict(list)
        unscheduled: list[dict] = []

        for t in tasks:
            start = t.get("scheduled_start")
            if start:
                try:
                    h = int(start.split(":")[0])
                    slots[h].append(t)
                except (ValueError, IndexError):
                    unscheduled.append(t)
            else:
                unscheduled.append(t)

        for hour in sorted(slots):
            for t in slots[hour]:
                self._add_task_row(t, hour, now_hour)

        for t in unscheduled:
            self._add_task_row(t, None, now_hour)

    def _add_task_row(self, t: dict, hour: int | None, now_hour: int):
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

        hour_str = f"{hour:02d}:00" if hour is not None else "--:--"
        key = f"{hour_str}_{task_id}" if hour is not None else f"xx_{task_id}"

        is_current = hour is not None and not is_done and not is_blocked and hour <= now_hour < hour + 1

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

        self.add_row(hour_str, block_cell, name_cell, priority_text, blocked_text, key=key)


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