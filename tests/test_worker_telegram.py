# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker Telegram API client tests.

Covers:
- BOT_TOKEN loading
- missing/empty token handling
- Telegram API URL construction
- JSON payload serialization
- sendMessage
- editMessageText
- answerCallbackQuery
- successful Telegram responses
- Telegram API errors
- invalid JSON responses
- invalid Telegram response shapes

These tests never contact the real Telegram API.
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
TELEGRAM_FILE = (
    SRC_ROOT
    / "worker"
    / "telegram.py"
)


class FakeResponse:
    def __init__(
        self,
        payload: Any,
        *,
        json_error: Exception | None = None,
    ):
        self.payload = payload
        self.json_error = json_error

    async def json(self):
        if self.json_error is not None:
            raise self.json_error

        return self.payload


class FakeFetch:
    def __init__(
        self,
        response: FakeResponse,
    ):
        self.response = response
        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []

    async def __call__(
        self,
        url,
        options,
    ):
        self.calls.append(
            (
                url,
                options,
            )
        )

        return self.response


class FakeEnv:
    def __init__(
        self,
        token: Any = "123456:TEST_TOKEN",
    ):
        if token is not None:
            self.BOT_TOKEN = token


def _load_telegram_module(
    fake_fetch: FakeFetch,
):
    workers_module = types.ModuleType(
        "workers"
    )

    workers_module.fetch = fake_fetch

    sys.modules["workers"] = (
        workers_module
    )

    spec = (
        importlib.util.spec_from_file_location(
            "worker.telegram_test_target",
            TELEGRAM_FILE,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            "Unable to load worker/telegram.py"
        )

    module = (
        importlib.util.module_from_spec(
            spec
        )
    )

    sys.modules[
        "worker.telegram_test_target"
    ] = module

    spec.loader.exec_module(
        module
    )

    return module


def run(coro):
    """
    Execute an async coroutine in an isolated
    event loop.
    """

    loop = asyncio.new_event_loop()

    try:
        return loop.run_until_complete(
            coro
        )
    finally:
        loop.close()


class TelegramClientTests(
    unittest.TestCase
):
    def setUp(self):
        self.fetch = FakeFetch(
            FakeResponse(
                {
                    "ok": True,
                    "result": {
                        "message_id": 100,
                    },
                }
            )
        )

        self.telegram = _load_telegram_module(
            self.fetch
        )

    def test_client_reads_bot_token_from_environment(self):
        client = self.telegram.TelegramClient(
            FakeEnv(
                "987654:ABC123"
            )
        )

        self.assertEqual(
            client._token,
            "987654:ABC123",
        )

        self.assertEqual(
            client._base_url,
            "https://api.telegram.org/bot987654:ABC123",
        )

    def test_client_strips_bot_token(self):
        client = self.telegram.TelegramClient(
            FakeEnv(
                "  987654:ABC123  "
            )
        )

        self.assertEqual(
            client._token,
            "987654:ABC123",
        )

    def test_missing_bot_token_raises(self):
        class MissingEnv:
            pass

        with self.assertRaises(
            self.telegram.TelegramAPIError
        ) as context:
            self.telegram.TelegramClient(
                MissingEnv()
            )

        self.assertEqual(
            str(context.exception),
            "BOT_TOKEN is not configured.",
        )

    def test_none_bot_token_raises(self):
        with self.assertRaises(
            self.telegram.TelegramAPIError
        ):
            self.telegram.TelegramClient(
                FakeEnv(None)
            )

    def test_empty_bot_token_raises(self):
        with self.assertRaises(
            self.telegram.TelegramAPIError
        ):
            self.telegram.TelegramClient(
                FakeEnv("   ")
            )

    def test_call_rejects_empty_method(self):
        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        with self.assertRaises(
            ValueError
        ):
            run(
                client.call("")
            )

        self.assertEqual(
            self.fetch.calls,
            [],
        )

    def test_call_builds_correct_telegram_url(self):
        client = self.telegram.TelegramClient(
            FakeEnv(
                "111:XYZ"
            )
        )

        result = run(
            client.call(
                "getMe",
                {},
            )
        )

        self.assertEqual(
            result,
            {
                "message_id": 100,
            },
        )

        self.assertEqual(
            len(
                self.fetch.calls
            ),
            1,
        )

        url, options = (
            self.fetch.calls[0]
        )

        self.assertEqual(
            url,
            "https://api.telegram.org/bot111:XYZ/getMe",
        )

        self.assertEqual(
            options["method"],
            "POST",
        )

        self.assertEqual(
            options["headers"][
                "Content-Type"
            ],
            "application/json",
        )

    def test_call_serializes_json_body(self):
        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        run(
            client.call(
                "testMethod",
                {
                    "chat_id": 123,
                    "text": "سلام",
                },
            )
        )

        _url, options = (
            self.fetch.calls[0]
        )

        self.assertEqual(
            options["body"],
            '{"chat_id":123,"text":"سلام"}',
        )

    def test_call_returns_result_on_success(self):
        self.fetch.response = (
            FakeResponse(
                {
                    "ok": True,
                    "result": {
                        "id": 42,
                        "is_bot": True,
                    },
                }
            )
        )

        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        result = run(
            client.call(
                "getMe"
            )
        )

        self.assertEqual(
            result,
            {
                "id": 42,
                "is_bot": True,
            },
        )

    def test_call_raises_api_error_when_ok_is_false(self):
        self.fetch.response = (
            FakeResponse(
                {
                    "ok": False,
                    "error_code": 400,
                    "description": (
                        "Bad Request: test error"
                    ),
                    "parameters": {
                        "retry_after": 3,
                    },
                }
            )
        )

        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        with self.assertRaises(
            self.telegram.TelegramAPIError
        ) as context:
            run(
                client.call(
                    "sendMessage"
                )
            )

        error = context.exception

        self.assertEqual(
            str(error),
            "Bad Request: test error",
        )

        self.assertEqual(
            error.method,
            "sendMessage",
        )

        self.assertEqual(
            error.error_code,
            400,
        )

        self.assertEqual(
            error.parameters,
            {
                "retry_after": 3,
            },
        )

    def test_call_rejects_non_object_response(self):
        self.fetch.response = (
            FakeResponse(
                [
                    "invalid"
                ]
            )
        )

        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        with self.assertRaises(
            self.telegram.TelegramAPIError
        ) as context:
            run(
                client.call(
                    "getMe"
                )
            )

        self.assertEqual(
            str(context.exception),
            "Telegram API returned an invalid response.",
        )

    def test_call_rejects_invalid_json(self):
        self.fetch.response = (
            FakeResponse(
                None,
                json_error=ValueError(
                    "invalid json"
                ),
            )
        )

        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        with self.assertRaises(
            self.telegram.TelegramAPIError
        ) as context:
            run(
                client.call(
                    "getMe"
                )
            )

        self.assertEqual(
            str(context.exception),
            "Telegram API returned invalid JSON.",
        )

    def test_send_message_builds_expected_payload(self):
        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        run(
            client.send_message(
                123456,
                "سلام ارزانکده",
            )
        )

        url, options = (
            self.fetch.calls[0]
        )

        self.assertTrue(
            url.endswith(
                "/sendMessage"
            )
        )

        self.assertEqual(
            options["body"],
            '{"chat_id":123456,"text":"سلام ارزانکده"}',
        )

    def test_send_message_includes_optional_parameters(self):
        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        run(
            client.send_message(
                123456,
                "سلام",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "تست",
                                "callback_data": "test",
                            }
                        ]
                    ]
                },
                parse_mode="HTML",
            )
        )

        _url, options = (
            self.fetch.calls[0]
        )

        body = options["body"]

        self.assertIn(
            '"chat_id":123456',
            body,
        )

        self.assertIn(
            '"text":"سلام"',
            body,
        )

        self.assertIn(
            '"parse_mode":"HTML"',
            body,
        )

        self.assertIn(
            '"callback_data":"test"',
            body,
        )

    def test_edit_message_text_builds_expected_payload(self):
        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        run(
            client.edit_message_text(
                123456,
                789,
                "متن جدید",
            )
        )

        url, options = (
            self.fetch.calls[0]
        )

        self.assertTrue(
            url.endswith(
                "/editMessageText"
            )
        )

        self.assertEqual(
            options["body"],
            '{"chat_id":123456,"message_id":789,"text":"متن جدید"}',
        )

    def test_edit_message_text_includes_optional_parameters(self):
        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        run(
            client.edit_message_text(
                123456,
                789,
                "متن",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "بازگشت",
                                "callback_data": "back",
                            }
                        ]
                    ]
                },
                parse_mode="HTML",
            )
        )

        _url, options = (
            self.fetch.calls[0]
        )

        body = options["body"]

        self.assertIn(
            '"message_id":789',
            body,
        )

        self.assertIn(
            '"parse_mode":"HTML"',
            body,
        )

        self.assertIn(
            '"callback_data":"back"',
            body,
        )

    def test_answer_callback_query_builds_expected_payload(self):
        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        run(
            client.answer_callback_query(
                "callback-123"
            )
        )

        url, options = (
            self.fetch.calls[0]
        )

        self.assertTrue(
            url.endswith(
                "/answerCallbackQuery"
            )
        )

        self.assertEqual(
            options["body"],
            '{"callback_query_id":"callback-123","show_alert":false}',
        )

    def test_answer_callback_query_supports_text_and_alert(self):
        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        run(
            client.answer_callback_query(
                "callback-456",
                text="انجام شد",
                show_alert=True,
            )
        )

        _url, options = (
            self.fetch.calls[0]
        )

        body = options["body"]

        self.assertIn(
            '"callback_query_id":"callback-456"',
            body,
        )

        self.assertIn(
            '"text":"انجام شد"',
            body,
        )

        self.assertIn(
            '"show_alert":true',
            body,
        )

    def test_telegram_api_error_without_parameters_uses_empty_dict(self):
        self.fetch.response = (
            FakeResponse(
                {
                    "ok": False,
                    "error_code": 403,
                    "description": "Forbidden",
                }
            )
        )

        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        with self.assertRaises(
            self.telegram.TelegramAPIError
        ) as context:
            run(
                client.call(
                    "sendMessage"
                )
            )

        self.assertEqual(
            context.exception.parameters,
            {},
        )

    def test_telegram_api_error_without_description_uses_default_message(self):
        self.fetch.response = (
            FakeResponse(
                {
                    "ok": False,
                    "error_code": 500,
                }
            )
        )

        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        with self.assertRaises(
            self.telegram.TelegramAPIError
        ) as context:
            run(
                client.call(
                    "testMethod"
                )
            )

        self.assertEqual(
            str(context.exception),
            "Telegram API request failed.",
        )

    def test_send_message_returns_telegram_result(self):
        self.fetch.response = (
            FakeResponse(
                {
                    "ok": True,
                    "result": {
                        "message_id": 555,
                        "chat": {
                            "id": 123,
                        },
                    },
                }
            )
        )

        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        result = run(
            client.send_message(
                123,
                "تست",
            )
        )

        self.assertEqual(
            result["message_id"],
            555,
        )

    def test_edit_message_text_returns_telegram_result(self):
        self.fetch.response = (
            FakeResponse(
                {
                    "ok": True,
                    "result": True,
                }
            )
        )

        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        result = run(
            client.edit_message_text(
                123,
                456,
                "تست",
            )
        )

        self.assertTrue(
            result
        )

    def test_answer_callback_query_returns_telegram_result(self):
        self.fetch.response = (
            FakeResponse(
                {
                    "ok": True,
                    "result": True,
                }
            )
        )

        client = self.telegram.TelegramClient(
            FakeEnv()
        )

        result = run(
            client.answer_callback_query(
                "abc"
            )
        )

        self.assertTrue(
            result
        )


if __name__ == "__main__":
    unittest.main()