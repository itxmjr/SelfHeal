from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

from selfheal.engine import life_model
from selfheal.interview import runner
from selfheal import obsidian, wallpaper


class Closeable:
    def __init__(self, name='conn'):
        self.name = name
        self.closed = False

    def close(self):
        self.closed = True


def test_generate_daily_report_with_tasks_and_score(monkeypatch):
    conn = Closeable()
    target = date(2026, 5, 4)
    monkeypatch.setattr(obsidian, 'get_connection', lambda: conn)
    monkeypatch.setattr(
        obsidian,
        'get_todays_tasks',
        lambda connection, day: [
            {
                'status': 'done',
                'scheduled_start': '09:00',
                'scheduled_end': '10:00',
                'emoji': 'R',
                'name': 'Read',
                'priority': 'high',
            },
            {'status': 'pending', 'name': 'Write'},
        ],
    )
    monkeypatch.setattr(
        obsidian,
        'get_score',
        lambda connection, day: {
            'score': 88.4,
            'task_completion': 35,
            'time_utilization': 25,
            'goal_alignment': 18,
            'consistency_bonus': 10,
        },
    )

    report = obsidian.generate_daily_report(target)

    assert '# SelfHeal Daily Report - Monday, May 04, 2026' in report
    assert '- **Score:** 88/100' in report
    assert '| ✅ | 09:00 - 10:00 | R Read | high |' in report
    assert '| ⏳ | --:-- - --:-- | Write | medium |' in report
    assert conn.closed is True


def test_generate_daily_report_without_score(monkeypatch):
    monkeypatch.setattr(obsidian, 'get_connection', lambda: Closeable())
    monkeypatch.setattr(obsidian, 'get_todays_tasks', lambda connection, day: [])
    monkeypatch.setattr(obsidian, 'get_score', lambda connection, day: None)

    report = obsidian.generate_daily_report(date(2026, 5, 4))

    assert '- *No score data available yet.*' in report


def test_sync_to_obsidian_handles_missing_and_writes_note(monkeypatch, tmp_path):
    monkeypatch.setattr(obsidian, 'load_config', lambda: {'obsidian': {}})
    assert obsidian.sync_to_obsidian() is False

    missing = tmp_path / 'missing'
    monkeypatch.setattr(obsidian, 'load_config', lambda: {'obsidian': {'vault_path': str(missing)}})
    assert obsidian.sync_to_obsidian() is False

    monkeypatch.setattr(obsidian, 'load_config', lambda: {'obsidian': {'vault_path': str(tmp_path)}})
    monkeypatch.setattr(obsidian, 'generate_daily_report', lambda target: f'report for {target.isoformat()}')

    assert obsidian.sync_to_obsidian() is True
    note = tmp_path / 'SelfHeal' / 'Daily' / f'{date.today().isoformat()}.md'
    assert note.read_text() == f'report for {date.today().isoformat()}'


def test_wallpaper_update_no_model_returns_without_file(monkeypatch, tmp_path):
    target = tmp_path / 'wallpaper.json'
    monkeypatch.setattr(wallpaper, 'WALLPAPER_DATA_PATH', target)
    monkeypatch.setattr(wallpaper, 'load_life_model', lambda: None)

    wallpaper.update_wallpaper_data()

    assert not target.exists()


def test_wallpaper_update_and_read_paths(monkeypatch, tmp_path):
    target = tmp_path / 'nested' / 'wallpaper.json'
    conn = Closeable()
    tasks = [
        {
            'emoji': 'A',
            'name': 'Active',
            'status': 'pending',
            'priority': 'high',
            'scheduled_start': '09:00',
            'scheduled_end': '10:00',
            'is_blocked': False,
        },
        {'emoji': 'D', 'name': 'Done', 'status': 'done', 'priority': 'low', 'is_blocked': False},
        {'emoji': 'B', 'name': 'Blocked', 'status': 'pending', 'is_blocked': True},
    ]
    model = {'sleep': {'wake': '06:30', 'bed': '22:30'}, 'energy': {'peak': '09:00-11:00', 'low': '14:00-15:00'}}
    monkeypatch.setattr(wallpaper, 'WALLPAPER_DATA_PATH', target)
    monkeypatch.setattr(wallpaper, 'load_life_model', lambda: model)
    monkeypatch.setattr(wallpaper, 'get_connection', lambda: conn)
    monkeypatch.setattr(wallpaper, 'get_todays_tasks', lambda connection: tasks)
    monkeypatch.setattr(wallpaper, 'calculate_score', lambda: {'score': 72, 'streak': 4})

    wallpaper.update_wallpaper_data()
    data = json.loads(target.read_text())

    assert data['score_color'] == 'green'
    assert data['mood'] == 'On Track'
    assert data['next'] == {'name': 'A Active', 'start': '09:00', 'end': '10:00'}
    assert data['tasks_done'] == 1
    assert data['tasks_total'] == 3
    assert data['model']['sleep_wake'] == '06:30'
    assert wallpaper.read_wallpaper_data() == data

    target.write_text('{bad json')
    assert wallpaper.read_wallpaper_data() is None

    target.write_text(json.dumps({'date': '1999-01-01'}))
    assert wallpaper.read_wallpaper_data() is None

    target.unlink()
    assert wallpaper.read_wallpaper_data() is None


def test_interview_extract_yaml_and_history_helpers():
    assert runner._extract_yaml('[INTERVIEW_COMPLETE]\n```yaml\nsleep:\n  wake: "07:00"\n```') == {'sleep': {'wake': '07:00'}}
    assert runner._extract_yaml('```\ngoals:\n  - name: Read\n```') == {'goals': [{'name': 'Read'}]}
    assert runner._extract_yaml('```yaml\n: bad: yaml:\n```') is None
    assert runner._extract_yaml('no block') is None

    compressed = runner._compress_history([
        {'role': 'system', 'content': 'x' * 350},
        {'role': 'user', 'content': 'answer'},
    ])

    assert compressed['role'] == 'system'
    assert 'system: ' + ('x' * 300) in compressed['content']
    assert 'user: answer' in compressed['content']


def test_run_interview_saves_completed_model(monkeypatch):
    saved = []
    printed = []

    class LLM:
        def chat(self, messages, temperature=0.7):
            return SimpleNamespace(content='[INTERVIEW_COMPLETE]\n```yaml\nsleep:\n  wake: "07:00"\n```')

    monkeypatch.setattr(runner, 'get_llm_with_fallback', lambda: LLM())
    monkeypatch.setattr(runner, 'save_life_model', lambda model: saved.append(model))
    monkeypatch.setattr(runner, '_print_summary', lambda model: printed.append(model))
    monkeypatch.setattr(runner, '_print_assistant', lambda text: None)
    monkeypatch.setattr(runner.console, 'print', lambda *args, **kwargs: None)
    monkeypatch.setattr(runner.console, 'input', lambda prompt: 'initial answer')

    result = runner.run_interview()

    assert result == {'sleep': {'wake': '07:00'}}
    assert saved == [result]
    assert printed == [result]


def test_run_interview_quit_and_regenerate_prompt(monkeypatch):
    seen_system_prompts = []

    class LLM:
        def chat(self, messages, temperature=0.7):
            seen_system_prompts.append(messages[0]['content'])
            return SimpleNamespace(content='[INTERVIEW_COMPLETE]\n```yaml\ngoals:\n  - name: Updated\n```')

    monkeypatch.setattr(runner, 'get_llm_with_fallback', lambda: LLM())
    monkeypatch.setattr(runner, 'load_life_model', lambda: {'goals': [{'name': 'Read'}]})
    monkeypatch.setattr(runner, 'save_life_model', lambda model: None)
    monkeypatch.setattr(runner, '_print_summary', lambda model: None)
    monkeypatch.setattr(runner, '_print_assistant', lambda text: None)
    monkeypatch.setattr(runner.console, 'print', lambda *args, **kwargs: None)
    monkeypatch.setattr(runner.console, 'input', lambda prompt: 'please update it')

    assert runner.run_interview(regenerate=True) == {'goals': [{'name': 'Updated'}]}
    assert 'Read' in seen_system_prompts[0]

    monkeypatch.setattr(runner.console, 'input', lambda prompt: 'quit')
    assert runner.run_interview(regenerate=False) is None


def _life_model():
    return {
        'sleep': {'wake': '06:00', 'bed': '12:00'},
        'commitments': [{'name': 'Work', 'hours': '08:00-09:00'}],
        'energy': {'peak': '09:00-10:00', 'low': '10:00-11:00'},
        'goals': [
            {'name': 'Daily', 'frequency': 'daily'},
            {'name': 'Gym', 'frequency': '3x/week'},
            {'name': 'Weekday', 'frequency': 'weekdays'},
            {'name': 'Weekend', 'frequency': 'weekends'},
        ],
    }


def test_life_model_available_hours_and_calendar(monkeypatch):
    today = date.today().isoformat()
    events = [
        {'summary': 'Meeting', 'start': f'{today}T07:00:00', 'end': f'{today}T08:00:00'},
        {'summary': 'Bad', 'start': 'not-a-date', 'end': ''},
    ]

    hours = life_model.get_available_hours(_life_model(), calendar_events=events)

    by_hour = {item['hour']: item for item in hours}
    assert by_hour[6]['status'] == 'free'
    assert by_hour[7]['status'] == 'committed'
    assert by_hour[7]['task'] == '[Cal] Meeting'
    assert by_hour[8]['status'] == 'committed'
    assert by_hour[8]['task'] == 'Work'
    assert by_hour[9]['status'] == 'peak'
    assert by_hour[10]['status'] == 'low'
    assert life_model.get_free_hours(_life_model())

    monkeypatch.setattr(life_model, 'load_life_model', lambda: None)
    assert life_model.get_available_hours(None) == []
    assert life_model.get_goals_for_today(None) == []


def test_life_model_goal_frequencies_and_parse_fallbacks():
    monday = date(2026, 5, 4)
    saturday = date(2026, 5, 2)

    weekday_goals = life_model.get_goals_for_today(_life_model(), monday)
    weekend_goals = life_model.get_goals_for_today(_life_model(), saturday)

    assert [goal['name'] for goal in weekday_goals] == ['Daily', 'Gym', 'Weekday']
    assert weekday_goals[1]['_weekly_target'] == 3
    assert [goal['name'] for goal in weekend_goals] == ['Daily', 'Gym', 'Weekend']
    assert life_model._parse_time('bad').hour == 7
    assert life_model._is_commitment_now({'hours': 'bad'}, 9) is False
    assert life_model._in_range(9, 'bad') is False
    assert life_model._parse_calendar_dt('2026-05-04').date() == date(2026, 5, 4)
