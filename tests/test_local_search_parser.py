# -*- coding: utf-8 -*-
"""
Tests for the current Worker-side local search parser.

The tests target src/worker/search.py directly.
"""

import unittest

from worker.search import (
    LocalQueryParser,
    StructuredQuery,
    _convert_number_unit,
    _extract_price,
    _remove_stopwords,
    normalize_persian_text,
)


class NormalizationTests(unittest.TestCase):
    def test_persian_digits_are_converted(self):
        text = normalize_persian_text("۳۰۰۰۰۰۰")

        self.assertIn(
            "3000000",
            text,
        )

    def test_arabic_digits_are_converted(self):
        text = normalize_persian_text("١٢٣")

        self.assertIn(
            "123",
            text,
        )

    def test_arabic_letter_variants_are_unified(self):
        self.assertEqual(
            normalize_persian_text("كتاب"),
            normalize_persian_text("کتاب"),
        )

        self.assertIn(
            "ی",
            normalize_persian_text("علي"),
        )

    def test_zwnj_is_normalized(self):
        self.assertEqual(
            normalize_persian_text("می‌خوام"),
            normalize_persian_text("می خوام"),
        )

    def test_punctuation_is_removed(self):
        text = normalize_persian_text("کفش داری؟!")

        self.assertNotIn("؟", text)
        self.assertNotIn("!", text)

    def test_whitespace_is_collapsed(self):
        self.assertEqual(
            normalize_persian_text("کفش    سفید"),
            "کفش سفید",
        )


class PriceExtractionTests(unittest.TestCase):
    def test_million_price(self):
        result = _extract_price("کفش زیر 3 میلیون")

        self.assertIsNotNone(result)

    def test_billion_price(self):
        result = _extract_price("خانه تا 2 میلیارد")

        self.assertIsNotNone(result)

    def test_price_range(self):
        result = _extract_price(
            "بین 2 میلیون تا 5 میلیون"
        )

        self.assertIsNotNone(result)

    def test_number_unit_conversion(self):
        self.assertEqual(
            _convert_number_unit(
                3,
                "میلیون",
            ),
            3_000_000,
        )

    def test_plain_number(self):
        result = _convert_number_unit(
            500,
            None,
        )

        self.assertEqual(
            result,
            500,
        )


class StopwordTests(unittest.TestCase):
    def test_common_stopwords_are_removed(self):
        result = _remove_stopwords(
            "من یک کفش سفید میخوام"
        )

        self.assertNotIn(
            "یک",
            result,
        )

    def test_meaningful_keyword_is_preserved(self):
        result = _remove_stopwords(
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


class StructuredQueryTests(unittest.TestCase):
    def test_default_query_has_no_extracted_fields(self):
        query = StructuredQuery(
            raw_query="سلام"
        )

        self.assertFalse(
            query.has_any_extracted_field()
        )

    def test_query_can_hold_search_fields(self):
        query = StructuredQuery(
            raw_query="کفش سفید مردانه تهران",
            keyword="کفش",
            gender="مردانه",
            color="سفید",
            city="تهران",
            max_price=3_000_000,
        )

        self.assertEqual(
            query.keyword,
            "کفش",
        )
        self.assertEqual(
            query.gender,
            "مردانه",
        )
        self.assertEqual(
            query.color,
            "سفید",
        )
        self.assertEqual(
            query.city,
            "تهران",
        )
        self.assertEqual(
            query.max_price,
            3_000_000,
        )

        self.assertTrue(
            query.has_any_extracted_field()
        )


class LocalQueryParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = LocalQueryParser()

    def test_parser_returns_structured_query(self):
        result = self.parser.parse(
            "کفش سفید مردانه زیر 3 میلیون تهران"
        )

        self.assertIsInstance(
            result,
            StructuredQuery,
        )

    def test_parser_preserves_raw_query(self):
        raw = "کفش سفید تهران"

        result = self.parser.parse(raw)

        self.assertEqual(
            result.raw_query,
            raw,
        )

    def test_parser_handles_empty_query(self):
        result = self.parser.parse("")

        self.assertIsInstance(
            result,
            StructuredQuery,
        )


if __name__ == "__main__":
    unittest.main()