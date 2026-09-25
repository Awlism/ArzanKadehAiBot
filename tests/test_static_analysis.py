# -*- coding: utf-8 -*-
"""
Static analysis for the modular ArzanKadeh AI bot.

These tests verify:
- bot.py remains a clean application entry point
- required handler/service modules exist
- required helpers live in their new modules
- navigation handler ordering is safe
- callback patterns do not collide
- SQL queries do not interpolate values directly
- source files compile successfully
"""

import ast
import re
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BOT_PY_PATH = PROJECT_ROOT / "bot.py"
BOT_PACKAGE_PATH = PROJECT_ROOT / "bot"

HANDLERS_PATH = BOT_PACKAGE_PATH / "handlers"
SERVICES_PATH = BOT_PACKAGE_PATH / "services"


class CompileTests(unittest.TestCase):
    """Ensure the main application and modular Python files compile."""

    def test_bot_py_compiles_without_syntax_errors(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "py_compile",
                str(BOT_PY_PATH),
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            result.returncode,
            0,
            (
                "py_compile failed:\n"
                f"stdout={result.stdout}\n"
                f"stderr={result.stderr}"
            ),
        )

    def test_bot_package_files_compile_without_syntax_errors(self):
        python_files = sorted(
            BOT_PACKAGE_PATH.rglob("*.py")
        )

        self.assertTrue(
            python_files,
            "No Python files found inside bot/ package.",
        )

        failures = []

        for path in python_files:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "py_compile",
                    str(path),
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                failures.append(
                    (
                        str(path.relative_to(PROJECT_ROOT)),
                        result.stdout,
                        result.stderr,
                    )
                )

        self.assertFalse(
            failures,
            "Python compilation failures:\n"
            + "\n".join(
                (
                    f"{path}\n"
                    f"stdout={stdout}\n"
                    f"stderr={stderr}"
                )
                for path, stdout, stderr in failures
            ),
        )


class ModularStructureTests(unittest.TestCase):
    """Verify the new modular project structure."""

    REQUIRED_HANDLER_MODULES = {
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
    }

    REQUIRED_SERVICE_MODULES = {
        "backups.py",
        "notifications.py",
        "referrals.py",
        "tasks.py",
    }

    REQUIRED_CORE_MODULES = {
        "config.py",
        "constants.py",
        "database.py",
        "keyboards.py",
        "repositories.py",
        "states.py",
        "utils.py",
    }

    def test_required_handler_modules_exist(self):
        missing = [
            name
            for name in self.REQUIRED_HANDLER_MODULES
            if not (HANDLERS_PATH / name).is_file()
        ]

        self.assertFalse(
            missing,
            f"Missing handler modules: {missing}",
        )

    def test_required_service_modules_exist(self):
        missing = [
            name
            for name in self.REQUIRED_SERVICE_MODULES
            if not (SERVICES_PATH / name).is_file()
        ]

        self.assertFalse(
            missing,
            f"Missing service modules: {missing}",
        )

    def test_required_core_modules_exist(self):
        missing = [
            name
            for name in self.REQUIRED_CORE_MODULES
            if not (BOT_PACKAGE_PATH / name).is_file()
        ]

        self.assertFalse(
            missing,
            f"Missing core modules: {missing}",
        )

    def test_bot_py_is_entry_point_not_monolith(self):
        source = BOT_PY_PATH.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(
            source,
            filename=str(BOT_PY_PATH),
        )

        top_level_functions = [
            node.name
            for node in tree.body
            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
        ]

        expected_functions = {
            "on_startup",
            "on_shutdown",
            "handle_global_error",
            "create_dispatcher",
            "main",
        }

        missing = expected_functions - set(
            top_level_functions
        )

        self.assertFalse(
            missing,
            (
                "bot.py is missing expected entry-point "
                f"functions: {sorted(missing)}"
            ),
        )

        forbidden_handler_names = {
            "handle_search_query",
            "handle_product_detail",
            "handle_notifications",
            "handle_support_start",
            "handle_admin_home",
            "handle_ads",
            "handle_compare_start",
            "handle_register_seller",
            "handle_add_product",
        }

        leaked = forbidden_handler_names.intersection(
            top_level_functions
        )

        self.assertFalse(
            leaked,
            (
                "bot.py still contains handler implementations "
                f"that should live in modules: {sorted(leaked)}"
            ),
        )

    def test_bot_py_registers_all_main_routers(self):
        source = BOT_PY_PATH.read_text(
            encoding="utf-8"
        )

        required_routers = {
            "buyer.router",
            "search.router",
            "compare.router",
            "products.router",
            "seller.router",
            "account.router",
            "support.router",
            "referrals.router",
            "notifications.router",
            "ads.router",
            "admin.router",
            "navigation.router",
        }

        missing = [
            router
            for router in required_routers
            if f"dp.include_router({router})" not in source
        ]

        self.assertFalse(
            missing,
            f"Missing router registrations in bot.py: {missing}",
        )

    def test_navigation_router_is_registered_last(self):
        source = BOT_PY_PATH.read_text(
            encoding="utf-8"
        )

        registrations = re.findall(
            r"dp\.include_router\(\s*([a-zA-Z_]+)\.router\s*\)",
            source,
        )

        self.assertTrue(
            registrations,
            "No Dispatcher router registrations found.",
        )

        self.assertEqual(
            registrations[-1],
            "navigation",
            (
                "navigation.router must remain the last "
                "registered router because it contains generic "
                "fallback handlers."
            ),
        )


class NavigationStructureTests(unittest.TestCase):
    """Verify safe ordering of navigation handlers."""

    @classmethod
    def setUpClass(cls):
        cls.navigation_path = (
            HANDLERS_PATH / "navigation.py"
        )

        cls.source = cls.navigation_path.read_text(
            encoding="utf-8"
        )

        cls.tree = ast.parse(
            cls.source,
            filename=str(cls.navigation_path),
        )

    def _line_of_def(self, func_name: str) -> int:
        for node in ast.walk(self.tree):
            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ) and node.name == func_name:
                return node.lineno

        raise AssertionError(
            f"Function '{func_name}' not found in navigation.py"
        )

    def test_command_start_handler_is_before_generic_message_fallback(
        self,
    ):
        start_line = self._line_of_def(
            "handle_start"
        )

        fallback_line = self._line_of_def(
            "handle_unknown_message"
        )

        self.assertLess(
            start_line,
            fallback_line,
            (
                "handle_start (CommandStart) must be registered "
                "before the generic message fallback."
            ),
        )

    def test_generic_callback_fallback_is_last(self):
        fallback_line = self._line_of_def(
            "handle_unknown_callback"
        )

        other_callback_lines = []

        for node in ast.walk(self.tree):
            if not isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                continue

            if node.name == "handle_unknown_callback":
                continue

            for decorator in node.decorator_list:
                source = (
                    ast.get_source_segment(
                        self.source,
                        decorator,
                    )
                    or ""
                )

                if "router.callback_query" in source:
                    other_callback_lines.append(
                        node.lineno
                    )

        self.assertTrue(
            other_callback_lines,
            "No other callback_query handlers found.",
        )

        self.assertGreater(
            fallback_line,
            max(other_callback_lines),
            (
                "The generic callback_query fallback must be "
                "registered after all specific callback handlers."
            ),
        )

    def test_generic_message_fallback_is_last(self):
        fallback_line = self._line_of_def(
            "handle_unknown_message"
        )

        other_message_lines = []

        for node in ast.walk(self.tree):
            if not isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                continue

            if node.name == "handle_unknown_message":
                continue

            for decorator in node.decorator_list:
                source = (
                    ast.get_source_segment(
                        self.source,
                        decorator,
                    )
                    or ""
                )

                if "router.message" in source:
                    other_message_lines.append(
                        node.lineno
                    )

        self.assertTrue(
            other_message_lines,
            "No other message handlers found.",
        )

        self.assertGreater(
            fallback_line,
            max(other_message_lines),
            (
                "The generic message fallback must be registered "
                "after all specific message handlers."
            ),
        )

    def test_navigation_has_command_start_handler(self):
        self.assertIn(
            "@router.message",
            self.source,
        )

        self.assertIn(
            "CommandStart()",
            self.source,
        )

        self.assertIn(
            "async def handle_start",
            self.source,
        )

    def test_navigation_handles_both_restart_callbacks(self):
        self.assertIn(
            'F.data == "restart_button"',
            self.source,
        )

        self.assertIn(
            'F.data == "restartmain"',
            self.source,
        )


class HelperLocationTests(unittest.TestCase):
    """
    Verify helpers moved out of bot.py into their intended modules.
    """

    EXPECTED_HELPERS = {
        "utils.py": {
            "ensure_user",
            "log_event",
            "notify_user",
            "safe_edit",
            "parse_int",
            "format_price",
            "status_badge",
            "instagram_url",
            "telegram_url",
            "website_url",
            "now_iso",
            "restart_requested",
        },
        "keyboards.py": {
            "kb_add_back",
            "kb_pagination_row",
            "main_menu_keyboard",
            "restart_button",
        },
        "handlers/products.py": {
            "_render_product_detail",
        },
        "handlers/notifications.py": {
            "_render_notifications",
        },
        "handlers/seller.py": {
            "_finish_register_seller",
        },
    }

    def _defined_functions(self, path: Path):
        source = path.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(
            source,
            filename=str(path),
        )

        return {
            node.name
            for node in ast.walk(tree)
            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
        }

    def test_helpers_are_in_expected_modules(self):
        missing = []

        for relative_path, expected in (
            self.EXPECTED_HELPERS.items()
        ):
            path = BOT_PACKAGE_PATH / relative_path

            self.assertTrue(
                path.is_file(),
                f"Expected module does not exist: {relative_path}",
            )

            defined = self._defined_functions(
                path
            )

            for function_name in expected:
                if function_name not in defined:
                    missing.append(
                        f"{relative_path}:{function_name}"
                    )

        self.assertFalse(
            missing,
            "Helpers missing from expected modules: "
            + ", ".join(missing),
        )

    def test_bot_py_no_longer_contains_moved_helpers(self):
        source = BOT_PY_PATH.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(
            source,
            filename=str(BOT_PY_PATH),
        )

        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
        }

        moved_helpers = set().union(
            *self.EXPECTED_HELPERS.values()
        )

        leaked = defined.intersection(
            moved_helpers
        )

        self.assertFalse(
            leaked,
            (
                "Moved helpers are still defined in bot.py: "
                f"{sorted(leaked)}"
            ),
        )


class SourceQualityTests(unittest.TestCase):
    """General source-level safety checks."""

    def test_no_bare_except_pass_in_bot_package(self):
        pattern = re.compile(
            r"except\s*:\s*\n\s*pass"
        )

        failures = []

        for path in BOT_PACKAGE_PATH.rglob("*.py"):
            source = path.read_text(
                encoding="utf-8"
            )

            if pattern.search(source):
                failures.append(
                    str(path.relative_to(PROJECT_ROOT))
                )

        self.assertFalse(
            failures,
            (
                "Found bare 'except: pass' blocks in: "
                f"{failures}"
            ),
        )

    def test_sql_queries_do_not_use_direct_f_string_interpolation(
        self,
    ):
        """
        Heuristic check for f-strings passed directly to database
        execution methods.

        Dynamic SQL that uses a fixed list of '?' placeholders is
        allowed only when the interpolated value is named
        `placeholders`.
        """

        suspicious = []

        pattern = re.compile(
            r"""
            (?:
                db\.execute
                |
                db\.fetchone
                |
                db\.fetchall
                |
                conn\.execute
            )
            \(
                \s*
                f["']
                [^"']*
                \{
                (?!placeholders\b)
            """,
            re.VERBOSE,
        )

        for path in BOT_PACKAGE_PATH.rglob("*.py"):
            source = path.read_text(
                encoding="utf-8"
            )

            matches = pattern.findall(
                source
            )

            if matches:
                suspicious.append(
                    str(path.relative_to(PROJECT_ROOT))
                )

        self.assertFalse(
            suspicious,
            (
                "Found database queries that may interpolate "
                f"values directly: {suspicious}"
            ),
        )

    def test_no_legacy_handler_implementation_remains_in_bot_py(
        self,
    ):
        source = BOT_PY_PATH.read_text(
            encoding="utf-8"
        )

        legacy_patterns = [
            r"@dp\.message",
            r"@dp\.callback_query",
            r"@router\.message",
            r"@router\.callback_query",
        ]

        found = []

        for pattern in legacy_patterns:
            if re.search(
                pattern,
                source,
            ):
                found.append(pattern)

        self.assertFalse(
            found,
            (
                "bot.py still contains handler decorators; "
                f"handlers should live in bot/handlers/: {found}"
            ),
        )


class CallbackDataCollisionTests(unittest.TestCase):
    """
    Detect callback-data patterns that could shadow one another.

    This scan covers all handler modules, not just bot.py.
    """

    @classmethod
    def setUpClass(cls):
        cls.python_sources = []

        for path in HANDLERS_PATH.rglob("*.py"):
            cls.python_sources.append(
                (
                    path,
                    path.read_text(
                        encoding="utf-8"
                    ),
                )
            )

    def _extract_patterns(self):
        exact = []
        prefixes = []

        for path, source in self.python_sources:
            exact_matches = re.findall(
                r'F\.data\s*==\s*"([^"]+)"',
                source,
            )

            prefix_matches = re.findall(
                r'F\.data\.startswith\("([^"]+)"\)',
                source,
            )

            exact.extend(
                (value, path)
                for value in exact_matches
            )

            prefixes.extend(
                (value, path)
                for value in prefix_matches
            )

        return exact, prefixes

    def test_exact_match_patterns_are_unique(self):
        exact, _prefixes = self._extract_patterns()

        values = [
            value
            for value, _path in exact
        ]

        duplicates = {
            value
            for value in values
            if values.count(value) > 1
        }

        self.assertFalse(
            duplicates,
            (
                "Duplicate exact callback patterns found: "
                f"{sorted(duplicates)}"
            ),
        )

    def test_prefix_patterns_do_not_shadow_each_other(self):
        _exact, prefixes = self._extract_patterns()

        unique_prefixes = sorted(
            {
                value
                for value, _path in prefixes
            }
        )

        collisions = []

        for i, first in enumerate(
            unique_prefixes
        ):
            for second in unique_prefixes[i + 1:]:
                if (
                    first.startswith(second)
                    or second.startswith(first)
                ):
                    collisions.append(
                        (first, second)
                    )

        self.assertFalse(
            collisions,
            (
                "Callback prefixes collide and could shadow "
                f"one another: {collisions}"
            ),
        )

    def test_exact_patterns_are_not_shadowed_by_different_prefix(
        self,
    ):
        exact, prefixes = self._extract_patterns()

        unique_prefixes = {
            value
            for value, _path in prefixes
        }

        collisions = []

        for exact_value, exact_path in exact:
            for prefix in unique_prefixes:
                if (
                    exact_value.startswith(prefix)
                    and exact_value != prefix
                ):
                    collisions.append(
                        (
                            exact_value,
                            str(
                                exact_path.relative_to(
                                    PROJECT_ROOT
                                )
                            ),
                            prefix,
                        )
                    )

        self.assertFalse(
            collisions,
            (
                "Exact callback patterns are shadowed by "
                f"prefix handlers: {collisions}"
            ),
        )


class ImportStructureTests(unittest.TestCase):
    """Verify that the modular entry point imports the expected modules."""

    def test_bot_py_imports_handler_package_modules(self):
        source = BOT_PY_PATH.read_text(
            encoding="utf-8"
        )

        expected_modules = [
            "account",
            "ads",
            "admin",
            "buyer",
            "compare",
            "navigation",
            "notifications",
            "products",
            "referrals",
            "search",
            "seller",
            "support",
        ]

        for module in expected_modules:
            self.assertRegex(
                source,
                rf"\b{module}\b",
                f"bot.py does not reference handler module '{module}'.",
            )

    def test_bot_py_imports_background_tasks(self):
        source = BOT_PY_PATH.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "periodic_backup_task",
            source,
        )

        self.assertIn(
            "periodic_ad_expiry_task",
            source,
        )


if __name__ == "__main__":
    unittest.main()