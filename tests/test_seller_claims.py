# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker seller-ownership claim contract tests.

These tests target the current Cloudflare Worker implementation:
src/worker/seller_claims.py

They intentionally do not import or emulate the legacy bot package.
"""

from __future__ import annotations

import inspect
import unittest

from worker import seller_claims


class SellerClaimsModuleTests(unittest.TestCase):
    def test_module_is_current_worker_module(self):
        self.assertEqual(
            seller_claims.__name__,
            "worker.seller_claims",
        )

    def test_module_has_no_legacy_runtime_dependencies(self):
        source = inspect.getsource(seller_claims)

        for forbidden in (
            "from aiogram",
            "import aiogram",
            "import aiosqlite",
            "from bot",
            "import bot",
            "sqlite3",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class SellerClaimsPublicApiTests(unittest.TestCase):
    def test_public_handlers_exist(self):
        expected = (
            "handle_claim",
            "handle_seller_claims_admin",
            "handle_seller_claim_detail",
            "handle_seller_claim_decision",
        )

        for name in expected:
            with self.subTest(handler=name):
                self.assertTrue(hasattr(seller_claims, name))
                self.assertTrue(callable(getattr(seller_claims, name)))

    def test_public_api_matches_all(self):
        self.assertEqual(
            set(seller_claims.__all__),
            {
                "handle_claim",
                "handle_seller_claims_admin",
                "handle_seller_claim_detail",
                "handle_seller_claim_decision",
            },
        )


class SellerClaimsConfigurationTests(unittest.TestCase):
    def test_page_size_is_positive(self):
        self.assertGreater(seller_claims.PAGE_SIZE, 0)

    def test_page_size_is_integer(self):
        self.assertIsInstance(seller_claims.PAGE_SIZE, int)


class SellerClaimsCallbackContractTests(unittest.TestCase):
    def test_claim_handler_accepts_worker_dependencies(self):
        self.assertEqual(
            list(inspect.signature(seller_claims.handle_claim).parameters),
            ["db", "telegram", "callback_query", "env"],
        )

    def test_admin_list_handler_accepts_worker_dependencies(self):
        self.assertEqual(
            list(
                inspect.signature(
                    seller_claims.handle_seller_claims_admin
                ).parameters
            ),
            ["db", "telegram", "callback_query", "env"],
        )

    def test_detail_handler_accepts_worker_dependencies(self):
        self.assertEqual(
            list(
                inspect.signature(
                    seller_claims.handle_seller_claim_detail
                ).parameters
            ),
            ["db", "telegram", "callback_query", "env"],
        )

    def test_decision_handler_accepts_worker_dependencies(self):
        self.assertEqual(
            list(
                inspect.signature(
                    seller_claims.handle_seller_claim_decision
                ).parameters
            ),
            ["db", "telegram", "callback_query", "env"],
        )

    def test_seller_claim_callbacks_are_present(self):
        source = inspect.getsource(seller_claims)

        for callback in (
            "sellerclaimdetail:",
            "sellerclaim:approve:",
            "sellerclaim:reject:",
            "sellerclaimsadmin",
        ):
            with self.subTest(callback=callback):
                self.assertIn(callback, source)


class SellerClaimsSecurityContractTests(unittest.TestCase):
    def test_admin_guard_exists(self):
        self.assertIn(
            "_is_admin",
            inspect.getsource(
                seller_claims.handle_seller_claims_admin
            ),
        )

    def test_admin_decision_guard_exists(self):
        self.assertIn(
            "_is_admin",
            inspect.getsource(
                seller_claims.handle_seller_claim_decision
            ),
        )

    def test_claim_requires_unclaimed_status(self):
        self.assertIn("UNCLAIMED", inspect.getsource(seller_claims))

    def test_claim_uses_owner_user_id(self):
        self.assertIn("owner_user_id", inspect.getsource(seller_claims))

    def test_claim_uses_created_by_user_id(self):
        self.assertIn(
            "created_by_user_id",
            inspect.getsource(seller_claims),
        )

    def test_claim_decision_checks_pending_status(self):
        self.assertIn("PENDING", inspect.getsource(seller_claims))


class SellerClaimsPersistenceTests(unittest.TestCase):
    def test_claim_creation_writes_seller_claims(self):
        self.assertIn(
            "INSERT INTO seller_claims",
            inspect.getsource(seller_claims._create_claim),
        )

    def test_claim_creation_is_user_scoped(self):
        source = inspect.getsource(seller_claims._create_claim)
        self.assertIn("user_id", source)
        self.assertIn("seller_id", source)

    def test_claim_approval_updates_claim(self):
        source = inspect.getsource(seller_claims._approve_claim)
        self.assertIn("UPDATE seller_claims", source)
        self.assertIn("APPROVED", source)

    def test_claim_approval_claims_seller(self):
        source = inspect.getsource(seller_claims._approve_claim)
        self.assertIn("UPDATE sellers", source)
        self.assertIn("CLAIMED", source)

    def test_claim_rejection_updates_pending_claim(self):
        source = inspect.getsource(seller_claims._reject_claim)
        self.assertIn("UPDATE seller_claims", source)
        self.assertIn("REJECTED", source)


class SellerClaimsAuditAndNotificationTests(unittest.TestCase):
    def test_claim_creation_writes_audit(self):
        source = inspect.getsource(seller_claims.handle_claim)
        self.assertIn("_audit", source)
        self.assertIn("seller_claim_requested", source)

    def test_approval_writes_audit_inside_transaction(self):
        source = inspect.getsource(seller_claims._approve_claim)
        self.assertIn("async with db.transaction()", source)
        self.assertIn("INSERT INTO audit_log", source)
        self.assertIn("transaction.execute(", source)
        self.assertIn("seller_claim_approved", source)

    def test_rejection_writes_audit_inside_transaction(self):
        source = inspect.getsource(seller_claims._reject_claim)
        self.assertIn("async with db.transaction()", source)
        self.assertIn("INSERT INTO audit_log", source)
        self.assertIn("transaction.execute(", source)
        self.assertIn("seller_claim_rejected", source)

    def test_approval_notification_is_inside_transaction(self):
        source = inspect.getsource(seller_claims._approve_claim)
        self.assertIn("async with db.transaction()", source)
        self.assertIn("INSERT INTO notifications", source)
        self.assertIn("updated_at = ?", source)

    def test_rejection_notification_is_inside_transaction(self):
        source = inspect.getsource(seller_claims._reject_claim)
        self.assertIn("async with db.transaction()", source)
        self.assertIn("INSERT INTO notifications", source)
        self.assertIn("updated_at = ?", source)

    def test_decision_handler_does_not_repeat_post_transaction_writes(self):
        source = inspect.getsource(
            seller_claims.handle_seller_claim_decision
        )
        self.assertNotIn("_audit(", source)
        self.assertNotIn("_notify_user(", source)

    def test_notification_helper_uses_notifications_table(self):
        source = inspect.getsource(seller_claims._notify_user)
        self.assertIn("INSERT INTO notifications", source)


if __name__ == "__main__":
    unittest.main()