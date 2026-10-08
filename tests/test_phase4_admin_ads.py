# -*- coding: utf-8 -*-
"""
Static tests for the current Worker admin-ad implementation.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "src" / "worker" / "admin_ads.py"


class AdminAdsWorkerTests(unittest.TestCase):
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

    def test_admin_ad_decision_handler_exists(self):
        names = {
            node.name
            for node in ast.walk(self.tree)
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
        }

        self.assertIn(
            "handle_admin_ad_decision",
            names,
        )

    def test_approve_callback_exists(self):
        self.assertIn(
            "adminaddecision:approve:",
            self.source,
        )

    def test_reject_callback_exists(self):
        self.assertIn(
            "adminaddecision:reject:",
            self.source,
        )

    def test_ad_request_lookup_exists(self):
        self.assertIn(
            "_get_ad_request",
            self.source,
        )

    def test_ad_request_types_are_supported(self):
        self.assertIn(
            "general_ad",
            self.source,
        )
        self.assertIn(
            "'ad'",
            self.source,
        )

    def test_pending_guard_exists(self):
        self.assertIn(
            "PENDING",
            self.source,
        )

    def test_admin_authorization_exists(self):
        self.assertIn(
            "ADMIN",
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


if __name__ == "__main__":
    unittest.main()