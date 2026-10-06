# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker review/report contract tests.

These tests verify the migrated review and report flows,
including identity scoping, state handling, target validation,
duplicate prevention, and D1 transaction compatibility.

These are source-contract tests only.
They do not contact Telegram or D1.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src" / "worker"

REVIEW_FILE = SRC_ROOT / "review.py"
REPORT_FILE = SRC_ROOT / "report.py"

FORBIDDEN_IMPORT_ROOTS = {
    "aiogram",
    "sqlite3",
    "aiosqlite",
}


def _read(path: Path) -> str:
    return path.read_text(
        encoding="utf-8"
    )


def _normalized(value: str) -> str:
    return " ".join(
        value.split()
    ).lower()


def _tree(path: Path) -> ast.AST:
    return ast.parse(
        _read(path),
        filename=str(path),
    )


def _functions(
    path: Path,
) -> list[
    ast.AsyncFunctionDef | ast.FunctionDef
]:
    result = []

    for node in ast.walk(
        _tree(path)
    ):
        if isinstance(
            node,
            (
                ast.AsyncFunctionDef,
                ast.FunctionDef,
            ),
        ):
            result.append(node)

    return result


def _function_source(
    path: Path,
    name: str,
) -> str:
    source = _read(path)

    for node in _functions(path):
        if node.name != name:
            continue

        result = ast.get_source_segment(
            source,
            node,
        )

        if result is None:
            raise AssertionError(
                f"Could not extract function {name!r}"
            )

        return result

    raise AssertionError(
        f"Function {name!r} not found in {path}"
    )


def _imports(
    path: Path,
) -> list[str]:
    imports: list[str] = []

    for node in ast.walk(
        _tree(path)
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            imports.extend(
                alias.name
                for alias in node.names
            )

        elif isinstance(
            node,
            ast.ImportFrom,
        ):
            if node.module:
                imports.append(
                    node.module
                )

    return imports


class WorkerReviewReportContractTests(
    unittest.TestCase
):
    def test_review_uses_internal_user_id(
        self,
    ):
        source = _read(
            REVIEW_FILE
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "select id",
            normalized,
        )

        self.assertIn(
            "from users",
            normalized,
        )

        self.assertIn(
            "where telegram_id = ?",
            normalized,
        )

    def test_report_uses_internal_user_id(
        self,
    ):
        source = _read(
            REPORT_FILE
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "select id",
            normalized,
        )

        self.assertIn(
            "from users",
            normalized,
        )

        self.assertIn(
            "where telegram_id = ?",
            normalized,
        )

    def test_review_duplicate_check_is_user_scoped(
        self,
    ):
        source = _function_source(
            REVIEW_FILE,
            "_has_existing_review",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "from reviews",
            normalized,
        )

        self.assertIn(
            "where user_id = ?",
            normalized,
        )

        self.assertIn(
            "product_id = ?",
            normalized,
        )

        self.assertIn(
            "seller_id = ?",
            normalized,
        )

    def test_review_product_and_seller_targets_are_distinct(
        self,
    ):
        source = _function_source(
            REVIEW_FILE,
            "_has_existing_review",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "seller_id is null",
            normalized,
        )

        self.assertIn(
            "product_id is null",
            normalized,
        )

    def test_review_state_is_persistent(
        self,
    ):
        source = _read(
            REVIEW_FILE
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "set_state",
            normalized,
        )

        self.assertIn(
            "get_state",
            normalized,
        )

        self.assertIn(
            "clear_state",
            normalized,
        )

        self.assertIn(
            "review:waiting_rating",
            normalized,
        )

        self.assertIn(
            "review:waiting_text",
            normalized,
        )

    def test_review_insert_contains_user_and_target(
        self,
    ):
        source = _function_source(
            REVIEW_FILE,
            "handle_review_text",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "insert into reviews",
            normalized,
        )

        self.assertIn(
            "user_id",
            normalized,
        )

        self.assertIn(
            "seller_id",
            normalized,
        )

        self.assertIn(
            "product_id",
            normalized,
        )

        self.assertIn(
            "rating",
            normalized,
        )

        self.assertIn(
            "text",
            normalized,
        )

    def test_review_write_is_transactional(
        self,
    ):
        source = _function_source(
            REVIEW_FILE,
            "handle_review_text",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "backend.transaction",
            normalized,
        )

        self.assertIn(
            "insert into reviews",
            normalized,
        )

        self.assertIn(
            "insert into events",
            normalized,
        )

        self.assertIn(
            "delete from worker_states",
            normalized,
        )

    def test_report_target_validation_supports_product_and_seller(
        self,
    ):
        source = _function_source(
            REPORT_FILE,
            "_target_exists",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "from sellers",
            normalized,
        )

        self.assertIn(
            "from products",
            normalized,
        )

    def test_report_duplicate_check_is_user_scoped(
        self,
    ):
        source = _function_source(
            REPORT_FILE,
            "_has_open_report",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "from reports",
            normalized,
        )

        self.assertIn(
            "where user_id = ?",
            normalized,
        )

        self.assertIn(
            "status = 'pending'",
            normalized,
        )

    def test_report_duplicate_check_is_target_scoped(
        self,
    ):
        source = _function_source(
            REPORT_FILE,
            "_has_open_report",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "seller_id = ?",
            normalized,
        )

        self.assertIn(
            "product_id = ?",
            normalized,
        )

    def test_report_insert_contains_user_and_target(
        self,
    ):
        source = _function_source(
            REPORT_FILE,
            "_save_report",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "insert into reports",
            normalized,
        )

        self.assertIn(
            "user_id",
            normalized,
        )

        self.assertIn(
            "seller_id",
            normalized,
        )

        self.assertIn(
            "product_id",
            normalized,
        )

        self.assertIn(
            "reason",
            normalized,
        )

        self.assertIn(
            "description",
            normalized,
        )

    def test_report_insert_is_transactional(
        self,
    ):
        source = _function_source(
            REPORT_FILE,
            "_save_report",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "backend.transaction",
            normalized,
        )

        self.assertIn(
            "insert into reports",
            normalized,
        )

        self.assertIn(
            "insert into events",
            normalized,
        )

        self.assertIn(
            "insert into audit_log",
            normalized,
        )

    def test_report_transaction_does_not_use_queued_lastrowid(
        self,
    ):
        """
        D1Transaction.execute() queues writes and returns a
        placeholder DatabaseResult without a usable lastrowid.

        Therefore report creation must not depend on:
            transaction.execute(...).lastrowid

        The migrated implementation should obtain the report
        id after commit or use another D1-compatible strategy.
        """

        source = _function_source(
            REPORT_FILE,
            "_save_report",
        )

        normalized = _normalized(
            source
        )

        self.assertNotRegex(
            normalized,
            r"\bresult\s*\.\s*last_row_id\b",
        )

        self.assertNotRegex(
            normalized,
            r"\bresult\s*\.\s*lastrowid\b",
        )

    def test_report_state_is_persistent(
        self,
    ):
        source = _read(
            REPORT_FILE
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "set_state",
            normalized,
        )

        self.assertIn(
            "get_state",
            normalized,
        )

        self.assertIn(
            "clear_state",
            normalized,
        )

        self.assertIn(
            "report:waiting_description",
            normalized,
        )

    def test_report_state_contains_target_and_reason(
        self,
    ):
        source = _function_source(
            REPORT_FILE,
            "handle_report_reason",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "target_type",
            normalized,
        )

        self.assertIn(
            "target_id",
            normalized,
        )

        self.assertIn(
            "reason_code",
            normalized,
        )

        self.assertIn(
            "set_state",
            normalized,
        )

    def test_report_completion_rechecks_target(
        self,
    ):
        source = _function_source(
            REPORT_FILE,
            "_complete_report",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "_target_exists",
            normalized,
        )

        self.assertIn(
            "_has_open_report",
            normalized,
        )

    def test_review_completion_rechecks_target_and_duplicate(
        self,
    ):
        source = _function_source(
            REVIEW_FILE,
            "handle_review_text",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "_get_target",
            normalized,
        )

        self.assertIn(
            "_has_existing_review",
            normalized,
        )

    def test_review_and_report_have_no_legacy_imports(
        self,
    ):
        for path in (
            REVIEW_FILE,
            REPORT_FILE,
        ):
            for imported in _imports(path):
                root = imported.split(
                    ".",
                    1,
                )[0]

                self.assertNotIn(
                    root,
                    FORBIDDEN_IMPORT_ROOTS,
                    f"Legacy import {imported!r} in {path}",
                )

    def test_review_rating_is_bounded(
        self,
    ):
        source = _function_source(
            REVIEW_FILE,
            "_parse_review_rate",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "rating < 1",
            normalized,
        )

        self.assertIn(
            "rating > 5",
            normalized,
        )

    def test_report_reason_must_be_known(
        self,
    ):
        source = _function_source(
            REPORT_FILE,
            "_parse_report_reason",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "reason_code",
            normalized,
        )

        self.assertIn(
            "report_reasons",
            normalized,
        )

    def test_report_status_is_pending_on_creation(
        self,
    ):
        source = _function_source(
            REPORT_FILE,
            "_save_report",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "'pending'",
            normalized,
        )


if __name__ == "__main__":
    unittest.main()