from __future__ import annotations

import subprocess
import logging
from datetime import datetime

from ...db import get_connection, get_todays_tasks

logger = logging.getLogger(__name__)


def send_notification(title: str, body: str) -> None:
    """Send a system notification."""
    try:
        subprocess.run(
            ["notify-send", "--app-name=SelfHeal", "--urgency=normal", title, body],
            capture_output=True,
        )
    except Exception:
        logger.exception("Failed to send desktop notification")


def check_overdue_tasks() -> None:
    """Check for overdue tasks and notify."""
    conn = get_connection()
    tasks = get_todays_tasks(conn)
    now = datetime.now()
    current_hour = now.hour
    conn.close()

    overdue = []
    for t in tasks:
        if t.get("status") != "pending" or t.get("is_blocked"):
            continue
        start = t.get("scheduled_start")
        if start:
            try:
                sh = int(start.split(":")[0])
                if sh < current_hour:
                    overdue.append(f"{t.get('emoji', '')} {t.get('name', '')}")
            except ValueError:
                logger.warning("Skipping task with invalid scheduled_start: %s", start)

    if overdue:
        task_list = "\n".join(f"  - {t}" for t in overdue[:5])
        body = f"Overdue tasks:\n{task_list}"
        send_notification("SelfHeal — Overdue Tasks", body)


def check_task_transitions(now: datetime, force: bool = False) -> None:
    """Notify user when it's time to start a new task."""
    if not force and (now.minute != 0 or now.second > 10):
        return

    conn = get_connection()
    tasks = get_todays_tasks(conn)
    conn.close()

    current_hour = now.hour
    for t in tasks:
        start_str = t.get("scheduled_start")
        if start_str and start_str.startswith(f"{current_hour:02d}:00"):
            name = t.get("name", "Unknown Task")
            emoji = t.get("emoji", "🔔")
            send_notification(
                f"Time for: {emoji} {name}",
                f"Scheduled for {start_str}"
            )
