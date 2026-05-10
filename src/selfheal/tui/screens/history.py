from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import DataTable, Static


def compose_history() -> ComposeResult:
    """Compose the history tab pane content."""
    yield DataTable(id="history-table")
    yield Static(id="history-box")
