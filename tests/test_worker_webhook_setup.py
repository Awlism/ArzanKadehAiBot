# -*- coding: utf-8 -*-
"""
ArzanKadeh AI - Telegram webhook setup tests.
"""

from __future__ import annotations

import asyncio
import sys
import unittest

from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from worker import webhook_setup


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeEnv:
    def __init__(
        self,
        *,
        token="test-token",
        secret="test_secret_123456",
    ):
        self.BOT_TOKEN = token
        self.TELEGRAM_WEBHOOK_SECRET = secret


class FakeDatabase:
    def __init__(self):
        self.row = {
            "status": "pending",
            "claim_token": None,
            "lease_expires_at": None,
            "configured_at": None,
        }

    async def execute(self, query, params=None):
        normalized = " ".join(
            query.lower().split()
        )
        params = params or ()

        if normalized.startswith(
            "insert into worker_webhook_setup"
        ):
            token = params[0]
            lease_seconds = int(params[1])

            if (
                self.row["status"] == "pending"
                or self.row["lease_expires_at"] is None
                or self.row["lease_expires_at"] <= 1000
            ):
                self.row.update({
                    "status": "processing",
                    "claim_token": token,
                    "lease_expires_at": 1000 + lease_seconds,
                    "configured_at": None,
                })

            return None

        if normalized.startswith(
            "update worker_webhook_setup"
        ):
            token = params[-1]

            if (
                self.row["status"] != "processing"
                or self.row["claim_token"] != token
            ):
                return None

            if "status = 'configured'" in normalized:
                configured_at = params[0]

                self.row.update({
                    "status": "configured",
                    "claim_token": None,
                    "lease_expires_at": None,
                    "configured_at": configured_at,
                })

            elif "status = 'pending'" in normalized:
                self.row.update({
                    "status": "pending",
                    "claim_token": None,
                    "lease_expires_at": None,
                    "configured_at": None,
                })

            return None

        raise AssertionError(
            f"Unexpected SQL: {query}"
        )

    async def fetchone(self, query, params=None):
        normalized = " ".join(
            query.lower().split()
        )

        if normalized.startswith(
            "select status from worker_webhook_setup"
        ):
            return {
                "status": self.row["status"],
            }

        if normalized.startswith(
            "select status, claim_token from worker_webhook_setup"
        ):
            return {
                "status": self.row["status"],
                "claim_token": self.row["claim_token"],
            }

        if normalized.startswith(
            "select status, configured_at from worker_webhook_setup"
        ):
            return {
                "status": self.row["status"],
                "configured_at": self.row["configured_at"],
            }

        raise AssertionError(
            f"Unexpected SELECT: {query}"
        )


class FakeTelegramClient:
    calls = []
    should_fail = False

    def __init__(self, env):
        self.env = env

    @staticmethod
    def _read_token(env):
        token = getattr(env, "BOT_TOKEN", None)

        if not token:
            raise RuntimeError(
                "BOT_TOKEN is not configured."
            )

        return token

    async def call(self, method, payload=None):
        self.calls.append({
            "method": method,
            "payload": payload,
        })

        if self.should_fail:
            raise RuntimeError(
                "Telegram API request failed."
            )

        return True


class WebhookSetupTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        self.env = FakeEnv()

        FakeTelegramClient.calls = []
        FakeTelegramClient.should_fail = False

        self.telegram_patch = patch.object(
            webhook_setup,
            "TelegramClient",
            FakeTelegramClient,
        )
        self.telegram_patch.start()

    def tearDown(self):
        self.telegram_patch.stop()

    def test_successful_setup(self):
        result = run(
            webhook_setup.ensure_telegram_webhook(
                self.db,
                self.env,
            )
        )

        self.assertTrue(result)
        self.assertEqual(
            self.db.row["status"],
            "configured",
        )
        self.assertIsNotNone(
            self.db.row["configured_at"],
        )

        self.assertEqual(
            len(FakeTelegramClient.calls),
            1,
        )

        call = FakeTelegramClient.calls[0]

        self.assertEqual(
            call["method"],
            "setWebhook",
        )
        self.assertEqual(
            call["payload"]["url"],
            webhook_setup.WEBHOOK_URL,
        )
        self.assertEqual(
            call["payload"]["allowed_updates"],
            ["message", "callback_query"],
        )

    def test_configured_setup_is_skipped(self):
        self.db.row["status"] = "configured"

        env = FakeEnv(
            token=None,
            secret=None,
        )

        result = run(
            webhook_setup.ensure_telegram_webhook(
                self.db,
                env,
            )
        )

        self.assertFalse(result)
        self.assertEqual(
            len(FakeTelegramClient.calls),
            0,
        )

    def test_active_lease_prevents_second_claim(self):
        self.db.row.update({
            "status": "processing",
            "claim_token": "another-owner",
            "lease_expires_at": 2000,
        })

        result = run(
            webhook_setup.ensure_telegram_webhook(
                self.db,
                self.env,
            )
        )

        self.assertFalse(result)
        self.assertEqual(
            self.db.row["claim_token"],
            "another-owner",
        )
        self.assertEqual(
            len(FakeTelegramClient.calls),
            0,
        )

    def test_missing_secret_is_rejected(self):
        env = FakeEnv(secret=None)

        with self.assertRaises(ValueError):
            run(
                webhook_setup.ensure_telegram_webhook(
                    self.db,
                    env,
                )
            )

        self.assertEqual(
            self.db.row["status"],
            "pending",
        )
        self.assertEqual(
            len(FakeTelegramClient.calls),
            0,
        )

    def test_invalid_secret_is_rejected(self):
        env = FakeEnv(
            secret="invalid secret with spaces",
        )

        with self.assertRaises(ValueError):
            run(
                webhook_setup.ensure_telegram_webhook(
                    self.db,
                    env,
                )
            )

        self.assertEqual(
            self.db.row["status"],
            "pending",
        )

    def test_api_failure_releases_claim(self):
        FakeTelegramClient.should_fail = True

        with self.assertRaisesRegex(
            RuntimeError,
            "Telegram API request failed",
        ):
            run(
                webhook_setup.ensure_telegram_webhook(
                    self.db,
                    self.env,
                )
            )

        self.assertEqual(
            self.db.row["status"],
            "pending",
        )
        self.assertIsNone(
            self.db.row["claim_token"],
        )
        self.assertIsNone(
            self.db.row["lease_expires_at"],
        )

    def test_missing_token_is_rejected(self):
        env = FakeEnv(token=None)

        with self.assertRaisesRegex(
            RuntimeError,
            "BOT_TOKEN is not configured",
        ):
            run(
                webhook_setup.ensure_telegram_webhook(
                    self.db,
                    env,
                )
            )

        self.assertEqual(
            self.db.row["status"],
            "pending",
        )
        self.assertEqual(
            len(FakeTelegramClient.calls),
            0,
        )


if __name__ == "__main__":
    unittest.main()