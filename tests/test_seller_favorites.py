
# -*- coding: utf-8 -*-
"""
Contract tests for Worker seller favorites.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SELLER_PATH = ROOT / "src" / "worker" / "seller.py"


def get_function_source(
    source: str,
    function_name: str,
) -> str:
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ) and node.name == function_name:
            lines = source.splitlines()
            return "\n".join(
                lines[node.lineno - 1:node.end_lineno]
            )

    raise AssertionError(
        f"Function not found: {function_name}"
    )


class SellerFavoriteAddTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SELLER_PATH.read_text(
            encoding="utf-8"
        )
        cls.handler = get_function_source(
            cls.source,
            "handle_seller_favorite_add",
        )

    def test_handler_exists(self):
        self.assertTrue(SELLER_PATH.is_file())
        self.assertIn(
            "async def handle_seller_favorite_add",
            self.source,
        )

    def test_favorite_and_event_use_same_transaction(self):
        self.assertIn(
            "async with db.transaction(immediate=True) as tx:",
            self.handler,
        )
        self.assertEqual(
            self.handler.count("await tx.execute("),
            2,
        )
        self.assertIn(
            "INSERT OR IGNORE INTO seller_favorites",
            self.handler,
        )
        self.assertIn(
            "INSERT INTO events",
            self.handler,
        )

    def test_event_is_conditional_on_new_favorite(self):
        self.assertIn(
            "WHERE changes() = 1;",
            self.handler,
        )
        self.assertIn(
            "SELECT ?, ?, ?, ?, ?",
            self.handler,
        )

    def test_both_writes_share_one_timestamp(self):
        self.assertEqual(
            self.handler.count(
                "favorite_created_at = _now_iso()"
            ),
            1,
        )
        self.assertIn(
            "favorite_created_at",
            self.handler,
        )

    def test_detail_rendering_remains_after_transaction(self):
        self.assertIn(
            "await _render_seller_detail(",
            self.handler,
        )
        self.assertIn(
            "❤️ ذخیره شد!",
            self.handler,
        )

    def test_no_legacy_database_imports(self):
        tree = ast.parse(self.source)
        imported = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(
                    alias.name for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module)

        for forbidden in (
            "aiogram",
            "aiosqlite",
            "sqlite3",
        ):
            self.assertNotIn(forbidden, imported)


if __name__ == "__main__":
    unittest.main()
