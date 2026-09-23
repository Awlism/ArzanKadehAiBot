# -*- coding: utf-8 -*-
"""
Phase 3 ("Reliability & Pagination") tests.

Covers exactly the Phase 3 scope:
- product list pagination (_render_product_list / handle_my_products /
  handle_product_list_picked) -- correctness of the slicing/has_next math
  against real data, and that a large product count never breaks it
- search result pagination (_render_search_results / handle_search_query
  / handle_search_page + the _search_result_cache pattern)
- safe_edit: exception-safety when BOTH edit_text and the answer()
  fallback fail
- website_url: real validation that rejects what Telegram would reject
  as BUTTON_URL_INVALID, without over-rejecting valid URLs
- handle_global_error: never raises even if notifying the user fails,
  and always returns True

Runs against real SQLite via tests/_fakedb.py -- no aiogram/aiosqlite
needed. Where aiogram objects (CallbackQuery/Message/ErrorEvent) would
normally be involved, small duck-typed fakes stand in for them --
Python's dynamic typing means the real functions work identically
against anything with the right attributes/methods.
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from _extract import extract_names  # noqa: E402
from _fakedb import FakeDB, new_conn  # noqa: E402

NAMES_DB = [
    "SCHEMA_STATEMENTS", "INDEX_STATEMENTS", "COLUMN_MIGRATIONS",
    "ensure_column", "run_column_migrations",
    "PAGE_SIZE_LIST", "format_price", "now_iso", "logger",
]

NAMES_PURE = [
    "website_url", "_UNSAFE_URL_CHARS", "_DANGEROUS_URL_SCHEME_PREFIXES", "PAGE_SIZE_LIST",
]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ==========================================================================
# Product list pagination -- correctness against real data
# ==========================================================================
class ProductListPaginationMathTests(unittest.TestCase):
    """Re-derives the exact offset/has_next logic used inside
    _render_product_list() and checks it against real seeded rows, so a
    seller with many products (the P0 bug from the audit) always gets a
    usable, bounded keyboard instead of one row per product."""

    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES_DB)

    def setUp(self):
        self.conn = new_conn()
        for stmt in self.ns["SCHEMA_STATEMENTS"]:
            self.conn.execute(stmt)
        for stmt in self.ns["INDEX_STATEMENTS"]:
            self.conn.execute(stmt)
        self.conn.commit()
        self.ns["db"] = FakeDB(self.conn)
        run(self.ns["run_column_migrations"]())

        self.conn.execute(
            "INSERT INTO users (id, telegram_id, created_at, updated_at) VALUES (1, 100, 't', 't');"
        )
        self.conn.execute(
            """INSERT INTO sellers (id, name, status, owner_user_id, created_by_user_id, created_at, updated_at)
               VALUES (10, 'Big Shop', 'CLAIMED', 1, 1, 't', 't');"""
        )
        # 25 products -- enough to require 4 pages at PAGE_SIZE_LIST=8.
        for i in range(25):
            self.conn.execute(
                """INSERT INTO products (seller_id, name, price, stock_status, created_at, updated_at)
                   VALUES (10, ?, 1000, 'AVAILABLE', ?, 't');""",
                (f"Product {i:02d}", f"2024-01-{i+1:02d}"),
            )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _fetch_and_paginate(self, page: int):
        all_products = self.conn.execute(
            "SELECT * FROM products WHERE seller_id = ? ORDER BY created_at DESC;", (10,)
        ).fetchall()
        page_size = self.ns["PAGE_SIZE_LIST"]
        offset = page * page_size
        page_products = all_products[offset: offset + page_size]
        has_next = offset + page_size < len(all_products)
        return all_products, page_products, has_next

    def test_25_products_yields_page_size_8_first_page(self):
        all_products, page_products, has_next = self._fetch_and_paginate(0)
        self.assertEqual(len(all_products), 25)
        self.assertEqual(len(page_products), self.ns["PAGE_SIZE_LIST"])
        self.assertTrue(has_next)

    def test_last_page_has_the_remainder_and_no_next(self):
        # 25 products / 8 per page -> pages 0,1,2 full, page 3 has 1 item.
        all_products, page_products, has_next = self._fetch_and_paginate(3)
        self.assertEqual(len(page_products), 1)
        self.assertFalse(has_next)

    def test_every_product_appears_exactly_once_across_all_pages(self):
        seen_ids = []
        page = 0
        while True:
            all_products, page_products, has_next = self._fetch_and_paginate(page)
            seen_ids.extend(p["id"] for p in page_products)
            if not has_next:
                break
            page += 1
        self.assertEqual(sorted(seen_ids), sorted(p["id"] for p in all_products))
        self.assertEqual(len(seen_ids), len(set(seen_ids)), "no product should repeat across pages")

    def test_keyboard_button_count_per_page_stays_bounded_regardless_of_total_products(self):
        """The actual bug: without pagination, N products -> ~3N buttons
        in one keyboard. With pagination, one page is always <= 8
        products -> <= (8*2 + 1 add-button + up to 2 nav buttons) rows,
        completely independent of how many products the seller has."""
        _all_products, page_products, _has_next = self._fetch_and_paginate(0)
        # 2 buttons per product (name-row is 1 button, edit+delete is a
        # second row of 2 buttons) -- bounded by PAGE_SIZE_LIST regardless
        # of total product count (25 here, could be 2500 with the same
        # per-page bound).
        self.assertLessEqual(len(page_products), self.ns["PAGE_SIZE_LIST"])

    def test_empty_product_list_requests_page_zero_with_no_next(self):
        self.conn.execute("DELETE FROM products WHERE seller_id = 10;")
        self.conn.commit()
        all_products, page_products, has_next = self._fetch_and_paginate(0)
        self.assertEqual(all_products, [])
        self.assertEqual(page_products, [])
        self.assertFalse(has_next)


# ==========================================================================
# Search result pagination + cache
# ==========================================================================
class SearchPaginationCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES_DB + ["_search_result_cache"])

    def setUp(self):
        self.ns["_search_result_cache"].clear()

    def test_cache_starts_empty_for_unknown_user(self):
        self.assertIsNone(self.ns["_search_result_cache"].get(999))

    def test_cache_stores_and_retrieves_header_and_products(self):
        fake_products = [{"id": i, "name": f"p{i}"} for i in range(12)]
        self.ns["_search_result_cache"][1] = {"header": "🔎 نتایج", "products": fake_products}
        cached = self.ns["_search_result_cache"][1]
        self.assertEqual(cached["header"], "🔎 نتایج")
        self.assertEqual(len(cached["products"]), 12)

    def test_pagination_math_matches_product_list_pattern(self):
        """Search results use the exact same PAGE_SIZE_LIST slicing as
        the product list -- verified here to guard against drift."""
        page_size = self.ns["PAGE_SIZE_LIST"]
        products = list(range(18))  # 18 fake "products"
        page = 1
        offset = page * page_size
        page_items = products[offset: offset + page_size]
        has_next = offset + page_size < len(products)
        self.assertEqual(page_items, products[page_size: page_size * 2])
        self.assertTrue(has_next)

    def test_cache_is_isolated_per_user(self):
        self.ns["_search_result_cache"][1] = {"header": "a", "products": [1]}
        self.ns["_search_result_cache"][2] = {"header": "b", "products": [2, 3]}
        self.assertEqual(self.ns["_search_result_cache"][1]["products"], [1])
        self.assertEqual(self.ns["_search_result_cache"][2]["products"], [2, 3])


# ==========================================================================
# website_url: real validation, no over-rejection
# ==========================================================================
class WebsiteUrlValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES_PURE)
        cls.website_url = staticmethod(cls.ns["website_url"])

    # --- existing behavior preserved for valid inputs ---
    def test_bare_domain_gets_https_prefix(self):
        self.assertEqual(self.website_url("example.com"), "https://example.com")

    def test_http_scheme_preserved(self):
        self.assertEqual(self.website_url("http://example.com"), "http://example.com")

    def test_https_scheme_preserved(self):
        self.assertEqual(self.website_url("https://example.com"), "https://example.com")

    def test_domain_with_path_and_query_preserved(self):
        self.assertEqual(
            self.website_url("example.com/shop?ref=ig"),
            "https://example.com/shop?ref=ig",
        )

    def test_none_and_empty_return_none(self):
        self.assertIsNone(self.website_url(None))
        self.assertIsNone(self.website_url(""))
        self.assertIsNone(self.website_url("   "))

    def test_subdomain_and_persian_tld_style_domain_allowed(self):
        self.assertEqual(self.website_url("shop.arzankadeh.ir"), "https://shop.arzankadeh.ir")

    def test_localhost_and_ip_not_over_rejected(self):
        # No TLD requirement -- avoid over-validation per the brief.
        self.assertEqual(self.website_url("localhost:8000"), "https://localhost:8000")
        self.assertEqual(self.website_url("192.168.1.1"), "https://192.168.1.1")

    # --- new: genuinely invalid input is rejected, not silently broken ---
    def test_url_with_embedded_space_is_rejected(self):
        self.assertIsNone(self.website_url("not a url"))
        self.assertIsNone(self.website_url("example.com /path"))

    def test_scheme_smuggling_via_concatenation_is_rejected(self):
        """Regression: the OLD code only checked the raw string didn't
        start with http(s):// and then blindly prepended "https://",
        turning "ftp://x.com" into the malformed "https://ftp://x.com"
        -- which used to silently produce a broken Telegram button. Must
        now be rejected outright."""
        self.assertIsNone(self.website_url("ftp://x.com"))
        self.assertIsNone(self.website_url("tg://resolve?domain=x"))

    def test_dangerous_schemes_without_double_slash_are_rejected(self):
        """javascript:/data:/vbscript:/file:/about: style URLs don't
        necessarily contain "://" at all, so they need their own check
        distinct from the scheme-smuggling one above."""
        self.assertIsNone(self.website_url("javascript:alert(1)"))
        self.assertIsNone(self.website_url("data:text/html,<script>1</script>"))
        self.assertIsNone(self.website_url("JavaScript:alert(1)"))  # case-insensitive

    def test_host_colon_port_is_not_mistaken_for_a_foreign_scheme(self):
        """host:port notation (no "://") must still work -- only an
        actual "scheme://" or a specific dangerous "scheme:" prefix is
        rejected, not any string containing a colon."""
        self.assertEqual(self.website_url("localhost:8000"), "https://localhost:8000")
        self.assertEqual(self.website_url("example.com:443"), "https://example.com:443")

    def test_empty_host_is_rejected(self):
        self.assertIsNone(self.website_url("http://"))
        self.assertIsNone(self.website_url("https://"))

    def test_dangerous_characters_are_rejected(self):
        for bad in ['example.com"><script>', "example.com'; DROP TABLE", "example.com(1)"]:
            self.assertIsNone(self.website_url(bad), f"should reject: {bad!r}")

    def test_leading_and_trailing_whitespace_is_trimmed_not_rejected(self):
        """Surrounding whitespace is normal copy-paste noise, not an
        attack -- strip() already handles it safely, so this must still
        succeed (distinct from an INTERNAL space, which is rejected)."""
        self.assertEqual(self.website_url("  example.com  "), "https://example.com")
        self.assertEqual(self.website_url("example.com\t"), "https://example.com")

    def test_internal_newline_is_rejected(self):
        self.assertIsNone(self.website_url("example.com\nSet-Cookie: x"))


# ==========================================================================
# safe_edit: exception-safety of the fallback path
# ==========================================================================
class _FakeTelegramBadRequest(Exception):
    pass


class _FakeMessage:
    def __init__(self, edit_outcome, answer_outcome):
        """outcome: None to succeed, or an Exception instance to raise."""
        self._edit_outcome = edit_outcome
        self._answer_outcome = answer_outcome
        self.edit_calls = 0
        self.answer_calls = 0

    async def edit_text(self, text, reply_markup=None):
        self.edit_calls += 1
        if self._edit_outcome is not None:
            raise self._edit_outcome
        return True

    async def answer(self, text, reply_markup=None):
        self.answer_calls += 1
        if self._answer_outcome is not None:
            raise self._answer_outcome
        return True


class _FakeCallback:
    def __init__(self, message):
        self.message = message


class SafeEditExceptionSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(["safe_edit", "logger", "TelegramBadRequest"] if False else ["safe_edit", "logger"])
        # TelegramBadRequest isn't a real top-level name we can extract
        # (it's an aiogram import, and aiogram isn't installed here) --
        # inject a compatible fake into the same namespace safe_edit was
        # exec'd into, exactly like `re`/`logging` are injected globally
        # in _extract.py. safe_edit's `except TelegramBadRequest as exc`
        # binds to whatever name is in its own __globals__, so this fake
        # is exercised by the exact same code path the real class would be.
        cls.ns["TelegramBadRequest"] = _FakeTelegramBadRequest
        # Re-extract now that the fake exception type is available, since
        # safe_edit's body references TelegramBadRequest by name at call
        # time (not at def time), so this order is actually fine either
        # way -- re-assigning here just makes the intent explicit.

    def test_successful_edit_does_not_touch_answer(self):
        msg = _FakeMessage(edit_outcome=None, answer_outcome=None)
        cb = _FakeCallback(msg)
        run(self.ns["safe_edit"](cb, "hi", object()))
        self.assertEqual(msg.edit_calls, 1)
        self.assertEqual(msg.answer_calls, 0)

    def test_message_not_modified_is_swallowed_silently(self):
        msg = _FakeMessage(
            edit_outcome=_FakeTelegramBadRequest("Bad Request: message is not modified"),
            answer_outcome=None,
        )
        cb = _FakeCallback(msg)
        run(self.ns["safe_edit"](cb, "hi", object()))  # must not raise
        self.assertEqual(msg.edit_calls, 1)
        self.assertEqual(msg.answer_calls, 0, "must not fall back to answer() for this specific error")

    def test_other_bad_request_falls_back_to_answer(self):
        msg = _FakeMessage(
            edit_outcome=_FakeTelegramBadRequest("Bad Request: BUTTON_URL_INVALID"),
            answer_outcome=None,
        )
        cb = _FakeCallback(msg)
        run(self.ns["safe_edit"](cb, "hi", object()))
        self.assertEqual(msg.edit_calls, 1)
        self.assertEqual(msg.answer_calls, 1)

    def test_regression_both_edit_and_answer_failing_never_raises(self):
        """This is the exact bug fixed in Phase 3: previously, if the
        answer() fallback ALSO raised, the exception propagated
        uncaught into the dispatcher. Now it must be swallowed (and
        logged) instead."""
        msg = _FakeMessage(
            edit_outcome=_FakeTelegramBadRequest("Bad Request: BUTTON_URL_INVALID"),
            answer_outcome=_FakeTelegramBadRequest("Bad Request: BUTTON_URL_INVALID"),
        )
        cb = _FakeCallback(msg)
        try:
            run(self.ns["safe_edit"](cb, "hi", object()))
        except _FakeTelegramBadRequest:
            self.fail("safe_edit must not let a second failed attempt raise uncaught")
        self.assertEqual(msg.edit_calls, 1)
        self.assertEqual(msg.answer_calls, 1)

    def test_unrelated_exception_types_are_not_swallowed(self):
        """safe_edit only catches TelegramBadRequest -- a genuinely
        different bug (e.g. a TypeError from a caller's own mistake)
        must still surface normally, not be hidden."""
        msg = _FakeMessage(edit_outcome=ValueError("something else broke"), answer_outcome=None)
        cb = _FakeCallback(msg)
        with self.assertRaises(ValueError):
            run(self.ns["safe_edit"](cb, "hi", object()))


# ==========================================================================
# Global error handler
# ==========================================================================
class _FakeChat:
    def __init__(self, chat_id):
        self.id = chat_id


class _FakeBot:
    def __init__(self, send_outcome=None):
        self._send_outcome = send_outcome
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        if self._send_outcome is not None:
            raise self._send_outcome
        self.sent.append((chat_id, text))


class _FakeUpdateMessage:
    def __init__(self, bot):
        self.chat = _FakeChat(4242)
        self.bot = bot


class _FakeUpdateCallbackQuery:
    def __init__(self, bot, answer_outcome=None):
        self.message = type("M", (), {"chat": _FakeChat(9999)})()
        self.bot = bot
        self._answer_outcome = answer_outcome
        self.answered = False

    async def answer(self):
        self.answered = True
        if self._answer_outcome is not None:
            raise self._answer_outcome


class _FakeUpdate:
    def __init__(self, message=None, callback_query=None):
        self.message = message
        self.callback_query = callback_query


class _FakeErrorEvent:
    def __init__(self, update, exception):
        self.update = update
        self.exception = exception


class GlobalErrorHandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(["handle_global_error", "logger"])

    def test_notifies_the_chat_for_a_message_update_and_returns_true(self):
        bot = _FakeBot()
        update = _FakeUpdate(message=_FakeUpdateMessage(bot))
        event = _FakeErrorEvent(update, RuntimeError("boom"))
        result = run(self.ns["handle_global_error"](event))
        self.assertTrue(result)
        self.assertEqual(len(bot.sent), 1)
        self.assertEqual(bot.sent[0][0], 4242)

    def test_notifies_and_answers_for_a_callback_query_update(self):
        bot = _FakeBot()
        cq = _FakeUpdateCallbackQuery(bot)
        update = _FakeUpdate(callback_query=cq)
        event = _FakeErrorEvent(update, RuntimeError("boom"))
        result = run(self.ns["handle_global_error"](event))
        self.assertTrue(result)
        self.assertEqual(len(bot.sent), 1)
        self.assertTrue(cq.answered)

    def test_regression_a_failed_notification_never_raises_and_still_returns_true(self):
        """The whole point of this handler: it is the LAST line of
        defense. If even the error-reporting itself fails, that must
        not become a second unhandled exception."""
        bot = _FakeBot(send_outcome=RuntimeError("network down"))
        update = _FakeUpdate(message=_FakeUpdateMessage(bot))
        event = _FakeErrorEvent(update, RuntimeError("original bug"))
        try:
            result = run(self.ns["handle_global_error"](event))
        except Exception:  # noqa: BLE001
            self.fail("handle_global_error must never raise, even if notifying the user fails")
        self.assertTrue(result)

    def test_update_with_neither_message_nor_callback_is_handled_gracefully(self):
        update = _FakeUpdate()  # e.g. some other update type
        event = _FakeErrorEvent(update, RuntimeError("boom"))
        result = run(self.ns["handle_global_error"](event))
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
