# -*- coding: utf-8 -*-
"""
Reliability and pagination tests for the current Worker architecture.

These tests intentionally avoid importing the legacy bot package.
"""

import inspect
import unittest

from worker.search import (
    PAGE_SIZE,
    SEARCH_RESULT_LIMIT,
    SELLER_SEARCH_LIMIT,
    _pagination,
)
from worker.state import (
    clear_state,
    get_state,
    set_state,
)


class SearchPaginationTests(unittest.TestCase):
    def test_page_size_is_positive(self):
        self.assertGreater(
            PAGE_SIZE,
            0,
        )

    def test_result_limit_is_positive(self):
        self.assertGreater(
            SEARCH_RESULT_LIMIT,
            0,
        )

    def test_seller_limit_is_positive(self):
        self.assertGreater(
            SELLER_SEARCH_LIMIT,
            0,
        )

    def test_pagination_function_exists(self):
        self.assertTrue(
            callable(_pagination)
        )

    def test_pagination_is_worker_function(self):
        self.assertEqual(
            inspect.getmodule(_pagination).__name__,
            "worker.search",
        )


class WorkerStateStructureTests(unittest.TestCase):
    def test_state_helpers_are_current_worker_functions(self):
        self.assertEqual(
            inspect.getmodule(get_state).__name__,
            "worker.state",
        )

        self.assertEqual(
            inspect.getmodule(set_state).__name__,
            "worker.state",
        )

        self.assertEqual(
            inspect.getmodule(clear_state).__name__,
            "worker.state",
        )

    def test_state_helpers_are_callable(self):
        self.assertTrue(
            callable(get_state)
        )

        self.assertTrue(
            callable(set_state)
        )

        self.assertTrue(
            callable(clear_state)
        )


class WorkerPaginationSafetyTests(unittest.TestCase):
    def test_page_size_does_not_exceed_result_limit(self):
        self.assertLessEqual(
            PAGE_SIZE,
            SEARCH_RESULT_LIMIT,
        )

    def test_seller_limit_does_not_exceed_result_limit(self):
        self.assertLessEqual(
            SELLER_SEARCH_LIMIT,
            SEARCH_RESULT_LIMIT,
        )

    def test_limits_are_integers(self):
        self.assertIsInstance(
            PAGE_SIZE,
            int,
        )

        self.assertIsInstance(
            SEARCH_RESULT_LIMIT,
            int,
        )

        self.assertIsInstance(
            SELLER_SEARCH_LIMIT,
            int,
        )


if __name__ == "__main__":
    unittest.main()