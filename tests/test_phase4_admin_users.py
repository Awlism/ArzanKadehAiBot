# -*- coding: utf-8 -*-
"""
Static tests for the current Worker admin/user implementation.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "src" / "worker" / "admin.py"


def imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)

    return modules


class AdminUsersWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PATH.read_text(
            encoding="utf-8"
        )
        cls.tree = ast.parse(cls.source)

    def test_file_exists(self):
        self.assertTrue(PATH.is_file())

    def test_admin_module_is_parseable(self):
        self.assertIsInstance(
            self.tree,
            ast.Module,
        )

    def test_user_table_is_used(self):
        self.assertIn(
            "users",
            self.source,
        )

    def test_admin_authorization_is_present(self):
        self.assertIn(
            "ADMIN",
            self.source,
        )

    def test_admin_user_handlers_exist(self):
        names = {
            node.name
            for node in ast.walk(self.tree)
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
        }

        for expected in (
            "handle_admin_home",
            "handle_admin_users_menu",
            "handle_admin_user_search_start",
            "handle_admin_user_search_message",
            "handle_admin_user_list",
            "handle_admin_user_view",
        ):
            self.assertIn(
                expected,
                names,
            )

    def test_admin_request_flow_exists(self):
        self.assertIn(
            "handle_admin_request_decision",
            self.source,
        )

    def test_audit_log_is_available(self):
        self.assertIn(
            "audit_log",
            self.source,
        )

    def test_no_legacy_imports(self):
        modules = imported_modules(self.tree)

        self.assertNotIn("aiogram", modules)
        self.assertNotIn("aiosqlite", modules)
        self.assertNotIn("sqlite3", modules)

    def test_no_legacy_bot_imports(self):
        self.assertNotIn(
            "bot.handlers",
            self.source,
        )
        self.assertNotIn(
            "bot.services",
            self.source,
        )


if __name__ == "__main__":
    unittest.main()