# -*- coding: utf-8 -*-
"""
Static tests for the current Worker admin-request implementation.
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


class AdminRequestWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PATH.read_text(
            encoding="utf-8"
        )
        cls.tree = ast.parse(cls.source)

    def test_file_exists(self):
        self.assertTrue(PATH.is_file())

    def test_admin_request_decision_handler_exists(self):
        names = {
            node.name
            for node in ast.walk(self.tree)
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
        }

        self.assertIn(
            "handle_admin_request_decision",
            names,
        )

    def test_request_decision_callbacks_are_supported_by_entry_contract(self):
        self.assertIn(
            "handle_admin_request_decision",
            self.source,
        )

    def test_support_request_type_exists(self):
        self.assertIn(
            '"support"',
            self.source,
        )

    def test_request_table_is_used(self):
        self.assertIn(
            "requests",
            self.source,
        )

    def test_pending_guard_exists(self):
        self.assertIn(
            "PENDING",
            self.source,
        )

    def test_audit_logging_exists(self):
        self.assertIn(
            "audit_log",
            self.source,
        )

    def test_notification_flow_exists(self):
        self.assertIn(
            "notifications",
            self.source,
        )

    def test_ad_requests_delegate_to_admin_ads(self):
        self.assertIn(
            "handle_admin_ad_decision",
            self.source,
        )

    def test_no_legacy_imports(self):
        modules = imported_modules(self.tree)

        self.assertNotIn("aiogram", modules)
        self.assertNotIn("aiosqlite", modules)
        self.assertNotIn("sqlite3", modules)


if __name__ == "__main__":
    unittest.main()