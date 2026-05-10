from __future__ import annotations

from textual.widgets import DataTable


class TaskTable(DataTable):
    def __init__(self, *, id: str | None = None):
        super().__init__(id=id)
        self.cursor_type = "row"
        self.zebra_stripes = True

    def on_mount(self):
        self.add_columns("ID", "Task", "Priority", "Status", "Time", "Blocked", "Goal", "Depends On", "Source")

    def set_tasks(self, tasks: list[dict]):
        self.clear(columns=False)

        for t in tasks:
            task_id = str(t.get("id", ""))
            task = f"{t.get('emoji', '')} {t.get('name', '')}".strip()

            priority = t.get("priority", "medium")
            p_color = {"critical": "red", "high": "yellow", "medium": "cyan", "low": "dim"}.get(priority, "cyan")
            priority_text = f"[{p_color}]{priority}[/]"

            status = str(t.get("status", "pending"))
            if status == "done":
                status_text = "[green]done[/]"
            elif status == "pending":
                status_text = "[yellow]pending[/]"
            elif status == "blocked":
                status_text = "[red]blocked[/]"
            else:
                status_text = f"[dim]{status}[/]"

            start = t.get("scheduled_start") or "--:--"
            end = t.get("scheduled_end") or "--:--"
            time_text = f"{start}-{end}"

            blocked = "[red]yes[/]" if t.get("is_blocked") else "[green]no[/]"

            goal = t.get("goal_name", "") or t.get("goal", "") or ""
            goal_text = f"[dim]{goal}[/]" if goal else "[dim]-[/]"

            depends_on = t.get("depends_on_names", "") or ""
            dep_text = f"[yellow]{depends_on}[/]" if depends_on else "[dim]-[/]"

            source = t.get("source", "local")
            if source == "clickup":
                ext_url = t.get("external_url", "")
                due = t.get("due_date", "") or t.get("due_datetime", "")
                due_str = f" (Due: {due})" if due else ""
                url_str = " 🔗" if ext_url else ""
                source_text = f"[magenta]ClickUp[/]{url_str}{due_str}"
            else:
                source_text = f"[dim]{source}[/]"

            key = task_id

            self.add_row(
                task_id, task, priority_text, status_text, time_text, blocked, goal_text, dep_text, source_text,
                key=key,
            )

    def selected_task_id(self) -> int | None:
        if self.row_count == 0:
            return None
        row_index = self.cursor_row
        if row_index is None or row_index < 0 or row_index >= self.row_count:
            return None

        row = self.get_row_at(row_index)
        if not row:
            return None

        raw = row[0]
        try:
            return int(str(raw))
        except ValueError:
            return None