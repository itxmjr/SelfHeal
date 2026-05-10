from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from ..widgets import HourBar, ScoreRing, TaskTable


def compose_dashboard() -> ComposeResult:
    """Compose the dashboard tab pane content."""
    with Horizontal(id="dashboard-wrap"):
        with Vertical(id="left-panel"):
            yield ScoreRing(id="score-ring")
            yield Static(id="stats-box")
            yield Static(id="next-box")
            with Horizontal(id="sync-buttons", classes="sync-controls"):
                yield Button("Sync All", id="btn-sync-all", variant="primary")
                yield Button("Calendar", id="btn-sync-calendar")
                yield Button("ClickUp", id="btn-sync-clickup")
                yield Button("Obsidian", id="btn-sync-obsidian")
        with Vertical(id="right-panel"):
            yield HourBar(id="hour-bar")
            yield TaskTable(id="schedule-table")
