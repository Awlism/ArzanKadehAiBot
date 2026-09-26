# -*- coding: utf-8 -*-
"""
Phase 4, Chunk 3 (📢 Admin Ads) tests.

Tests the actual modular admin-ad handlers:
- admin authorization
- request status transitions
- ad price / duration / placement updates
- notification integration
- admin ad panel queries
"""

import ast
import asyncio
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from _fakedb import FakeDB, new_conn  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADMIN_PY_PATH = PROJECT_ROOT / "bot" / "handlers" / "admin.py"


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class AdminAdsQueryLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from bot.database import (
            COLUMN_MIGRATIONS,
            INDEX_STATEMENTS,
            SCHEMA_STATEMENTS,
            run_column_migrations,
        )

        cls.schema_statements = SCHEMA_STATEMENTS
        cls.index_statements = INDEX_STATEMENTS
        cls.column_migrations = COLUMN_MIGRATIONS
        cls.run_column_migrations = run_column_migrations

    def setUp(self):
        self.conn = new_conn()

        for stmt in self.schema_statements:
            self.conn.execute(stmt)

        for stmt in self.index_statements:
            self.conn.execute(stmt)

        self.conn.commit()

        self.fake_db = FakeDB(self.conn)

        import bot.database as database_module
        import bot.handlers.admin as admin_module
        import bot.services.notifications as notifications_module
        import bot.repositories as repositories_module

        database_module.db = self.fake_db
        admin_module.db = self.fake_db
        notifications_module.db = self.fake_db
        repositories_module.db = self.fake_db

        run(self.run_column_migrations())

        self.conn.execute(
            """
            INSERT INTO users (
                id,
                telegram_id,
                username,
                first_name,
                created_at,
                updated_at
            )
            VALUES (
                1,
                100,
                'test_user',
                'Test',
                't',
                't'
            );
            """
        )

        self.conn.executemany(
            """
            INSERT INTO requests (
                id,
                user_id,
                request_type,
                topic,
                status,
                ad_title,
                message,
                ad_price,
                ad_duration_days,
                ad_placement,
                ad_link,
                created_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 't', 't'
            );
            """,
            [
                (
                    1,
                    1,
                    "general_ad",
                    "تبلیغ فروشگاه",
                    "PENDING",
                    "تبلیغ تستی",
                    "متن تبلیغ",
                    None,
                    None,
                    None,
                    "https://example.com",
                ),
                (
                    2,
                    1,
                    "general_ad",
                    "تبلیغ فعال",
                    "ACTIVE",
                    "تبلیغ فعال",
                    "متن فعال",
                    500000,
                    7,
                    "صفحه اصلی",
                    "https://example.com/active",
                ),
                (
                    3,
                    1,
                    "support",
                    "پشتیبانی",
                    "PENDING",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            ],
        )

        self.conn.commit()

        self.admin_module = admin_module
        self.notifications_module = notifications_module

    def tearDown(self):
        self.conn.close()

    def test_pending_ads_query_returns_only_ad_requests(self):
        rows = self.conn.execute(
            """
            SELECT *
            FROM requests
            WHERE request_type IN ('ad', 'general_ad')
              AND status = 'PENDING'
            ORDER BY created_at DESC
            LIMIT 10;
            """
        ).fetchall()

        self.assertEqual(
            [row["id"] for row in rows],
            [1],
        )

    def test_active_ads_query_returns_only_active_ads(self):
        rows = self.conn.execute(
            """
            SELECT *
            FROM requests
            WHERE request_type IN ('ad', 'general_ad')
              AND status = 'ACTIVE'
            ORDER BY ad_expires_at ASC
            LIMIT 10;
            """
        ).fetchall()

        self.assertEqual(
            [row["id"] for row in rows],
            [2],
        )

    def test_ad_price_update_persists(self):
        self.conn.execute(
            """
            UPDATE requests
            SET ad_price = ?,
                updated_at = ?
            WHERE id = ?;
            """,
            (750000, "updated", 1),
        )
        self.conn.commit()

        row = self.conn.execute(
            """
            SELECT ad_price, updated_at
            FROM requests
            WHERE id = ?;
            """,
            (1,),
        ).fetchone()

        self.assertEqual(row["ad_price"], 750000)
        self.assertEqual(row["updated_at"], "updated")

    def test_ad_duration_update_persists(self):
        self.conn.execute(
            """
            UPDATE requests
            SET ad_duration_days = ?,
                updated_at = ?
            WHERE id = ?;
            """,
            (14, "updated", 1),
        )
        self.conn.commit()

        row = self.conn.execute(
            """
            SELECT ad_duration_days
            FROM requests
            WHERE id = ?;
            """,
            (1,),
        ).fetchone()

        self.assertEqual(row["ad_duration_days"], 14)

    def test_ad_placement_update_persists(self):
        self.conn.execute(
            """
            UPDATE requests
            SET ad_placement = ?,
                updated_at = ?
            WHERE id = ?;
            """,
            ("نتایج جستجو", "updated", 1),
        )
        self.conn.commit()

        row = self.conn.execute(
            """
            SELECT ad_placement
            FROM requests
            WHERE id = ?;
            """,
            (1,),
        ).fetchone()

        self.assertEqual(
            row["ad_placement"],
            "نتایج جستجو",
        )

    def test_approved_ad_with_duration_becomes_active(self):
        self.conn.execute(
            """
            UPDATE requests
            SET status = 'APPROVED',
                ad_duration_days = 7
            WHERE id = 1;
            """
        )
        self.conn.commit()

        row = self.conn.execute(
            """
            SELECT status, ad_duration_days
            FROM requests
            WHERE id = 1;
            """
        ).fetchone()

        self.assertEqual(row["status"], "APPROVED")
        self.assertEqual(row["ad_duration_days"], 7)

        self.conn.execute(
            """
            UPDATE requests
            SET status = 'ACTIVE',
                ad_expires_at = ?
            WHERE id = 1;
            """,
            ("2099-01-01T00:00:00+00:00",),
        )
        self.conn.commit()

        row = self.conn.execute(
            """
            SELECT status, ad_expires_at
            FROM requests
            WHERE id = 1;
            """
        ).fetchone()

        self.assertEqual(row["status"], "ACTIVE")
        self.assertEqual(
            row["ad_expires_at"],
            "2099-01-01T00:00:00+00:00",
        )

    def test_rejected_ad_has_rejected_status(self):
        self.conn.execute(
            """
            UPDATE requests
            SET status = 'REJECTED',
                updated_at = ?
            WHERE id = ?;
            """,
            ("updated", 1),
        )
        self.conn.commit()

        row = self.conn.execute(
            """
            SELECT status
            FROM requests
            WHERE id = ?;
            """,
            (1,),
        ).fetchone()

        self.assertEqual(
            row["status"],
            "REJECTED",
        )

    def test_notification_can_be_created_for_ad_user(self):
        result = run(
            self.notifications_module.notify_user(
                user_id=1,
                title="تبلیغ در ارزانکده",
                message="تبلیغت تأیید شد.",
            )
        )

        self.assertTrue(result)

        row = self.conn.execute(
            """
            SELECT *
            FROM notifications
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1;
            """,
            (1,),
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(
            row["user_id"],
            1,
        )
        self.assertEqual(
            row["title"],
            "تبلیغ در ارزانکده",
        )


class AdminAdsAuthorizationSourceTests(unittest.TestCase):
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
    def _get_function_body(
        source,
        tree,
        name,
    ):
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

    def test_admin_ad_callback_handlers_check_authorization(self):
        handlers = [
            "handle_admin_ad_set_price_start",
            "handle_admin_ad_set_duration_start",
            "handle_admin_ad_set_placement_start",
            "handle_ads_admin_panel",
            "handle_ads_admin_detail",
        ]

        for name in handlers:
            body = self._get_function_body(
                self.source,
                self.tree,
                name,
            )

            self.assertIn(
                "_is_admin(callback)",
                body,
                f"{name} must check _is_admin(callback)",
            )

    def test_admin_ad_message_handlers_use_admin_flow(self):
        handlers = [
            "handle_admin_ad_set_price_value",
            "handle_admin_ad_set_duration_value",
            "handle_admin_ad_set_placement_value",
        ]

        for name in handlers:
            body = self._get_function_body(
                self.source,
                self.tree,
                name,
            )

            self.assertIn(
                "restart_requested",
                body,
                f"{name} must use restart/state guard",
            )

            self.assertIn(
                "ensure_user",
                body,
                f"{name} must identify the acting admin",
            )

    def test_admin_request_decision_is_authorized(self):
        body = self._get_function_body(
            self.source,
            self.tree,
            "handle_admin_request_decision",
        )

        self.assertIn(
            "_is_admin(callback)",
            body,
        )

    def test_centralized_is_admin_check_is_used(self):
        body = self._get_function_body(
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


class AdminAdsBehaviorSourceTests(unittest.TestCase):
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
    def _get_body(cls, name):
        for node in ast.walk(cls.tree):
            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ) and node.name == name:
                return "\n".join(
                    cls.source.splitlines()[
                        node.lineno - 1 : node.end_lineno
                    ]
                )

        raise AssertionError(
            f"Function '{name}' not found"
        )

    def test_request_decision_handles_approve_and_reject(self):
        body = self._get_body(
            "handle_admin_request_decision"
        )

        self.assertIn(
            'action not in ("approve", "reject")',
            body,
        )

        self.assertIn(
            'if action == "reject":',
            body,
        )

        self.assertIn(
            'if action == "approve":',
            body,
        )

    def test_ad_approval_can_activate_duration_based_ad(self):
        body = self._get_body(
            "handle_admin_request_decision"
        )

        self.assertIn(
            'req["request_type"] in ("ad", "general_ad")',
            body,
        )

        self.assertIn(
            'req["ad_duration_days"]',
            body,
        )

        self.assertIn(
            'new_status = "ACTIVE"',
            body,
        )

        self.assertIn(
            "ad_expires_at",
            body,
        )

    def test_price_handler_validates_non_negative_price(self):
        body = self._get_body(
            "handle_admin_ad_set_price_value"
        )

        self.assertIn(
            "price is None",
            body,
        )

        self.assertIn(
            "price < 0",
            body,
        )

        self.assertIn(
            "ad_price",
            body,
        )

    def test_duration_handler_requires_positive_days(self):
        body = self._get_body(
            "handle_admin_ad_set_duration_value"
        )

        self.assertIn(
            "days is None",
            body,
        )

        self.assertIn(
            "days <= 0",
            body,
        )

        self.assertIn(
            "ad_duration_days",
            body,
        )

    def test_placement_handler_rejects_empty_value(self):
        body = self._get_body(
            "handle_admin_ad_set_placement_value"
        )

        self.assertIn(
            "not placement",
            body,
        )

        self.assertIn(
            "ad_placement",
            body,
        )

    def test_ad_detail_exposes_expected_controls(self):
        body = self._get_body(
            "handle_ads_admin_detail"
        )

        for callback_prefix in (
            "adminreq:approve:",
            "adminreq:reject:",
            "adsetprice:",
            "adsetduration:",
            "adsetplacement:",
        ):
            self.assertIn(
                callback_prefix,
                body,
            )


if __name__ == "__main__":
    unittest.main()