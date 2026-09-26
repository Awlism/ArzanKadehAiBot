# -*- coding: utf-8 -*-
"""
Sanity checks that the supporting project files exist and contain the
minimum expected content. Pure file-system / text checks - no
dependencies required.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ProjectFilesTests(unittest.TestCase):
    def test_modular_bot_package_exists(self):
        bot_dir = ROOT / "bot"
        self.assertTrue(bot_dir.is_dir())

        required_files = (
            "__init__.py",
            "__main__.py",
            "config.py",
            "constants.py",
            "database.py",
            "keyboards.py",
            "repositories.py",
            "states.py",
            "utils.py",
        )

        for filename in required_files:
            self.assertTrue(
                (bot_dir / filename).exists(),
                f"Missing required bot module: bot/{filename}",
            )

    def test_required_handler_modules_exist(self):
        handlers_dir = ROOT / "bot" / "handlers"
        self.assertTrue(handlers_dir.is_dir())

        required_handlers = (
            "account.py",
            "ads.py",
            "admin.py",
            "buyer.py",
            "compare.py",
            "navigation.py",
            "notifications.py",
            "products.py",
            "referrals.py",
            "search.py",
            "seller.py",
            "support.py",
        )

        for filename in required_handlers:
            self.assertTrue(
                (handlers_dir / filename).exists(),
                f"Missing required handler: bot/handlers/{filename}",
            )

    def test_required_service_modules_exist(self):
        services_dir = ROOT / "bot" / "services"
        self.assertTrue(services_dir.is_dir())

        required_services = (
            "backups.py",
            "notifications.py",
            "referrals.py",
            "tasks.py",
        )

        for filename in required_services:
            self.assertTrue(
                (services_dir / filename).exists(),
                f"Missing required service: bot/services/{filename}",
            )

    def test_requirements_txt_lists_required_packages(self):
        content = (ROOT / "requirements.txt").read_text(encoding="utf-8")

        for pkg in ("aiogram", "aiosqlite", "python-dotenv"):
            self.assertIn(pkg, content)

    def test_env_example_has_required_settings(self):
        content = (ROOT / ".env.example").read_text(encoding="utf-8")

        for setting in (
            "BOT_TOKEN",
            "DATABASE_PATH",
            "SEED_DEMO_DATA",
            "ADMIN_CHAT_ID",
            "ADMIN_USERNAME",
        ):
            self.assertIn(setting, content)

    def test_gitignore_excludes_env_and_db_files(self):
        content = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn(".env", content)
        self.assertIn("*.db", content)
        self.assertIn("__pycache__", content)

    def test_readme_exists_and_mentions_modular_run_command(self):
        content = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertTrue(content.strip())
        self.assertTrue(
            "python -m bot" in content
            or "python bot/__main__.py" in content
        )

    def test_miniapp_index_html_exists_and_is_valid_shell(self):
        path = ROOT / "miniapp" / "index.html"

        self.assertTrue(path.exists())

        content = path.read_text(encoding="utf-8")

        self.assertIn("<!DOCTYPE html>", content)
        self.assertIn("telegram-web-app.js", content)


if __name__ == "__main__":
    unittest.main()