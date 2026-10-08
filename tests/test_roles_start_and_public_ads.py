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
    ).read_text(
        encoding="utf-8"
    )


def tree(name: str) -> ast.AST:
    return ast.parse(
        read(name)
    )


def names(name: str) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree(name))
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
    }


def imported_modules(name: str) -> set[str]:
    modules: set[str] = set()

    for node in ast.walk(tree(name)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)

    return modules


class StartWorkerTests(unittest.TestCase):
    def test_start_exists(self):
        self.assertTrue(
            (WORKER / "start.py").is_file()
        )

    def test_start_handlers_exist(self):
        available = names("start.py")

        self.assertIn(
            "handle_start",
            available,
        )

        self.assertIn(
            "handle_role_pick",
            available,
        )

    def test_start_uses_users(self):
        self.assertIn(
            "users",
            read("start.py"),
        )


class RequestWorkerTests(unittest.TestCase):
    def test_requests_module_exists(self):
        self.assertTrue(
            (WORKER / "requests.py").is_file()
        )

    def test_my_requests_handler_exists(self):
        self.assertIn(
            "handle_my_requests",
            names("requests.py"),
        )

    def test_requests_table_is_used(self):
        self.assertIn(
            "requests",
            read("requests.py"),
        )


class AdsWorkerTests(unittest.TestCase):
    def test_ads_module_exists(self):
        self.assertTrue(
            (WORKER / "ads.py").is_file()
        )

    def test_ads_handlers_exist(self):
        available = names("ads.py")

        for expected in (
            "handle_ads",
            "handle_ad_type_detail",
            "handle_ad_confirm",
        ):
            self.assertIn(
                expected,
                available,
            )

    def test_ads_use_requests(self):
        self.assertIn(
            "requests",
            read("ads.py"),
        )


class PublicAdsWorkerTests(unittest.TestCase):
    def test_publicads_module_exists(self):
        self.assertTrue(
            (WORKER / "publicads.py").is_file()
        )

    def test_public_ad_handlers_exist(self):
        available = names("publicads.py")

        for expected in (
            "handle_public_ads",
            "handle_public_ad_models",
            "handle_public_ad_start",
            "handle_public_ad_kind",
            "handle_public_ad_message",
            "handle_public_ad_skip",
        ):
            self.assertIn(
                expected,
                available,
            )


class CurrentArchitectureTests(unittest.TestCase):
    def test_start_has_no_legacy_imports(self):
        modules = imported_modules("start.py")

        self.assertNotIn("aiogram", modules)
        self.assertNotIn("aiosqlite", modules)
        self.assertNotIn("sqlite3", modules)

    def test_requests_has_no_legacy_imports(self):
        modules = imported_modules("requests.py")

        self.assertNotIn("aiogram", modules)
        self.assertNotIn("aiosqlite", modules)
        self.assertNotIn("sqlite3", modules)

    def test_ads_has_no_legacy_imports(self):
        modules = imported_modules("ads.py")

        self.assertNotIn("aiogram", modules)
        self.assertNotIn("aiosqlite", modules)
        self.assertNotIn("sqlite3", modules)

    def test_publicads_has_no_legacy_imports(self):
        modules = imported_modules("publicads.py")

        self.assertNotIn("aiogram", modules)
        self.assertNotIn("aiosqlite", modules)
        self.assertNotIn("sqlite3", modules)


if __name__ == "__main__":
    unittest.main()