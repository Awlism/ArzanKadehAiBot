# -*- coding: utf-8 -*-
"""
Phase 3 reliability and pagination tests for the modular architecture.

These tests target the real modular source files instead of the old
monolithic bot.py implementation.
"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from _extract import extract_names  # noqa: E402
from _fakedb import FakeDB, new_conn  # noqa: E402


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ==========================================================================
# Product pagination
# ==========================================================================


class ProductPaginationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(
            [
                "SCHEMA_STATEMENTS",
                "INDEX_STATEMENTS",
                "COLUMN_MIGRATIONS",
                "run_column_migrations",
                "PAGE_SIZE_LIST",
            ]
        )

    def setUp(self):
        self.conn = new_conn()

        for statement in self.ns["SCHEMA_STATEMENTS"]:
            self.conn.execute(statement)

        for statement in self.ns["INDEX_STATEMENTS"]:
            self.conn.execute(statement)

        self.conn.commit()

        self.ns["db"] = FakeDB(self.conn)

        run(self.ns["run_column_migrations"]())

        self.conn.execute(
            """
            INSERT INTO users (
                id,
                telegram_id,
                created_at,
                updated_at
            )
            VALUES (1, 100, 't', 't');
            """
        )

        self.conn.execute(
            """
            INSERT INTO sellers (
                id,
                name,
                status,
                owner_user_id,
                created_by_user_id,
                created_at,
                updated_at
            )
            VALUES (
                10,
                'Big Shop',
                'CLAIMED',
                1,
                1,
                't',
                't'
            );
            """
        )

        for index in range(25):
            self.conn.execute(
                """
                INSERT INTO products (
                    seller_id,
                    name,
                    price,
                    stock_status,
                    created_at,
                    updated_at
                )
                VALUES (
                    10,
                    ?,
                    1000,
                    'AVAILABLE',
                    ?,
                    't'
                );
                """,
                (
                    f"Product {index:02d}",
                    f"2024-01-{index + 1:02d}",
                ),
            )

        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _paginate(self, page):
        products = self.conn.execute(
            """
            SELECT *
            FROM products
            WHERE seller_id = ?
            ORDER BY created_at DESC;
            """,
            (10,),
        ).fetchall()

        page_size = self.ns["PAGE_SIZE_LIST"]
        offset = page * page_size

        page_products = products[
            offset:offset + page_size
        ]

        has_next = (
            offset + page_size < len(products)
        )

        return products, page_products, has_next

    def test_first_page_is_bounded(self):
        products, page_products, has_next = self._paginate(0)

        self.assertEqual(len(products), 25)
        self.assertEqual(
            len(page_products),
            self.ns["PAGE_SIZE_LIST"],
        )
        self.assertTrue(has_next)

    def test_last_page_contains_only_remaining_products(self):
        _products, page_products, has_next = self._paginate(3)

        self.assertEqual(len(page_products), 1)
        self.assertFalse(has_next)

    def test_all_products_are_seen_exactly_once(self):
        products, _page_products, _has_next = self._paginate(0)

        seen_ids = []

        page = 0

        while True:
            _all, page_products, has_next = self._paginate(page)

            seen_ids.extend(
                product["id"]
                for product in page_products
            )

            if not has_next:
                break

            page += 1

        self.assertEqual(
            sorted(seen_ids),
            sorted(product["id"] for product in products),
        )

        self.assertEqual(
            len(seen_ids),
            len(set(seen_ids)),
        )

    def test_empty_product_list_has_no_next_page(self):
        self.conn.execute(
            "DELETE FROM products WHERE seller_id = 10;"
        )
        self.conn.commit()

        products, page_products, has_next = self._paginate(0)

        self.assertEqual(products, [])
        self.assertEqual(page_products, [])
        self.assertFalse(has_next)

    def test_page_size_constant_is_positive(self):
        self.assertGreater(
            self.ns["PAGE_SIZE_LIST"],
            0,
        )


# ==========================================================================
# Search pagination cache
# ==========================================================================


class SearchPaginationCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(
            [
                "PAGE_SIZE_LIST",
                "_search_result_cache",
            ]
        )

    def setUp(self):
        self.ns["_search_result_cache"].clear()

    def test_cache_starts_empty(self):
        self.assertEqual(
            self.ns["_search_result_cache"],
            {},
        )

    def test_cache_is_isolated_per_user(self):
        cache = self.ns["_search_result_cache"]

        cache[100] = {
            "header": "نتایج کاربر اول",
            "products": [1, 2],
        }

        cache[200] = {
            "header": "نتایج کاربر دوم",
            "products": [3, 4, 5],
        }

        self.assertEqual(
            cache[100]["products"],
            [1, 2],
        )

        self.assertEqual(
            cache[200]["products"],
            [3, 4, 5],
        )

    def test_cached_search_results_preserve_header_and_products(self):
        cache = self.ns["_search_result_cache"]

        products = [
            {
                "id": index,
                "name": f"Product {index}",
            }
            for index in range(12)
        ]

        cache[1] = {
            "header": "🔎 نتایج",
            "products": products,
        }

        self.assertEqual(
            cache[1]["header"],
            "🔎 نتایج",
        )

        self.assertEqual(
            cache[1]["products"],
            products,
        )

    def test_search_page_math_matches_shared_page_size(self):
        page_size = self.ns["PAGE_SIZE_LIST"]
        products = list(range(18))

        page = 1
        offset = page * page_size

        page_items = products[
            offset:offset + page_size
        ]

        has_next = (
            offset + page_size < len(products)
        )

        self.assertEqual(
            page_items,
            products[page_size:page_size * 2],
        )

        self.assertTrue(has_next)

    def test_last_search_page_has_no_next(self):
        page_size = self.ns["PAGE_SIZE_LIST"]
        products = list(range(page_size + 1))

        page = 1
        offset = page * page_size

        page_items = products[
            offset:offset + page_size
        ]

        has_next = (
            offset + page_size < len(products)
        )

        self.assertEqual(
            len(page_items),
            1,
        )

        self.assertFalse(has_next)


# ==========================================================================
# Website URL validation
# ==========================================================================


class WebsiteUrlValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(
            [
                "website_url",
                "_UNSAFE_URL_CHARS",
                "_DANGEROUS_URL_SCHEME_PREFIXES",
            ]
        )

        cls.website_url = staticmethod(
            cls.ns["website_url"]
        )

    def test_bare_domain_gets_https(self):
        self.assertEqual(
            self.website_url("example.com"),
            "https://example.com",
        )

    def test_http_is_preserved(self):
        self.assertEqual(
            self.website_url("http://example.com"),
            "http://example.com",
        )

    def test_https_is_preserved(self):
        self.assertEqual(
            self.website_url("https://example.com"),
            "https://example.com",
        )

    def test_path_and_query_are_preserved(self):
        self.assertEqual(
            self.website_url(
                "example.com/shop?ref=telegram"
            ),
            "https://example.com/shop?ref=telegram",
        )

    def test_subdomain_is_valid(self):
        self.assertEqual(
            self.website_url(
                "shop.arzankadeh.ir"
            ),
            "https://shop.arzankadeh.ir",
        )

    def test_localhost_with_port_is_valid(self):
        self.assertEqual(
            self.website_url(
                "localhost:8000"
            ),
            "https://localhost:8000",
        )

    def test_ipv4_address_is_valid(self):
        self.assertEqual(
            self.website_url(
                "192.168.1.1"
            ),
            "https://192.168.1.1",
        )

    def test_none_and_empty_are_rejected(self):
        self.assertIsNone(
            self.website_url(None)
        )

        self.assertIsNone(
            self.website_url("")
        )

        self.assertIsNone(
            self.website_url("   ")
        )

    def test_internal_spaces_are_rejected(self):
        self.assertIsNone(
            self.website_url("not a url")
        )

        self.assertIsNone(
            self.website_url(
                "example.com /path"
            )
        )

    def test_foreign_schemes_are_rejected(self):
        self.assertIsNone(
            self.website_url(
                "ftp://example.com"
            )
        )

        self.assertIsNone(
            self.website_url(
                "tg://resolve?domain=test"
            )
        )

    def test_dangerous_schemes_are_rejected(self):
        self.assertIsNone(
            self.website_url(
                "javascript:alert(1)"
            )
        )

        self.assertIsNone(
            self.website_url(
                "JavaScript:alert(1)"
            )
        )

        self.assertIsNone(
            self.website_url(
                "data:text/html,test"
            )
        )

        self.assertIsNone(
            self.website_url(
                "file:///tmp/test"
            )
        )

    def test_credentials_are_rejected(self):
        self.assertIsNone(
            self.website_url(
                "https://user:pass@example.com"
            )
        )

    def test_empty_host_is_rejected(self):
        self.assertIsNone(
            self.website_url("http://")
        )

        self.assertIsNone(
            self.website_url("https://")
        )

    def test_invalid_host_is_rejected(self):
        self.assertIsNone(
            self.website_url(
                "https://example..com"
            )
        )

    def test_invalid_port_is_rejected(self):
        self.assertIsNone(
            self.website_url(
                "https://example.com:99999"
            )
        )

    def test_surrounding_whitespace_is_trimmed(self):
        self.assertEqual(
            self.website_url(
                "  example.com  "
            ),
            "https://example.com",
        )

    def test_control_characters_are_rejected(self):
        self.assertIsNone(
            self.website_url(
                "example.com\nSet-Cookie: x"
            )
        )


# ==========================================================================
# safe_edit
# ==========================================================================


class _FakeTelegramBadRequest(Exception):
    pass


class _FakeMessage:
    def __init__(
        self,
        edit_error=None,
        answer_error=None,
    ):
        self.edit_error = edit_error
        self.answer_error = answer_error
        self.edit_calls = 0
        self.answer_calls = 0

    async def edit_text(
        self,
        text,
        reply_markup=None,
    ):
        self.edit_calls += 1

        if self.edit_error is not None:
            raise self.edit_error

        return True

    async def answer(
        self,
        text,
        reply_markup=None,
    ):
        self.answer_calls += 1

        if self.answer_error is not None:
            raise self.answer_error

        return True


class _FakeCallback:
    def __init__(self, message):
        self.message = message


class SafeEditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(
            [
                "safe_edit",
                "logger",
            ]
        )

        cls.ns["TelegramBadRequest"] = (
            _FakeTelegramBadRequest
        )

    def test_successful_edit_returns_true(self):
        message = _FakeMessage()

        callback = _FakeCallback(message)

        result = run(
            self.ns["safe_edit"](
                callback,
                "hello",
                object(),
            )
        )

        self.assertTrue(result)
        self.assertEqual(
            message.edit_calls,
            1,
        )
        self.assertEqual(
            message.answer_calls,
            0,
        )

    def test_message_not_modified_does_not_fallback(self):
        message = _FakeMessage(
            edit_error=_FakeTelegramBadRequest(
                "Bad Request: message is not modified"
            )
        )

        callback = _FakeCallback(message)

        result = run(
            self.ns["safe_edit"](
                callback,
                "hello",
                object(),
            )
        )

        self.assertFalse(result)

        self.assertEqual(
            message.edit_calls,
            1,
        )

        self.assertEqual(
            message.answer_calls,
            0,
        )

    def test_other_bad_request_uses_fallback(self):
        message = _FakeMessage(
            edit_error=_FakeTelegramBadRequest(
                "Bad Request: BUTTON_URL_INVALID"
            )
        )

        callback = _FakeCallback(message)

        result = run(
            self.ns["safe_edit"](
                callback,
                "hello",
                object(),
            )
        )

        self.assertTrue(result)

        self.assertEqual(
            message.edit_calls,
            1,
        )

        self.assertEqual(
            message.answer_calls,
            1,
        )

    def test_fallback_failure_is_not_silently_swallowed(self):
        message = _FakeMessage(
            edit_error=_FakeTelegramBadRequest(
                "Bad Request: BUTTON_URL_INVALID"
            ),
            answer_error=_FakeTelegramBadRequest(
                "Bad Request: BUTTON_URL_INVALID"
            ),
        )

        callback = _FakeCallback(message)

        with self.assertRaises(
            _FakeTelegramBadRequest
        ):
            run(
                self.ns["safe_edit"](
                    callback,
                    "hello",
                    object(),
                )
            )

        self.assertEqual(
            message.edit_calls,
            1,
        )

        self.assertEqual(
            message.answer_calls,
            1,
        )

    def test_unrelated_exception_is_not_swallowed(self):
        message = _FakeMessage(
            edit_error=ValueError(
                "unexpected failure"
            )
        )

        callback = _FakeCallback(message)

        with self.assertRaises(ValueError):
            run(
                self.ns["safe_edit"](
                    callback,
                    "hello",
                    object(),
                )
            )


if __name__ == "__main__":
    unittest.main()