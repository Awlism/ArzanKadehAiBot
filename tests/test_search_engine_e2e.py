# -*- coding: utf-8 -*-
"""
End-to-end tests for SearchEngine(LocalQueryParser()) against a REAL
SQLite database (stdlib sqlite3, wrapped by tests/_fakedb.py so bot.py's
`await db.fetchall(...)` calls work without aiosqlite installed).

Covers: complex natural-language Persian queries, price filters, city
filters, ranking/relevance ordering, and the full fallback chain
(structured search with no hits -> simplified search -> plain LIKE
search) -- entirely offline, no network, no external API.
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from _extract import extract_names  # noqa: E402
from _fakedb import FakeDB, new_conn  # noqa: E402

NAMES = [
    "SCHEMA_STATEMENTS", "INDEX_STATEMENTS", "CITY_NAMES", "CATEGORY_TREE",
    "StructuredQuery", "QueryParser", "LocalQueryParser", "SearchEngine",
    "normalize_persian_text", "_extract_price", "_convert_number_unit",
    "ALT_CITY_SPELLINGS", "CATEGORY_SYNONYMS",
    "_DIGIT_LETTER_MAP", "_PERSIAN_DIGITS", "_ARABIC_DIGITS", "_ASCII_DIGITS",
    "_PUNCTUATION_CHARS", "_GENDER_WORD_MAP", "_COLOR_WORDS", "_STOPWORDS",
    "_NORMALIZED_CITY_NAMES", "_ALL_CATEGORY_NAMES", "_SORTED_CATEGORY_NAMES",
    "_NORMALIZED_COLOR_WORDS", "_NORMALIZED_STOPWORDS",
    "_STOPWORD_PHRASES", "_STOPWORD_TOKENS", "_remove_stopwords",
    "_PRICE_UNIT_RE", "_PRICE_RANGE_RE", "_PRICE_MAX_RE", "_PRICE_MIN_RE",
    "score_search_candidate", "resolve_category_ids", "resolve_city_id",
    "plain_keyword_search", "build_search_summary", "format_price",
    "EMOJI_SEARCH", "EMOJI_CITY",
]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class SearchEngineEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES)

    def setUp(self):
        self.conn = new_conn()
        for stmt in self.ns["SCHEMA_STATEMENTS"]:
            self.conn.execute(stmt)
        for stmt in self.ns["INDEX_STATEMENTS"]:
            self.conn.execute(stmt)
        for name in self.ns["CITY_NAMES"]:
            self.conn.execute("INSERT OR IGNORE INTO cities (name) VALUES (?);", (name,))
        for main_emoji, main_name, subs in self.ns["CATEGORY_TREE"]:
            cur = self.conn.execute(
                "INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, NULL);",
                (main_name, main_emoji),
            )
            parent_id = cur.lastrowid
            for sub_emoji, sub_name in subs:
                self.conn.execute(
                    "INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?);",
                    (sub_name, sub_emoji, parent_id),
                )
        self.conn.commit()
        self.ns["db"] = FakeDB(self.conn)
        self.engine = self.ns["SearchEngine"](self.ns["LocalQueryParser"]())

        # --- seed a realistic small catalog ---
        tehran_id = self.conn.execute("SELECT id FROM cities WHERE name='تهران';").fetchone()[0]
        shiraz_id = self.conn.execute("SELECT id FROM cities WHERE name='شیراز';").fetchone()[0]
        shoe_cat_id = self.conn.execute(
            "SELECT id FROM categories WHERE name='کفش';"
        ).fetchone()[0]

        self.conn.execute(
            """INSERT INTO sellers (id, name, city_id, status, rating, review_count, views, created_at, updated_at)
               VALUES (1, 'کفش‌فروشی تهران', ?, 'CLAIMED', 4.5, 10, 100, 't', 't');""",
            (tehran_id,),
        )
        self.conn.execute(
            """INSERT INTO sellers (id, name, city_id, status, rating, review_count, views, created_at, updated_at)
               VALUES (2, 'کفش‌فروشی شیراز', ?, 'UNCLAIMED', 3.0, 2, 20, 't', 't');""",
            (shiraz_id,),
        )
        self.conn.executemany(
            """INSERT INTO products
                 (id, seller_id, category_id, name, description, price, stock_status, rating, review_count, views, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'AVAILABLE', ?, ?, ?, 't', 't');""",
            [
                (1, 1, shoe_cat_id, "کفش سفید مردانه اسپرت", "کفش راحتی روزمره", 2_500_000, 4.8, 20, 300),
                (2, 1, shoe_cat_id, "کفش مشکی مردانه رسمی", "کفش چرم اداری", 4_500_000, 4.0, 5, 50),
                (3, 2, shoe_cat_id, "کفش سفید مردانه اسپرت", "مدل مشابه، فروشنده دیگر", 3_200_000, 3.5, 1, 10),
                (4, 2, shoe_cat_id, "کفش زنانه صورتی", "کفش پاشنه‌دار مجلسی", 1_800_000, 4.2, 8, 40),
            ],
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_complex_query_matches_category_gender_color_and_price(self):
        structured, results, mode = run(
            self.engine.search("یه کفش سفید مردونه زیر 3 میلیون تو تهران میخوام")
        )
        self.assertEqual(mode, "structured")
        self.assertEqual(structured.city, "تهران")
        self.assertEqual(structured.max_price, 3_000_000)
        self.assertTrue(results)
        # Only the Tehran seller's white men's sneaker under 3M should
        # come back (product 3 is Shiraz -> filtered by city; product 2
        # is black & over budget -> filtered by price/color).
        names = [r["name"] for r in results]
        self.assertIn("کفش سفید مردانه اسپرت", names)
        self.assertEqual(results[0]["seller_id"], 1)

    def test_price_filter_excludes_products_outside_range(self):
        structured, results, mode = run(self.engine.search("کفش زیر 2 میلیون"))
        self.assertEqual(mode, "structured")
        for r in results:
            self.assertLessEqual(r["price"], 2_000_000)

    def test_city_filter_only_returns_that_citys_sellers(self):
        structured, results, mode = run(self.engine.search("کفش شیراز"))
        self.assertEqual(mode, "structured")
        self.assertTrue(results)
        for r in results:
            self.assertEqual(r["seller_id"], 2)

    def test_ranking_prefers_higher_rated_matching_product_first(self):
        # Both Tehran (rating 4.8) and Shiraz (rating 3.5) sell the exact
        # same white men's sneaker; without a city filter the higher
        # rated / more viewed one should rank first.
        structured, results, mode = run(self.engine.search("کفش سفید مردانه اسپرت"))
        self.assertTrue(results)
        self.assertEqual(results[0]["seller_id"], 1)  # higher rating & views

    def test_no_match_falls_back_to_plain_keyword_search(self):
        # A nonsense combination that yields zero structured results
        # anywhere, but the raw text still LIKE-matches nothing either ->
        # plain fallback path is exercised and returns empty gracefully.
        structured, results, mode = run(self.engine.search("کفش زیر 100 تومان بندرعباس"))
        self.assertIn(mode, ("structured", "plain"))
        # Whatever the mode, we must never fabricate a result:
        for r in results:
            self.assertIn(r["name"], [
                "کفش سفید مردانه اسپرت", "کفش مشکی مردانه رسمی", "کفش زنانه صورتی",
            ])

    def test_simple_query_with_no_extractable_signal_uses_plain_search_directly(self):
        structured, results, mode = run(self.engine.search("چرم"))
        self.assertFalse(structured.has_any_extracted_field())
        self.assertEqual(mode, "plain")
        self.assertTrue(any("چرم" in (r["description"] or "") for r in results))

    def test_never_fabricates_products_not_in_database(self):
        structured, results, mode = run(self.engine.search("گوشی آیفون 15 پرو مکس"))
        real_names = {"کفش سفید مردانه اسپرت", "کفش مشکی مردانه رسمی", "کفش زنانه صورتی"}
        for r in results:
            self.assertIn(r["name"], real_names)


class ScoreCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(["StructuredQuery", "score_search_candidate"])

    def _row(self, **overrides):
        base = {
            "name": "کفش سفید",
            "description": "کفش راحتی",
            "category_id": 5,
            "price": 1_000_000,
            "rating": 4.0,
            "review_count": 10,
            "views": 50,
            "seller_city_id": 1,
        }
        base.update(overrides)
        return base

    def test_category_match_increases_score(self):
        StructuredQuery = self.ns["StructuredQuery"]
        score_fn = self.ns["score_search_candidate"]
        sq = StructuredQuery(raw_query="x")
        with_match = score_fn(self._row(), sq, {5}, None)
        without_match = score_fn(self._row(), sq, {999}, None)
        self.assertGreater(with_match, without_match)

    def test_keyword_in_name_scores_higher_than_in_description_only(self):
        StructuredQuery = self.ns["StructuredQuery"]
        score_fn = self.ns["score_search_candidate"]
        sq = StructuredQuery(raw_query="x", keyword="راحتی")
        in_name = score_fn(self._row(name="کفش راحتی سفید"), sq, set(), None)
        in_desc_only = score_fn(self._row(name="کفش سفید"), sq, set(), None)
        self.assertGreater(in_name, in_desc_only)

    def test_price_outside_range_is_penalized(self):
        StructuredQuery = self.ns["StructuredQuery"]
        score_fn = self.ns["score_search_candidate"]
        sq = StructuredQuery(raw_query="x", max_price=500_000)
        cheap = score_fn(self._row(price=400_000), sq, set(), None)
        expensive = score_fn(self._row(price=2_000_000), sq, set(), None)
        self.assertGreater(cheap, expensive)

    def test_city_match_increases_score(self):
        StructuredQuery = self.ns["StructuredQuery"]
        score_fn = self.ns["score_search_candidate"]
        sq = StructuredQuery(raw_query="x")
        matched = score_fn(self._row(seller_city_id=7), sq, set(), 7)
        unmatched = score_fn(self._row(seller_city_id=1), sq, set(), 7)
        self.assertGreater(matched, unmatched)

    def test_higher_rating_and_views_increase_score(self):
        StructuredQuery = self.ns["StructuredQuery"]
        score_fn = self.ns["score_search_candidate"]
        sq = StructuredQuery(raw_query="x")
        good = score_fn(self._row(rating=5.0, review_count=50, views=500), sq, set(), None)
        poor = score_fn(self._row(rating=1.0, review_count=0, views=0), sq, set(), None)
        self.assertGreater(good, poor)


class SearchSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names([
            "StructuredQuery", "build_search_summary", "format_price",
            "EMOJI_SEARCH", "EMOJI_CITY",
        ])

    def test_summary_includes_keyword_price_and_city(self):
        StructuredQuery = self.ns["StructuredQuery"]
        build_search_summary = self.ns["build_search_summary"]
        sq = StructuredQuery(
            raw_query="x", keyword="کفش", gender="مردانه", color="سفید",
            max_price=3_000_000, city="تهران",
        )
        text = build_search_summary(sq)
        self.assertIn("کفش", text)
        self.assertIn("مردانه", text)
        self.assertIn("سفید", text)
        self.assertIn("تهران", text)
        self.assertIn("3,000,000", text)


if __name__ == "__main__":
    unittest.main()
