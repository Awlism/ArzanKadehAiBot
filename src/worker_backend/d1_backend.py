
# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare D1 database backend for Python Workers.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .database_backend import (
    DatabaseIntegrityError,
    DatabaseResult,
    DatabaseTransaction,
    Params,
    normalize_params,
)


class D1Transaction:
    """
    D1 transaction adapter.

    Writes are queued and committed atomically with D1 batch().
    Reads execute immediately.
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
                    raise DatabaseIntegrityError(str(exc)) from exc
                raise

            results = _to_python(results)

            if results is None:
                self._batch_results = []
            elif isinstance(results, (list, tuple)):
                self._batch_results = list(results)
            else:
                self._batch_results = [results]

            self._committed = True
            return None
        finally:
            self._active = False
            self._statements = []

    @property
    def results(self) -> tuple[DatabaseResult, ...]:
        """Per-statement results, available only after successful commit."""
        if self._active:
            raise RuntimeError(
                "Transaction results are not available before it exits."
            )

        if not self._committed:
            raise RuntimeError(
                "Transaction did not commit successfully."
            )

        return tuple(
            _result_to_database_result(result)
            for result in self._batch_results
        )

    def _require_active(self) -> None:
        if not self._active:
            raise RuntimeError("Transaction is not active.")

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
                return statement.bind(*normalized.values())
            return statement

        if normalized:
            return statement.bind(*normalized)

        return statement

    async def execute(
        self,
        query: str,
        params: Params = None,
    ) -> DatabaseResult:
        self._statements.append(
            self._prepare(query, params)
        )
        return DatabaseResult()

    async def fetchone(
        self,
        query: str,
        params: Params = None,
    ) -> Optional[dict[str, Any]]:
        statement = self._prepare(query, params)

        try:
            result = await statement.first()
        except Exception as exc:
            if _is_integrity_error(exc):
                raise DatabaseIntegrityError(str(exc)) from exc
            raise

        if result is None:
            return None

        return _to_dict(result)

    async def fetchall(
        self,
        query: str,
        params: Params = None,
    ) -> list[dict[str, Any]]:
        statement = self._prepare(query, params)

        try:
            result = await statement.run()
        except Exception as exc:
            if _is_integrity_error(exc):
                raise DatabaseIntegrityError(str(exc)) from exc
            raise

        return _extract_rows(result)

    async def executemany(
        self,
        query: str,
        parameters: Iterable[Params],
    ) -> DatabaseResult:
        self._require_active()

        for params in parameters:
            self._statements.append(
                self._prepare(query, params)
            )

        return DatabaseResult()


class D1Backend:
    """Cloudflare D1 implementation of the database contract."""

    def __init__(self, database: Any) -> None:
        if database is None:
            raise ValueError("D1 database binding is required.")

        self._database = database
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def close(self) -> None:
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
                return statement.bind(*normalized.values())
            return statement

        if normalized:
            return statement.bind(*normalized)

        return statement

    async def execute(
        self,
        query: str,
        params: Params = None,
    ) -> DatabaseResult:
        """Execute and commit a single statement through D1 batch()."""
        statement = self._prepare(query, params)

        try:
            results = await self._database.batch([statement])
        except Exception as exc:
            if _is_integrity_error(exc):
                raise DatabaseIntegrityError(str(exc)) from exc
            raise

        return _batch_to_database_result(results)

    async def fetchone(
        self,
        query: str,
        params: Params = None,
    ) -> Optional[dict[str, Any]]:
        statement = self._prepare(query, params)

        try:
            result = await statement.first()
        except Exception as exc:
            if _is_integrity_error(exc):
                raise DatabaseIntegrityError(str(exc)) from exc
            raise

        if result is None:
            return None

        return _to_dict(result)

    async def fetchall(
        self,
        query: str,
        params: Params = None,
    ) -> list[dict[str, Any]]:
        statement = self._prepare(query, params)

        try:
            result = await statement.run()
        except Exception as exc:
            if _is_integrity_error(exc):
                raise DatabaseIntegrityError(str(exc)) from exc
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
                    statement = statement.bind(*normalized.values())
            elif normalized:
                statement = statement.bind(*normalized)

            statements.append(statement)

        if not statements:
            return DatabaseResult()

        try:
            results = await database.batch(statements)
        except Exception as exc:
            if _is_integrity_error(exc):
                raise DatabaseIntegrityError(str(exc)) from exc
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


def _to_python(value: Any) -> Any:
    """
    Convert JavaScript/Workers values to Python values when supported.

    Some Workers objects expose only to_py(), rather than Python
    attributes such as results or meta.
    """
    if value is None:
        return None

    converter = getattr(value, "to_py", None)
    if callable(converter):
        try:
            converted = converter()
        except Exception:
            return value

        if converted is not None:
            return converted

    return value


def _to_dict(row: Any) -> dict[str, Any]:
    row = _to_python(row)

    if isinstance(row, dict):
        return dict(row)

    if hasattr(row, "items"):
        return dict(row.items())

    try:
        converted = dict(row)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"Unsupported D1 row type: {type(row)!r}"
        ) from exc

    return converted


def _extract_rows(result: Any) -> list[dict[str, Any]]:
    result = _to_python(result)

    if result is None:
        return []

    if isinstance(result, dict):
        rows = result.get("results", [])
    else:
        rows = getattr(result, "results", [])

    rows = _to_python(rows)

    if rows is None:
        return []

    if isinstance(rows, dict):
        rows = [rows]
    elif not isinstance(rows, (list, tuple)):
        try:
            rows = list(rows)
        except TypeError:
            return []

    return [
        _to_dict(row)
        for row in rows
    ]


def _result_to_database_result(result: Any) -> DatabaseResult:
    meta = _extract_meta(result)

    return DatabaseResult(
        rowcount=_get_int(meta, "changes"),
        lastrowid=_get_optional_int(meta, "last_row_id"),
    )


def _batch_to_database_result(results: Any) -> DatabaseResult:
    results = _to_python(results)

    if results is None:
        return DatabaseResult()

    if not isinstance(results, (list, tuple)):
        return _result_to_database_result(results)

    total_rowcount = 0
    lastrowid: Optional[int] = None

    for result in results:
        converted = _result_to_database_result(result)
        total_rowcount += converted.rowcount

        if converted.lastrowid is not None:
            lastrowid = converted.lastrowid

    return DatabaseResult(
        rowcount=total_rowcount,
        lastrowid=lastrowid,
    )


def _extract_meta(result: Any) -> Any:
    result = _to_python(result)

    if result is None:
        return {}

    if isinstance(result, dict):
        meta = result.get("meta", {})
    else:
        meta = getattr(result, "meta", {})

    meta = _to_python(meta)

    if meta is None:
        return {}

    return meta


def _get_int(mapping: Any, key: str) -> int:
    value = _get_value(mapping, key)

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
    value = _get_value(mapping, key)

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_value(mapping: Any, key: str) -> Any:
    mapping = _to_python(mapping)

    if isinstance(mapping, dict):
        return mapping.get(key)

    if hasattr(mapping, key):
        return getattr(mapping, key)

    if hasattr(mapping, "get"):
        try:
            return mapping.get(key)
        except Exception:
            pass

    return None


def _is_integrity_error(exc: Exception) -> bool:
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
