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
        self.assertEqual(
            phone_number("1234567"),
            "1234567",
        )

    def test_valid_fifteen_digit_number_is_accepted(self):
        self.assertEqual(
            phone_number("123456789012345"),
            "123456789012345",
        )

    def test_non_string_inputs_are_rejected(self):
        for value in (
            None,
            9123456789,
            9.123456789,
            True,
            False,
            [],
            {},
        ):
            with self.subTest(value=value):
                self.assertIsNone(phone_number(value))

    def test_empty_and_whitespace_inputs_are_rejected(self):
        for value in (
            "",
            " ",
            "\t",
            "\n",
        ):
            with self.subTest(value=value):
                self.assertIsNone(phone_number(value))

    def test_numbers_shorter_than_seven_digits_are_rejected(self):
        self.assertIsNone(phone_number("123456"))

    def test_numbers_longer_than_fifteen_digits_are_rejected(self):
        self.assertIsNone(phone_number("1234567890123456"))

    def test_letters_and_urls_are_rejected(self):
        for value in (
            "hello12345678",
            "https://example.com",
            "0912abc3456",
        ):
            with self.subTest(value=value):
                self.assertIsNone(phone_number(value))

    def test_plus_sign_is_only_allowed_at_the_start(self):
        for value in (
            "+",
            "++989123456789",
            "989+123456789",
        ):
            with self.subTest(value=value):
                self.assertIsNone(phone_number(value))

    def test_non_latin_digits_are_rejected(self):
        for value in (
            "۰۹۱۲۳۴۵۶۷۸۹",
            "٠٩١٢٣٤٥٦٧٨٩",
        ):
            with self.subTest(value=value):
                self.assertIsNone(phone_number(value))

    def test_control_characters_are_rejected(self):
        for value in (
            "0912\n3456789",
            "0912\t3456789",
            "0912\x003456789",
        ):
            with self.subTest(value=value):
                self.assertIsNone(phone_number(value))


if __name__ == "__main__":
    unittest.main()