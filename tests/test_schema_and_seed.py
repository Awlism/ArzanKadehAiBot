# -*- coding: utf-8 -*-
"""
Validates bot.py's real SCHEMA_STATEMENTS / INDEX_STATEMENTS / seed data
against an actual (stdlib) SQLite engine, in-memory.

Does NOT require aiogram or aiosqlite -- only ast (to pull the constants
out of bot.py, see _extract.py) and Python's built-in sqlite3 + unittest.
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from _extract import extract_names  # noqa: E402

NAMES = [
    "SCHEMA_STATEMENTS",
    "INDEX_STATEMENTS",
    "CITY_NAMES",
    "CATEGORY_TREE",
    "DEMO_SELLER_NAME",
    "DEMO_PRODUCT_NAME",
]

EXPECTED_TABLES = {
    "users", "cities", "categories", "sellers", "products", "favorites",
    "seller_claims", "reviews", "reports", "events", "notifications",
}

EXPECTED_MAIN_CATEGORIES = [
    ("👗", "مد و پوشاک"), ("💄", "زیبایی و آرایشی"), ("💇", "سالن و خدمات زیبایی"),
    ("💎", "طلا و جواهر"), ("📱", "موبایل و دیجیتال"), ("🏠", "خانه و آشپزخانه"),
    ("🧸", "کودک و نوزاد"), ("🥗", "خوراکی و نوشیدنی"), ("🎨", "صنایع دستی و هنری"),
    ("🎁", "هدیه"), ("🌱", "گل و گیاه"), ("🏋️", "ورزش"), ("🚗", "خودرو و موتور"),
    ("📚", "کتاب و آموزش"), ("🛠️", "خدمات"), ("🐾", "حیوانات خانگی"),
    ("📦", "محصولات وارداتی"), ("🏡", "املاک"),
]


class SchemaAndSeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES)

    def _new_conn(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON;")
        for stmt in self.ns["SCHEMA_STATEMENTS"]:
            conn.execute(stmt)
        for stmt in self.ns["INDEX_STATEMENTS"]:
            conn.execute(stmt)
        conn.commit()
        return conn

    # ---------------------------------------------------------------
    # Schema
    # ---------------------------------------------------------------
    def test_all_required_tables_are_created(self):
        conn = self._new_conn()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
        table_names = {r[0] for r in rows}
        missing = EXPECTED_TABLES - table_names
        self.assertFalse(missing, f"Missing tables: {missing}")

    def test_indexes_are_created_without_error(self):
        # If this doesn't raise, all CREATE INDEX statements are valid
        # against the schema they reference.
        conn = self._new_conn()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';"
        ).fetchall()
        self.assertGreaterEqual(len(rows), 8)

    def test_foreign_keys_are_enforced(self):
        conn = self._new_conn()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO products (seller_id, name, stock_status, created_at, updated_at)
                   VALUES (99999, 'x', 'AVAILABLE', 't', 't');"""
            )
            conn.commit()

    def test_ids_are_integer_autoincrement_primary_keys(self):
        for stmt in self.ns["SCHEMA_STATEMENTS"]:
            self.assertIn("id INTEGER PRIMARY KEY AUTOINCREMENT", stmt)

    # ---------------------------------------------------------------
    # City seed
    # ---------------------------------------------------------------
    def test_city_seed_count(self):
        self.assertEqual(len(self.ns["CITY_NAMES"]), 25)
        self.assertIn("تهران", self.ns["CITY_NAMES"])

    def test_city_seed_is_idempotent(self):
        conn = self._new_conn()

        def seed_once():
            row = conn.execute("SELECT COUNT(*) FROM cities;").fetchone()
            if row[0] > 0:
                return
            for name in self.ns["CITY_NAMES"]:
                conn.execute("INSERT OR IGNORE INTO cities (name) VALUES (?);", (name,))
            conn.commit()

        seed_once()
        seed_once()  # simulate a bot restart
        count = conn.execute("SELECT COUNT(*) FROM cities;").fetchone()[0]
        self.assertEqual(count, len(self.ns["CITY_NAMES"]))

    def test_city_name_is_unique(self):
        conn = self._new_conn()
        conn.execute("INSERT INTO cities (name) VALUES ('تهران');")
        conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO cities (name) VALUES ('تهران');")
            conn.commit()

    # ---------------------------------------------------------------
    # Category seed
    # ---------------------------------------------------------------
    def test_category_tree_has_18_main_categories_with_correct_emoji(self):
        tree = self.ns["CATEGORY_TREE"]
        self.assertEqual(len(tree), 18)
        actual = [(emoji, name) for emoji, name, _subs in tree]
        self.assertEqual(actual, EXPECTED_MAIN_CATEGORIES)

    def test_every_subcategory_has_a_non_empty_emoji_and_name(self):
        for _emoji, _name, subs in self.ns["CATEGORY_TREE"]:
            self.assertGreater(len(subs), 0)
            for sub_emoji, sub_name in subs:
                self.assertTrue(sub_emoji)
                self.assertTrue(sub_name.strip())

    def test_category_seed_creates_correct_parent_child_hierarchy(self):
        conn = self._new_conn()
        for main_emoji, main_name, subs in self.ns["CATEGORY_TREE"]:
            cur = conn.execute(
                "INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, NULL);",
                (main_name, main_emoji),
            )
            parent_id = cur.lastrowid
            for sub_emoji, sub_name in subs:
                conn.execute(
                    "INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?);",
                    (sub_name, sub_emoji, parent_id),
                )
        conn.commit()

        roots = conn.execute(
            "SELECT id FROM categories WHERE parent_id IS NULL;"
        ).fetchall()
        self.assertEqual(len(roots), 18)

        # every subcategory's parent must exist and itself be a root category
        root_ids = {r[0] for r in roots}
        children = conn.execute(
            "SELECT id, parent_id FROM categories WHERE parent_id IS NOT NULL;"
        ).fetchall()
        self.assertGreater(len(children), 0)
        for _child_id, parent_id in children:
            self.assertIn(parent_id, root_ids)

        total_expected = len(self.ns["CATEGORY_TREE"]) + sum(
            len(subs) for _e, _n, subs in self.ns["CATEGORY_TREE"]
        )
        total_actual = conn.execute("SELECT COUNT(*) FROM categories;").fetchone()[0]
        self.assertEqual(total_actual, total_expected)

    def test_category_seed_is_idempotent(self):
        conn = self._new_conn()

        def seed_once():
            row = conn.execute("SELECT COUNT(*) FROM categories;").fetchone()
            if row[0] > 0:
                return
            for main_emoji, main_name, subs in self.ns["CATEGORY_TREE"]:
                cur = conn.execute(
                    "INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, NULL);",
                    (main_name, main_emoji),
                )
                parent_id = cur.lastrowid
                for sub_emoji, sub_name in subs:
                    conn.execute(
                        "INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?);",
                        (sub_name, sub_emoji, parent_id),
                    )
            conn.commit()

        seed_once()
        first_count = conn.execute("SELECT COUNT(*) FROM categories;").fetchone()[0]
        seed_once()  # simulate a bot restart
        second_count = conn.execute("SELECT COUNT(*) FROM categories;").fetchone()[0]
        self.assertEqual(first_count, second_count)

    # ---------------------------------------------------------------
    # Uniqueness / business rules
    # ---------------------------------------------------------------
    def test_favorites_unique_per_user_and_product(self):
        conn = self._new_conn()
        conn.execute(
            "INSERT INTO users (telegram_id, created_at, updated_at) VALUES (1,'t','t');"
        )
        conn.execute(
            "INSERT INTO sellers (name, status, created_at, updated_at) VALUES ('s','UNCLAIMED','t','t');"
        )
        conn.execute(
            "INSERT INTO products (seller_id, name, stock_status, created_at, updated_at) "
            "VALUES (1, 'p', 'AVAILABLE', 't', 't');"
        )
        conn.commit()
        conn.execute(
            "INSERT INTO favorites (user_id, product_id, created_at) VALUES (1, 1, 't');"
        )
        conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO favorites (user_id, product_id, created_at) VALUES (1, 1, 't');"
            )
            conn.commit()

    def test_users_telegram_id_is_unique(self):
        conn = self._new_conn()
        conn.execute(
            "INSERT INTO users (telegram_id, created_at, updated_at) VALUES (42,'t','t');"
        )
        conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users (telegram_id, created_at, updated_at) VALUES (42,'t','t');"
            )
            conn.commit()

    def test_review_rating_aggregate_query_used_by_bot(self):
        conn = self._new_conn()
        conn.execute(
            "INSERT INTO users (telegram_id, created_at, updated_at) VALUES (1,'t','t');"
        )
        conn.execute(
            "INSERT INTO sellers (name, status, created_at, updated_at) VALUES ('s','UNCLAIMED','t','t');"
        )
        conn.execute(
            "INSERT INTO products (seller_id, name, stock_status, created_at, updated_at) "
            "VALUES (1,'p','AVAILABLE','t','t');"
        )
        conn.commit()
        conn.execute(
            "INSERT INTO reviews (user_id, product_id, rating, text, created_at) VALUES (1,1,4,'ok','t');"
        )
        conn.execute(
            "INSERT INTO reviews (user_id, product_id, rating, text, created_at) VALUES (1,1,2,'meh','t');"
        )
        conn.commit()
        conn.execute(
            """UPDATE products SET rating = (SELECT AVG(rating) FROM reviews WHERE product_id=1),
               review_count = (SELECT COUNT(*) FROM reviews WHERE product_id=1) WHERE id=1;"""
        )
        conn.commit()
        rating, count = conn.execute(
            "SELECT rating, review_count FROM products WHERE id=1;"
        ).fetchone()
        self.assertAlmostEqual(rating, 3.0)
        self.assertEqual(count, 2)

    # ---------------------------------------------------------------
    # Demo data naming (item 10 of the request: must be unmistakably DEMO)
    # ---------------------------------------------------------------
    def test_demo_data_names_are_clearly_labeled(self):
        self.assertTrue(self.ns["DEMO_SELLER_NAME"].startswith("DEMO -"))
        self.assertTrue(self.ns["DEMO_PRODUCT_NAME"].startswith("DEMO -"))


if __name__ == "__main__":
    unittest.main()
