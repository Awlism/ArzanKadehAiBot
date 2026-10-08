# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker test import helper.

This helper loads names directly from the current Cloudflare Worker
modules under src/worker.

It intentionally does not import the legacy bot package.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


NAME_MODULES = {
    # Search
    "StructuredQuery": "worker.search",
    "LocalQueryParser": "worker.search",
    "normalize_persian_text": "worker.search",
    "_remove_stopwords": "worker.search",
    "_convert_number_unit": "worker.search",
    "_extract_price": "worker.search",
    "_PERSIAN_DIGITS": "worker.search",
    "_ARABIC_DIGITS": "worker.search",
    "_ASCII_DIGITS": "worker.search",
    "_PUNCTUATION_CHARS": "worker.search",
    "_GENDER_WORD_MAP": "worker.search",
    "_COLOR_WORDS": "worker.search",
    "_STOPWORDS": "worker.search",
    "_PRICE_UNIT_RE": "worker.search",
    "_PRICE_RANGE_RE": "worker.search",
    "_PRICE_MAX_RE": "worker.search",
    "_PRICE_MIN_RE": "worker.search",
    "build_search_summary": "worker.search",
    "format_price": "worker.search",

    # Referrals
    "REFERRAL_MILESTONES": "worker.referrals",
    "build_referral_link": "worker.referrals",
    "get_referral_count": "worker.referrals",
    "next_referral_milestone": "worker.referrals",
    "record_referral_if_new": "worker.referrals",
    "get_sellers_owned_by_user": "worker.referrals",
}


def get_module(module_name: str):
    """Import a current Worker module."""
    if not module_name.startswith("worker."):
        raise AssertionError(
            f"Only Worker modules are supported: {module_name}"
        )

    return importlib.import_module(module_name)


def extract_names(names):
    """
    Return requested names from the current Worker modules.

    This keeps the old test helper API so tests can remain simple while
    completely removing dependency on bot/*.
    """
    namespace = {}

    missing = []

    for name in names:
        module_name = NAME_MODULES.get(name)

        if module_name is None:
            missing.append(name)
            continue

        module = get_module(module_name)

        if not hasattr(module, name):
            missing.append(name)
            continue

        namespace[name] = getattr(module, name)

    if missing:
        raise AssertionError(
            "Could not find requested names in the current Worker "
            f"source tree: {sorted(missing)}"
        )

    return namespace


def get_source_text(module_name: str) -> str:
    """Return source text for a current Worker module."""
    if not module_name.startswith("worker."):
        raise AssertionError(
            f"Only Worker modules are supported: {module_name}"
        )

    module = importlib.import_module(module_name)

    path = Path(module.__file__)

    return path.read_text(
        encoding="utf-8"
    )


def get_module_path(module_name: str) -> Path:
    """Return the filesystem path of a current Worker module."""
    if not module_name.startswith("worker."):
        raise AssertionError(
            f"Only Worker modules are supported: {module_name}"
        )

    module = importlib.import_module(module_name)

    return Path(module.__file__)