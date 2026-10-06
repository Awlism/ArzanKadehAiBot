# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker message/state dispatch tests.

Covers:
- user lookup
- worker state table initialization
- persistent state loading
- active state dispatch
- unknown state handling
- invalid Telegram user handling
- admin env requirements
- state serialization and validation
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
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


HANDLER_CALLS: list[dict[str, Any]] = []


def _make_handler(
    name: str,
):
    async def handler(
        *args,
        **kwargs,
    ):
        HANDLER_CALLS.append(
            {
                "name": name,
                "args": args,
                "kwargs": kwargs,
            }
        )

        return name

    return handler


def _install_worker_dependencies() -> None:
    module_specs = {
        "worker.admin": [
            "handle_admin_user_search_message",
        ],
        "worker.admin_ads": [
            "handle_admin_ad_message",
        ],
        "worker.product_management": [
            "handle_product_message",
        ],
        "worker.publicads": [
            "handle_public_ad_message",
        ],
        "worker.report": [
            "handle_report_text",
        ],
        "worker.review": [
            "handle_review_text",
        ],
        "worker.search": [
            "handle_search_message",
        ],
        "worker.seller_registration": [
            "handle_register_seller_message",
        ],
        "worker.shop": [
            "handle_shop_edit_message",
        ],
        "worker.support": [
            "handle_support_text",
        ],
        "worker.telegram": [
            "TelegramClient",
        ],
    }

    for module_name, names in module_specs.items():
        module = types.ModuleType(
            module_name
        )

        for name in names:
            if name == "TelegramClient":

                class FakeTelegramClient:
                    pass

                setattr(
                    module,
                    name,
                    FakeTelegramClient,
                )
            else:
                setattr(
                    module,
                    name,
                    _make_handler(name),
                )

        _install_module(
            module_name,
            module,
        )


class FakeBackend:
    """
    Minimal backend used by messages.py.
    """

    def __init__(self):
        self.fetchone_calls: list[
            tuple[str, Any]
        ] = []

        self.execute_calls: list[
            tuple[str, Any]
        ] = []

        self.user_row: dict[str, Any] | None = {
            "id": 100,
        }

        self.state_row: dict[str, Any] | None = {
            "state": "search",
            "data": "{\"query\":\"کفش\"}",
            "updated_at": "2026-10-06T20:00:00+00:00",
        }

    async def fetchone(
        self,
        query,
        params=None,
    ):
        self.fetchone_calls.append(
            (
                query,
                params,
            )
        )

        if "FROM users" in query:
            return self.user_row

        if "FROM worker_states" in query:
            return self.state_row

        return None

    async def execute(
        self,
        query,
        params=None,
    ):
        self.execute_calls.append(
            (
                query,
                params,
            )
        )

        return None


class FakeBackendProxy:
    """
    Proxy object matching the backend imported by messages.py.
    """

    def __init__(
        self,
        backend,
    ):
        self.backend = backend

    async def fetchone(
        self,
        query,
        params=None,
    ):
        return await self.backend.fetchone(
            query,
            params,
        )

    async def execute(
        self,
        query,
        params=None,
    ):
        return await self.backend.execute(
            query,
            params,
        )


def _install_state_module(
    backend,
):
    state_module = types.ModuleType(
        "worker.state"
    )

    async def ensure_state_table(
        db,
    ):
        HANDLER_CALLS.append(
            {
                "name": "ensure_state_table",
                "args": (
                    db,
                ),
                "kwargs": {},
            }
        )

    async def get_state(
        db,
        user_id,
    ):
        row = await db.fetchone(
            """
            SELECT
                state,
                data,
                updated_at
            FROM worker_states
            WHERE user_id = ?
            LIMIT 1;
            """,
            (user_id,),
        )

        if row is None:
            return None

        return {
            "state": str(
                row["state"]
            ),
            "data": json.loads(
                row["data"]
            ),
            "updated_at": str(
                row["updated_at"]
            ),
        }

    state_module.ensure_state_table = (
        ensure_state_table
    )

    state_module.get_state = (
        get_state
    )

    _install_module(
        "worker.state",
        state_module,
    )


def _install_backend_module(
    backend,
):
    backend_module = types.ModuleType(
        "worker_backend.backend"
    )

    backend_module.backend = (
        FakeBackendProxy(
            backend
        )
    )

    _install_module(
        "worker_backend.backend",
        backend_module,
    )

    package = types.ModuleType(
        "worker_backend"
    )
    package.__path__ = [
        str(
            SRC_ROOT / "worker_backend"
        )
    ]

    _install_module(
        "worker_backend",
        package,
    )


def _load_messages_module(
    backend,
):
    _install_worker_dependencies()
    _install_backend_module(
        backend
    )
    _install_state_module(
        backend
    )

    spec = importlib.util.spec_from_file_location(
        "worker.messages",
        SRC_ROOT / "worker" / "messages.py",
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            "Unable to load worker/messages.py"
        )

    module = importlib.util.module_from_spec(
        spec
    )

    _install_module(
        "worker.messages",
        module,
    )

    spec.loader.exec_module(
        module
    )

    return module


def run(coro):
    """
    Run an async coroutine in a dedicated event loop.
    """

    loop = asyncio.new_event_loop()

    try:
        return loop.run_until_complete(
            coro
        )
    finally:
        loop.close()


class FakeTelegram:
    pass


class MessagesStateDispatchTests(
    unittest.TestCase
):
    def setUp(self):
        HANDLER_CALLS.clear()

        self.backend = FakeBackend()

        self.messages = _load_messages_module(
            self.backend
        )

        self.telegram = FakeTelegram()

    def _message(
        self,
        telegram_id=123,
        text="سلام",
    ):
        return {
            "from": {
                "id": telegram_id,
            },
            "chat": {
                "id": telegram_id,
            },
            "text": text,
        }

    def test_valid_user_loads_state_and_dispatches_search(self):
        result = run(
            self.messages.handle_message(
                self._message(),
                self.telegram,
            )
        )

        self.assertEqual(
            result,
            "handle_search_message",
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
            "handle_search_message",
            names,
        )

        self.assertEqual(
            self.backend.fetchone_calls[0][1],
            (123,),
        )

    def test_missing_user_is_ignored(self):
        self.backend.user_row = None

        result = run(
            self.messages.handle_message(
                self._message(),
                self.telegram,
            )
        )

        self.assertIsNone(
            result
        )

        names = [
            item["name"]
            for item in HANDLER_CALLS
        ]

        self.assertNotIn(
            "ensure_state_table",
            names,
        )

    def test_missing_state_is_ignored(self):
        self.backend.state_row = None

        result = run(
            self.messages.handle_message(
                self._message(),
                self.telegram,
            )
        )

        self.assertIsNone(
            result
        )

        names = [
            item["name"]
            for item in HANDLER_CALLS
        ]

        self.assertIn(
            "ensure_state_table",
            names,
        )

    def test_missing_from_user_is_ignored(self):
        result = run(
            self.messages.handle_message(
                {
                    "text": "سلام",
                },
                self.telegram,
            )
        )

        self.assertIsNone(
            result
        )

        self.assertEqual(
            self.backend.fetchone_calls,
            [],
        )

    def test_missing_telegram_id_is_ignored(self):
        result = run(
            self.messages.handle_message(
                {
                    "from": {},
                    "text": "سلام",
                },
                self.telegram,
            )
        )

        self.assertIsNone(
            result
        )

        self.assertEqual(
            self.backend.fetchone_calls,
            [],
        )

    def test_invalid_telegram_id_is_ignored(self):
        result = run(
            self.messages.handle_message(
                self._message(
                    telegram_id="abc"
                ),
                self.telegram,
            )
        )

        self.assertIsNone(
            result
        )

        self.assertEqual(
            self.backend.fetchone_calls,
            [],
        )

    def test_zero_telegram_id_is_ignored(self):
        result = run(
            self.messages.handle_message(
                self._message(
                    telegram_id=0
                ),
                self.telegram,
            )
        )

        self.assertIsNone(
            result
        )

        self.assertEqual(
            self.backend.fetchone_calls,
            [],
        )

    def test_review_state_dispatches_review_text(self):
        self.backend.state_row = {
            "state": "review:waiting_text",
            "data": "{}",
            "updated_at": "2026-10-06T20:00:00+00:00",
        }

        result = run(
            self.messages.handle_message(
                self._message(
                    text="عالی بود"
                ),
                self.telegram,
            )
        )

        self.assertEqual(
            result,
            "handle_review_text",
        )

    def test_report_state_dispatches_report_text(self):
        self.backend.state_row = {
            "state": "report:waiting_description",
            "data": "{}",
            "updated_at": "2026-10-06T20:00:00+00:00",
        }

        result = run(
            self.messages.handle_message(
                self._message(
                    text="توضیحات گزارش"
                ),
                self.telegram,
            )
        )

        self.assertEqual(
            result,
            "handle_report_text",
        )

    def test_seller_registration_state_dispatches(self):
        self.backend.state_row = {
            "state": "seller_registration",
            "data": "{}",
            "updated_at": "2026-10-06T20:00:00+00:00",
        }

        result = run(
            self.messages.handle_message(
                self._message(),
                self.telegram,
            )
        )

        self.assertEqual(
            result,
            "handle_register_seller_message",
        )

    def test_product_management_state_dispatches(self):
        self.backend.state_row = {
            "state": "product_management",
            "data": "{}",
            "updated_at": "2026-10-06T20:00:00+00:00",
        }

        result = run(
            self.messages.handle_message(
                self._message(),
                self.telegram,
            )
        )

        self.assertEqual(
            result,
            "handle_product_message",
        )

    def test_shop_edit_state_dispatches(self):
        self.backend.state_row = {
            "state": "shop_edit",
            "data": "{}",
            "updated_at": "2026-10-06T20:00:00+00:00",
        }

        result = run(
            self.messages.handle_message(
                self._message(),
                self.telegram,
            )
        )

        self.assertEqual(
            result,
            "handle_shop_edit_message",
        )

    def test_support_state_dispatches(self):
        self.backend.state_row = {
            "state": "support",
            "data": "{}",
            "updated_at": "2026-10-06T20:00:00+00:00",
        }

        result = run(
            self.messages.handle_message(
                self._message(),
                self.telegram,
            )
        )

        self.assertEqual(
            result,
            "handle_support_text",
        )

    def test_public_ad_state_dispatches(self):
        self.backend.state_row = {
            "state": "public_ad",
            "data": "{}",
            "updated_at": "2026-10-06T20:00:00+00:00",
        }

        result = run(
            self.messages.handle_message(
                self._message(),
                self.telegram,
            )
        )

        self.assertEqual(
            result,
            "handle_public_ad_message",
        )

    def test_admin_user_search_requires_env(self):
        self.backend.state_row = {
            "state": "admin:user_search",
            "data": "{}",
            "updated_at": "2026-10-06T20:00:00+00:00",
        }

        result = run(
            self.messages.handle_message(
                self._message(),
                self.telegram,
                env=None,
            )
        )

        self.assertIsNone(
            result
        )

    def test_admin_user_search_dispatches_with_env(self):
        self.backend.state_row = {
            "state": "admin:user_search",
            "data": "{}",
            "updated_at": "2026-10-06T20:00:00+00:00",
        }

        env = object()

        result = run(
            self.messages.handle_message(
                self._message(),
                self.telegram,
                env=env,
            )
        )

        self.assertEqual(
            result,
            "handle_admin_user_search_message",
        )

    def test_admin_ad_setting_requires_env(self):
        self.backend.state_row = {
            "state": "admin_ad_setting",
            "data": "{}",
            "updated_at": "2026-10-06T20:00:00+00:00",
        }

        result = run(
            self.messages.handle_message(
                self._message(),
                self.telegram,
                env=None,
            )
        )

        self.assertIsNone(
            result
        )

    def test_admin_ad_setting_dispatches_with_env(self):
        self.backend.state_row = {
            "state": "admin_ad_setting",
            "data": "{}",
            "updated_at": "2026-10-06T20:00:00+00:00",
        }

        env = object()

        result = run(
            self.messages.handle_message(
                self._message(),
                self.telegram,
                env=env,
            )
        )

        self.assertEqual(
            result,
            "handle_admin_ad_message",
        )

    def test_unknown_state_is_ignored(self):
        self.backend.state_row = {
            "state": "some_unknown_state",
            "data": "{}",
            "updated_at": "2026-10-06T20:00:00+00:00",
        }

        result = run(
            self.messages.handle_message(
                self._message(),
                self.telegram,
            )
        )

        self.assertIsNone(
            result
        )

        names = [
            item["name"]
            for item in HANDLER_CALLS
        ]

        self.assertNotIn(
            "handle_search_message",
            names,
        )


class WorkerStateBehaviorTests(
    unittest.TestCase
):
    def setUp(self):
        self.backend = FakeBackend()

        state_module = types.ModuleType(
            "worker.state"
        )

        spec = importlib.util.spec_from_file_location(
            "worker.state_real",
            SRC_ROOT / "worker" / "state.py",
        )

        if (
            spec is None
            or spec.loader is None
        ):
            raise RuntimeError(
                "Unable to load worker/state.py"
            )

        module = importlib.util.module_from_spec(
            spec
        )

        spec.loader.exec_module(
            module
        )

        self.state = module

        _install_module(
            "worker.state",
            state_module,
        )

    def test_ensure_state_table_executes_create_statement(self):
        run(
            self.state.ensure_state_table(
                self.backend
            )
        )

        self.assertEqual(
            len(
                self.backend.execute_calls
            ),
            1,
        )

        query = (
            self.backend.execute_calls[0][0]
        )

        self.assertIn(
            "CREATE TABLE IF NOT EXISTS worker_states",
            query,
        )

    def test_set_state_rejects_invalid_user_id(self):
        with self.assertRaises(
            ValueError
        ):
            run(
                self.state.set_state(
                    self.backend,
                    0,
                    "search",
                )
            )

    def test_set_state_rejects_empty_state(self):
        with self.assertRaises(
            ValueError
        ):
            run(
                self.state.set_state(
                    self.backend,
                    100,
                    "   ",
                )
            )

    def test_set_state_rejects_non_dict_data(self):
        with self.assertRaises(
            TypeError
        ):
            run(
                self.state.set_state(
                    self.backend,
                    100,
                    "search",
                    data=["invalid"],
                )
            )

    def test_set_state_serializes_dict_as_json(self):
        run(
            self.state.set_state(
                self.backend,
                100,
                "search",
                {
                    "query": "کفش",
                    "page": 2,
                },
            )
        )

        self.assertEqual(
            len(
                self.backend.execute_calls
            ),
            1,
        )

        query, params = (
            self.backend.execute_calls[0]
        )

        self.assertIn(
            "INSERT INTO worker_states",
            query,
        )

        self.assertEqual(
            params[0],
            100,
        )

        self.assertEqual(
            params[1],
            "search",
        )

        decoded = json.loads(
            params[2]
        )

        self.assertEqual(
            decoded,
            {
                "query": "کفش",
                "page": 2,
            },
        )

    def test_get_state_deserializes_json(self):
        result = run(
            self.state.get_state(
                self.backend,
                100,
            )
        )

        self.assertEqual(
            result["state"],
            "search",
        )

        self.assertEqual(
            result["data"],
            {
                "query": "کفش",
            },
        )

        self.assertEqual(
            result["updated_at"],
            "2026-10-06T20:00:00+00:00",
        )

    def test_get_state_returns_none_when_missing(self):
        self.backend.state_row = None

        result = run(
            self.state.get_state(
                self.backend,
                100,
            )
        )

        self.assertIsNone(
            result
        )

    def test_clear_state_executes_delete(self):
        run(
            self.state.clear_state(
                self.backend,
                100,
            )
        )

        self.assertEqual(
            len(
                self.backend.execute_calls
            ),
            1,
        )

        query, params = (
            self.backend.execute_calls[0]
        )

        self.assertIn(
            "DELETE FROM worker_states",
            query,
        )

        self.assertEqual(
            params,
            (100,),
        )

    def test_clear_state_rejects_invalid_user_id(self):
        with self.assertRaises(
            ValueError
        ):
            run(
                self.state.clear_state(
                    self.backend,
                    -1,
                )
            )


if __name__ == "__main__":
    unittest.main()