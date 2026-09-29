# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Active database backend selector.

This module provides one stable backend object for application and
repository code.

IMPORTANT:
- Local SQLite is loaded lazily so Cloudflare Worker imports do not
  automatically load aiosqlite or SQLite-specific modules.
- Cloudflare Worker entrypoints can replace the active backend with D1Backend.
- Application and repository code should only depend on the backend proxy.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .database_backend import (
    DatabaseBackend,
    DatabaseResult,
    DatabaseTransaction,
    Params,
)


class BackendProxy:
    """
    Stable proxy around the currently active DatabaseBackend.

    The default local backend is created lazily. This prevents importing
    SQLite/aiosqlite merely because application code imports this module.

    Cloudflare Worker entrypoints can call set_backend() with D1Backend
    before using the application layer.
    """

    def __init__(self) -> None:
        self._backend: Optional[DatabaseBackend] = None

    @property
    def active(self) -> DatabaseBackend:
        """
        Return the currently active backend.

        If no backend has been explicitly configured, initialize the
        local SQLite backend lazily.
        """
        if self._backend is None:
            from .sqlite_backend import sqlite_backend

            self._backend = sqlite_backend

        return self._backend

    def set_backend(self, backend: DatabaseBackend) -> None:
        """
        Replace the active database backend.

        The Cloudflare Worker uses this to switch from the default local
        SQLite backend to Cloudflare D1.
        """
        if backend is None:
            raise ValueError("Database backend is required.")

        self._backend = backend

    async def connect(self) -> None:
        """Connect the active backend."""
        await self.active.connect()

    async def close(self) -> None:
        """Close the active backend."""
        await self.active.close()

    async def execute(
        self,
        query: str,
        params: Params = None,
    ) -> DatabaseResult:
        """Execute a statement through the active backend."""
        return await self.active.execute(
            query,
            params,
        )

    async def fetchone(
        self,
        query: str,
        params: Params = None,
    ) -> Optional[dict]:
        """Fetch one row through the active backend."""
        return await self.active.fetchone(
            query,
            params,
        )

    async def fetchall(
        self,
        query: str,
        params: Params = None,
    ) -> list[dict]:
        """Fetch all rows through the active backend."""
        return await self.active.fetchall(
            query,
            params,
        )

    async def executemany(
        self,
        query: str,
        parameters: Iterable[Params],
    ) -> DatabaseResult:
        """Execute many statements through the active backend."""
        return await self.active.executemany(
            query,
            parameters,
        )

    def transaction(
        self,
        *,
        immediate: bool = False,
    ) -> DatabaseTransaction:
        """Create a transaction through the active backend."""
        return self.active.transaction(
            immediate=immediate,
        )


backend = BackendProxy()


__all__ = [
    "BackendProxy",
    "backend",
]