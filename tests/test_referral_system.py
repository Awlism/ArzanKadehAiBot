# -*- coding: utf-8 -*-
"""
Tests for the current Worker referral system.

Targets src/worker/referrals.py directly.
"""

import unittest

from worker.referrals import (
    BOT_USERNAME,
    REFERRAL_MILESTONES,
    build_referral_link,
    next_referral_milestone,
)


class ReferralConstantsTests(unittest.TestCase):
    def test_bot_username_is_defined(self):
        self.assertEqual(
            BOT_USERNAME,
            "ArzanKadehAiBot",
        )

    def test_milestones_are_ascending(self):
        thresholds = [
            threshold
            for threshold, _label
            in REFERRAL_MILESTONES
        ]

        self.assertEqual(
            thresholds,
            sorted(thresholds),
        )

        self.assertEqual(
            len(thresholds),
            len(set(thresholds)),
        )


class ReferralLinkTests(unittest.TestCase):
    def test_referral_link_contains_bot_username(self):
        link = build_referral_link(
            BOT_USERNAME,
            123,
        )

        self.assertIn(
            "ArzanKadehAiBot",
            link,
        )

    def test_referral_link_contains_seller_id(self):
        link = build_referral_link(
            BOT_USERNAME,
            123,
        )

        self.assertIn(
            "123",
            link,
        )

    def test_referral_link_has_telegram_scheme(self):
        link = build_referral_link(
            BOT_USERNAME,
            123,
        )

        self.assertTrue(
            link.startswith("https://t.me/")
        )

    def test_different_ids_produce_different_links(self):
        first = build_referral_link(
            BOT_USERNAME,
            1,
        )

        second = build_referral_link(
            BOT_USERNAME,
            2,
        )

        self.assertNotEqual(
            first,
            second,
        )


class ReferralMilestoneTests(unittest.TestCase):
    def test_zero_referrals_have_a_next_milestone(self):
        result = next_referral_milestone(0)

        self.assertIsNotNone(
            result
        )

    def test_first_milestone_is_five(self):
        result = next_referral_milestone(0)

        self.assertEqual(
            result[0],
            5,
        )

    def test_count_below_twenty_points_to_twenty(self):
        result = next_referral_milestone(5)

        self.assertEqual(
            result[0],
            20,
        )

    def test_count_above_all_milestones_returns_none(self):
        result = next_referral_milestone(100)

        self.assertIsNone(
            result
        )


if __name__ == "__main__":
    unittest.main()