# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker database backend contract
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    AsyncContextManager,
    Iterable,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    TypeAlias,
)


Params: TypeAlias = (
    Sequence[Any]
    | Mapping[str, Any]
    | None
)


class DatabaseIntegrityError(Exception):
    """
    Backend-neutral integrity constraint error.
    """


@dataclass(slots=True, frozen=True)
class DatabaseResult:
    rowcount: int = 0
    lastrowid: Optional[int] = None


class DatabaseBackend(Protocol):
    async def connect(self) -> None:
        ...

    async def close(self) -> None:
        ...

    async def execute(
        self,
        query: str,
        params: Params = None,
    ) -> DatabaseResult:
        ...

    async def fetchone(
        self,
        query: str,
        params: Params = None,
    ) -> Optional[dict[str, Any]]:
        ...

    async def fetchall(
        self,
        query: str,
        params: Params = None,
    ) -> list[dict[str, Any]]:
        ...

    async def executemany(
        self,
        query: str,
        parameters: Iterable[Params],
    ) -> DatabaseResult:
        ...

    def transaction(
        self,
        *,
        immediate: bool = False,
    ) -> AsyncContextManager["DatabaseTransaction"]:
        ...


class DatabaseTransaction(Protocol):
    async def __aenter__(self) -> "DatabaseTransaction":
        ...

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> Optional[bool]:
        ...

    async def execute(
        self,
        query: str,
        params: Params = None,
    ) -> DatabaseResult:
        ...

    async def fetchone(
        self,
        query: str,
        params: Params = None,
    ) -> Optional[dict[str, Any]]:
        ...

    async def fetchall(
        self,
        query: str,
        params: Params = None,
    ) -> list[dict[str, Any]]:
        ...

    async def executemany(
        self,
        query: str,
        parameters: Iterable[Params],
    ) -> DatabaseResult:
        ...


def normalize_params(
    params: Params,
) -> tuple[Any, ...] | dict[str, Any]:
    if params is None:
        return ()

    if isinstance(params, Mapping):
        return dict(params)

    return tuple(params)