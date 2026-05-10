from . import client as _client
from .service import DaemonServer

daemon_add_task = _client.daemon_add_task
daemon_generate_schedule = _client.daemon_generate_schedule
daemon_get_next = _client.daemon_get_next
daemon_get_score = _client.daemon_get_score
daemon_get_status = _client.daemon_get_status
daemon_get_tasks = _client.daemon_get_tasks
daemon_mark_task_done = _client.daemon_mark_task_done
daemon_mark_task_pending = _client.daemon_mark_task_pending
daemon_refresh = _client.daemon_refresh
daemon_regenerate = _client.daemon_regenerate
daemon_send = _client.daemon_send
daemon_send_cmd = _client.daemon_send_cmd
daemon_stop = _client.daemon_stop
daemon_sync_all = _client.daemon_sync_all
daemon_sync_calendar = _client.daemon_sync_calendar
daemon_sync_clickup = _client.daemon_sync_clickup
daemon_sync_obsidian = _client.daemon_sync_obsidian
daemon_toggle_task = _client.daemon_toggle_task
is_daemon_running = _client.is_daemon_running

__all__ = [
    "DaemonServer",
    "daemon_add_task",
    "daemon_generate_schedule",
    "daemon_get_next",
    "daemon_get_score",
    "daemon_get_status",
    "daemon_get_tasks",
    "daemon_mark_task_done",
    "daemon_mark_task_pending",
    "daemon_refresh",
    "daemon_regenerate",
    "daemon_send",
    "daemon_send_cmd",
    "daemon_stop",
    "daemon_sync_all",
    "daemon_sync_calendar",
    "daemon_sync_clickup",
    "daemon_sync_obsidian",
    "daemon_toggle_task",
    "is_daemon_running",
]
