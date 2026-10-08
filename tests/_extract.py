# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Current Worker test import helper.

This helper only works with modules under src/worker.
It intentionally has no dependency on the legacy bot package.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def get_module(module_name: str):
    """
    Import a current Worker module.

    Only worker.* modules are accepted.
    """
    if not module_name.startswith("worker."):
        raise AssertionError(
            "Only current Worker modules are supported: "
            f"{module_name}"
        )

    return importlib.import_module(
        module_name
    )


def get_module_path(module_name: str) -> Path:
    """Return the filesystem path of a Worker module."""
    module = get_module(
        module_name
    )

    filename = getattr(
        module,
        "__file__",
        None,
    )

    if not filename:
        raise AssertionError(
            f"Worker module has no source file: {module_name}"
        )

    return Path(filename)


def get_source_text(module_name: str) -> str:
    """Read source text from a current Worker module."""
    path = get_module_path(
        module_name
    )

    return path.read_text(
        encoding="utf-8"
    )


def extract_names(
    names,
    *,
    module_name: str | None = None,
):
    """
    Return requested names from a current Worker module.

    When module_name is omitted, each name must be qualified as:

        "worker.search:normalize_persian_text"

    This avoids maintaining a stale legacy name-to-bot-path map.
    """
    namespace = {}

    for name in names:
        if ":" not in name:
            raise AssertionError(
                "Worker test names must be qualified as "
                "'worker.module:name'. "
                f"Received: {name}"
            )

        qualified_module, attribute = name.split(
            ":",
            1,
        )

        if module_name is not None:
            qualified_module = module_name

        module = get_module(
            qualified_module
        )

        if not hasattr(
            module,
            attribute,
        ):
            raise AssertionError(
                "Name not found in current Worker module: "
                f"{qualified_module}:{attribute}"
            )

        namespace[attribute] = getattr(
            module,
            attribute,
        )

    return namespace


def worker_source_path(relative_path: str) -> Path:
    """
    Resolve a path below src/worker.

    This function prevents accidental access to bot/*.
    """
    path = (
        SRC_ROOT
        / "worker"
        / relative_path
    ).resolve()

    worker_root = (
        SRC_ROOT
        / "worker"
    ).resolve()

    if (
        path != worker_root
        and worker_root not in path.parents
    ):
        raise AssertionError(
            "Path escapes src/worker: "
            f"{relative_path}"
        )

    return path