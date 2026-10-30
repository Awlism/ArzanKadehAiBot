# -*- coding: utf-8 -*-
"""Integration tests for the public seller contact redirect endpoint."""

from __future__ import annotations

import sys
import types
import unittest
from urllib.parse import quote

import test_worker_entry as harness


class ContactEndpointTests(unittest.TestCase):
    def setUp(self):
        self.entry = harness.entry
        self.original_response = self.entry.Response

        self.fake_response = type(
            "TestResponse",
            (self.original_response,),
            {
                "__init__": self._response_init,
            },
        )
        self.entry.Response = self.fake_response

        self.backend_class = self.entry.D1Backend
        self.original_fetchone = self.backend_class.fetchone
        self.backend_class.contact_seller_row = None

        async def fake_fetchone(backend, query, params=None):
            if "FROM sellers" in query:
                row = backend.__class__.contact_seller_row
                return dict(row) if row is not None else None

            return await self.original_fetchone(
                backend,
                query,
                params,
            )

        self.backend_class.fetchone = fake_fetchone

        self.previous_worker = sys.modules.get("worker")
        self.previous_seller = sys.modules.get("worker.seller")

        worker_module = types.ModuleType("worker")
        worker_module.__path__ = []

        seller_module = types.ModuleType("worker.seller")

        seller_module._instagram_url = (
            lambda value: (
                "https://instagram.com/sample"
                if value == "sample"
                else None
            )
        )
        seller_module._telegram_url = (
            lambda value: (
                "https://t.me/sample"
                if value == "sample"
                else None
            )
        )
        seller_module._whatsapp_url = (
            lambda value: (
                "https://wa.me/989121234567"
                if value == "989121234567"
                else None
            )
        )

        sys.modules["worker"] = worker_module
        sys.modules["worker.seller"] = seller_module

        self.entry.backend.backend = None
        self.entry.backend.connected = False
        self.backend_class.instances.clear()

        self.worker = self.entry.Default()
        self.worker.env = harness.FakeEnv(
            secret="test-secret"
        )

    @staticmethod
    def _response_init(response, body, status=200, headers=None):
        response.body = body
        response.status = status
        response.headers = dict(headers or {})

    def tearDown(self):
        self.entry.Response = self.original_response
        self.backend_class.fetchone = self.original_fetchone
        self.backend_class.contact_seller_row = None

        if self.previous_worker is None:
            sys.modules.pop("worker", None)
        else:
            sys.modules["worker"] = self.previous_worker

        if self.previous_seller is None:
            sys.modules.pop("worker.seller", None)
        else:
            sys.modules["worker.seller"] = self.previous_seller

    def _request(self, url):
        request = harness.FakeRequest("GET")
        request.url = url

        return request

    def _fetch(self, query):
        return harness.run(
            self.worker.fetch(
                self._request(
                    "https://example.test/contact?" + query
                )
            )
        )

    def _active_seller(self, **overrides):
        seller = {
            "id": 12,
            "instagram": "sample",
            "telegram": "sample",
            "whatsapp": "989121234567",
            "is_active": 1,
        }
        seller.update(overrides)

        self.backend_class.contact_seller_row = seller

    def test_missing_query_parameters_return_400(self):
        response = self._fetch("channel=instagram")

        self.assertEqual(response.status, 400)
        self.assertEqual(
            len(self.backend_class.instances),
            0,
        )

    def test_duplicate_channel_returns_400(self):
        response = self._fetch(
            "channel=instagram&channel=telegram&seller_id=12"
        )

        self.assertEqual(response.status, 400)
        self.assertEqual(
            len(self.backend_class.instances),
            0,
        )

    def test_duplicate_seller_id_returns_400(self):
        response = self._fetch(
            "channel=instagram&seller_id=12&seller_id=13"
        )

        self.assertEqual(response.status, 400)
        self.assertEqual(
            len(self.backend_class.instances),
            0,
        )

    def test_invalid_seller_id_returns_400(self):
        for seller_id in ("abc", "0", "-1"):
            with self.subTest(seller_id=seller_id):
                response = self._fetch(
                    f"channel=instagram&seller_id={quote(seller_id)}"
                )

                self.assertEqual(response.status, 400)

        self.assertEqual(
            len(self.backend_class.instances),
            0,
        )

    def test_unsupported_channel_returns_400(self):
        response = self._fetch(
            "channel=website&seller_id=12"
        )

        self.assertEqual(response.status, 400)
        self.assertEqual(
            len(self.backend_class.instances),
            0,
        )

    def test_missing_seller_returns_404(self):
        self.backend_class.contact_seller_row = None

        response = self._fetch(
            "channel=instagram&seller_id=12"
        )

        self.assertEqual(response.status, 404)
        self.assertEqual(
            len(self.backend_class.instances),
            1,
        )
        self.assertEqual(
            self.backend_class.instances[0].execute_calls,
            [],
        )

    def test_inactive_seller_returns_410(self):
        self._active_seller(is_active=0)

        response = self._fetch(
            "channel=instagram&seller_id=12"
        )

        self.assertEqual(response.status, 410)
        self.assertEqual(
            self.backend_class.instances[0].execute_calls,
            [],
        )

    def test_null_active_status_is_treated_as_active(self):
        self._active_seller(is_active=None)

        response = self._fetch(
            "channel=instagram&seller_id=12"
        )

        self.assertEqual(response.status, 302)
        self.assertEqual(
            response.headers["Location"],
            "https://instagram.com/sample",
        )

    def test_invalid_contact_value_returns_404(self):
        self._active_seller(instagram="invalid")

        response = self._fetch(
            "channel=instagram&seller_id=12"
        )

        self.assertEqual(response.status, 404)
        self.assertEqual(
            self.backend_class.instances[0].execute_calls,
            [],
        )

    def test_successful_redirects_for_all_channels(self):
        cases = (
            (
                "instagram",
                "https://instagram.com/sample",
                "instagram_click",
            ),
            (
                "telegram",
                "https://t.me/sample",
                "telegram_click",
            ),
            (
                "whatsapp",
                "https://wa.me/989121234567",
                "whatsapp_click",
            ),
        )

        for channel, expected_url, expected_event in cases:
            with self.subTest(channel=channel):
                self.backend_class.instances.clear()
                self.entry.backend.backend = None
                self.entry.backend.connected = False

                self._active_seller()

                response = self._fetch(
                    f"channel={channel}&seller_id=12"
                )

                self.assertEqual(response.status, 302)
                self.assertEqual(response.body, "")
                self.assertEqual(
                    response.headers.get("Location"),
                    expected_url,
                )
                self.assertEqual(
                    response.headers.get("Cache-Control"),
                    "no-store",
                )

                self.assertEqual(
                    len(self.backend_class.instances),
                    1,
                )

                backend = self.backend_class.instances[0]

                self.assertTrue(backend.connected)
                self.assertEqual(
                    len(backend.execute_calls),
                    1,
                )

                query, params = backend.execute_calls[0]
                normalized_query = " ".join(
                    query.lower().split()
                )

                self.assertIn("insert into events", normalized_query)
                self.assertIn("user_id", normalized_query)
                self.assertIn("entity_type", normalized_query)
                self.assertEqual(
                    params[0],
                    expected_event,
                )
                self.assertEqual(params[1], 12)
                self.assertTrue(params[2])


if __name__ == "__main__":
    unittest.main()