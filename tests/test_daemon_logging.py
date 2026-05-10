import logging
from unittest.mock import patch

from selfheal.daemon.service import DaemonServer
from selfheal.daemon.tasks import notify, sync


def test_update_wallpaper_task_logs_failures(caplog):
    with patch.dict("sys.modules", {"selfheal.wallpaper": None}):
        with caplog.at_level(logging.ERROR):
            sync.update_wallpaper_task()

    assert "Wallpaper update task failed" in caplog.text


def test_obsidian_sync_task_logs_failures(caplog):
    with patch.dict("sys.modules", {"selfheal.obsidian": None}):
        with caplog.at_level(logging.ERROR):
            sync.obsidian_sync_task()

    assert "Obsidian sync task failed" in caplog.text


def test_send_notification_logs_failures(caplog):
    with patch("selfheal.daemon.tasks.notify.subprocess.run", side_effect=OSError("missing notify-send")):
        with caplog.at_level(logging.ERROR):
            notify.send_notification("title", "body")

    assert "Failed to send desktop notification" in caplog.text


def test_daemon_task_wrapper_logs_failures(caplog):
    server = DaemonServer()

    def failing_task():
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        server._run_daemon_task("test task", failing_task)

    assert "Daemon task failed: test task" in caplog.text
