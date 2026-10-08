# -*- coding: utf-8 -*-
"""
Static tests for the current seller active/inactive Worker flow.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "src" / "worker" / "store_status.py"


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


class StoreStatusWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PATH.read_text(
            encoding="utf-8"
        )
        cls.tree = ast.parse(cls.source)

    def test_file_exists(self):
        self.assertTrue(PATH.is_file())

    def test_handler_functions_exist(self):
        functions = {
            node.name
            for node in ast.walk(self.tree)
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
        }

        for expected in (
            "handle_store_status",
            "handle_store_status_picked",
            "handle_store_toggle_active",
        ):
            self.assertIn(
                expected,
                functions,
            )

    def test_store_toggle_callback_is_present(self):
        self.assertIn(
            "storetoggle:",
            self.source,
        )

    def test_is_active_column_is_used(self):
        self.assertIn(
            "is_active",
            self.source,
        )

    def test_owner_check_is_present(self):
        self.assertIn(
            "owner_user_id",
            self.source,
        )

    def test_database_update_is_present(self):
        self.assertIn(
            "UPDATE sellers",
            self.source,
        )

    def test_audit_logging_is_present(self):
        self.assertIn(
            "audit_log",
            self.source,
        )

    def test_no_legacy_imports(self):
        modules = imported_modules(self.tree)

        self.assertNotIn("aiogram", modules)
        self.assertNotIn("aiosqlite", modules)
        self.assertNotIn("sqlite3", modules)


if __name__ == "__main__":
    unittest.main()