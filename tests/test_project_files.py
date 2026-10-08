# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker project structure tests.

These tests validate the current Cloudflare/D1 migration layout and
must not enforce the retired aiogram/SQLite runtime structure.
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
WORKER = SRC / "worker"
BACKEND = SRC / "worker_backend"


class ProjectFilesTests(unittest.TestCase):
    def test_cloudflare_worker_entry_exists(self):
        path = SRC / "entry.py"

        self.assertTrue(
            path.exists(),
            "Missing Cloudflare Worker entry: src/entry.py",
        )

        content = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "class ArzanKadehWorker",
            content,
        )

        self.assertIn(
            "fetch",
            content,
        )

    def test_cloudflare_configuration_exists(self):
        path = ROOT / "wrangler.jsonc"

        self.assertTrue(
            path.exists(),
            "Missing Cloudflare configuration: wrangler.jsonc",
        )

        content = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            '"name": "arzankadehaibot"',
            content,
        )

        self.assertIn(
            '"main": "src/entry.py"',
            content,
        )

        self.assertIn(
            '"python_workers"',
            content,
        )

        self.assertIn(
            '"binding": "DB"',
            content,
        )

        self.assertIn(
            '"database_name": "arzankadeh-db"',
            content,
        )

    def test_worker_backend_modules_exist(self):
        self.assertTrue(
            BACKEND.is_dir(),
            "Missing Worker backend directory: src/worker_backend",
        )

        required_files = (
            "__init__.py",
            "backend.py",
            "database_backend.py",
            "d1_backend.py",
        )

        for filename in required_files:
            self.assertTrue(
                (BACKEND / filename).exists(),
                f"Missing Worker backend module: src/worker_backend/{filename}",
            )

    def test_worker_modules_exist(self):
        self.assertTrue(
            WORKER.is_dir(),
            "Missing Worker module directory: src/worker",
        )

        required_modules = (
            "account.py",
            "admin.py",
            "admin_ads.py",
            "ads.py",
            "categories.py",
            "compare.py",
            "discovery.py",
            "favorites.py",
            "hot.py",
            "messages.py",
            "notifications.py",
            "product_management.py",
            "product_stats.py",
            "products.py",
            "publicads.py",
            "referrals.py",
            "report.py",
            "requests.py",
            "review.py",
            "seller.py",
            "seller_claims.py",
            "seller_registration.py",
            "shop.py",
            "start.py",
            "state.py",
            "store_status.py",
            "support.py",
            "telegram.py",
            "webhook.py",
        )

        for filename in required_modules:
            self.assertTrue(
                (WORKER / filename).exists(),
                f"Missing Worker module: src/worker/{filename}",
            )

    def test_pyproject_is_worker_oriented(self):
        path = ROOT / "pyproject.toml"

        self.assertTrue(
            path.exists(),
            "Missing pyproject.toml",
        )

        content = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'name = "arzankadehaibot"',
            content,
        )

        self.assertIn(
            "workers-py",
            content,
        )

        self.assertNotIn(
            "aiogram>=",
            content,
        )

        self.assertNotIn(
            "aiosqlite>=",
            content,
        )

    def test_env_example_does_not_contain_real_secrets(self):
        path = ROOT / ".env.example"

        self.assertTrue(
            path.exists(),
            "Missing .env.example",
        )

        content = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "BOT_TOKEN=",
            content,
        )

        self.assertIn(
            "ADMIN_CHAT_ID=",
            content,
        )

        self.assertIn(
            "ADMIN_USERNAME=",
            content,
        )

        self.assertIn(
            "your_telegram_bot_token_here",
            content,
        )

    def test_gitignore_protects_local_secrets_and_databases(self):
        path = ROOT / ".gitignore"

        self.assertTrue(
            path.exists(),
            "Missing .gitignore",
        )

        content = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            ".env",
            content,
        )

        self.assertIn(
            "*.db",
            content,
        )

        self.assertIn(
            "__pycache__",
            content,
        )

    def test_miniapp_placeholder_exists(self):
        path = ROOT / "miniapp" / "index.html"

        self.assertTrue(
            path.exists(),
            "Missing Mini App placeholder: miniapp/index.html",
        )

        content = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "<!DOCTYPE html>",
            content,
        )

        self.assertIn(
            "telegram-web-app.js",
            content,
        )

    def test_legacy_runtime_files_are_not_required_by_worker_tests(self):
        """
        The migration may retain legacy bot/ files for historical reference,
        but the current Worker test suite must not require the retired runtime
        dependency files.
        """

        self.assertFalse(
            (ROOT / "requirements.txt").exists(),
            "requirements.txt should not be required by the current Worker runtime.",
        )


if __name__ == "__main__":
    unittest.main()