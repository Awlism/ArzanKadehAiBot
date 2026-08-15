# -*- coding: utf-8 -*-
"""
Static analysis over bot.py's source text / AST. These tests catch exactly
the class of bugs the project brief calls out: wrong imports, undefined
names, colliding callback_data prefixes, and a generic handler silently
swallowing messages meant for a more specific handler (e.g. a bare
@router.message() fallback registered before @router.message(CommandStart())
would eat every "/start").

No aiogram/aiosqlite import is required for any test in this file.
"""
import ast
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

BOT_PY_PATH = Path(__file__).resolve().parent.parent / "bot.py"


class CompileTests(unittest.TestCase):
    def test_bot_py_compiles_without_syntax_errors(self):
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(BOT_PY_PATH)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode, 0,
            f"py_compile failed:\nstdout={result.stdout}\nstderr={result.stderr}",
        )


class SourceStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = BOT_PY_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(BOT_PY_PATH))

    def _line_of_def(self, func_name: str) -> int:
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                return node.lineno
        raise AssertionError(f"Function '{func_name}' not found in bot.py")

    def test_no_duplicate_top_level_function_definitions(self):
        names = []
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.append(node.name)
        duplicates = {n for n in names if names.count(n) > 1}
        self.assertFalse(duplicates, f"Duplicate top-level function defs: {duplicates}")

    def test_no_duplicate_top_level_class_definitions(self):
        names = [n.name for n in self.tree.body if isinstance(n, ast.ClassDef)]
        duplicates = {n for n in names if names.count(n) > 1}
        self.assertFalse(duplicates, f"Duplicate top-level class defs: {duplicates}")

    def test_command_start_handler_is_registered_before_generic_message_fallback(self):
        """
        Regression test for a real bug found in review: a bare
        `@router.message()` (no filter) matches every message, including
        "/start". If it is registered before the CommandStart() handler,
        aiogram dispatches to the first match and /start would never reach
        handle_start(). This test fails loudly if that ordering regresses.
        """
        start_line = self._line_of_def("handle_start")
        fallback_line = self._line_of_def("handle_unknown_message")
        self.assertLess(
            start_line, fallback_line,
            "handle_start (CommandStart) must be registered BEFORE the generic "
            "@router.message() fallback, or /start will be swallowed.",
        )

    def test_generic_callback_fallback_is_registered_last(self):
        """
        The bare `@router.callback_query()` fallback (handle_unknown_callback)
        must be the LAST callback_query handler registered, otherwise it
        would intercept callback_data meant for more specific handlers.
        """
        fallback_line = self._line_of_def("handle_unknown_callback")
        other_callback_lines = []
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for deco in node.decorator_list:
                    src = ast.get_source_segment(self.source, deco) or ""
                    if "router.callback_query" in src and node.name != "handle_unknown_callback":
                        other_callback_lines.append(node.lineno)
        self.assertTrue(other_callback_lines, "No other callback_query handlers found - unexpected.")
        self.assertGreater(
            fallback_line, max(other_callback_lines),
            "The generic @router.callback_query() fallback must be registered "
            "after every specific callback_query handler.",
        )

    def test_generic_message_fallback_is_registered_last(self):
        fallback_line = self._line_of_def("handle_unknown_message")
        other_message_lines = []
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for deco in node.decorator_list:
                    src = ast.get_source_segment(self.source, deco) or ""
                    if "router.message" in src and node.name != "handle_unknown_message":
                        other_message_lines.append(node.lineno)
        self.assertTrue(other_message_lines)
        self.assertGreater(fallback_line, max(other_message_lines))

    def test_required_helper_functions_are_defined(self):
        required = [
            "ensure_user", "log_event", "notify_user", "safe_edit",
            "kb_add_back", "kb_pagination_row", "send_main_menu",
            "restart_requested", "_render_product_detail", "_render_notifications",
            "_save_report", "_finish_register_seller", "parse_int",
            "format_price", "status_badge", "instagram_url", "telegram_url",
            "website_url", "now_iso",
        ]
        defined = set()
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(node.name)
        missing = [name for name in required if name not in defined]
        self.assertFalse(missing, f"Referenced helper functions are not defined: {missing}")

    def test_no_bare_except_pass(self):
        """The project brief explicitly forbids `except: pass`."""
        pattern = re.compile(r"except\s*:\s*\n\s*pass")
        self.assertIsNone(
            pattern.search(self.source),
            "Found a bare 'except: pass' block - not allowed by project rules.",
        )

    def test_all_sql_queries_use_placeholders_not_fstring_interpolation_of_user_input(self):
        """
        Heuristic check: an f-string passed straight to db.execute/fetchone/
        fetchall/conn.execute as the query argument (rather than only for
        building an IN (...) placeholder list) would indicate unsafe SQL.
        We whitelist the one legitimate dynamic-placeholder-count query
        (the gift list IN clause), which itself never interpolates values,
        only a fixed string of '?' placeholders.
        """
        suspicious = re.findall(
            r'(?:db\.execute|db\.fetchone|db\.fetchall|conn\.execute)\(\s*f"[^"]*\{(?!placeholders\b)',
            self.source,
        )
        self.assertFalse(
            suspicious,
            f"Found query strings that may interpolate values directly: {suspicious}",
        )


class CallbackDataCollisionTests(unittest.TestCase):
    """
    Extracts every literal string used in F.data == "..." and
    F.data.startswith("...") across callback_query handlers, and checks
    that no two DISTINCT handlers' patterns can match the same
    callback_data value. This is exactly the propagation-bug class the
    project brief asked to guard against.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = BOT_PY_PATH.read_text(encoding="utf-8")

    def _extract_patterns(self):
        exact = re.findall(r'F\.data\s*==\s*"([^"]+)"', self.source)
        prefixes = re.findall(r'F\.data\.startswith\("([^"]+)"\)', self.source)
        return exact, prefixes

    def test_exact_match_patterns_are_unique(self):
        exact, _prefixes = self._extract_patterns()
        duplicates = {p for p in exact if exact.count(p) > 1}
        self.assertFalse(duplicates, f"Duplicate exact F.data patterns: {duplicates}")

    def test_prefix_patterns_do_not_shadow_each_other(self):
        _exact, prefixes = self._extract_patterns()
        unique_prefixes = sorted(set(prefixes))
        for i, p1 in enumerate(unique_prefixes):
            for p2 in unique_prefixes[i + 1:]:
                self.assertFalse(
                    p1.startswith(p2) or p2.startswith(p1),
                    f"Callback prefixes collide and could shadow one another: "
                    f"'{p1}' vs '{p2}'",
                )

    def test_exact_patterns_are_not_shadowed_by_a_different_prefix(self):
        exact, prefixes = self._extract_patterns()
        unique_prefixes = set(prefixes)
        for e in set(exact):
            for p in unique_prefixes:
                if e.startswith(p) and not e == p:
                    self.fail(f"Exact pattern '{e}' would be shadowed by prefix '{p}:' handler")


if __name__ == "__main__":
    unittest.main()
