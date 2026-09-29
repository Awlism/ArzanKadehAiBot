# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Active database backend selector.

This module provides one stable backend object for application and
repository code.

Local development/tests use SQLiteBackend by default.
Cloudflare Worker entrypoints can replace the active backend with
D1Backend at runtime.

IMPORTANT:
- Do not import bot.database directly from application/repository code
  when backend access is required.
- Do not put SQLite-specific or D1-specific logic in this module.
- The active backend can be replaced without changing repository imports.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .database_backend import (
    DatabaseBackend,
    DatabaseResult,
    DatabaseTransaction,
    Params,
)
from .sqlite_backend import sqlite_backend


class BackendProxy:
    """
    Stable proxy around the currently active DatabaseBackend.

    Repositories import this object once and continue using the same
    reference even if the active backend is later switched from SQLite
    to Cloudflare D1.
    """

    def __init__(self, backend: DatabaseBackend) -> None:
        self._backend = backend

    @property
    def active(self) -> DatabaseBackend:
        """Return the currently active database backend."""
        return self._backend

    def set_backend(self, backend: DatabaseBackend) -> None:
        """
        Replace the active database backend.

        This is used by the Cloudflare Worker entrypoint to switch from
        the default local SQLite backend to the D1 backend.
        """
        if backend is None:
            raise ValueError("Database backend is required.")

        self._backend = backend

    async def connect(self) -> None:
        """Connect the active backend."""
        await self._backend.connect()

    async def close(self) -> None:
        """Close the active backend."""
        await self._backend.close()

    async def execute(
        self,
        query: str,
        params: Params = None,
    ) -> DatabaseResult:
        """Execute a statement through the active backend."""
        return await self._backend.execute(
            query,
            params,
        )

    async def fetchone(
        self,
        query: str,
        params: Params = None,
    ) -> Optional[dict]:
        """Fetch one row through the active backend."""
        return await self._backend.fetchone(
            query,
            params,
        )

    async def fetchall(
        self,
        query: str,
        params: Params = None,
    ) -> list[dict]:
        """Fetch all rows through the active backend."""
        return await self._backend.fetchall(
            query,
            params,
        )

    async def executemany(
        self,
        query: str,
        parameters: Iterable[Params],
    ) -> DatabaseResult:
        """Execute many statements through the active backend."""
        return await self._backend.executemany(
            query,
            parameters,
        )

    def transaction(
        self,
        *,
        immediate: bool = False,
    ) -> DatabaseTransaction:
        """Create a transaction through the active backend."""
        return self._backend.transaction(
            immediate=immediate,
        )


backend = BackendProxy(sqlite_backend)


__all__ = [
    "BackendProxy",
    "backend",
]