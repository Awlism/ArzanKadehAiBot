# -*- coding: utf-8 -*-
"""Focused safety tests for seller contact URL builders."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SELLER_PATH = (
    PROJECT_ROOT
    / "src"
    / "worker"
    / "seller.py"
)

# Load the real source file independently of test modules that may
# install a stub named worker.seller.
SPEC = importlib.util.spec_from_file_location(
    "worker_seller_url_tests_subject",
    SELLER_PATH,
)

if SPEC is None or SPEC.loader is None:
    raise RuntimeError(
        f"Cannot load seller module from {SELLER_PATH}"
    )

SELLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SELLER)

_whatsapp_url = SELLER._whatsapp_url


class WhatsAppUrlSafetyTests(unittest.TestCase):
    def test_international_phone_becomes_wa_me_link(self):
        self.assertEqual(
            _whatsapp_url("+98 912 345 6789"),
            "https://wa.me/989123456789",
        )

    def test_formatted_phone_becomes_wa_me_link(self):
        self.assertEqual(
            _whatsapp_url("(0912) 345-6789"),
            "https://wa.me/09123456789",
        )

    def test_valid_wa_me_link_is_accepted(self):
        url = "https://wa.me/989123456789"

        self.assertEqual(
            _whatsapp_url(url),
            url,
        )

    def test_valid_api_whatsapp_link_is_accepted(self):
        url = (
            "https://api.whatsapp.com/send"
            "?phone=989123456789&text=hello"
        )

        self.assertEqual(
            _whatsapp_url(url),
            url,
        )

    def test_api_link_with_text_parameter_is_accepted(self):
        url = (
            "https://api.whatsapp.com/send"
            "?phone=989123456789&text=Hello%20World"
        )

        self.assertEqual(
            _whatsapp_url(url),
            url,
        )

    def test_non_whatsapp_website_is_rejected(self):
        self.assertIsNone(
            _whatsapp_url("https://example.com/redirect")
        )

    def test_lookalike_whatsapp_domains_are_rejected(self):
        for value in (
            "https://wa.me.evil.example/989123456789",
            "https://evilwa.me/989123456789",
            "https://api.whatsapp.com.evil.example/send?phone=989123456789",
        ):
            with self.subTest(value=value):
                self.assertIsNone(_whatsapp_url(value))

    def test_http_whatsapp_link_is_rejected(self):
        self.assertIsNone(
            _whatsapp_url("http://wa.me/989123456789")
        )

    def test_credentials_in_url_are_rejected(self):
        for value in (
            "https://attacker.example@wa.me/989123456789",
            "https://user:pass@api.whatsapp.com/send?phone=989123456789",
        ):
            with self.subTest(value=value):
                self.assertIsNone(_whatsapp_url(value))

    def test_nonstandard_ports_are_rejected(self):
        for value in (
            "https://wa.me:8443/989123456789",
            "https://api.whatsapp.com:8443/send?phone=989123456789",
        ):
            with self.subTest(value=value):
                self.assertIsNone(_whatsapp_url(value))

    def test_invalid_api_paths_are_rejected(self):
        for value in (
            "https://api.whatsapp.com/redirect?phone=989123456789",
            "https://api.whatsapp.com/send/",
            "https://api.whatsapp.com/",
        ):
            with self.subTest(value=value):
                self.assertIsNone(_whatsapp_url(value))

    def test_wa_me_query_and_fragment_are_rejected(self):
        for value in (
            "https://wa.me/989123456789?text=hello",
            "https://wa.me/989123456789#section",
        ):
            with self.subTest(value=value):
                self.assertIsNone(_whatsapp_url(value))

    def test_api_link_without_phone_is_rejected(self):
        self.assertIsNone(
            _whatsapp_url("https://api.whatsapp.com/send?text=hello")
        )

    def test_api_link_with_duplicate_phone_parameters_is_rejected(self):
        value = (
            "https://api.whatsapp.com/send"
            "?phone=989123456789&phone=1234567"
        )

        self.assertIsNone(_whatsapp_url(value))

    def test_api_link_with_invalid_phone_is_rejected(self):
        for value in (
            "https://api.whatsapp.com/send?phone=123",
            "https://api.whatsapp.com/send?phone=1234567890123456",
            "https://api.whatsapp.com/send?phone=hello123456",
        ):
            with self.subTest(value=value):
                self.assertIsNone(_whatsapp_url(value))

    def test_non_string_inputs_are_rejected(self):
        for value in (
            None,
            989123456789,
            9.12,
            True,
            False,
            [],
            {},
        ):
            with self.subTest(value=value):
                self.assertIsNone(_whatsapp_url(value))

    def test_empty_and_whitespace_inputs_are_rejected(self):
        for value in (
            "",
            " ",
            "\t",
            "\n",
        ):
            with self.subTest(value=value):
                self.assertIsNone(_whatsapp_url(value))

    def test_invalid_phone_values_are_rejected(self):
        for value in (
            "hello12345678",
            "123",
            "+",
            "https://example.com",
            "۰۹۱۲۳۴۵۶۷۸۹",
            "٠٩١٢٣٤٥٦٧٨٩",
            "0912\n3456789",
            "0912\t3456789",
            "0912\x003456789",
        ):
            with self.subTest(value=value):
                self.assertIsNone(_whatsapp_url(value))

    def test_phone_length_boundaries_are_enforced(self):
        self.assertEqual(
            _whatsapp_url("1234567"),
            "https://wa.me/1234567",
        )

        self.assertEqual(
            _whatsapp_url("123456789012345"),
            "https://wa.me/123456789012345",
        )

        for value in (
            "123456",
            "1234567890123456",
        ):
            with self.subTest(value=value):
                self.assertIsNone(_whatsapp_url(value))


if __name__ == "__main__":
    unittest.main()