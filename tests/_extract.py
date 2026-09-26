# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Test extraction helper for the modular architecture.

This helper lets offline tests extract selected constants, classes and
pure/helper functions directly from the real modular source files without
importing the whole Telegram application.

The old project stored most test targets in bot.py. The project is now
modular, so extraction must resolve names from their actual modules.
"""

from __future__ import annotations

import ast
import datetime
import logging
import re
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent


MODULE_PATHS = {
    "constants": PROJECT_ROOT / "bot" / "constants.py",
    "database": PROJECT_ROOT / "bot" / "database.py",
    "repositories": PROJECT_ROOT / "bot" / "repositories.py",
    "utils": PROJECT_ROOT / "bot" / "utils.py",
    "search": PROJECT_ROOT / "bot" / "handlers" / "search.py",
    "navigation": PROJECT_ROOT / "bot" / "handlers" / "navigation.py",
    "products": PROJECT_ROOT / "bot" / "handlers" / "products.py",
    "sellers": PROJECT_ROOT / "bot" / "handlers" / "sellers.py",
    "favorites": PROJECT_ROOT / "bot" / "handlers" / "favorites.py",
    "compare": PROJECT_ROOT / "bot" / "handlers" / "compare.py",
    "orders": PROJECT_ROOT / "bot" / "handlers" / "orders.py",
    "notifications": PROJECT_ROOT / "bot" / "services" / "notifications.py",
    "referrals": PROJECT_ROOT / "bot" / "services" / "referrals.py",
    "admin": PROJECT_ROOT / "bot" / "handlers" / "admin.py",
    "account": PROJECT_ROOT / "bot" / "handlers" / "account.py",
}


SAFE_GLOBALS = {
    "datetime": datetime.datetime,
    "timezone": timezone,
    "Optional": Optional,
    "re": re,
    "urlparse": urlparse,
    "dataclass": dataclass,
    "field": field,
    "logging": logging,
}


NAME_MODULES = {
    # ------------------------------------------------------------------
    # constants
    # ------------------------------------------------------------------
    "ROLE_BUYER": "constants",
    "ROLE_SELLER": "constants",
    "ROLE_ADMIN": "constants",
    "VALID_MODES": "constants",
    "SELLER_PENDING": "constants",
    "SELLER_APPROVED": "constants",
    "SELLER_REJECTED": "constants",
    "SELLER_SUSPENDED": "constants",
    "VALID_SELLER_STATES": "constants",
    "PAGE_SIZE_CATEGORIES": "constants",
    "PAGE_SIZE_LIST": "constants",
    "TOP_LIST_LIMIT": "constants",
    "SUPPORT_MESSAGE_MAX_LEN": "constants",
    "COMPARE_MAX_ITEMS": "constants",
    "SHOP_EDITABLE_FIELDS": "constants",
    "SHOP_UPDATE_QUERIES": "constants",
    "PRODUCT_EDITABLE_FIELDS": "constants",
    "PRODUCT_UPDATE_QUERIES": "constants",
    "EVENT_START": "constants",
    "EVENT_SEARCH": "constants",
    "EVENT_PRODUCT_VIEW": "constants",
    "EVENT_SELLER_VIEW": "constants",
    "EVENT_FAVORITE_ADD": "constants",
    "EVENT_FAVORITE_REMOVE": "constants",
    "EVENT_COMPARE_ADD": "constants",
    "EVENT_COMPARE_REMOVE": "constants",
    "EVENT_ORDER_CREATE": "constants",
    "EVENT_ORDER_STATUS": "constants",
    "EVENT_CONTACT_SELLER": "constants",
    "EVENT_SUPPORT": "constants",
    "EVENT_AD_VIEW": "constants",
    "EVENT_AD_CLICK": "constants",
    "REFERRAL_REWARD_INVITER": "constants",
    "REFERRAL_REWARD_INVITEE": "constants",
    "REFERRAL_DEEP_LINK_PREFIX": "constants",
    "AD_TYPES": "constants",
    "STATUS_ACTIVE": "constants",
    "STATUS_INACTIVE": "constants",
    "STATUS_PENDING": "constants",
    "STATUS_APPROVED": "constants",
    "STATUS_REJECTED": "constants",
    "STATUS_RUNNING": "constants",
    "STATUS_COMPLETED": "constants",
    "STATUS_CANCELLED": "constants",
    "ADMIN_MODE_PLACEHOLDER_TEXT": "constants",
    "DATABASE_QUICK_CHECK_OK": "constants",
    "CALLBACK_PREFIX_CATEGORY": "constants",
    "CALLBACK_PREFIX_PRODUCT": "constants",
    "CALLBACK_PREFIX_SELLER": "constants",
    "CALLBACK_PREFIX_PAGE": "constants",
    "CALLBACK_PREFIX_COMPARE": "constants",
    "CALLBACK_PREFIX_FAVORITE": "constants",
    "CALLBACK_PREFIX_REQUEST": "constants",
    "CALLBACK_PREFIX_AD": "constants",
    "_UNSAFE_URL_CHARS": "constants",
    "_DANGEROUS_URL_SCHEME_PREFIXES": "constants",

    # ------------------------------------------------------------------
    # database
    # ------------------------------------------------------------------
    "Database": "database",
    "db": "database",
    "SCHEMA_STATEMENTS": "database",
    "INDEX_STATEMENTS": "database",
    "COLUMN_MIGRATIONS": "database",
    "CITY_NAMES": "database",
    "CATEGORY_TREE": "database",
    "DEMO_SELLER_NAME": "database",
    "DEMO_PRODUCT_NAME": "database",
    "ensure_column": "database",
    "run_column_migrations": "database",

    # ------------------------------------------------------------------
    # repositories
    # ------------------------------------------------------------------
    "ORDER_STATUSES": "repositories",

    # ------------------------------------------------------------------
    # search
    # ------------------------------------------------------------------
    "StructuredQuery": "search",
    "QueryParser": "search",
    "LocalQueryParser": "search",
    "SearchEngine": "search",
    "normalize_persian_text": "search",
    "build_search_summary": "search",
    "_extract_price": "search",
    "_convert_number_unit": "search",
    "_remove_stopwords": "search",
    "plain_keyword_search": "search",
    "ALT_CITY_SPELLINGS": "search",
    "CATEGORY_SYNONYMS": "search",
    "REFERRAL_DEEP_LINK_RE": "search",
    "_DIGIT_LETTER_MAP": "search",
    "_PERSIAN_DIGITS": "search",
    "_ARABIC_DIGITS": "search",
    "_ASCII_DIGITS": "search",
    "_PUNCTUATION_CHARS": "search",
    "_GENDER_WORD_MAP": "search",
    "_COLOR_WORDS": "search",
    "_STOPWORDS": "search",
    "_NORMALIZED_CITY_NAMES": "search",
    "_ALL_CATEGORY_NAMES": "search",
    "_SORTED_CATEGORY_NAMES": "search",
    "_NORMALIZED_COLOR_WORDS": "search",
    "_NORMALIZED_STOPWORDS": "search",
    "_STOPWORD_PHRASES": "search",
    "_STOPWORD_TOKENS": "search",
    "_PRICE_UNIT_RE": "search",
    "_PRICE_RANGE_RE": "search",
    "_PRICE_MAX_RE": "search",
    "_PRICE_MIN_RE": "search",

    # ------------------------------------------------------------------
    # utils
    # ------------------------------------------------------------------
    "now_iso": "utils",
    "parse_int": "utils",
    "format_price": "utils",
    "status_badge": "utils",
    "_normalize_url": "utils",
    "instagram_url": "utils",
    "telegram_url": "utils",
    "website_url": "utils",
    "whatsapp_url": "utils",
    "safe_edit": "utils",
    "ensure_user": "utils",
    "log_event": "utils",
    "log_audit": "utils",
    "is_admin_telegram_id": "utils",
    "send_admin_dm": "utils",
    "restart_requested": "utils",

    # ------------------------------------------------------------------
    # notifications
    # ------------------------------------------------------------------
    "notify_user": "notifications",

    # ------------------------------------------------------------------
    # referrals
    # ------------------------------------------------------------------
    "get_referral_count": "referrals",
    "get_sellers_owned_by_user": "referrals",
}


def _parse_module(module_name: str) -> ast.Module:
    path = MODULE_PATHS.get(module_name)

    if path is None:
        raise AssertionError(f"Unknown source module: {module_name}")

    if not path.exists():
        raise AssertionError(f"Source module does not exist: {path}")

    return ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )


def _top_level_nodes(module_name: str) -> dict[str, ast.AST]:
    tree = _parse_module(module_name)
    result: dict[str, ast.AST] = {}

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result[target.id] = node

        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                result[node.target.id] = node

        elif isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            result[node.name] = node

    return result


def _find_owner(name: str) -> str | None:
    explicit = NAME_MODULES.get(name)

    if explicit is not None:
        return explicit

    for module_name in MODULE_PATHS:
        if name in _top_level_nodes(module_name):
            return module_name

    return None


def _module_imports(module_name: str) -> dict[str, tuple[str, str]]:
    """
    Resolve project-local imports used by extracted nodes.
    """
    tree = _parse_module(module_name)
    result: dict[str, tuple[str, str]] = {}

    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue

        module = node.module or ""

        if "constants" in module:
            source_module = "constants"
        elif "database" in module:
            source_module = "database"
        elif "repositories" in module:
            source_module = "repositories"
        elif module.endswith(".utils") or module == "utils":
            source_module = "utils"
        elif module.endswith(".search") or module == "search":
            source_module = "search"
        elif module.endswith(".notifications"):
            source_module = "notifications"
        elif module.endswith(".referrals"):
            source_module = "referrals"
        elif module.endswith(".admin"):
            source_module = "admin"
        elif module.endswith(".account"):
            source_module = "account"
        elif module.endswith(".navigation"):
            source_module = "navigation"
        elif module.endswith(".products"):
            source_module = "products"
        elif module.endswith(".sellers"):
            source_module = "sellers"
        elif module.endswith(".favorites"):
            source_module = "favorites"
        elif module.endswith(".compare"):
            source_module = "compare"
        elif module.endswith(".orders"):
            source_module = "orders"
        else:
            continue

        for alias in node.names:
            if alias.name == "*":
                continue

            local_name = alias.asname or alias.name
            result[local_name] = (
                source_module,
                alias.name,
            )

    return result


def _compile_node(
    node: ast.AST,
    filename: str,
    namespace: dict,
) -> None:
    module = ast.Module(
        body=[node],
        type_ignores=[],
    )

    ast.fix_missing_locations(module)

    code = compile(
        module,
        filename=filename,
        mode="exec",
    )

    exec(code, namespace)


def _extract_from_module(
    module_name: str,
    name: str,
    namespace: dict,
    visiting: set[tuple[str, str]],
) -> bool:
    key = (module_name, name)

    if key in visiting:
        return False

    visiting.add(key)

    nodes = _top_level_nodes(module_name)
    node = nodes.get(name)

    if node is None:
        return False

    imports = _module_imports(module_name)

    referenced_names = {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name)
    }

    for referenced_name in referenced_names:
        imported = imports.get(referenced_name)

        if imported is None or referenced_name in namespace:
            continue

        source_module, source_name = imported

        _extract_from_module(
            source_module,
            source_name,
            namespace,
            visiting,
        )

        if source_name in namespace:
            namespace[referenced_name] = namespace[source_name]

    _compile_node(
        node,
        str(MODULE_PATHS[module_name]),
        namespace,
    )

    return name in namespace


def extract_names(names) -> dict:
    """
    Extract selected names from the modular project.
    """

    wanted = list(dict.fromkeys(names))
    namespace = dict(SAFE_GLOBALS)

    namespace.setdefault("datetime", datetime.datetime)

    missing = []

    for name in wanted:
        if name in namespace:
            continue

        owner = _find_owner(name)

        if owner is None:
            missing.append(name)
            continue

        if not _extract_from_module(
            owner,
            name,
            namespace,
            set(),
        ):
            missing.append(name)

    if missing:
        raise AssertionError(
            "Could not find or extract the following names "
            f"from the modular source tree: {sorted(missing)}"
        )

    return namespace


def get_source_text(module_name: str = "utils") -> str:
    """
    Return source text for a real modular source file.
    """

    path = MODULE_PATHS.get(module_name)

    if path is None:
        raise AssertionError(f"Unknown source module: {module_name}")

    return path.read_text(encoding="utf-8")


def get_module_path(module_name: str) -> Path:
    """
    Return the filesystem path of a registered project module.
    """

    path = MODULE_PATHS.get(module_name)

    if path is None:
        raise AssertionError(f"Unknown source module: {module_name}")

    return path