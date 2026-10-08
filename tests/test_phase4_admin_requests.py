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


class AdminRequestWorkerTests(unittest.TestCase):
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

    def test_approve_callback_exists(self):
        self.assertIn(
            "adminreq:approve:",
            self.source,
        )

    def test_reject_callback_exists(self):
        self.assertIn(
            "adminreq:reject:",
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