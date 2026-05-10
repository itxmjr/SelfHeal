from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical

from ..widgets import DependencyChain, TimelineTable


def compose_schedule() -> ComposeResult:
    """Compose the schedule tab pane content."""
    with Horizontal(id="schedule-wrap"):
        with Vertical(id="schedule-main"):
            yield TimelineTable(id="schedule-timeline")
        with Vertical(id="schedule-side"):
            yield DependencyChain(id="dep-chain")
