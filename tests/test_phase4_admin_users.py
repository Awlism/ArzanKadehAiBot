# -*- coding: utf-8 -*-
"""
Phase 4, Chunk 1 (👥 Users) tests.

- Search/list/pagination query logic against real SQLite (mirrors the
  exact SQL used in handle_admin_user_search_query / handle_admin_user_list)
- User profile aggregation (owned stores, requests, reports, referrals)
  reflects real data, never fabricated
- Source-level authorization: every new admin-users handler must check
  admin status before doing anything
"""
import ast
import asyncio
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _extract import extract_names  # noqa: E402
from _fakedb import FakeDB, new_conn  # noqa: E402

BOT_PY_PATH = Path(__file__).resolve().parent.parent / "bot.py"

NAMES = [
    "SCHEMA_STATEMENTS", "INDEX_STATEMENTS", "COLUMN_MIGRATIONS",
    "ensure_column", "run_column_migrations",
    "PAGE_SIZE_LIST", "get_sellers_owned_by_user", "get_active_mode", "VALID_MODES",
    "get_referral_count", "now_iso", "logger",
]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class AdminUserQueryLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES)

    def setUp(self):
        self.conn = new_conn()
        for stmt in self.ns["SCHEMA_STATEMENTS"]:
            self.conn.execute(stmt)
        for stmt in self.ns["INDEX_STATEMENTS"]:
            self.conn.execute(stmt)
        self.conn.commit()
        self.ns["db"] = FakeDB(self.conn)
        run(self.ns["run_column_migrations"]())

        users = [
            (1, 100, "ali_shop", "Ali", "Rezaei"),
            (2, 200, "sara99", "Sara", "Ahmadi"),
            (3, 300, None, "Reza", None),
            (4, 400, "ali_buyer", "Ali", "Karimi"),
        ]
        for uid, tg, uname, fn, ln in users:
            self.conn.execute(
                "INSERT INTO users (id, telegram_id, username, first_name, last_name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 't', 't');",
                (uid, tg, uname, fn, ln),
            )
        self.conn.execute(
            """INSERT INTO sellers (id, name, status, owner_user_id, created_by_user_id, created_at, updated_at)
               VALUES (10, 'Ali Shop', 'CLAIMED', 1, 1, 't', 't');"""
        )
        self.conn.execute(
            "INSERT INTO requests (user_id, request_type, topic, status, created_at, updated_at) "
            "VALUES (1, 'support', 'test', 'PENDING', 't', 't');"
        )
        self.conn.execute(
            "INSERT INTO requests (user_id, request_type, topic, status, created_at, updated_at) "
            "VALUES (1, 'support', 'test2', 'PENDING', 't', 't');"
        )
        self.conn.execute(
            """INSERT INTO products (id, seller_id, name, stock_status, created_at, updated_at)
               VALUES (100, 10, 'Widget', 'AVAILABLE', 't', 't');"""
        )
        self.conn.execute(
            "INSERT INTO reports (user_id, product_id, reason, status, created_at) "
            "VALUES (2, 100, 'کلاهبرداری', 'PENDING', 't');"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _search(self, query):
        """Mirrors handle_admin_user_search_query's exact SQL branch."""
        like = f"%{query}%"
        if query.isdigit():
            return self.conn.execute(
                """SELECT * FROM users
                   WHERE username LIKE ? OR first_name LIKE ? OR last_name LIKE ? OR CAST(telegram_id AS TEXT) LIKE ?
                   ORDER BY id DESC LIMIT ?;""",
                (like, like, like, like, self.ns["PAGE_SIZE_LIST"]),
            ).fetchall()
        return self.conn.execute(
            """SELECT * FROM users
               WHERE username LIKE ? OR first_name LIKE ? OR last_name LIKE ?
               ORDER BY id DESC LIMIT ?;""",
            (like, like, like, self.ns["PAGE_SIZE_LIST"]),
        ).fetchall()

    def test_search_by_first_name_finds_multiple_matches(self):
        results = self._search("Ali")
        self.assertEqual({r["id"] for r in results}, {1, 4})

    def test_search_by_username_finds_exact_owner(self):
        results = self._search("sara99")
        self.assertEqual([r["id"] for r in results], [2])

    def test_search_by_numeric_telegram_id(self):
        results = self._search("300")
        self.assertEqual([r["id"] for r in results], [3])

    def test_search_no_match_returns_empty(self):
        results = self._search("nonexistent_zzz")
        self.assertEqual(results, [])

    def test_user_list_pagination_math(self):
        for i in range(5, 15):
            self.conn.execute(
                "INSERT INTO users (id, telegram_id, created_at, updated_at) VALUES (?, ?, 't', 't');",
                (i, 1000 + i),
            )
        self.conn.commit()
        all_users = self.conn.execute("SELECT * FROM users ORDER BY id DESC;").fetchall()
        page_size = self.ns["PAGE_SIZE_LIST"]
        self.assertEqual(len(all_users), 14)
        page0 = all_users[0:page_size]
        has_next = page_size < len(all_users)
        self.assertEqual(len(page0), page_size)
        self.assertTrue(has_next)

    # ------------------------------------------------------------
    # User profile aggregation -- real data only, never fabricated
    # ------------------------------------------------------------
    def test_owned_sellers_reflects_real_ownership(self):
        sellers = run(self.ns["get_sellers_owned_by_user"](1))
        self.assertEqual([s["id"] for s in sellers], [10])
        sellers_other = run(self.ns["get_sellers_owned_by_user"](2))
        self.assertEqual(sellers_other, [])

    def test_request_count_matches_real_rows(self):
        row = self.conn.execute("SELECT COUNT(*) AS c FROM requests WHERE user_id = ?;", (1,)).fetchone()
        self.assertEqual(row["c"], 2)
        row_empty = self.conn.execute("SELECT COUNT(*) AS c FROM requests WHERE user_id = ?;", (3,)).fetchone()
        self.assertEqual(row_empty["c"], 0)

    def test_report_count_matches_real_rows(self):
        row = self.conn.execute("SELECT COUNT(*) AS c FROM reports WHERE user_id = ?;", (2,)).fetchone()
        self.assertEqual(row["c"], 1)

    def test_referral_total_sums_across_owned_sellers(self):
        self.conn.execute(
            "INSERT INTO users (id, telegram_id, created_at, updated_at) VALUES (50, 5000, 't', 't');"
        )
        self.conn.execute(
            "INSERT INTO referrals (seller_id, referred_user_id, created_at) VALUES (10, 50, 't');"
        )
        self.conn.commit()
        total = 0
        for s in run(self.ns["get_sellers_owned_by_user"](1)):
            total += run(self.ns["get_referral_count"](s["id"]))
        self.assertEqual(total, 1)

    def test_active_mode_is_read_via_existing_function_not_fabricated(self):
        mode = run(self.ns["get_active_mode"](1))
        self.assertIn(mode, ("buyer", "seller", "admin"))


class AdminUsersAuthorizationSourceTests(unittest.TestCase):
    """Every new admin-users handler must verify admin status itself
    (never rely on the button just being hidden)."""

    @classmethod
    def setUpClass(cls):
        cls.source = BOT_PY_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(BOT_PY_PATH))

    def _get_function_body(self, name: str) -> str:
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                lines = self.source.splitlines()[node.lineno - 1: node.end_lineno]
                return "\n".join(lines)
        raise AssertionError(f"Function '{name}' not found")

    def test_all_new_admin_user_handlers_check_authorization(self):
        handlers_with_callback_auth = [
            "handle_admin_home",
            "handle_admin_users_menu",
            "handle_admin_user_search_start",
            "handle_admin_user_list",
            "handle_admin_user_view",
        ]
        for name in handlers_with_callback_auth:
            body = self._get_function_body(name)
            self.assertIn("_is_admin(callback)", body, f"{name} must check _is_admin(callback)")

    def test_message_handler_checks_admin_via_telegram_id(self):
        body = self._get_function_body("handle_admin_user_search_query")
        self.assertIn("is_admin_telegram_id(message.from_user.id)", body)

    def test_is_admin_is_the_single_consolidated_check(self):
        """Regression: _is_admin() must delegate to is_admin_telegram_id(),
        not re-derive its own comparison (Phase 4 consolidation)."""
        body = self._get_function_body("_is_admin")
        self.assertIn("is_admin_telegram_id(callback.from_user.id)", body)
        self.assertNotIn("ADMIN_CHAT_ID ==", body)
        self.assertNotIn("== ADMIN_CHAT_ID", body)

    def test_no_duplicate_is_admin_definition(self):
        count = sum(
            1 for node in ast.walk(self.tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_is_admin"
        )
        self.assertEqual(count, 1)

    def test_admin_home_reachable_from_account_for_admin_mode(self):
        body = self._get_function_body("handle_account")
        self.assertIn('mode == "admin"', body)
        self.assertIn("_render_admin_home", body)

    def test_admin_user_view_does_not_invent_a_ban_or_score_system(self):
        body = self._get_function_body("handle_admin_user_view")
        for forbidden in ("ban", "warning_point", "negative_score", "reputation"):
            self.assertNotIn(forbidden, body.lower())

    def test_admin_role_selection_activates_admin_mode_and_opens_panel(self):
        body = self._get_function_body("handle_role_pick")

        self.assertIn('await set_active_mode(user_id, "admin")', body)
        self.assertIn("await _render_admin_home(callback)", body)

        admin_pos = body.index('if role == "admin":')
        admin_branch = body[admin_pos:]

        self.assertIn('await set_active_mode(user_id, "admin")', admin_branch)
        self.assertIn("await _render_admin_home(callback)", admin_branch)
        self.assertNotIn("ADMIN_MODE_PLACEHOLDER_TEXT", admin_branch)

if __name__ == "__main__":
    unittest.main()
