# -*- coding: utf-8 -*-
"""
A minimal async-shaped test database backed by the stdlib sqlite3 module.

FakeDB provides the small async database surface used by the modular
application code under test:

- fetchone()
- fetchall()
- execute()
- conn.execute()
- conn.commit()

The implementation uses a real in-memory SQLite database, allowing tests
to exercise async application functions against real SQL without requiring
the production database connection.

This is intentionally a small test double, not a general aiosqlite
replacement.
"""

import sqlite3


class _FakeCursor:
    """Awaitable-shaped wrapper around a plain sqlite3.Cursor."""

    def __init__(self, cursor: sqlite3.Cursor):
        self._cursor = cursor

    async def fetchone(self):
        return self._cursor.fetchone()

    async def fetchall(self):
        return self._cursor.fetchall()

    async def close(self):
        self._cursor.close()

    @property
    def lastrowid(self):
        return self._cursor.lastrowid


class _FakeConn:
    """
    Awaitable-shaped wrapper around a plain sqlite3.Connection.

    Used by modular database helpers that access ``db.conn`` directly,
    including schema inspection and column migration helpers.
    """

    def __init__(self, raw_conn: sqlite3.Connection):
        self._raw = raw_conn

    async def execute(self, query, params=()):
        return _FakeCursor(self._raw.execute(query, params))

    async def commit(self):
        self._raw.commit()


class FakeDB:
    """
    Minimal async database test double.

    It preserves the database interface used by the modular application
    code while executing all SQL against an in-memory SQLite connection.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._raw = conn
        self.conn = _FakeConn(conn)

    async def fetchone(self, query, params=()):
        cur = self._raw.execute(query, params)
        row = cur.fetchone()
        cur.close()
        return row

    async def fetchall(self, query, params=()):
        cur = self._raw.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        return rows

    async def execute(self, query, params=()):
        cur = self._raw.execute(query, params)
        self._raw.commit()
        return cur


def new_conn() -> sqlite3.Connection:
    """Create a fresh in-memory SQLite connection for tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn