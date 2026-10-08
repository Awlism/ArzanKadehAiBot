# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Static analysis for the current Cloudflare Worker architecture.

The legacy aiogram/SQLite application is intentionally not used as the
runtime source of truth for these tests.

Current runtime:

    src/entry.py
        |
        +-- src/worker/
        |
        +-- src/worker_backend/
        |
        +-- Cloudflare D1
"""

from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
ENTRY_PATH = SRC_PATH / "entry.py"
WORKER_PATH = SRC_PATH / "worker"
BACKEND_PATH = SRC_PATH / "worker_backend"


EXPECTED_WORKER_MODULES = {
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
}


EXPECTED_BACKEND_MODULES = {
    "__init__.py",
    "backend.py",
    "database_backend.py",
    "d1_backend.py",
}


FORBIDDEN_WORKER_TEXT = (
    "import aiogram",
    "from aiogram",
    "import aiosqlite",
    "from aiosqlite",
    "import sqlite3",
    "from sqlite3",
)


def _python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []

    return sorted(
        path
        for path in root.rglob("*.py")
        if path.is_file()
    )


def _parse(path: Path) -> ast.AST:
    return ast.parse(
        path.read_text(
            encoding="utf-8"
        ),
        filename=str(path),
    )


def _defined_functions(tree: ast.AST) -> set[str]:
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


def _called_names(tree: ast.AST) -> list[str]:
    names: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        current = node.func
        parts: list[str] = []

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.append(current.id)

        if parts:
            names.append(
                ".".join(
                    reversed(parts)
                )
            )

    return names


class WorkerStructureTests(unittest.TestCase):
    """Verify the current Worker source tree exists."""

    def test_src_directory_exists(self):
        self.assertTrue(
            SRC_PATH.is_dir(),
            "Missing src/ directory.",
        )

    def test_entry_exists(self):
        self.assertTrue(
            ENTRY_PATH.is_file(),
            "Missing Worker entry: src/entry.py",
        )

    def test_worker_directory_exists(self):
        self.assertTrue(
            WORKER_PATH.is_dir(),
            "Missing Worker module directory: src/worker/",
        )

    def test_backend_directory_exists(self):
        self.assertTrue(
            BACKEND_PATH.is_dir(),
            "Missing Worker backend directory: src/worker_backend/",
        )

    def test_expected_worker_modules_exist(self):
        missing = [
            name
            for name in sorted(
                EXPECTED_WORKER_MODULES
            )
            if not (
                WORKER_PATH / name
            ).is_file()
        ]

        self.assertFalse(
            missing,
            "Missing Worker modules: "
            + ", ".join(missing),
        )

    def test_expected_backend_modules_exist(self):
        missing = [
            name
            for name in sorted(
                EXPECTED_BACKEND_MODULES
            )
            if not (
                BACKEND_PATH / name
            ).is_file()
        ]

        self.assertFalse(
            missing,
            "Missing Worker backend modules: "
            + ", ".join(missing),
        )


class WorkerCompilationTests(unittest.TestCase):
    """Verify Worker Python sources compile."""

    def test_entry_compiles(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "py_compile",
                str(ENTRY_PATH),
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            result.returncode,
            0,
            (
                "src/entry.py failed compilation:\n"
                f"stdout={result.stdout}\n"
                f"stderr={result.stderr}"
            ),
        )

    def test_worker_modules_compile(self):
        failures = []

        for path in _python_files(
            WORKER_PATH
        ):
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
                        str(
                            path.relative_to(
                                PROJECT_ROOT
                            )
                        ),
                        result.stdout,
                        result.stderr,
                    )
                )

        self.assertFalse(
            failures,
            "Worker compilation failures:\n"
            + "\n".join(
                (
                    f"{path}\n"
                    f"stdout={stdout}\n"
                    f"stderr={stderr}"
                )
                for path, stdout, stderr in failures
            ),
        )

    def test_backend_modules_compile(self):
        failures = []

        for path in _python_files(
            BACKEND_PATH
        ):
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
                        str(
                            path.relative_to(
                                PROJECT_ROOT
                            )
                        ),
                        result.stdout,
                        result.stderr,
                    )
                )

        self.assertFalse(
            failures,
            "Worker backend compilation failures:\n"
            + "\n".join(
                (
                    f"{path}\n"
                    f"stdout={stdout}\n"
                    f"stderr={stderr}"
                )
                for path, stdout, stderr in failures
            ),
        )


class WorkerForbiddenDependencyTests(unittest.TestCase):
    """
    Ensure the current Worker runtime does not depend on the retired
    aiogram/SQLite runtime.
    """

    def _worker_source_files(self):
        return [
            ENTRY_PATH,
            *_python_files(WORKER_PATH),
            *_python_files(BACKEND_PATH),
        ]

    def test_worker_has_no_legacy_runtime_imports(self):
        violations = []

        for path in self._worker_source_files():
            source = path.read_text(
                encoding="utf-8"
            )

            for forbidden in FORBIDDEN_WORKER_TEXT:
                if forbidden in source:
                    violations.append(
                        (
                            str(
                                path.relative_to(
                                    PROJECT_ROOT
                                )
                            ),
                            forbidden,
                        )
                    )

        self.assertFalse(
            violations,
            (
                "Legacy runtime imports found in Worker source: "
                f"{violations}"
            ),
        )

    def test_worker_has_no_bot_db_reference(self):
        violations = []

        for path in self._worker_source_files():
            source = path.read_text(
                encoding="utf-8"
            )

            if "bot.db" in source:
                violations.append(
                    str(
                        path.relative_to(
                            PROJECT_ROOT
                        )
                    )
                )

        self.assertFalse(
            violations,
            (
                "Worker source references bot.db: "
                f"{violations}"
            ),
        )

    def test_worker_has_no_todo_markers(self):
        violations = []

        for path in self._worker_source_files():
            source = path.read_text(
                encoding="utf-8"
            )

            if "TODO" in source:
                violations.append(
                    str(
                        path.relative_to(
                            PROJECT_ROOT
                        )
                    )
                )

        self.assertFalse(
            violations,
            (
                "TODO markers remain in Worker source: "
                f"{violations}"
            ),
        )

    def test_worker_has_no_bare_pass_statements(self):
        violations = []

        for path in self._worker_source_files():
            tree = _parse(path)

            for node in ast.walk(tree):
                if isinstance(
                    node,
                    ast.Pass,
                ):
                    violations.append(
                        (
                            str(
                                path.relative_to(
                                    PROJECT_ROOT
                                )
                            ),
                            node.lineno,
                        )
                    )

        self.assertFalse(
            violations,
            (
                "Bare pass statements remain in Worker source: "
                f"{violations}"
            ),
        )


class EntryPointTests(unittest.TestCase):
    """Verify the Worker entry point remains thin and explicit."""

    @classmethod
    def setUpClass(cls):
        cls.source = ENTRY_PATH.read_text(
            encoding="utf-8"
        )

        cls.tree = _parse(
            ENTRY_PATH
        )

    def test_entry_defines_worker_fetch_path(self):
        functions = _defined_functions(
            self.tree
        )

        self.assertIn(
            "fetch",
            functions,
            "src/entry.py must define fetch().",
        )

    def test_entry_defines_worker_class(self):
        class_names = {
            node.name
            for node in ast.walk(
                self.tree
            )
            if isinstance(
                node,
                ast.ClassDef,
            )
        }

        self.assertIn(
            "ArzanKadehWorker",
            class_names,
            "ArzanKadehWorker is missing from entry.py.",
        )

    def test_entry_imports_worker_modules(self):
        required_modules = {
            "worker.start",
            "worker.messages",
            "worker.seller",
            "worker.report",
            "worker.store_status",
            "worker.admin",
        }

        imported = set()

        for node in self.tree.body:
            if isinstance(
                node,
                ast.ImportFrom,
            ):
                if node.module:
                    imported.add(
                        node.module
                    )

            elif isinstance(
                node,
                ast.Import,
            ):
                for alias in node.names:
                    imported.add(
                        alias.name
                    )

        missing = sorted(
            required_modules - imported
        )

        self.assertFalse(
            missing,
            (
                "entry.py does not import required Worker modules: "
                f"{missing}"
            ),
        )

    def test_entry_contains_no_aiogram(self):
        self.assertNotIn(
            "aiogram",
            self.source,
        )

    def test_entry_contains_no_sqlite_runtime_import(self):
        self.assertNotIn(
            "sqlite3",
            self.source,
        )

        self.assertNotIn(
            "aiosqlite",
            self.source,
        )


class DatabaseBackendContractTests(unittest.TestCase):
    """Verify the Worker backend exposes the expected database contract."""

    def test_database_backend_defines_required_contract(self):
        path = (
            BACKEND_PATH
            / "database_backend.py"
        )

        tree = _parse(path)

        classes = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(
                node,
                ast.ClassDef,
            )
        }

        self.assertIn(
            "DatabaseBackend",
            classes,
        )

        source = path.read_text(
            encoding="utf-8"
        )

        for method_name in (
            "connect",
            "close",
            "execute",
            "fetchone",
            "fetchall",
            "executemany",
            "transaction",
        ):
            self.assertIn(
                f"def {method_name}",
                source,
                (
                    "DatabaseBackend is missing "
                    f"{method_name}()."
                ),
            )

    def test_d1_backend_defines_required_operations(self):
        path = (
            BACKEND_PATH
            / "d1_backend.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        for method_name in (
            "connect",
            "close",
            "execute",
            "fetchone",
            "fetchall",
            "executemany",
            "transaction",
        ):
            self.assertIn(
                f"def {method_name}",
                source,
                (
                    "D1Backend is missing "
                    f"{method_name}()."
                ),
            )

    def test_d1_backend_uses_d1_batch_for_writes(self):
        path = (
            BACKEND_PATH
            / "d1_backend.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "await self._database.batch",
            source,
        )

        self.assertIn(
            "await database.batch",
            source,
        )

    def test_d1_backend_does_not_use_sqlite(self):
        path = (
            BACKEND_PATH
            / "d1_backend.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            "sqlite3",
            source,
        )

        self.assertNotIn(
            "aiosqlite",
            source,
        )


class WorkerDatabaseUsageTests(unittest.TestCase):
    """
    Ensure Worker application modules use the backend abstraction instead
    of direct SQLite APIs.
    """

    def test_worker_modules_do_not_call_sqlite_apis(self):
        violations = []

        for path in _python_files(
            WORKER_PATH
        ):
            source = path.read_text(
                encoding="utf-8"
            )

            forbidden = (
                "sqlite3.",
                "aiosqlite.",
                "sqlite_backend",
                "bot.database",
            )

            for token in forbidden:
                if token in source:
                    violations.append(
                        (
                            str(
                                path.relative_to(
                                    PROJECT_ROOT
                                )
                            ),
                            token,
                        )
                    )

        self.assertFalse(
            violations,
            (
                "Worker modules contain direct SQLite "
                f"references: {violations}"
            ),
        )

    def test_worker_modules_use_database_backend_methods(self):
        database_methods = (
            ".execute(",
            ".fetchone(",
            ".fetchall(",
            ".executemany(",
            ".transaction(",
        )

        violations = []

        for path in _python_files(
            WORKER_PATH
        ):
            source = path.read_text(
                encoding="utf-8"
            )

            if any(
                method in source
                for method in database_methods
            ):
                continue

            if path.name in {
                "telegram.py",
                "webhook.py",
            }:
                continue

            violations.append(
                str(
                    path.relative_to(
                        PROJECT_ROOT
                    )
                )
            )

        self.assertFalse(
            violations,
            (
                "Worker modules contain no recognizable "
                "DatabaseBackend operations: "
                f"{violations}"
            ),
        )


class CallbackRouteTests(unittest.TestCase):
    """Verify important callback routes remain wired in entry.py."""

    @classmethod
    def setUpClass(cls):
        cls.source = ENTRY_PATH.read_text(
            encoding="utf-8"
        )

    def test_seller_contact_routes_exist(self):
        for callback_prefix in (
            "igclick:",
            "tgclick:",
            "waclick:",
        ):
            self.assertIn(
                callback_prefix,
                self.source,
            )

        for handler_name in (
            "handle_instagram_click",
            "handle_telegram_click",
            "handle_whatsapp_click",
        ):
            self.assertIn(
                handler_name,
                self.source,
            )

    def test_store_toggle_route_exists(self):
        self.assertIn(
            'data.startswith("storetoggle:")',
            self.source,
        )

        self.assertIn(
            "handle_store_toggle_active",
            self.source,
        )

    def test_admin_request_route_exists(self):
        self.assertIn(
            'data.startswith("adminreq:")',
            self.source,
        )

        self.assertIn(
            "handle_admin_request_decision",
            self.source,
        )

    def test_admin_report_route_exists(self):
        self.assertIn(
            'data.startswith("adminreport:")',
            self.source,
        )

        self.assertIn(
            "handle_admin_report_decision",
            self.source,
        )

    def test_unknown_callback_fallback_exists(self):
        self.assertIn(
            "⚠️ این گزینه هنوز فعال نیست.",
            self.source,
        )

        self.assertIn(
            "show_alert=True",
            self.source,
        )


class SellerAndReviewSafetyTests(unittest.TestCase):
    """Verify important inactive-target safety checks remain present."""

    def test_seller_module_checks_owner_and_active_status(self):
        path = (
            WORKER_PATH
            / "seller.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "owner_user_id",
            source,
        )

        self.assertIn(
            "created_by_user_id",
            source,
        )

        self.assertIn(
            "is_active",
            source,
        )

    def test_review_module_checks_active_status(self):
        path = (
            WORKER_PATH
            / "review.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "is_active",
            source,
        )

        self.assertIn(
            "COALESCE",
            source,
        )

    def test_report_module_contains_admin_decision_flow(self):
        path = (
            WORKER_PATH
            / "report.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "handle_admin_report_decision",
            source,
        )

        self.assertIn(
            "adminreport:approve:",
            source,
        )

        self.assertIn(
            "adminreport:reject:",
            source,
        )


class SupportFlowTests(unittest.TestCase):
    """Verify support request flow contains the required admin handoff."""

    def test_support_module_accepts_environment(self):
        path = (
            WORKER_PATH
            / "support.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "env: Any",
            source,
        )

    def test_support_module_uses_admin_chat_id(self):
        path = (
            WORKER_PATH
            / "support.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "ADMIN_CHAT_ID",
            source,
        )

    def test_support_module_contains_admin_decision_callbacks(self):
        path = (
            WORKER_PATH
            / "support.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "adminreq:approve:",
            source,
        )

        self.assertIn(
            "adminreq:reject:",
            source,
        )


class SourceQualityTests(unittest.TestCase):
    """General source-level checks for the current Worker."""

    def test_worker_files_have_no_wildcard_imports(self):
        violations = []

        roots = (
            SRC_PATH,
        )

        for root in roots:
            for path in _python_files(root):
                tree = _parse(path)

                for node in ast.walk(tree):
                    if not isinstance(
                        node,
                        ast.ImportFrom,
                    ):
                        continue

                    if any(
                        alias.name == "*"
                        for alias in node.names
                    ):
                        violations.append(
                            str(
                                path.relative_to(
                                    PROJECT_ROOT
                                )
                            )
                        )

        self.assertFalse(
            violations,
            (
                "Wildcard imports found in Worker source: "
                f"{violations}"
            ),
        )

    def test_worker_source_does_not_use_runtime_exec(self):
        violations = []

        for path in _python_files(
            SRC_PATH
        ):
            source = path.read_text(
                encoding="utf-8"
            )

            tree = _parse(path)

            for node in ast.walk(tree):
                if not isinstance(
                    node,
                    ast.Call,
                ):
                    continue

                if not isinstance(
                    node.func,
                    ast.Name,
                ):
                    continue

                if node.func.id in {
                    "eval",
                    "exec",
                }:
                    violations.append(
                        (
                            str(
                                path.relative_to(
                                    PROJECT_ROOT
                                )
                            ),
                            node.func.id,
                        )
                    )

        self.assertFalse(
            violations,
            (
                "Runtime eval/exec usage found: "
                f"{violations}"
            ),
        )

    def test_entry_uses_d1_binding(self):
        source = ENTRY_PATH.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "env.DB",
            source,
        )

        self.assertIn(
            "D1Backend",
            source,
        )

    def test_entry_routes_webhook_processing(self):
        source = ENTRY_PATH.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "handle_webhook",
            source,
        )

    def test_telegram_client_is_worker_specific(self):
        path = (
            WORKER_PATH
            / "telegram.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "BOT_TOKEN",
            source,
        )

        self.assertIn(
            "api.telegram.org",
            source,
        )

        self.assertNotIn(
            "aiogram",
            source,
        )


if __name__ == "__main__":
    unittest.main()