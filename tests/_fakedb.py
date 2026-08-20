# -*- coding: utf-8 -*-
"""
A minimal async-shaped stand-in for bot.py's `Database` class, backed by
the stdlib (synchronous) sqlite3 module. Only fetchone/fetchall/execute
are implemented -- exactly the surface bot.py's business-logic functions
(resolve_category_ids, resolve_city_id, plain_keyword_search,
SearchEngine, referral helpers, ...) actually call.

This lets us exercise real async functions end-to-end (including real
SQL against a real SQLite engine) without aiosqlite being installed.
It is NOT a general aiosqlite replacement and is only used in tests.
"""
import sqlite3


class FakeDB:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    async def fetchone(self, query, params=()):
        cur = self.conn.execute(query, params)
        row = cur.fetchone()
        cur.close()
        return row

    async def fetchall(self, query, params=()):
        cur = self.conn.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        return rows

    async def execute(self, query, params=()):
        cur = self.conn.execute(query, params)
        self.conn.commit()
        return cur


def new_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
