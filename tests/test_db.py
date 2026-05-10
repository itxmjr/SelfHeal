import sqlite3
from datetime import date

from selfheal.db import (
    SCHEMA,
    SCHEMA_VERSION,
    upsert_goal,
    upsert_task,
    get_todays_tasks,
    mark_task_done,
    mark_task_pending,
    save_score,
    get_score,
    run_migrations,
)

def test_upsert_goal(temp_db):
    goal_id = upsert_goal(temp_db, name="Test Goal", priority="high")
    assert goal_id > 0
    
    # Verify insertion
    cur = temp_db.execute("SELECT name, priority FROM goals WHERE id = ?", (goal_id,))
    row = cur.fetchone()
    assert row["name"] == "Test Goal"
    assert row["priority"] == "high"

def test_upsert_task_and_get_todays(temp_db):
    # Insert task
    task_id = upsert_task(
        temp_db, 
        name="Test Task", 
        emoji="🚀", 
        schedule="daily",
        priority="high"
    )
    assert task_id > 0

    # Ensure get_todays_tasks retrieves it automatically
    today_str = date.today().isoformat()
    tasks = get_todays_tasks(temp_db, today_str)
    
    assert len(tasks) == 1
    assert tasks[0]["name"] == "Test Task"
    assert tasks[0]["emoji"] == "🚀"
    assert tasks[0]["status"] == "pending"
    assert tasks[0]["source"] == "manual"
    assert tasks[0]["external_id"] is None

def test_fresh_db_schema_has_external_identity_columns(temp_db):
    task_columns = {
        row["name"] for row in temp_db.execute("PRAGMA table_info(tasks)").fetchall()
    }
    assert {
        "source",
        "external_id",
        "external_url",
        "external_updated_at",
        "sync_hash",
    }.issubset(task_columns)

    sync_log_columns = {
        row["name"] for row in temp_db.execute("PRAGMA table_info(sync_log)").fetchall()
    }
    assert sync_log_columns == {
        "id",
        "source",
        "action",
        "external_id",
        "status",
        "error",
        "created_at",
    }

    row = temp_db.execute("SELECT version FROM schema_version").fetchone()
    assert row["version"] == SCHEMA_VERSION

    indexes = temp_db.execute("PRAGMA index_list(tasks)").fetchall()
    external_id_index = next(
        index for index in indexes if index["name"] == "idx_tasks_source_external_id"
    )
    assert external_id_index["unique"] == 1

    index_columns = [
        row["name"]
        for row in temp_db.execute("PRAGMA index_info(idx_tasks_source_external_id)").fetchall()
    ]
    assert index_columns == ["source", "external_id"]

def test_migration_preserves_existing_tasks_as_manual():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO tasks (name) VALUES (?)", ("Existing Task",))

    run_migrations(conn)

    row = conn.execute(
        "SELECT source, external_id, external_url, external_updated_at, sync_hash FROM tasks"
    ).fetchone()
    assert row["source"] == "manual"
    assert row["external_id"] is None
    assert row["external_url"] is None
    assert row["external_updated_at"] is None
    assert row["sync_hash"] is None
    conn.close()

def test_migration_is_idempotent(temp_db):
    run_migrations(temp_db)
    run_migrations(temp_db)

    rows = temp_db.execute("SELECT version FROM schema_version").fetchall()
    assert [row["version"] for row in rows] == [SCHEMA_VERSION]

    task_columns = [
        row["name"] for row in temp_db.execute("PRAGMA table_info(tasks)").fetchall()
    ]
    assert task_columns.count("source") == 1
    assert task_columns.count("external_id") == 1

def test_external_identity_insert_and_retrieval(temp_db):
    task_id = upsert_task(
        temp_db,
        name="Synced Task",
        source="clickup",
        external_id="cu_123",
        external_url="https://app.clickup.com/t/cu_123",
        external_updated_at="2026-05-04T12:00:00Z",
        sync_hash="abc123",
    )

    tasks = get_todays_tasks(temp_db)
    task = next(task for task in tasks if task["id"] == task_id)
    assert task["source"] == "clickup"
    assert task["external_id"] == "cu_123"
    assert task["external_url"] == "https://app.clickup.com/t/cu_123"
    assert task["external_updated_at"] == "2026-05-04T12:00:00Z"
    assert task["sync_hash"] == "abc123"

def test_duplicate_external_identity_for_same_source_fails(temp_db):
    upsert_task(
        temp_db,
        name="First Synced Task",
        source="clickup",
        external_id="cu_123",
    )

    try:
        upsert_task(
            temp_db,
            name="Duplicate Synced Task",
            source="clickup",
            external_id="cu_123",
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("duplicate external identity insert should fail")

def test_multiple_manual_tasks_with_null_external_id_allowed(temp_db):
    first_id = upsert_task(temp_db, name="First Manual Task")
    second_id = upsert_task(temp_db, name="Second Manual Task")

    rows = temp_db.execute(
        "SELECT id, source, external_id FROM tasks WHERE id IN (?, ?) ORDER BY id",
        (first_id, second_id),
    ).fetchall()
    assert [row["source"] for row in rows] == ["manual", "manual"]
    assert [row["external_id"] for row in rows] == [None, None]

def test_mark_task_status(temp_db):
    task_id = upsert_task(temp_db, name="Toggle Task")
    today_str = date.today().isoformat()
    
    # Initial is pending
    tasks = get_todays_tasks(temp_db, today_str)
    assert tasks[0]["status"] == "pending"
    
    # Mark done
    mark_task_done(temp_db, task_id, today_str)
    tasks = get_todays_tasks(temp_db, today_str)
    assert tasks[0]["status"] == "done"
    
    # Mark pending again
    mark_task_pending(temp_db, task_id, today_str)
    tasks = get_todays_tasks(temp_db, today_str)
    assert tasks[0]["status"] == "pending"

def test_score_saving(temp_db):
    today_str = date.today().isoformat()
    
    # No score initially
    assert get_score(temp_db, today_str) is None
    
    # Save a score
    save_score(temp_db, today_str, 85.5, 40.0, 25.5, 20.0, 0.0)
    
    # Retrieve it
    score = get_score(temp_db, today_str)
    assert score is not None
    assert score["score"] == 85.5
    assert score["task_completion"] == 40.0
