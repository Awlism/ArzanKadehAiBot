# -*- coding: utf-8 -*-
"""
Static validation of the current Cloudflare D1 configuration contract.
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

WRANGLER = ROOT / "wrangler.jsonc"
D1_BACKEND = ROOT / "src" / "worker_backend" / "d1_backend.py"
DATABASE_BACKEND = ROOT / "src" / "worker_backend" / "database_backend.py"


EXPECTED_TABLES = {
    "users",
    "cities",
    "categories",
    "sellers",
    "products",
    "favorites",
    "seller_claims",
    "reviews",
    "reports",
    "events",
    "notifications",
    "referrals",
    "referral_rewards",
    "seller_favorites",
    "requests",
    "audit_log",
    "orders",
    "compare_selections",
    "worker_states",
}


class D1ConfigurationTests(unittest.TestCase):
    def test_wrangler_exists(self):
        self.assertTrue(WRANGLER.is_file())

    def test_d1_binding_exists(self):
        source = WRANGLER.read_text(encoding="utf-8")

        self.assertIn('"binding": "DB"', source)
        self.assertIn('"database_name": "arzankadeh-db"', source)
        self.assertIn(
            '"database_id": "1f3a3d15-aaaa-4b17-992a-74c508582917"',
            source,
        )

    def test_worker_entry_is_configured(self):
        source = WRANGLER.read_text(encoding="utf-8")

        self.assertIn('"main": "src/entry.py"', source)
        self.assertIn('"python_workers"', source)


class D1BackendContractTests(unittest.TestCase):
    def test_backend_files_exist(self):
        self.assertTrue(D1_BACKEND.is_file())
        self.assertTrue(DATABASE_BACKEND.is_file())

    def test_database_backend_has_core_methods(self):
        source = DATABASE_BACKEND.read_text(
            encoding="utf-8"
        )

        for method in (
            "connect",
            "close",
            "execute",
            "fetchone",
            "fetchall",
            "executemany",
            "transaction",
        ):
            self.assertIn(
                f"def {method}",
                source,
                f"Missing DatabaseBackend.{method}().",
            )

    def test_d1_backend_has_core_methods(self):
        source = D1_BACKEND.read_text(
            encoding="utf-8"
        )

        for method in (
            "connect",
            "close",
            "execute",
            "fetchone",
            "fetchall",
            "executemany",
            "transaction",
        ):
            self.assertIn(
                f"def {method}",
                source,
                f"Missing D1Backend.{method}().",
            )

    def test_d1_backend_has_no_sqlite_runtime_import(self):
        source = D1_BACKEND.read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            "import sqlite3",
            source,
        )
        self.assertNotIn(
            "import aiosqlite",
            source,
        )


class ExpectedSchemaContractTests(unittest.TestCase):
    def test_expected_tables_are_defined(self):
        self.assertTrue(EXPECTED_TABLES)

    def test_worker_states_exists(self):
        self.assertIn(
            "worker_states",
            EXPECTED_TABLES,
        )

    def test_compare_selections_exists(self):
        self.assertIn(
            "compare_selections",
            EXPECTED_TABLES,
        )

    def test_seller_favorites_exists(self):
        self.assertIn(
            "seller_favorites",
            EXPECTED_TABLES,
        )


if __name__ == "__main__":
    unittest.main()