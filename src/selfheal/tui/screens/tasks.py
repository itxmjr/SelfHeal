from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from ..widgets import TaskTable


def compose_tasks() -> ComposeResult:
    """Compose the tasks tab pane content."""
    yield TaskTable(id="tasks-table")
    yield Static(
        "[bold]d[/] toggle selected  |  [bold]r[/] refresh  |  [bold]g[/] regenerate  |  [bold]q[/] quit",
        id="tasks-help",
    )
