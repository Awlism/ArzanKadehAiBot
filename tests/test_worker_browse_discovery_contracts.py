# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker browse/discovery contract tests.

These tests inspect migrated Worker source and verify the contracts
that protect public browsing, discovery, favorites, search, ads,
notifications, profile, requests, statistics, and referrals.

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


FILES = {
    "categories": SRC_ROOT / "categories.py",
    "hot": SRC_ROOT / "hot.py",
    "discovery": SRC_ROOT / "discovery.py",
    "favorites": SRC_ROOT / "favorites.py",
    "search": SRC_ROOT / "search.py",
    "publicads": SRC_ROOT / "publicads.py",
    "notifications": SRC_ROOT / "notifications.py",
    "profile": SRC_ROOT / "profile.py",
    "requests": SRC_ROOT / "requests.py",
    "store_status": SRC_ROOT / "store_status.py",
    "product_stats": SRC_ROOT / "product_stats.py",
    "referrals": SRC_ROOT / "referrals.py",
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


def _functions(path: Path) -> list[
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
                f"Could not extract {name!r}"
            )

        return result

    raise AssertionError(
        f"Function {name!r} not found in {path}"
    )


def _all_source(
    *paths: Path,
) -> str:
    return "\n".join(
        _read(path)
        for path in paths
    )


def _imports(path: Path) -> list[str]:
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


class WorkerBrowseDiscoveryContractTests(
    unittest.TestCase
):
    def test_categories_use_parent_child_relationship(
        self,
    ):
        source = _all_source(
            FILES["categories"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "parent_id",
            normalized,
        )

        self.assertIn(
            "where parent_id is null",
            normalized,
        )

        self.assertIn(
            "where parent_id = ?",
            normalized,
        )

    def test_categories_query_products_by_category(
        self,
    ):
        source = _function_source(
            FILES["categories"],
            "_render_category_products",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "from products p",
            normalized,
        )

        self.assertIn(
            "p.category_id = ?",
            normalized,
        )

    def test_categories_show_only_active_sellers(
        self,
    ):
        source = _function_source(
            FILES["categories"],
            "_render_category_products",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "is_active",
            normalized,
        )

        self.assertIn(
            "coalesce(s.is_active, 1) = 1",
            normalized,
        )

    def test_hot_products_show_only_active_sellers(
        self,
    ):
        source = _all_source(
            FILES["hot"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "is_active",
            normalized,
        )

        self.assertTrue(
            (
                "coalesce(s.is_active, 1) = 1"
                in normalized
            )
            or (
                "s.is_active = 1"
                in normalized
            )
        )

    def test_hot_products_have_bounded_result_limit(
        self,
    ):
        source = _all_source(
            FILES["hot"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "top_list_limit",
            normalized,
        )

        self.assertIn(
            "limit",
            normalized,
        )

    def test_discovery_has_bounded_public_results(
        self,
    ):
        source = _all_source(
            FILES["discovery"]
        )

        normalized = _normalized(
            source
        )

        limit_constants = re.findall(
            r"\b[a-z_]*limit[a-z_]*\b\s*=\s*\d+",
            normalized,
        )

        self.assertTrue(
            limit_constants
            or "limit ?" in normalized
            or "limit " in normalized
        )

    def test_discovery_filters_inactive_sellers(
        self,
    ):
        source = _all_source(
            FILES["discovery"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "is_active",
            normalized,
        )

        self.assertTrue(
            (
                "coalesce(s.is_active, 1) = 1"
                in normalized
            )
            or (
                "s.is_active = 1"
                in normalized
            )
        )

    def test_favorites_are_user_scoped(
        self,
    ):
        source = _all_source(
            FILES["favorites"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "user_id",
            normalized,
        )

        self.assertIn(
            "favorites",
            normalized,
        )

        self.assertIn(
            "user_id = ?",
            normalized,
        )

    def test_favorite_removal_is_user_scoped(
        self,
    ):
        source = _all_source(
            FILES["favorites"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "delete from favorites",
            normalized,
        )

        self.assertIn(
            "user_id = ?",
            normalized,
        )

    def test_search_has_result_bound(
        self,
    ):
        source = _all_source(
            FILES["search"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "search_result_limit",
            normalized,
        )

        self.assertTrue(
            "limit" in normalized
        )

    def test_search_uses_product_and_seller_data(
        self,
    ):
        source = _all_source(
            FILES["search"]
        )

        normalized = _normalized(
            source
        )

        self.assertTrue(
            "products" in normalized
        )

        self.assertTrue(
            "sellers" in normalized
        )

    def test_public_ads_use_public_ad_state(
        self,
    ):
        source = _all_source(
            FILES["publicads"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "public_ad",
            normalized,
        )

    def test_public_ads_write_notifications_to_user(
        self,
    ):
        source = _all_source(
            FILES["publicads"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "notifications",
            normalized,
        )

        self.assertIn(
            "user_id",
            normalized,
        )

    def test_notifications_are_user_scoped(
        self,
    ):
        source = _all_source(
            FILES["notifications"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "from notifications",
            normalized,
        )

        self.assertIn(
            "user_id = ?",
            normalized,
        )

    def test_notification_read_update_is_user_scoped(
        self,
    ):
        source = _all_source(
            FILES["notifications"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "update notifications",
            normalized,
        )

        self.assertIn(
            "where",
            normalized,
        )

        self.assertIn(
            "user_id = ?",
            normalized,
        )

    def test_notification_list_has_limit(
        self,
    ):
        source = _all_source(
            FILES["notifications"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "notification_limit",
            normalized,
        )

        self.assertIn(
            "20",
            normalized,
        )

    def test_profile_resolves_internal_user(
        self,
    ):
        source = _all_source(
            FILES["profile"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "telegram_id",
            normalized,
        )

        self.assertIn(
            "select id",
            normalized,
        )

        self.assertIn(
            "from users",
            normalized,
        )

    def test_profile_does_not_depend_on_legacy_user_identity(
        self,
    ):
        source = _all_source(
            FILES["profile"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "telegram_id",
            normalized,
        )

        self.assertNotIn(
            "aiogram",
            normalized,
        )

    def test_requests_use_internal_user_id(
        self,
    ):
        source = _all_source(
            FILES["requests"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "user_id",
            normalized,
        )

        self.assertIn(
            "telegram_id",
            normalized,
        )

    def test_requests_use_request_type_column(
        self,
    ):
        source = _all_source(
            FILES["requests"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "request_type",
            normalized,
        )

        self.assertNotIn(
            "requests.type",
            normalized,
        )

    def test_store_status_is_user_owned(
        self,
    ):
        source = _all_source(
            FILES["store_status"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "owner_user_id",
            normalized,
        )

        self.assertIn(
            "created_by_user_id",
            normalized,
        )

        self.assertIn(
            "user_id = ?",
            normalized,
        )

    def test_product_stats_owned_product_is_user_scoped(
        self,
    ):
        source = _all_source(
            FILES["product_stats"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "_get_owned_product",
            normalized,
        )

        self.assertIn(
            "you do not have access"
            if False
            else "دسترسی ندارید",
            normalized,
        )

    def test_product_stats_favorite_count_is_product_scoped(
        self,
    ):
        source = _all_source(
            FILES["product_stats"]
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "from favorites",
            normalized,
        )

        self.assertIn(
            "product_id = ?",
            normalized,
        )

    def test_referrals_scope_owned_sellers(
        self,
    ):
        source = _function_source(
            FILES["referrals"],
            "get_sellers_owned_by_user",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "owner_user_id = ?",
            normalized,
        )

        self.assertIn(
            "created_by_user_id = ?",
            normalized,
        )

    def test_referral_stats_recheck_seller_ownership(
        self,
    ):
        source = _function_source(
            FILES["referrals"],
            "handle_referral_stats",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "_get_owned_seller",
            normalized,
        )

        self.assertIn(
            "شما به این فروشگاه دسترسی ندارید",
            normalized,
        )

    def test_referral_cannot_count_owner_as_referral(
        self,
    ):
        source = _function_source(
            FILES["referrals"],
            "record_referral_if_new",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "owner_user_id",
            normalized,
        )

        self.assertIn(
            "created_by_user_id",
            normalized,
        )

        self.assertIn(
            "referred_user_id",
            normalized,
        )

    def test_referral_is_unique_per_referred_user(
        self,
    ):
        source = _function_source(
            FILES["referrals"],
            "record_referral_if_new",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "where referred_user_id = ?",
            normalized,
        )

        self.assertIn(
            "unique",
            normalized,
        )

    def test_referral_insert_contains_required_identity_fields(
        self,
    ):
        source = _function_source(
            FILES["referrals"],
            "record_referral_if_new",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "insert into referrals",
            normalized,
        )

        self.assertIn(
            "seller_id",
            normalized,
        )

        self.assertIn(
            "referred_user_id",
            normalized,
        )

    def test_worker_browse_modules_have_no_legacy_imports(
        self,
    ):
        forbidden_roots = {
            "aiogram",
            "sqlite3",
            "aiosqlite",
            "bot",
        }

        for name, path in FILES.items():
            for imported in _imports(path):
                root = imported.split(
                    ".",
                    1,
                )[0]

                self.assertNotIn(
                    root,
                    forbidden_roots,
                    f"Legacy import {imported!r} found in {name}",
                )


if __name__ == "__main__":
    unittest.main()