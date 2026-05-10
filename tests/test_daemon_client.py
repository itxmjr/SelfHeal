from __future__ import annotations

import json

import pytest

from selfheal.daemon import client
from selfheal.errors import DaemonError


class FakeSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = b""
        self.connected_to = None
        self.timeout = None
        self.closed = False

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect(self, path):
        self.connected_to = path

    def sendall(self, payload):
        self.sent += payload

    def recv(self, size):
        if self.chunks:
            return self.chunks.pop(0)
        return b""

    def close(self):
        self.closed = True


def test_daemon_send_cmd_sends_newline_json_and_reads_chunked_response(monkeypatch):
    payload = json.dumps({"ok": True, "data": {"value": 1}}).encode()
    sock = FakeSocket([payload[:10], payload[10:]])
    monkeypatch.setattr(client.socket, "socket", lambda *args: sock)

    result = client.daemon_send_cmd("add_task", name="Read")

    assert result == {"ok": True, "data": {"value": 1}}
    assert json.loads(sock.sent.decode()) == {"cmd": "add_task", "name": "Read"}
    assert sock.sent.endswith(b"\n")
    assert sock.closed is True


def test_daemon_send_cmd_raises_on_error_response(monkeypatch):
    sock = FakeSocket([b'{"ok": false, "error": "boom"}'])
    monkeypatch.setattr(client.socket, "socket", lambda *args: sock)

    with pytest.raises(DaemonError, match="boom"):
        client.daemon_send_cmd("missing")


def test_daemon_send_preserves_legacy_error_dict(monkeypatch):
    monkeypatch.setattr(client, "daemon_send_cmd", lambda *args, **kwargs: (_ for _ in ()).throw(DaemonError("offline")))

    assert client.daemon_send("status") == {"ok": False, "error": "offline"}


def test_new_client_wrappers_call_expected_commands(monkeypatch):
    calls = []

    def fake_send(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd == "add_task":
            return {"ok": True, "data": {"task_id": 42}}
        if cmd == "generate_schedule":
            return {"ok": True, "data": [{"name": "Task"}]}
        if cmd == "toggle_task":
            return {"ok": True, "data": {"id": kwargs["task_id"], "status": "done"}}
        return {"ok": True, "data": {"command": cmd}}

    monkeypatch.setattr(client, "daemon_send_cmd", fake_send)

    assert client.daemon_sync_clickup() == {"command": "sync_clickup"}
    assert client.daemon_sync_all() == {"command": "sync_all"}
    assert client.daemon_add_task("Read", priority="high", estimated_minutes=20) == 42
    assert client.daemon_generate_schedule("2026-05-04") == [{"name": "Task"}]
    assert client.daemon_toggle_task(7) == {"id": 7, "status": "done"}

    assert calls == [
        ("sync_clickup", {}),
        ("sync_all", {}),
        ("add_task", {"name": "Read", "priority": "high", "emoji": "", "estimated_minutes": 20, "schedule": "daily"}),
        ("generate_schedule", {"date": "2026-05-04"}),
        ("toggle_task", {"task_id": 7}),
    ]
