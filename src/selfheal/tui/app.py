from __future__ import annotations

from datetime import date
from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane

from ..calendar import Provider, check_auth_status, list_calendar_events
from ..config import load_life_model, set_config_path
from ..daemon import (
    daemon_add_task,
    daemon_generate_schedule,
    daemon_get_next,
    daemon_get_score,
    daemon_get_status,
    daemon_get_tasks,
    daemon_sync_all,
    daemon_sync_calendar,
    daemon_sync_clickup,
    daemon_sync_obsidian,
    daemon_toggle_task,
    is_daemon_running,
)
from ..db import (
    get_connection,
    get_history,
    get_todays_tasks,
)
from ..engine.life_model import get_available_hours
from ..engine.scheduler import get_next_action
from ..engine.scorer import calculate_score
from .widgets import DependencyChain, HourBar, ScoreRing, TaskTable, TimelineTable

from .screens.dashboard import compose_dashboard
from .screens.schedule import compose_schedule
from .screens.tasks import compose_tasks
from .screens.history import compose_history
from .screens.modals import AddTaskModal, VisionImportModal, ConfigModal, HelpModal
import base64
import json
import webbrowser
from pathlib import Path
from ..llm import get_llm_client


class SelfHealApp(App):
    TITLE = "SelfHeal"
    SUB_TITLE = "Minimalist productivity command center"
    _daemon_connected: bool = False
    _calendar_events: list[dict[str, Any]] = []
    _daemon_status: dict[str, Any] = {}

    CSS = """
    Screen {
        layout: vertical;
    }

    #daemon-status {
        height: 1;
        padding-left: 1;
        color: $text-muted;
    }

    #root-tabs {
        height: 1fr;
    }

    #dashboard-wrap {
        layout: horizontal;
        height: 1fr;
    }

    #left-panel {
        width: 38;
        min-width: 32;
        margin-right: 1;
    }

    #right-panel {
        width: 1fr;
    }

    #score-ring {
        border: solid $accent;
        padding: 1;
        height: 8;
        margin-bottom: 1;
    }

    #stats-box, #next-box {
        border: solid $surface;
        padding: 1;
        margin-bottom: 1;
    }

    #sync-buttons {
        height: auto;
        margin-bottom: 1;
    }

    #sync-buttons Button {
        min-width: 10;
        margin-right: 1;
    }

    #dep-chain {
        border: solid $surface;
        padding: 1;
        height: 1fr;
        margin-top: 1;
    }

    #hour-bar {
        border: solid $surface;
        padding: 1;
        height: 6;
        margin-bottom: 1;
    }

    #tasks-table, #schedule-table, #history-table {
        height: 1fr;
    }

    #schedule-wrap {
        layout: horizontal;
        height: 1fr;
    }

    #schedule-main {
        width: 1fr;
        margin-right: 1;
    }

    #schedule-side {
        width: 30;
    }

    #tasks-help {
        border: solid $surface;
        padding: 1;
        height: 3;
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("d", "toggle_selected", "Toggle"),
        ("g", "regenerate", "Regenerate"),
        ("a", "add_task", "Add Task"),
        ("v", "vision_import", "Vision Import"),
        ("c", "show_config", "Config"),
        ("?", "show_help", "Help"),
        ("1", "switch_tab('tab-dashboard')", "Dashboard"),
        ("2", "switch_tab('tab-tasks')", "Tasks"),
        ("3", "switch_tab('tab-schedule')", "Schedule"),
        ("4", "switch_tab('tab-history')", "History"),
        ("alt+left", "prev_tab", "Prev Tab"),
        ("alt+right", "next_tab", "Next Tab"),
        ("o", "open_link", "Open Link"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Daemon: checking", id="daemon-status")
        with TabbedContent(id="root-tabs"):
            with TabPane("Dashboard", id="tab-dashboard"):
                yield from compose_dashboard()
            with TabPane("Tasks", id="tab-tasks"):
                yield from compose_tasks()
            with TabPane("Schedule", id="tab-schedule"):
                yield from compose_schedule()
            with TabPane("History", id="tab-history"):
                yield from compose_history()

        yield Footer()

    def on_mount(self) -> None:
        self._daemon_connected = is_daemon_running()
        if self._daemon_connected:
            try:
                self._daemon_status = daemon_get_status()
                pid = self._daemon_status.get("pid", "?")
                self.notify(f"Daemon connected (PID {pid})", severity="information")
            except Exception:
                self._daemon_connected = False
                self._daemon_status = {}

        model = load_life_model()
        if not model:
            self.notify("Run `selfheal interview` first to create your life model.", severity="warning")

        self._sync_calendar()

        tasks = self._load_tasks()
        if not any(t.get("scheduled_start") for t in tasks):
            if self._daemon_connected:
                try:
                    daemon_generate_schedule(date.today())
                except Exception:
                    self._set_daemon_offline()
                    self.notify("Daemon schedule generation failed; offline mode is read-only for scheduling", severity="warning")
            else:
                self.notify("No schedule yet; start the daemon to generate one", severity="warning")

        history_table = self.query_one("#history-table", DataTable)
        history_table.add_columns("Date", "Score", "Tasks", "Time", "Goal", "Bonus")

        self.set_timer(30, self._auto_refresh_tick)

        self.refresh_all()

    def _sync_calendar(self) -> None:
        if self._daemon_connected:
            try:
                sync_result = daemon_sync_all()
                self._daemon_status = daemon_get_status()
                self._apply_daemon_calendar_sync(sync_result)
                return
            except Exception:
                self._set_daemon_offline()
                self.notify("Daemon calendar sync failed; using local calendar fallback", severity="warning")
        self._sync_calendar_locally()

    def _sync_calendar_locally(self) -> None:
        status = check_auth_status()
        if status.get("caldav"):
            events = list_calendar_events(Provider.CALDAV, date.today(), date.today())
            self._calendar_events = events
            if events:
                self.notify(f"Loaded {len(events)} calendar event(s) from CalDAV", severity="information")
        elif status.get("google"):
            events = list_calendar_events(Provider.GOOGLE, date.today(), date.today())
            self._calendar_events = events
            if events:
                self.notify(f"Loaded {len(events)} calendar event(s) from Google Calendar", severity="information")
        else:
            self._calendar_events = []

    def _apply_daemon_calendar_sync(self, sync_result: dict[str, Any]) -> None:
        calendar_result = sync_result.get("calendar", {})
        events = calendar_result.get("events", []) if isinstance(calendar_result, dict) else []
        self._calendar_events = events if isinstance(events, list) else []
        provider = calendar_result.get("provider") if isinstance(calendar_result, dict) else None
        if self._calendar_events and provider:
            self.notify(
                f"Loaded {len(self._calendar_events)} calendar event(s) from daemon {provider}",
                severity="information",
            )

    def _auto_refresh_tick(self) -> None:
        self.refresh_all()
        self.set_timer(30, self._auto_refresh_tick)

    def action_refresh(self) -> None:
        if self._daemon_connected:
            try:
                sync_result = daemon_sync_all()
                self._daemon_status = daemon_get_status()
                self._apply_daemon_calendar_sync(sync_result)
                self.refresh_all()
                self.notify("Synced via daemon")
                return
            except Exception:
                self._set_daemon_offline()
                self.notify("Daemon offline; refreshed local read model", severity="warning")
        self.refresh_all()
        self.notify("Refreshed")

    def action_toggle_selected(self) -> None:
        table = self._current_task_table()
        if table is None:
            self.notify("No task table focused", severity="warning")
            return

        task_id = table.selected_task_id()
        if task_id is None:
            self.notify("Select a task row first", severity="warning")
            return

        tasks = self._load_tasks()
        task = next((t for t in tasks if t.get("id") == task_id), None)
        if not task:
            self.notify("Task not found", severity="error")
            return

        if task.get("is_blocked"):
            self.notify("Task is blocked by dependencies", severity="warning")
            return

        if self._daemon_connected:
            try:
                updated = daemon_toggle_task(task_id)
                self.notify(f"Marked {updated.get('status', 'updated')}: {task.get('name', '')}")
                self.refresh_all()
                return
            except Exception:
                self._set_daemon_offline()
        self.notify("Daemon offline; start daemon to toggle tasks", severity="warning")
        self.refresh_all()

    def action_regenerate(self) -> None:
        if not self._daemon_connected:
            self.notify("Start the daemon to generate schedules", severity="warning")
            self.refresh_all()
            return
        try:
            updated = daemon_generate_schedule(date.today())
            self._daemon_status = daemon_get_status()
        except Exception:
            self._set_daemon_offline()
            self.refresh_all()
            self.notify("Daemon offline; schedule generation skipped", severity="warning")
            return
        self.refresh_all()
        self.notify(f"Generated {len(updated)} schedule block(s) via daemon")

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one(TabbedContent)
        tabs.active = tab_id

    def action_prev_tab(self) -> None:
        tabs = self.query_one(TabbedContent)
        tab_ids = ["tab-dashboard", "tab-tasks", "tab-schedule", "tab-history"]
        try:
            idx = tab_ids.index(tabs.active)
            tabs.active = tab_ids[(idx - 1) % len(tab_ids)]
        except ValueError:
            pass

    def action_next_tab(self) -> None:
        tabs = self.query_one(TabbedContent)
        tab_ids = ["tab-dashboard", "tab-tasks", "tab-schedule", "tab-history"]
        try:
            idx = tab_ids.index(tabs.active)
            tabs.active = tab_ids[(idx + 1) % len(tab_ids)]
        except ValueError:
            pass

    def action_open_link(self) -> None:
        table = self._current_task_table()
        if table is None:
            self.notify("No task table focused", severity="warning")
            return

        task_id = table.selected_task_id()
        if task_id is None:
            self.notify("Select a task row first", severity="warning")
            return

        tasks = self._load_tasks()
        task = next((t for t in tasks if t.get("id") == task_id), None)
        if not task:
            self.notify("Task not found", severity="error")
            return

        url = task.get("external_url")
        if not url:
            self.notify("No external URL for this task", severity="warning")
            return

        try:
            webbrowser.open(url)
            self.notify(f"Opened {url}")
        except Exception as e:
            self.notify(f"Failed to open URL: {e}", severity="error")

    def on_button_pressed(self, event: Any) -> None:
        if event.button.id == "btn-sync-all":
            self.action_refresh()
        elif event.button.id == "btn-sync-calendar":
            if self._daemon_connected:
                try:
                    daemon_sync_calendar()
                    self.notify("Synced Calendar via daemon")
                    self.refresh_all()
                except Exception:
                    self._set_daemon_offline()
                    self.notify("Daemon offline; calendar sync failed", severity="warning")
            else:
                self.notify("Daemon offline; start daemon to sync calendar", severity="warning")
        elif event.button.id == "btn-sync-clickup":
            if self._daemon_connected:
                try:
                    daemon_sync_clickup()
                    self.notify("Synced ClickUp via daemon")
                    self.refresh_all()
                except Exception:
                    self._set_daemon_offline()
                    self.notify("Daemon offline; ClickUp sync failed", severity="warning")
            else:
                self.notify("Daemon offline; start daemon to sync ClickUp", severity="warning")
        elif event.button.id == "btn-sync-obsidian":
            if self._daemon_connected:
                try:
                    daemon_sync_obsidian()
                    self.notify("Synced Obsidian via daemon")
                    self.refresh_all()
                except Exception:
                    self._set_daemon_offline()
                    self.notify("Daemon offline; Obsidian sync failed", severity="warning")
            else:
                self.notify("Daemon offline; start daemon to sync Obsidian", severity="warning")

    def action_add_task(self) -> None:
        def check_add_task(result: dict | None) -> None:
            if result is None:
                return
            if self._daemon_connected:
                try:
                    daemon_add_task(**result)
                    self.notify(f"Added task via daemon: {result['name']}")
                    self.refresh_all()
                    return
                except Exception:
                    self._set_daemon_offline()
            self.notify("Daemon offline; start daemon to add tasks", severity="warning")
            self.refresh_all()

        self.push_screen(AddTaskModal(), check_add_task)

    def action_vision_import(self) -> None:
        if not self._daemon_connected:
            self.notify("Daemon offline; start daemon to import vision tasks", severity="warning")
            return

        def check_vision_import(image_path: str | None) -> None:
            if not image_path:
                return
            
            img_path = Path(image_path).expanduser().resolve()
            if not img_path.exists():
                self.notify(f"Image not found: {img_path}", severity="error")
                return

            self.notify("Analyzing image with AI...", severity="information")
            
            # Run in background to avoid blocking TUI
            self.run_worker(self._do_vision_import(img_path), exclusive=True)

        self.push_screen(VisionImportModal(), check_vision_import)

    async def _do_vision_import(self, img_path: Path) -> None:
        try:
            with open(img_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()

            client = get_llm_client()
            prompt = """Extract actionable tasks from this image. 
Return ONLY a JSON list of tasks, where each task has:
- name: string
- emoji: single emoji
- priority: low, medium, or high
- estimated_minutes: integer
Example: [{"name": "Buy milk", "emoji": "🥛", "priority": "medium", "estimated_minutes": 10}]"""

            resp = client.vision(prompt, img_b64)
            import re
            json_match = re.search(r"\[.*\]", resp.content, re.DOTALL)
            if not json_match:
                self.call_from_thread(self.notify, "Could not parse tasks from AI response.", severity="error")
                return

            parsed_tasks = json.loads(json_match.group(0))
            if not parsed_tasks:
                self.call_from_thread(self.notify, "No tasks identified in image.", severity="warning")
                return

            if self._daemon_connected:
                try:
                    for t in parsed_tasks:
                        daemon_add_task(
                            name=t["name"],
                            emoji=t.get("emoji", "📝"),
                            priority=t.get("priority", "medium"),
                            estimated_minutes=t.get("estimated_minutes", 30)
                        )
                    self.call_from_thread(self.notify, f"Successfully imported {len(parsed_tasks)} tasks via daemon.", severity="information")
                    self.call_from_thread(self.refresh_all)
                    return
                except Exception:
                    self.call_from_thread(self._set_daemon_offline)
                    self.call_from_thread(self.notify, "Daemon offline; vision import was not saved", severity="warning")
            self.call_from_thread(self.refresh_all)
        except Exception as e:
            self.call_from_thread(self.notify, f"Vision error: {e}", severity="error")

    def action_show_config(self) -> None:
        def save_config_value(result: dict[str, str] | None) -> None:
            if result is None:
                return
            try:
                value = set_config_path(result["path"], result["value"])
            except ValueError as error:
                self.notify(str(error), severity="error")
                return
            self.notify(f"Set {result['path']} = {value}", severity="information")

        self.push_screen(ConfigModal(), save_config_value)

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    def refresh_all(self) -> None:
        self._refresh_daemon_status()
        self._refresh_dashboard()
        self._refresh_tasks()
        self._refresh_schedule()
        self._refresh_history()

    def _refresh_daemon_status(self) -> None:
        status_line = self.query_one("#daemon-status", Static)
        if self._daemon_connected:
            try:
                self._daemon_status = daemon_get_status()
            except Exception:
                self._set_daemon_offline()
        if self._daemon_connected:
            pid = self._daemon_status.get("pid", "?")
            last_schedule = self._daemon_status.get("last_schedule") or "never"
            last_sync = self._daemon_status.get("last_calendar_sync") or "never"
            status_line.update(f"Daemon: connected pid={pid} | schedule={last_schedule} | calendar={last_sync}")
        else:
            status_line.update("Daemon: offline | local reads enabled | schedule mutations disabled")

    def _refresh_dashboard(self) -> None:
        score = self._load_score()
        score_ring = self.query_one("#score-ring", ScoreRing)
        score_ring.update_score(score.get("score", 0))

        stats = self.query_one("#stats-box", Static)
        done = score.get("done", 0)
        total = score.get("total", 0)
        streak = score.get("streak", 0)
        completion = score.get("task_completion", 0)
        time_use = score.get("time_utilization", 0)

        sc = "green" if score.get("score", 0) >= 70 else "yellow" if score.get("score", 0) >= 40 else "red"

        stats.update(
            f"[bold]Tasks:[/] [{sc}]{done}/{total}[/]\n"
            f"[bold]Streak:[/] {streak}d\n"
            f"[bold]Completion:[/] {completion:.1f}/40\n"
            f"[bold]Time Use:[/] {time_use:.1f}/30"
        )

        next_task = self._load_next()
        next_box = self.query_one("#next-box", Static)
        if next_task:
            n = f"{next_task.get('emoji', '')} {next_task.get('name', '')}"
            s = next_task.get("scheduled_start", "--:--")
            e = next_task.get("scheduled_end", "--:--")
            blocked = " [red][blocked][/]" if next_task.get("is_blocked") else ""
            next_box.update(f"[bold]Do This Next[/]\n[yellow]{n}[/]{blocked}\n[dim]{s} - {e}[/]")
        else:
            next_box.update("[bold]Do This Next[/]\n[green]All clear for now[/]")

        model = load_life_model()
        blocks = get_available_hours(model, calendar_events=self._calendar_events) if model else []
        hour_bar = self.query_one("#hour-bar", HourBar)
        hour_bar.update_blocks(blocks)

        schedule_table = self.query_one("#schedule-table", TaskTable)
        schedule_table.set_tasks(self._load_tasks())

    def _refresh_tasks(self) -> None:
        table = self.query_one("#tasks-table", TaskTable)
        table.set_tasks(self._load_tasks())

    def _refresh_schedule(self) -> None:
        timeline = self.query_one("#schedule-timeline", TimelineTable)
        dep_chain = self.query_one("#dep-chain", DependencyChain)
        tasks = self._load_tasks()
        timeline.set_tasks(tasks)
        dep_chain.update_tasks(tasks)

    def _refresh_history(self) -> None:
        table = self.query_one("#history-table", DataTable)
        table.clear(columns=False)

        conn = get_connection()
        history = get_history(conn, days=14)
        conn.close()

        for h in history:
            score_val = float(h.get("score", 0))
            color = "green" if score_val >= 70 else "yellow" if score_val >= 40 else "red"
            table.add_row(
                str(h.get("date", "")),
                f"[{color}]{score_val:.0f}[/]",
                f"{h.get('task_completion', 0):.1f}",
                f"{h.get('time_utilization', 0):.1f}",
                f"{h.get('goal_alignment', 0):.1f}",
                f"{h.get('consistency_bonus', 0):.1f}",
            )

        box = self.query_one("#history-box", Static)
        today_score = self._load_score().get("score", 0)
        sc = "green" if today_score >= 70 else "yellow" if today_score >= 40 else "red"
        box.update(f"[bold]Today:[/] [{sc}]{today_score:.0f}[/]  |  [dim]Last {len(history)} day(s)[/]")

    def _load_tasks(self) -> list[dict[str, Any]]:
        if self._daemon_connected:
            try:
                return daemon_get_tasks()
            except Exception:
                self._set_daemon_offline()
        conn = get_connection()
        try:
            return get_todays_tasks(conn)
        finally:
            conn.close()

    def _load_score(self) -> dict[str, Any]:
        if self._daemon_connected:
            try:
                return daemon_get_score()
            except Exception:
                self._set_daemon_offline()
        return calculate_score()

    def _load_next(self) -> dict[str, Any] | None:
        if self._daemon_connected:
            try:
                return daemon_get_next()
            except Exception:
                self._set_daemon_offline()
        return get_next_action()

    def _set_daemon_offline(self) -> None:
        self._daemon_connected = False
        self._daemon_status = {}

    def _current_task_table(self) -> TaskTable | None:
        focused = self.focused
        if isinstance(focused, TaskTable):
            return focused

        active_tab = self.query_one(TabbedContent).active
        if active_tab == "tab-dashboard":
            return self.query_one("#schedule-table", TaskTable)
        if active_tab == "tab-tasks":
            return self.query_one("#tasks-table", TaskTable)
        if active_tab == "tab-schedule":
            return self.query_one("#schedule-timeline", TaskTable)
        return None


def run_tui() -> None:
    app = SelfHealApp()
    app.run()
