# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Behavioral tests for shared Worker admin authorization helpers.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from worker.admin_auth import (  # noqa: E402
    get_admin_chat_id,
    is_admin_user,
)


class WorkerAdminAuthTests(unittest.TestCase):
    def test_configured_admin_user_is_authorized(self):
        env = SimpleNamespace(
            ADMIN_USER_ID="123456",
            ADMIN_CHAT_ID="654321",
        )

        self.assertTrue(
            is_admin_user(env, 123456)
        )

    def test_non_admin_user_is_rejected(self):
        env = SimpleNamespace(
            ADMIN_USER_ID="123456",
        )

        self.assertFalse(
            is_admin_user(env, 654321)
        )

    def test_admin_user_id_takes_precedence(self):
        env = {
            "ADMIN_USER_ID": "123456",
            "ADMIN_CHAT_ID": "654321",
        }

        self.assertFalse(
            is_admin_user(env, 654321)
        )

        self.assertTrue(
            is_admin_user(env, 123456)
        )

    def test_legacy_admin_chat_id_fallback(self):
        env = {
            "ADMIN_CHAT_ID": "123456",
        }

        self.assertTrue(
            is_admin_user(env, 123456)
        )

    def test_missing_admin_configuration_denies_access(self):
        self.assertFalse(
            is_admin_user({}, 123456)
        )

        self.assertFalse(
            is_admin_user(None, 123456)
        )

    def test_invalid_configured_admin_id_denies_access(self):
        env = {
            "ADMIN_USER_ID": "not-a-number",
            "ADMIN_CHAT_ID": "123456",
        }

        self.assertFalse(
            is_admin_user(env, 123456)
        )

    def test_blank_admin_user_id_uses_legacy_fallback(self):
        env = {
            "ADMIN_USER_ID": "   ",
            "ADMIN_CHAT_ID": "123456",
        }

        self.assertTrue(
            is_admin_user(env, 123456)
        )

    def test_invalid_telegram_user_ids_are_rejected(self):
        env = {
            "ADMIN_USER_ID": "123456",
        }

        for user_id in (
            None,
            "",
            "invalid",
            0,
            -123456,
            True,
        ):
            with self.subTest(user_id=user_id):
                self.assertFalse(
                    is_admin_user(env, user_id)
                )

    def test_negative_group_chat_id_is_valid_destination(self):
        env = {
            "ADMIN_CHAT_ID": "-1001234567890",
        }

        self.assertEqual(
            get_admin_chat_id(env),
            -1001234567890,
        )

    def test_positive_personal_chat_id_is_valid_destination(self):
        env = {
            "ADMIN_CHAT_ID": "123456",
        }

        self.assertEqual(
            get_admin_chat_id(env),
            123456,
        )

    def test_zero_and_invalid_chat_ids_are_rejected(self):
        for value in (
            None,
            "",
            "   ",
            "invalid",
            "0",
            0,
            True,
        ):
            with self.subTest(value=value):
                self.assertIsNone(
                    get_admin_chat_id(
                        {"ADMIN_CHAT_ID": value}
                    )
                )

    def test_group_chat_id_does_not_authorize_admin(self):
        env = {
            "ADMIN_CHAT_ID": "-1001234567890",
        }

        self.assertFalse(
            is_admin_user(
                env,
                1001234567890,
            )
        )


if __name__ == "__main__":
    unittest.main()