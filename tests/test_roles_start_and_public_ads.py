# -*- coding: utf-8 -*-
"""
Tests for:
- Role selection at first /start (users.role_chosen migration + _go_to_start)
- The general/public "📢 تبلیغ در ارزانکده" advertising system, built on
  top of the EXISTING `requests` table (ad_kind/ad_title/ad_price/
  ad_duration_days/ad_placement/ad_expires_at columns) rather than a
  parallel ads system.
- Auto-expiry of active ads (expire_overdue_ads()).

Runs against real SQLite via tests/_fakedb.py -- no aiogram/aiosqlite needed.
"""
import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from _extract import extract_names  # noqa: E402
from _fakedb import FakeDB, new_conn  # noqa: E402

NAMES = [
    "SCHEMA_STATEMENTS", "INDEX_STATEMENTS", "COLUMN_MIGRATIONS",
    "ensure_column", "run_column_migrations",
    "AD_KIND_LABELS", "REQUEST_STATUS_LABELS",
    "has_open_request", "create_request", "list_my_requests",
    "expire_overdue_ads", "notify_user",
    "now_iso", "logger",
]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class RoleSelectionMigrationTests(unittest.TestCase):
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

    def tearDown(self):
        self.conn.close()

    def test_role_chosen_column_added_defaulting_to_zero(self):
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(users);").fetchall()}
        self.assertIn("role_chosen", cols)

        self.conn.execute(
            "INSERT INTO users (id, telegram_id, created_at, updated_at) VALUES (1, 100, 't', 't');"
        )
        self.conn.commit()
        row = self.conn.execute("SELECT role_chosen FROM users WHERE id = 1;").fetchone()
        self.assertEqual(row["role_chosen"], 0)

    def test_existing_users_unaffected_until_they_pick_a_role(self):
        # Simulates a pre-existing user row from before this migration.
        self.conn.execute(
            "INSERT INTO users (id, telegram_id, created_at, updated_at) VALUES (2, 200, 't', 't');"
        )
        self.conn.commit()
        run(self.ns["run_column_migrations"]())  # simulate a restart after the migration ships
        row = self.conn.execute("SELECT role_chosen FROM users WHERE id = 2;").fetchone()
        self.assertEqual(row["role_chosen"], 0, "existing users must not be auto-marked as having chosen a role")

    def test_setting_role_chosen_persists(self):
        self.conn.execute(
            "INSERT INTO users (id, telegram_id, created_at, updated_at) VALUES (3, 300, 't', 't');"
        )
        self.conn.commit()
        self.conn.execute("UPDATE users SET role_chosen = 1 WHERE id = 3;")
        self.conn.commit()
        row = self.conn.execute("SELECT role_chosen FROM users WHERE id = 3;").fetchone()
        self.assertEqual(row["role_chosen"], 1)


class GeneralAdsSystemTests(unittest.TestCase):
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

        self.conn.execute(
            "INSERT INTO users (id, telegram_id, created_at, updated_at) VALUES (1, 100, 't', 't');"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    # ------------------------------------------------------------
    # Schema: general ads reuse `requests`, no parallel table
    # ------------------------------------------------------------
    def test_no_parallel_ads_table_was_created(self):
        tables = {
            row[0] for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        }
        for forbidden in ("general_ads", "ads", "advertisements", "ad_requests"):
            self.assertNotIn(forbidden, tables, f"found an unexpected parallel ads table: {forbidden}")
        self.assertIn("requests", tables)

    def test_ad_columns_added_to_requests_table(self):
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(requests);").fetchall()}
        for col in ("ad_kind", "ad_title", "ad_image_url", "ad_link", "ad_price", "ad_duration_days", "ad_placement", "ad_expires_at"):
            self.assertIn(col, cols)

    def test_ad_kind_labels_cover_the_six_spec_options(self):
        self.assertEqual(
            set(self.ns["AD_KIND_LABELS"].keys()),
            {"business", "page", "channel", "service", "brand", "other"},
        )

    # ------------------------------------------------------------
    # Submission + duplicate prevention
    # ------------------------------------------------------------
    def test_create_general_ad_request_stores_ad_fields(self):
        request_id = run(self._insert_general_ad(user_id=1, kind="page", title="My Cool Page"))
        row = self.conn.execute("SELECT * FROM requests WHERE id = ?;", (request_id,)).fetchone()
        self.assertEqual(row["request_type"], "general_ad")
        self.assertEqual(row["ad_kind"], "page")
        self.assertEqual(row["ad_title"], "My Cool Page")
        self.assertEqual(row["status"], "PENDING")

    def test_duplicate_open_general_ad_request_is_detected(self):
        run(self._insert_general_ad(user_id=1, kind="page", title="First"))
        self.assertTrue(run(self.ns["has_open_request"](1, "general_ad")))

    def test_no_open_request_for_a_different_user(self):
        run(self._insert_general_ad(user_id=1, kind="page", title="First"))
        self.assertFalse(run(self.ns["has_open_request"](2, "general_ad")))

    def test_general_ad_appears_in_my_requests(self):
        run(self._insert_general_ad(user_id=1, kind="brand", title="Cool Brand"))
        items = run(self.ns["list_my_requests"](1))
        self.assertEqual(len(items), 1)
        self.assertIn("Cool Brand", items[0]["title"])

    async def _insert_general_ad(self, user_id, kind, title):
        """Mirrors the real INSERT in bot.py's _finish_public_ad() (which
        writes ad_kind/ad_title directly via SQL, not through the generic
        create_request() helper -- that helper only covers the common
        columns shared by 'support' and plain 'ad' requests)."""
        cur = await self.ns["db"].execute(
            """INSERT INTO requests (user_id, request_type, topic, message, status, created_at, updated_at,
                   ad_kind, ad_title)
               VALUES (?, 'general_ad', ?, NULL, 'PENDING', ?, ?, ?, ?);""",
            (user_id, title, self.ns["now_iso"](), self.ns["now_iso"](), kind, title),
        )
        return cur.lastrowid

    # ------------------------------------------------------------
    # Admin activation with computed expiry, and auto-expiry
    # ------------------------------------------------------------
    def test_active_ad_with_past_expiry_gets_expired(self):
        request_id = run(self._insert_general_ad(user_id=1, kind="business", title="Shop"))
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE requests SET status='ACTIVE', ad_expires_at=? WHERE id=?;", (past, request_id)
        )
        self.conn.commit()

        expired_count = run(self.ns["expire_overdue_ads"]())
        self.assertEqual(expired_count, 1)
        row = self.conn.execute("SELECT status FROM requests WHERE id=?;", (request_id,)).fetchone()
        self.assertEqual(row["status"], "EXPIRED")

    def test_active_ad_with_future_expiry_is_not_touched(self):
        request_id = run(self._insert_general_ad(user_id=1, kind="business", title="Shop"))
        future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE requests SET status='ACTIVE', ad_expires_at=? WHERE id=?;", (future, request_id)
        )
        self.conn.commit()

        expired_count = run(self.ns["expire_overdue_ads"]())
        self.assertEqual(expired_count, 0)
        row = self.conn.execute("SELECT status FROM requests WHERE id=?;", (request_id,)).fetchone()
        self.assertEqual(row["status"], "ACTIVE")

    def test_pending_ad_without_expiry_is_never_expired(self):
        run(self._insert_general_ad(user_id=1, kind="business", title="Shop"))
        expired_count = run(self.ns["expire_overdue_ads"]())
        self.assertEqual(expired_count, 0)

    def test_expiring_an_ad_notifies_the_user(self):
        request_id = run(self._insert_general_ad(user_id=1, kind="business", title="Shop"))
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE requests SET status='ACTIVE', ad_expires_at=? WHERE id=?;", (past, request_id)
        )
        self.conn.commit()
        run(self.ns["expire_overdue_ads"]())
        notif_count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE user_id=1;"
        ).fetchone()["c"]
        self.assertEqual(notif_count, 1)

    def test_status_labels_cover_active_and_expired(self):
        self.assertIn("ACTIVE", self.ns["REQUEST_STATUS_LABELS"])
        self.assertIn("EXPIRED", self.ns["REQUEST_STATUS_LABELS"])


if __name__ == "__main__":
    unittest.main()
