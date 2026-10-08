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


class AdminUsersWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PATH.read_text(
            encoding="utf-8"
        )
        cls.tree = ast.parse(
            cls.source
        )

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

    def test_admin_home_exists(self):
        names = {
            node.name
            for node in ast.walk(self.tree)
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
        }

        self.assertTrue(
            any(
                name.startswith("handle_admin")
                for name in names
            )
        )

    def test_admin_request_flow_is_in_same_worker_module(self):
        self.assertIn(
            "handle_admin_request_decision",
            self.source,
        )

    def test_audit_log_is_available(self):
        self.assertIn(
            "audit_log",
            self.source,
        )

    def test_no_legacy_runtime(self):
        self.assertNotIn(
            "aiogram",
            self.source,
        )
        self.assertNotIn(
            "sqlite3",
            self.source,
        )
        self.assertNotIn(
            "aiosqlite",
            self.source,
        )

    def test_no_import_from_legacy_bot_handlers(self):
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