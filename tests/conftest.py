import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from unittest.mock import patch

from selfheal.db import SCHEMA, run_migrations

@pytest.fixture
def temp_db():
    """Create a temporary SQLite database with the SelfHeal schema."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    run_migrations(conn)
    
    yield conn
    
    conn.close()
    os.remove(path)

@pytest.fixture
def temp_config_dir():
    """Provide a temporary directory for config files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)

@pytest.fixture
def mock_env(temp_config_dir):
    """Mock environment variables to use temp dirs."""
    env_vars = {
        "SELFHEAL_CONFIG": str(temp_config_dir / "config"),
        "SELFHEAL_DATA": str(temp_config_dir / "data"),
    }
    with patch.dict(os.environ, env_vars):
        yield env_vars
