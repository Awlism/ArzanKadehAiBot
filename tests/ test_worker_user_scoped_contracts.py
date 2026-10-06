# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker user-scoped security contract tests.

These tests inspect the migrated Worker source directly and verify
that user-sensitive database operations remain scoped to the
authenticated/internal user.

Covered:
- Review uniqueness is user-scoped.
- Review insert contains user_id.
- Product review and seller review use separate target columns.
- Report uniqueness is user-scoped.
- Report insert contains user_id.
- Notification listing is user-scoped.
- Notification read update is scoped by notification id + user_id.
- Notification handlers resolve the internal user from Telegram ID.
- No legacy aiogram/sqlite imports are introduced in these modules.

These are source-contract tests and do not contact D1 or Telegram.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src" / "worker"


REVIEW_FILE = SRC_ROOT / "review.py"
REPORT_FILE = SRC_ROOT / "report.py"
NOTIFICATIONS_FILE = SRC_ROOT / "notifications.py"


def _read(path: Path) -> str:
    return path.read_text(
        encoding="utf-8"
    )


def _tree(path: Path) -> ast.AST:
    return ast.parse(
        _read(path),
        filename=str(path),
    )


def _normalized_sql(sql: str) -> str:
    return " ".join(
        sql.split()
    ).lower()


def _string_constants(
    node: ast.AST,
) -> list[str]:
    values: list[str] = []

    for child in ast.walk(node):
        if isinstance(
            child,
            ast.Constant,
        ) and isinstance(
            child.value,
            str,
        ):
            values.append(
                child.value
            )

    return values


def _sql_strings(
    path: Path,
) -> list[str]:
    result: list[str] = []

    tree = _tree(path)

    for node in ast.walk(tree):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        if not isinstance(
            node.func,
            ast.Attribute,
        ):
            continue

        if node.func.attr not in {
            "execute",
            "fetchone",
            "fetchall",
            "executemany",
        }:
            continue

        if not node.args:
            continue

        first = node.args[0]

        if isinstance(
            first,
            ast.Constant,
        ) and isinstance(
            first.value,
            str,
        ):
            result.append(
                first.value
            )

    return result


def _function(
    path: Path,
    name: str,
) -> ast.AsyncFunctionDef | ast.FunctionDef:
    tree = _tree(path)

    for node in ast.walk(tree):
        if isinstance(
            node,
            (
                ast.AsyncFunctionDef,
                ast.FunctionDef,
            ),
        ) and node.name == name:
            return node

    raise AssertionError(
        f"Function {name!r} not found in {path}"
    )


def _function_sql(
    path: Path,
    name: str,
) -> list[str]:
    node = _function(
        path,
        name,
    )

    values = _string_constants(
        node
    )

    return [
        value
        for value in values
        if any(
            keyword in value.upper()
            for keyword in (
                "SELECT",
                "INSERT",
                "UPDATE",
                "DELETE",
                "FROM",
                "WHERE",
            )
        )
    ]


class WorkerUserScopedContractTests(
    unittest.TestCase
):
    def test_review_has_internal_user_lookup_by_telegram_id(self):
        source = _read(
            REVIEW_FILE
        )

        normalized = _normalized_sql(
            source
        )

        self.assertIn(
            "select id",
            normalized,
        )

        self.assertIn(
            "from users",
            normalized,
        )

        self.assertIn(
            "where telegram_id = ?",
            normalized,
        )

    def test_product_review_duplicate_check_is_user_scoped(self):
        sql = "\n".join(
            _function_sql(
                REVIEW_FILE,
                "_has_existing_review",
            )
        )

        normalized = _normalized_sql(
            sql
        )

        self.assertIn(
            "from reviews",
            normalized,
        )

        self.assertIn(
            "where user_id = ?",
            normalized,
        )

        self.assertIn(
            "and product_id = ?",
            normalized,
        )

        self.assertIn(
            "seller_id is null",
            normalized,
        )

    def test_seller_review_duplicate_check_is_user_scoped(self):
        sql = "\n".join(
            _function_sql(
                REVIEW_FILE,
                "_has_existing_review",
            )
        )

        normalized = _normalized_sql(
            sql
        )

        self.assertIn(
            "where user_id = ?",
            normalized,
        )

        self.assertIn(
            "and seller_id = ?",
            normalized,
        )

        self.assertIn(
            "product_id is null",
            normalized,
        )

    def test_review_insert_contains_user_id(self):
        sql = "\n".join(
            _sql_strings(
                REVIEW_FILE
            )
        )

        normalized = _normalized_sql(
            sql
        )

        self.assertIn(
            "insert into reviews",
            normalized,
        )

        match = re.search(
            r"insert\s+into\s+reviews\s*\((.*?)\)",
            normalized,
            re.DOTALL,
        )

        self.assertIsNotNone(
            match
        )

        columns = match.group(1)

        self.assertIn(
            "user_id",
            columns,
        )

    def test_review_insert_supports_product_and_seller_targets(self):
        sql = "\n".join(
            _sql_strings(
                REVIEW_FILE
            )
        )

        normalized = _normalized_sql(
            sql
        )

        self.assertIn(
            "product_id",
            normalized,
        )

        self.assertIn(
            "seller_id",
            normalized,
        )

    def test_review_state_is_user_specific(self):
        start_source = _read(
            REVIEW_FILE
        )

        normalized = _normalized_sql(
            start_source
        )

        self.assertIn(
            "set_state",
            normalized,
        )

        self.assertIn(
            "get_state",
            normalized,
        )

        self.assertIn(
            "clear_state",
            normalized,
        )

        state_calls = [
            node
            for node in ast.walk(
                _tree(REVIEW_FILE)
            )
            if isinstance(
                node,
                ast.Call,
            )
            and isinstance(
                node.func,
                ast.Name,
            )
            and node.func.id
            in {
                "set_state",
                "get_state",
                "clear_state",
            }
        ]

        self.assertGreaterEqual(
            len(state_calls),
            3,
        )

    def test_report_has_internal_user_lookup_by_telegram_id(self):
        source = _read(
            REPORT_FILE
        )

        normalized = _normalized_sql(
            source
        )

        self.assertIn(
            "from users",
            normalized,
        )

        self.assertIn(
            "where telegram_id = ?",
            normalized,
        )

    def test_report_open_check_is_user_scoped(self):
        sql = "\n".join(
            _function_sql(
                REPORT_FILE,
                "_has_open_report",
            )
        )

        normalized = _normalized_sql(
            sql
        )

        self.assertIn(
            "from reports",
            normalized,
        )

        self.assertIn(
            "where user_id = ?",
            normalized,
        )

        self.assertTrue(
            (
                "seller_id = ?"
                in normalized
            )
            or (
                "product_id = ?"
                in normalized
            )
        )

    def test_report_insert_contains_user_id(self):
        sql = "\n".join(
            _sql_strings(
                REPORT_FILE
            )
        )

        normalized = _normalized_sql(
            sql
        )

        self.assertIn(
            "insert into reports",
            normalized,
        )

        match = re.search(
            r"insert\s+into\s+reports\s*\((.*?)\)",
            normalized,
            re.DOTALL,
        )

        self.assertIsNotNone(
            match
        )

        columns = match.group(1)

        self.assertIn(
            "user_id",
            columns,
        )

    def test_report_insert_supports_product_and_seller_targets(self):
        sql = "\n".join(
            _sql_strings(
                REPORT_FILE
            )
        )

        normalized = _normalized_sql(
            sql
        )

        self.assertIn(
            "seller_id",
            normalized,
        )

        self.assertIn(
            "product_id",
            normalized,
        )

    def test_report_flow_uses_persistent_user_state(self):
        source = _read(
            REPORT_FILE
        )

        normalized = _normalized_sql(
            source
        )

        self.assertIn(
            "get_state",
            normalized,
        )

        self.assertIn(
            "set_state",
            normalized,
        )

        self.assertIn(
            "clear_state",
            normalized,
        )

    def test_notification_listing_is_user_scoped(self):
        sql = "\n".join(
            _sql_strings(
                NOTIFICATIONS_FILE
            )
        )

        normalized = _normalized_sql(
            sql
        )

        self.assertIn(
            "from notifications",
            normalized,
        )

        self.assertIn(
            "where user_id = ?",
            normalized,
        )

    def test_notification_read_update_is_user_scoped(self):
        sql = "\n".join(
            _sql_strings(
                NOTIFICATIONS_FILE
            )
        )

        normalized = _normalized_sql(
            sql
        )

        match = re.search(
            r"update\s+notifications.*?"
            r"where\s+id\s*=\s*\?"
            r".*?"
            r"and\s+user_id\s*=\s*\?"
            r".*?"
            r"and\s+is_read\s*=\s*0",
            normalized,
            re.DOTALL,
        )

        self.assertIsNotNone(
            match,
            (
                "Notification read update must "
                "be scoped by notification id, "
                "user_id, and unread state."
            ),
        )

    def test_notification_handlers_resolve_internal_user(self):
        source = _read(
            NOTIFICATIONS_FILE
        )

        tree = _tree(
            NOTIFICATIONS_FILE
        )

        ensure_user = _function(
            NOTIFICATIONS_FILE,
            "_ensure_user",
        )

        ensure_source = ast.get_source_segment(
            source,
            ensure_user,
        )

        self.assertIsNotNone(
            ensure_source
        )

        ensure_normalized = _normalized_sql(
            ensure_source or ""
        )

        self.assertIn(
            "insert into users",
            ensure_normalized,
        )

        self.assertIn(
            "telegram_id",
            ensure_normalized,
        )

        self.assertIn(
            "where telegram_id = ?",
            ensure_normalized,
        )

        handler_names = {
            "handle_notifications",
            "handle_notification_read",
        }

        for node in ast.walk(tree):
            if not isinstance(
                node,
                ast.AsyncFunctionDef,
            ):
                continue

            if node.name not in handler_names:
                continue

            calls = [
                call
                for call in ast.walk(node)
                if isinstance(
                    call,
                    ast.Call,
                )
                and isinstance(
                    call.func,
                    ast.Name,
                )
                and call.func.id
                == "_ensure_user"
            ]

            self.assertGreaterEqual(
                len(calls),
                1,
                (
                    f"{node.name} must resolve "
                    "the internal user."
                ),
            )

    def test_notification_limit_is_defined(self):
        source = _read(
            NOTIFICATIONS_FILE
        )

        tree = _tree(
            NOTIFICATIONS_FILE
        )

        found = False

        for node in tree.body:
            if not isinstance(
                node,
                ast.Assign,
            ):
                continue

            for target in node.targets:
                if not isinstance(
                    target,
                    ast.Name,
                ):
                    continue

                if target.id != (
                    "NOTIFICATION_LIMIT"
                ):
                    continue

                self.assertIsInstance(
                    node.value,
                    ast.Constant,
                )

                self.assertEqual(
                    node.value.value,
                    20,
                )

                found = True

        self.assertTrue(
            found
        )

    def test_user_scoped_modules_have_no_legacy_database_imports(self):
        forbidden = {
            "aiogram",
            "sqlite3",
            "aiosqlite",
        }

        for path in (
            REVIEW_FILE,
            REPORT_FILE,
            NOTIFICATIONS_FILE,
        ):
            tree = _tree(
                path
            )

            imports: list[str] = []

            for node in ast.walk(
                tree
            ):
                if isinstance(
                    node,
                    ast.Import,
                ):
                    imports.extend(
                        alias.name
                        for alias in node.names
                    )

                elif isinstance(
                    node,
                    ast.ImportFrom,
                ):
                    if node.module:
                        imports.append(
                            node.module
                        )

            for imported in imports:
                root = imported.split(
                    ".",
                    1,
                )[0]

                self.assertNotIn(
                    root,
                    forbidden,
                    f"Forbidden legacy import {imported!r} in {path}",
                )

    def test_review_target_parser_rejects_invalid_target_types(self):
        source = _read(
            REVIEW_FILE
        )

        self.assertIn(
            '"product"',
            source,
        )

        self.assertIn(
            '"seller"',
            source,
        )

        self.assertIn(
            "target_id < 1",
            source,
        )

    def test_report_flow_checks_existing_open_report_before_save(self):
        source = _read(
            REPORT_FILE
        )

        normalized = _normalized_sql(
            source
        )

        self.assertIn(
            "_has_open_report",
            normalized,
        )

        self.assertIn(
            "an open report already exists.",
            normalized,
        )

    def test_notification_read_requires_unread_status(self):
        sql = "\n".join(
            _sql_strings(
                NOTIFICATIONS_FILE
            )
        )

        normalized = _normalized_sql(
            sql
        )

        self.assertIn(
            "is_read = 0",
            normalized,
        )

    def test_notification_queries_use_internal_user_id_not_telegram_id(self):
        sql = "\n".join(
            _sql_strings(
                NOTIFICATIONS_FILE
            )
        )

        normalized = _normalized_sql(
            sql
        )

        self.assertIn(
            "where user_id = ?",
            normalized,
        )

        # The notification table must not be filtered directly
        # by Telegram ID because its foreign key is internal users.id.
        notification_section = normalized[
            normalized.find(
                "from notifications"
            ):
        ]

        self.assertNotIn(
            "where telegram_id = ?",
            notification_section,
        )


if __name__ == "__main__":
    unittest.main()