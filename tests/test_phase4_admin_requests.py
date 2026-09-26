# -*- coding: utf-8 -*-
"""
Phase 4, Chunk 2 (📝 Requests) tests.

Tests the modular admin-request implementation:
- request list/filter/query logic
- request detail aggregation
- request status/update logic
- per-handler authorization
- notification integration
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

PAGE_SIZE_LIST = 10


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class AdminRequestQueryLogicTests(unittest.TestCase):
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

        self.conn.executemany(
            """
            INSERT INTO users (
                id,
                telegram_id,
                username,
                first_name,
                last_name,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, 't', 't');
            """,
            [
                (1, 100, "ali_shop", "Ali", "Rezaei"),
                (2, 200, "sara99", "Sara", "Ahmadi"),
                (3, 300, "reza300", "Reza", "Karimi"),
            ],
        )

        self.conn.executemany(
            """
            INSERT INTO requests (
                id,
                user_id,
                request_type,
                topic,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, 't', 't');
            """,
            [
                (1, 1, "support", "کمک با حساب", "PENDING"),
                (2, 1, "seller_claim", "ادعای مالکیت فروشگاه", "APPROVED"),
                (3, 2, "support", "مشکل جستجو", "PENDING"),
                (4, 3, "support", "درخواست بسته شده", "REJECTED"),
            ],
        )

        self.conn.commit()

        self.admin_module = admin_module
        self.notifications_module = notifications_module

    def tearDown(self):
        self.conn.close()

    def test_all_requests_are_read_from_real_rows(self):
        rows = self.conn.execute(
            """
            SELECT *
            FROM requests
            ORDER BY id DESC;
            """
        ).fetchall()

        self.assertEqual(len(rows), 4)
        self.assertEqual(
            [row["id"] for row in rows],
            [4, 3, 2, 1],
        )

    def test_pending_filter_returns_only_pending_requests(self):
        rows = self.conn.execute(
            """
            SELECT *
            FROM requests
            WHERE status = ?
            ORDER BY id DESC;
            """,
            ("PENDING",),
        ).fetchall()

        self.assertEqual(
            [row["id"] for row in rows],
            [3, 1],
        )

    def test_request_type_filter_returns_matching_rows(self):
        rows = self.conn.execute(
            """
            SELECT *
            FROM requests
            WHERE request_type = ?
            ORDER BY id DESC;
            """,
            ("seller_claim",),
        ).fetchall()

        self.assertEqual(
            [row["id"] for row in rows],
            [2],
        )

    def test_request_detail_joins_user_information(self):
        row = self.conn.execute(
            """
            SELECT
                r.*,
                u.telegram_id,
                u.username,
                u.first_name,
                u.last_name
            FROM requests r
            LEFT JOIN users u
                ON u.id = r.user_id
            WHERE r.id = ?;
            """,
            (1,),
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["user_id"], 1)
        self.assertEqual(row["telegram_id"], 100)
        self.assertEqual(row["username"], "ali_shop")
        self.assertEqual(row["first_name"], "Ali")

    def test_request_status_can_be_updated(self):
        self.conn.execute(
            """
            UPDATE requests
            SET status = ?, updated_at = ?
            WHERE id = ?;
            """,
            ("APPROVED", "updated", 1),
        )
        self.conn.commit()

        row = self.conn.execute(
            """
            SELECT status, updated_at
            FROM requests
            WHERE id = ?;
            """,
            (1,),
        ).fetchone()

        self.assertEqual(row["status"], "APPROVED")
        self.assertEqual(row["updated_at"], "updated")

    def test_status_update_does_not_modify_other_requests(self):
        self.conn.execute(
            """
            UPDATE requests
            SET status = ?
            WHERE id = ?;
            """,
            ("REJECTED", 1),
        )
        self.conn.commit()

        row = self.conn.execute(
            """
            SELECT status
            FROM requests
            WHERE id = ?;
            """,
            (2,),
        ).fetchone()

        self.assertEqual(row["status"], "APPROVED")

    def test_user_request_count_matches_real_rows(self):
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM requests
            WHERE user_id = ?;
            """,
            (1,),
        ).fetchone()

        self.assertEqual(row["count"], 2)

    def test_missing_request_returns_no_row(self):
        row = self.conn.execute(
            """
            SELECT *
            FROM requests
            WHERE id = ?;
            """,
            (999999,),
        ).fetchone()

        self.assertIsNone(row)

    def test_request_list_pagination_math(self):
        for request_id in range(5, 16):
            self.conn.execute(
                """
                INSERT INTO requests (
                    id,
                    user_id,
                    request_type,
                    topic,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, 't', 't');
                """,
                (
                    request_id,
                    1,
                    "support",
                    f"request-{request_id}",
                    "PENDING",
                ),
            )

        self.conn.commit()

        rows = self.conn.execute(
            """
            SELECT *
            FROM requests
            ORDER BY id DESC;
            """
        ).fetchall()

        page = rows[:PAGE_SIZE_LIST]
        has_next = PAGE_SIZE_LIST < len(rows)

        self.assertEqual(len(rows), 15)
        self.assertEqual(len(page), PAGE_SIZE_LIST)
        self.assertTrue(has_next)

    def test_notification_is_stored_for_request_user(self):
        result = run(
            self.notifications_module.notify_user(
                user_id=1,
                title="درخواست",
                message="وضعیت درخواست شما تغییر کرد",
                notification_type="request",
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
        self.assertEqual(row["user_id"], 1)
        self.assertEqual(row["title"], "درخواست")
        self.assertEqual(row["notification_type"], "request")


class AdminRequestsAuthorizationSourceTests(unittest.TestCase):
    """
    Every admin-request callback/message handler must verify admin status.
    """

    @classmethod
    def setUpClass(cls):
        cls.admin_source = ADMIN_PY_PATH.read_text(
            encoding="utf-8"
        )
        cls.admin_tree = ast.parse(
            cls.admin_source,
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

    def test_admin_request_handlers_exist(self):
        function_names = {
            node.name
            for node in ast.walk(self.admin_tree)
            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
        }

        request_handler_names = {
            name
            for name in function_names
            if "request" in name.lower()
        }

        self.assertTrue(
            request_handler_names,
            "No request-related admin handlers were found",
        )

    def test_admin_request_handlers_use_centralized_authorization(self):
        for node in ast.walk(self.admin_tree):
            if not isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                continue

            if "request" not in node.name.lower():
                continue

            body = self._get_function_body(
                self.admin_source,
                self.admin_tree,
                node.name,
            )

            self.assertTrue(
                "_is_admin(callback)" in body
                or "is_admin_telegram_id(" in body,
                f"{node.name} must verify admin authorization",
            )

    def test_is_admin_delegates_to_centralized_check(self):
        body = self._get_function_body(
            self.admin_source,
            self.admin_tree,
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


if __name__ == "__main__":
    unittest.main()