# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker admin report notification contract tests.

These tests inspect source contracts only.
They do not contact Telegram or D1.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

REPORT_FILE = SRC_ROOT / "worker" / "report.py"
MESSAGES_FILE = SRC_ROOT / "worker" / "messages.py"
ENTRY_FILE = SRC_ROOT / "entry.py"


def _read(path: Path) -> str:
    return path.read_text(
        encoding="utf-8"
    )


def _tree(path: Path) -> ast.AST:
    return ast.parse(
        _read(path),
        filename=str(path),
    )


def _function(
    path: Path,
    name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(_tree(path)):
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ) and node.name == name:
            return node

    raise AssertionError(
        f"Function {name!r} not found in {path}"
    )


def _source(
    path: Path,
    name: str,
) -> str:
    result = ast.get_source_segment(
        _read(path),
        _function(path, name),
    )

    if result is None:
        raise AssertionError(
            f"Could not read function {name!r}"
        )

    return result


def _normalized(value: str) -> str:
    return " ".join(
        value.split()
    ).lower()


class WorkerReportAdminNotificationContractTests(
    unittest.TestCase
):
    def test_admin_notification_uses_shared_chat_id_helper(
        self,
    ):
        source = _normalized(
            _source(
                REPORT_FILE,
                "_notify_admin_new_report",
            )
        )

        self.assertIn(
            "get_admin_chat_id(env)",
            source,
        )

        self.assertIn(
            "if admin_chat_id is none:",
            source,
        )

        self.assertNotIn(
            "if admin_chat_id < 1:",
            source,
        )

    def test_admin_notification_contains_report_details(
        self,
    ):
        source = _normalized(
            _source(
                REPORT_FILE,
                "_notify_admin_new_report",
            )
        )

        for expected in (
            "report_id",
            "target_type",
            "target_id",
            "reason_code",
            "description",
            "reporter_label",
            "user_id",
        ):
            with self.subTest(
                field=expected
            ):
                self.assertIn(
                    expected,
                    source,
                )

    def test_notification_has_approve_and_reject_actions(
        self,
    ):
        source = _normalized(
            _source(
                REPORT_FILE,
                "_notify_admin_new_report",
            )
        )

        self.assertIn(
            "adminreport:approve:",
            source,
        )

        self.assertIn(
            "adminreport:reject:",
            source,
        )

        self.assertIn(
            "reply_markup=keyboard",
            source,
        )

    def test_notification_uses_html_escaping(
        self,
    ):
        source = _normalized(
            _source(
                REPORT_FILE,
                "_notify_admin_new_report",
            )
        )

        self.assertIn(
            "_html(",
            source,
        )

        self.assertIn(
            'parse_mode="html"',
            source,
        )

    def test_notification_failure_does_not_escape_helper(
        self,
    ):
        source = _normalized(
            _source(
                REPORT_FILE,
                "_notify_admin_new_report",
            )
        )

        self.assertIn(
            "except exception:",
            source,
        )

        self.assertIn(
            "# the report is already saved.",
            source,
        )

    def test_skip_handler_accepts_environment(
        self,
    ):
        source = _normalized(
            _source(
                REPORT_FILE,
                "handle_report_skip",
            )
        )

        self.assertIn(
            "env: optional[Any] = none",
            source,
        )

    def test_skip_handler_notifies_admin_after_save(
        self,
    ):
        source = _normalized(
            _source(
                REPORT_FILE,
                "handle_report_skip",
            )
        )

        self.assertIn(
            "_complete_report(",
            source,
        )

        self.assertIn(
            "_notify_admin_new_report(",
            source,
        )

        self.assertIn(
            "env=env",
            source,
        )

    def test_text_handler_accepts_environment(
        self,
    ):
        source = _normalized(
            _source(
                REPORT_FILE,
                "handle_report_text",
            )
        )

        self.assertIn(
            "env: optional[Any] = none",
            source,
        )

    def test_text_handler_notifies_admin_after_save(
        self,
    ):
        source = _normalized(
            _source(
                REPORT_FILE,
                "handle_report_text",
            )
        )

        self.assertIn(
            "_complete_report(",
            source,
        )

        self.assertIn(
            "_notify_admin_new_report(",
            source,
        )

        self.assertIn(
            "env=env",
            source,
        )

        self.assertIn(
            "description=description",
            source,
        )

    def test_message_router_passes_environment_to_report(
        self,
    ):
        source = _normalized(
            _source(
                MESSAGES_FILE,
                "_handle_active_state",
            )
        )

        self.assertIn(
            'if state_name == "report:waiting_description":',
            source,
        )

        self.assertIn(
            "handle_report_text( message, telegram, env, )",
            source,
        )

    def test_entry_passes_environment_to_skip_handler(
        self,
    ):
        source = _read(
            ENTRY_FILE
        )

        tree = ast.parse(source)

        found = False

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

            if node.func.id != "handle_report_skip":
                continue

            if len(node.args) < 3:
                continue

            third_arg = node.args[2]

            if (
                isinstance(
                    third_arg,
                    ast.Name,
                )
                and third_arg.id == "env"
            ):
                found = True
                break

        self.assertTrue(
            found,
            "handle_report_skip must receive env",
        )

    def test_entry_routes_admin_report_decisions(
        self,
    ):
        source = _normalized(
            _read(ENTRY_FILE)
        )

        self.assertIn(
            'data.startswith("adminreport:")',
            source,
        )

        self.assertIn(
            "handle_admin_report_decision(",
            source,
        )

        self.assertIn(
            "callback_query, telegram, env,",
            source,
        )


if __name__ == "__main__":
    unittest.main()