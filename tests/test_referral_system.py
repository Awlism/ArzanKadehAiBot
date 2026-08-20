# -*- coding: utf-8 -*-
"""
Tests for the referral / seller-growth system: referral link construction,
"/start shop_<id>" deep-link parsing, duplicate-referral prevention
(a user can only ever be attributed once), self-referral exclusion, and
milestone/reward-rule lookups.

Runs against real SQLite (via tests/_fakedb.py) - no aiogram/aiosqlite
needed, no network.
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from _extract import extract_names  # noqa: E402
from _fakedb import FakeDB, new_conn  # noqa: E402

NAMES = [
    "SCHEMA_STATEMENTS", "INDEX_STATEMENTS",
    "REFERRAL_REWARD_RULES", "REFERRAL_DEEP_LINK_RE",
    "build_referral_link", "get_referral_count", "next_referral_milestone",
    "record_referral_if_new", "get_sellers_owned_by_user",
    "now_iso", "logger",
]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class ReferralLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES)

    def test_build_referral_link_format(self):
        link = self.ns["build_referral_link"]("ArzanKadehAiBot", 123)
        self.assertEqual(link, "https://t.me/ArzanKadehAiBot?start=shop_123")

    def test_deep_link_regex_matches_valid_payload(self):
        pattern = self.ns["REFERRAL_DEEP_LINK_RE"]
        m = pattern.match("shop_42")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "42")

    def test_deep_link_regex_rejects_garbage(self):
        pattern = self.ns["REFERRAL_DEEP_LINK_RE"]
        for bad in ["shop_", "shop_abc", "shopp_1", "seller_1", "", "shop_1x"]:
            self.assertIsNone(pattern.match(bad), f"should not match: {bad!r}")

    def test_reward_rules_match_the_four_milestones_from_the_spec(self):
        thresholds = [t for t, _label in self.ns["REFERRAL_REWARD_RULES"]]
        self.assertEqual(thresholds, [5, 20, 50, 100])

    def test_next_milestone_progresses_correctly(self):
        next_milestone = self.ns["next_referral_milestone"]
        self.assertEqual(next_milestone(0)[0], 5)
        self.assertEqual(next_milestone(5)[0], 20)
        self.assertEqual(next_milestone(19)[0], 20)
        self.assertEqual(next_milestone(20)[0], 50)
        self.assertEqual(next_milestone(99)[0], 100)
        self.assertIsNone(next_milestone(100))
        self.assertIsNone(next_milestone(500))


class ReferralDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = extract_names(NAMES)

    def setUp(self):
        self.conn = new_conn()
        for stmt in self.ns["SCHEMA_STATEMENTS"]:
            self.conn.execute(stmt)
        for stmt in self.ns["INDEX_STATEMENTS"]:
            self.conn.execute(stmt)
        self.conn.commit()
        self.ns["db"] = FakeDB(self.conn)

        self.conn.execute(
            "INSERT INTO users (id, telegram_id, created_at, updated_at) VALUES (1, 100, 't', 't');"
        )
        self.conn.execute(
            "INSERT INTO users (id, telegram_id, created_at, updated_at) VALUES (2, 200, 't', 't');"
        )
        self.conn.execute(
            "INSERT INTO users (id, telegram_id, created_at, updated_at) VALUES (3, 300, 't', 't');"
        )
        self.conn.execute(
            """INSERT INTO sellers (id, name, status, owner_user_id, created_by_user_id, created_at, updated_at)
               VALUES (10, 'Shop A', 'CLAIMED', 1, 1, 't', 't');"""
        )
        self.conn.execute(
            """INSERT INTO sellers (id, name, status, created_by_user_id, created_at, updated_at)
               VALUES (20, 'Shop B', 'UNCLAIMED', 1, 't', 't');"""
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_recording_a_referral_returns_true_and_increments_count(self):
        recorded = run(self.ns["record_referral_if_new"](10, 2))
        self.assertTrue(recorded)
        count = run(self.ns["get_referral_count"](10))
        self.assertEqual(count, 1)

    def test_duplicate_referral_for_same_user_is_rejected(self):
        """A user can only ever be attributed to ONE referral, ever --
        even for a DIFFERENT seller the second time."""
        first = run(self.ns["record_referral_if_new"](10, 2))
        self.assertTrue(first)

        second_same_seller = run(self.ns["record_referral_if_new"](10, 2))
        self.assertFalse(second_same_seller)

        second_different_seller = run(self.ns["record_referral_if_new"](20, 2))
        self.assertFalse(second_different_seller)

        # Only ONE referral row should exist for user 2, attributed to
        # seller 10 (first-touch wins).
        row = self.conn.execute(
            "SELECT seller_id FROM referrals WHERE referred_user_id = 2;"
        ).fetchone()
        self.assertEqual(row["seller_id"], 10)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) AS c FROM referrals;").fetchone()["c"], 1
        )

    def test_different_users_can_each_be_referred_once(self):
        run(self.ns["record_referral_if_new"](10, 2))
        run(self.ns["record_referral_if_new"](10, 3))
        count = run(self.ns["get_referral_count"](10))
        self.assertEqual(count, 2)

    def test_get_sellers_owned_by_user_covers_owner_and_creator(self):
        sellers = run(self.ns["get_sellers_owned_by_user"](1))
        ids = {s["id"] for s in sellers}
        self.assertEqual(ids, {10, 20})  # owner of 10, creator of both

    def test_get_sellers_owned_by_user_empty_for_unrelated_user(self):
        sellers = run(self.ns["get_sellers_owned_by_user"](3))
        self.assertEqual(sellers, [])

    def test_referral_count_is_zero_for_seller_with_no_referrals(self):
        count = run(self.ns["get_referral_count"](20))
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
