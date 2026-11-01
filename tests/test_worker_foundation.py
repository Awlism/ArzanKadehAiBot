# -*- coding: utf-8 -*-
"""
ArzanKadeh AI - Worker foundation tests.

Covers webhook validation, routing, persistent state, and update claims
without requiring aiogram, SQLite, network access, or BOT_TOKEN.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"


def _load_module(name: str, relative_path: str):
    path = SRC_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load Worker module: {relative_path}"
        )

    module = importlib.util.module_from_spec(spec)
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
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeHeaders:
    def __init__(self, values: dict[str, str] | None = None):
        self._values = {
            str(key).lower(): value
            for key, value in (values or {}).items()
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key.lower(), default)


class FakeRequest:
    def __init__(
        self,
        payload: Any,
        headers: dict[str, str] | None = None,
    ):
        self._payload = payload
        self.headers = FakeHeaders(headers)

    async def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeEnv:
    def __init__(self, *, secret: str | None = None):
        if secret is not None:
            self.TELEGRAM_WEBHOOK_SECRET = secret


class FakeResult:
    def __init__(self, rowcount: int = 0):
        self.rowcount = rowcount



class FakeDatabase:
    """In-memory test double for the state.py database operations."""

    def __init__(self):
        self.tables: set[str] = set()
        self.rows: dict[int, dict[str, Any]] = {}
        self.processed_updates: dict[int, dict[str, Any]] = {}
        self.clock = 1000

    async def execute(self, query: str, params: Any = None):
        normalized = " ".join(query.lower().split())
        params = params or ()

        if normalized.startswith(
            "create table if not exists worker_states"
        ):
            self.tables.add("worker_states")
            return FakeResult()

        if normalized.startswith(
            "create table if not exists processed_updates"
        ):
            self.tables.add("processed_updates")
            return FakeResult()

        if normalized.startswith("insert into worker_states"):
            user_id = int(params[0])
            self.rows[user_id] = {
                "state": str(params[1]),
                "data": str(params[2]),
                "updated_at": str(params[3]),
            }
            return FakeResult(1)

        if normalized.startswith("delete from worker_states"):
            user_id = int(params[0])
            existed = user_id in self.rows
            self.rows.pop(user_id, None)
            return FakeResult(1 if existed else 0)

        if normalized.startswith("insert into processed_updates"):
            update_id = int(params[0])
            claim_token = str(params[1])
            lease_seconds = int(params[2])

            existing = self.processed_updates.get(update_id)

            if existing is None:
                self.processed_updates[update_id] = {
                    "status": "processing",
                    "claimed_at": self.clock,
                    "processed_at": None,
                    "claim_token": claim_token,
                    "lease_expires_at": self.clock + lease_seconds,
                }
                return FakeResult(1)

            if (
                existing["status"] == "processing"
                and (
                    existing["lease_expires_at"] is None
                    or existing["lease_expires_at"] <= self.clock
                )
            ):
                existing.update({
                    "status": "processing",
                    "claimed_at": self.clock,
                    "processed_at": None,
                    "claim_token": claim_token,
                    "lease_expires_at": self.clock + lease_seconds,
                })
                return FakeResult(1)

            return FakeResult(0)

        if normalized.startswith("update processed_updates"):
            update_id = int(params[0])
            claim_token = str(params[1])
            row = self.processed_updates.get(update_id)

            if (
                row is not None
                and row["status"] == "processing"
                and row["claim_token"] == claim_token
            ):
                row["status"] = "processed"
                row["processed_at"] = self.clock
                row["lease_expires_at"] = None
                return FakeResult(1)

            return FakeResult(0)

        if normalized.startswith("delete from processed_updates"):
            update_id = int(params[0])
            claim_token = str(params[1])
            row = self.processed_updates.get(update_id)

            if (
                row is not None
                and row["status"] == "processing"
                and row["claim_token"] == claim_token
            ):
                del self.processed_updates[update_id]
                return FakeResult(1)

            return FakeResult(0)

        raise AssertionError(f"Unexpected state SQL: {query}")

    async def fetchone(self, query: str, params: Any = None):
        normalized = " ".join(query.lower().split())
        params = params or ()

        if normalized.startswith(
            "select state, data, updated_at from worker_states"
        ):
            return self.rows.get(int(params[0]))

        if normalized.startswith(
            "select status, claim_token from processed_updates"
        ):
            row = self.processed_updates.get(int(params[0]))
            if row is None:
                return None

            return {
                "status": row["status"],
                "claim_token": row["claim_token"],
            }

        raise AssertionError(f"Unexpected state SELECT: {query}")


class WebhookFoundationTests(unittest.TestCase):
    def test_valid_json_object_is_parsed(self):
        result = run(
            webhook.parse_webhook_update(
                FakeRequest({
                    "update_id": 100,
                    "message": {"text": "/start"},
                })
            )
        )
        self.assertEqual(result["update_id"], 100)

    def test_invalid_json_raises_webhook_error(self):
        with self.assertRaises(webhook.InvalidWebhookPayloadError):
            run(
                webhook.parse_webhook_update(
                    FakeRequest(ValueError("invalid json"))
                )
            )

    def test_non_object_json_is_rejected(self):
        with self.assertRaises(webhook.InvalidWebhookPayloadError):
            run(
                webhook.parse_webhook_update(
                    FakeRequest(["not", "an", "object"])
                )
            )

    def test_message_update_is_detected(self):
        self.assertEqual(
            webhook.detect_update_type({"update_id": 1, "message": {}}),
            "message",
        )

    def test_callback_update_is_detected(self):
        self.assertEqual(
            webhook.detect_update_type(
                {"update_id": 2, "callback_query": {}}
            ),
            "callback_query",
        )

    def test_unknown_update_is_detected(self):
        self.assertEqual(
            webhook.detect_update_type(
                {"update_id": 3, "future_update": {}}
            ),
            "unknown",
        )

    def test_missing_secret_is_rejected(self):
        with self.assertRaises(webhook.UnauthorizedWebhookError):
            webhook.verify_webhook_secret(
                FakeRequest({}),
                FakeEnv(),
            )

    def test_matching_secret_is_accepted(self):
        request = FakeRequest(
            {},
            {"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        self.assertIsNone(
            webhook.verify_webhook_secret(
                request,
                FakeEnv(secret="test-secret"),
            )
        )

    def test_wrong_secret_is_rejected(self):
        request = FakeRequest(
            {},
            {"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        )
        with self.assertRaises(webhook.UnauthorizedWebhookError):
            webhook.verify_webhook_secret(
                request,
                FakeEnv(secret="expected-secret"),
            )


class WorkerRouterTests(unittest.TestCase):
    def test_message_handler_receives_message(self):
        received = []

        async def handler(message):
            received.append(message)
            return "message-ok"

        router = router_module.WorkerRouter()
        router.set_message_handler(handler)

        message = {"message_id": 10, "text": "سلام"}
        result = run(router.dispatch({"message": message}))

        self.assertEqual(result, "message-ok")
        self.assertEqual(received, [message])

    def test_callback_handler_receives_callback(self):
        received = []

        async def handler(callback):
            received.append(callback)
            return "callback-ok"

        router = router_module.WorkerRouter()
        router.set_callback_handler(handler)

        callback = {"id": "callback-1", "data": "favorites:0"}
        result = run(router.dispatch({"callback_query": callback}))

        self.assertEqual(result, "callback-ok")
        self.assertEqual(received, [callback])

    def test_message_is_preferred_when_both_types_exist(self):
        received = []

        async def message_handler(message):
            received.append("message")
            return "message"

        async def callback_handler(callback):
            received.append("callback")
            return "callback"

        router = router_module.WorkerRouter()
        router.set_message_handler(message_handler)
        router.set_callback_handler(callback_handler)

        result = run(
            router.dispatch({
                "message": {},
                "callback_query": {},
            })
        )

        self.assertEqual(result, "message")
        self.assertEqual(received, ["message"])

    def test_unknown_update_is_ignored(self):
        router = router_module.WorkerRouter()
        self.assertIsNone(run(router.dispatch({"poll": {}})))

    def test_missing_handlers_are_safe(self):
        router = router_module.WorkerRouter()
        self.assertIsNone(run(router.dispatch({"message": {}})))
        self.assertIsNone(run(router.dispatch({"callback_query": {}})))


class WorkerStateTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        run(state.ensure_state_table(self.db))

    def test_state_table_can_be_initialized(self):
        self.assertIn("worker_states", self.db.tables)

    def test_state_can_be_created_and_read(self):
        run(
            state.set_state(
                self.db,
                10,
                "search",
                {"page": 2, "query": "کفش"},
            )
        )

        result = run(state.get_state(self.db, 10))

        self.assertIsNotNone(result)
        self.assertEqual(result["state"], "search")
        self.assertEqual(
            result["data"],
            {"page": 2, "query": "کفش"},
        )

    def test_state_is_replaced_for_same_user(self):
        run(state.set_state(self.db, 10, "search", {"page": 1}))
        run(
            state.set_state(
                self.db,
                10,
                "support",
                {"topic": "seller"},
            )
        )

        result = run(state.get_state(self.db, 10))
        self.assertEqual(result["state"], "support")
        self.assertEqual(result["data"], {"topic": "seller"})

    def test_state_data_is_stored_as_json(self):
        run(
            state.set_state(
                self.db,
                10,
                "search",
                {"text": "کفش", "page": 3},
            )
        )

        self.assertEqual(
            json.loads(self.db.rows[10]["data"]),
            {"text": "کفش", "page": 3},
        )

    def test_state_can_be_cleared(self):
        run(state.set_state(self.db, 10, "search", {"page": 1}))
        run(state.clear_state(self.db, 10))
        self.assertIsNone(run(state.get_state(self.db, 10)))

    def test_invalid_user_id_is_rejected(self):
        with self.assertRaises(ValueError):
            run(state.set_state(self.db, 0, "search"))

    def test_get_state_rejects_invalid_user_ids(self):
        for user_id in (0, -1, True, 1.5, "10"):
            with self.subTest(user_id=user_id):
                with self.assertRaises(ValueError):
                    run(state.get_state(self.db, user_id))

    def test_database_errors_propagate(self):
        class FailingDatabase:
            async def execute(self, query, params=None):
                raise RuntimeError("D1 execute failed")

            async def fetchone(self, query, params=None):
                raise RuntimeError("D1 fetchone failed")

        db = FailingDatabase()

        with self.assertRaisesRegex(
            RuntimeError,
            "D1 execute failed",
        ):
            run(state.set_state(db, 10, "search"))

        with self.assertRaisesRegex(
            RuntimeError,
            "D1 fetchone failed",
        ):
            run(state.get_state(db, 10))

    def test_invalid_state_name_is_rejected(self):
        with self.assertRaises(ValueError):
            run(state.set_state(self.db, 10, ""))

    def test_non_dictionary_state_data_is_rejected(self):
        with self.assertRaises(TypeError):
            run(state.set_state(self.db, 10, "search", ["invalid"]))



class ProcessedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        run(state.ensure_processed_updates_table(self.db))

    def test_processed_updates_table_can_be_initialized(self):
        self.assertIn("processed_updates", self.db.tables)

    def test_first_claim_returns_token_and_duplicate_claim_fails(self):
        token = run(state.claim_update(self.db, 100))

        self.assertIsInstance(token, str)
        self.assertTrue(token)

        self.assertIsNone(
            run(state.claim_update(self.db, 100))
        )

    def test_each_claim_has_a_unique_token(self):
        first = run(state.claim_update(self.db, 100))
        self.assertTrue(
            run(state.release_update_claim(self.db, 100, first))
        )

        second = run(state.claim_update(self.db, 100))

        self.assertIsInstance(second, str)
        self.assertNotEqual(first, second)

    def test_expired_processing_claim_can_be_reclaimed(self):
        update_id = 104

        first_token = run(
            state.claim_update(self.db, update_id)
        )

        original_claimed_at = (
            self.db.processed_updates[update_id]["claimed_at"]
        )

        self.db.clock += (
            state.UPDATE_CLAIM_LEASE_SECONDS + 1
        )

        second_token = run(
            state.claim_update(self.db, update_id)
        )

        self.assertIsInstance(second_token, str)
        self.assertNotEqual(first_token, second_token)

        row = self.db.processed_updates[update_id]

        self.assertEqual(row["status"], "processing")
        self.assertGreater(
            row["claimed_at"],
            original_claimed_at,
        )
        self.assertEqual(
            row["claim_token"],
            second_token,
        )

    def test_expired_claim_can_be_reclaimed_at_exact_lease_boundary(self):
        update_id = 105

        first_token = run(
            state.claim_update(self.db, update_id)
        )

        self.db.clock += state.UPDATE_CLAIM_LEASE_SECONDS

        second_token = run(
            state.claim_update(self.db, update_id)
        )

        self.assertIsInstance(second_token, str)
        self.assertNotEqual(first_token, second_token)

    def test_old_owner_cannot_mark_reclaimed_update_processed(self):
        update_id = 106

        old_token = run(
            state.claim_update(self.db, update_id)
        )

        self.db.clock += state.UPDATE_CLAIM_LEASE_SECONDS

        new_token = run(
            state.claim_update(self.db, update_id)
        )

        with self.assertRaises(RuntimeError):
            run(
                state.mark_update_processed(
                    self.db,
                    update_id,
                    old_token,
                )
            )

        self.assertEqual(
            self.db.processed_updates[update_id]["claim_token"],
            new_token,
        )
        self.assertEqual(
            self.db.processed_updates[update_id]["status"],
            "processing",
        )

    def test_old_owner_cannot_release_new_owners_claim(self):
        update_id = 107

        old_token = run(
            state.claim_update(self.db, update_id)
        )

        self.db.clock += state.UPDATE_CLAIM_LEASE_SECONDS

        new_token = run(
            state.claim_update(self.db, update_id)
        )

        released = run(
            state.release_update_claim(
                self.db,
                update_id,
                old_token,
            )
        )

        self.assertFalse(released)
        self.assertEqual(
            self.db.processed_updates[update_id]["claim_token"],
            new_token,
        )

    def test_current_owner_can_mark_update_processed(self):
        update_id = 108

        token = run(
            state.claim_update(self.db, update_id)
        )

        self.assertTrue(
            run(
                state.mark_update_processed(
                    self.db,
                    update_id,
                    token,
                )
            )
        )

        self.assertEqual(
            self.db.processed_updates[update_id]["status"],
            "processed",
        )

        self.assertIsNone(
            self.db.processed_updates[update_id]["lease_expires_at"]
        )

    def test_processed_update_cannot_be_claimed_again(self):
        token = run(state.claim_update(self.db, 109))

        self.assertTrue(
            run(
                state.mark_update_processed(
                    self.db,
                    109,
                    token,
                )
            )
        )

        self.assertIsNone(
            run(state.claim_update(self.db, 109))
        )

    def test_claim_update_rejects_invalid_update_ids(self):
        for update_id in (-1, True, 1.5, "105"):
            with self.subTest(update_id=update_id):
                with self.assertRaises(ValueError):
                    run(state.claim_update(self.db, update_id))

    def test_claim_update_rejects_invalid_lease_seconds(self):
        for lease_seconds in (0, -1, True, 1.5, "300"):
            with self.subTest(lease_seconds=lease_seconds):
                with self.assertRaises(ValueError):
                    run(
                        state.claim_update(
                            self.db,
                            110,
                            lease_seconds=lease_seconds,
                        )
                    )

    def test_mark_update_processed_rejects_invalid_update_ids(self):
        for update_id in (-1, True, 1.5, "107"):
            with self.subTest(update_id=update_id):
                with self.assertRaises(ValueError):
                    run(
                        state.mark_update_processed(
                            self.db,
                            update_id,
                            "test-token",
                        )
                    )

    def test_release_update_claim_rejects_invalid_update_ids(self):
        for update_id in (-1, True, 1.5, "108"):
            with self.subTest(update_id=update_id):
                with self.assertRaises(ValueError):
                    run(
                        state.release_update_claim(
                            self.db,
                            update_id,
                            "test-token",
                        )
                    )

    def test_mark_and_release_reject_invalid_tokens(self):
        for token in ("", " ", None, 123):
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    run(
                        state.mark_update_processed(
                            self.db,
                            111,
                            token,
                        )
                    )

                with self.assertRaises(ValueError):
                    run(
                        state.release_update_claim(
                            self.db,
                            111,
                            token,
                        )
                    )

    def test_database_execute_errors_propagate_for_update_claims(self):
        class FailingDatabase:
            async def execute(self, query, params=None):
                raise RuntimeError("D1 execute failed")

        db = FailingDatabase()

        operations = (
            lambda: state.claim_update(db, 200),
            lambda: state.mark_update_processed(
                db, 200, "test-token"
            ),
            lambda: state.release_update_claim(
                db, 200, "test-token"
            ),
        )

        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "D1 execute failed",
                ):
                    run(operation())

    def test_mark_processed_fetchone_errors_propagate(self):
        class FailingFetchDatabase:
            async def execute(self, query, params=None):
                return FakeResult(1)

            async def fetchone(self, query, params=None):
                raise RuntimeError("D1 fetchone failed")

        with self.assertRaisesRegex(
            RuntimeError,
            "D1 fetchone failed",
        ):
            run(
                state.mark_update_processed(
                    FailingFetchDatabase(),
                    201,
                    "test-token",
                )
            )

    def test_marking_missing_update_as_processed_raises(self):
        with self.assertRaises(RuntimeError):
            run(
                state.mark_update_processed(
                    self.db,
                    999,
                    "missing-token",
                )
            )

    def test_releasing_processing_claim_allows_retry(self):
        first_token = run(
            state.claim_update(self.db, 112)
        )

        self.assertTrue(
            run(
                state.release_update_claim(
                    self.db,
                    112,
                    first_token,
                )
            )
        )

        second_token = run(
            state.claim_update(self.db, 112)
        )

        self.assertIsInstance(second_token, str)
        self.assertNotEqual(first_token, second_token)

    def test_processed_claim_is_not_deleted_by_release(self):
        token = run(state.claim_update(self.db, 113))

        run(
            state.mark_update_processed(
                self.db,
                113,
                token,
            )
        )

        released = run(
            state.release_update_claim(
                self.db,
                113,
                token,
            )
        )

        self.assertFalse(released)
        self.assertEqual(
            self.db.processed_updates[113]["status"],
            "processed",
        )


if __name__ == "__main__":
    unittest.main()