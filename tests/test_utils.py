# -*- coding: utf-8 -*-
"""
Tests for utility behavior currently owned by Worker modules.

The legacy bot/utils.py is intentionally not imported.
"""

import unittest

from worker.search import normalize_persian_text


class WorkerUtilityTests(unittest.TestCase):
    def test_persian_digit_normalization(self):
        self.assertEqual(
            normalize_persian_text("۱۲۳"),
            "123",
        )

    def test_arabic_digit_normalization(self):
        self.assertEqual(
            normalize_persian_text("١٢٣"),
            "123",
        )

    def test_arabic_kaf_normalization(self):
        self.assertEqual(
            normalize_persian_text("كفش"),
            "کفش",
        )

    def test_arabic_yeh_normalization(self):
        self.assertEqual(
            normalize_persian_text("علي"),
            "علی",
        )

    def test_zwnj_normalization(self):
        self.assertEqual(
            normalize_persian_text("می‌خوام"),
            normalize_persian_text("می خوام"),
        )

    def test_whitespace_normalization(self):
        self.assertEqual(
            normalize_persian_text(
                "  کفش   سفید  "
            ),
            "کفش سفید",
        )

    def test_punctuation_normalization(self):
        result = normalize_persian_text(
            "کفش، سفید؟!"
        )

        self.assertNotIn(
            "؟",
            result,
        )
        self.assertNotIn(
            "!",
            result,
        )

    def test_normalization_does_not_create_fake_content(self):
        result = normalize_persian_text(
            "کفش سفید"
        )

        self.assertIn(
            "کفش",
            result,
        )
        self.assertIn(
            "سفید",
            result,
        )


if __name__ == "__main__":
    unittest.main()