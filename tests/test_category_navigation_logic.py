# -*- coding: utf-8 -*-
"""
Static tests for the current Worker category navigation implementation.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "src" / "worker" / "categories.py"


class CategoryWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_file_exists(self):
        self.assertTrue(PATH.is_file())

    def test_category_handler_exists(self):
        names = {
            node.name
            for node in ast.walk(self.tree)
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
        }

        self.assertIn(
            "handle_category",
            names,
        )

    def test_pagination_constants_exist(self):
        self.assertIn(
            "PAGE_SIZE_CATEGORIES",
            self.source,
        )
        self.assertIn(
            "PAGE_SIZE_PRODUCTS",
            self.source,
        )

    def test_category_callback_format_exists(self):
        self.assertIn(
            'f"cat:{row[\'id\']}:0"',
            self.source,
        )

    def test_root_category_query_exists(self):
        self.assertIn(
            "WHERE parent_id IS NULL",
            self.source,
        )

    def test_child_category_query_exists(self):
        self.assertIn(
            "WHERE parent_id = ?",
            self.source,
        )

    def test_product_query_uses_active_seller(self):
        self.assertIn(
            "COALESCE(s.is_active, 1) = 1",
            self.source,
        )

    def test_category_click_event_exists(self):
        self.assertIn(
            '"category_click"',
            self.source,
        )

    def test_invalid_callback_is_handled(self):
        self.assertIn(
            "درخواست نامعتبر است",
            self.source,
        )

    def test_no_legacy_runtime_import(self):
        self.assertNotIn("aiogram", self.source)
        self.assertNotIn("aiosqlite", self.source)
        self.assertNotIn("sqlite3", self.source)


if __name__ == "__main__":
    unittest.main()