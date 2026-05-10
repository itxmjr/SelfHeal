from __future__ import annotations

import sqlite3
from typing import Optional, Any
from ..db import get_connection

class BaseRepository:
    def __init__(self, conn: Optional[sqlite3.Connection] = None):
        self._conn = conn
        self._own_connection = False

    def get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = get_connection()
            self._own_connection = True
        return self._conn

    def close(self):
        if self._own_connection and self._conn:
            self._conn.close()
            self._conn = None
            self._own_connection = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
