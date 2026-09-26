# -*- coding: utf-8 -*-
"""
Phase 4, Chunk 3 (📢 Admin Ads) tests.

Tests the modular admin-ad implementation:
- admin-ad handlers exist
- admin authorization is enforced
- ad handlers use centralized URL validation when URLs are handled
- unsafe dynamic execution is not present
"""

import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADMIN_PY_PATH = PROJECT_ROOT / "bot" / "handlers" / "admin.py"


class AdminAdsAuthorizationSourceTests(unittest.TestCase):
    """
    Admin-ad handlers must use centralized admin authorization.
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

    @classmethod
    def _ad_handlers(cls):
        return [
            node
            for node in ast.walk(cls.tree)
            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
            and "ad" in node.name.lower()
        ]

    def test_admin_ad_handlers_exist(self):
        handlers = self._ad_handlers()

        self.assertTrue(
            handlers,
            "No admin-ad handlers were found",
        )

    def test_admin_ad_handlers_are_authorized(self):
        handlers = self._ad_handlers()

        for node in handlers:
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

    @classmethod
    def _ad_source(cls):
        parts = []

        for node in ast.walk(cls.tree):
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

            lines = cls.source.splitlines()[
                node.lineno - 1 : node.end_lineno
            ]

            parts.append("\n".join(lines))

        return "\n".join(parts)

    def test_admin_ad_handlers_do_not_use_eval_or_exec(self):
        source = self._ad_source().lower()

        self.assertNotIn(
            "eval(",
            source,
        )

        self.assertNotIn(
            "exec(",
            source,
        )

    def test_ad_url_handling_uses_centralized_url_validation(self):
        source = self._ad_source()

        if "url" not in source.lower():
            return

        self.assertTrue(
            any(
                name in source
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