# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker seller-claim admin notification contract tests.

These tests verify that seller-claim notifications use the shared
admin chat destination validator and do not confuse notification
destinations with admin user authorization.
"""

from __future__ import annotations

import inspect
import unittest

from worker import seller_claims
from worker import admin_auth


class SellerClaimAdminNotificationImportTests(unittest.TestCase):
    def test_shared_admin_chat_helper_is_imported(self):
        self.assertIs(
            seller_claims.get_admin_chat_id,
            admin_auth.get_admin_chat_id,
        )

    def test_legacy_positive_only_parsing_is_not_used_for_notifications(self):
        source = inspect.getsource(seller_claims.handle_claim)

        self.assertNotIn(
            "admin_chat_id = int(configured)",
            source,
        )

        self.assertIn(
            "get_admin_chat_id(env)",
            source,
        )


class SellerClaimAdminNotificationDestinationTests(unittest.TestCase):
    def test_notification_destination_uses_shared_validator(self):
        source = inspect.getsource(seller_claims.handle_claim)

        self.assertIn(
            "admin_chat_id = get_admin_chat_id(env)",
            source,
        )

    def test_missing_or_invalid_destination_is_checked_with_none(self):
        source = inspect.getsource(seller_claims.handle_claim)

        self.assertIn(
            "if admin_chat_id is not None:",
            source,
        )

    def test_notification_does_not_require_positive_destination(self):
        source = inspect.getsource(seller_claims.handle_claim)

        self.assertNotIn(
            "if admin_chat_id > 0:",
            source,
        )

        self.assertNotIn(
            "if admin_chat_id:",
            source,
        )

    def test_notification_uses_telegram_send_message(self):
        source = inspect.getsource(seller_claims.handle_claim)

        self.assertIn(
            "await telegram.send_message(",
            source,
        )

    def test_notification_failure_does_not_undo_claim(self):
        source = inspect.getsource(seller_claims.handle_claim)

        self.assertIn(
            "except Exception:",
            source,
        )

        self.assertIn(
            "# Notification failure must not undo the claim.",
            source,
        )


class SellerClaimAdminNotificationHelperTests(unittest.TestCase):
    def test_positive_personal_chat_id_is_accepted(self):
        self.assertEqual(
            admin_auth.get_admin_chat_id(
                {"ADMIN_CHAT_ID": "123456"}
            ),
            123456,
        )

    def test_negative_group_chat_id_is_accepted(self):
        self.assertEqual(
            admin_auth.get_admin_chat_id(
                {"ADMIN_CHAT_ID": "-1001234567890"}
            ),
            -1001234567890,
        )

    def test_zero_chat_id_is_rejected(self):
        self.assertIsNone(
            admin_auth.get_admin_chat_id(
                {"ADMIN_CHAT_ID": "0"}
            )
        )

    def test_blank_chat_id_is_rejected(self):
        self.assertIsNone(
            admin_auth.get_admin_chat_id(
                {"ADMIN_CHAT_ID": "   "}
            )
        )

    def test_invalid_chat_id_is_rejected(self):
        self.assertIsNone(
            admin_auth.get_admin_chat_id(
                {"ADMIN_CHAT_ID": "not-a-number"}
            )
        )

    def test_boolean_chat_id_is_rejected(self):
        self.assertIsNone(
            admin_auth.get_admin_chat_id(
                {"ADMIN_CHAT_ID": True}
            )
        )


if __name__ == "__main__":
    unittest.main()