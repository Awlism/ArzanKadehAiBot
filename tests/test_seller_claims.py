# -*- coding: utf-8 -*-
"""
Seller ownership claim repository tests.

These tests intentionally exercise the seller-claim lifecycle without
running the full project test suite.
"""

from __future__ import annotations

import asyncio
import inspect
import sqlite3
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Minimal module stubs for extracting repository/database functions without
# importing the entire bot runtime.
# ---------------------------------------------------------------------------

def _install_stub_modules() -> None:
    if "bot.config" not in sys.modules:
        config = types.ModuleType("bot.config")
        config.ADMIN_CHAT_ID = 100
        config.DATABASE_PATH = ":memory:"
        config.SEED_DEMO_DATA = False
        sys.modules["bot.config"] = config

    if "bot.utils" not in sys.modules:
        utils = types.ModuleType("bot.utils")

        def now_iso() -> str:
            return "2026-01-01T00:00:00+00:00"

        utils.now_iso = now_iso
        sys.modules["bot.utils"] = utils


_install_stub_modules()


# ---------------------------------------------------------------------------
# Source extraction helpers
# ---------------------------------------------------------------------------

def _extract_source() -> str:
    path = ROOT / "bot" / "repositories.py"
    return path.read_text(encoding="utf-8")


def _extract_database_source() -> str:
    path = ROOT / "bot" / "database.py"
    return path.read_text(encoding="utf-8")


def _extract_symbol(source: str, name: str) -> str:
    import ast

    tree = ast.parse(source)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return ast.get_source_segment(source, node) or ""

    raise AssertionError(f"Could not extract symbol: {name}")


def _extract_assignment(source: str, name: str) -> str:
    import ast

    tree = ast.parse(source)

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.get_source_segment(source, node) or ""

    raise AssertionError(f"Could not extract assignment: {name}")


def _load_symbols() -> dict[str, object]:
    repository_source = _extract_source()
    database_source = _extract_database_source()

    names = [
        "get_seller_claim",
        "get_pending_seller_claims",
        "get_seller_claims_for_seller",
        "get_user_seller_claims",
        "create_seller_claim",
        "approve_seller_claim",
        "reject_seller_claim",
        "is_admin_user_id",
    ]

    namespace: dict[str, object] = {
        "__name__": "bot.repositories",
        "__package__": "bot",
        "Optional": object,
        "Any": object,
    }

    # Fake imports used by the extracted repository functions.
    config = sys.modules["bot.config"]
    namespace["ADMIN_CHAT_ID"] = config.ADMIN_CHAT_ID

    utils = sys.modules["bot.utils"]
    namespace["now_iso"] = utils.now_iso

    for name in names:
        exec(_extract_symbol(repository_source, name), namespace)

    # Database schema/migration assignments/functions.
    database_namespace: dict[str, object] = {
        "__name__": "bot.database",
        "__package__": "bot",
        "Optional": object,
        "Sequence": object,
        "logging": __import__("logging"),
        "re": __import__("re"),
        "datetime": __import__("datetime").datetime,
        "timezone": __import__("datetime").timezone,
        "aiosqlite": __import__("aiosqlite"),
        "DATABASE_PATH": ":memory:",
        "SEED_DEMO_DATA": False,
    }

    for name in ("SCHEMA_STATEMENTS", "INDEX_STATEMENTS"):
        exec(
            _extract_assignment(database_source, name),
            database_namespace,
        )

    exec(
        _extract_symbol(database_source, "run_column_migrations"),
        database_namespace,
    )

    exec(
        _extract_symbol(database_source, "run_seller_claim_migration"),
        database_namespace,
    )

    namespace["SCHEMA_STATEMENTS"] = database_namespace["SCHEMA_STATEMENTS"]
    namespace["INDEX_STATEMENTS"] = database_namespace["INDEX_STATEMENTS"]
    namespace["run_column_migrations"] = database_namespace[
        "run_column_migrations"
    ]
    namespace["run_seller_claim_migration"] = database_namespace[
        "run_seller_claim_migration"
    ]

    return namespace


_SYMBOLS = _load_symbols()


# ---------------------------------------------------------------------------
# Lightweight async database wrapper
# ---------------------------------------------------------------------------

class FakeCursor:
    def __init__(self, cursor: sqlite3.Cursor):
        self._cursor = cursor
        self.lastrowid = cursor.lastrowid
        self.rowcount = cursor.rowcount


class FakeDB:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    async def execute(self, query: str, params=()) -> FakeCursor:
        cursor = self.conn.execute(query, tuple(params))
        self.conn.commit()
        return FakeCursor(cursor)

    async def fetchone(self, query: str, params=()):
        cursor = self.conn.execute(query, tuple(params))
        return cursor.fetchone()

    async def fetchall(self, query: str, params=()):
        cursor = self.conn.execute(query, tuple(params))
        return cursor.fetchall()

    async def executescript(self, script: str) -> None:
        self.conn.executescript(script)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class SellerClaimsRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = FakeDB()

        _SYMBOLS["db"] = self.db

        self.schema_statements = _SYMBOLS["SCHEMA_STATEMENTS"]
        self.index_statements = _SYMBOLS["INDEX_STATEMENTS"]
        self.run_column_migrations = _SYMBOLS["run_column_migrations"]
        self.run_seller_claim_migration = _SYMBOLS[
            "run_seller_claim_migration"
        ]

        for statement in self.schema_statements:
            self.db.conn.execute(statement)

        self.db.conn.commit()

        for statement in self.index_statements:
            self.db.conn.execute(statement)

        self.db.conn.commit()

        _run(self.run_column_migrations(self.db))
        _run(self.run_seller_claim_migration(self.db))

        self._seed_users()
        self._seed_sellers()

    def tearDown(self) -> None:
        self.db.close()

    def _seed_users(self) -> None:
        self.db.conn.execute(
            """
            INSERT INTO users (
                id,
                telegram_id,
                username,
                first_name,
                role,
                active_mode
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (1, 100, "admin", "Admin", "admin", "admin"),
        )

        self.db.conn.execute(
            """
            INSERT INTO users (
                id,
                telegram_id,
                username,
                first_name,
                role,
                active_mode
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (2, 200, "buyer", "Buyer", "user", "buyer"),
        )

        self.db.conn.execute(
            """
            INSERT INTO users (
                id,
                telegram_id,
                username,
                first_name,
                role,
                active_mode
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (3, 300, "seller", "Seller", "seller", "seller"),
        )

        self.db.conn.commit()

    def _seed_sellers(self) -> None:
        self.db.conn.execute(
            """
            INSERT INTO sellers (
                id,
                name,
                status,
                owner_user_id,
                created_by_user_id,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (20, "Unclaimed Store", "UNCLAIMED", None, None, 1),
        )

        self.db.conn.execute(
            """
            INSERT INTO sellers (
                id,
                name,
                status,
                owner_user_id,
                created_by_user_id,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (30, "Claimed Store", "CLAIMED", 3, 3, 1),
        )

        self.db.conn.execute(
            """
            INSERT INTO sellers (
                id,
                name,
                status,
                owner_user_id,
                created_by_user_id,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (40, "Created By User", "UNCLAIMED", None, 2, 1),
        )

        self.db.conn.commit()

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def test_create_claim_returns_new_pending_claim(self) -> None:
        claim_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        self.assertIsNotNone(claim_id)

        row = self.db.conn.execute(
            """
            SELECT seller_id, user_id, status
            FROM seller_claims
            WHERE id = ?
            """,
            (claim_id,),
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["seller_id"], 20)
        self.assertEqual(row["user_id"], 2)
        self.assertEqual(row["status"], "PENDING")

    def test_duplicate_pending_claim_returns_same_id(self) -> None:
        first_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        second_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        self.assertEqual(first_id, second_id)

        count = self.db.conn.execute(
            """
            SELECT COUNT(*)
            FROM seller_claims
            WHERE seller_id = ? AND user_id = ?
            """,
            (20, 2),
        ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_rejected_claim_can_be_submitted_again(self) -> None:
        first_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        self.assertIsNotNone(first_id)

        rejected = _run(
            _SYMBOLS["reject_seller_claim"](first_id, 1)
        )

        self.assertTrue(rejected)

        second_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        self.assertIsNotNone(second_id)
        self.assertNotEqual(first_id, second_id)

        rows = self.db.conn.execute(
            """
            SELECT id, status
            FROM seller_claims
            WHERE seller_id = ? AND user_id = ?
            ORDER BY id ASC
            """,
            (20, 2),
        ).fetchall()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], first_id)
        self.assertEqual(rows[0]["status"], "REJECTED")
        self.assertEqual(rows[1]["id"], second_id)
        self.assertEqual(rows[1]["status"], "PENDING")

    def test_missing_seller_returns_none(self) -> None:
        claim_id = _run(
            _SYMBOLS["create_seller_claim"](999, 2)
        )

        self.assertIsNone(claim_id)

    def test_claimed_seller_returns_none(self) -> None:
        claim_id = _run(
            _SYMBOLS["create_seller_claim"](30, 2)
        )

        self.assertIsNone(claim_id)

    def test_owner_cannot_claim_own_store(self) -> None:
        self.db.conn.execute(
            """
            UPDATE sellers
            SET owner_user_id = ?
            WHERE id = ?
            """,
            (2, 20),
        )
        self.db.conn.commit()

        claim_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        self.assertIsNone(claim_id)

    def test_creator_cannot_claim_own_store(self) -> None:
        claim_id = _run(
            _SYMBOLS["create_seller_claim"](40, 2)
        )

        self.assertIsNone(claim_id)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def test_get_seller_claim_returns_joined_data(self) -> None:
        claim_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        row = _run(
            _SYMBOLS["get_seller_claim"](claim_id)
        )

        self.assertIsNotNone(row)
        self.assertEqual(row["id"], claim_id)
        self.assertEqual(row["seller_id"], 20)
        self.assertEqual(row["user_id"], 2)
        self.assertEqual(row["status"], "PENDING")

    def test_get_seller_claim_missing_returns_none(self) -> None:
        row = _run(
            _SYMBOLS["get_seller_claim"](999999)
        )

        self.assertIsNone(row)

    def test_get_pending_seller_claims_returns_pending_only(self) -> None:
        first_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        second_id = _run(
            _SYMBOLS["create_seller_claim"](20, 3)
        )

        _run(
            _SYMBOLS["reject_seller_claim"](first_id, 1)
        )

        rows = _run(
            _SYMBOLS["get_pending_seller_claims"](100)
        )

        ids = {int(row["id"]) for row in rows}

        self.assertNotIn(first_id, ids)
        self.assertIn(second_id, ids)

    def test_get_pending_seller_claims_respects_limit(self) -> None:
        for user_id, seller_id in (
            (2, 20),
            (3, 20),
            (2, 40),
        ):
            # seller 40 is created by user 2, so use a different claimant
            claimant = 3 if seller_id == 40 else user_id
            _run(
                _SYMBOLS["create_seller_claim"](
                    seller_id,
                    claimant,
                )
            )

        rows = _run(
            _SYMBOLS["get_pending_seller_claims"](2)
        )

        self.assertLessEqual(len(rows), 2)

    def test_get_seller_claims_for_seller_is_scoped(self) -> None:
        first_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        second_id = _run(
            _SYMBOLS["create_seller_claim"](20, 3)
        )

        rows = _run(
            _SYMBOLS["get_seller_claims_for_seller"](20)
        )

        ids = {int(row["id"]) for row in rows}

        self.assertEqual(ids, {first_id, second_id})

    def test_get_user_seller_claims_is_scoped(self) -> None:
        first_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        second_id = _run(
            _SYMBOLS["create_seller_claim"](20, 3)
        )

        rows = _run(
            _SYMBOLS["get_user_seller_claims"](2)
        )

        ids = {int(row["id"]) for row in rows}

        self.assertIn(first_id, ids)
        self.assertNotIn(second_id, ids)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def test_only_admin_can_approve_claim(self) -> None:
        claim_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        result = _run(
            _SYMBOLS["approve_seller_claim"](claim_id, 2)
        )

        self.assertFalse(result)

        claim = self.db.conn.execute(
            """
            SELECT status
            FROM seller_claims
            WHERE id = ?
            """,
            (claim_id,),
        ).fetchone()

        self.assertEqual(claim["status"], "PENDING")

    def test_only_admin_can_reject_claim(self) -> None:
        claim_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        result = _run(
            _SYMBOLS["reject_seller_claim"](claim_id, 2)
        )

        self.assertFalse(result)

        claim = self.db.conn.execute(
            """
            SELECT status
            FROM seller_claims
            WHERE id = ?
            """,
            (claim_id,),
        ).fetchone()

        self.assertEqual(claim["status"], "PENDING")

    # ------------------------------------------------------------------
    # Approval lifecycle
    # ------------------------------------------------------------------

    def test_admin_approval_is_atomic(self) -> None:
        claim_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        result = _run(
            _SYMBOLS["approve_seller_claim"](claim_id, 1)
        )

        self.assertTrue(result)

        claim = self.db.conn.execute(
            """
            SELECT status
            FROM seller_claims
            WHERE id = ?
            """,
            (claim_id,),
        ).fetchone()

        seller = self.db.conn.execute(
            """
            SELECT status, owner_user_id
            FROM sellers
            WHERE id = ?
            """,
            (20,),
        ).fetchone()

        self.assertEqual(claim["status"], "APPROVED")
        self.assertEqual(seller["status"], "CLAIMED")
        self.assertEqual(seller["owner_user_id"], 2)

    def test_approved_claim_cannot_be_approved_again(self) -> None:
        claim_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        self.assertTrue(
            _run(
                _SYMBOLS["approve_seller_claim"](claim_id, 1)
            )
        )

        self.assertFalse(
            _run(
                _SYMBOLS["approve_seller_claim"](claim_id, 1)
            )
        )

    def test_approval_fails_if_seller_is_already_claimed(self) -> None:
        claim_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        self.db.conn.execute(
            """
            UPDATE sellers
            SET status = 'CLAIMED',
                owner_user_id = ?
            WHERE id = ?
            """,
            (3, 20),
        )
        self.db.conn.commit()

        result = _run(
            _SYMBOLS["approve_seller_claim"](claim_id, 1)
        )

        self.assertFalse(result)

        claim = self.db.conn.execute(
            """
            SELECT status
            FROM seller_claims
            WHERE id = ?
            """,
            (claim_id,),
        ).fetchone()

        self.assertEqual(claim["status"], "PENDING")

    # ------------------------------------------------------------------
    # Rejection lifecycle
    # ------------------------------------------------------------------

    def test_rejection_updates_only_target_claim(self) -> None:
        first_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        second_id = _run(
            _SYMBOLS["create_seller_claim"](20, 3)
        )

        result = _run(
            _SYMBOLS["reject_seller_claim"](first_id, 1)
        )

        self.assertTrue(result)

        first = self.db.conn.execute(
            """
            SELECT status
            FROM seller_claims
            WHERE id = ?
            """,
            (first_id,),
        ).fetchone()

        second = self.db.conn.execute(
            """
            SELECT status
            FROM seller_claims
            WHERE id = ?
            """,
            (second_id,),
        ).fetchone()

        self.assertEqual(first["status"], "REJECTED")
        self.assertEqual(second["status"], "PENDING")

    def test_rejected_claim_cannot_be_rejected_again(self) -> None:
        claim_id = _run(
            _SYMBOLS["create_seller_claim"](20, 2)
        )

        self.assertTrue(
            _run(
                _SYMBOLS["reject_seller_claim"](claim_id, 1)
            )
        )

        self.assertFalse(
            _run(
                _SYMBOLS["reject_seller_claim"](claim_id, 1)
            )
        )

    def test_reject_missing_claim_returns_false(self) -> None:
        result = _run(
            _SYMBOLS["reject_seller_claim"](999999, 1)
        )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()