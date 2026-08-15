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
    def test_bot_py_exists(self):
        self.assertTrue((ROOT / "bot.py").exists())

    def test_requirements_txt_lists_required_packages(self):
        content = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        for pkg in ("aiogram", "aiosqlite", "python-dotenv"):
            self.assertIn(pkg, content)

    def test_env_example_has_bot_token_placeholder(self):
        content = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("BOT_TOKEN", content)
        self.assertIn("DATABASE_PATH", content)

    def test_gitignore_excludes_env_and_db_files(self):
        content = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".env", content)
        self.assertIn("*.db", content)
        self.assertIn("__pycache__", content)

    def test_readme_exists_and_mentions_run_command(self):
        content = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("python bot.py", content)

    def test_miniapp_index_html_exists_and_is_valid_shell(self):
        path = ROOT / "miniapp" / "index.html"
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", content)
        self.assertIn("telegram-web-app.js", content)


if __name__ == "__main__":
    unittest.main()
