# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker callback route contract tests.

This test verifies that the authoritative Worker entry point
still contains the complete callback routing contract.

It intentionally does not contact Telegram or Cloudflare D1.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENTRY_FILE = (
    PROJECT_ROOT
    / "src"
    / "entry.py"
)


EXPECTED_ROUTES = {
    "cat:": "handle_category",
    "product:": "handle_product_detail",
    "favorite:": "handle_favorite_add",
    "unfavorite:": "handle_favorite_remove",
    "favorites:": "handle_favorites_list",
    "sellers:": "handle_sellers_list",
    "seller:": "handle_seller_detail",
    "sfav:": "handle_seller_favorite_add",
    "sunfav:": "handle_seller_favorite_remove",
    "reviewstart:": "handle_review_start",
    "reviewrate:": "handle_review_rating",
    "reportreason:": "handle_report_reason",
    "reportskip": "handle_report_skip",
    "report:": "handle_report_start",
    "compare": "handle_compare",
    "comparelist": "handle_compare_list",
    "comparestart:": "handle_compare_start",
    "comparedrop:": "handle_compare_drop",
    "comparereset": "handle_compare_reset",
    "hot": "handle_hot",
    "newtoday": "handle_new_today",
    "picks": "handle_picks",
    "nearme": "handle_near_me",
    "topsellers": "handle_top_sellers",
    "registerseller": "handle_register_seller_start",
    "registercity:": "handle_register_city",
    "registerskip:": "handle_register_skip",
    "search": "handle_search_start",
    "searchpage:": "handle_search_page",
    "publicads": "handle_public_ads",
    "pubadmodels": "handle_public_ad_models",
    "pubadstart": "handle_public_ad_start",
    "pubadkind:": "handle_public_ad_kind",
    "pubadskip:": "handle_public_ad_skip",
    "account": "handle_account",
    "setmode:": "handle_set_mode",
    "supportstart:": "handle_support_start",
    "supporttopic:": "handle_support_topic",
    "notifications": "handle_notifications",
    "notifread:": "handle_notification_read",
    "myprofile": "handle_my_profile",
    "setcity": "handle_set_city",
    "pickcity:": "handle_pick_city",
    "myrequests": "handle_my_requests",
    "storestatus": "handle_store_status",
    "storestat:": "handle_store_status_picked",
    "storetoggle:": "handle_shop_toggle_active",
    "mystats": "handle_my_stats",
    "statshome:": "handle_stats_home_picked",
    "statsprod:": "handle_stats_product",
    "reflist": "handle_referral_list",
    "refstats:": "handle_referral_stats",
    "myproducts": "handle_my_products",
    "prodlist:": "handle_product_list",
    "prodadd:": "handle_product_add_start",
    "prodaddskip:": "handle_product_add_skip",
    "prodedit:": "handle_product_edit_menu",
    "prodfield:": "handle_product_field_start",
    "prodstock:": "handle_product_stock_menu",
    "prodstockset:": "handle_product_stock_set",
    "proddel:": "handle_product_delete",
    "proddelyes:": "handle_product_delete_confirmed",
    "myshop": "handle_my_shop",
    "shopview:": "handle_shop_view",
    "shopeditmenu:": "handle_shop_edit_menu",
    "shopedit:": "handle_shop_edit_start",
    "shopcity:": "handle_shop_city_start",
    "shopcitypick:": "handle_shop_city_pick",
    "ads": "handle_ads",
    "adtype:": "handle_ad_type_detail",
    "adconfirm:": "handle_ad_confirm",
    "sellerclaimsadmin": "handle_seller_claims_admin",
    "sellerclaimdetail:": "handle_seller_claim_detail",
    "sellerclaim:": "handle_seller_claim_decision",
    "claim:": "handle_claim",
    "adminhome": "handle_admin_home",
    "adminusers": "handle_admin_users_menu",
    "adminusersearch": "handle_admin_user_search_start",
    "adminuserlist:": "handle_admin_user_list",
    "adminuserview:": "handle_admin_user_view",
    "adsadmin": "handle_ads_admin",
    "adminadview:": "handle_admin_ad_view",
    "adsadmindetail:": "handle_admin_ad_view",
    "adminadprice:": "handle_admin_ad_price_start",
    "adminadduration:": "handle_admin_ad_duration_start",
    "adminadplacement:": "handle_admin_ad_placement_start",
    "adsetprice:": "handle_admin_ad_price_start",
    "adsetduration:": "handle_admin_ad_duration_start",
    "adsetplacement:": "handle_admin_ad_placement_start",
    "adminaddecision:": "handle_admin_ad_decision",
    "adminreq:": "handle_admin_ad_decision",
}


class CallbackRouteContractTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.source = ENTRY_FILE.read_text(
            encoding="utf-8"
        )

        cls.tree = ast.parse(
            cls.source,
            filename=str(
                ENTRY_FILE
            ),
        )

        cls.callback_function = None

        for node in ast.walk(
            cls.tree
        ):
            if (
                isinstance(
                    node,
                    ast.AsyncFunctionDef,
                )
                and node.name
                == "_handle_callback_query"
            ):
                cls.callback_function = node
                break

        if cls.callback_function is None:
            raise AssertionError(
                "_handle_callback_query was not found."
            )

    @classmethod
    def _route_contracts(cls):
        contracts = []

        for node in ast.walk(
            cls.callback_function
        ):
            if not isinstance(
                node,
                ast.If,
            ):
                continue

            test = node.test

            route = None
            route_kind = None

            if (
                isinstance(
                    test,
                    ast.Call,
                )
                and isinstance(
                    test.func,
                    ast.Attribute,
                )
                and test.func.attr
                == "startswith"
                and len(test.args) == 1
                and isinstance(
                    test.args[0],
                    ast.Constant,
                )
                and isinstance(
                    test.args[0].value,
                    str,
                )
            ):
                route = test.args[0].value
                route_kind = "startswith"

            elif (
                isinstance(
                    test,
                    ast.Compare,
                )
                and len(test.ops) == 1
                and isinstance(
                    test.ops[0],
                    ast.Eq,
                )
                and len(test.comparators) == 1
                and isinstance(
                    test.comparators[0],
                    ast.Constant,
                )
                and isinstance(
                    test.comparators[0].value,
                    str,
                )
            ):
                left = test.left

                if isinstance(
                    left,
                    ast.Name,
                ) and left.id == "data":
                    route = (
                        test.comparators[0].value
                    )
                    route_kind = "equals"

            if route is None:
                continue

            handler_names = []

            for child in ast.walk(
                node.body
            ):
                if not isinstance(
                    child,
                    ast.Await,
                ):
                    continue

                call = child.value

                if not isinstance(
                    call,
                    ast.Call,
                ):
                    continue

                if not isinstance(
                    call.func,
                    ast.Name,
                ):
                    continue

                handler_names.append(
                    call.func.id
                )

            contracts.append(
                (
                    route,
                    route_kind,
                    tuple(
                        handler_names
                    ),
                    node.lineno,
                )
            )

        return contracts

    def test_entry_file_exists(self):
        self.assertTrue(
            ENTRY_FILE.exists()
        )

    def test_callback_handler_exists(self):
        self.assertIsNotNone(
            self.callback_function
        )

    def test_all_expected_routes_exist(self):
        contracts = (
            self._route_contracts()
        )

        discovered = {
            route
            for route, _, _, _
            in contracts
        }

        missing = sorted(
            set(
                EXPECTED_ROUTES
            )
            - discovered
        )

        self.assertEqual(
            missing,
            [],
            (
                "Callback routes missing "
                f"from entry.py: {missing}"
            ),
        )

    def test_expected_routes_point_to_expected_handlers(self):
        contracts = (
            self._route_contracts()
        )

        route_handlers = {}

        for (
            route,
            _kind,
            handlers,
            _line,
        ) in contracts:
            route_handlers.setdefault(
                route,
                set(),
            ).update(
                handlers
            )

        failures = []

        for (
            route,
            expected_handler,
        ) in EXPECTED_ROUTES.items():
            actual_handlers = (
                route_handlers.get(
                    route,
                    set(),
                )
            )

            if (
                expected_handler
                not in actual_handlers
            ):
                failures.append(
                    (
                        route,
                        expected_handler,
                        sorted(
                            actual_handlers
                        ),
                    )
                )

        self.assertEqual(
            failures,
            [],
            (
                "Callback route handler "
                "contract mismatch: "
                f"{failures}"
            ),
        )

    def test_admin_ad_view_aliases_share_handler(self):
        contracts = (
            self._route_contracts()
        )

        route_handlers = {}

        for (
            route,
            _kind,
            handlers,
            _line,
        ) in contracts:
            route_handlers[
                route
            ] = set(
                handlers
            )

        self.assertIn(
            "handle_admin_ad_view",
            route_handlers[
                "adminadview:"
            ],
        )

        self.assertIn(
            "handle_admin_ad_view",
            route_handlers[
                "adsadmindetail:"
            ],
        )

    def test_admin_ad_setting_aliases_share_handlers(self):
        contracts = (
            self._route_contracts()
        )

        route_handlers = {}

        for (
            route,
            _kind,
            handlers,
            _line,
        ) in contracts:
            route_handlers[
                route
            ] = set(
                handlers
            )

        aliases = {
            "adsetprice:": "handle_admin_ad_price_start",
            "adsetduration:": "handle_admin_ad_duration_start",
            "adsetplacement:": "handle_admin_ad_placement_start",
        }

        for (
            route,
            expected_handler,
        ) in aliases.items():
            self.assertIn(
                expected_handler,
                route_handlers[
                    route
                ],
            )

    def test_admin_decision_aliases_share_handler(self):
        contracts = (
            self._route_contracts()
        )

        route_handlers = {}

        for (
            route,
            _kind,
            handlers,
            _line,
        ) in contracts:
            route_handlers[
                route
            ] = set(
                handlers
            )

        self.assertIn(
            "handle_admin_ad_decision",
            route_handlers[
                "adminaddecision:"
            ],
        )

        self.assertIn(
            "handle_admin_ad_decision",
            route_handlers[
                "adminreq:"
            ],
        )

    def test_callback_route_count_is_not_smaller_than_contract(self):
        contracts = (
            self._route_contracts()
        )

        discovered = {
            route
            for route, _, _, _
            in contracts
        }

        self.assertGreaterEqual(
            len(discovered),
            len(
                EXPECTED_ROUTES
            ),
        )

    def test_worker_entry_does_not_import_legacy_aiogram_stack(self):
        forbidden = (
            "from aiogram",
            "import aiogram",
            "import sqlite3",
            "import aiosqlite",
            "from aiosqlite",
        )

        violations = [
            token
            for token in forbidden
            if token in self.source
        ]

        self.assertEqual(
            violations,
            [],
            (
                "Legacy imports found in "
                f"src/entry.py: {violations}"
            ),
        )


if __name__ == "__main__":
    unittest.main()