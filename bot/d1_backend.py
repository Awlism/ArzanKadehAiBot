# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare D1 database backend

Concrete Cloudflare D1 implementation of the generic DatabaseBackend
contract.

IMPORTANT:
- This module is intended for the Cloudflare Python Worker runtime.
- It must not import aiosqlite or the SQLite database module.
- Application/repository code should depend on DatabaseBackend instead.
- D1 uses prepared statements with bound parameters.
- D1Database.batch() is used for atomic multi-statement writes.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .database_backend import (
    DatabaseBackend,
    DatabaseIntegrityError,
    DatabaseResult,
    DatabaseTransaction,
    Params,
    normalize_params,
)


class D1Transaction:
    """
    Transaction adapter for Cloudflare D1.

    Cloudflare D1 does not expose SQLite-style BEGIN/COMMIT statements
    through the Worker Binding API.

    Therefore:

    - write statements are queued;
    - the queued statements are committed atomically with batch();
    - if the context exits with an exception, nothing is committed;
    - read operations are executed immediately against D1 and are NOT
      part of the atomic batch.

    This distinction is intentional. A D1 batch can atomically execute
    multiple statements, but it cannot use the result of one statement
    to dynamically construct later statements inside the same batch.
    """

    def __init__(
        self,
        database: Any,
        *,
        immediate: bool = False,
    ) -> None:
        self._database = database
        self._immediate = immediate

        self._statements: list[Any] = []
        self._batch_results: list[Any] = []

        self._active = False
        self._committed = False

    async def __aenter__(self) -> "D1Transaction":
        if self._active:
            raise RuntimeError("Transaction is already active.")

        self._active = True
        self._committed = False
        self._statements = []
        self._batch_results = []

        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> Optional[bool]:
        try:
            if exc_type is not None:
                return None

            if not self._statements:
                self._committed = True
                return None

            try:
                results = await self._database.batch(
                    self._statements
                )
            except Exception as exc:
                if _is_integrity_error(exc):
                    raise DatabaseIntegrityError(
                        str(exc)
                    ) from exc

                raise

            if results is None:
                self._batch_results = []
            elif hasattr(results, "to_py"):
                converted = results.to_py()

                if isinstance(converted, (list, tuple)):
                    self._batch_results = list(converted)
                else:
                    self._batch_results = [converted]
            elif isinstance(results, (list, tuple)):
                self._batch_results = list(results)
            else:
                self._batch_results = [results]

            self._committed = True

            return None

        finally:
            self._active = False
            self._statements = []

    def _require_active(self) -> None:
        if not self._active:
            raise RuntimeError(
                "Transaction is not active."
            )

    def _prepare(
        self,
        query: str,
        params: Params = None,
    ) -> Any:
        self._require_active()

        statement = self._database.prepare(query)
        normalized = normalize_params(params)

        if isinstance(normalized, dict):
            if normalized:
                return statement.bind(
                    *normalized.values()
                )

            return statement

        if normalized:
            return statement.bind(*normalized)

        return statement

    async def execute(
        self,
        query: str,
        params: Params = None,
    ) -> DatabaseResult:
        """
        Queue a write statement for the final D1 batch.

        The statement is NOT executed immediately.

        Consequently rowcount/lastrowid are not available at this point.
        The actual D1 results become available only after the context
        manager commits the batch.
        """
        statement = self._prepare(
            query,
            params,
        )

        self._statements.append(statement)

        return DatabaseResult()

    async def fetchone(
        self,
        query: str,
        params: Params = None,
    ) -> Optional[dict[str, Any]]:
        """
        Execute a read immediately.

        D1 batch() cannot expose the result of one statement to Python
        before subsequent statements in the same batch are constructed.
        Therefore reads are intentionally executed outside the queued
        write batch.
        """
        statement = self._prepare(
            query,
            params,
        )

        try:
            result = await statement.first()
        except Exception as exc:
            if _is_integrity_error(exc):
                raise DatabaseIntegrityError(
                    str(exc)
                ) from exc

            raise

        if result is None:
            return None

        return _to_dict(result)

    async def fetchall(
        self,
        query: str,
        params: Params = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a read immediately.

        See fetchone() for the D1 transaction limitation.
        """
        statement = self._prepare(
            query,
            params,
        )

        try:
            result = await statement.run()
        except Exception as exc:
            if _is_integrity_error(exc):
                raise DatabaseIntegrityError(
                    str(exc)
                ) from exc

            raise

        return _extract_rows(result)

    async def executemany(
        self,
        query: str,
        parameters: Iterable[Params],
    ) -> DatabaseResult:
        """
        Queue multiple write statements for one atomic D1 batch.
        """
        self._require_active()

        for params in parameters:
            statement = self._prepare(
                query,
                params,
            )

            self._statements.append(statement)

        return DatabaseResult()


class D1Backend:
    """
    Cloudflare D1 implementation of DatabaseBackend.

    The Worker environment supplies the D1 binding. The backend receives
    that binding explicitly so it does not depend on the Worker entrypoint.
    """

    def __init__(self, database: Any) -> None:
        if database is None:
            raise ValueError(
                "D1 database binding is required."
            )

        self._database = database
        self._connected = False

    async def connect(self) -> None:
        """
        D1 bindings do not require an explicit connection.

        This method exists to satisfy the shared DatabaseBackend contract.
        """
        self._connected = True

    async def close(self) -> None:
        """
        D1 bindings do not require an explicit close operation.
        """
        self._connected = False

    def _require_database(self) -> Any:
        if self._database is None:
            raise RuntimeError(
                "D1 database binding is not available."
            )

        return self._database

    def _prepare(
        self,
        query: str,
        params: Params = None,
    ) -> Any:
        database = self._require_database()

        statement = database.prepare(query)
        normalized = normalize_params(params)

        if isinstance(normalized, dict):
            if normalized:
                return statement.bind(
                    *normalized.values()
                )

            return statement

        if normalized:
            return statement.bind(*normalized)

        return statement

    async def execute(
        self,
        query: str,
        params: Params = None,
    ) -> DatabaseResult:
        statement = self._prepare(
            query,
            params,
        )

        try:
            result = await statement.run()
        except Exception as exc:
            if _is_integrity_error(exc):
                raise DatabaseIntegrityError(
                    str(exc)
                ) from exc

            raise

        return _result_to_database_result(result)

    async def fetchone(
        self,
        query: str,
        params: Params = None,
    ) -> Optional[dict[str, Any]]:
        statement = self._prepare(
            query,
            params,
        )

        try:
            result = await statement.first()
        except Exception as exc:
            if _is_integrity_error(exc):
                raise DatabaseIntegrityError(
                    str(exc)
                ) from exc

            raise

        if result is None:
            return None

        return _to_dict(result)

    async def fetchall(
        self,
        query: str,
        params: Params = None,
    ) -> list[dict[str, Any]]:
        statement = self._prepare(
            query,
            params,
        )

        try:
            result = await statement.run()
        except Exception as exc:
            if _is_integrity_error(exc):
                raise DatabaseIntegrityError(
                    str(exc)
                ) from exc

            raise

        return _extract_rows(result)

    async def executemany(
        self,
        query: str,
        parameters: Iterable[Params],
    ) -> DatabaseResult:
        database = self._require_database()

        statements: list[Any] = []

        for params in parameters:
            statement = database.prepare(query)
            normalized = normalize_params(params)

            if isinstance(normalized, dict):
                if normalized:
                    statement = statement.bind(
                        *normalized.values()
                    )
            elif normalized:
                statement = statement.bind(*normalized)

            statements.append(statement)

        if not statements:
            return DatabaseResult()

        try:
            results = await database.batch(
                statements
            )
        except Exception as exc:
            if _is_integrity_error(exc):
                raise DatabaseIntegrityError(
                    str(exc)
                ) from exc

            raise

        return _batch_to_database_result(results)

    def transaction(
        self,
        *,
        immediate: bool = False,
    ) -> DatabaseTransaction:
        return D1Transaction(
            self._require_database(),
            immediate=immediate,
        )


def _to_dict(row: Any) -> dict[str, Any]:
    """
    Convert a D1 row object into a normal Python dictionary.
    """
    if isinstance(row, dict):
        return dict(row)

    if hasattr(row, "to_py"):
        converted = row.to_py()

        if isinstance(converted, dict):
            return dict(converted)

    if hasattr(row, "items"):
        return dict(row.items())

    try:
        return dict(row)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"Unsupported D1 row type: {type(row)!r}"
        ) from exc


def _extract_rows(result: Any) -> list[dict[str, Any]]:
    """
    Extract rows from a D1Result returned by statement.run().
    """
    if result is None:
        return []

    if hasattr(result, "results"):
        rows = result.results
    elif isinstance(result, dict):
        rows = result.get(
            "results",
            [],
        )
    else:
        rows = []

    if hasattr(rows, "to_py"):
        rows = rows.to_py()

    if rows is None:
        return []

    return [
        _to_dict(row)
        for row in rows
    ]


def _result_to_database_result(
    result: Any,
) -> DatabaseResult:
    """
    Convert a D1Result metadata object into DatabaseResult.
    """
    meta = _extract_meta(result)

    return DatabaseResult(
        rowcount=_get_int(
            meta,
            "changes",
        ),
        lastrowid=_get_optional_int(
            meta,
            "last_row_id",
        ),
    )


def _batch_to_database_result(
    results: Any,
) -> DatabaseResult:
    """
    Convert the result list returned by D1Database.batch().
    """
    if results is None:
        return DatabaseResult()

    if hasattr(results, "to_py"):
        results = results.to_py()

    if not isinstance(
        results,
        (list, tuple),
    ):
        return _result_to_database_result(
            results
        )

    total_rowcount = 0
    lastrowid: Optional[int] = None

    for result in results:
        converted = _result_to_database_result(
            result
        )

        total_rowcount += converted.rowcount

        if converted.lastrowid is not None:
            lastrowid = converted.lastrowid

    return DatabaseResult(
        rowcount=total_rowcount,
        lastrowid=lastrowid,
    )


def _extract_meta(result: Any) -> Any:
    if result is None:
        return {}

    if hasattr(result, "meta"):
        return result.meta

    if isinstance(result, dict):
        return result.get(
            "meta",
            {},
        )

    return {}


def _get_int(
    mapping: Any,
    key: str,
) -> int:
    value = _get_value(
        mapping,
        key,
    )

    if value is None:
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _get_optional_int(
    mapping: Any,
    key: str,
) -> Optional[int]:
    value = _get_value(
        mapping,
        key,
    )

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_value(
    mapping: Any,
    key: str,
) -> Any:
    if isinstance(mapping, dict):
        return mapping.get(key)

    if hasattr(mapping, key):
        return getattr(
            mapping,
            key,
        )

    if hasattr(mapping, "to_py"):
        converted = mapping.to_py()

        if isinstance(converted, dict):
            return converted.get(key)

    return None


def _is_integrity_error(
    exc: Exception,
) -> bool:
    """
    Detect D1/SQLite constraint errors without importing SQLite.

    D1 errors are surfaced through the Worker runtime, so we intentionally
    avoid depending on a runtime-specific exception class here.
    """
    message = str(exc).lower()

    integrity_markers = (
        "constraint",
        "unique",
        "not null",
        "foreign key",
        "primary key",
        "check constraint",
    )

    return any(
        marker in message
        for marker in integrity_markers
    )


__all__ = [
    "D1Backend",
    "D1Transaction",
]