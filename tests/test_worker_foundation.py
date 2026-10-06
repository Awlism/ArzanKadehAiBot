# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker foundation tests.

Covers the Cloudflare Worker-side foundation without requiring:
- aiogram
- aiosqlite
- SQLite
- Telegram network access
- BOT_TOKEN

Tested areas:
- webhook payload parsing
- webhook update type detection
- webhook secret validation
- WorkerRouter message dispatch
- WorkerRouter callback dispatch
- persistent Worker state serialization
- persistent Worker state replacement
- persistent Worker state clearing
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


def _load_module(
    name: str,
    relative_path: str,
):
    """
    Load one Worker module directly from src/ without importing
    the complete Worker application.
    """

    path = SRC_ROOT / relative_path

    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load Worker module: {relative_path}"
        )

    module = importlib.util.module_from_spec(
        spec
    )

    sys.modules[name] = module
    spec.loader.exec_module(module)

    return module


webhook = _load_module(
    "worker_test_webhook",
    "worker/webhook.py",
)

router_module = _load_module(
    "worker_test_router",
    "worker/router.py",
)

state = _load_module(
    "worker_test_state",
    "worker/state.py",
)


def run(coro):
    """
    Run an async test coroutine without relying on pytest.
    """

    loop = asyncio.new_event_loop()

    try:
        return loop.run_until_complete(
            coro
        )
    finally:
        loop.close()


class FakeHeaders:
    """
    Minimal request-header adapter.
    """

    def __init__(
        self,
        values: dict[str, str] | None = None,
    ):
        self._values = {
            str(key).lower(): value
            for key, value in (
                values or {}
            ).items()
        }

    def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        return self._values.get(
            key.lower(),
            default,
        )


class FakeRequest:
    """
    Minimal Worker request adapter.
    """

    def __init__(
        self,
        payload: Any,
        headers: dict[str, str] | None = None,
    ):
        self._payload = payload
        self.headers = FakeHeaders(
            headers
        )

    async def json(self):
        if isinstance(
            self._payload,
            Exception,
        ):
            raise self._payload

        return self._payload


class FakeEnv:
    """
    Minimal Worker environment adapter.
    """

    def __init__(
        self,
        *,
        secret: str | None = None,
    ):
        if secret is not None:
            self.TELEGRAM_WEBHOOK_SECRET = secret


class FakeDatabase:
    """
    Small async backend used only for Worker state tests.

    It implements the subset of the DatabaseBackend contract required
    by state.py.
    """

    def __init__(self):
        self.tables: set[str] = set()
        self.rows: dict[int, dict[str, Any]] = {}

    async def execute(
        self,
        query: str,
        params: Any = None,
    ):
        normalized = " ".join(
            query.lower().split()
        )

        if normalized.startswith(
            "create table if not exists worker_states"
        ):
            self.tables.add(
                "worker_states"
            )
            return None

        if normalized.startswith(
            "insert into worker_states"
        ):
            user_id = int(
                params[0]
            )
            state_name = str(
                params[1]
            )
            data = str(
                params[2]
            )
            updated_at = str(
                params[3]
            )

            self.rows[user_id] = {
                "state": state_name,
                "data": data,
                "updated_at": updated_at,
            }

            return None

        if normalized.startswith(
            "delete from worker_states"
        ):
            user_id = int(
                params[0]
            )

            self.rows.pop(
                user_id,
                None,
            )

            return None

        raise AssertionError(
            f"Unexpected state SQL: {query}"
        )

    async def fetchone(
        self,
        query: str,
        params: Any = None,
    ):
        normalized = " ".join(
            query.lower().split()
        )

        if normalized.startswith(
            "select state, data, updated_at from worker_states"
        ):
            user_id = int(
                params[0]
            )

            return self.rows.get(
                user_id
            )

        raise AssertionError(
            f"Unexpected state SELECT: {query}"
        )


class WebhookFoundationTests(
    unittest.TestCase
):
    """
    Tests for webhook parsing and validation.
    """

    def test_valid_json_object_is_parsed(self):
        request = FakeRequest(
            {
                "update_id": 100,
                "message": {
                    "text": "/start",
                },
            }
        )

        result = run(
            webhook.parse_webhook_update(
                request
            )
        )

        self.assertEqual(
            result["update_id"],
            100,
        )

    def test_invalid_json_raises_webhook_error(self):
        request = FakeRequest(
            ValueError(
                "invalid json"
            )
        )

        with self.assertRaises(
            webhook.InvalidWebhookPayloadError
        ):
            run(
                webhook.parse_webhook_update(
                    request
                )
            )

    def test_non_object_json_is_rejected(self):
        request = FakeRequest(
            [
                "not",
                "an",
                "object",
            ]
        )

        with self.assertRaises(
            webhook.InvalidWebhookPayloadError
        ):
            run(
                webhook.parse_webhook_update(
                    request
                )
            )

    def test_message_update_is_detected(self):
        update = {
            "update_id": 1,
            "message": {},
        }

        self.assertEqual(
            webhook.detect_update_type(
                update
            ),
            "message",
        )

    def test_callback_update_is_detected(self):
        update = {
            "update_id": 2,
            "callback_query": {},
        }

        self.assertEqual(
            webhook.detect_update_type(
                update
            ),
            "callback_query",
        )

    def test_unknown_update_is_detected(self):
        update = {
            "update_id": 3,
            "future_update": {},
        }

        self.assertEqual(
            webhook.detect_update_type(
                update
            ),
            "unknown",
        )

    def test_missing_secret_does_not_block_request(self):
        request = FakeRequest(
            {},
        )

        env = FakeEnv()

        result = webhook.verify_webhook_secret(
            request,
            env,
        )

        self.assertIsNone(
            result
        )

    def test_matching_secret_is_accepted(self):
        request = FakeRequest(
            {},
            {
                "X-Telegram-Bot-Api-Secret-Token":
                    "test-secret",
            },
        )

        env = FakeEnv(
            secret="test-secret"
        )

        result = webhook.verify_webhook_secret(
            request,
            env,
        )

        self.assertIsNone(
            result
        )

    def test_wrong_secret_is_rejected(self):
        request = FakeRequest(
            {},
            {
                "X-Telegram-Bot-Api-Secret-Token":
                    "wrong-secret",
            },
        )

        env = FakeEnv(
            secret="expected-secret"
        )

        with self.assertRaises(
            webhook.UnauthorizedWebhookError
        ):
            webhook.verify_webhook_secret(
                request,
                env,
            )


class WorkerRouterTests(
    unittest.TestCase
):
    """
    Tests for per-request WorkerRouter dispatch.
    """

    def test_message_handler_receives_message(self):
        received = []

        async def message_handler(
            message
        ):
            received.append(
                message
            )
            return "message-ok"

        router = router_module.WorkerRouter()

        router.set_message_handler(
            message_handler
        )

        message = {
            "message_id": 10,
            "text": "سلام",
        }

        result = run(
            router.dispatch(
                {
                    "message": message,
                }
            )
        )

        self.assertEqual(
            result,
            "message-ok",
        )

        self.assertEqual(
            received,
            [message],
        )

    def test_callback_handler_receives_callback(self):
        received = []

        async def callback_handler(
            callback
        ):
            received.append(
                callback
            )
            return "callback-ok"

        router = router_module.WorkerRouter()

        router.set_callback_handler(
            callback_handler
        )

        callback = {
            "id": "callback-1",
            "data": "favorites:0",
        }

        result = run(
            router.dispatch(
                {
                    "callback_query": callback,
                }
            )
        )

        self.assertEqual(
            result,
            "callback-ok",
        )

        self.assertEqual(
            received,
            [callback],
        )

    def test_message_is_preferred_when_both_types_exist(self):
        received = []

        async def message_handler(
            message
        ):
            received.append(
                "message"
            )
            return "message"

        async def callback_handler(
            callback
        ):
            received.append(
                "callback"
            )
            return "callback"

        router = router_module.WorkerRouter()

        router.set_message_handler(
            message_handler
        )

        router.set_callback_handler(
            callback_handler
        )

        result = run(
            router.dispatch(
                {
                    "message": {},
                    "callback_query": {},
                }
            )
        )

        self.assertEqual(
            result,
            "message",
        )

        self.assertEqual(
            received,
            ["message"],
        )

    def test_unknown_update_is_ignored(self):
        router = router_module.WorkerRouter()

        result = run(
            router.dispatch(
                {
                    "poll": {},
                }
            )
        )

        self.assertIsNone(
            result
        )

    def test_missing_handlers_are_safe(self):
        router = router_module.WorkerRouter()

        self.assertIsNone(
            run(
                router.dispatch(
                    {
                        "message": {},
                    }
                )
            )
        )

        self.assertIsNone(
            run(
                router.dispatch(
                    {
                        "callback_query": {},
                    }
                )
            )
        )


class WorkerStateTests(
    unittest.TestCase
):
    """
    Tests for persistent Worker state semantics.
    """

    def setUp(self):
        self.db = FakeDatabase()

        run(
            state.ensure_state_table(
                self.db
            )
        )

    def test_state_table_can_be_initialized(self):
        self.assertIn(
            "worker_states",
            self.db.tables,
        )

    def test_state_can_be_created_and_read(self):
        run(
            state.set_state(
                self.db,
                10,
                "search",
                {
                    "page": 2,
                    "query": "کفش",
                },
            )
        )

        result = run(
            state.get_state(
                self.db,
                10,
            )
        )

        self.assertIsNotNone(
            result
        )

        self.assertEqual(
            result["state"],
            "search",
        )

        self.assertEqual(
            result["data"],
            {
                "page": 2,
                "query": "کفش",
            },
        )

    def test_state_is_replaced_for_same_user(self):
        run(
            state.set_state(
                self.db,
                10,
                "search",
                {
                    "page": 1,
                },
            )
        )

        run(
            state.set_state(
                self.db,
                10,
                "support",
                {
                    "topic": "seller",
                },
            )
        )

        result = run(
            state.get_state(
                self.db,
                10,
            )
        )

        self.assertEqual(
            result["state"],
            "support",
        )

        self.assertEqual(
            result["data"],
            {
                "topic": "seller",
            },
        )

    def test_state_data_is_stored_as_json(self):
        run(
            state.set_state(
                self.db,
                10,
                "search",
                {
                    "text": "کفش",
                    "page": 3,
                },
            )
        )

        raw = self.db.rows[10]["data"]

        decoded = json.loads(
            raw
        )

        self.assertEqual(
            decoded,
            {
                "text": "کفش",
                "page": 3,
            },
        )

    def test_state_can_be_cleared(self):
        run(
            state.set_state(
                self.db,
                10,
                "search",
                {
                    "page": 1,
                },
            )
        )

        run(
            state.clear_state(
                self.db,
                10,
            )
        )

        result = run(
            state.get_state(
                self.db,
                10,
            )
        )

        self.assertIsNone(
            result
        )

    def test_invalid_user_id_is_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            run(
                state.set_state(
                    self.db,
                    0,
                    "search",
                )
            )

    def test_invalid_state_name_is_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            run(
                state.set_state(
                    self.db,
                    10,
                    "",
                )
            )

    def test_non_dictionary_state_data_is_rejected(self):
        with self.assertRaises(
            TypeError
        ):
            run(
                state.set_state(
                    self.db,
                    10,
                    "search",
                    ["invalid"],
                )
            )


if __name__ == "__main__":
    unittest.main()