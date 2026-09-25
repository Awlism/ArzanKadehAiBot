# -*- coding: utf-8 -*-
"""
Tests for pure utility helpers in bot/utils.py.

These tests use tests/_extract.py so the real modular utility functions
are exercised without importing the Telegram application.
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from _extract import extract_names  # noqa: E402


NAMES = [
    "parse_int",
    "format_price",
    "status_badge",
    "instagram_url",
    "telegram_url",
    "website_url",
    "whatsapp_url",
    "now_iso",
]


class UtilsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES)

    def test_parse_int_valid(self):
        parse_int = self.ns["parse_int"]

        self.assertEqual(parse_int("42"), 42)
        self.assertEqual(parse_int("0"), 0)
        self.assertEqual(parse_int("-5"), -5)

    def test_parse_int_invalid_returns_none(self):
        parse_int = self.ns["parse_int"]

        self.assertIsNone(parse_int("abc"))
        self.assertIsNone(parse_int(None))
        self.assertIsNone(parse_int(""))
        self.assertIsNone(parse_int("1.5"))

    def test_format_price_none(self):
        format_price = self.ns["format_price"]

        self.assertEqual(
            format_price(None),
            "قیمت نامشخص",
        )

    def test_format_price_numeric(self):
        format_price = self.ns["format_price"]

        self.assertEqual(
            format_price(150000),
            "150,000 تومان",
        )
        self.assertEqual(
            format_price(0),
            "0 تومان",
        )

    def test_status_badge_known_statuses(self):
        status_badge = self.ns["status_badge"]

        self.assertEqual(
            status_badge("PENDING"),
            "🟡",
        )
        self.assertEqual(
            status_badge("APPROVED"),
            "🟢",
        )
        self.assertEqual(
            status_badge("REJECTED"),
            "🔴",
        )
        self.assertEqual(
            status_badge("COMPLETED"),
            "✅",
        )
        self.assertEqual(
            status_badge("CANCELLED"),
            "❌",
        )

    def test_status_badge_unknown_status_uses_safe_fallback(self):
        status_badge = self.ns["status_badge"]

        self.assertEqual(
            status_badge("UNKNOWN_STATUS"),
            "⚪",
        )

    def test_instagram_url_strips_at_sign(self):
        instagram_url = self.ns["instagram_url"]

        self.assertEqual(
            instagram_url("@shopname"),
            "https://instagram.com/shopname",
        )
        self.assertEqual(
            instagram_url("shopname"),
            "https://instagram.com/shopname",
        )

    def test_instagram_url_accepts_existing_url(self):
        instagram_url = self.ns["instagram_url"]

        self.assertEqual(
            instagram_url(
                "https://instagram.com/shopname"
            ),
            "https://instagram.com/shopname",
        )

    def test_instagram_url_none_or_empty(self):
        instagram_url = self.ns["instagram_url"]

        self.assertIsNone(
            instagram_url(None)
        )
        self.assertIsNone(
            instagram_url("")
        )
        self.assertIsNone(
            instagram_url("   ")
        )

    def test_instagram_url_rejects_unsafe_input(self):
        instagram_url = self.ns["instagram_url"]

        self.assertIsNone(
            instagram_url("shop name")
        )
        self.assertIsNone(
            instagram_url("shop/name")
        )
        self.assertIsNone(
            instagram_url("shop<script>")
        )

    def test_telegram_url_strips_at_sign(self):
        telegram_url = self.ns["telegram_url"]

        self.assertEqual(
            telegram_url("@myshop"),
            "https://t.me/myshop",
        )
        self.assertEqual(
            telegram_url("myshop"),
            "https://t.me/myshop",
        )

    def test_telegram_url_accepts_existing_url(self):
        telegram_url = self.ns["telegram_url"]

        self.assertEqual(
            telegram_url(
                "https://t.me/myshop"
            ),
            "https://t.me/myshop",
        )

    def test_telegram_url_none_or_empty(self):
        telegram_url = self.ns["telegram_url"]

        self.assertIsNone(
            telegram_url(None)
        )
        self.assertIsNone(
            telegram_url("")
        )
        self.assertIsNone(
            telegram_url("   ")
        )

    def test_telegram_url_rejects_unsafe_input(self):
        telegram_url = self.ns["telegram_url"]

        self.assertIsNone(
            telegram_url("my shop")
        )
        self.assertIsNone(
            telegram_url("my/shop")
        )
        self.assertIsNone(
            telegram_url("my<script>")
        )

    def test_website_url_adds_https_when_missing(self):
        website_url = self.ns["website_url"]

        self.assertEqual(
            website_url("example.com"),
            "https://example.com",
        )

    def test_website_url_preserves_existing_scheme(self):
        website_url = self.ns["website_url"]

        self.assertEqual(
            website_url("http://example.com"),
            "http://example.com",
        )
        self.assertEqual(
            website_url("https://example.com"),
            "https://example.com",
        )

    def test_website_url_none_or_empty(self):
        website_url = self.ns["website_url"]

        self.assertIsNone(
            website_url(None)
        )
        self.assertIsNone(
            website_url("")
        )
        self.assertIsNone(
            website_url("   ")
        )

    def test_website_url_rejects_dangerous_scheme(self):
        website_url = self.ns["website_url"]

        self.assertIsNone(
            website_url("javascript:alert(1)")
        )
        self.assertIsNone(
            website_url("data:text/html,test")
        )
        self.assertIsNone(
            website_url("file:///tmp/test")
        )

    def test_website_url_rejects_credentials(self):
        website_url = self.ns["website_url"]

        self.assertIsNone(
            website_url("https://user:pass@example.com")
        )

    def test_website_url_rejects_invalid_host(self):
        website_url = self.ns["website_url"]

        self.assertIsNone(
            website_url("https://")
        )
        self.assertIsNone(
            website_url("https://example..com")
        )

    def test_whatsapp_url_from_phone_number(self):
        whatsapp_url = self.ns["whatsapp_url"]

        self.assertEqual(
            whatsapp_url("+989121234567"),
            "https://wa.me/989121234567",
        )

    def test_whatsapp_url_normalizes_zero_zero_prefix(self):
        whatsapp_url = self.ns["whatsapp_url"]

        self.assertEqual(
            whatsapp_url("00989121234567"),
            "https://wa.me/989121234567",
        )

    def test_whatsapp_url_accepts_existing_http_url(self):
        whatsapp_url = self.ns["whatsapp_url"]

        self.assertEqual(
            whatsapp_url("https://wa.me/989121234567"),
            "https://wa.me/989121234567",
        )

    def test_whatsapp_url_rejects_invalid_phone(self):
        whatsapp_url = self.ns["whatsapp_url"]

        self.assertIsNone(
            whatsapp_url("123")
        )
        self.assertIsNone(
            whatsapp_url("not-a-phone")
        )

    def test_whatsapp_url_none_or_empty(self):
        whatsapp_url = self.ns["whatsapp_url"]

        self.assertIsNone(
            whatsapp_url(None)
        )
        self.assertIsNone(
            whatsapp_url("")
        )
        self.assertIsNone(
            whatsapp_url("   ")
        )

    def test_now_iso_returns_parseable_timestamp(self):
        now_iso = self.ns["now_iso"]

        value = now_iso()

        datetime.datetime.fromisoformat(value)


if __name__ == "__main__":
    unittest.main()