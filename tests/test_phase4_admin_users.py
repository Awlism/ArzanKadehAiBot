# -*- coding: utf-8 -*-
"""
Phase 4, Chunk 1 (👥 Users) tests.

Tests the modular admin-users implementation:
- real SQLite query logic
- real user profile aggregation
- per-handler authorization in bot/handlers/admin.py
- admin role routing in bot/handlers/account.py
"""

import ast
import asyncio
import os
import unittest
from pathlib import Path

sys_path = os.path.dirname(__file__)
import sys

sys.path.insert(0, sys_path)

from _fakedb import FakeDB, new_conn  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADMIN_PY_PATH = PROJECT_ROOT / "bot" / "handlers" / "admin.py"
ACCOUNT_PY_PATH = PROJECT_ROOT / "bot" / "handlers" / "account.py"

PAGE_SIZE_LIST = 10


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class AdminUserQueryLogicTests(unittest.TestCase):
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

        import bot.handlers.admin as admin_module
        import bot.services.referrals as referrals_module
        import bot.repositories as repositories_module

        self.admin_module = admin_module
        self.referrals_module = referrals_module
        self.repositories_module = repositories_module

        admin_module.db = self.fake_db
        referrals_module.db = self.fake_db
        repositories_module.db = self.fake_db

        run(self.run_column_migrations())

        users = [
            (1, 100, "ali_shop", "Ali", "Rezaei"),
            (2, 200, "sara99", "Sara", "Ahmadi"),
            (3, 300, None, "Reza", None),
            (4, 400, "ali_buyer", "Ali", "Karimi"),
        ]

        for uid, tg, username, first_name, last_name in users:
            self.conn.execute(
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
                (
                    uid,
                    tg,
                    username,
                    first_name,
                    last_name,
                ),
            )

        self.conn.execute(
            """
            INSERT INTO sellers (
                id,
                name,
                status,
                owner_user_id,
                created_by_user_id,
                created_at,
                updated_at
            )
            VALUES (
                10,
                'Ali Shop',
                'CLAIMED',
                1,
                1,
                't',
                't'
            );
            """
        )

        self.conn.execute(
            """
            INSERT INTO requests (
                user_id,
                request_type,
                topic,
                status,
                created_at,
                updated_at
            )
            VALUES (
                1,
                'support',
                'test',
                'PENDING',
                't',
                't'
            );
            """
        )

        self.conn.execute(
            """
            INSERT INTO requests (
                user_id,
                request_type,
                topic,
                status,
                created_at,
                updated_at
            )
            VALUES (
                1,
                'support',
                'test2',
                'PENDING',
                't',
                't'
            );
            """
        )

        self.conn.execute(
            """
            INSERT INTO products (
                id,
                seller_id,
                name,
                stock_status,
                created_at,
                updated_at
            )
            VALUES (
                100,
                10,
                'Widget',
                'AVAILABLE',
                't',
                't'
            );
            """
        )

        self.conn.execute(
            """
            INSERT INTO reports (
                user_id,
                product_id,
                reason,
                status,
                created_at
            )
            VALUES (
                2,
                100,
                'کلاهبرداری',
                'PENDING',
                't'
            );
            """
        )

        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _search(self, query):
        like = f"%{query}%"

        if query.isdigit():
            return self.conn.execute(
                """
                SELECT *
                FROM users
                WHERE username LIKE ?
                   OR first_name LIKE ?
                   OR last_name LIKE ?
                   OR CAST(telegram_id AS TEXT) LIKE ?
                ORDER BY id DESC
                LIMIT ?;
                """,
                (
                    like,
                    like,
                    like,
                    like,
                    PAGE_SIZE_LIST,
                ),
            ).fetchall()

        return self.conn.execute(
            """
            SELECT *
            FROM users
            WHERE username LIKE ?
               OR first_name LIKE ?
               OR last_name LIKE ?
            ORDER BY id DESC
            LIMIT ?;
            """,
            (
                like,
                like,
                like,
                PAGE_SIZE_LIST,
            ),
        ).fetchall()

    def test_search_by_first_name_finds_multiple_matches(self):
        results = self._search("Ali")
        self.assertEqual(
            {row["id"] for row in results},
            {1, 4},
        )

    def test_search_by_username_finds_exact_owner(self):
        results = self._search("sara99")
        self.assertEqual(
            [row["id"] for row in results],
            [2],
        )

    def test_search_by_numeric_telegram_id(self):
        results = self._search("300")
        self.assertEqual(
            [row["id"] for row in results],
            [3],
        )

    def test_search_no_match_returns_empty(self):
        results = self._search("nonexistent_zzz")
        self.assertEqual(results, [])

    def test_user_list_pagination_math(self):
        for user_id in range(5, 15):
            self.conn.execute(
                """
                INSERT INTO users (
                    id,
                    telegram_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, 't', 't');
                """,
                (
                    user_id,
                    1000 + user_id,
                ),
            )

        self.conn.commit()

        all_users = self.conn.execute(
            "SELECT * FROM users ORDER BY id DESC;"
        ).fetchall()

        page0 = all_users[:PAGE_SIZE_LIST]
        has_next = PAGE_SIZE_LIST < len(all_users)

        self.assertEqual(len(all_users), 14)
        self.assertEqual(len(page0), PAGE_SIZE_LIST)
        self.assertTrue(has_next)

    def test_owned_sellers_reflect_real_ownership(self):
        sellers = run(
            self.referrals_module.get_sellers_owned_by_user(1)
        )

        self.assertEqual(
            [seller["id"] for seller in sellers],
            [10],
        )

        sellers_other = run(
            self.referrals_module.get_sellers_owned_by_user(2)
        )

        self.assertEqual(sellers_other, [])

    def test_request_count_matches_real_rows(self):
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM requests
            WHERE user_id = ?;
            """,
            (1,),
        ).fetchone()

        self.assertEqual(row["c"], 2)

        row_empty = self.conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM requests
            WHERE user_id = ?;
            """,
            (3,),
        ).fetchone()

        self.assertEqual(row_empty["c"], 0)

    def test_report_count_matches_real_rows(self):
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM reports
            WHERE user_id = ?;
            """,
            (2,),
        ).fetchone()

        self.assertEqual(row["c"], 1)

    def test_referral_total_sums_across_owned_sellers(self):
        self.conn.execute(
            """
            INSERT INTO users (
                id,
                telegram_id,
                created_at,
                updated_at
            )
            VALUES (
                50,
                5000,
                't',
                't'
            );
            """
        )

        self.conn.execute(
            """
            INSERT INTO referrals (
                seller_id,
                referred_user_id,
                created_at
            )
            VALUES (
                10,
                50,
                't'
            );
            """
        )

        self.conn.commit()

        total = 0

        sellers = run(
            self.referrals_module.get_sellers_owned_by_user(1)
        )

        for seller in sellers:
            total += run(
                self.referrals_module.get_referral_count(
                    seller["id"]
                )
            )

        self.assertEqual(total, 1)

    def test_active_mode_is_read_via_existing_function(self):
        mode = run(
            self.repositories_module.get_active_mode(1)
        )

        self.assertIn(
            mode,
            ("buyer", "seller", "admin"),
        )


class AdminUsersAuthorizationSourceTests(unittest.TestCase):
    """
    Every admin-users callback handler must verify admin status itself.
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

        cls.account_source = ACCOUNT_PY_PATH.read_text(
            encoding="utf-8"
        )
        cls.account_tree = ast.parse(
            cls.account_source,
            filename=str(ACCOUNT_PY_PATH),
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

    def test_all_admin_user_callback_handlers_check_authorization(self):
        handlers = [
            "handle_admin_home",
            "handle_admin_users_menu",
            "handle_admin_user_search_start",
            "handle_admin_user_list",
            "handle_admin_user_view",
        ]

        for name in handlers:
            body = self._get_function_body(
                self.admin_source,
                self.admin_tree,
                name,
            )

            self.assertIn(
                "_is_admin(callback)",
                body,
                f"{name} must check _is_admin(callback)",
            )

    def test_message_handler_checks_admin_via_telegram_id(self):
        body = self._get_function_body(
            self.admin_source,
            self.admin_tree,
            "handle_admin_user_search_query",
        )

        self.assertIn(
            "is_admin_telegram_id(message.from_user.id)",
            body,
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

    def test_no_duplicate_is_admin_definition(self):
        count = sum(
            1
            for node in ast.walk(self.admin_tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_is_admin"
        )

        self.assertEqual(count, 1)

    def test_admin_user_view_does_not_invent_ban_or_score_system(self):
        body = self._get_function_body(
            self.admin_source,
            self.admin_tree,
            "handle_admin_user_view",
        )

        for forbidden in (
            "ban",
            "warning_point",
            "negative_score",
            "reputation",
        ):
            self.assertNotIn(
                forbidden,
                body.lower(),
            )

    def test_admin_role_selection_activates_admin_mode_and_opens_panel(self):
        body = self._get_function_body(
            self.account_source,
            self.account_tree,
            "handle_role_pick",
        )

        self.assertIn(
            'await set_active_mode(user_id, "admin")',
            body,
        )

        self.assertIn(
            "await _render_admin_home(callback)",
            body,
        )

        admin_pos = body.find(
            'if role == "admin":'
        )

        self.assertGreaterEqual(admin_pos, 0)

        admin_branch = body[admin_pos:]

        self.assertIn(
            'await set_active_mode(user_id, "admin")',
            admin_branch,
        )

        self.assertIn(
            "await _render_admin_home(callback)",
            admin_branch,
        )

        self.assertNotIn(
            "ADMIN_MODE_PLACEHOLDER_TEXT",
            admin_branch,
        )


if __name__ == "__main__":
    unittest.main()