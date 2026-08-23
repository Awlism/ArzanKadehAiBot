# -*- coding: utf-8 -*-
"""
A minimal async-shaped stand-in for bot.py's `Database` class, backed by
the stdlib (synchronous) sqlite3 module. fetchone/fetchall/execute cover
the surface most of bot.py's business-logic functions call directly on
`db`.

`FakeDB.conn` additionally mimics the awaitable subset of aiosqlite's
Connection API (`await db.conn.execute(...)`, `await cursor.fetchall()`,
`await cursor.close()`, `await db.conn.commit()`) that a few lower-level
functions -- currently only ensure_column()/run_column_migrations() --
call directly instead of going through the fetchone/fetchall/execute
wrappers. This is additive: FakeDB's existing fetchone/fetchall/execute
behavior and signatures are unchanged, so every test written before this
was added keeps working exactly as before.

This lets us exercise real async functions end-to-end (including real
SQL against a real SQLite engine) without aiosqlite being installed.
It is NOT a general aiosqlite replacement and is only used in tests.
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
    """Awaitable-shaped wrapper around a plain sqlite3.Connection, used
    only by code that talks to `db.conn` directly (e.g. ensure_column's
    `PRAGMA table_info(...)` + `ALTER TABLE ... ADD COLUMN ...`)."""

    def __init__(self, raw_conn: sqlite3.Connection):
        self._raw = raw_conn

    async def execute(self, query, params=()):
        return _FakeCursor(self._raw.execute(query, params))

    async def commit(self):
        self._raw.commit()


class FakeDB:
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
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
