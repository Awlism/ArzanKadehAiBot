# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare D1 backend tests.

Covers:
- parameter binding
- execute result mapping
- fetchone/fetchall row conversion
- executemany batch aggregation
- integrity error normalization
- transaction batching
- transaction read behavior
- transaction write-result contract
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"


def _load_database_modules():
    """
    Load the Worker backend modules directly from src/.

    The package is installed manually here so relative imports inside
    d1_backend.py work without importing the rest of the application.
    """

    package = types.ModuleType("worker_backend")
    package.__path__ = [
        str(SRC_ROOT / "worker_backend")
    ]
    sys.modules["worker_backend"] = package

    database_backend_spec = (
        importlib.util.spec_from_file_location(
            "worker_backend.database_backend",
            SRC_ROOT / "worker_backend" / "database_backend.py",
        )
    )

    if (
        database_backend_spec is None
        or database_backend_spec.loader is None
    ):
        raise RuntimeError(
            "Unable to load database_backend.py"
        )

    database_backend = (
        importlib.util.module_from_spec(
            database_backend_spec
        )
    )

    sys.modules[
        "worker_backend.database_backend"
    ] = database_backend

    database_backend_spec.loader.exec_module(
        database_backend
    )

    d1_spec = importlib.util.spec_from_file_location(
        "worker_backend.d1_backend",
        SRC_ROOT / "worker_backend" / "d1_backend.py",
    )

    if d1_spec is None or d1_spec.loader is None:
        raise RuntimeError(
            "Unable to load d1_backend.py"
        )

    d1_backend = importlib.util.module_from_spec(
        d1_spec
    )

    sys.modules[
        "worker_backend.d1_backend"
    ] = d1_backend

    d1_spec.loader.exec_module(
        d1_backend
    )

    return database_backend, d1_backend


database_backend, d1_backend = _load_database_modules()


def run(coro):
    """
    Run an async test coroutine without requiring pytest.
    """

    loop = asyncio.new_event_loop()

    try:
        return loop.run_until_complete(
            coro
        )
    finally:
        loop.close()


class FakeJSObject:
    """
    Minimal object exposing the to_py() behavior used by Workers SDK
    objects.
    """

    def __init__(
        self,
        value: Any,
    ):
        self._value = value

    def to_py(self):
        return self._value


class FakeD1Statement:
    """
    Fake D1 prepared statement.
    """

    def __init__(
        self,
        database: "FakeD1Database",
        query: str,
    ):
        self.database = database
        self.query = query
        self.params: tuple[Any, ...] = ()

    def bind(self, *params: Any):
        self.params = tuple(params)
        return self

    async def run(self):
        return self.database.run_statement(
            self
        )

    async def first(self):
        return self.database.first_statement(
            self
        )


class FakeD1Database:
    """
    Fake D1 binding covering prepare(), run(), first(), and batch().
    """

    def __init__(self):
        self.prepared: list[
            FakeD1Statement
        ] = []

        self.batch_calls: list[
            list[FakeD1Statement]
        ] = []

        self.rows = [
            {
                "id": 1,
                "name": "کفش",
            },
            {
                "id": 2,
                "name": "کیف",
            },
        ]

        self.run_meta = {
            "changes": 3,
            "last_row_id": 42,
        }

        self.batch_results: list[Any] = []

        self.raise_integrity_on_run = False
        self.raise_integrity_on_first = False
        self.raise_integrity_on_batch = False

    def prepare(
        self,
        query: str,
    ) -> FakeD1Statement:
        statement = FakeD1Statement(
            self,
            query,
        )

        self.prepared.append(
            statement
        )

        return statement

    def run_statement(
        self,
        statement: FakeD1Statement,
    ):
        if self.raise_integrity_on_run:
            raise Exception(
                "UNIQUE constraint failed"
            )

        return FakeJSObject(
            {
                "meta": dict(
                    self.run_meta
                )
            }
        )

    def first_statement(
        self,
        statement: FakeD1Statement,
    ):
        if self.raise_integrity_on_first:
            raise Exception(
                "FOREIGN KEY constraint failed"
            )

        if not self.rows:
            return None

        return FakeJSObject(
            dict(
                self.rows[0]
            )
        )

    async def batch(
        self,
        statements: list[FakeD1Statement],
    ):
        self.batch_calls.append(
            list(statements)
        )

        if self.raise_integrity_on_batch:
            raise Exception(
                "CHECK constraint failed"
            )

        if self.batch_results:
            return FakeJSObject(
                list(
                    self.batch_results
                )
            )

        return FakeJSObject(
            [
                {
                    "meta": {
                        "changes": 1,
                        "last_row_id": 10,
                    }
                }
                for _ in statements
            ]
        )


class D1BackendExecutionTests(
    unittest.TestCase
):
    """
    Tests for direct D1Backend operations.
    """

    def setUp(self):
        self.database = FakeD1Database()
        self.backend = d1_backend.D1Backend(
            self.database
        )

    def test_execute_binds_sequence_parameters_and_maps_meta(self):
        result = run(
            self.backend.execute(
                "INSERT INTO products (name) VALUES (?)",
                ("کفش",),
            )
        )

        self.assertEqual(
            result.rowcount,
            3,
        )

        self.assertEqual(
            result.lastrowid,
            42,
        )

        self.assertEqual(
            self.database.prepared[0].params,
            ("کفش",),
        )

    def test_execute_binds_mapping_parameters(self):
        result = run(
            self.backend.execute(
                "INSERT INTO products (name) VALUES (?)",
                {
                    "name": "کفش",
                },
            )
        )

        self.assertEqual(
            result.rowcount,
            3,
        )

        self.assertEqual(
            self.database.prepared[0].params,
            ("کفش",),
        )

    def test_execute_normalizes_integrity_errors(self):
        self.database.raise_integrity_on_run = True

        with self.assertRaises(
            database_backend.DatabaseIntegrityError
        ):
            run(
                self.backend.execute(
                    "INSERT INTO products (id) VALUES (?)",
                    (1,),
                )
            )

    def test_fetchone_converts_d1_row_to_dict(self):
        result = run(
            self.backend.fetchone(
                "SELECT id, name FROM products WHERE id = ?",
                (1,),
            )
        )

        self.assertEqual(
            result,
            {
                "id": 1,
                "name": "کفش",
            },
        )

    def test_fetchone_returns_none_for_missing_row(self):
        self.database.rows = []

        result = run(
            self.backend.fetchone(
                "SELECT id FROM products WHERE id = ?",
                (999,),
            )
        )

        self.assertIsNone(
            result
        )

    def test_fetchone_normalizes_integrity_errors(self):
        self.database.raise_integrity_on_first = True

        with self.assertRaises(
            database_backend.DatabaseIntegrityError
        ):
            run(
                self.backend.fetchone(
                    "SELECT id FROM products",
                )
            )

    def test_fetchall_extracts_result_rows(self):
        result = run(
            self.backend.fetchall(
                "SELECT id, name FROM products",
            )
        )

        self.assertEqual(
            result,
            [
                {
                    "id": 1,
                    "name": "کفش",
                },
                {
                    "id": 2,
                    "name": "کیف",
                },
            ],
        )

    def test_executemany_batches_all_statements_and_aggregates_results(self):
        self.database.batch_results = [
            {
                "meta": {
                    "changes": 1,
                    "last_row_id": 11,
                }
            },
            {
                "meta": {
                    "changes": 2,
                    "last_row_id": 12,
                }
            },
            {
                "meta": {
                    "changes": 1,
                    "last_row_id": 13,
                }
            },
        ]

        result = run(
            self.backend.executemany(
                "INSERT INTO events (name) VALUES (?)",
                [
                    ("one",),
                    ("two",),
                    ("three",),
                ],
            )
        )

        self.assertEqual(
            result.rowcount,
            4,
        )

        self.assertEqual(
            result.lastrowid,
            13,
        )

        self.assertEqual(
            len(
                self.database.batch_calls
            ),
            1,
        )

        statements = (
            self.database.batch_calls[0]
        )

        self.assertEqual(
            [
                statement.params
                for statement in statements
            ],
            [
                ("one",),
                ("two",),
                ("three",),
            ],
        )

    def test_empty_executemany_does_not_call_batch(self):
        result = run(
            self.backend.executemany(
                "INSERT INTO events (name) VALUES (?)",
                [],
            )
        )

        self.assertEqual(
            result.rowcount,
            0,
        )

        self.assertIsNone(
            result.lastrowid
        )

        self.assertEqual(
            self.database.batch_calls,
            [],
        )

    def test_executemany_normalizes_integrity_errors(self):
        self.database.raise_integrity_on_batch = True

        with self.assertRaises(
            database_backend.DatabaseIntegrityError
        ):
            run(
                self.backend.executemany(
                    "INSERT INTO events (name) VALUES (?)",
                    [
                        ("one",),
                    ],
                )
            )


class D1TransactionTests(
    unittest.TestCase
):
    """
    Tests for the D1 transaction adapter.
    """

    def setUp(self):
        self.database = FakeD1Database()
        self.backend = d1_backend.D1Backend(
            self.database
        )

    def test_transaction_queues_writes_until_exit(self):
        async def scenario():
            async with self.backend.transaction() as tx:
                result = await tx.execute(
                    "INSERT INTO events (name) VALUES (?)",
                    ("one",),
                )

                self.assertEqual(
                    result.rowcount,
                    0,
                )

                self.assertIsNone(
                    result.lastrowid
                )

                self.assertEqual(
                    self.database.batch_calls,
                    [],
                )

            self.assertEqual(
                len(
                    self.database.batch_calls
                ),
                1,
            )

            self.assertEqual(
                len(
                    self.database.batch_calls[0]
                ),
                1,
            )

        run(
            scenario()
        )

    def test_transaction_read_executes_immediately(self):
        async def scenario():
            async with self.backend.transaction() as tx:
                result = await tx.fetchone(
                    "SELECT id, name FROM products WHERE id = ?",
                    (1,),
                )

                self.assertEqual(
                    result,
                    {
                        "id": 1,
                        "name": "کفش",
                    },
                )

                self.assertEqual(
                    self.database.batch_calls,
                    [],
                )

        run(
            scenario()
        )

    def test_transaction_executemany_queues_each_statement(self):
        async def scenario():
            async with self.backend.transaction() as tx:
                result = await tx.executemany(
                    "INSERT INTO events (name) VALUES (?)",
                    [
                        ("one",),
                        ("two",),
                    ],
                )

                self.assertEqual(
                    result.rowcount,
                    0,
                )

                self.assertIsNone(
                    result.lastrowid
                )

            self.assertEqual(
                len(
                    self.database.batch_calls
                ),
                1,
            )

            self.assertEqual(
                [
                    statement.params
                    for statement in self.database.batch_calls[0]
                ],
                [
                    ("one",),
                    ("two",),
                ],
            )

        run(
            scenario()
        )

    def test_transaction_integrity_error_is_normalized(self):
        self.database.raise_integrity_on_batch = True

        async def scenario():
            async with self.backend.transaction() as tx:
                await tx.execute(
                    "INSERT INTO events (name) VALUES (?)",
                    ("one",),
                )

        with self.assertRaises(
            database_backend.DatabaseIntegrityError
        ):
            run(
                scenario()
            )

    def test_transaction_exception_does_not_commit_batch(self):
        async def scenario():
            async with self.backend.transaction() as tx:
                await tx.execute(
                    "INSERT INTO events (name) VALUES (?)",
                    ("one",),
                )

                raise ValueError(
                    "abort transaction"
                )

        with self.assertRaises(
            ValueError
        ):
            run(
                scenario()
            )

        self.assertEqual(
            self.database.batch_calls,
            [],
        )

    def test_transaction_requires_active_context(self):
        tx = self.backend.transaction()

        with self.assertRaises(
            RuntimeError
        ):
            run(
                tx.execute(
                    "SELECT 1"
                )
            )

    def test_transaction_write_result_does_not_expose_batch_lastrowid(self):
        async def scenario():
            async with self.backend.transaction() as tx:
                result = await tx.execute(
                    "INSERT INTO products (name) VALUES (?)",
                    ("کفش",),
                )

                self.assertEqual(
                    result.rowcount,
                    0,
                )

                self.assertIsNone(
                    result.lastrowid
                )

        run(
            scenario()
        )


if __name__ == "__main__":
    unittest.main()