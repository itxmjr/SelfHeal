import sqlite3
from datetime import date

from .config import DB_PATH, ensure_dirs

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'medium',
    frequency TEXT NOT NULL DEFAULT 'daily',
    preferred_time TEXT,
    estimated_minutes INTEGER DEFAULT 30,
    target_count INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    emoji TEXT NOT NULL DEFAULT '',
    schedule TEXT NOT NULL DEFAULT 'daily',
    priority TEXT NOT NULL DEFAULT 'medium',
    goal_id INTEGER,
    depends_on TEXT DEFAULT '',
    estimated_minutes INTEGER DEFAULT 30,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (goal_id) REFERENCES goals(id)
);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id INTEGER NOT NULL,
    depends_on_id INTEGER NOT NULL,
    PRIMARY KEY (task_id, depends_on_id),
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    FOREIGN KEY (depends_on_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS daily_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    task_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    scheduled_start TEXT,
    scheduled_end TEXT,
    actual_start TEXT,
    actual_end TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    UNIQUE(date, task_id)
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    score REAL NOT NULL DEFAULT 0,
    task_completion REAL NOT NULL DEFAULT 0,
    time_utilization REAL NOT NULL DEFAULT 0,
    goal_alignment REAL NOT NULL DEFAULT 0,
    consistency_bonus REAL NOT NULL DEFAULT 0
);
"""


def get_connection() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    run_migrations(conn)
    conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _get_schema_version(conn: sqlite3.Connection) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
    )
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        return 1
    return row["version"]


def _set_schema_version(conn: sqlite3.Connection, version: int):
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))


def _migrate_to_v2(conn: sqlite3.Connection):
    columns = _table_columns(conn, "tasks")
    migrations = {
        "source": "ALTER TABLE tasks ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'",
        "external_id": "ALTER TABLE tasks ADD COLUMN external_id TEXT",
        "external_url": "ALTER TABLE tasks ADD COLUMN external_url TEXT",
        "external_updated_at": "ALTER TABLE tasks ADD COLUMN external_updated_at TEXT",
        "sync_hash": "ALTER TABLE tasks ADD COLUMN sync_hash TEXT",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)

    conn.execute("UPDATE tasks SET source = 'manual' WHERE source IS NULL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            action TEXT NOT NULL,
            external_id TEXT,
            status TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )


def _ensure_v2_indexes(conn: sqlite3.Connection):
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_source_external_id "
        "ON tasks(source, external_id) WHERE external_id IS NOT NULL"
    )


def run_migrations(conn: sqlite3.Connection):
    version = _get_schema_version(conn)
    if version < 2:
        _migrate_to_v2(conn)
        _set_schema_version(conn, 2)
    if version <= 2:
        _ensure_v2_indexes(conn)
    conn.commit()


def upsert_goal(conn: sqlite3.Connection, name: str, priority: str = "medium",
                frequency: str = "daily", preferred_time: str | None = None,
                estimated_minutes: int = 30, target_count: int | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO goals (name, priority, frequency, preferred_time, estimated_minutes, target_count) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, priority, frequency, preferred_time, estimated_minutes, target_count),
    )
    conn.commit()
    goal_id = cur.lastrowid
    assert goal_id is not None
    return goal_id


def upsert_task(conn: sqlite3.Connection, name: str, emoji: str = "",
                schedule: str = "daily", priority: str = "medium",
                goal_id: int | None = None, depends_on: str = "",
                estimated_minutes: int = 30, *, source: str = "manual",
                external_id: str | None = None, external_url: str | None = None,
                external_updated_at: str | None = None,
                sync_hash: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO tasks (name, emoji, schedule, priority, goal_id, depends_on, estimated_minutes, "
        "source, external_id, external_url, external_updated_at, sync_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, emoji, schedule, priority, goal_id, depends_on, estimated_minutes,
         source, external_id, external_url, external_updated_at, sync_hash),
    )
    conn.commit()
    task_id = cur.lastrowid
    assert task_id is not None
    return task_id


def add_dependency(conn: sqlite3.Connection, task_id: int, depends_on_id: int):
    conn.execute(
        "INSERT OR IGNORE INTO task_dependencies (task_id, depends_on_id) VALUES (?, ?)",
        (task_id, depends_on_id),
    )
    conn.commit()


def get_todays_tasks(conn: sqlite3.Connection, today: str | None = None) -> list[dict]:
    today = today or date.today().isoformat()
    rows = conn.execute(
        "SELECT t.*, "
        "COALESCE(dl.status, 'pending') AS status, "
        "dl.scheduled_start, dl.scheduled_end, dl.actual_start, dl.actual_end, "
        "g.name AS goal_name, "
        "(SELECT GROUP_CONCAT(t2.name, ', ') FROM task_dependencies td "
        " JOIN tasks t2 ON t2.id = td.depends_on_id "
        " WHERE td.task_id = t.id) AS depends_on_names "
        "FROM tasks t "
        "LEFT JOIN daily_logs dl ON dl.task_id = t.id AND dl.date = ? "
        "LEFT JOIN goals g ON g.id = t.goal_id "
        "WHERE t.is_active = 1 "
        "ORDER BY dl.scheduled_start, t.priority",
        (today,),
    ).fetchall()
    
    tasks = [dict(r) for r in rows]
    
    # Check dependencies
    for task in tasks:
        deps = conn.execute(
            "SELECT td.depends_on_id, dl.status "
            "FROM task_dependencies td "
            "LEFT JOIN daily_logs dl ON dl.task_id = td.depends_on_id AND dl.date = ? "
            "WHERE td.task_id = ?",
            (today, task["id"])
        ).fetchall()
        
        is_blocked = False
        for dep in deps:
            if dep["status"] != "done":
                is_blocked = True
                break
        task["is_blocked"] = is_blocked
        
    return tasks


def mark_task_done(conn: sqlite3.Connection, task_id: int, today: str | None = None):
    today = today or date.today().isoformat()
    conn.execute(
        "INSERT INTO daily_logs (date, task_id, status, actual_end) VALUES (?, ?, 'done', datetime('now')) "
        "ON CONFLICT(date, task_id) DO UPDATE SET status='done', actual_end=datetime('now')",
        (today, task_id),
    )
    conn.commit()


def mark_task_pending(conn: sqlite3.Connection, task_id: int, today: str | None = None):
    today = today or date.today().isoformat()
    conn.execute(
        "INSERT INTO daily_logs (date, task_id, status) VALUES (?, ?, 'pending') "
        "ON CONFLICT(date, task_id) DO UPDATE SET status='pending', actual_start=NULL, actual_end=NULL",
        (today, task_id),
    )
    conn.commit()


def save_score(conn: sqlite3.Connection, today: str, score: float,
               task_completion: float, time_utilization: float,
               goal_alignment: float, consistency_bonus: float):
    conn.execute(
        "INSERT INTO scores (date, score, task_completion, time_utilization, goal_alignment, consistency_bonus) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(date) DO UPDATE SET score=?, task_completion=?, time_utilization=?, "
        "goal_alignment=?, consistency_bonus=?",
        (today, score, task_completion, time_utilization, goal_alignment, consistency_bonus,
         score, task_completion, time_utilization, goal_alignment, consistency_bonus),
    )
    conn.commit()


def get_score(conn: sqlite3.Connection, today: str) -> dict | None:
    row = conn.execute("SELECT * FROM scores WHERE date = ?", (today,)).fetchone()
    return dict(row) if row else None


def get_streak(conn: sqlite3.Connection, threshold: float = 70.0) -> int:
    rows = conn.execute(
        "SELECT date, score FROM scores ORDER BY date DESC LIMIT 365"
    ).fetchall()
    streak = 0
    for row in rows:
        if row["score"] >= threshold:
            streak += 1
        else:
            break
    return streak


def get_history(conn: sqlite3.Connection, days: int = 14) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM scores ORDER BY date DESC LIMIT ?", (days,)
    ).fetchall()
    return [dict(r) for r in rows]
