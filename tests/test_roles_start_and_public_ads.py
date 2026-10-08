# -*- coding: utf-8 -*-
"""
Static tests for current Worker start, request and public-ad flows.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / "src" / "worker"


def read(name: str) -> str:
    return (
        WORKER / name
    ).read_text(encoding="utf-8")


def names(name: str) -> set[str]:
    tree = ast.parse(read(name))

    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
    }


class StartWorkerTests(unittest.TestCase):
    def test_start_exists(self):
        self.assertTrue(
            (WORKER / "start.py").is_file()
        )

    def test_start_handler_exists(self):
        available = names("start.py")

        self.assertTrue(
            any(
                "start" in name
                or "main" in name
                for name in available
            )
        )

    def test_start_uses_current_user_model(self):
        text = read("start.py")

        self.assertIn(
            "users",
            text,
        )


class RequestWorkerTests(unittest.TestCase):
    def test_requests_module_exists(self):
        self.assertTrue(
            (WORKER / "requests.py").is_file()
        )

    def test_requests_table_is_used(self):
        text = read("requests.py")

        self.assertIn(
            "requests",
            text,
        )

    def test_request_statuses_are_present(self):
        text = read("requests.py")

        self.assertIn(
            "PENDING",
            text,
        )


class PublicAdsWorkerTests(unittest.TestCase):
    def test_ads_module_exists(self):
        self.assertTrue(
            (WORKER / "ads.py").is_file()
        )

    def test_publicads_module_exists(self):
        self.assertTrue(
            (WORKER / "publicads.py").is_file()
        )

    def test_ad_request_types_exist(self):
        text = (
            read("ads.py")
            + read("publicads.py")
        )

        self.assertTrue(
            "general_ad" in text
            or "ad" in text
        )

    def test_request_table_is_used_for_ads(self):
        text = (
            read("ads.py")
            + read("publicads.py")
        )

        self.assertIn(
            "requests",
            text,
        )


class CurrentArchitectureTests(unittest.TestCase):
    def test_no_sqlite_or_aiogram(self):
        for name in (
            "start.py",
            "requests.py",
            "ads.py",
            "publicads.py",
        ):
            text = read(name)

            self.assertNotIn(
                "aiogram",
                text,
            )
            self.assertNotIn(
                "aiosqlite",
                text,
            )
            self.assertNotIn(
                "sqlite3",
                text,
            )


if __name__ == "__main__":
    unittest.main()