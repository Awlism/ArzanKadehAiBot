# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
SQLite database backend

Concrete local implementation of the generic DatabaseBackend contract.

IMPORTANT:
- This module is SQLite-specific by design.
- Application/repository code must depend on DatabaseBackend instead.
- Existing bot.database.Database remains the owner of the current
  SQLite connection lifecycle and schema/migration logic.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

import aiosqlite

from .database import db
from .database_backend import (
    DatabaseBackend,
    DatabaseIntegrityError,
    DatabaseResult,
    DatabaseTransaction,
    Params,
    normalize_params,
)


class SQLiteTransaction:
    def __init__(self, *, immediate: bool = False) -> None:
        self._conn: Optional[aiosqlite.Connection] = None
        self._immediate = immediate

    async def __aenter__(self) -> "SQLiteTransaction":
        if db.conn is None:
            raise RuntimeError("Database is not connected.")

        self._conn = db.conn

        begin_sql = (
            "BEGIN IMMEDIATE"
            if self._immediate
            else "BEGIN"
        )

        await self._conn.execute(begin_sql)

        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> Optional[bool]:
        if self._conn is None:
            return None

        if exc_type is None:
            await self._conn.commit()
        else:
            await self._conn.rollback()

        self._conn = None

        return None

    def _require_connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Transaction is not active.")

        return self._conn

    async def execute(
        self,
        query: str,
        params: Params = None,
    ) -> DatabaseResult:
        conn = self._require_connection()

        try:
            cursor = await conn.execute(
                query,
                normalize_params(params),
            )
        except aiosqlite.IntegrityError as exc:
            raise DatabaseIntegrityError(
                str(exc)
            ) from exc

        try:
            return DatabaseResult(
                rowcount=cursor.rowcount,
                lastrowid=cursor.lastrowid,
            )
        finally:
            await cursor.close()

    async def fetchone(
        self,
        query: str,
        params: Params = None,
    ) -> Optional[dict[str, Any]]:
        conn = self._require_connection()

        cursor = await conn.execute(
            query,
            normalize_params(params),
        )

        try:
            row = await cursor.fetchone()

            if row is None:
                return None

            return dict(row)

        finally:
            await cursor.close()

    async def fetchall(
        self,
        query: str,
        params: Params = None,
    ) -> list[dict[str, Any]]:
        conn = self._require_connection()

        cursor = await conn.execute(
            query,
            normalize_params(params),
        )

        try:
            rows = await cursor.fetchall()

            return [dict(row) for row in rows]

        finally:
            await cursor.close()

    async def executemany(
        self,
        query: str,
        parameters: Iterable[Params],
    ) -> DatabaseResult:
        conn = self._require_connection()

        normalized_parameters = [
            normalize_params(params)
            for params in parameters
        ]

        try:
            cursor = await conn.executemany(
                query,
                normalized_parameters,
            )
        except aiosqlite.IntegrityError as exc:
            raise DatabaseIntegrityError(
                str(exc)
            ) from exc

        try:
            return DatabaseResult(
                rowcount=cursor.rowcount,
                lastrowid=cursor.lastrowid,
            )
        finally:
            await cursor.close()


class SQLiteBackend:
    def __init__(self) -> None:
        self._database = db

    async def connect(self) -> None:
        await self._database.connect()

    async def close(self) -> None:
        await self._database.close()

    async def execute(
        self,
        query: str,
        params: Params = None,
    ) -> DatabaseResult:
        try:
            cursor = await self._database.execute(
                query,
                normalize_params(params),
            )
        except aiosqlite.IntegrityError as exc:
            raise DatabaseIntegrityError(
                str(exc)
            ) from exc

        try:
            return DatabaseResult(
                rowcount=cursor.rowcount,
                lastrowid=cursor.lastrowid,
            )
        finally:
            await cursor.close()

    async def fetchone(
        self,
        query: str,
        params: Params = None,
    ) -> Optional[dict[str, Any]]:
        row = await self._database.fetchone(
            query,
            normalize_params(params),
        )

        if row is None:
            return None

        return dict(row)

    async def fetchall(
        self,
        query: str,
        params: Params = None,
    ) -> list[dict[str, Any]]:
        rows = await self._database.fetchall(
            query,
            normalize_params(params),
        )

        return [dict(row) for row in rows]

    async def executemany(
        self,
        query: str,
        parameters: Iterable[Params],
    ) -> DatabaseResult:
        if self._database.conn is None:
            raise RuntimeError(
                "Database is not connected."
            )

        normalized_parameters = [
            normalize_params(params)
            for params in parameters
        ]

        try:
            cursor = await self._database.conn.executemany(
                query,
                normalized_parameters,
            )
        except aiosqlite.IntegrityError as exc:
            raise DatabaseIntegrityError(
                str(exc)
            ) from exc

        try:
            await self._database.conn.commit()

            return DatabaseResult(
                rowcount=cursor.rowcount,
                lastrowid=cursor.lastrowid,
            )

        finally:
            await cursor.close()

    def transaction(
        self,
        *,
        immediate: bool = False,
    ) -> DatabaseTransaction:
        return SQLiteTransaction(immediate=immediate)


sqlite_backend = SQLiteBackend()


__all__ = [
    "SQLiteBackend",
    "SQLiteTransaction",
    "sqlite_backend",
]