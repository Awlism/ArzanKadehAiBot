# -*- coding: utf-8 -*-
"""
Worker search-engine tests.

These tests validate the current src/worker/search.py implementation
without importing the legacy bot package.
"""

import inspect
import unittest

from worker.search import (
    LocalQueryParser,
    StructuredQuery,
    _convert_number_unit,
    _extract_price,
    _remove_stopwords,
    normalize_persian_text,
)


class SearchWorkerStructureTests(unittest.TestCase):
    def test_search_module_is_worker_module(self):
        module = inspect.getmodule(LocalQueryParser)

        self.assertIsNotNone(module)
        self.assertEqual(
            module.__name__,
            "worker.search",
        )

    def test_search_module_exposes_current_parser(self):
        parser = LocalQueryParser()

        self.assertIsInstance(
            parser,
            LocalQueryParser,
        )

    def test_structured_query_is_current_worker_type(self):
        query = StructuredQuery(
            raw_query="کفش"
        )

        self.assertEqual(
            type(query).__module__,
            "worker.search",
        )


class SearchNormalizationTests(unittest.TestCase):
    def test_persian_numbers(self):
        self.assertEqual(
            normalize_persian_text("۱۲۳۴۵"),
            "12345",
        )

    def test_arabic_numbers(self):
        self.assertEqual(
            normalize_persian_text("١٢٣٤٥"),
            "12345",
        )

    def test_persian_arabic_letter_normalization(self):
        self.assertEqual(
            normalize_persian_text("ك"),
            normalize_persian_text("ک"),
        )

        self.assertEqual(
            normalize_persian_text("ي"),
            normalize_persian_text("ی"),
        )


class SearchPriceTests(unittest.TestCase):
    def test_million_conversion(self):
        self.assertEqual(
            _convert_number_unit(
                3,
                "میلیون",
            ),
            3_000_000,
        )

    def test_billion_conversion(self):
        self.assertEqual(
            _convert_number_unit(
                2,
                "میلیارد",
            ),
            2_000_000_000,
        )

    def test_price_extraction_returns_value(self):
        result = _extract_price(
            "کفش زیر 3 میلیون"
        )

        self.assertIsNotNone(result)

    def test_price_extraction_handles_range(self):
        result = _extract_price(
            "بین 2 میلیون تا 5 میلیون"
        )

        self.assertIsNotNone(result)


class SearchKeywordTests(unittest.TestCase):
    def test_stopwords_do_not_remove_main_keyword(self):
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

    def test_normalization_is_stable(self):
        first = normalize_persian_text(
            "کفش سفید تهران"
        )

        second = normalize_persian_text(
            first
        )

        self.assertEqual(
            first,
            second,
        )


class SearchQueryTests(unittest.TestCase):
    def test_structured_query_can_represent_complex_request(self):
        query = StructuredQuery(
            raw_query=(
                "یه کفش سفید مردونه زیر "
                "3 میلیون تو تهران میخوام"
            ),
            keyword="کفش",
            gender="مردانه",
            color="سفید",
            max_price=3_000_000,
            city="تهران",
        )

        self.assertTrue(
            query.has_any_extracted_field()
        )

        self.assertEqual(
            query.max_price,
            3_000_000,
        )

    def test_empty_query_has_no_extracted_signal(self):
        query = StructuredQuery(
            raw_query=""
        )

        self.assertFalse(
            query.has_any_extracted_field()
        )


if __name__ == "__main__":
    unittest.main()