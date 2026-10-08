# -*- coding: utf-8 -*-
"""
Static tests for current role, favorites and compare Worker modules.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / "src" / "worker"


def source(name: str) -> str:
    return (
        WORKER / name
    ).read_text(encoding="utf-8")


def functions(name: str) -> set[str]:
    tree = ast.parse(source(name))

    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
    }


class CompareWorkerTests(unittest.TestCase):
    def test_compare_file_exists(self):
        self.assertTrue(
            (WORKER / "compare.py").is_file()
        )

    def test_compare_max_items_is_four(self):
        text = source("compare.py")

        self.assertIn(
            "COMPARE_MAX_ITEMS = 4",
            text,
        )

    def test_compare_storage_is_dedicated(self):
        text = source("compare.py")

        self.assertIn(
            "compare_selections",
            text,
        )

    def test_compare_add_is_present(self):
        names = functions("compare.py")

        self.assertIn(
            "handle_compare_add",
            names,
        )

    def test_compare_reset_is_present(self):
        names = functions("compare.py")

        self.assertIn(
            "handle_compare_reset",
            names,
        )

    def test_compare_event_is_present(self):
        text = source("compare.py")

        self.assertIn(
            '"compare_add"',
            text,
        )


class FavoritesWorkerTests(unittest.TestCase):
    def test_favorites_file_exists(self):
        self.assertTrue(
            (WORKER / "favorites.py").is_file()
        )

    def test_product_favorites_table_is_used(self):
        text = source("favorites.py")

        self.assertIn(
            "favorites",
            text,
        )

    def test_favorites_module_has_handlers(self):
        names = functions("favorites.py")

        self.assertTrue(
            any(
                "favorite" in name
                for name in names
            )
        )

    def test_favorites_has_no_sqlite(self):
        text = source("favorites.py")

        self.assertNotIn("sqlite3", text)
        self.assertNotIn("aiosqlite", text)


class CurrentArchitectureTests(unittest.TestCase):
    def test_no_legacy_imports(self):
        for name in (
            "compare.py",
            "favorites.py",
        ):
            text = source(name)

            self.assertNotIn(
                "aiogram",
                text,
            )
            self.assertNotIn(
                "aiosqlite",
                text,
            )
            self.assertNotIn(
                "sqlite3",
                text,
            )


if __name__ == "__main__":
    unittest.main()