# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker entry integration tests.

Covers:
- Worker GET routing
- Worker POST routing
- webhook validation
- D1 backend initialization
- worker_states initialization
- message routing
- callback routing
- unknown update handling
- HTTP method handling
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


def _install_module(
    name: str,
    module: types.ModuleType,
) -> None:
    sys.modules[name] = module


def _install_worker_sdk_stubs() -> None:
    workers = types.ModuleType("workers")

    class FakeResponse:
        def __init__(
            self,
            body: str,
            status: int = 200,
        ):
            self.body = body
            self.status = status

    class FakeWorkerEntrypoint:
        pass

    workers.Response = FakeResponse
    workers.WorkerEntrypoint = FakeWorkerEntrypoint

    _install_module(
        "workers",
        workers,
    )


def _install_backend_stubs() -> None:
    backend_module = types.ModuleType(
        "worker_backend.backend"
    )

    class FakeBackendProxy:
        def __init__(self):
            self.backend = None
            self.connected = False

        def set_backend(
            self,
            backend,
        ):
            self.backend = backend

        async def connect(self):
            self.connected = True
            if self.backend is not None:
                await self.backend.connect()

        async def fetchall(
            self,
            query,
            params=None,
        ):
            if self.backend is None:
                return []

            return await self.backend.fetchall(
                query,
                params,
            )

    backend_module.backend = FakeBackendProxy()

    _install_module(
        "worker_backend.backend",
        backend_module,
    )

    d1_module = types.ModuleType(
        "worker_backend.d1_backend"
    )

    class FakeD1Backend:
        instances = []

        def __init__(
            self,
            database,
        ):
            self.database = database
            self.connected = False
            self.fetchall_calls = []
            self.__class__.instances.append(self)

        async def connect(self):
            self.connected = True

        async def fetchall(
            self,
            query,
            params=None,
        ):
            self.fetchall_calls.append(
                (
                    query,
                    params,
                )
            )

            return [
                {
                    "name": "users",
                },
                {
                    "name": "products",
                },
            ]

    d1_module.D1Backend = FakeD1Backend

    _install_module(
        "worker_backend.d1_backend",
        d1_module,
    )


def _install_worker_module_stubs() -> None:
    """
    Install minimal handler modules so entry.py can be loaded directly.

    The tests exercise entry routing rather than individual business
    handlers. Each stub records the callback/message path it receives.
    """

    handler_calls = []

    def make_handler(
        name: str,
    ):
        async def handler(
            *args,
            **kwargs,
        ):
            handler_calls.append(
                {
                    "name": name,
                    "args": args,
                    "kwargs": kwargs,
                }
            )

            return name

        return handler

    module_specs = {
        "worker.start": [
            "handle_start",
        ],
        "worker.messages": [
            "handle_message",
        ],
        "worker.categories": [
            "handle_category",
        ],
        "worker.products": [
            "handle_product_detail",
            "handle_favorite_add",
            "handle_favorite_remove",
        ],
        "worker.compare": [
            "handle_compare",
            "handle_compare_drop",
            "handle_compare_list",
            "handle_compare_reset",
            "handle_compare_start",
        ],
        "worker.seller": [
            "handle_sellers_list",
            "handle_seller_detail",
            "handle_seller_favorite_add",
            "handle_seller_favorite_remove",
        ],
        "worker.review": [
            "handle_review_start",
            "handle_review_rating",
        ],
        "worker.report": [
            "handle_report_reason",
            "handle_report_skip",
            "handle_report_start",
        ],
        "worker.hot": [
            "handle_hot",
        ],
        "worker.discovery": [
            "handle_near_me",
            "handle_new_today",
            "handle_picks",
            "handle_top_sellers",
        ],
        "worker.favorites": [
            "handle_favorites_list",
        ],
        "worker.seller_registration": [
            "handle_register_seller_start",
            "handle_register_city",
            "handle_register_skip",
        ],
        "worker.search": [
            "handle_search_start",
            "handle_search_page",
        ],
        "worker.publicads": [
            "handle_public_ads",
            "handle_public_ad_models",
            "handle_public_ad_start",
            "handle_public_ad_kind",
            "handle_public_ad_skip",
        ],
        "worker.account": [
            "handle_account",
            "handle_set_mode",
        ],
        "worker.support": [
            "handle_support_start",
            "handle_support_topic",
        ],
        "worker.notifications": [
            "handle_notifications",
            "handle_notification_read",
        ],
        "worker.profile": [
            "handle_my_profile",
            "handle_set_city",
            "handle_pick_city",
        ],
        "worker.requests": [
            "handle_my_requests",
        ],
        "worker.store_status": [
            "handle_store_status",
            "handle_store_status_picked",
        ],
        "worker.product_stats": [
            "handle_my_stats",
            "handle_stats_home_picked",
            "handle_stats_product",
        ],
        "worker.referrals": [
            "handle_referral_list",
            "handle_referral_stats",
        ],
        "worker.product_management": [
            "handle_my_products",
            "handle_product_list",
            "handle_product_add_start",
            "handle_product_add_skip",
            "handle_product_edit_menu",
            "handle_product_field_start",
            "handle_product_stock_menu",
            "handle_product_stock_set",
            "handle_product_delete",
            "handle_product_delete_confirmed",
        ],
        "worker.shop": [
            "handle_my_shop",
            "handle_shop_view",
            "handle_shop_edit_menu",
            "handle_shop_edit_start",
            "handle_shop_city_start",
            "handle_shop_city_pick",
            "handle_shop_toggle_active",
        ],
        "worker.ads": [
            "handle_ads",
            "handle_ad_type_detail",
            "handle_ad_confirm",
        ],
        "worker.seller_claims": [
            "handle_claim",
            "handle_seller_claims_admin",
            "handle_seller_claim_detail",
            "handle_seller_claim_decision",
        ],
        "worker.admin": [
            "handle_admin_home",
            "handle_admin_users_menu",
            "handle_admin_user_search_start",
            "handle_admin_user_list",
            "handle_admin_user_view",
            "handle_admin_user_search_message",
        ],
        "worker.admin_ads": [
            "handle_ads_admin",
            "handle_admin_ad_view",
            "handle_admin_ad_price_start",
            "handle_admin_ad_duration_start",
            "handle_admin_ad_placement_start",
            "handle_admin_ad_decision",
            "handle_admin_ad_message",
        ],
    }

    for module_name, functions in module_specs.items():
        module = types.ModuleType(
            module_name
        )

        for function_name in functions:
            setattr(
                module,
                function_name,
                make_handler(
                    function_name
                ),
            )

        _install_module(
            module_name,
            module,
        )

    state_module = types.ModuleType(
        "worker.state"
    )

    async def ensure_state_table(
        backend,
    ):
        handler_calls.append(
            {
                "name": "ensure_state_table",
                "args": (
                    backend,
                ),
                "kwargs": {},
            }
        )

    state_module.ensure_state_table = (
        ensure_state_table
    )

    _install_module(
        "worker.state",
        state_module,
    )

    telegram_module = types.ModuleType(
        "worker.telegram"
    )

    class FakeTelegramClient:
        def __init__(
            self,
            env,
        ):
            self.env = env

        async def answer_callback_query(
            self,
            callback_id,
        ):
            handler_calls.append(
                {
                    "name": "answer_callback_query",
                    "args": (
                        callback_id,
                    ),
                    "kwargs": {},
                }
            )

        async def edit_message_text(
            self,
            *args,
            **kwargs,
        ):
            handler_calls.append(
                {
                    "name": "edit_message_text",
                    "args": args,
                    "kwargs": kwargs,
                }
            )

        async def send_message(
            self,
            *args,
            **kwargs,
        ):
            handler_calls.append(
                {
                    "name": "send_message",
                    "args": args,
                    "kwargs": kwargs,
                }
            )

    telegram_module.TelegramClient = (
        FakeTelegramClient
    )

    _install_module(
        "worker.telegram",
        telegram_module,
    )

    webhook_spec = importlib.util.spec_from_file_location(
        "worker.webhook",
        SRC_ROOT / "worker" / "webhook.py",
    )

    if (
        webhook_spec is None
        or webhook_spec.loader is None
    ):
        raise RuntimeError(
            "Unable to load worker.webhook"
        )

    webhook_module = (
        importlib.util.module_from_spec(
            webhook_spec
        )
    )

    _install_module(
        "worker.webhook",
        webhook_module,
    )

    webhook_spec.loader.exec_module(
        webhook_module
    )

    router_spec = importlib.util.spec_from_file_location(
        "worker.router",
        SRC_ROOT / "worker" / "router.py",
    )

    if (
        router_spec is None
        or router_spec.loader is None
    ):
        raise RuntimeError(
            "Unable to load worker.router"
        )

    router_module = (
        importlib.util.module_from_spec(
            router_spec
        )
    )

    _install_module(
        "worker.router",
        router_module,
    )

    router_spec.loader.exec_module(
        router_module
    )

    return handler_calls


_install_worker_sdk_stubs()
_install_backend_stubs()
HANDLER_CALLS = _install_worker_module_stubs()


entry_spec = importlib.util.spec_from_file_location(
    "entry",
    SRC_ROOT / "entry.py",
)

if (
    entry_spec is None
    or entry_spec.loader is None
):
    raise RuntimeError(
        "Unable to load src/entry.py"
    )

entry = importlib.util.module_from_spec(
    entry_spec
)

sys.modules["entry"] = entry

entry_spec.loader.exec_module(
    entry
)


def run(coro):
    """
    Run an async test coroutine.
    """

    loop = asyncio.new_event_loop()

    try:
        return loop.run_until_complete(
            coro
        )
    finally:
        loop.close()


class FakeHeaders:
    def __init__(
        self,
        values=None,
    ):
        self.values = dict(
            values or {}
        )

    def get(
        self,
        name,
    ):
        return self.values.get(
            name
        )


class FakeRequest:
    def __init__(
        self,
        method: str,
        payload: Any = None,
        headers=None,
    ):
        self.method = method
        self.payload = payload
        self.headers = FakeHeaders(
            headers
        )

    async def json(self):
        return self.payload


class FakeEnv:
    def __init__(
        self,
        secret=None,
    ):
        self.DB = object()

        if secret is not None:
            self.TELEGRAM_WEBHOOK_SECRET = (
                secret
            )


class WorkerEntryIntegrationTests(
    unittest.TestCase
):
    def setUp(self):
        HANDLER_CALLS.clear()

        entry.backend.backend = None
        entry.backend.connected = False

        entry.D1Backend.instances.clear()

        self.worker = entry.Default()

        self.worker.env = FakeEnv()

    def test_get_returns_d1_health_response(self):
        response = run(
            self.worker.fetch(
                FakeRequest(
                    "GET"
                )
            )
        )

        self.assertEqual(
            response.status,
            200,
        )

        self.assertIn(
            "ArzanKadeh Worker + D1Backend OK",
            response.body,
        )

        self.assertIn(
            "Tables: 2",
            response.body,
        )

        self.assertTrue(
            entry.backend.connected
        )

        self.assertEqual(
            len(
                entry.D1Backend.instances
            ),
            1,
        )

        self.assertTrue(
            entry.D1Backend.instances[0].connected
        )

    def test_post_message_initializes_state_table_and_dispatches_message(self):
        response = run(
            self.worker.fetch(
                FakeRequest(
                    "POST",
                    {
                        "update_id": 1,
                        "message": {
                            "message_id": 10,
                            "from": {
                                "id": 123,
                            },
                            "chat": {
                                "id": 123,
                            },
                            "text": "سلام",
                        },
                    },
                )
            )
        )

        self.assertEqual(
            response.status,
            200,
        )

        self.assertIn(
            "Update type: message",
            response.body,
        )

        names = [
            item["name"]
            for item in HANDLER_CALLS
        ]

        self.assertIn(
            "ensure_state_table",
            names,
        )

        self.assertIn(
            "handle_message",
            names,
        )

    def test_post_start_command_uses_start_handler(self):
        response = run(
            self.worker.fetch(
                FakeRequest(
                    "POST",
                    {
                        "update_id": 2,
                        "message": {
                            "message_id": 11,
                            "from": {
                                "id": 123,
                            },
                            "chat": {
                                "id": 123,
                            },
                            "text": "/start",
                        },
                    },
                )
            )
        )

        self.assertEqual(
            response.status,
            200,
        )

        names = [
            item["name"]
            for item in HANDLER_CALLS
        ]

        self.assertIn(
            "handle_start",
            names,
        )

        self.assertNotIn(
            "handle_message",
            names,
        )

    def test_post_callback_dispatches_callback_handler(self):
        response = run(
            self.worker.fetch(
                FakeRequest(
                    "POST",
                    {
                        "update_id": 3,
                        "callback_query": {
                            "id": "callback-1",
                            "from": {
                                "id": 123,
                            },
                            "data": "hot",
                        },
                    },
                )
            )
        )

        self.assertEqual(
            response.status,
            200,
        )

        self.assertIn(
            "Update type: callback_query",
            response.body,
        )

        names = [
            item["name"]
            for item in HANDLER_CALLS
        ]

        self.assertIn(
            "ensure_state_table",
            names,
        )

        self.assertIn(
            "handle_hot",
            names,
        )

    def test_callback_routes_product_detail(self):
        response = run(
            self.worker.fetch(
                FakeRequest(
                    "POST",
                    {
                        "update_id": 4,
                        "callback_query": {
                            "id": "callback-2",
                            "from": {
                                "id": 123,
                            },
                            "data": "product:42",
                        },
                    },
                )
            )
        )

        self.assertEqual(
            response.status,
            200,
        )

        names = [
            item["name"]
            for item in HANDLER_CALLS
        ]

        self.assertIn(
            "handle_product_detail",
            names,
        )

    def test_callback_routes_seller_detail(self):
        response = run(
            self.worker.fetch(
                FakeRequest(
                    "POST",
                    {
                        "update_id": 5,
                        "callback_query": {
                            "id": "callback-3",
                            "from": {
                                "id": 123,
                            },
                            "data": "seller:42",
                        },
                    },
                )
            )
        )

        self.assertEqual(
            response.status,
            200,
        )

        names = [
            item["name"]
            for item in HANDLER_CALLS
        ]

        self.assertIn(
            "handle_seller_detail",
            names,
        )

    def test_wrong_webhook_secret_returns_401(self):
        self.worker.env = FakeEnv(
            secret="correct-secret"
        )

        response = run(
            self.worker.fetch(
                FakeRequest(
                    "POST",
                    {
                        "update_id": 6,
                        "message": {
                            "from": {
                                "id": 123,
                            },
                            "text": "سلام",
                        },
                    },
                    headers={
                        "X-Telegram-Bot-Api-Secret-Token":
                            "wrong-secret",
                    },
                )
            )
        )

        self.assertEqual(
            response.status,
            401,
        )

        self.assertEqual(
            response.body,
            "Unauthorized",
        )

        self.assertEqual(
            HANDLER_CALLS,
            [],
        )

    def test_correct_webhook_secret_allows_update(self):
        self.worker.env = FakeEnv(
            secret="correct-secret"
        )

        response = run(
            self.worker.fetch(
                FakeRequest(
                    "POST",
                    {
                        "update_id": 7,
                        "callback_query": {
                            "id": "callback-4",
                            "from": {
                                "id": 123,
                            },
                            "data": "hot",
                        },
                    },
                    headers={
                        "X-Telegram-Bot-Api-Secret-Token":
                            "correct-secret",
                    },
                )
            )
        )

        self.assertEqual(
            response.status,
            200,
        )

        names = [
            item["name"]
            for item in HANDLER_CALLS
        ]

        self.assertIn(
            "handle_hot",
            names,
        )

    def test_invalid_json_returns_400(self):
        request = FakeRequest(
            "POST",
            payload=None,
        )

        async def invalid_json():
            raise ValueError(
                "invalid json"
            )

        request.json = invalid_json

        response = run(
            self.worker.fetch(
                request
            )
        )

        self.assertEqual(
            response.status,
            400,
        )

        self.assertEqual(
            response.body,
            "Invalid Telegram update",
        )

    def test_non_object_update_returns_400(self):
        response = run(
            self.worker.fetch(
                FakeRequest(
                    "POST",
                    [
                        "not",
                        "an",
                        "object",
                    ],
                )
            )
        )

        self.assertEqual(
            response.status,
            400,
        )

        self.assertEqual(
            response.body,
            "Invalid Telegram update",
        )

    def test_unknown_update_type_returns_200_without_handler(self):
        response = run(
            self.worker.fetch(
                FakeRequest(
                    "POST",
                    {
                        "update_id": 8,
                        "some_future_update": {},
                    },
                )
            )
        )

        self.assertEqual(
            response.status,
            200,
        )

        self.assertIn(
            "Update type: unknown",
            response.body,
        )

        names = [
            item["name"]
            for item in HANDLER_CALLS
        ]

        self.assertNotIn(
            "handle_message",
            names,
        )

        self.assertNotIn(
            "handle_hot",
            names,
        )

    def test_unsupported_method_returns_405(self):
        response = run(
            self.worker.fetch(
                FakeRequest(
                    "PUT"
                )
            )
        )

        self.assertEqual(
            response.status,
            405,
        )

        self.assertEqual(
            response.body,
            "Method Not Allowed",
        )


if __name__ == "__main__":
    unittest.main()