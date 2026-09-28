# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Database backend contract

This module defines the database interface shared by local SQLite
and the future Cloudflare D1 backend.

IMPORTANT:
- This file contains no SQLite-specific implementation.
- It must remain usable by both local and Cloudflare runtimes.
- Existing SQLite behavior is not changed by this module alone.
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


# ============================================================================
# TYPES
# ============================================================================

Params: TypeAlias = (
    Sequence[Any]
    | Mapping[str, Any]
    | None
)


@dataclass(slots=True, frozen=True)
class DatabaseResult:
    """
    Normalized result for database write operations.

    SQLite can provide rowcount and lastrowid through its cursor.
    D1 has different response objects, so repositories should depend
    on this normalized representation instead of a SQLite cursor.
    """

    rowcount: int = 0
    lastrowid: Optional[int] = None


# ============================================================================
# DATABASE BACKEND CONTRACT
# ============================================================================


class DatabaseBackend(Protocol):
    """
    Common async database contract.

    Implementations:
        - Local SQLite backend
        - Cloudflare D1 backend

    The application/repository layer must depend on this contract
    rather than on a concrete database driver.
    """

    async def connect(self) -> None:
        """
        Open or initialize the backend connection/resource.
        """
        ...

    async def close(self) -> None:
        """
        Release backend resources.
        """
        ...

    async def execute(
        self,
        query: str,
        params: Params = None,
    ) -> DatabaseResult:
        """
        Execute one write statement.

        Returns normalized write metadata instead of a driver-specific
        cursor object.
        """
        ...

    async def fetchone(
        self,
        query: str,
        params: Params = None,
    ) -> Optional[dict[str, Any]]:
        """
        Execute a query and return one row, or None.
        """
        ...

    async def fetchall(
        self,
        query: str,
        params: Params = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a query and return all rows.
        """
        ...

    async def executemany(
        self,
        query: str,
        parameters: Iterable[Params],
    ) -> DatabaseResult:
        """
        Execute one statement against multiple parameter sets.
        """
        ...

    def transaction(
        self,
    ) -> AsyncContextManager["DatabaseTransaction"]:
        """
        Create a transaction context.

        The concrete backend decides how the transaction is implemented.

        SQLite may use BEGIN/COMMIT/ROLLBACK.
        D1 may use batch/atomic operations where appropriate.
        """
        ...


# ============================================================================
# TRANSACTION CONTRACT
# ============================================================================


class DatabaseTransaction(Protocol):
    """
    Common transaction contract.

    Repositories should use this abstraction for operations that must
    succeed or fail as one logical unit.
    """

    async def __aenter__(self) -> "DatabaseTransaction":
        """
        Start/enter the transaction.
        """
        ...

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> Optional[bool]:
        """
        Commit on success or roll back on failure according to
        the concrete backend.
        """
        ...

    async def execute(
        self,
        query: str,
        params: Params = None,
    ) -> DatabaseResult:
        """
        Execute a write statement inside the transaction.
        """
        ...

    async def fetchone(
        self,
        query: str,
        params: Params = None,
    ) -> Optional[dict[str, Any]]:
        """
        Fetch one row inside the transaction.
        """
        ...

    async def fetchall(
        self,
        query: str,
        params: Params = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch all rows inside the transaction.
        """
        ...

    async def executemany(
        self,
        query: str,
        parameters: Iterable[Params],
    ) -> DatabaseResult:
        """
        Execute one statement against multiple parameter sets
        inside the transaction.
        """
        ...


# ============================================================================
# TYPE CHECKING HELPERS
# ============================================================================


def normalize_params(
    params: Params,
) -> tuple[Any, ...] | dict[str, Any]:
    """
    Normalize supported parameter containers.

    This helper intentionally does not perform SQL interpolation.

    Positional parameters remain positional.
    Mapping parameters remain mappings.
    """

    if params is None:
        return ()

    if isinstance(params, Mapping):
        return dict(params)

    return tuple(params)