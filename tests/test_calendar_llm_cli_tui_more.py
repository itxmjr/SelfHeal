from __future__ import annotations
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalSubscript=false, reportGeneralTypeIssues=false

import json
import sys
import types
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
import typer

from selfheal import CalendarError, LLMError
from selfheal.calendar import Provider
from selfheal.calendar.providers import caldav, google
from selfheal.cli import calendar as cli_calendar
from selfheal.cli import daemon as cli_daemon
from selfheal.cli import main as cli_main
from selfheal.cli import tasks as cli_tasks
from selfheal.daemon import service
from selfheal.daemon.service import DaemonServer
from selfheal.llm.base import LLMResponse
from selfheal.llm.nim import NIMClient
from selfheal.llm.ollama import OllamaClient
from selfheal.tui import app as tui_app
from selfheal.tui.app import SelfHealApp
from selfheal.tui.screens.modals import AddTaskModal, ConfigModal, HelpModal, VisionImportModal
from selfheal.tui.widgets.hour_bar import HourBar
from selfheal.tui.widgets.score_ring import ScoreRing
from selfheal.tui.widgets.task_table import TaskTable
from selfheal.tui.widgets.timeline import DependencyChain, TimelineTable


class ConnectionProxy:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass


class Prints:
    def __init__(self):
        self.items = []

    def __call__(self, *args, **kwargs):
        self.items.append(' '.join(str(arg) for arg in args))

    @property
    def text(self):
        return '\n'.join(self.items)


class FakeResponse:
    def __init__(self, data=None, exc=None):
        self.data = data or {}
        self.exc = exc

    def raise_for_status(self):
        if self.exc:
            raise self.exc

    def json(self):
        return self.data


class FakeEvent:
    def __init__(self, button_id):
        self.button = SimpleNamespace(id=button_id)


class FakeInput:
    def __init__(self, value):
        self.value = value


class FakeSelect:
    def __init__(self, value):
        self.value = value


def _capture_cli(monkeypatch, module):
    prints = Prints()
    monkeypatch.setattr(module, '_ensure_init', lambda: None, raising=False)
    monkeypatch.setattr(module.console, 'print', prints)
    return prints


def test_google_token_auth_event_and_create_paths(monkeypatch, tmp_path):
    token_path = tmp_path / 'token.json'
    creds_path = tmp_path / 'credentials.json'
    monkeypatch.setattr(google, 'GOOGLE_TOKEN_PATH', token_path)
    monkeypatch.setattr(google, 'GOOGLE_CREDENTIALS_PATH', creds_path)

    assert google.load_google_token() is None
    assert google.is_google_authenticated() is False

    future = (datetime.now().astimezone() + timedelta(hours=1)).isoformat()
    google.save_google_token({'expiry': future, 'access_token': 'tok'})
    assert json.loads(token_path.read_text())['access_token'] == 'tok'
    assert google.load_google_token()['expiry'] == future
    assert google.is_google_authenticated() is True

    token_path.write_text(json.dumps({'expiry': (datetime.now().astimezone() - timedelta(minutes=1)).isoformat()}))
    assert google.is_google_authenticated() is False

    class Events:
        def list(self, **kwargs):
            self.list_kwargs = kwargs
            return 'list-request'

        def insert(self, **kwargs):
            self.insert_kwargs = kwargs
            return 'insert-request'

    class Service:
        def __init__(self):
            self.events_obj = Events()

        def events(self):
            return self.events_obj

    service_obj = Service()
    monkeypatch.setattr(google, 'get_google_calendar_service', lambda: service_obj)
    monkeypatch.setattr(
        google,
        '_execute_google_request',
        lambda request: {
            'list-request': {
                'items': [
                    {
                        'id': '1',
                        'summary': 'Meeting',
                        'start': {'dateTime': '2026-05-04T09:00:00'},
                        'end': {'dateTime': '2026-05-04T10:00:00'},
                        'location': 'Room',
                        'description': 'Discuss',
                    },
                    {
                        'id': '2',
                        'start': {'date': '2026-05-05'},
                        'end': {'date': '2026-05-06'},
                    },
                ]
            },
            'insert-request': {'id': 'new'},
        }[request],
    )

    events = google.list_google_events(date(2026, 5, 4), date(2026, 5, 6))
    assert events[0]['summary'] == 'Meeting'
    assert events[0]['all_day'] is False
    assert events[1]['summary'] == 'Untitled Event'
    assert events[1]['all_day'] is True
    created = google.create_google_event('Task', datetime(2026, 5, 4, 9), datetime(2026, 5, 4, 10), 'desc')
    assert created == {'id': 'new'}
    assert service_obj.events_obj.insert_kwargs['body']['summary'] == 'Task'


def test_google_request_wrappers_raise_domain_errors(monkeypatch):
    class BadRequest:
        def execute(self):
            raise RuntimeError('boom')

    monkeypatch.setattr('selfheal.retry.time.sleep', lambda seconds: None)
    with pytest.raises(CalendarError, match='Google Calendar request failed'):
        google._execute_google_request(BadRequest())


def test_caldav_config_list_and_create(monkeypatch):
    monkeypatch.delenv('SELFHEAL_CALDAV_URL', raising=False)
    assert caldav.is_caldav_configured() is False
    with pytest.raises(CalendarError, match='not configured'):
        caldav.get_caldav_client()

    monkeypatch.setenv('SELFHEAL_CALDAV_URL', 'https://dav.test')
    monkeypatch.setenv('SELFHEAL_CALDAV_USERNAME', 'user')
    monkeypatch.setenv('SELFHEAL_CALDAV_PASSWORD', 'pass')
    assert caldav.is_caldav_configured() is True

    saved = {}

    class Value:
        def __init__(self, value):
            self.value = value

    class VEvent:
        uid = Value('uid-1')
        summary = Value('Meeting')
        dtstart = Value(datetime(2026, 5, 4, 9))
        dtend = Value(datetime(2026, 5, 4, 10))
        location = Value('Room')
        description = Value('Desc')

    good = SimpleNamespace(instance=SimpleNamespace(vevent=VEvent()))
    bad = SimpleNamespace(instance=SimpleNamespace(vevent=object()))

    class Calendar:
        def date_search(self, start, end, expand=True):
            return [bad, good]

        def save_event(self, ical_str):
            saved['ical'] = ical_str
            return SimpleNamespace(url='event-url')

    class Principal:
        def calendars(self):
            return [Calendar()]

    class Client:
        def principal(self):
            return Principal()

    monkeypatch.setattr(caldav, 'get_caldav_client', lambda: Client())
    events = caldav.list_caldav_events(date(2026, 5, 4), date(2026, 5, 5))
    assert events == [
        {
            'id': 'uid-1',
            'summary': 'Meeting',
            'start': '2026-05-04T09:00:00',
            'end': '2026-05-04T10:00:00',
            'all_day': False,
            'location': 'Room',
            'description': 'Desc',
            'provider': 'caldav',
        }
    ]
    assert caldav.create_caldav_event('Task', datetime(2026, 5, 4, 9), datetime(2026, 5, 4, 10), 'line,one')['id'] == 'event-url'
    assert 'DESCRIPTION:line\\,one' in saved['ical']

    monkeypatch.setattr(caldav, '_get_calendars', lambda principal: [])
    assert caldav.list_caldav_events(date(2026, 5, 4), date(2026, 5, 5)) == []
    with pytest.raises(CalendarError, match='No CalDAV calendars'):
        caldav.create_caldav_event('Task', datetime(2026, 5, 4, 9), datetime(2026, 5, 4, 10))


def test_nim_and_ollama_chat_payloads_and_errors(monkeypatch):
    nim_calls = []
    monkeypatch.setattr(
        'selfheal.llm.nim._post_json',
        lambda url, headers, payload, timeout: nim_calls.append((url, headers, payload, timeout)) or {
            'choices': [{'message': {'content': 'hello'}}],
            'usage': {'prompt_tokens': 3, 'completion_tokens': 4},
        },
    )
    nim_client = NIMClient(api_key='key', model='nim-model', base_url='https://nim.test/')
    assert nim_client.chat([{'role': 'user', 'content': 'hi'}], temperature=0.2, max_tokens=99) == LLMResponse('hello', 'nim-model', 3, 4)
    assert nim_calls[0][0] == 'https://nim.test/chat/completions'
    assert nim_calls[0][1]['Authorization'] == 'Bearer key'
    assert nim_calls[0][2]['max_tokens'] == 99

    nim_calls.clear()
    monkeypatch.setattr('selfheal.llm.nim._post_json', lambda *args: nim_calls.append(args) or {'choices': [{'message': {'content': 'vision'}}]})
    assert nim_client.vision('see', 'abc').content == 'vision'
    assert nim_calls[0][2]['messages'][0]['content'][1]['image_url']['url'] == 'data:image/png;base64,abc'

    ollama_calls = []
    monkeypatch.setattr(
        'selfheal.llm.ollama._post_json',
        lambda url, payload, timeout: ollama_calls.append((url, payload, timeout)) or {
            'message': {'content': 'local'},
            'prompt_eval_count': 5,
            'eval_count': 6,
        },
    )
    ollama_client = OllamaClient(model='chat-model', base_url='http://ollama.test/')
    assert ollama_client.chat([{'role': 'user', 'content': 'hi'}], temperature=0.1, max_tokens=10) == LLMResponse('local', 'chat-model', 5, 6)
    assert ollama_calls[0][1]['options'] == {'temperature': 0.1, 'num_predict': 10}


def test_cli_main_interview_sync_vision_and_import(monkeypatch, tmp_path, temp_db):
    prints = _capture_cli(monkeypatch, cli_main)
    monkeypatch.setattr(cli_main, 'load_life_model', lambda: None)
    monkeypatch.setattr(cli_main, 'run_tui', lambda: (_ for _ in ()).throw(AssertionError('no tui')))
    cli_main.main(SimpleNamespace(invoked_subcommand=None))
    assert prints.items

    called = []
    monkeypatch.setattr(cli_main, 'load_life_model', lambda: {'sleep': {}})
    monkeypatch.setattr(cli_main, 'run_tui', lambda: called.append('tui'))
    cli_main.main(SimpleNamespace(invoked_subcommand=None))
    assert called == ['tui']

    interviews = []
    monkeypatch.setattr(cli_main, 'run_interview', lambda regenerate: interviews.append(regenerate))
    cli_main.interview()
    assert interviews == [True]

    calendar_calls = []
    monkeypatch.setattr(cli_main, 'check_auth_status', lambda: {'caldav': True, 'google': True})
    monkeypatch.setattr(cli_main, 'list_calendar_events', lambda provider, start, end: calendar_calls.append(provider) or [{'id': 1}])
    monkeypatch.setattr(cli_main, 'sync_to_obsidian', lambda: True)
    monkeypatch.setattr(cli_main, 'update_wallpaper_data', lambda: called.append('wallpaper'))
    cli_main.sync_cmd()
    assert calendar_calls == [Provider.CALDAV]
    assert 'Obsidian sync complete' in prints.text

    img = tmp_path / 'tasks.png'
    img.write_bytes(b'image')
    class Client:
        def vision(self, prompt, image_b64):
            return SimpleNamespace(content='noise [{"name":"Photo Task","emoji":"P","priority":"high","estimated_minutes":12}]')
    monkeypatch.setattr(cli_main, 'get_llm_client', lambda: Client())
    monkeypatch.setattr(cli_main, 'get_connection', lambda: ConnectionProxy(temp_db))
    cli_main.vision_cmd(str(img))
    assert 'Successfully imported 1 tasks from image' in prints.text

    with pytest.raises(typer.Exit):
        cli_main.vision_cmd(str(tmp_path / 'missing.png'))

    home = tmp_path / 'home'
    conf = home / '.config' / 'mjr'
    conf.mkdir(parents=True)
    (conf / 'tasks.conf').write_text('# comment\ndaily | E | Existing\nweekly|W|Write\n')
    monkeypatch.setattr(cli_main.Path, 'home', lambda: home)
    cli_main.import_mjr()
    assert 'Imported 2 tasks from mjr' in prints.text


def test_cli_task_commands(monkeypatch, temp_db):
    prints = _capture_cli(monkeypatch, cli_tasks)
    monkeypatch.setattr(cli_tasks, 'load_life_model', lambda: None)
    with pytest.raises(typer.Exit):
        cli_tasks.today()
    with pytest.raises(typer.Exit):
        cli_tasks.next_action()

    monkeypatch.setattr(cli_tasks, 'load_life_model', lambda: {'sleep': {}})
    monkeypatch.setattr(cli_tasks, 'generate_and_persist_schedule', lambda **kwargs: [])
    with pytest.raises(typer.Exit):
        cli_tasks.today()

    monkeypatch.setattr(cli_tasks, 'generate_and_persist_schedule', lambda **kwargs: [{'start_hour': 9, 'end_hour': 10, 'emoji': 'R', 'name': 'Read', 'priority': 'high', 'status': 'done'}])
    monkeypatch.setattr(cli_tasks, 'calculate_score', lambda: {'score': 82, 'done': 1, 'total': 1, 'streak': 2, 'task_completion': 40, 'time_utilization': 20, 'goal_alignment': 15, 'consistency_bonus': 7})
    cli_tasks.today()
    assert prints.items

    monkeypatch.setattr(cli_tasks, 'get_next_action', lambda: None)
    with pytest.raises(typer.Exit):
        cli_tasks.next_action()
    monkeypatch.setattr(cli_tasks, 'get_next_action', lambda: {'emoji': 'N', 'name': 'Next', 'priority': 'medium', 'scheduled_start': '09:00', 'scheduled_end': '10:00'})
    cli_tasks.next_action()
    assert prints.items

    monkeypatch.setattr(cli_tasks, 'get_connection', lambda: ConnectionProxy(temp_db))
    cli_tasks.add_task('Read', priority='high', emoji='R', minutes=15)
    cli_tasks.mark_done('Read')
    cli_tasks.toggle(1)
    cli_tasks.score()
    with pytest.raises(typer.Exit):
        cli_tasks.mark_done('Missing')
    with pytest.raises(typer.Exit):
        cli_tasks.toggle(999)


def test_cli_calendar_and_daemon_commands(monkeypatch, temp_db, tmp_path):
    prints = _capture_cli(monkeypatch, cli_calendar)
    monkeypatch.setattr(cli_calendar, 'GOOGLE_CREDENTIALS_PATH', tmp_path / 'missing-google-credentials.json')
    with pytest.raises(typer.Exit):
        cli_calendar.calendar_auth()

    credentials = tmp_path / 'google-credentials.json'
    credentials.write_text('{}')
    flow_calls = []

    class FakeCredentials:
        def to_json(self):
            return '{"token":"saved"}'

    class FakeFlow:
        credentials = FakeCredentials()

        def fetch_token(self, code):
            flow_calls.append(('fetch', code))

    def fake_from_client_secrets_file(path, scopes=None):
        flow_calls.append((path, scopes))
        return FakeFlow()

    fake_flow_module = types.SimpleNamespace(Flow=types.SimpleNamespace(from_client_secrets_file=fake_from_client_secrets_file))
    monkeypatch.setitem(sys.modules, 'google_auth_oauthlib', types.SimpleNamespace(flow=fake_flow_module))
    monkeypatch.setitem(sys.modules, 'google_auth_oauthlib.flow', fake_flow_module)
    monkeypatch.setattr(cli_calendar, 'GOOGLE_CREDENTIALS_PATH', credentials)
    monkeypatch.setattr(cli_calendar, 'get_google_auth_url', lambda: 'https://auth.test')
    monkeypatch.setattr(cli_calendar.typer, 'prompt', lambda message: 'code-123')
    saved_tokens = []
    monkeypatch.setattr(cli_calendar, 'save_google_token', lambda token: saved_tokens.append(token))

    cli_calendar.calendar_auth()

    assert flow_calls[0] == (str(credentials), cli_calendar.GOOGLE_CALENDAR_SCOPES)
    assert flow_calls[1] == ('fetch', 'code-123')
    assert saved_tokens == [{'token': 'saved'}]

    monkeypatch.setattr(cli_calendar, 'check_auth_status', lambda: {'google': True, 'google_credentials': True, 'google_token': True, 'caldav': False})
    cli_calendar.calendar_status()
    assert prints.items

    monkeypatch.setattr(cli_calendar, 'list_calendar_events', lambda provider, start, end: [])
    cli_calendar.calendar_sync(provider='google', days=1)
    monkeypatch.setattr(cli_calendar, 'list_calendar_events', lambda provider, start, end: [{'start': '2026-05-04T09:00:00', 'end': '2026-05-04T10:00:00', 'summary': 'Meet', 'all_day': False, 'location': 'Room'}])
    cli_calendar.calendar_sync(provider='google', days=1)
    monkeypatch.setattr(cli_calendar, 'list_calendar_events', lambda provider, start, end: (_ for _ in ()).throw(RuntimeError('bad')))
    with pytest.raises(typer.Exit):
        cli_calendar.calendar_sync(provider='google', days=1)

    monkeypatch.setattr(cli_calendar, 'load_life_model', lambda: None)
    with pytest.raises(typer.Exit):
        cli_calendar.calendar_push(provider='google', day_offset=0)
    monkeypatch.setattr(cli_calendar, 'load_life_model', lambda: {'sleep': {}})
    monkeypatch.setattr(cli_calendar, 'get_connection', lambda: ConnectionProxy(temp_db))
    from selfheal.db import upsert_task
    task_id = upsert_task(temp_db, name='Push', emoji='P')
    temp_db.execute("INSERT INTO daily_logs (date, task_id, status, scheduled_start, scheduled_end) VALUES (?, ?, 'pending', '09:00', '10:00')", (date.today().isoformat(), task_id))
    created = []
    monkeypatch.setattr(cli_calendar, 'create_calendar_event', lambda provider, **kwargs: created.append(kwargs) or {'id': 'event'})
    cli_calendar.calendar_push(provider='google', day_offset=0)
    assert created[0]['summary'] == 'P Push'

    daemon_prints = _capture_cli(monkeypatch, cli_daemon)
    monkeypatch.setattr(cli_daemon, 'is_daemon_running', lambda: False)
    cli_daemon.daemon_stop_cmd()
    cli_daemon.daemon_status()
    monkeypatch.setattr(cli_daemon, 'is_daemon_running', lambda: True)
    monkeypatch.setattr(cli_daemon, 'daemon_get_status', lambda: {'pid': 123, 'socket': 'sock', 'uptime': '1s'})
    cli_daemon.daemon_status()
    monkeypatch.setattr(cli_daemon, 'daemon_stop', lambda: True)
    cli_daemon.daemon_stop_cmd()
    assert 'Daemon stopped' in daemon_prints.text

    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr('shutil.which', lambda name: '/tmp/bin/selfheal')
    systemctl_calls = []
    monkeypatch.setattr('subprocess.run', lambda args, check: systemctl_calls.append(args))
    cli_daemon.daemon_install()
    installed_service = tmp_path / '.config' / 'systemd' / 'user' / 'selfheal-daemon.service'
    installed_target = tmp_path / '.config' / 'systemd' / 'user' / 'selfheal.target'
    assert 'ExecStart=/tmp/bin/selfheal daemon serve' in installed_service.read_text()
    assert installed_target.exists()
    assert systemctl_calls[-1] == ['systemctl', '--user', 'start', 'selfheal-daemon.service']


def test_daemon_service_remaining_command_and_task_branches(monkeypatch, temp_db):
    monkeypatch.setattr(service, 'get_connection', lambda: ConnectionProxy(temp_db))
    server = DaemonServer()

    assert server._process_command({'cmd': 'ping'})['ok'] is True
    assert server._process_command({'cmd': 'unknown'})['ok'] is False
    assert server._process_command({'cmd': 'add_task', 'name': ''})['ok'] is False
    assert server._process_command({'cmd': 'quit'})['data'] == 'stopping'

    calls = []
    monkeypatch.setattr(service, 'sync_clickup_task', lambda: calls.append('clickup') or {'count': 1})
    monkeypatch.setattr(service, 'sync_calendar_task', lambda: calls.append('calendar') or {'events': []})
    monkeypatch.setattr(service, 'obsidian_sync_task', lambda: calls.append('obsidian') or {'success': True})
    monkeypatch.setattr(service, 'sync_all_task', lambda: calls.append('all') or {'calendar': {}})
    assert server._process_command({'cmd': 'sync_clickup'})['data'] == {'count': 1}
    assert server._process_command({'cmd': 'sync_calendar'})['data'] == {'events': []}
    assert server._process_command({'cmd': 'sync_obsidian'})['data'] == {'success': True}
    assert server._process_command({'cmd': 'sync_all'})['data'] == {'calendar': {}}

    monkeypatch.setattr(service, 'calculate_score', lambda: {'score': 50})
    monkeypatch.setattr('selfheal.engine.scheduler.get_next_action', lambda: {'name': 'Next'})
    assert server._process_command({'cmd': 'get_score'})['data'] == {'score': 50}
    assert server._process_command({'cmd': 'get_next'})['data'] == {'name': 'Next'}

    ran = []
    now = datetime.now()
    monkeypatch.setattr(service, 'load_life_model', lambda: {'sleep': {}})
    monkeypatch.setattr(server, '_check_morning_generation', lambda *args: ran.append('morning'))
    monkeypatch.setattr(server, '_check_notify', lambda *args: ran.append('notify'))
    monkeypatch.setattr(server, '_check_calendar_sync', lambda *args: ran.append('calendar'))
    monkeypatch.setattr(server, '_check_clickup_sync', lambda *args: ran.append('clickup'))
    monkeypatch.setattr(server, '_check_wallpaper_update', lambda *args: ran.append('wallpaper'))
    monkeypatch.setattr(server, '_check_score_save', lambda *args: ran.append('score'))
    monkeypatch.setattr(server, '_check_obsidian_sync', lambda *args: ran.append('obsidian'))
    monkeypatch.setattr(server, '_check_task_transitions', lambda *args: ran.append('transitions'))
    server._run_background_tasks(force=True)
    assert ran == ['morning', 'notify', 'calendar', 'clickup', 'wallpaper', 'score', 'obsidian', 'transitions']

    checks = []
    server2 = DaemonServer()
    monkeypatch.setattr(service, 'generate_schedule_task', lambda target_date=None: checks.append(('schedule', target_date)))
    server2._check_morning_generation({'sleep': {}}, now.replace(hour=7), True)
    monkeypatch.setattr(service, 'check_overdue_tasks', lambda: checks.append(('overdue', None)))
    server2._check_notify({'sleep': {}}, now, True)
    monkeypatch.setattr(service, 'update_wallpaper_task', lambda: checks.append(('wallpaper', None)))
    server2._check_wallpaper_update(None, now, True)
    monkeypatch.setattr(service, 'check_task_transitions', lambda now_arg, force: checks.append(('transitions', force)))
    server2._check_task_transitions(None, now, True)
    assert ('overdue', None) in checks
    assert ('wallpaper', None) in checks
    assert ('transitions', True) in checks


def test_tui_widgets_modals_and_app_branches(monkeypatch, temp_db, tmp_path):
    score = ScoreRing()
    score.refresh = lambda: None
    score.update_score(110)
    assert '100/100' in str(score.render())
    score.update_score(35)
    assert 'Needs Focus' in str(score.render())

    hour_bar = HourBar()
    hour_bar.refresh = lambda: None
    assert 'No hour data' in str(hour_bar.render())
    hour_bar.update_blocks([{'status': 'committed'}, {'status': 'peak'}, {'status': 'low'}, {'status': 'free'}, {'status': 'other'}])
    assert 'Hour Burn-down' in str(hour_bar.render())

    dep = DependencyChain()
    dep.refresh = lambda: None
    assert 'No tasks today' in str(dep.render())
    dep.update_tasks([
        {'name': 'Done', 'status': 'done'},
        {'name': 'Blocked', 'is_blocked': True, 'depends_on_names': 'Done'},
        {'name': 'Open'},
    ])
    assert 'Dependency Chain' in str(dep.render())

    table = SimpleNamespace(row_count=0, cursor_row=0, get_row_at=lambda row: ['42'])
    assert TaskTable.selected_task_id(table) is None
    table.row_count = 1
    table.cursor_row = -1
    assert TaskTable.selected_task_id(table) is None
    table.cursor_row = 0
    table.get_row_at = lambda row: ['not-int']
    assert TaskTable.selected_task_id(table) is None
    table.get_row_at = lambda row: ['42']
    assert TaskTable.selected_task_id(table) == 42

    timeline = TimelineTable()
    rows = []
    timeline.clear = lambda columns=False: None
    timeline.add_row = lambda *args, **kwargs: rows.append((args, kwargs))
    timeline.set_tasks([
        {'id': 1, 'name': 'Current', 'scheduled_start': '09:00', 'priority': 'critical'},
        {'id': 2, 'name': 'Done', 'scheduled_start': '10:00', 'status': 'done'},
        {'id': 3, 'name': 'Blocked', 'scheduled_start': 'bad', 'is_blocked': True, 'depends_on_names': 'Current'},
    ])
    assert len(rows) == 3

    add_modal = object.__new__(AddTaskModal)
    dismissed = []
    notified = []
    add_modal.dismiss = lambda value: dismissed.append(value)
    monkeypatch.setattr(AddTaskModal, 'app', property(lambda self: SimpleNamespace(notify=lambda *args, **kwargs: notified.append((args, kwargs)))), raising=False)
    values = {
        '#task-name': FakeInput(''),
        '#task-emoji': FakeInput('E'),
        '#task-priority': FakeSelect('high'),
        '#task-minutes': FakeInput('bad'),
        '#task-schedule': FakeInput(''),
    }
    add_modal.query_one = lambda selector, cls: values[selector]
    AddTaskModal.on_button_pressed(add_modal, FakeEvent('add'))
    assert notified
    values['#task-name'] = FakeInput('Task')
    AddTaskModal.on_button_pressed(add_modal, FakeEvent('add'))
    assert dismissed[-1]['estimated_minutes'] == 30
    AddTaskModal.on_button_pressed(add_modal, FakeEvent('cancel'))
    assert dismissed[-1] is None

    vision_modal = object.__new__(VisionImportModal)
    vision_modal.dismiss = lambda value: dismissed.append(value)
    monkeypatch.setattr(VisionImportModal, 'app', property(lambda self: SimpleNamespace(notify=lambda *args, **kwargs: notified.append((args, kwargs)))), raising=False)
    vision_modal.query_one = lambda selector, cls: FakeInput('')
    VisionImportModal.on_button_pressed(vision_modal, FakeEvent('import'))
    vision_modal.query_one = lambda selector, cls: FakeInput('/tmp/img.png')
    VisionImportModal.on_button_pressed(vision_modal, FakeEvent('import'))
    assert dismissed[-1] == '/tmp/img.png'
    VisionImportModal.on_button_pressed(vision_modal, FakeEvent('cancel'))
    ConfigModal.on_button_pressed(SimpleNamespace(dismiss=lambda value: dismissed.append(value)), FakeEvent('close'))
    HelpModal.on_button_pressed(SimpleNamespace(dismiss=lambda value: dismissed.append(value)), FakeEvent('close'))

    app = object.__new__(SelfHealApp)
    app._daemon_connected = True
    app._daemon_status = {}
    app._calendar_events = []
    app.notifications = []
    app.notify = lambda message, **kwargs: app.notifications.append((message, kwargs))
    app.refresh_count = 0
    app.refresh_all = lambda: setattr(app, 'refresh_count', app.refresh_count + 1)
    app._current_task_table = lambda: None
    SelfHealApp.action_toggle_selected(app)
    SelfHealApp.action_open_link(app)
    assert 'No task table focused' in app.notifications[-1][0]

    app._current_task_table = lambda: SimpleNamespace(selected_task_id=lambda: None)
    SelfHealApp.action_toggle_selected(app)
    SelfHealApp.action_open_link(app)
    assert 'Select a task row first' in app.notifications[-1][0]

    app._current_task_table = lambda: SimpleNamespace(selected_task_id=lambda: 7)
    app._load_tasks = lambda: [{'id': 7, 'name': 'Blocked', 'is_blocked': True}]
    SelfHealApp.action_toggle_selected(app)
    assert 'blocked' in app.notifications[-1][0]
    app._load_tasks = lambda: [{'id': 7, 'name': 'No URL'}]
    SelfHealApp.action_open_link(app)
    assert 'No external URL' in app.notifications[-1][0]

    app.pushes = []
    app.push_screen = lambda screen, callback=None: app.pushes.append((type(screen).__name__, callback))
    SelfHealApp.action_show_config(app)
    SelfHealApp.action_show_help(app)
    assert app.pushes[0][0] == 'ConfigModal'
    assert app.pushes[1][0] == 'HelpModal'

    img = tmp_path / 'img.png'
    img.write_bytes(b'image')
    workers = []
    app.run_worker = lambda coro, exclusive=True: workers.append((coro, exclusive))
    SelfHealApp.action_vision_import(app)
    _, callback = app.pushes[-1]
    callback(str(tmp_path / 'missing.png'))
    callback(str(img))
    assert workers and workers[-1][1] is True
    workers[-1][0].close()

    offline = []
    app._set_daemon_offline = lambda: offline.append(True)
    monkeypatch.setattr(tui_app, 'daemon_sync_calendar', lambda: (_ for _ in ()).throw(RuntimeError('down')))
    SelfHealApp.on_button_pressed(app, FakeEvent('btn-sync-calendar'))
    assert offline
