# -*- coding: utf-8 -*-
"""
Tests the small pure-Python helper functions in bot.py directly (parse_int,
format_price, status_badge, instagram_url, telegram_url, website_url,
now_iso). These don't touch Telegram or the database, so they're extracted
via ast (see _extract.py) and exercised without needing aiogram/aiosqlite.
"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from _extract import extract_names  # noqa: E402

NAMES = [
    "EMOJI_CLAIMED",
    "EMOJI_UNCLAIMED",
    "parse_int",
    "format_price",
    "status_badge",
    "instagram_url",
    "telegram_url",
    "website_url",
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
        self.assertEqual(format_price(None), "نامشخص")

    def test_format_price_numeric(self):
        format_price = self.ns["format_price"]
        self.assertEqual(format_price(150000), "150,000 تومان")
        self.assertEqual(format_price(0), "0 تومان")

    def test_status_badge_claimed(self):
        status_badge = self.ns["status_badge"]
        self.assertIn("تأییدشده", status_badge("CLAIMED"))
        self.assertTrue(status_badge("CLAIMED").startswith(self.ns["EMOJI_CLAIMED"]))

    def test_status_badge_unclaimed_and_unknown_defaults_to_unclaimed(self):
        status_badge = self.ns["status_badge"]
        self.assertIn("معرفی‌شده", status_badge("UNCLAIMED"))
        # Anything other than exactly "CLAIMED" must safely fall back,
        # never claim an unverified seller is verified.
        self.assertIn("معرفی‌شده", status_badge("SOMETHING_ELSE"))

    def test_instagram_url_strips_at_sign(self):
        instagram_url = self.ns["instagram_url"]
        self.assertEqual(instagram_url("@shopname"), "https://instagram.com/shopname")
        self.assertEqual(instagram_url("shopname"), "https://instagram.com/shopname")

    def test_instagram_url_none_or_empty(self):
        instagram_url = self.ns["instagram_url"]
        self.assertIsNone(instagram_url(None))
        self.assertIsNone(instagram_url(""))
        self.assertIsNone(instagram_url("   "))

    def test_telegram_url_strips_at_sign(self):
        telegram_url = self.ns["telegram_url"]
        self.assertEqual(telegram_url("@myshop"), "https://t.me/myshop")
        self.assertEqual(telegram_url("myshop"), "https://t.me/myshop")

    def test_website_url_adds_https_when_missing(self):
        website_url = self.ns["website_url"]
        self.assertEqual(website_url("example.com"), "https://example.com")

    def test_website_url_preserves_existing_scheme(self):
        website_url = self.ns["website_url"]
        self.assertEqual(website_url("http://example.com"), "http://example.com")
        self.assertEqual(website_url("https://example.com"), "https://example.com")

    def test_website_url_none_or_empty(self):
        website_url = self.ns["website_url"]
        self.assertIsNone(website_url(None))
        self.assertIsNone(website_url(""))

    def test_now_iso_returns_parseable_timestamp(self):
        now_iso = self.ns["now_iso"]
        value = now_iso()
        # Must not raise
        datetime.datetime.fromisoformat(value)


if __name__ == "__main__":
    unittest.main()
