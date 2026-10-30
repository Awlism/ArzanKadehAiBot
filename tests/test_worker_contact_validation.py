# -*- coding: utf-8 -*-
"""Focused tests for seller contact validation."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALIDATION_PATH = (
    PROJECT_ROOT
    / "src"
    / "worker"
    / "contact_validation.py"
)

SPEC = importlib.util.spec_from_file_location(
    "worker_contact_validation_tests_subject",
    VALIDATION_PATH,
)

if SPEC is None or SPEC.loader is None:
    raise RuntimeError(
        f"Cannot load validation module from {VALIDATION_PATH}"
    )

VALIDATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATION)

phone_number = VALIDATION.phone_number
instagram_url = VALIDATION.instagram_url
telegram_url = VALIDATION.telegram_url
website_url = VALIDATION.website_url
whatsapp_url = VALIDATION.whatsapp_url


class PhoneNumberValidationTests(unittest.TestCase):
    def test_international_number_is_normalized(self):
        self.assertEqual(
            phone_number("+98 912 345 6789"),
            "+989123456789",
        )

    def test_formatted_local_number_is_normalized(self):
        self.assertEqual(
            phone_number("(0912) 345-6789"),
            "09123456789",
        )

    def test_spaces_and_punctuation_are_removed(self):
        self.assertEqual(
            phone_number("0912.345.6789"),
            "09123456789",
        )

    def test_valid_seven_digit_number_is_accepted(self):
        self.assertEqual(phone_number("1234567"), "1234567")

    def test_valid_fifteen_digit_number_is_accepted(self):
        self.assertEqual(
            phone_number("123456789012345"),
            "123456789012345",
        )

    def test_non_string_inputs_are_rejected(self):
        for value in (None, 9123456789, 9.12, True, False, [], {}):
            with self.subTest(value=value):
                self.assertIsNone(phone_number(value))

    def test_empty_inputs_are_rejected(self):
        for value in ("", " ", "\t", "\n"):
            with self.subTest(value=value):
                self.assertIsNone(phone_number(value))

    def test_invalid_lengths_are_rejected(self):
        for value in ("123456", "1234567890123456"):
            with self.subTest(value=value):
                self.assertIsNone(phone_number(value))

    def test_letters_and_urls_are_rejected(self):
        for value in (
            "hello12345678",
            "https://example.com",
            "0912abc3456",
        ):
            with self.subTest(value=value):
                self.assertIsNone(phone_number(value))

    def test_plus_sign_must_only_appear_at_start(self):
        for value in ("+", "++989123456789", "989+123456789"):
            with self.subTest(value=value):
                self.assertIsNone(phone_number(value))

    def test_non_latin_digits_are_rejected(self):
        for value in ("۰۹۱۲۳۴۵۶۷۸۹", "٠٩١٢٣٤٥٦٧٨٩"):
            with self.subTest(value=value):
                self.assertIsNone(phone_number(value))

    def test_control_characters_are_rejected(self):
        for value in ("0912\n3456789", "0912\t3456789", "0912\x003456789"):
            with self.subTest(value=value):
                self.assertIsNone(phone_number(value))


class InstagramUrlValidationTests(unittest.TestCase):
    def test_username_is_normalized(self):
        self.assertEqual(
            instagram_url("@my_shop.official"),
            "https://instagram.com/my_shop.official",
        )

    def test_valid_profile_urls_are_accepted(self):
        for value in (
            "https://instagram.com/myshop",
            "https://www.instagram.com/myshop",
            "http://instagram.com/myshop",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    instagram_url(value),
                    "https://instagram.com/myshop",
                )

    def test_invalid_domains_are_rejected(self):
        for value in (
            "https://instagram.com.evil.example/myshop",
            "https://evilinstagram.com/myshop",
            "https://attacker.example@instagram.com/myshop",
        ):
            with self.subTest(value=value):
                self.assertIsNone(instagram_url(value))

    def test_query_and_fragment_are_rejected(self):
        for value in (
            "https://instagram.com/myshop?next=evil",
            "https://instagram.com/myshop#section",
        ):
            with self.subTest(value=value):
                self.assertIsNone(instagram_url(value))

    def test_extra_path_segments_are_rejected(self):
        self.assertIsNone(
            instagram_url("https://instagram.com/myshop/posts")
        )

    def test_invalid_usernames_are_rejected(self):
        for value in (
            None,
            123456,
            "",
            "@@myshop",
            ".myshop",
            "myshop.",
            "my..shop",
            "a" * 31,
            "my shop",
        ):
            with self.subTest(value=value):
                self.assertIsNone(instagram_url(value))


class TelegramUrlValidationTests(unittest.TestCase):
    def test_username_is_normalized(self):
        self.assertEqual(
            telegram_url("@MyShop123"),
            "https://t.me/MyShop123",
        )

    def test_valid_profile_urls_are_accepted(self):
        for value in (
            "https://t.me/MyShop123",
            "https://www.t.me/MyShop123",
            "http://t.me/MyShop123",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    telegram_url(value),
                    "https://t.me/MyShop123",
                )

    def test_invalid_domains_are_rejected(self):
        for value in (
            "https://t.me.evil.example/MyShop123",
            "https://evilt.me/MyShop123",
            "https://attacker.example@t.me/MyShop123",
        ):
            with self.subTest(value=value):
                self.assertIsNone(telegram_url(value))

    def test_query_and_fragment_are_rejected(self):
        for value in (
            "https://t.me/MyShop123?start=payload",
            "https://t.me/MyShop123#section",
        ):
            with self.subTest(value=value):
                self.assertIsNone(telegram_url(value))

    def test_extra_path_segments_are_rejected(self):
        self.assertIsNone(
            telegram_url("https://t.me/MyShop123/extra")
        )

    def test_invalid_usernames_are_rejected(self):
        for value in (
            None,
            123456,
            "",
            "@@MyShop123",
            "abc",
            "1MyShop123",
            "MyShop123_",
            "My Shop",
            "a" * 33,
        ):
            with self.subTest(value=value):
                self.assertIsNone(telegram_url(value))


class WebsiteUrlValidationTests(unittest.TestCase):
    def test_domain_gets_https_scheme(self):
        self.assertEqual(
            website_url("example.com"),
            "https://example.com",
        )

    def test_valid_http_and_https_urls_are_accepted(self):
        for value in (
            "https://example.com",
            "http://example.com/path",
            "https://sub.example.co.uk/path?q=1",
            "https://example.com:8443/path",
        ):
            with self.subTest(value=value):
                self.assertEqual(website_url(value), value)

    def test_valid_ip_addresses_are_accepted(self):
        for value in (
            "https://192.0.2.1",
            "https://[2001:db8::1]",
        ):
            with self.subTest(value=value):
                self.assertEqual(website_url(value), value)

    def test_invalid_schemes_are_rejected(self):
        for value in (
            "ftp://example.com",
            "javascript://example.com",
            "file://example.com",
        ):
            with self.subTest(value=value):
                self.assertIsNone(website_url(value))

    def test_credentials_are_rejected(self):
        self.assertIsNone(
            website_url("https://user:pass@example.com")
        )

    def test_invalid_ports_are_rejected(self):
        for value in (
            "https://example.com:0",
            "https://example.com:65536",
            "https://example.com:abc",
        ):
            with self.subTest(value=value):
                self.assertIsNone(website_url(value))

    def test_invalid_hostnames_are_rejected(self):
        for value in (
            "localhost",
            "example",
            "-example.com",
            "example-.com",
            "exa_mple.com",
            "example..com",
            "example.123",
            "https://example.com..",
        ):
            with self.subTest(value=value):
                self.assertIsNone(website_url(value))

    def test_whitespace_and_unsafe_characters_are_rejected(self):
        for value in (
            "example .com",
            "https://example.com/path with space",
            'https://example.com/"quoted"',
            "https://example.com/<script>",
        ):
            with self.subTest(value=value):
                self.assertIsNone(website_url(value))

    def test_non_string_inputs_are_rejected(self):
        for value in (None, 123, True, [], {}):
            with self.subTest(value=value):
                self.assertIsNone(website_url(value))


class WhatsAppUrlValidationTests(unittest.TestCase):
    def test_international_phone_becomes_wa_me_link(self):
        self.assertEqual(
            whatsapp_url("+98 912 345 6789"),
            "https://wa.me/989123456789",
        )

    def test_formatted_phone_becomes_wa_me_link(self):
        self.assertEqual(
            whatsapp_url("(0912) 345-6789"),
            "https://wa.me/09123456789",
        )

    def test_valid_wa_me_link_is_accepted(self):
        url = "https://wa.me/989123456789"
        self.assertEqual(whatsapp_url(url), url)

    def test_valid_api_whatsapp_link_is_accepted(self):
        url = (
            "https://api.whatsapp.com/send"
            "?phone=989123456789&text=hello"
        )
        self.assertEqual(whatsapp_url(url), url)

    def test_non_whatsapp_domains_are_rejected(self):
        for value in (
            "https://example.com/redirect",
            "https://wa.me.evil.example/989123456789",
            "https://evilwa.me/989123456789",
        ):
            with self.subTest(value=value):
                self.assertIsNone(whatsapp_url(value))

    def test_http_links_are_rejected(self):
        self.assertIsNone(
            whatsapp_url("http://wa.me/989123456789")
        )

    def test_credentials_and_ports_are_rejected(self):
        for value in (
            "https://attacker.example@wa.me/989123456789",
            "https://wa.me:8443/989123456789",
        ):
            with self.subTest(value=value):
                self.assertIsNone(whatsapp_url(value))

    def test_invalid_api_paths_and_phone_parameters_are_rejected(self):
        for value in (
            "https://api.whatsapp.com/redirect?phone=989123456789",
            "https://api.whatsapp.com/send",
            "https://api.whatsapp.com/send?phone=123",
            "https://api.whatsapp.com/send?phone=989123456789&phone=1234567",
        ):
            with self.subTest(value=value):
                self.assertIsNone(whatsapp_url(value))

    def test_wa_me_query_and_fragment_are_rejected(self):
        for value in (
            "https://wa.me/989123456789?text=hello",
            "https://wa.me/989123456789#section",
        ):
            with self.subTest(value=value):
                self.assertIsNone(whatsapp_url(value))

    def test_non_string_and_invalid_phone_inputs_are_rejected(self):
        for value in (
            None,
            989123456789,
            "",
            "hello12345678",
            "123",
            "+",
            "https://example.com",
            "۰۹۱۲۳۴۵۶۷۸۹",
        ):
            with self.subTest(value=value):
                self.assertIsNone(whatsapp_url(value))


if __name__ == "__main__":
    unittest.main()