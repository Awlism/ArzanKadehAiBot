# -*- coding: utf-8 -*-
"""
Test helper: pulls specific module-level names (constants / pure functions)
out of bot.py using the `ast` module and executes ONLY those nodes in an
isolated namespace.

Why this exists
----------------
bot.py's top-level imports include `aiogram` and `aiosqlite`. In some
environments (including the one this project was built in) those packages
cannot be installed because there is no network access. A plain
`import bot` would therefore fail immediately with ModuleNotFoundError,
even though most of bot.py's logic (schema SQL, seed data, small pure
utility functions) has nothing to do with Telegram or async I/O at all.

This helper parses bot.py's source with `ast`, picks out only the
top-level assignments / function defs the caller asks for, and execs
just those nodes into a fresh dict. That lets the test suite verify the
real SQL/seed data/utility logic that ships in bot.py, without needing
aiogram or aiosqlite to be installed.

This is NOT a substitute for running the bot for real -- it cannot
exercise Telegram handlers, FSM transitions at runtime, or actual
aiosqlite I/O. See tests/test_static_analysis.py for source-level
handler/callback checks, and the final report for exactly what is and
isn't covered.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BOT_PY_PATH = Path(__file__).resolve().parent.parent / "bot.py"


def get_source_text() -> str:
    return BOT_PY_PATH.read_text(encoding="utf-8")


def extract_names(names) -> dict:
    """Return a namespace containing only the requested top-level names
    from bot.py (plus a few safe stdlib helpers pure functions rely on).
    """
    source = get_source_text()
    tree = ast.parse(source, filename=str(BOT_PY_PATH))

    ns: dict = {
        "Optional": Optional,
        "datetime": datetime,
        "timezone": timezone,
    }

    wanted = set(names)
    found = set()

    for node in tree.body:
        matched = False
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(t in wanted for t in targets):
                matched = True
                found.update(t for t in targets if t in wanted)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in wanted:
                matched = True
                found.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in wanted:
                matched = True
                found.add(node.name)

        if matched:
            module = ast.Module(body=[node], type_ignores=[])
            code = compile(module, filename=str(BOT_PY_PATH), mode="exec")
            exec(code, ns)  # noqa: S102 - controlled, test-only AST subset

    missing = wanted - found
    if missing:
        raise AssertionError(
            f"Could not find the following top-level names in bot.py: {sorted(missing)}"
        )
    return ns
