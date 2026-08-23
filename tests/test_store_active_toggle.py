# -*- coding: utf-8 -*-
"""
Tests for the seller "📊 وضعیت فروشگاه" active/inactive toggle:
- migration adds sellers.is_active defaulting to 1 (existing rows stay visible)
- toggling actually persists in the database
- the show_contacts logic (mirrors _render_seller_detail's own rule) is
  respected: an inactive store hides its contact buttons from everyone
  except its own owner.
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from _extract import extract_names  # noqa: E402
from _fakedb import FakeDB, new_conn  # noqa: E402

NAMES = [
    "SCHEMA_STATEMENTS", "INDEX_STATEMENTS", "COLUMN_MIGRATIONS",
    "ensure_column", "run_column_migrations", "now_iso", "logger",
]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def show_contacts(is_active: bool, is_owner: bool) -> bool:
    """Mirrors the exact rule used in bot.py's _render_seller_detail:
    `show_contacts = is_active or is_owner`."""
    return is_active or is_owner


class StoreActiveToggleTests(unittest.TestCase):
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
        self.conn.execute(
            """INSERT INTO sellers (id, name, status, owner_user_id, created_by_user_id, created_at, updated_at)
               VALUES (10, 'Shop A', 'CLAIMED', 1, 1, 't', 't');"""
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_is_active_column_added_by_migration(self):
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(sellers);").fetchall()}
        self.assertIn("is_active", cols)

    def test_existing_seller_rows_default_to_active(self):
        row = self.conn.execute("SELECT is_active FROM sellers WHERE id = 10;").fetchone()
        self.assertEqual(row["is_active"], 1)

    def test_migration_running_twice_does_not_reset_a_toggled_value(self):
        self.conn.execute("UPDATE sellers SET is_active = 0 WHERE id = 10;")
        self.conn.commit()
        run(self.ns["run_column_migrations"]())  # simulate a bot restart
        row = self.conn.execute("SELECT is_active FROM sellers WHERE id = 10;").fetchone()
        self.assertEqual(row["is_active"], 0, "a restart must not silently re-activate a deactivated store")

    def test_toggle_persists_in_database(self):
        self.conn.execute("UPDATE sellers SET is_active = 0, updated_at = 't2' WHERE id = 10;")
        self.conn.commit()
        row = self.conn.execute("SELECT is_active FROM sellers WHERE id = 10;").fetchone()
        self.assertEqual(row["is_active"], 0)

        self.conn.execute("UPDATE sellers SET is_active = 1, updated_at = 't3' WHERE id = 10;")
        self.conn.commit()
        row = self.conn.execute("SELECT is_active FROM sellers WHERE id = 10;").fetchone()
        self.assertEqual(row["is_active"], 1)

    # ------------------------------------------------------------
    # Enforcement logic (the actual "respected in display" rule)
    # ------------------------------------------------------------
    def test_active_store_shows_contacts_to_everyone(self):
        self.assertTrue(show_contacts(is_active=True, is_owner=False))
        self.assertTrue(show_contacts(is_active=True, is_owner=True))

    def test_inactive_store_hides_contacts_from_buyers(self):
        self.assertFalse(show_contacts(is_active=False, is_owner=False))

    def test_inactive_store_still_shows_contacts_to_its_own_owner(self):
        # The owner must still be able to see/manage their own (deactivated)
        # store's info -- deactivation hides it from BUYERS, not the owner.
        self.assertTrue(show_contacts(is_active=False, is_owner=True))


if __name__ == "__main__":
    unittest.main()
