# -*- coding: utf-8 -*-
"""
Static analysis for the modular ArzanKadeh AI bot.

These tests verify:

- bot.py remains a clean application entry point
- the legacy monolithic handler architecture is gone
- the root start.py entry point is gone
- required modular handler/service/core modules exist
- all application routers are imported and registered
- navigation.router remains the final router registration
- helpers live in their canonical modules
- moved helpers are not duplicated in bot.py
- legacy imports/references to the monolithic architecture are absent
- navigation handler ordering is safe
- callback patterns do not collide
- SQL queries do not interpolate runtime values directly
- unsafe bare "except: pass" blocks are absent
- all Python source files compile successfully
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


EXPECTED_HANDLER_MODULES = {
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

EXPECTED_SERVICE_MODULES = {
    "backups.py",
    "notifications.py",
    "referrals.py",
    "tasks.py",
}

EXPECTED_CORE_MODULES = {
    "config.py",
    "constants.py",
    "database.py",
    "keyboards.py",
    "repositories.py",
    "states.py",
    "utils.py",
}

EXPECTED_ROUTER_MODULES = {
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
}


def _python_files(root: Path):
    """Return sorted Python files below a directory."""
    return sorted(root.rglob("*.py"))


def _defined_functions(tree: ast.AST):
    """Return all function names defined in an AST."""
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


def _decorator_source(source: str, decorator: ast.AST) -> str:
    """Return source text for a decorator node."""
    return ast.get_source_segment(source, decorator) or ""


def _call_name(node: ast.Call) -> str:
    """
    Return a dotted call name when statically identifiable.

    Examples:
        dp.include_router(...) -> "dp.include_router"
        router.message(...) -> "router.message"
    """
    parts = []
    current = node.func

    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value

    if isinstance(current, ast.Name):
        parts.append(current.id)

    return ".".join(reversed(parts))


def _router_registrations(tree: ast.AST):
    """
    Return router module names registered through dp.include_router().

    The registrations live inside create_dispatcher(), so this helper
    intentionally walks the entire AST rather than only module-level
    statements.
    """
    registrations = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if _call_name(node) != "dp.include_router":
            continue

        if not node.args:
            continue

        argument = node.args[0]

        if (
            isinstance(argument, ast.Attribute)
            and argument.attr == "router"
            and isinstance(argument.value, ast.Name)
        ):
            registrations.append(argument.value.id)

    return registrations


class CompileTests(unittest.TestCase):
    """Ensure the application and modular Python files compile."""

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
        python_files = _python_files(BOT_PACKAGE_PATH)

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

    def test_all_test_files_compile_without_syntax_errors(self):
        tests_path = PROJECT_ROOT / "tests"
        python_files = _python_files(tests_path)

        self.assertTrue(
            python_files,
            "No Python test files found.",
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
            "Test compilation failures:\n"
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
    """Verify the current modular project structure."""

    def test_required_handler_modules_exist(self):
        missing = [
            name
            for name in sorted(EXPECTED_HANDLER_MODULES)
            if not (HANDLERS_PATH / name).is_file()
        ]

        self.assertFalse(
            missing,
            f"Missing handler modules: {missing}",
        )

    def test_required_service_modules_exist(self):
        missing = [
            name
            for name in sorted(EXPECTED_SERVICE_MODULES)
            if not (SERVICES_PATH / name).is_file()
        ]

        self.assertFalse(
            missing,
            f"Missing service modules: {missing}",
        )

    def test_required_core_modules_exist(self):
        missing = [
            name
            for name in sorted(EXPECTED_CORE_MODULES)
            if not (BOT_PACKAGE_PATH / name).is_file()
        ]

        self.assertFalse(
            missing,
            f"Missing core modules: {missing}",
        )

    def test_bot_package_has_init_file(self):
        init_path = BOT_PACKAGE_PATH / "__init__.py"

        self.assertTrue(
            init_path.is_file(),
            "bot/ must remain a Python package with __init__.py.",
        )

    def test_handlers_package_has_init_file(self):
        init_path = HANDLERS_PATH / "__init__.py"

        self.assertTrue(
            init_path.is_file(),
            "bot/handlers/ must remain a Python package.",
        )

    def test_services_package_has_init_file(self):
        init_path = SERVICES_PATH / "__init__.py"

        self.assertTrue(
            init_path.is_file(),
            "bot/services/ must remain a Python package.",
        )


class EntryPointArchitectureTests(unittest.TestCase):
    """Verify that bot.py is only the application entry point."""

    @classmethod
    def setUpClass(cls):
        cls.source = BOT_PY_PATH.read_text(
            encoding="utf-8"
        )
        cls.tree = ast.parse(
            cls.source,
            filename=str(BOT_PY_PATH),
        )

    def test_root_start_py_does_not_exist(self):
        legacy_start = PROJECT_ROOT / "start.py"

        self.assertFalse(
            legacy_start.exists(),
            (
                "Legacy root start.py still exists. "
                "The modular project uses bot.py as its entry point."
            ),
        )

    def test_bot_py_contains_expected_entry_point_functions(self):
        functions = _defined_functions(self.tree)

        expected_functions = {
            "on_startup",
            "on_shutdown",
            "handle_global_error",
            "create_dispatcher",
            "main",
        }

        missing = expected_functions - functions

        self.assertFalse(
            missing,
            (
                "bot.py is missing expected entry-point "
                f"functions: {sorted(missing)}"
            ),
        )

    def test_bot_py_contains_no_handler_decorators(self):
        forbidden_patterns = (
            "@dp.message",
            "@dp.callback_query",
            "@router.message",
            "@router.callback_query",
        )

        found = [
            pattern
            for pattern in forbidden_patterns
            if pattern in self.source
        ]

        self.assertFalse(
            found,
            (
                "bot.py contains handler decorators. "
                "Handlers must live under bot/handlers/: "
                f"{found}"
            ),
        )

    def test_bot_py_contains_no_router_handler_decorator_calls(self):
        leaked = []

        for node in ast.walk(self.tree):
            if not isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                continue

            for decorator in node.decorator_list:
                decorator_text = _decorator_source(
                    self.source,
                    decorator,
                )

                if (
                    "message" in decorator_text
                    or "callback_query" in decorator_text
                ):
                    leaked.append(
                        (
                            node.name,
                            decorator_text,
                        )
                    )

        self.assertFalse(
            leaked,
            (
                "bot.py still contains handler decorators: "
                f"{leaked}"
            ),
        )

    def test_bot_py_has_no_handler_like_functions(self):
        functions = _defined_functions(self.tree)

        allowed = {
            "on_startup",
            "on_shutdown",
            "handle_global_error",
            "create_dispatcher",
            "main",
        }

        unexpected = sorted(
            functions - allowed
        )

        self.assertFalse(
            unexpected,
            (
                "Unexpected functions found in bot.py. "
                "The entry point should not contain business "
                f"logic or handler implementations: {unexpected}"
            ),
        )

    def test_bot_py_does_not_define_router_objects(self):
        assignments = []

        for node in self.tree.body:
            if not isinstance(node, ast.Assign):
                continue

            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id in {
                        "router",
                        "dp",
                    }:
                        assignments.append(target.id)

        self.assertNotIn(
            "router",
            assignments,
            (
                "bot.py must not define its own Router. "
                "Routers belong to bot/handlers/ modules."
            ),
        )

    def test_bot_py_registers_all_main_routers(self):
        registrations = _router_registrations(
            self.tree
        )

        missing = sorted(
            EXPECTED_ROUTER_MODULES - set(registrations)
        )

        self.assertFalse(
            missing,
            (
                "Missing router registrations in bot.py: "
                f"{missing}"
            ),
        )

    def test_bot_py_does_not_register_unknown_routers(self):
        registrations = _router_registrations(
            self.tree
        )

        unknown = sorted(
            set(registrations) - EXPECTED_ROUTER_MODULES
        )

        self.assertFalse(
            unknown,
            (
                "bot.py registers unexpected routers: "
                f"{unknown}"
            ),
        )

    def test_navigation_router_is_registered_last(self):
        registrations = _router_registrations(
            self.tree
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
                "registered router because it contains "
                "generic fallback handlers."
            ),
        )


class RouterImportTests(unittest.TestCase):
    """Verify that bot.py imports the modular handler routers."""

    @classmethod
    def setUpClass(cls):
        cls.source = BOT_PY_PATH.read_text(
            encoding="utf-8"
        )
        cls.tree = ast.parse(
            cls.source,
            filename=str(BOT_PY_PATH),
        )

    def _imported_handler_modules(self):
        imported = set()

        for node in self.tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name

                    if name.startswith("bot.handlers."):
                        imported.add(
                            name.rsplit(".", 1)[-1]
                        )

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""

                if module.startswith("bot.handlers."):
                    imported.add(
                        module.rsplit(".", 1)[-1]
                    )

                elif module == "bot.handlers":
                    for alias in node.names:
                        if (
                            alias.name != "*"
                            and alias.name in EXPECTED_ROUTER_MODULES
                        ):
                            imported.add(
                                alias.name
                            )

        return imported

    def test_all_handler_modules_are_imported_by_bot_py(self):
        imported = self._imported_handler_modules()

        missing = sorted(
            EXPECTED_ROUTER_MODULES - imported
        )

        self.assertFalse(
            missing,
            (
                "bot.py does not import all modular handler "
                f"modules: {missing}"
            ),
        )

    def test_no_legacy_monolithic_bot_imports_in_application_code(self):
        violations = []

        for path in _python_files(BOT_PACKAGE_PATH):
            source = path.read_text(
                encoding="utf-8"
            )

            if re.search(
                r"(?:from\s+bot\s+import|import\s+bot\b)",
                source,
            ):
                violations.append(
                    str(path.relative_to(PROJECT_ROOT))
                )

        self.assertFalse(
            violations,
            (
                "Application modules still import the root "
                f"bot.py module: {violations}"
            ),
        )


class NavigationStructureTests(unittest.TestCase):
    """Verify safe ordering of navigation handlers."""

    @classmethod
    def setUpClass(cls):
        cls.navigation_path = HANDLERS_PATH / "navigation.py"

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

    def test_command_start_handler_is_before_generic_message_fallback(self):
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
                "handle_start must be registered before "
                "the generic message fallback."
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
                decorator_text = _decorator_source(
                    self.source,
                    decorator,
                )

                if "router.callback_query" in decorator_text:
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
                decorator_text = _decorator_source(
                    self.source,
                    decorator,
                )

                if "router.message" in decorator_text:
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
                "The generic message fallback must be "
                "registered after all specific message handlers."
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
    """Verify helpers live in their canonical modules."""

    EXPECTED_HELPERS = {
        "utils.py": {
            "ensure_user",
            "log_event",
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
        "services/notifications.py": {
            "notify_user",
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

        return _defined_functions(tree)

    def test_helpers_are_in_expected_modules(self):
        missing = []

        for relative_path, expected in self.EXPECTED_HELPERS.items():
            path = BOT_PACKAGE_PATH / relative_path

            self.assertTrue(
                path.is_file(),
                f"Expected module does not exist: {relative_path}",
            )

            defined = self._defined_functions(path)

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

        defined = _defined_functions(tree)

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


class LegacyArchitectureReferenceTests(unittest.TestCase):
    """Detect stale references to the removed monolithic architecture."""

    LEGACY_PATTERNS = (
        r"from\s+bot\s+import\s+",
        r"import\s+bot\b",
        r"bot\.py['\"]",
        r"bot\.py[`\"]",
        r"monolithic\s+bot",
        r"monolithic\s+architecture",
    )

    def test_tests_do_not_import_root_bot_module(self):
        tests_path = PROJECT_ROOT / "tests"

        violations = []

        for path in _python_files(tests_path):
            source = path.read_text(
                encoding="utf-8"
            )

            if re.search(
                r"(?:from\s+bot\s+import|import\s+bot\b)",
                source,
            ):
                violations.append(
                    str(path.relative_to(PROJECT_ROOT))
                )

        self.assertFalse(
            violations,
            (
                "Tests still import the root bot.py module: "
                f"{violations}"
            ),
        )

    def test_application_and_tests_have_no_stale_architecture_references(self):
        roots = (
            BOT_PACKAGE_PATH,
            PROJECT_ROOT / "tests",
        )

        violations = []

        for root in roots:
            for path in _python_files(root):
                if path.name == "test_static_analysis.py":
                    continue

                source = path.read_text(
                    encoding="utf-8"
                )

                for pattern in self.LEGACY_PATTERNS:
                    if re.search(pattern, source):
                        violations.append(
                            (
                                str(
                                    path.relative_to(
                                        PROJECT_ROOT
                                    )
                                ),
                                pattern,
                            )
                        )

        self.assertFalse(
            violations,
            (
                "Found stale monolithic architecture references: "
                f"{violations}"
            ),
        )


class SourceQualityTests(unittest.TestCase):
    """General source-level safety checks."""

    def test_no_bare_except_pass_in_bot_package(self):
        pattern = re.compile(
            r"except\s*:\s*\n\s*pass"
        )

        failures = []

        for path in _python_files(BOT_PACKAGE_PATH):
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

    def test_no_wildcard_imports_in_application_package(self):
        violations = []

        for path in _python_files(BOT_PACKAGE_PATH):
            source = path.read_text(
                encoding="utf-8"
            )

            tree = ast.parse(
                source,
                filename=str(path),
            )

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if any(
                        alias.name == "*"
                        for alias in node.names
                    ):
                        violations.append(
                            str(path.relative_to(PROJECT_ROOT))
                        )

        self.assertFalse(
            violations,
            (
                "Wildcard imports are not allowed in the "
                f"application package: {violations}"
            ),
        )

    def test_sql_queries_do_not_use_direct_f_string_interpolation(self):
        """
        Detect f-strings used directly as SQL statements.

        Dynamic SQL is allowed only when the interpolated expression
        is the controlled `placeholders` variable.
        """
        suspicious = []

        sql_methods = {
            "execute",
            "executemany",
            "executescript",
            "fetchone",
            "fetchall",
        }

        for path in _python_files(BOT_PACKAGE_PATH):
            source = path.read_text(
                encoding="utf-8"
            )

            tree = ast.parse(
                source,
                filename=str(path),
            )

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue

                if not isinstance(node.func, ast.Attribute):
                    continue

                if node.func.attr not in sql_methods:
                    continue

                if not node.args:
                    continue

                query_arg = node.args[0]

                if not isinstance(
                    query_arg,
                    ast.JoinedStr,
                ):
                    continue

                for value in query_arg.values:
                    if not isinstance(
                        value,
                        ast.FormattedValue,
                    ):
                        continue

                    expression = ast.get_source_segment(
                        source,
                        value.value,
                    )

                    if not expression:
                        expression = ast.unparse(
                            value.value
                        )

                    expression = expression.strip()

                    if expression == "placeholders":
                        continue

                    suspicious.append(
                        (
                            str(
                                path.relative_to(
                                    PROJECT_ROOT
                                )
                            ),
                            expression,
                        )
                    )

        self.assertFalse(
            suspicious,
            (
                "Found database queries that interpolate "
                f"values directly: {suspicious}"
            ),
        )

    def test_no_legacy_handler_implementation_remains_in_bot_py(self):
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
            if re.search(pattern, source):
                found.append(pattern)

        self.assertFalse(
            found,
            (
                "bot.py still contains handler decorators; "
                f"handlers should live in bot/handlers/: {found}"
            ),
        )


class CallbackDataCollisionTests(unittest.TestCase):
    """Detect callback-data patterns that could shadow one another."""

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
            tree = ast.parse(
                source,
                filename=str(path),
            )

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue

                if not isinstance(node.func, ast.Attribute):
                    continue

                if node.func.attr != "startswith":
                    continue

                receiver = node.func.value

                if not (
                    isinstance(receiver, ast.Attribute)
                    and receiver.attr == "data"
                    and isinstance(receiver.value, ast.Name)
                    and receiver.value.id == "F"
                ):
                    continue

                if not node.args:
                    continue

                argument = node.args[0]

                if not (
                    isinstance(argument, ast.Constant)
                    and isinstance(argument.value, str)
                ):
                    continue

                prefixes.append(
                    (
                        argument.value,
                        path,
                    )
                )

            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue

                if len(node.ops) != 1:
                    continue

                if not isinstance(node.ops[0], ast.Eq):
                    continue

                if len(node.comparators) != 1:
                    continue

                left = node.left
                right = node.comparators[0]

                if not (
                    isinstance(left, ast.Attribute)
                    and left.attr == "data"
                    and isinstance(left.value, ast.Name)
                    and left.value.id == "F"
                ):
                    continue

                if not (
                    isinstance(right, ast.Constant)
                    and isinstance(right.value, str)
                ):
                    continue

                exact.append(
                    (
                        right.value,
                        path,
                    )
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

        for i, first in enumerate(unique_prefixes):
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

    def test_exact_patterns_are_not_shadowed_by_different_prefix(self):
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


class BackgroundTaskStructureTests(unittest.TestCase):
    """Verify required background services remain wired into bot.py."""

    @classmethod
    def setUpClass(cls):
        cls.source = BOT_PY_PATH.read_text(
            encoding="utf-8"
        )

    def test_bot_py_imports_background_tasks(self):
        self.assertIn(
            "periodic_backup_task",
            self.source,
        )

        self.assertIn(
            "periodic_ad_expiry_task",
            self.source,
        )

    def test_bot_py_starts_background_tasks(self):
        self.assertRegex(
            self.source,
            r"(?:asyncio\.)?create_task\([^)]*periodic_backup_task",
        )

        self.assertRegex(
            self.source,
            r"(?:asyncio\.)?create_task\([^)]*periodic_ad_expiry_task",
        )


if __name__ == "__main__":
    unittest.main()