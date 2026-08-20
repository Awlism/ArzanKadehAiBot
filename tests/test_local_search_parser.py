# -*- coding: utf-8 -*-
"""
Tests LocalQueryParser (100% local, no network/API) directly. These are
pure-function tests -- no database, no aiogram, no aiosqlite needed.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from _extract import extract_names  # noqa: E402

NAMES = [
    "CITY_NAMES", "CATEGORY_TREE",
    "StructuredQuery", "QueryParser", "LocalQueryParser",
    "normalize_persian_text", "_extract_price", "_convert_number_unit",
    "ALT_CITY_SPELLINGS", "CATEGORY_SYNONYMS", "REFERRAL_DEEP_LINK_RE",
    "_DIGIT_LETTER_MAP", "_PERSIAN_DIGITS", "_ARABIC_DIGITS", "_ASCII_DIGITS",
    "_PUNCTUATION_CHARS", "_GENDER_WORD_MAP", "_COLOR_WORDS", "_STOPWORDS",
    "_NORMALIZED_CITY_NAMES", "_ALL_CATEGORY_NAMES", "_SORTED_CATEGORY_NAMES",
    "_NORMALIZED_COLOR_WORDS", "_NORMALIZED_STOPWORDS",
    "_STOPWORD_PHRASES", "_STOPWORD_TOKENS", "_remove_stopwords",
    "_PRICE_UNIT_RE", "_PRICE_RANGE_RE", "_PRICE_MAX_RE", "_PRICE_MIN_RE",
]


class NormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES)

    def test_persian_digits_are_converted_to_ascii(self):
        normalize = self.ns["normalize_persian_text"]
        self.assertIn("3000000", normalize("۳۰۰۰۰۰۰"))

    def test_arabic_digits_are_converted_to_ascii(self):
        normalize = self.ns["normalize_persian_text"]
        self.assertIn("123", normalize("١٢٣"))

    def test_arabic_letter_variants_are_unified(self):
        normalize = self.ns["normalize_persian_text"]
        # ي (Arabic yeh) -> ی (Persian yeh), ك (Arabic kaf) -> ک (Persian kaf)
        self.assertEqual(normalize("كتاب"), normalize("کتاب"))
        self.assertIn("ی", normalize("علي"))

    def test_zwnj_is_treated_as_a_space(self):
        normalize = self.ns["normalize_persian_text"]
        self.assertEqual(normalize("می\u200cخوام"), normalize("می خوام"))

    def test_punctuation_is_stripped(self):
        normalize = self.ns["normalize_persian_text"]
        self.assertNotIn("؟", normalize("کفش داری؟"))
        self.assertNotIn("!", normalize("سلام!"))

    def test_whitespace_is_collapsed(self):
        normalize = self.ns["normalize_persian_text"]
        self.assertEqual(normalize("کفش    سفید"), "کفش سفید")


class PriceExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES)

    def test_convert_number_unit_million(self):
        convert = self.ns["_convert_number_unit"]
        self.assertEqual(convert("3", "میلیون"), 3_000_000)

    def test_convert_number_unit_thousand(self):
        convert = self.ns["_convert_number_unit"]
        self.assertEqual(convert("500", "هزار"), 500_000)

    def test_convert_number_unit_plain(self):
        convert = self.ns["_convert_number_unit"]
        self.assertEqual(convert("150000", None), 150_000)

    def test_extract_price_zir_gives_max_price(self):
        extract_price = self.ns["_extract_price"]
        min_p, max_p, remaining = extract_price("کفش سفید زیر 3 میلیون تهران")
        self.assertIsNone(min_p)
        self.assertEqual(max_p, 3_000_000)
        self.assertNotIn("میلیون", remaining)

    def test_extract_price_balaye_gives_min_price(self):
        extract_price = self.ns["_extract_price"]
        min_p, max_p, remaining = extract_price("کیف بالای 500 هزار")
        self.assertEqual(min_p, 500_000)
        self.assertIsNone(max_p)

    def test_extract_price_range(self):
        extract_price = self.ns["_extract_price"]
        min_p, max_p, remaining = extract_price("گوشی بین 1 میلیون تا 3 میلیون")
        self.assertEqual(min_p, 1_000_000)
        self.assertEqual(max_p, 3_000_000)

    def test_extract_price_none_when_no_price_signal(self):
        extract_price = self.ns["_extract_price"]
        min_p, max_p, remaining = extract_price("کفش سفید مردانه")
        self.assertIsNone(min_p)
        self.assertIsNone(max_p)


class LocalQueryParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES)
        cls.parser = cls.ns["LocalQueryParser"]()

    def test_full_example_query_from_the_spec(self):
        # "یه کفش سفید مردونه زیر ۳ میلیون تو تهران میخوام"
        sq = self.parser.parse("یه کفش سفید مردونه زیر ۳ میلیون تو تهران میخوام")
        self.assertEqual(sq.category, "کفش")
        self.assertEqual(sq.color, "سفید")
        self.assertEqual(sq.gender, "مردانه")  # مردونه -> مردانه (colloquial normalized)
        self.assertEqual(sq.max_price, 3_000_000)
        self.assertEqual(sq.city, "تهران")

    def test_colloquial_city_spelling_is_corrected(self):
        sq = self.parser.parse("کیف زنونه تهرون")
        self.assertEqual(sq.city, "تهران")

    def test_category_synonym_goshi_maps_to_mobile(self):
        sq = self.parser.parse("گوشی سامسونگ ارزون")
        self.assertEqual(sq.category, "موبایل")

    def test_stopwords_are_removed_from_keyword(self):
        sq = self.parser.parse("دنبال یه کیف چرم میگردم لطفا")
        self.assertNotIn("دنبال", sq.keyword or "")
        self.assertNotIn("لطفا", sq.keyword or "")

    def test_gender_word_variants_normalize_to_canonical_form(self):
        self.assertEqual(self.parser.parse("پیراهن زنونه").gender, "زنانه")
        self.assertEqual(self.parser.parse("پیراهن زنانه").gender, "زنانه")
        self.assertEqual(self.parser.parse("کفش بچگانه").gender, "بچگانه")

    def test_simple_query_without_any_signal_becomes_pure_keyword(self):
        sq = self.parser.parse("گردنبند خاص")
        self.assertIsNone(sq.city)
        self.assertIsNone(sq.min_price)
        self.assertIsNone(sq.max_price)
        self.assertIsNone(sq.color)
        self.assertIsNone(sq.gender)
        self.assertIn("خاص", sq.keyword)

    def test_category_word_alone_is_recognized_as_category_not_keyword(self):
        # "کیف چرم" -> "کیف" is a real subcategory name, so the parser
        # should classify it as `category`, leaving "چرم" as the keyword.
        sq = self.parser.parse("کیف چرم")
        self.assertEqual(sq.category, "کیف")
        self.assertEqual(sq.keyword, "چرم")

    def test_empty_query_returns_all_none(self):
        sq = self.parser.parse("")
        self.assertFalse(sq.has_any_extracted_field())

    def test_has_any_extracted_field_true_when_something_found(self):
        sq = self.parser.parse("تهران")
        self.assertTrue(sq.has_any_extracted_field())

    def test_simplified_drops_price_and_city_but_keeps_keyword_and_category(self):
        sq = self.parser.parse("کفش سفید مردونه زیر 3 میلیون تهران")
        simplified = sq.simplified()
        self.assertIsNone(simplified.city)
        self.assertIsNone(simplified.max_price)
        self.assertEqual(simplified.category, sq.category)
        self.assertEqual(simplified.keyword, sq.keyword)

    def test_raw_query_is_always_preserved_verbatim(self):
        original = "یه کفش سفید مردونه زیر ۳ میلیون تو تهران میخوام"
        sq = self.parser.parse(original)
        self.assertEqual(sq.raw_query, original)

    # ------------------------------------------------------------------
    # Regression tests for two real bugs found during code review:
    # ------------------------------------------------------------------
    def test_regression_stopword_removal_does_not_corrupt_words_containing_yek(self):
        """BUG: a naive substring .replace("یک", " ") also mangled any
        word merely CONTAINING "یک", e.g. "نزدیک" (nearby) -> "نزد" and
        "شیک" (stylish) -> "ش". Fixed by switching to word-boundary/
        token-based stopword removal. This must never regress."""
        sq = self.parser.parse("یه مانتو شیک مشکی می‌خوام")
        self.assertIn("شیک", sq.keyword)
        sq2 = self.parser.parse("نزدیک ترین فروشگاه کجاست")
        self.assertIn("نزدیک", sq2.keyword)

    def test_regression_preposition_before_city_is_not_left_as_keyword(self):
        """BUG: "تو تهران" (in Tehran) left a dangling "تو" as a bogus
        keyword after the city word was removed, which then made the
        structured SQL search over-restrictive (name/description LIKE
        '%تو%' matched nothing) and silently fell back to plain search
        even though the city/price/color/gender were all understood."""
        sq = self.parser.parse("یه کفش سفید مردونه زیر 3 میلیون تو تهران میخوام")
        self.assertEqual(sq.city, "تهران")
        self.assertIsNone(sq.keyword)

    def test_regression_bare_keyword_alone_is_not_treated_as_structured(self):
        """BUG: has_any_extracted_field() used to count a bare keyword as
        "structured", routing single-word queries through the narrower
        structured-search SQL (name/description only) instead of the
        broader original plain search (name+description+seller+category).
        A keyword-only result must NOT be treated as structured."""
        sq = self.parser.parse("چرم")
        self.assertEqual(sq.keyword, "چرم")
        self.assertIsNone(sq.category)
        self.assertFalse(sq.has_any_extracted_field())


class ReferralDeepLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES)

    def test_matches_valid_payload(self):
        regex = self.ns["REFERRAL_DEEP_LINK_RE"]
        match = regex.match("shop_123")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "123")

    def test_rejects_garbage_payload(self):
        regex = self.ns["REFERRAL_DEEP_LINK_RE"]
        self.assertIsNone(regex.match("not_a_shop_link"))
        self.assertIsNone(regex.match("shop_"))
        self.assertIsNone(regex.match("shop_abc"))


if __name__ == "__main__":
    unittest.main()
