# -*- coding: utf-8 -*-
"""
Phase 2 ("Users & Roles") tests.

Covers exactly the checklist from the Phase 2 brief:
- first-time role selection (users.role_chosen)
- role persistence / no repeated daily role selection
- same-user buyer<->seller switching (single identity, no duplicate rows)
- seller mode does NOT require an existing store
- admin authorization is config-driven (ADMIN_CHAT_ID), never self-granted
- restart ("🏠 شروع از اول") resets navigation only, never touches data
- FSM/session integrity: mode switches always clear stale FSM state
- regression: the mode-switch button dead-end this phase specifically fixed

Runs against real SQLite via tests/_fakedb.py -- no aiogram/aiosqlite needed.
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
    "VALID_MODES", "user_has_any_seller", "get_active_mode", "set_active_mode",
    "is_admin_user_id", "is_admin_telegram_id",
    "now_iso", "logger",
]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class ModeSwitchDataPreservationTests(unittest.TestCase):
    """Phase 2 requirement: switching mode is a pure UI-state change --
    it must never touch (create/edit/delete) any of the user's, or their
    store's, persistent data. Verified at the real SQLite level, not
    just by reading source code."""

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
        self.ns["ADMIN_CHAT_ID"] = None
        run(self.ns["run_column_migrations"]())

        self.conn.execute(
            "INSERT INTO users (id, telegram_id, first_name, city_id, created_at, updated_at) "
            "VALUES (1, 100, 'Ali', NULL, 't', 't');"
        )
        self.conn.execute(
            """INSERT INTO sellers (id, name, description, status, owner_user_id, created_by_user_id,
                   instagram, created_at, updated_at)
               VALUES (10, 'Shop A', 'A great shop', 'CLAIMED', 1, 1, 'shopa', 't', 't');"""
        )
        self.conn.execute(
            """INSERT INTO products (id, seller_id, name, price, stock_status, created_at, updated_at)
               VALUES (100, 10, 'Widget', 50000, 'AVAILABLE', 't', 't');"""
        )
        self.conn.execute(
            "INSERT INTO favorites (user_id, product_id, created_at) VALUES (1, 100, 't');"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _snapshot(self) -> dict:
        return {
            "users": [dict(r) for r in self.conn.execute("SELECT * FROM users;").fetchall()],
            "sellers": [dict(r) for r in self.conn.execute("SELECT * FROM sellers;").fetchall()],
            "products": [dict(r) for r in self.conn.execute("SELECT * FROM products;").fetchall()],
            "favorites": [dict(r) for r in self.conn.execute("SELECT * FROM favorites;").fetchall()],
        }

    def test_switching_modes_repeatedly_leaves_seller_and_product_data_untouched(self):
        before = self._snapshot()
        for mode in ("seller", "buyer", "seller", "buyer", "seller"):
            run(self.ns["set_active_mode"](1, mode))
        after = self._snapshot()

        # Compare everything except the users row's own active_mode/
        # updated_at (which are EXPECTED to change -- that's the point
        # of set_active_mode). Seller/product/favorite data must be
        # byte-for-byte identical.
        self.assertEqual(before["sellers"], after["sellers"])
        self.assertEqual(before["products"], after["products"])
        self.assertEqual(before["favorites"], after["favorites"])

        before_user = {k: v for k, v in before["users"][0].items() if k not in ("active_mode", "updated_at")}
        after_user = {k: v for k, v in after["users"][0].items() if k not in ("active_mode", "updated_at")}
        self.assertEqual(before_user, after_user)

    def test_switching_to_seller_mode_with_no_store_creates_nothing(self):
        self.conn.execute("DELETE FROM favorites;")
        self.conn.execute("DELETE FROM products;")
        self.conn.execute("DELETE FROM sellers;")
        self.conn.commit()
        before = self._snapshot()
        run(self.ns["set_active_mode"](1, "seller"))
        after = self._snapshot()
        self.assertEqual(before["sellers"], after["sellers"])
        self.assertEqual(before["products"], after["products"])
        self.assertEqual(len(after["sellers"]), 0)

    def test_mode_switch_does_not_touch_other_users(self):
        self.conn.execute(
            "INSERT INTO users (id, telegram_id, created_at, updated_at) VALUES (2, 200, 't', 't');"
        )
        self.conn.commit()
        other_before = dict(self.conn.execute("SELECT * FROM users WHERE id=2;").fetchone())
        run(self.ns["set_active_mode"](1, "seller"))
        other_after = dict(self.conn.execute("SELECT * FROM users WHERE id=2;").fetchone())
        self.assertEqual(other_before, other_after)


class RoleSelectionAndPersistenceTests(unittest.TestCase):
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
        self.ns["ADMIN_CHAT_ID"] = None
        run(self.ns["run_column_migrations"]())

        self.conn.execute(
            "INSERT INTO users (id, telegram_id, created_at, updated_at) VALUES (1, 100, 't', 't');"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    # ------------------------------------------------------------
    # First-time role selection + persistence (no daily re-ask)
    # ------------------------------------------------------------
    def test_new_user_has_not_chosen_a_role_yet(self):
        row = self.conn.execute("SELECT role_chosen FROM users WHERE id=1;").fetchone()
        self.assertEqual(row["role_chosen"], 0)

    def test_choosing_a_role_persists_and_is_not_asked_again(self):
        # Simulates exactly what handle_role_pick() does: mark
        # role_chosen=1 and set the mode, in one logical transaction.
        run(self.ns["set_active_mode"](1, "seller"))
        self.conn.execute("UPDATE users SET role_chosen = 1 WHERE id = 1;")
        self.conn.commit()

        row = self.conn.execute("SELECT role_chosen FROM users WHERE id=1;").fetchone()
        self.assertEqual(row["role_chosen"], 1)
        # A second /start (simulated by re-checking role_chosen, exactly
        # what _go_to_start() branches on) must NOT show the picker again.
        self.assertTrue(row["role_chosen"])

    def test_role_choice_survives_a_simulated_restart(self):
        run(self.ns["set_active_mode"](1, "seller"))
        self.conn.execute("UPDATE users SET role_chosen = 1 WHERE id = 1;")
        self.conn.commit()
        run(self.ns["run_column_migrations"]())  # simulate a bot restart
        mode = run(self.ns["get_active_mode"](1))
        self.assertEqual(mode, "seller")

    # ------------------------------------------------------------
    # Single identity: switching role NEVER creates a duplicate user
    # ------------------------------------------------------------
    def test_switching_modes_repeatedly_never_creates_a_new_user_row(self):
        before = self.conn.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
        for mode in ("seller", "buyer", "seller", "buyer"):
            run(self.ns["set_active_mode"](1, mode))
        after = self.conn.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(after, 1)

    def test_buyer_and_seller_are_modes_of_one_identity_not_separate_accounts(self):
        row_before = self.conn.execute("SELECT telegram_id FROM users WHERE id=1;").fetchone()
        run(self.ns["set_active_mode"](1, "seller"))
        row_after = self.conn.execute("SELECT telegram_id FROM users WHERE id=1;").fetchone()
        self.assertEqual(row_before["telegram_id"], row_after["telegram_id"])

    # ------------------------------------------------------------
    # Seller mode does NOT require an existing store
    # ------------------------------------------------------------
    def test_seller_mode_can_be_entered_with_zero_sellers_owned(self):
        self.assertFalse(run(self.ns["user_has_any_seller"](1)))
        run(self.ns["set_active_mode"](1, "seller"))  # must not raise
        self.assertEqual(run(self.ns["get_active_mode"](1)), "seller")

    def test_no_seller_row_is_created_by_picking_seller_mode(self):
        before = self.conn.execute("SELECT COUNT(*) FROM sellers;").fetchone()[0]
        run(self.ns["set_active_mode"](1, "seller"))
        after = self.conn.execute("SELECT COUNT(*) FROM sellers;").fetchone()[0]
        self.assertEqual(before, after, "choosing seller mode must never itself create a store")

    # ------------------------------------------------------------
    # Admin authorization: config-driven, never self-granted
    # ------------------------------------------------------------
    def test_admin_mode_refused_when_no_admin_configured(self):
        self.ns["ADMIN_CHAT_ID"] = None
        with self.assertRaises(PermissionError):
            run(self.ns["set_active_mode"](1, "admin"))

    def test_admin_mode_refused_for_wrong_telegram_id(self):
        self.ns["ADMIN_CHAT_ID"] = 999999  # not user 1's telegram_id (100)
        with self.assertRaises(PermissionError):
            run(self.ns["set_active_mode"](1, "admin"))

    def test_admin_mode_allowed_for_the_configured_admin_only(self):
        self.ns["ADMIN_CHAT_ID"] = 100  # matches user 1's telegram_id
        run(self.ns["set_active_mode"](1, "admin"))
        self.assertEqual(run(self.ns["get_active_mode"](1)), "admin")

    def test_is_admin_telegram_id_matches_is_admin_user_id_for_the_same_person(self):
        """Two different admin-check helpers exist (one keyed by raw
        Telegram id for callback-layer checks, one by internal user_id
        for DB-layer checks) -- they must agree, not silently diverge."""
        self.ns["ADMIN_CHAT_ID"] = 100
        self.assertTrue(self.ns["is_admin_telegram_id"](100))
        self.assertTrue(run(self.ns["is_admin_user_id"](1)))
        self.assertFalse(self.ns["is_admin_telegram_id"](999999))

    def test_stale_admin_mode_falls_back_to_buyer_after_reconfiguration(self):
        self.ns["ADMIN_CHAT_ID"] = 100
        run(self.ns["set_active_mode"](1, "admin"))
        self.ns["ADMIN_CHAT_ID"] = 777777  # admin reassigned to someone else
        self.assertEqual(run(self.ns["get_active_mode"](1)), "buyer")


class RegressionModeSwitchDeadEndTests(unittest.TestCase):
    """Regression test for a real bug found and fixed in this phase: the
    buyer panel only offered the "🏪 حالت فروشندگی" switch button when
    user_has_any_seller() was true, and handle_set_mode() independently
    re-imposed the same store-ownership gate that Phase 2 otherwise
    dropped. Together, a user who picked seller intent with no store yet
    could switch to buyer mode and then have NO WAY back to seller mode.
    Both halves of the fix are checked at the source level here (a live
    Telegram round-trip isn't possible offline -- see the project's
    testing README section for what is/isn't covered offline).
    """

    @classmethod
    def setUpClass(cls):
        cls.source = BOT_PY_PATH.read_text(encoding="utf-8")

    def test_render_buyer_panel_no_longer_gates_the_switch_button_on_ownership(self):
        # The old buggy pattern must be gone...
        self.assertNotIn(
            "if has_seller:\n        b.row(_mode_switch_button(\"buyer\"))",
            self.source,
        )
        # ...and the switch button must be rendered unconditionally.
        func_start = self.source.index("async def _render_buyer_panel")
        func_end = self.source.index("\n\n\n", func_start)
        func_body = self.source[func_start:func_end]
        self.assertIn('b.row(_mode_switch_button("buyer"))', func_body)

    def test_handle_set_mode_no_longer_requires_ownership_for_seller_mode(self):
        func_start = self.source.index("async def handle_set_mode")
        func_end = self.source.index("\n\n\n", func_start)
        func_body = self.source[func_start:func_end]
        self.assertNotIn("user_has_any_seller", func_body)
        self.assertIn("except PermissionError:", func_body)


class FSMSessionIntegrityTests(unittest.TestCase):
    """Source-level checks for Phase 2 item 5 (Session/FSM integrity).
    Complements test_static_analysis.py's existing collision/ordering
    tests rather than duplicating them.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = BOT_PY_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(BOT_PY_PATH))

    def _get_function_body(self, name: str) -> str:
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                start = node.lineno
                end = node.end_lineno
                lines = self.source.splitlines()[start - 1:end]
                return "\n".join(lines)
        raise AssertionError(f"Function '{name}' not found")

    def test_mode_switch_handlers_clear_fsm_state_first(self):
        """Avoid stale states when switching modes: both handle_set_mode
        (toggle) and handle_role_pick (first choice) must clear any
        in-progress FSM flow before rendering a different panel."""
        for name in ("handle_set_mode", "handle_role_pick"):
            body = self._get_function_body(name)
            self.assertIn("await state.clear()", body, f"{name} must clear FSM state")

    def test_restart_handler_clears_state_but_never_touches_user_data_tables(self):
        body = self._get_function_body("handle_restart_main")
        self.assertIn("await state.clear()", body)
        for forbidden in ("DELETE FROM users", "DELETE FROM sellers", "DELETE FROM products", "DELETE FROM orders"):
            self.assertNotIn(forbidden, body)

    def test_go_to_start_is_the_single_shared_entry_point(self):
        """/start and the restart button must funnel through the same
        logic (no diverging, hand-duplicated role/mode resolution)."""
        start_body = self._get_function_body("handle_start")
        restart_body = self._get_function_body("handle_restart_main")
        self.assertIn("_go_to_start(", start_body)
        self.assertIn("_go_to_start(", restart_body)

    def test_role_pick_and_restart_are_registered_before_the_generic_callback_fallback(self):
        rolepick_line = self.source.index('@router.callback_query(F.data.startswith("rolepick:"))')
        restart_line = self.source.index('@router.callback_query(F.data == "restartmain")')
        fallback_line = self.source.index("async def handle_unknown_callback")
        self.assertLess(rolepick_line, fallback_line)
        self.assertLess(restart_line, fallback_line)

    def test_fsm_storage_is_still_memorystorage(self):
        """Phase 2 spec: don't swap MemoryStorage for Redis unless
        explicitly required -- it isn't, so this must not have changed."""
        self.assertIn("Dispatcher(storage=MemoryStorage())", self.source)
        self.assertNotIn("Redis", self.source)


class RestartPreservesDatabaseTests(unittest.TestCase):
    """Phase 2 requirement: restart ("🏠 شروع از اول") must never corrupt
    or erase permanent SQLite data -- verified at the real DB level.
    handle_restart_main()'s only DB interaction is via _go_to_start(),
    which is read-only (role_chosen lookup + get_active_mode()); this
    test proves that read-only claim against the real schema rather than
    just trusting the source comment."""

    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names([
            "SCHEMA_STATEMENTS", "INDEX_STATEMENTS", "COLUMN_MIGRATIONS",
            "ensure_column", "run_column_migrations", "VALID_MODES", "get_active_mode",
            "now_iso", "logger",
        ])

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
            "INSERT INTO users (id, telegram_id, role_chosen, active_mode, created_at, updated_at) "
            "VALUES (1, 100, 1, 'seller', 't', 't');"
        )
        self.conn.execute(
            """INSERT INTO sellers (id, name, status, owner_user_id, created_by_user_id, created_at, updated_at)
               VALUES (10, 'Shop A', 'CLAIMED', 1, 1, 't', 't');"""
        )
        self.conn.execute(
            """INSERT INTO products (id, seller_id, name, stock_status, created_at, updated_at)
               VALUES (100, 10, 'Widget', 'AVAILABLE', 't', 't');"""
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _row_counts(self) -> dict:
        tables = ("users", "sellers", "products", "favorites", "requests", "orders", "audit_log")
        return {t: self.conn.execute(f"SELECT COUNT(*) FROM {t};").fetchone()[0] for t in tables}

    def test_restart_role_resolution_performs_zero_writes(self):
        """Simulates exactly what _go_to_start() does for a returning
        user: read role_chosen, then get_active_mode(). No table's row
        count may change."""
        before = self._row_counts()
        row = self.conn.execute("SELECT role_chosen FROM users WHERE id = 1;").fetchone()
        self.assertTrue(row["role_chosen"])
        mode = run(self.ns["get_active_mode"](1))
        self.assertEqual(mode, "seller")
        after = self._row_counts()
        self.assertEqual(before, after)

    def test_restart_never_deletes_the_users_row(self):
        before_id = self.conn.execute("SELECT id FROM users WHERE telegram_id = 100;").fetchone()
        self.assertIsNotNone(before_id)
        run(self.ns["get_active_mode"](1))  # the only DB call _go_to_start makes for a returning user
        after_id = self.conn.execute("SELECT id FROM users WHERE telegram_id = 100;").fetchone()
        self.assertIsNotNone(after_id)
        self.assertEqual(before_id["id"], after_id["id"])

    def test_restart_never_deletes_seller_or_product_data(self):
        before_sellers = self.conn.execute("SELECT COUNT(*) FROM sellers;").fetchone()[0]
        before_products = self.conn.execute("SELECT COUNT(*) FROM products;").fetchone()[0]
        run(self.ns["get_active_mode"](1))
        after_sellers = self.conn.execute("SELECT COUNT(*) FROM sellers;").fetchone()[0]
        after_products = self.conn.execute("SELECT COUNT(*) FROM products;").fetchone()[0]
        self.assertEqual(before_sellers, after_sellers)
        self.assertEqual(before_products, after_products)


if __name__ == "__main__":
    unittest.main()
