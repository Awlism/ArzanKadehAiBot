# -*- coding: utf-8 -*-
"""
Mirrors the exact SQL/branching logic used inside handle_category() in
bot.py (root -> main category -> subcategory -> products, with a Back
target derived from parent_id) and runs it against real SQLite. This is
the closest an offline test can get to verifying "دسته‌بندی اصلی باز شود /
زیردسته‌ها نمایش داده شوند / Back درست کار کند" without an actual Telegram
runtime (which needs aiogram - unavailable offline, see README).
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from _extract import extract_names  # noqa: E402

NAMES = ["SCHEMA_STATEMENTS", "INDEX_STATEMENTS", "CATEGORY_TREE"]


def resolve_category_screen(conn, cat_id: int):
    """Re-implementation of the branching in handle_category(), using the
    identical SQL, so we can assert on it without aiogram."""
    if cat_id == 0:
        rows = conn.execute(
            "SELECT id, name, emoji FROM categories WHERE parent_id IS NULL ORDER BY id;"
        ).fetchall()
        return {"kind": "list", "rows": rows, "back": None}

    category = conn.execute(
        "SELECT * FROM categories WHERE id = ?;", (cat_id,)
    ).fetchone()
    if not category:
        return {"kind": "not_found"}

    children = conn.execute(
        "SELECT id, name, emoji FROM categories WHERE parent_id = ? ORDER BY id;",
        (cat_id,),
    ).fetchall()

    back_target = f"cat:{category['parent_id']}:0" if category["parent_id"] else "cat:0:0"

    if children:
        return {"kind": "children", "rows": children, "back": back_target, "category": category}

    products = conn.execute(
        """SELECT p.* FROM products p WHERE p.category_id = ?
           ORDER BY p.views DESC, p.id DESC;""",
        (cat_id,),
    ).fetchall()
    return {"kind": "products", "rows": products, "back": back_target, "category": category}


class CategoryNavigationLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES)

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        for stmt in self.ns["SCHEMA_STATEMENTS"]:
            self.conn.execute(stmt)
        for stmt in self.ns["INDEX_STATEMENTS"]:
            self.conn.execute(stmt)
        for main_emoji, main_name, subs in self.ns["CATEGORY_TREE"]:
            cur = self.conn.execute(
                "INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, NULL);",
                (main_name, main_emoji),
            )
            parent_id = cur.lastrowid
            for sub_emoji, sub_name in subs:
                self.conn.execute(
                    "INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?);",
                    (sub_name, sub_emoji, parent_id),
                )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_root_screen_lists_all_18_main_categories(self):
        screen = resolve_category_screen(self.conn, 0)
        self.assertEqual(screen["kind"], "list")
        self.assertEqual(len(screen["rows"]), 18)
        self.assertIsNone(screen["back"])

    def test_main_category_shows_its_subcategories_with_back_to_root(self):
        main = self.conn.execute(
            "SELECT id FROM categories WHERE name = 'زیبایی و آرایشی' AND parent_id IS NULL;"
        ).fetchone()
        self.assertIsNotNone(main)

        screen = resolve_category_screen(self.conn, main["id"])
        self.assertEqual(screen["kind"], "children")
        names = {r["name"] for r in screen["rows"]}
        self.assertIn("مراقبت پوست", names)
        self.assertIn("آرایشی", names)
        self.assertEqual(screen["back"], "cat:0:0")

    def test_leaf_subcategory_shows_empty_state_with_back_to_main_category(self):
        main = self.conn.execute(
            "SELECT id FROM categories WHERE name = 'زیبایی و آرایشی' AND parent_id IS NULL;"
        ).fetchone()
        leaf = self.conn.execute(
            "SELECT id, parent_id FROM categories WHERE name = 'مراقبت پوست' AND parent_id = ?;",
            (main["id"],),
        ).fetchone()
        self.assertIsNotNone(leaf)

        screen = resolve_category_screen(self.conn, leaf["id"])
        self.assertEqual(screen["kind"], "products")
        self.assertEqual(screen["rows"], [])  # no products seeded yet -> empty state in bot.py
        self.assertEqual(screen["back"], f"cat:{main['id']}:0")

    def test_leaf_subcategory_lists_its_products(self):
        main = self.conn.execute(
            "SELECT id FROM categories WHERE name = 'زیبایی و آرایشی' AND parent_id IS NULL;"
        ).fetchone()
        leaf = self.conn.execute(
            "SELECT id FROM categories WHERE name = 'مراقبت پوست' AND parent_id = ?;",
            (main["id"],),
        ).fetchone()

        self.conn.execute(
            "INSERT INTO sellers (name, status, created_at, updated_at) VALUES ('s','UNCLAIMED','t','t');"
        )
        self.conn.execute(
            """INSERT INTO products (seller_id, category_id, name, stock_status, created_at, updated_at)
               VALUES (1, ?, 'کرم مرطوب‌کننده', 'AVAILABLE', 't', 't');""",
            (leaf["id"],),
        )
        self.conn.commit()

        screen = resolve_category_screen(self.conn, leaf["id"])
        self.assertEqual(screen["kind"], "products")
        self.assertEqual(len(screen["rows"]), 1)
        self.assertEqual(screen["rows"][0]["name"], "کرم مرطوب‌کننده")

    def test_back_navigation_round_trip_root_to_leaf_and_back(self):
        # root -> main
        main = self.conn.execute(
            "SELECT id FROM categories WHERE name = 'موبایل و دیجیتال' AND parent_id IS NULL;"
        ).fetchone()
        screen1 = resolve_category_screen(self.conn, main["id"])
        self.assertEqual(screen1["back"], "cat:0:0")

        # main -> leaf
        leaf = self.conn.execute(
            "SELECT id FROM categories WHERE name = 'موبایل' AND parent_id = ?;", (main["id"],)
        ).fetchone()
        screen2 = resolve_category_screen(self.conn, leaf["id"])
        self.assertEqual(screen2["back"], f"cat:{main['id']}:0")

        # leaf's back target must resolve to the SAME main category we came from
        back_id = int(screen2["back"].split(":")[1])
        self.assertEqual(back_id, main["id"])

        # root's back target chain terminates correctly (no infinite loop)
        root_target = "cat:0:0"
        root_cat_id = int(root_target.split(":")[1])
        self.assertEqual(root_cat_id, 0)

    def test_unknown_category_id_is_reported_not_found(self):
        screen = resolve_category_screen(self.conn, 999999)
        self.assertEqual(screen["kind"], "not_found")


if __name__ == "__main__":
    unittest.main()
