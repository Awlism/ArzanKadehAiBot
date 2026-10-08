# -*- coding: utf-8 -*-
"""
Static tests for current compare and favorites Worker modules.
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
    ).read_text(
        encoding="utf-8"
    )


def tree(name: str) -> ast.AST:
    return ast.parse(
        source(name)
    )


def functions(name: str) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree(name))
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
    }


def imported_modules(name: str) -> set[str]:
    modules: set[str] = set()

    for node in ast.walk(tree(name)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)

    return modules


class CompareWorkerTests(unittest.TestCase):
    def test_compare_file_exists(self):
        self.assertTrue(
            (WORKER / "compare.py").is_file()
        )

    def test_compare_max_items_is_four(self):
        self.assertIn(
            "COMPARE_MAX_ITEMS = 4",
            source("compare.py"),
        )

    def test_compare_storage_is_dedicated(self):
        self.assertIn(
            "compare_selections",
            source("compare.py"),
        )

    def test_compare_handlers_exist(self):
        names = functions("compare.py")

        for expected in (
            "handle_compare",
            "handle_compare_list",
            "handle_compare_start",
            "handle_compare_drop",
            "handle_compare_reset",
        ):
            self.assertIn(
                expected,
                names,
            )

    def test_compare_event_exists(self):
        self.assertIn(
            '"compare_add"',
            source("compare.py"),
        )


class FavoritesWorkerTests(unittest.TestCase):
    def test_favorites_file_exists(self):
        self.assertTrue(
            (WORKER / "favorites.py").is_file()
        )

    def test_product_favorites_table_is_used(self):
        self.assertIn(
            "favorites",
            source("favorites.py"),
        )

    def test_favorite_handlers_exist(self):
        names = functions("favorites.py")

        for expected in (
            "handle_favorite_add",
            "handle_favorite_remove",
            "handle_favorites_list",
        ):
            self.assertIn(
                expected,
                names,
            )


class CurrentArchitectureTests(unittest.TestCase):
    def test_compare_has_no_legacy_imports(self):
        modules = imported_modules("compare.py")

        self.assertNotIn("aiogram", modules)
        self.assertNotIn("aiosqlite", modules)
        self.assertNotIn("sqlite3", modules)

    def test_favorites_has_no_legacy_imports(self):
        modules = imported_modules("favorites.py")

        self.assertNotIn("aiogram", modules)
        self.assertNotIn("aiosqlite", modules)
        self.assertNotIn("sqlite3", modules)


if __name__ == "__main__":
    unittest.main()