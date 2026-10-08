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


class FakeSearchDB:
    """Minimal async DB double required by LocalQueryParser."""

    def __init__(self, cities=None, categories=None):
        self.cities = cities or []
        self.categories = categories or []

    async def fetchall(self, sql, params=None):
        normalized = " ".join(
            str(sql).lower().split()
        )

        if "from cities" in normalized:
            return [
                {"name": name}
                for name in self.cities
            ]

        if "from categories" in normalized:
            return [
                {"name": name}
                for name in self.categories
            ]

        return []


class NormalizationTests(unittest.TestCase):
    def test_persian_digits_are_converted(self):
        text = normalize_persian_text("۳۰۰۰۰۰۰")

        self.assertEqual(
            text,
            "3000000",
        )

    def test_arabic_digits_are_converted(self):
        text = normalize_persian_text("١٢٣")

        self.assertEqual(
            text,
            "123",
        )

    def test_arabic_letter_variants_are_unified(self):
        self.assertEqual(
            normalize_persian_text("كتاب"),
            normalize_persian_text("کتاب"),
        )

        self.assertEqual(
            normalize_persian_text("علي"),
            normalize_persian_text("علی"),
        )

    def test_zwnj_is_normalized(self):
        self.assertEqual(
            normalize_persian_text("می‌خوام"),
            normalize_persian_text("می خوام"),
        )

    def test_punctuation_is_removed(self):
        text = normalize_persian_text("کفش داری؟!")

        self.assertNotIn(
            "؟",
            text,
        )

        self.assertNotIn(
            "!",
            text,
        )

    def test_whitespace_is_collapsed(self):
        self.assertEqual(
            normalize_persian_text(
                "کفش    سفید"
            ),
            "کفش سفید",
        )


class PriceExtractionTests(unittest.TestCase):
    def test_million_price(self):
        minimum, maximum, text = _extract_price(
            "کفش زیر 3 میلیون"
        )

        self.assertIsNone(
            minimum
        )

        self.assertIsNotNone(
            maximum
        )

        self.assertEqual(
            maximum,
            3_000_000,
        )

        self.assertIsInstance(
            text,
            str,
        )

    def test_billion_price(self):
        minimum, maximum, text = _extract_price(
            "خانه تا 2 میلیارد"
        )

        self.assertIsNone(
            minimum
        )

        self.assertEqual(
            maximum,
            2_000_000_000,
        )

        self.assertIsInstance(
            text,
            str,
        )

    def test_price_range(self):
        minimum, maximum, text = _extract_price(
            "بین 2 میلیون تا 5 میلیون"
        )

        self.assertEqual(
            minimum,
            2_000_000,
        )

        self.assertEqual(
            maximum,
            5_000_000,
        )

        self.assertIsInstance(
            text,
            str,
        )

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
            result.split(),
        )

    def test_meaningful_keywords_are_preserved(self):
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


class LocalQueryParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_parser_returns_structured_query(self):
        db = FakeSearchDB(
            cities=["تهران"],
            categories=[],
        )

        parser = LocalQueryParser()

        result = await parser.parse(
            db,
            "کفش سفید مردانه زیر 3 میلیون تهران",
        )

        self.assertIsInstance(
            result,
            StructuredQuery,
        )

    async def test_parser_preserves_raw_query(self):
        raw = "کفش سفید تهران"

        db = FakeSearchDB(
            cities=["تهران"],
            categories=[],
        )

        parser = LocalQueryParser()

        result = await parser.parse(
            db,
            raw,
        )

        self.assertEqual(
            result.raw_query,
            raw,
        )

    async def test_parser_extracts_city(self):
        db = FakeSearchDB(
            cities=["تهران"],
            categories=[],
        )

        parser = LocalQueryParser()

        result = await parser.parse(
            db,
            "کفش سفید تهران",
        )

        self.assertEqual(
            result.city,
            "تهران",
        )

    async def test_parser_extracts_price(self):
        db = FakeSearchDB(
            cities=[],
            categories=[],
        )

        parser = LocalQueryParser()

        result = await parser.parse(
            db,
            "کفش زیر 3 میلیون",
        )

        self.assertEqual(
            result.max_price,
            3_000_000,
        )

    async def test_parser_handles_empty_query(self):
        db = FakeSearchDB()

        parser = LocalQueryParser()

        result = await parser.parse(
            db,
            "",
        )

        self.assertIsInstance(
            result,
            StructuredQuery,
        )


if __name__ == "__main__":
    unittest.main()