# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker database backend selector.
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
    Stable database backend proxy for the Cloudflare Worker.

    Unlike the main application backend, this Worker-specific proxy
    never imports SQLite or aiosqlite.
    """

    def __init__(self) -> None:
        self._backend: Optional[DatabaseBackend] = None

    @property
    def active(self) -> DatabaseBackend:
        if self._backend is None:
            raise RuntimeError(
                "Cloudflare Worker database backend is not configured."
            )

        return self._backend

    def set_backend(
        self,
        backend: DatabaseBackend,
    ) -> None:
        if backend is None:
            raise ValueError(
                "Database backend is required."
            )

        self._backend = backend

    async def connect(self) -> None:
        await self.active.connect()

    async def close(self) -> None:
        await self.active.close()

    async def execute(
        self,
        query: str,
        params: Params = None,
    ) -> DatabaseResult:
        return await self.active.execute(
            query,
            params,
        )

    async def fetchone(
        self,
        query: str,
        params: Params = None,
    ) -> Optional[dict]:
        return await self.active.fetchone(
            query,
            params,
        )

    async def fetchall(
        self,
        query: str,
        params: Params = None,
    ) -> list[dict]:
        return await self.active.fetchall(
            query,
            params,
        )

    async def executemany(
        self,
        query: str,
        parameters: Iterable[Params],
    ) -> DatabaseResult:
        return await self.active.executemany(
            query,
            parameters,
        )

    def transaction(
        self,
        *,
        immediate: bool = False,
    ) -> DatabaseTransaction:
        return self.active.transaction(
            immediate=immediate,
        )


backend = BackendProxy()


__all__ = [
    "BackendProxy",
    "backend",
]