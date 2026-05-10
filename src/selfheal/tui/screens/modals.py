from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from ...config import CONFIG_PATH, LIFE_MODEL_PATH

class AddTaskModal(ModalScreen[dict | None]):
    CSS = """
    AddTaskModal {
        align: center middle;
    }
    #add-task-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        border: thick $background 80%;
        background: $surface;
    }
    .input-row {
        margin-bottom: 1;
    }
    #buttons {
        margin-top: 1;
        align: right middle;
    }
    Button {
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="add-task-dialog"):
            yield Label("Add New Task", classes="input-row")
            yield Input(placeholder="Task name", id="task-name", classes="input-row")
            yield Input(placeholder="Emoji (e.g. 📝)", id="task-emoji", classes="input-row")
            yield Select(
                [("Low", "low"), ("Medium", "medium"), ("High", "high"), ("Critical", "critical")],
                prompt="Priority",
                value="medium",
                id="task-priority",
                classes="input-row"
            )
            yield Input(placeholder="Estimated minutes (e.g. 30)", value="30", id="task-minutes", classes="input-row")
            yield Input(placeholder="Schedule (e.g. daily, weekly)", value="daily", id="task-schedule", classes="input-row")
            with Horizontal(id="buttons"):
                yield Button("Cancel", variant="error", id="cancel")
                yield Button("Add", variant="success", id="add")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
        elif event.button.id == "add":
            name = self.query_one("#task-name", Input).value.strip()
            if not name:
                self.app.notify("Task name is required", severity="error")
                return
            emoji = self.query_one("#task-emoji", Input).value.strip()
            priority = self.query_one("#task-priority", Select).value
            try:
                minutes = int(self.query_one("#task-minutes", Input).value.strip())
            except ValueError:
                minutes = 30
            schedule = self.query_one("#task-schedule", Input).value.strip() or "daily"
            
            self.dismiss({
                "name": name,
                "emoji": emoji,
                "priority": priority,
                "estimated_minutes": minutes,
                "schedule": schedule
            })

class VisionImportModal(ModalScreen[str | None]):
    CSS = """
    VisionImportModal {
        align: center middle;
    }
    #vision-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        border: thick $background 80%;
        background: $surface;
    }
    #buttons {
        margin-top: 1;
        align: right middle;
    }
    Button {
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="vision-dialog"):
            yield Label("Vision Import", classes="input-row")
            yield Label("Enter path to image (photo/screenshot) to extract tasks:", classes="input-row")
            yield Input(placeholder="/path/to/image.jpg", id="image-path", classes="input-row")
            with Horizontal(id="buttons"):
                yield Button("Cancel", variant="error", id="cancel")
                yield Button("Import", variant="success", id="import")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
        elif event.button.id == "import":
            path = self.query_one("#image-path", Input).value.strip()
            if not path:
                self.app.notify("Image path is required", severity="error")
                return
            self.dismiss(path)

class ConfigModal(ModalScreen[dict[str, str] | None]):
    CSS = """
    ConfigModal {
        align: center middle;
    }
    #config-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        border: thick $background 80%;
        background: $surface;
    }
    #buttons {
        margin-top: 1;
        align: right middle;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="config-dialog"):
            yield Label("[bold]Configuration[/]")
            yield Static(f"Config Path: {CONFIG_PATH}")
            yield Static(f"Life Model Path: {LIFE_MODEL_PATH}")
            yield Static(f"Life Model Exists: {LIFE_MODEL_PATH.exists()}")
            yield Input(placeholder="Config path (e.g. llm.provider)", id="config-path")
            yield Input(placeholder="Value", id="config-value")
            with Horizontal(id="buttons"):
                yield Button("Save", variant="success", id="save")
                yield Button("Close", variant="primary", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss(None)
            return
        if event.button.id == "save":
            path = self.query_one("#config-path", Input).value.strip()
            value = self.query_one("#config-value", Input).value.strip()
            if not path:
                self.app.notify("Config path is required", severity="error")
                return
            self.dismiss({"path": path, "value": value})

class HelpModal(ModalScreen[None]):
    CSS = """
    HelpModal {
        align: center middle;
    }
    #help-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        border: thick $background 80%;
        background: $surface;
    }
    #buttons {
        margin-top: 1;
        align: right middle;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Label("[bold]Keyboard Shortcuts[/]")
            yield Static("a - Add task")
            yield Static("v - Vision import (from image)")
            yield Static("c - View configuration")
            yield Static("? - Show this help")
            yield Static("1..4 - Switch tabs")
            yield Static("alt+left/right - Prev/Next tab")
            yield Static("o - Open external link (ClickUp)")
            yield Static("q - Quit")
            yield Static("r - Refresh / Sync All")
            yield Static("d - Toggle selected task")
            yield Static("g - Regenerate schedule")
            with Horizontal(id="buttons"):
                yield Button("Close", variant="primary", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)
