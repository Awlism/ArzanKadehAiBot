# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker ownership and admin security contract tests.

These tests inspect the migrated Worker source directly and verify
that seller/product management and administrative operations remain
properly scoped to the authenticated user or configured admin.

Covered:
- Seller ownership uses owner_user_id OR created_by_user_id.
- Product ownership is derived from the owning seller.
- Product management checks ownership before access.
- Shop management checks ownership before access.
- Seller registration prevents duplicate active ownership.
- Seller registration writes owner and creator IDs.
- Admin authorization uses ADMIN_CHAT_ID.
- Admin handlers require admin authorization.
- Seller claim admin handlers require admin authorization.
- Seller claim approval is bound to the claimant user.
- Seller claim approval only applies to an UNCLAIMED seller.
- Legacy aiogram/sqlite imports are absent.

These are source-contract tests and do not contact D1 or Telegram.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src" / "worker"

PRODUCT_MANAGEMENT_FILE = (
    SRC_ROOT / "product_management.py"
)
SHOP_FILE = SRC_ROOT / "shop.py"
SELLER_REGISTRATION_FILE = (
    SRC_ROOT / "seller_registration.py"
)
ADMIN_FILE = SRC_ROOT / "admin.py"
ADMIN_ADS_FILE = SRC_ROOT / "admin_ads.py"
SELLER_CLAIMS_FILE = (
    SRC_ROOT / "seller_claims.py"
)


def _read(path: Path) -> str:
    return path.read_text(
        encoding="utf-8"
    )


def _tree(path: Path) -> ast.AST:
    return ast.parse(
        _read(path),
        filename=str(path),
    )


def _normalized(value: str) -> str:
    return " ".join(
        value.split()
    ).lower()


def _function(
    path: Path,
    name: str,
) -> ast.AsyncFunctionDef | ast.FunctionDef:
    tree = _tree(path)

    for node in ast.walk(tree):
        if isinstance(
            node,
            (
                ast.AsyncFunctionDef,
                ast.FunctionDef,
            ),
        ) and node.name == name:
            return node

    raise AssertionError(
        f"Function {name!r} not found in {path}"
    )


def _function_source(
    path: Path,
    name: str,
) -> str:
    source = _read(path)
    node = _function(
        path,
        name,
    )

    result = ast.get_source_segment(
        source,
        node,
    )

    if result is None:
        raise AssertionError(
            f"Could not extract source for {name!r}"
        )

    return result


def _function_sql(
    path: Path,
    name: str,
) -> list[str]:
    node = _function(
        path,
        name,
    )

    values: list[str] = []

    for child in ast.walk(node):
        if not isinstance(
            child,
            ast.Constant,
        ):
            continue

        if not isinstance(
            child.value,
            str,
        ):
            continue

        value = child.value

        if any(
            keyword in value.upper()
            for keyword in (
                "SELECT",
                "INSERT",
                "UPDATE",
                "DELETE",
                "FROM",
                "WHERE",
            )
        ):
            values.append(
                value
            )

    return values


def _all_imports(
    path: Path,
) -> list[str]:
    tree = _tree(path)
    imports: list[str] = []

    for node in ast.walk(tree):
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


class WorkerOwnershipAdminContractTests(
    unittest.TestCase
):
    def test_product_management_owned_seller_is_user_scoped(
        self,
    ):
        source = _function_source(
            PRODUCT_MANAGEMENT_FILE,
            "_owned_seller",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "where id = ?",
            normalized,
        )

        self.assertIn(
            "owner_user_id = ?",
            normalized,
        )

        self.assertIn(
            "created_by_user_id = ?",
            normalized,
        )

        self.assertIn(
            "or",
            normalized,
        )

    def test_product_management_owned_product_is_user_scoped(
        self,
    ):
        source = _function_source(
            PRODUCT_MANAGEMENT_FILE,
            "_owned_product",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "from products p",
            normalized,
        )

        self.assertIn(
            "join sellers s",
            normalized,
        )

        self.assertIn(
            "where p.id = ?",
            normalized,
        )

        self.assertIn(
            "s.owner_user_id = ?",
            normalized,
        )

        self.assertIn(
            "s.created_by_user_id = ?",
            normalized,
        )

    def test_product_management_owned_sellers_support_owner_or_creator(
        self,
    ):
        source = _function_source(
            PRODUCT_MANAGEMENT_FILE,
            "_owned_sellers",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "from sellers",
            normalized,
        )

        self.assertIn(
            "owner_user_id = ?",
            normalized,
        )

        self.assertIn(
            "created_by_user_id = ?",
            normalized,
        )

    def test_product_list_handler_checks_owned_seller(
        self,
    ):
        source = _function_source(
            PRODUCT_MANAGEMENT_FILE,
            "handle_product_list",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "_owned_seller",
            normalized,
        )

        self.assertIn(
            "شما به این فروشگاه دسترسی ندارید.",
            normalized,
        )

    def test_shop_owned_seller_is_user_scoped(
        self,
    ):
        source = _function_source(
            SHOP_FILE,
            "_owned_seller",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "where s.id = ?",
            normalized,
        )

        self.assertIn(
            "s.owner_user_id = ?",
            normalized,
        )

        self.assertIn(
            "s.created_by_user_id = ?",
            normalized,
        )

    def test_shop_owned_sellers_support_owner_or_creator(
        self,
    ):
        source = _function_source(
            SHOP_FILE,
            "_owned_sellers",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "from sellers",
            normalized,
        )

        self.assertIn(
            "owner_user_id = ?",
            normalized,
        )

        self.assertIn(
            "created_by_user_id = ?",
            normalized,
        )

    def test_seller_registration_prevents_duplicate_active_ownership(
        self,
    ):
        source = _function_source(
            SELLER_REGISTRATION_FILE,
            "_finish_registration",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "from sellers",
            normalized,
        )

        self.assertIn(
            "owner_user_id = ?",
            normalized,
        )

        self.assertIn(
            "created_by_user_id = ?",
            normalized,
        )

        self.assertIn(
            "status != 'rejected'",
            normalized,
        )

    def test_seller_registration_insert_binds_owner_and_creator(
        self,
    ):
        source = _function_source(
            SELLER_REGISTRATION_FILE,
            "_finish_registration",
        )

        normalized = _normalized(
            source
        )

        match = re.search(
            r"insert\s+into\s+sellers\s*\((.*?)\)",
            normalized,
            re.DOTALL,
        )

        self.assertIsNotNone(
            match
        )

        columns = match.group(1)

        self.assertIn(
            "owner_user_id",
            columns,
        )

        self.assertIn(
            "created_by_user_id",
            columns,
        )

    def test_seller_registration_uses_internal_user_id(
        self,
    ):
        source = _function_source(
            SELLER_REGISTRATION_FILE,
            "_ensure_user",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "insert into users",
            normalized,
        )

        self.assertIn(
            "telegram_id",
            normalized,
        )

        self.assertIn(
            "where telegram_id = ?",
            normalized,
        )

    def test_admin_is_bound_to_configured_admin_chat_id(
        self,
    ):
        source = _function_source(
            ADMIN_FILE,
            "_is_admin",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "admin_chat_id",
            normalized,
        )

        self.assertIn(
            "getattr",
            normalized,
        )

        self.assertIn(
            "int(admin_chat_id)",
            normalized,
        )

        self.assertIn(
            "int(telegram_user_id)",
            normalized,
        )

    def test_admin_missing_configuration_is_denied(
        self,
    ):
        source = _function_source(
            ADMIN_FILE,
            "_is_admin",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "if admin_chat_id is none",
            normalized,
        )

        self.assertIn(
            "return false",
            normalized,
        )

    def test_admin_ad_flow_checks_admin_authorization(
        self,
    ):
        for function_name in (
            "handle_admin_ad_price_start",
            "handle_admin_ad_duration_start",
            "handle_admin_ad_placement_start",
            "handle_admin_ad_decision",
        ):
            source = _function_source(
                ADMIN_ADS_FILE,
                function_name,
            )

            normalized = _normalized(
                source
            )

            self.assertIn(
                "_is_admin",
                normalized,
                function_name,
            )

    def test_admin_ad_message_rejects_non_admin(
        self,
    ):
        source = _function_source(
            ADMIN_ADS_FILE,
            "handle_admin_ad_message",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "_is_admin",
            normalized,
        )

        self.assertIn(
            "if not _is_admin",
            normalized,
        )

        self.assertIn(
            "return false",
            normalized,
        )

    def test_seller_claim_admin_list_requires_admin(
        self,
    ):
        source = _function_source(
            SELLER_CLAIMS_FILE,
            "handle_seller_claims_admin",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "_is_admin",
            normalized,
        )

        self.assertIn(
            "if not _is_admin",
            normalized,
        )

    def test_seller_claim_detail_requires_admin(
        self,
    ):
        source = _function_source(
            SELLER_CLAIMS_FILE,
            "handle_seller_claim_detail",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "_is_admin",
            normalized,
        )

        self.assertIn(
            "if not _is_admin",
            normalized,
        )

    def test_seller_claim_decision_requires_admin(
        self,
    ):
        source = _function_source(
            SELLER_CLAIMS_FILE,
            "handle_seller_claim_decision",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "_is_admin",
            normalized,
        )

        self.assertIn(
            "if not _is_admin",
            normalized,
        )

    def test_seller_claim_approval_binds_claim_to_user(
        self,
    ):
        source = _function_source(
            SELLER_CLAIMS_FILE,
            "_approve_claim",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "from seller_claims",
            normalized,
        )

        self.assertIn(
            "where id = ?",
            normalized,
        )

        self.assertIn(
            "user_id",
            normalized,
        )

        self.assertIn(
            "status",
            normalized,
        )

    def test_seller_claim_approval_requires_unclaimed_seller(
        self,
    ):
        source = _function_source(
            SELLER_CLAIMS_FILE,
            "_approve_claim",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "from sellers",
            normalized,
        )

        self.assertIn(
            "status = 'unclaimed'",
            normalized,
        )

    def test_seller_claim_approval_updates_claim_for_matching_user(
        self,
    ):
        source = _function_source(
            SELLER_CLAIMS_FILE,
            "_approve_claim",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "update seller_claims",
            normalized,
        )

        self.assertIn(
            "user_id = ?",
            normalized,
        )

        self.assertIn(
            "status = 'approved'",
            normalized,
        )

    def test_seller_claim_approval_updates_seller_owner(
        self,
    ):
        source = _function_source(
            SELLER_CLAIMS_FILE,
            "_approve_claim",
        )

        normalized = _normalized(
            source
        )

        self.assertIn(
            "update sellers",
            normalized,
        )

        self.assertIn(
            "owner_user_id = ?",
            normalized,
        )

        self.assertIn(
            "status = 'claimed'",
            normalized,
        )

    def test_seller_claim_request_rejects_existing_owner_or_creator(
        self,
    ):
        source = _function_source(
            SELLER_CLAIMS_FILE,
            "handle_claim",
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
            "user_id in",
            normalized,
        )

    def test_seller_claim_handlers_resolve_internal_user(
        self,
    ):
        for function_name in (
            "handle_claim",
            "handle_seller_claim_decision",
        ):
            source = _function_source(
                SELLER_CLAIMS_FILE,
                function_name,
            )

            normalized = _normalized(
                source
            )

            self.assertIn(
                "_ensure_user",
                normalized,
                function_name,
            )

    def test_security_sensitive_worker_modules_have_no_legacy_imports(
        self,
    ):
        forbidden = {
            "aiogram",
            "sqlite3",
            "aiosqlite",
            "bot",
        }

        for path in (
            PRODUCT_MANAGEMENT_FILE,
            SHOP_FILE,
            SELLER_REGISTRATION_FILE,
            ADMIN_FILE,
            ADMIN_ADS_FILE,
            SELLER_CLAIMS_FILE,
        ):
            for imported in _all_imports(
                path
            ):
                root = imported.split(
                    ".",
                    1,
                )[0]

                self.assertNotIn(
                    root,
                    forbidden,
                    f"Forbidden legacy import {imported!r} in {path}",
                )


if __name__ == "__main__":
    unittest.main()