from __future__ import annotations
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalSubscript=false, reportIncompatibleMethodOverride=false

import json
import socket
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from selfheal.calendar import Provider
from selfheal.calendar import providers
from selfheal.config import DEFAULT_CONFIG
from selfheal.daemon import client
from selfheal.daemon.tasks import notify
from selfheal.errors import DaemonError
from selfheal.tui import app as tui_app
from selfheal.tui.app import SelfHealApp
from selfheal.tui.widgets import DependencyChain, HourBar, ScoreRing, TaskTable, TimelineTable


class Closeable:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeStatusLine:
    def __init__(self):
        self.values = []

    def update(self, value):
        self.values.append(value)


class FakeTable:
    def __init__(self):
        self.rows = []
        self.cleared = False

    def add_columns(self, *args):
        self.columns = args

    def clear(self, columns=False):
        self.cleared = True

    def add_row(self, *args, **kwargs):
        self.rows.append(args)

    def set_tasks(self, tasks):
        self.tasks = tasks


class FakeScoreRing:
    def update_score(self, score):
        self.score = score


class FakeStatic:
    def __init__(self):
        self.values = []

    def update(self, value):
        self.values.append(value)


class FakeHourBar:
    def update_blocks(self, blocks):
        self.blocks = blocks


class FakeDepChain:
    def update_tasks(self, tasks):
        self.tasks = tasks


def test_calendar_provider_dispatch_and_create_branches(monkeypatch):
    status = {'google': True, 'google_credentials': True, 'google_token': True, 'caldav': True, 'clickup': True}
    monkeypatch.setattr(providers, 'is_google_authenticated', lambda: status['google'])
    monkeypatch.setattr(providers, 'is_caldav_configured', lambda: status['caldav'])
    monkeypatch.setattr(providers, 'is_clickup_configured', lambda: status['clickup'])
    monkeypatch.setattr(providers, 'GOOGLE_CREDENTIALS_PATH', SimpleNamespace(exists=lambda: status['google_credentials']))
    monkeypatch.setattr(providers, 'GOOGLE_TOKEN_PATH', SimpleNamespace(exists=lambda: status['google_token']))
    assert providers.check_auth_status() == status

    calls = []
    monkeypatch.setattr(providers, 'list_google_events', lambda start, end: calls.append('google') or [{'provider': 'google'}])
    monkeypatch.setattr(providers, 'list_caldav_events', lambda start, end: calls.append('caldav') or [{'provider': 'caldav'}])
    monkeypatch.setattr(providers, 'list_clickup_events', lambda start, end: calls.append('clickup') or [{'provider': 'clickup'}])
    assert providers.list_calendar_events(Provider.GOOGLE, date.today(), date.today()) == [{'provider': 'google'}]
    assert providers.list_calendar_events(Provider.CALDAV, date.today(), date.today()) == [{'provider': 'caldav'}]
    assert providers.list_calendar_events(Provider.CLICKUP, date.today(), date.today()) == [{'provider': 'clickup'}]
    with pytest.raises(ValueError):
        providers.list_calendar_events('bad', date.today(), date.today())

    status['google'] = False
    with pytest.raises(RuntimeError, match='Google'):
        providers.list_calendar_events(Provider.GOOGLE, date.today(), date.today())
    status['google'] = True
    status['caldav'] = False
    with pytest.raises(RuntimeError, match='CalDAV'):
        providers.list_calendar_events(Provider.CALDAV, date.today(), date.today())
    status['caldav'] = True
    status['clickup'] = False
    with pytest.raises(RuntimeError, match='ClickUp'):
        providers.list_calendar_events(Provider.CLICKUP, date.today(), date.today())
    status['clickup'] = True

    created = []
    monkeypatch.setattr(providers, 'create_google_event', lambda summary, start, end, description=None: created.append(('google', summary, description)) or {'id': 'g'})
    monkeypatch.setattr(providers, 'create_caldav_event', lambda summary, start, end, description=None: created.append(('caldav', summary, description)) or {'id': 'c'})
    now = datetime(2026, 5, 4, 9)
    assert providers.create_calendar_event(Provider.GOOGLE, 'G', now, now, 'desc') == {'id': 'g'}
    assert providers.create_calendar_event(Provider.CALDAV, 'C', now, now) == {'id': 'c'}
    with pytest.raises(ValueError):
        providers.create_calendar_event(Provider.CLICKUP, 'X', now, now)


def test_config_env_overrides_and_life_model_io(monkeypatch, tmp_path):
    from selfheal import config

    cfg_dir = tmp_path / 'config'
    monkeypatch.setenv('SELFHEAL_CONFIG', str(cfg_dir))
    monkeypatch.setenv('SELFHEAL_LLM_PROVIDER', 'ollama')
    monkeypatch.setenv('SELFHEAL_NIM_API_KEY', 'nim-key')
    monkeypatch.setenv('SELFHEAL_NIM_MODEL', 'nim-model')
    monkeypatch.setenv('SELFHEAL_NIM_BASE_URL', 'https://nim')
    monkeypatch.setenv('SELFHEAL_OLLAMA_MODEL', 'ollama-model')
    monkeypatch.setenv('SELFHEAL_OLLAMA_BASE_URL', 'http://ollama')
    monkeypatch.setenv('SELFHEAL_OBSIDIAN_VAULT_PATH', '/vault')
    monkeypatch.setenv('SELFHEAL_CLICKUP_LIST_ID', 'list')
    monkeypatch.setenv('SELFHEAL_WALLPAPER_ENABLED', 'no')
    monkeypatch.setenv('SELFHEAL_WALLPAPER_INTERVAL', 'bad')

    cfg_dir.mkdir(parents=True)
    cfg = config.load_config()
    assert cfg['llm']['provider'] == 'ollama'
    assert cfg['llm']['nim']['api_key'] == 'nim-key'
    assert cfg['llm']['ollama']['model'] == 'ollama-model'
    assert cfg['obsidian']['vault_path'] == '/vault'
    assert cfg['clickup']['list_id'] == 'list'
    assert cfg['wallpaper']['enabled'] is False

    saved = DEFAULT_CONFIG.copy()
    saved['obsidian'] = {'vault_path': 'saved'}
    config.save_config(saved)
    loaded = config.load_config()
    assert loaded['obsidian']['vault_path'] == '/vault'
    assert config._deep_merge({'a': {'b': 1}, 'x': 1}, {'a': {'c': 2}}) == {'a': {'b': 1, 'c': 2}, 'x': 1}

    monkeypatch.setattr(config, 'LIFE_MODEL_PATH', cfg_dir / 'life_model.yaml')
    assert config.load_life_model() is None
    config.save_life_model({'sleep': {'wake': '07:00'}})
    assert config.load_life_model() == {'sleep': {'wake': '07:00'}}


def test_daemon_client_socket_edge_cases_and_wrappers(monkeypatch):
    original_send_cmd = client.daemon_send_cmd
    monkeypatch.setattr(client, 'daemon_send_cmd', lambda *args, **kwargs: {'ok': True, 'data': {'task_id': 5}})
    assert client.is_daemon_running() is True
    assert client.daemon_refresh() is True
    assert client.daemon_regenerate() is True
    assert client.daemon_add_task('Read') == 5
    monkeypatch.setattr(client, 'daemon_send_cmd', lambda *args, **kwargs: (_ for _ in ()).throw(DaemonError('offline')))
    assert client.is_daemon_running() is False

    class NoResponseSocket:
        def settimeout(self, timeout): pass
        def connect(self, path): pass
        def sendall(self, data): pass
        def recv(self, size): return b''
        def close(self): pass

    monkeypatch.setattr(client, 'daemon_send_cmd', original_send_cmd)
    monkeypatch.setattr(client.socket, 'socket', lambda *args, **kwargs: NoResponseSocket())
    with pytest.raises(DaemonError, match='no response'):
        client.daemon_send_cmd('ping')

    class MalformedSocket(NoResponseSocket):
        def __init__(self): self.done = False
        def recv(self, size):
            if not self.done:
                self.done = True
                return b'{"data": 1}'
            return b''

    monkeypatch.setattr(client.socket, 'socket', lambda *args, **kwargs: MalformedSocket())
    with pytest.raises(DaemonError, match='malformed'):
        client.daemon_send_cmd('ping')

    class OSErrorSocket(NoResponseSocket):
        def connect(self, path):
            raise OSError('missing')

    monkeypatch.setattr(client.socket, 'socket', lambda *args, **kwargs: OSErrorSocket())
    with pytest.raises(DaemonError, match='connection failed'):
        client.daemon_send_cmd('ping')


def test_notify_tasks(monkeypatch):
    sent = []
    monkeypatch.setattr(notify.subprocess, 'run', lambda cmd, capture_output=True: sent.append(cmd))
    notify.send_notification('Title', 'Body')
    assert sent[0][:3] == ['notify-send', '--app-name=SelfHeal', '--urgency=normal']

    conn = Closeable()
    monkeypatch.setattr(notify, 'get_connection', lambda: conn)
    monkeypatch.setattr(notify, 'datetime', SimpleNamespace(now=lambda: datetime(2026, 5, 4, 12, 0, 0)))
    notices = []
    monkeypatch.setattr(notify, 'send_notification', lambda title, body: notices.append((title, body)))
    monkeypatch.setattr(
        notify,
        'get_todays_tasks',
        lambda connection: [
            {'name': 'Old', 'emoji': 'O', 'status': 'pending', 'scheduled_start': '09:00'},
            {'name': 'Done', 'status': 'done', 'scheduled_start': '08:00'},
            {'name': 'Blocked', 'status': 'pending', 'is_blocked': True, 'scheduled_start': '07:00'},
            {'name': 'Bad', 'status': 'pending', 'scheduled_start': 'bad'},
        ],
    )
    notify.check_overdue_tasks()
    assert notices[0][0] == 'SelfHeal — Overdue Tasks'
    assert 'Old' in notices[0][1]
    assert conn.closed is True

    conn2 = Closeable()
    monkeypatch.setattr(notify, 'get_connection', lambda: conn2)
    monkeypatch.setattr(notify, 'get_todays_tasks', lambda connection: [{'name': 'Start', 'emoji': 'S', 'scheduled_start': '13:00'}])
    notices.clear()
    notify.check_task_transitions(datetime(2026, 5, 4, 13, 1, 0))
    assert notices == []
    notify.check_task_transitions(datetime(2026, 5, 4, 13, 1, 0), force=True)
    assert notices[0][0] == 'Time for: S Start'


def test_tui_refresh_load_and_mount_branches(monkeypatch, temp_db):
    app = object.__new__(SelfHealApp)
    app._daemon_connected = True
    app._daemon_status = {'pid': 1, 'last_schedule': 'today', 'last_calendar_sync': 'now'}
    app._calendar_events = []
    app.notifications = []
    app.notify = lambda message, **kwargs: app.notifications.append((message, kwargs))

    widgets = {
        '#daemon-status': FakeStatusLine(),
        '#score-ring': FakeScoreRing(),
        '#stats-box': FakeStatic(),
        '#next-box': FakeStatic(),
        '#hour-bar': FakeHourBar(),
        '#schedule-table': FakeTable(),
        '#tasks-table': FakeTable(),
        '#schedule-timeline': FakeTable(),
        '#dep-chain': FakeDepChain(),
        '#history-table': FakeTable(),
        '#history-box': FakeStatic(),
    }
    app.query_one = lambda selector, cls=None: widgets[selector] if isinstance(selector, str) else SimpleNamespace(active='tab-dashboard')
    tasks = [{'id': 1, 'name': 'Read', 'scheduled_start': '09:00'}]
    monkeypatch.setattr(tui_app, 'daemon_get_status', lambda: app._daemon_status)
    monkeypatch.setattr(tui_app, 'daemon_get_tasks', lambda: tasks)
    monkeypatch.setattr(tui_app, 'daemon_get_score', lambda: {'score': 75, 'done': 1, 'total': 2, 'streak': 3, 'task_completion': 20, 'time_utilization': 10})
    monkeypatch.setattr(tui_app, 'daemon_get_next', lambda: {'emoji': 'R', 'name': 'Read', 'scheduled_start': '09:00', 'scheduled_end': '10:00'})
    monkeypatch.setattr(tui_app, 'load_life_model', lambda: {'sleep': {'wake': '07:00', 'bed': '09:00'}})
    monkeypatch.setattr(tui_app, 'get_available_hours', lambda model, calendar_events=None: [{'hour': 7, 'status': 'free'}])
    monkeypatch.setattr(tui_app, 'get_connection', lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(tui_app, 'get_history', lambda conn, days=14: [{'date': '2026-05-04', 'score': 75, 'task_completion': 10, 'time_utilization': 8, 'goal_alignment': 6, 'consistency_bonus': 4}])

    SelfHealApp.refresh_all(app)
    assert widgets['#daemon-status'].values[-1].startswith('Daemon: connected')
    assert widgets['#score-ring'].score == 75
    assert widgets['#schedule-table'].tasks == tasks
    assert widgets['#history-table'].rows

    monkeypatch.setattr(tui_app, 'daemon_get_tasks', lambda: (_ for _ in ()).throw(RuntimeError('down')))
    monkeypatch.setattr(tui_app, 'get_todays_tasks', lambda conn: [{'id': 2, 'name': 'Local'}])
    app._daemon_connected = True
    assert SelfHealApp._load_tasks(app) == [{'id': 2, 'name': 'Local'}]
    assert app._daemon_connected is False

    app._daemon_connected = True
    monkeypatch.setattr(tui_app, 'daemon_get_score', lambda: (_ for _ in ()).throw(RuntimeError('down')))
    monkeypatch.setattr(tui_app, 'calculate_score', lambda: {'score': 10})
    assert SelfHealApp._load_score(app) == {'score': 10}

    app._daemon_connected = True
    monkeypatch.setattr(tui_app, 'daemon_get_next', lambda: (_ for _ in ()).throw(RuntimeError('down')))
    monkeypatch.setattr(tui_app, 'get_next_action', lambda: {'name': 'Local Next'})
    assert SelfHealApp._load_next(app) == {'name': 'Local Next'}

    focused = TaskTable()
    monkeypatch.setattr(SelfHealApp, 'focused', property(lambda self: focused), raising=False)
    assert SelfHealApp._current_task_table(app) is focused
    monkeypatch.setattr(SelfHealApp, 'focused', property(lambda self: None), raising=False)
    app.query_one = lambda selector, cls=None: SimpleNamespace(active='tab-history') if not isinstance(selector, str) else widgets[selector]
    assert SelfHealApp._current_task_table(app) is None


def test_tui_on_mount_connected_and_offline(monkeypatch):
    app = object.__new__(SelfHealApp)
    app.notifications = []
    app.notify = lambda message, **kwargs: app.notifications.append((message, kwargs))
    app._sync_calendar = lambda: None
    app._load_tasks = lambda: []
    app.refresh_all = lambda: None
    app.set_timer = lambda seconds, callback: None
    app.query_one = lambda selector, cls=None: SimpleNamespace(add_columns=lambda *args: None)

    calls = []
    monkeypatch.setattr(tui_app, 'is_daemon_running', lambda: True)
    monkeypatch.setattr(tui_app, 'daemon_get_status', lambda: {'pid': 9})
    monkeypatch.setattr(tui_app, 'load_life_model', lambda: None)
    monkeypatch.setattr(tui_app, 'daemon_generate_schedule', lambda target: calls.append(target))
    SelfHealApp.on_mount(app)
    assert 'Daemon connected' in app.notifications[0][0]
    assert any('interview' in note[0] for note in app.notifications)

    app.notifications.clear()
    monkeypatch.setattr(tui_app, 'is_daemon_running', lambda: False)
    monkeypatch.setattr(tui_app, 'load_life_model', lambda: {'sleep': {}})
    SelfHealApp.on_mount(app)
    assert any('No schedule yet' in note[0] for note in app.notifications)
