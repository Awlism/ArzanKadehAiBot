# -*- coding: utf-8 -*-
"""
Phase 1 ("Core & Database") infrastructure tests:

- orders table: schema, FKs, status CHECK constraint, repository functions
- get_product_by_id / get_seller_by_id: byte-identical behavior to the
  inline SQL they replaced (a pure, behavior-preserving refactor)
- get_seller_statistics / get_product_statistics: real numbers from real
  data, 0/empty (never fabricated) when no orders exist yet
- User/Role integrity: picking a role, or owning a seller, NEVER creates
  a second user row for the same telegram_id
- Request persistence: a request survives as a real row (not just a
  Telegram message) and correctly links to a seller when relevant
- Seller/Store/Product/Order relations: foreign keys are enforced
- Security/configuration: no hardcoded secrets anywhere in bot.py

Runs against real SQLite via tests/_fakedb.py -- no aiogram/aiosqlite needed.
"""
import asyncio
import os
import re
import sqlite3
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
    "get_product_by_id", "get_seller_by_id",
    "create_product_record", "delete_product_record",
    "ORDER_STATUSES", "create_order", "get_order", "update_order_status",
    "list_orders_for_buyer", "list_orders_for_seller",
    "get_seller_statistics", "get_product_statistics",
    "user_has_any_seller", "get_active_mode", "set_active_mode", "VALID_MODES",
    "create_request", "list_my_requests", "count_seller_favorites",
    "REQUEST_STATUS_LABELS",
    "now_iso", "logger",
]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class OrdersInfrastructureTests(unittest.TestCase):
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
        self.conn.execute(
            """INSERT INTO products (id, seller_id, name, price, stock_status, created_at, updated_at)
               VALUES (100, 10, 'Widget', 50000, 'AVAILABLE', 't', 't');"""
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_orders_table_exists_with_expected_columns(self):
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(orders);").fetchall()}
        for col in ("buyer_user_id", "seller_id", "product_id", "quantity", "total_price", "status"):
            self.assertIn(col, cols)

    def test_orders_foreign_keys_are_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                """INSERT INTO orders (buyer_user_id, seller_id, product_id, quantity, status, created_at, updated_at)
                   VALUES (1, 99999, 100, 1, 'PENDING', 't', 't');"""
            )
            self.conn.commit()

    def test_orders_status_check_constraint_rejects_invalid_status(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                """INSERT INTO orders (buyer_user_id, seller_id, product_id, quantity, status, created_at, updated_at)
                   VALUES (1, 10, 100, 1, 'NOT_A_REAL_STATUS', 't', 't');"""
            )
            self.conn.commit()

    def test_create_order_and_get_order_round_trip(self):
        order_id = run(self.ns["create_order"](1, 10, 100, quantity=2, total_price=100000))
        order = run(self.ns["get_order"](order_id))
        self.assertEqual(order["buyer_user_id"], 1)
        self.assertEqual(order["seller_id"], 10)
        self.assertEqual(order["product_id"], 100)
        self.assertEqual(order["quantity"], 2)
        self.assertEqual(order["total_price"], 100000)
        self.assertEqual(order["status"], "PENDING")

    def test_update_order_status_persists(self):
        order_id = run(self.ns["create_order"](1, 10, 100))
        run(self.ns["update_order_status"](order_id, "COMPLETED"))
        order = run(self.ns["get_order"](order_id))
        self.assertEqual(order["status"], "COMPLETED")

    def test_update_order_status_rejects_invalid_status(self):
        order_id = run(self.ns["create_order"](1, 10, 100))
        with self.assertRaises(ValueError):
            run(self.ns["update_order_status"](order_id, "MADE_UP_STATUS"))

    def test_list_orders_for_buyer_and_seller(self):
        run(self.ns["create_order"](1, 10, 100))
        run(self.ns["create_order"](1, 10, 100))
        buyer_orders = run(self.ns["list_orders_for_buyer"](1))
        seller_orders = run(self.ns["list_orders_for_seller"](10))
        self.assertEqual(len(buyer_orders), 2)
        self.assertEqual(len(seller_orders), 2)

    # ------------------------------------------------------------
    # Statistics: real numbers, never fabricated
    # ------------------------------------------------------------
    def test_seller_statistics_with_no_orders_yet_shows_honest_zeros(self):
        stats = run(self.ns["get_seller_statistics"](10))
        self.assertEqual(stats["product_count"], 1)
        self.assertEqual(stats["active_product_count"], 1)
        self.assertEqual(stats["completed_order_count"], 0)
        self.assertEqual(stats["completed_order_revenue"], 0)

    def test_seller_statistics_reflects_completed_orders_only(self):
        oid1 = run(self.ns["create_order"](1, 10, 100, total_price=50000))
        oid2 = run(self.ns["create_order"](1, 10, 100, total_price=70000))
        run(self.ns["update_order_status"](oid1, "COMPLETED"))
        # oid2 stays PENDING -- must NOT count toward completed stats.
        stats = run(self.ns["get_seller_statistics"](10))
        self.assertEqual(stats["completed_order_count"], 1)
        self.assertEqual(stats["completed_order_revenue"], 50000)

    def test_product_statistics_with_no_orders_yet_shows_honest_zeros(self):
        stats = run(self.ns["get_product_statistics"](100))
        self.assertEqual(stats["completed_order_count"], 0)
        self.assertEqual(stats["completed_units_sold"], 0)

    def test_product_statistics_reflects_completed_units(self):
        oid = run(self.ns["create_order"](1, 10, 100, quantity=3))
        run(self.ns["update_order_status"](oid, "COMPLETED"))
        stats = run(self.ns["get_product_statistics"](100))
        self.assertEqual(stats["completed_order_count"], 1)
        self.assertEqual(stats["completed_units_sold"], 3)

    # ------------------------------------------------------------
    # get_product_by_id / get_seller_by_id: behavior-identical to the
    # inline SQL they replaced
    # ------------------------------------------------------------
    def test_get_product_by_id_matches_inline_query(self):
        via_helper = run(self.ns["get_product_by_id"](100))
        via_inline = self.conn.execute("SELECT * FROM products WHERE id = ?;", (100,)).fetchone()
        self.assertEqual(dict(via_helper), dict(via_inline))

    def test_get_product_by_id_returns_none_for_missing(self):
        self.assertIsNone(run(self.ns["get_product_by_id"](999999)))

    def test_get_seller_by_id_matches_inline_query(self):
        via_helper = run(self.ns["get_seller_by_id"](10))
        via_inline = self.conn.execute("SELECT * FROM sellers WHERE id = ?;", (10,)).fetchone()
        self.assertEqual(dict(via_helper), dict(via_inline))

    def test_create_and_delete_product_record(self):
        new_id = run(self.ns["create_product_record"](10, "New Thing", price=1000))
        self.assertIsNotNone(run(self.ns["get_product_by_id"](new_id)))
        run(self.ns["delete_product_record"](new_id))
        self.assertIsNone(run(self.ns["get_product_by_id"](new_id)))

    # ------------------------------------------------------------
    # User / Role integrity: one identity, role is just a mode
    # ------------------------------------------------------------
    def test_owning_a_seller_never_creates_a_second_user_row(self):
        before = self.conn.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
        # Simulate everything that touches "role" for this user.
        run(self.ns["set_active_mode"](1, "seller"))
        run(self.ns["user_has_any_seller"](1))
        run(self.ns["get_active_mode"](1))
        after = self.conn.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
        self.assertEqual(before, after)

    def test_users_telegram_id_stays_unique_regardless_of_role(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO users (telegram_id, created_at, updated_at) VALUES (100, 't', 't');"
            )
            self.conn.commit()

    # ------------------------------------------------------------
    # Requests: real persisted rows, correctly linked to a seller
    # ------------------------------------------------------------
    def test_request_persists_as_a_real_database_row(self):
        request_id = run(self.ns["create_request"](1, "support", topic="مشکل فنی", message="hi"))
        row = self.conn.execute("SELECT * FROM requests WHERE id = ?;", (request_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["request_type"], "support")
        self.assertEqual(row["status"], "PENDING")

    def test_request_can_link_to_a_seller(self):
        request_id = run(self.ns["create_request"](1, "ad", topic="⭐ فروشگاهم", seller_id=10))
        row = self.conn.execute("SELECT * FROM requests WHERE id = ?;", (request_id,)).fetchone()
        self.assertEqual(row["seller_id"], 10)

    def test_requests_appear_in_list_my_requests(self):
        run(self.ns["create_request"](1, "support", topic="سلام", message="کمک می‌خوام"))
        items = run(self.ns["list_my_requests"](1))
        self.assertEqual(len(items), 1)


class SecurityConfigurationTests(unittest.TestCase):
    """No secrets hardcoded anywhere in bot.py -- everything sensitive
    must come from os.getenv()."""

    @classmethod
    def setUpClass(cls):
        cls.source = BOT_PY_PATH.read_text(encoding="utf-8")

    def test_bot_token_is_read_from_env_not_hardcoded(self):
        self.assertIn('BOT_TOKEN: Optional[str] = os.getenv("BOT_TOKEN")', self.source)

    def test_admin_chat_id_is_read_from_env_not_hardcoded(self):
        self.assertIn('os.getenv("ADMIN_CHAT_ID"', self.source)

    def test_no_suspicious_hardcoded_secret_assignments(self):
        # Looks for patterns like TOKEN = "actual_value_here" (a literal
        # string assigned directly, not an os.getenv(...) call).
        suspicious = re.findall(
            r'\b(?:token|api_key|secret|password)\s*[:=]\s*["\'][^"\']+["\']',
            self.source,
            re.IGNORECASE,
        )
        # ADMIN_USERNAME is a public display string ("@awlism"), not a
        # secret -- explicitly not matched by the pattern above since it
        # doesn't contain the words token/api_key/secret/password.
        self.assertFalse(suspicious, f"Found suspicious hardcoded secret-like assignments: {suspicious}")


if __name__ == "__main__":
    unittest.main()
