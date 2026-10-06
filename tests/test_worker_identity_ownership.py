# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker identity, ownership, and user-scoped data contract tests.

These tests validate the SQL contracts used by the migrated Worker
handlers without contacting Telegram or the real D1 database.

Covered:
- Telegram user -> internal user mapping
- product favorites scoped by user_id
- seller favorites scoped by user_id
- owned seller lookup
- referral ownership lookup
- referral self-referral protection
- duplicate referral protection
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"


class DatabaseResult:
    def __init__(
        self,
        rowcount: int = 0,
        lastrowid: int | None = None,
    ):
        self.rowcount = rowcount
        self.lastrowid = lastrowid


class FakeDB:
    """
    Minimal async database double.

    It records SQL and provides deterministic rows for the
    identity/ownership helpers under test.
    """

    def __init__(self):
        self.fetchone_results: list[
            dict[str, Any] | None
        ] = []

        self.fetchall_results: list[
            list[dict[str, Any]]
        ] = []

        self.execute_calls: list[
            tuple[str, Any]
        ] = []

        self.fetchone_calls: list[
            tuple[str, Any]
        ] = []

        self.fetchall_calls: list[
            tuple[str, Any]
        ] = []

        self.execute_results: list[
            DatabaseResult
        ] = []

    async def fetchone(
        self,
        sql: str,
        params=None,
    ):
        self.fetchone_calls.append(
            (
                sql,
                params,
            )
        )

        if self.fetchone_results:
            return self.fetchone_results.pop(
                0
            )

        return None

    async def fetchall(
        self,
        sql: str,
        params=None,
    ):
        self.fetchall_calls.append(
            (
                sql,
                params,
            )
        )

        if self.fetchall_results:
            return self.fetchall_results.pop(
                0
            )

        return []

    async def execute(
        self,
        sql: str,
        params=None,
    ):
        self.execute_calls.append(
            (
                sql,
                params,
            )
        )

        if self.execute_results:
            return self.execute_results.pop(
                0
            )

        return DatabaseResult(
            rowcount=1
        )


def _load_module(
    name: str,
    path: Path,
    extra_modules: dict[str, types.ModuleType]
):
    for module_name, module in (
        extra_modules.items()
    ):
        sys.modules[module_name] = module

    spec = (
        importlib.util.spec_from_file_location(
            name,
            path,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            f"Unable to load {path}"
        )

    module = (
        importlib.util.module_from_spec(
            spec
        )
    )

    sys.modules[name] = module

    spec.loader.exec_module(
        module
    )

    return module


def run(coro):
    loop = asyncio.new_event_loop()

    try:
        return loop.run_until_complete(
            coro
        )
    finally:
        loop.close()


class IdentityOwnershipTests(
    unittest.TestCase
):
    def setUp(self):
        self.db = FakeDB()

        telegram_module = types.ModuleType(
            "worker.telegram"
        )

        class FakeTelegramClient:
            pass

        telegram_module.TelegramClient = (
            FakeTelegramClient
        )

        backend_module = types.ModuleType(
            "worker_backend.backend"
        )

        backend_module.backend = self.db

        self.products = _load_module(
            "worker.products_identity_test",
            SRC_ROOT
            / "worker"
            / "products.py",
            {
                "worker.telegram": telegram_module,
                "worker_backend.backend": (
                    backend_module
                ),
            },
        )

        self.seller = _load_module(
            "worker.seller_identity_test",
            SRC_ROOT
            / "worker"
            / "seller.py",
            {
                "worker.telegram": telegram_module,
                "worker_backend.backend": (
                    backend_module
                ),
            },
        )

        self.favorites = _load_module(
            "worker.favorites_identity_test",
            SRC_ROOT
            / "worker"
            / "favorites.py",
            {
                "worker.telegram": telegram_module,
                "worker_backend.backend": (
                    backend_module
                ),
            },
        )

        self.referrals = _load_module(
            "worker.referrals_identity_test",
            SRC_ROOT
            / "worker"
            / "referrals.py",
            {
                "worker.telegram": telegram_module,
                "worker_backend.backend": (
                    backend_module
                ),
            },
        )

    def test_product_favorite_lookup_is_scoped_to_user(self):
        result = run(
            self.products._is_favorite(
                self.db,
                10,
                20,
            )
        )

        self.assertFalse(
            result
        )

        self.assertEqual(
            len(
                self.db.fetchone_calls
            ),
            1,
        )

        sql, params = (
            self.db.fetchone_calls[0]
        )

        normalized = " ".join(
            sql.split()
        ).lower()

        self.assertIn(
            "from favorites",
            normalized,
        )

        self.assertIn(
            "where user_id = ?",
            normalized,
        )

        self.assertIn(
            "and product_id = ?",
            normalized,
        )

        self.assertEqual(
            params,
            (
                10,
                20,
            ),
        )

    def test_product_favorite_lookup_does_not_use_product_only(self):
        self.db.fetchone_results = [
            {
                "id": 999,
            }
        ]

        result = run(
            self.products._is_favorite(
                self.db,
                10,
                20,
            )
        )

        self.assertTrue(
            result
        )

        sql, params = (
            self.db.fetchone_calls[0]
        )

        normalized = " ".join(
            sql.split()
        ).lower()

        self.assertIn(
            "user_id = ?",
            normalized,
        )

        self.assertEqual(
            params,
            (
                10,
                20,
            ),
        )

    def test_seller_favorite_lookup_is_scoped_to_user(self):
        result = run(
            self.seller._is_seller_favorite(
                self.db,
                10,
                30,
            )
        )

        self.assertFalse(
            result
        )

        sql, params = (
            self.db.fetchone_calls[0]
        )

        normalized = " ".join(
            sql.split()
        ).lower()

        self.assertIn(
            "from seller_favorites",
            normalized,
        )

        self.assertIn(
            "where user_id = ?",
            normalized,
        )

        self.assertIn(
            "and seller_id = ?",
            normalized,
        )

        self.assertEqual(
            params,
            (
                10,
                30,
            ),
        )

    def test_seller_favorite_lookup_returns_true_for_existing_row(self):
        self.db.fetchone_results = [
            {
                "1": 1,
            }
        ]

        result = run(
            self.seller._is_seller_favorite(
                self.db,
                10,
                30,
            )
        )

        self.assertTrue(
            result
        )

    def test_owned_seller_requires_user_ownership(self):
        self.db.fetchone_results = [
            {
                "id": 50,
                "owner_user_id": 10,
                "created_by_user_id": 99,
            }
        ]

        result = run(
            self.referrals._get_owned_seller(
                self.db,
                10,
                50,
            )
        )

        self.assertIsNotNone(
            result
        )

        sql, params = (
            self.db.fetchone_calls[0]
        )

        normalized = " ".join(
            sql.split()
        ).lower()

        self.assertIn(
            "where id = ?",
            normalized,
        )

        self.assertIn(
            "owner_user_id = ?",
            normalized,
        )

        self.assertIn(
            "created_by_user_id = ?",
            normalized,
        )

        self.assertEqual(
            params,
            (
                50,
                10,
                10,
            ),
        )

    def test_owned_seller_query_supports_owner_or_creator(self):
        self.db.fetchone_results = [
            {
                "id": 50,
                "owner_user_id": 99,
                "created_by_user_id": 10,
            }
        ]

        result = run(
            self.referrals._get_owned_seller(
                self.db,
                10,
                50,
            )
        )

        self.assertIsNotNone(
            result
        )

        sql, _params = (
            self.db.fetchone_calls[0]
        )

        normalized = " ".join(
            sql.split()
        ).lower()

        self.assertIn(
            "owner_user_id = ?",
            normalized,
        )

        self.assertIn(
            "created_by_user_id = ?",
            normalized,
        )

        self.assertIn(
            "or",
            normalized,
        )

    def test_owned_seller_returns_none_for_unowned_seller(self):
        self.db.fetchone_results = [
            None
        ]

        result = run(
            self.referrals._get_owned_seller(
                self.db,
                10,
                50,
            )
        )

        self.assertIsNone(
            result
        )

        _sql, params = (
            self.db.fetchone_calls[0]
        )

        self.assertEqual(
            params,
            (
                50,
                10,
                10,
            ),
        )

    def test_get_sellers_owned_by_user_uses_both_owner_and_creator(self):
        self.db.fetchall_results = [
            [
                {
                    "id": 1,
                    "owner_user_id": 10,
                    "created_by_user_id": 10,
                }
            ]
        ]

        result = run(
            self.referrals.get_sellers_owned_by_user(
                self.db,
                10,
            )
        )

        self.assertEqual(
            len(result),
            1,
        )

        sql, params = (
            self.db.fetchall_calls[0]
        )

        normalized = " ".join(
            sql.split()
        ).lower()

        self.assertIn(
            "from sellers",
            normalized,
        )

        self.assertIn(
            "owner_user_id = ?",
            normalized,
        )

        self.assertIn(
            "created_by_user_id = ?",
            normalized,
        )

        self.assertEqual(
            params,
            (
                10,
                10,
            ),
        )

    def test_referral_rejects_missing_seller(self):
        self.db.fetchone_results = [
            None
        ]

        result = run(
            self.referrals.record_referral_if_new(
                self.db,
                999,
                100,
            )
        )

        self.assertFalse(
            result
        )

        self.assertEqual(
            self.db.execute_calls,
            [],
        )

    def test_referral_rejects_self_referral_by_owner(self):
        self.db.fetchone_results = [
            {
                "id": 50,
                "owner_user_id": 100,
                "created_by_user_id": 200,
            }
        ]

        result = run(
            self.referrals.record_referral_if_new(
                self.db,
                50,
                100,
            )
        )

        self.assertFalse(
            result
        )

        self.assertEqual(
            self.db.execute_calls,
            [],
        )

    def test_referral_rejects_self_referral_by_creator(self):
        self.db.fetchone_results = [
            {
                "id": 50,
                "owner_user_id": 100,
                "created_by_user_id": 200,
            }
        ]

        result = run(
            self.referrals.record_referral_if_new(
                self.db,
                50,
                200,
            )
        )

        self.assertFalse(
            result
        )

        self.assertEqual(
            self.db.execute_calls,
            [],
        )

    def test_referral_rejects_user_already_referred(self):
        self.db.fetchone_results = [
            {
                "id": 50,
                "owner_user_id": 999,
                "created_by_user_id": 998,
            },
            {
                "id": 700,
            },
        ]

        result = run(
            self.referrals.record_referral_if_new(
                self.db,
                50,
                100,
            )
        )

        self.assertFalse(
            result
        )

        self.assertEqual(
            self.db.execute_calls,
            [],
        )

    def test_referral_inserts_new_referral(self):
        self.db.fetchone_results = [
            {
                "id": 50,
                "owner_user_id": 999,
                "created_by_user_id": 998,
            },
            None,
        ]

        result = run(
            self.referrals.record_referral_if_new(
                self.db,
                50,
                100,
            )
        )

        self.assertTrue(
            result
        )

        self.assertEqual(
            len(
                self.db.execute_calls
            ),
            1,
        )

        sql, params = (
            self.db.execute_calls[0]
        )

        normalized = " ".join(
            sql.split()
        ).lower()

        self.assertIn(
            "insert into referrals",
            normalized,
        )

        self.assertIn(
            "seller_id",
            normalized,
        )

        self.assertIn(
            "referred_user_id",
            normalized,
        )

        self.assertEqual(
            params[0],
            50,
        )

        self.assertEqual(
            params[1],
            100,
        )

    def test_referral_duplicate_constraint_is_safe(self):
        self.db.fetchone_results = [
            {
                "id": 50,
                "owner_user_id": 999,
                "created_by_user_id": 998,
            },
            None,
        ]

        class DuplicateDB(FakeDB):
            async def execute(
                self,
                sql,
                params=None,
            ):
                self.execute_calls.append(
                    (
                        sql,
                        params,
                    )
                )

                raise Exception(
                    "UNIQUE constraint failed: referrals.referred_user_id"
                )

        db = DuplicateDB()

        db.fetchone_results = [
            {
                "id": 50,
                "owner_user_id": 999,
                "created_by_user_id": 998,
            },
            None,
        ]

        result = run(
            self.referrals.record_referral_if_new(
                db,
                50,
                100,
            )
        )

        self.assertFalse(
            result
        )

    def test_product_favorite_remove_sql_is_user_scoped(self):
        self.db.execute_results = [
            DatabaseResult(
                rowcount=1
            )
        ]

        callback = {
            "data": "unfavorite:20",
            "from": {
                "id": 10,
            },
            "id": "callback-1",
            "message": {
                "chat": {
                    "id": 500,
                },
                "message_id": 600,
            },
        }

        class FakeTelegram:
            def __init__(self):
                self.calls = []

            async def answer_callback_query(
                self,
                *args,
                **kwargs,
            ):
                self.calls.append(
                    (
                        "answer",
                        args,
                        kwargs,
                    )
                )

            async def edit_message_text(
                self,
                *args,
                **kwargs,
            ):
                self.calls.append(
                    (
                        "edit",
                        args,
                        kwargs,
                    )
                )

        telegram = FakeTelegram()

        self.db.fetchone_results = [
            {
                "id": 10,
                "telegram_id": 10,
            },
            {
                "id": 20,
                "seller_id": 30,
                "seller_name": "Test",
                "seller_status": "ACTIVE",
                "city_name": "Tehran",
            },
        ]

        run(
            self.products.handle_favorite_remove(
                self.db,
                telegram,
                callback,
            )
        )

        delete_calls = [
            call
            for call in self.db.execute_calls
            if "delete from favorites"
            in " ".join(
                call[0].split()
            ).lower()
        ]

        self.assertEqual(
            len(delete_calls),
            1,
        )

        _sql, params = (
            delete_calls[0]
        )

        self.assertEqual(
            params,
            (
                10,
                20,
            ),
        )


if __name__ == "__main__":
    unittest.main()