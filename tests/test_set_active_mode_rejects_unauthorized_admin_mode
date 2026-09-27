# -*- coding: utf-8 -*-
"""
Tests for:

- Roles: user_has_any_seller / get_active_mode / set_active_mode
- Seller favorites as separate storage from product favorites
- Compare selection limits and duplicate handling
- Per-user compare sessions
- Persisted compare-intro state

Runs against real SQLite via tests/_fakedb.py without importing the
Telegram application.
"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from _extract import extract_names  # noqa: E402
from _fakedb import FakeDB, new_conn  # noqa: E402


NAMES = [
    "SCHEMA_STATEMENTS",
    "INDEX_STATEMENTS",
    "COLUMN_MIGRATIONS",
    "ensure_column",
    "run_column_migrations",
    "VALID_MODES",
    "user_has_any_seller",
    "get_active_mode",
    "set_active_mode",
    "is_seller_favorite",
    "toggle_seller_favorite",
    "count_seller_favorites",
    "COMPARE_MAX_ITEMS",
    "COMPARE_INTRO_TEXT",
    "compare_add",
    "_compare_sessions",
    "get_compare_selection",
    "set_compare_selection",
    "clear_compare_selection",
    "has_seen_compare_intro",
    "mark_compare_intro_seen",
    "now_iso",
    "logger",
]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class RolesFavoritesCompareTests(unittest.TestCase):
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
            """
            INSERT INTO users (
                id,
                telegram_id,
                created_at,
                updated_at
            )
            VALUES (1, 100, 't', 't');
            """
        )

        self.conn.execute(
            """
            INSERT INTO users (
                id,
                telegram_id,
                created_at,
                updated_at
            )
            VALUES (2, 200, 't', 't');
            """
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
                'Shop A',
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
            INSERT INTO sellers (
                id,
                name,
                status,
                created_at,
                updated_at
            )
            VALUES (
                20,
                'Shop B',
                'UNCLAIMED',
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
                'Prod A',
                'AVAILABLE',
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
                200,
                20,
                'Prod B',
                'AVAILABLE',
                't',
                't'
            );
            """
        )

        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    # ------------------------------------------------------------
    # Column migrations
    # ------------------------------------------------------------

    def test_migrations_added_expected_columns(self):
        for table, column, _ in self.ns["COLUMN_MIGRATIONS"]:
            cols = {
                row[1]
                for row in self.conn.execute(
                    f"PRAGMA table_info({table});"
                ).fetchall()
            }

            self.assertIn(
                column,
                cols,
                f"{table}.{column} missing after migration",
            )

    def test_migrations_are_idempotent(self):
        run(self.ns["run_column_migrations"]())
        run(self.ns["run_column_migrations"]())

    # ------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------

    def test_user_with_no_seller_is_never_seller_mode(self):
        self.assertFalse(
            run(
                self.ns["user_has_any_seller"](2)
            )
        )

        self.assertEqual(
            run(
                self.ns["get_active_mode"](2)
            ),
            "buyer",
        )

    def test_stale_seller_mode_without_seller_falls_back_to_buyer(self):
        self.conn.execute(
            """
            UPDATE users
            SET active_mode = 'seller'
            WHERE id = 2;
            """
        )
        self.conn.commit()

        self.assertEqual(
            run(
                self.ns["get_active_mode"](2)
            ),
            "buyer",
        )

    def test_user_with_seller_defaults_to_buyer_mode(self):
        self.assertTrue(
            run(
                self.ns["user_has_any_seller"](1)
            )
        )

        self.assertEqual(
            run(
                self.ns["get_active_mode"](1)
            ),
            "buyer",
        )

    def test_set_active_mode_switches_and_persists(self):
        run(
            self.ns["set_active_mode"](
                1,
                "seller",
            )
        )

        self.assertEqual(
            run(
                self.ns["get_active_mode"](1)
            ),
            "seller",
        )

        run(
            self.ns["set_active_mode"](
                1,
                "buyer",
            )
        )

        self.assertEqual(
            run(
                self.ns["get_active_mode"](1)
            ),
            "buyer",
        )

    def test_set_active_mode_rejects_invalid_mode(self):
        with self.assertRaises(ValueError):
            run(
                self.ns["set_active_mode"](
                    1,
                    "admin",
                )
            )

    # ------------------------------------------------------------
    # Seller favorites
    # ------------------------------------------------------------

    def test_seller_favorite_toggle_add_and_remove(self):
        self.assertFalse(
            run(
                self.ns["is_seller_favorite"](
                    2,
                    10,
                )
            )
        )

        new_state = run(
            self.ns["toggle_seller_favorite"](
                2,
                10,
            )
        )

        self.assertTrue(new_state)

        self.assertTrue(
            run(
                self.ns["is_seller_favorite"](
                    2,
                    10,
                )
            )
        )

        new_state = run(
            self.ns["toggle_seller_favorite"](
                2,
                10,
            )
        )

        self.assertFalse(new_state)

        self.assertFalse(
            run(
                self.ns["is_seller_favorite"](
                    2,
                    10,
                )
            )
        )

    def test_seller_favorite_has_no_duplicate_rows(self):
        run(
            self.ns["toggle_seller_favorite"](
                2,
                10,
            )
        )

        count = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM seller_favorites
            WHERE user_id = 2
              AND seller_id = 10;
            """
        ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_count_seller_favorites(self):
        run(
            self.ns["toggle_seller_favorite"](
                1,
                10,
            )
        )

        run(
            self.ns["toggle_seller_favorite"](
                2,
                10,
            )
        )

        self.assertEqual(
            run(
                self.ns["count_seller_favorites"](10)
            ),
            2,
        )

        self.assertEqual(
            run(
                self.ns["count_seller_favorites"](20)
            ),
            0,
        )

    def test_seller_favorites_are_independent_of_product_favorites(self):
        self.conn.execute(
            """
            INSERT INTO favorites (
                user_id,
                product_id,
                created_at
            )
            VALUES (2, 100, 't');
            """
        )
        self.conn.commit()

        self.assertFalse(
            run(
                self.ns["is_seller_favorite"](
                    2,
                    10,
                )
            )
        )

        favorite_count = self.conn.execute(
            "SELECT COUNT(*) FROM seller_favorites;"
        ).fetchone()[0]

        self.assertEqual(favorite_count, 0)

    # ------------------------------------------------------------
    # Compare
    # ------------------------------------------------------------

    def test_compare_add_first_item(self):
        selection, outcome = self.ns["compare_add"](
            [],
            100,
        )

        self.assertEqual(selection, [100])
        self.assertEqual(
            outcome,
            "added_need_one_more",
        )

    def test_compare_add_second_item_becomes_ready(self):
        selection, outcome = self.ns["compare_add"](
            [100],
            200,
        )

        self.assertEqual(
            selection,
            [100, 200],
        )
        self.assertEqual(
            outcome,
            "added_ready",
        )

    def test_compare_add_third_item_respects_configured_limit(self):
        current = list(range(self.ns["COMPARE_MAX_ITEMS"]))

        selection, outcome = self.ns["compare_add"](
            current,
            999,
        )

        self.assertEqual(
            selection,
            current,
        )
        self.assertEqual(
            outcome,
            "already_full",
        )

    def test_compare_add_duplicate_item_is_rejected(self):
        selection, outcome = self.ns["compare_add"](
            [100],
            100,
        )

        self.assertEqual(
            selection,
            [100],
        )
        self.assertEqual(
            outcome,
            "already_in_selection",
        )

    def test_compare_max_items_matches_canonical_configuration(self):
        self.assertGreater(
            self.ns["COMPARE_MAX_ITEMS"],
            0,
        )

        self.assertEqual(
            self.ns["COMPARE_MAX_ITEMS"],
            4,
        )

    def test_compare_intro_text_matches_expected_content(self):
        text = self.ns["COMPARE_INTRO_TEXT"]

        self.assertIn(
            "مقایسه چیه",
            text,
        )

        self.assertIn(
            "محصول",
            text,
        )

    # ------------------------------------------------------------
    # Compare session
    # ------------------------------------------------------------

    def test_compare_session_get_set_clear(self):
        self.assertEqual(
            self.ns["get_compare_selection"](2),
            [],
        )

        self.ns["set_compare_selection"](
            2,
            [100, 200],
        )

        self.assertEqual(
            self.ns["get_compare_selection"](2),
            [100, 200],
        )

        self.ns["clear_compare_selection"](2)

        self.assertEqual(
            self.ns["get_compare_selection"](2),
            [],
        )

    def test_compare_session_isolated_per_user(self):
        self.ns["set_compare_selection"](
            1,
            [100],
        )

        self.ns["set_compare_selection"](
            2,
            [200],
        )

        self.assertEqual(
            self.ns["get_compare_selection"](1),
            [100],
        )

        self.assertEqual(
            self.ns["get_compare_selection"](2),
            [200],
        )

    # ------------------------------------------------------------
    # Compare intro state
    # ------------------------------------------------------------

    def test_compare_intro_not_seen_by_default(self):
        self.assertFalse(
            run(
                self.ns["has_seen_compare_intro"](2)
            )
        )

    def test_compare_intro_marked_seen_persists_per_user(self):
        run(
            self.ns["mark_compare_intro_seen"](2)
        )

        self.assertTrue(
            run(
                self.ns["has_seen_compare_intro"](2)
            )
        )

        self.assertFalse(
            run(
                self.ns["has_seen_compare_intro"](1)
            )
        )


if __name__ == "__main__":
    unittest.main()