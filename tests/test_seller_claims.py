# -*- coding: utf-8 -*-
"""
Tests for the seller-claim repository lifecycle.

Runs against real in-memory SQLite via tests/_fakedb.py without importing
the Telegram application.
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
    "run_column_migrations",
    "get_seller_claim",
    "get_pending_seller_claims",
    "get_seller_claims_for_seller",
    "get_user_seller_claims",
    "create_seller_claim",
    "approve_seller_claim",
    "reject_seller_claim",
    "is_admin_user_id",
    "now_iso",
]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class SellerClaimRepositoryTests(unittest.TestCase):
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
        self.ns["ADMIN_CHAT_ID"] = 999

        run(self.ns["run_column_migrations"]())

        self.conn.execute(
            """
            INSERT INTO users (
                id,
                telegram_id,
                username,
                first_name,
                created_at,
                updated_at
            )
            VALUES (1, 999, 'admin', 'Admin', 't', 't');
            """
        )

        self.conn.execute(
            """
            INSERT INTO users (
                id,
                telegram_id,
                username,
                first_name,
                created_at,
                updated_at
            )
            VALUES (2, 200, 'claimant', 'Claimant', 't', 't');
            """
        )

        self.conn.execute(
            """
            INSERT INTO users (
                id,
                telegram_id,
                username,
                first_name,
                created_at,
                updated_at
            )
            VALUES (3, 300, 'other', 'Other', 't', 't');
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
                20,
                'Shop Unclaimed',
                'UNCLAIMED',
                NULL,
                NULL,
                '2026-01-01T00:00:00',
                '2026-01-01T00:00:00'
            );
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
                30,
                'Shop Claimed',
                'CLAIMED',
                2,
                2,
                '2026-01-01T00:00:00',
                '2026-01-01T00:00:00'
            );
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
                40,
                'Shop Created By User',
                'UNCLAIMED',
                NULL,
                2,
                '2026-01-01T00:00:00',
                '2026-01-01T00:00:00'
            );
            """
        )

        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    # ------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------

    def test_create_claim_returns_new_id_and_pending_state(self):
        claim_id = run(
            self.ns["create_seller_claim"](20, 2)
        )

        self.assertIsInstance(claim_id, int)

        row = self.conn.execute(
            """
            SELECT seller_id, user_id, status
            FROM seller_claims
            WHERE id = ?;
            """,
            (claim_id,),
        ).fetchone()

        self.assertEqual(
            tuple(row),
            (20, 2, "PENDING"),
        )

    def test_duplicate_pending_claim_returns_same_id(self):
        first_id = run(
            self.ns["create_seller_claim"](20, 2)
        )

        second_id = run(
            self.ns["create_seller_claim"](20, 2)
        )

        self.assertEqual(first_id, second_id)

        count = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM seller_claims
            WHERE seller_id = 20
              AND user_id = 2;
            """
        ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_create_claim_rejects_missing_seller(self):
        self.assertIsNone(
            run(
                self.ns["create_seller_claim"](999, 2)
            )
        )

    def test_create_claim_rejects_claimed_seller(self):
        self.assertIsNone(
            run(
                self.ns["create_seller_claim"](30, 3)
            )
        )

    def test_create_claim_rejects_seller_owner_or_creator(self):
        self.assertIsNone(
            run(
                self.ns["create_seller_claim"](30, 2)
            )
        )

        self.assertIsNone(
            run(
                self.ns["create_seller_claim"](40, 2)
            )
        )

    # ------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------

    def test_get_seller_claim_returns_joined_claimant_and_seller_data(self):
        claim_id = run(
            self.ns["create_seller_claim"](20, 2)
        )

        claim = run(
            self.ns["get_seller_claim"](claim_id)
        )

        self.assertIsNotNone(claim)
        self.assertEqual(claim["id"], claim_id)
        self.assertEqual(claim["seller_name"], "Shop Unclaimed")
        self.assertEqual(claim["seller_status"], "UNCLAIMED")
        self.assertEqual(claim["claimant_telegram_id"], 200)
        self.assertEqual(claim["claimant_username"], "claimant")
        self.assertEqual(claim["claimant_first_name"], "Claimant")

    def test_get_seller_claim_returns_none_for_missing_claim(self):
        self.assertIsNone(
            run(
                self.ns["get_seller_claim"](999999)
            )
        )

    def test_pending_claim_list_and_limit(self):
        first_id = run(
            self.ns["create_seller_claim"](20, 2)
        )

        # Make the first claim explicitly older so the repository's
        # created_at ASC ordering is deterministic.
        self.conn.execute(
            """
            UPDATE seller_claims
            SET
                created_at = '2026-01-01T00:00:00',
                updated_at = '2026-01-01T00:00:00'
            WHERE id = ?;
            """,
            (first_id,),
        )

        self.conn.execute(
            """
            INSERT INTO seller_claims (
                seller_id,
                user_id,
                status,
                created_at,
                updated_at
            )
            VALUES (
                20,
                3,
                'PENDING',
                '2026-01-02T00:00:00',
                '2026-01-02T00:00:00'
            );
            """
        )

        self.conn.commit()

        pending = run(
            self.ns["get_pending_seller_claims"](1)
        )

        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], first_id)

        self.assertEqual(
            run(self.ns["get_pending_seller_claims"](0)),
            [],
        )

    def test_claim_lists_are_scoped_to_seller_and_user(self):
        claim_a = run(
            self.ns["create_seller_claim"](20, 2)
        )

        claim_b = run(
            self.ns["create_seller_claim"](20, 3)
        )

        seller_claims = run(
            self.ns["get_seller_claims_for_seller"](20)
        )

        self.assertEqual(
            {row["id"] for row in seller_claims},
            {claim_a, claim_b},
        )

        user_claims = run(
            self.ns["get_user_seller_claims"](2)
        )

        self.assertEqual(
            [row["id"] for row in user_claims],
            [claim_a],
        )

    # ------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------

    def test_only_configured_admin_can_approve_or_reject(self):
        claim_id = run(
            self.ns["create_seller_claim"](20, 2)
        )

        with self.assertRaises(PermissionError):
            run(
                self.ns["approve_seller_claim"](
                    claim_id,
                    2,
                )
            )

        with self.assertRaises(PermissionError):
            run(
                self.ns["reject_seller_claim"](
                    claim_id,
                    2,
                )
            )

        self.assertEqual(
            self.conn.execute(
                """
                SELECT status
                FROM seller_claims
                WHERE id = ?;
                """,
                (claim_id,),
            ).fetchone()[0],
            "PENDING",
        )

    # ------------------------------------------------------------
    # Approval
    # ------------------------------------------------------------

    def test_admin_approval_updates_claim_and_seller_atomically(self):
        claim_id = run(
            self.ns["create_seller_claim"](20, 2)
        )

        approved = run(
            self.ns["approve_seller_claim"](
                claim_id,
                1,
            )
        )

        self.assertTrue(approved)

        claim_status = self.conn.execute(
            """
            SELECT status
            FROM seller_claims
            WHERE id = ?;
            """,
            (claim_id,),
        ).fetchone()[0]

        seller_status, owner_id = self.conn.execute(
            """
            SELECT status, owner_user_id
            FROM sellers
            WHERE id = 20;
            """
        ).fetchone()

        self.assertEqual(claim_status, "APPROVED")
        self.assertEqual(seller_status, "CLAIMED")
        self.assertEqual(owner_id, 2)

    def test_approval_is_not_repeatable(self):
        claim_id = run(
            self.ns["create_seller_claim"](20, 2)
        )

        self.assertTrue(
            run(
                self.ns["approve_seller_claim"](
                    claim_id,
                    1,
                )
            )
        )

        self.assertFalse(
            run(
                self.ns["approve_seller_claim"](
                    claim_id,
                    1,
                )
            )
        )

    def test_approval_fails_when_seller_is_already_claimed(self):
        claim_id = run(
            self.ns["create_seller_claim"](20, 3)
        )

        self.conn.execute(
            """
            UPDATE sellers
            SET
                status = 'CLAIMED',
                owner_user_id = 2
            WHERE id = 20;
            """
        )

        self.conn.commit()

        self.assertFalse(
            run(
                self.ns["approve_seller_claim"](
                    claim_id,
                    1,
                )
            )
        )

        claim_status = self.conn.execute(
            """
            SELECT status
            FROM seller_claims
            WHERE id = ?;
            """,
            (claim_id,),
        ).fetchone()[0]

        self.assertEqual(claim_status, "PENDING")

    # ------------------------------------------------------------
    # Rejection
    # ------------------------------------------------------------

    def test_admin_rejection_updates_only_claim(self):
        claim_id = run(
            self.ns["create_seller_claim"](20, 2)
        )

        rejected = run(
            self.ns["reject_seller_claim"](
                claim_id,
                1,
            )
        )

        self.assertTrue(rejected)

        claim_status = self.conn.execute(
            """
            SELECT status
            FROM seller_claims
            WHERE id = ?;
            """,
            (claim_id,),
        ).fetchone()[0]

        seller_status, owner_id = self.conn.execute(
            """
            SELECT status, owner_user_id
            FROM sellers
            WHERE id = 20;
            """
        ).fetchone()

        self.assertEqual(claim_status, "REJECTED")
        self.assertEqual(seller_status, "UNCLAIMED")
        self.assertIsNone(owner_id)

    def test_rejection_is_not_repeatable(self):
        claim_id = run(
            self.ns["create_seller_claim"](20, 2)
        )

        self.assertTrue(
            run(
                self.ns["reject_seller_claim"](
                    claim_id,
                    1,
                )
            )
        )

        self.assertFalse(
            run(
                self.ns["reject_seller_claim"](
                    claim_id,
                    1,
                )
            )
        )

    def test_reject_missing_claim_returns_false(self):
        self.assertFalse(
            run(
                self.ns["reject_seller_claim"](
                    999999,
                    1,
                )
            )
        )


if __name__ == "__main__":
    unittest.main()