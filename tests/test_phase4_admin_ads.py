# -*- coding: utf-8 -*-
"""
Phase 4, Chunk 3 (📢 Admin Ads) tests.

Tests the modular admin-ad implementation:
- ad settings persistence
- authorization
- source-level handler coverage
- notification integration
"""

import ast
import asyncio
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from _fakedb import FakeDB, new_conn  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADMIN_PY_PATH = PROJECT_ROOT / "bot" / "handlers" / "admin.py"

AD_KEYS = (
    "ad_enabled",
    "ad_text",
    "ad_button_text",
    "ad_button_url",
)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class AdminAdsStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from bot.database import (
            COLUMN_MIGRATIONS,
            INDEX_STATEMENTS,
            SCHEMA_STATEMENTS,
            run_column_migrations,
        )

        cls.schema_statements = SCHEMA_STATEMENTS
        cls.index_statements = INDEX_STATEMENTS
        cls.column_migrations = COLUMN_MIGRATIONS
        cls.run_column_migrations = run_column_migrations

    def setUp(self):
        self.conn = new_conn()

        for stmt in self.schema_statements:
            self.conn.execute(stmt)

        for stmt in self.index_statements:
            self.conn.execute(stmt)

        self.conn.commit()

        self.fake_db = FakeDB(self.conn)

        import bot.database as database_module
        import bot.handlers.admin as admin_module

        database_module.db = self.fake_db
        admin_module.db = self.fake_db

        run(self.run_column_migrations())

        self.admin_module = admin_module

    def tearDown(self):
        self.conn.close()

    def _table_names(self):
        rows = self.conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table';
            """
        ).fetchall()

        return {row["name"] for row in rows}

    def _column_names(self, table_name):
        rows = self.conn.execute(
            f'PRAGMA table_info("{table_name}");'
        ).fetchall()

        return {row["name"] for row in rows}

    def test_admin_ad_storage_exists(self):
        tables = self._table_names()

        self.assertTrue(
            any(
                "ad" in table.lower()
                for table in tables
            ),
            f"No ad-related storage table found: {tables}",
        )

    def test_ad_storage_has_expected_core_fields(self):
        tables = self._table_names()

        ad_tables = [
            table
            for table in tables
            if "ad" in table.lower()
        ]

        self.assertTrue(ad_tables)

        combined_columns = set()

        for table in ad_tables:
            combined_columns.update(
                self._column_names(table)
            )

        self.assertTrue(
            {"text", "ad_text", "content"}
            & combined_columns,
            f"No ad text field found: {combined_columns}",
        )

    def test_ad_storage_can_persist_text(self):
        tables = self._table_names()

        ad_tables = [
            table
            for table in tables
            if "ad" in table.lower()
        ]

        self.assertTrue(ad_tables)

        persisted = False

        for table in ad_tables:
            columns = self._column_names(table)

            text_column = next(
                (
                    column
                    for column in (
                        "ad_text",
                        "text",
                        "content",
                    )
                    if column in columns
                ),
                None,
            )

            if text_column is None:
                continue

            id_column = (
                "id"
                if "id" in columns
                else None
            )

            if id_column:
                self.conn.execute(
                    f"""
                    INSERT INTO "{table}" (
                        "{id_column}",
                        "{text_column}"
                    )
                    VALUES (?, ?);
                    """,
                    (
                        1,
                        "تبلیغ تستی",
                    ),
                )
            else:
                self.conn.execute(
                    f"""
                    INSERT INTO "{table}" (
                        "{text_column}"
                    )
                    VALUES (?);
                    """,
                    ("تبلیغ تستی",),
                )

            self.conn.commit()

            row = self.conn.execute(
                f"""
                SELECT "{text_column}"
                FROM "{table}"
                LIMIT 1;
                """
            ).fetchone()

            if row and row[0] == "تبلیغ تستی":
                persisted = True
                break

        self.assertTrue(
            persisted,
            "Could not persist ad text in ad storage",
        )


class AdminAdsAuthorizationSourceTests(unittest.TestCase):
    """
    Admin-ad handlers must use the centralized admin authorization.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = ADMIN_PY_PATH.read_text(
            encoding="utf-8"
        )
        cls.tree = ast.parse(
            cls.source,
            filename=str(ADMIN_PY_PATH),
        )

    @staticmethod
    def _function_body(source, tree, name):
        for node in ast.walk(tree):
            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ) and node.name == name:
                lines = source.splitlines()[
                    node.lineno - 1 : node.end_lineno
                ]
                return "\n".join(lines)

        raise AssertionError(
            f"Function '{name}' not found"
        )

    def test_admin_ad_handlers_exist(self):
        names = {
            node.name
            for node in ast.walk(self.tree)
            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
        }

        ad_handlers = {
            name
            for name in names
            if "ad" in name.lower()
        }

        self.assertTrue(
            ad_handlers,
            "No admin-ad handlers were found",
        )

    def test_admin_ad_handlers_are_authorized(self):
        for node in ast.walk(self.tree):
            if not isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                continue

            if "ad" not in node.name.lower():
                continue

            body = self._function_body(
                self.source,
                self.tree,
                node.name,
            )

            self.assertTrue(
                "_is_admin(callback)" in body
                or "is_admin_telegram_id(" in body,
                f"{node.name} must verify admin authorization",
            )

    def test_centralized_is_admin_check_is_used(self):
        body = self._function_body(
            self.source,
            self.tree,
            "_is_admin",
        )

        self.assertIn(
            "is_admin_telegram_id(callback.from_user.id)",
            body,
        )

        self.assertNotIn(
            "ADMIN_CHAT_ID ==",
            body,
        )

        self.assertNotIn(
            "== ADMIN_CHAT_ID",
            body,
        )


class AdminAdsSafetySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ADMIN_PY_PATH.read_text(
            encoding="utf-8"
        )
        cls.tree = ast.parse(
            cls.source,
            filename=str(ADMIN_PY_PATH),
        )

    def test_ad_handlers_do_not_use_eval_or_exec(self):
        tree_source = cls_source = self.source.lower()

        self.assertNotIn(
            "eval(",
            tree_source,
        )
        self.assertNotIn(
            "exec(",
            tree_source,
        )

    def test_ad_url_handling_uses_existing_url_validation(self):
        ad_related = []

        for node in ast.walk(self.tree):
            if not isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                continue

            if "ad" not in node.name.lower():
                continue

            lines = self.source.splitlines()[
                node.lineno - 1 : node.end_lineno
            ]

            ad_related.append(
                "\n".join(lines)
            )

        combined = "\n".join(ad_related)

        if "url" in combined.lower():
            self.assertTrue(
                any(
                    name in combined
                    for name in (
                        "_normalize_url",
                        "normalize_url",
                        "is_valid_url",
                    )
                ),
                "Ad URL handling must use centralized URL validation",
            )


if __name__ == "__main__":
    unittest.main()