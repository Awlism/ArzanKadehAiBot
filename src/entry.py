# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker entrypoint.

Routes:
- GET  / -> D1 health check
- POST / -> Telegram webhook router

No aiogram is imported here.
"""

from __future__ import annotations

from typing import Any

from workers import WorkerEntrypoint, Response

from worker_backend.backend import backend
from worker_backend.d1_backend import D1Backend

from worker.webhook import (
    InvalidWebhookPayloadError,
    UnauthorizedWebhookError,
    build_webhook_response_body,
    detect_update_type,
    parse_webhook_update,
    verify_webhook_secret,
)

from worker.router import WorkerRouter
from worker.start import handle_start
from worker.messages import handle_message
from worker.telegram import TelegramClient

from worker.categories import handle_category

from worker.products import (
    handle_product_detail,
    handle_favorite_add,
    handle_favorite_remove,
)

from worker.compare import (
    handle_compare,
    handle_compare_drop,
    handle_compare_list,
    handle_compare_reset,
    handle_compare_start,
)

from worker.seller import (
    handle_sellers_list,
    handle_seller_detail,
    handle_seller_favorite_add,
    handle_seller_favorite_remove,
)

from worker.review import (
    handle_review_start,
    handle_review_rating,
)

from worker.report import (
    handle_report_reason,
    handle_report_skip,
    handle_report_start,
)

from worker.hot import (
    handle_hot,
)

from worker.discovery import (
    handle_near_me,
    handle_new_today,
    handle_picks,
    handle_top_sellers,
)

from worker.favorites import (
    handle_favorites_list,
)

from worker.seller_registration import (
    handle_register_seller_start,
    handle_register_city,
    handle_register_skip,
)

from worker.search import (
    handle_search_start,
    handle_search_page,
)

from worker.publicads import (
    handle_public_ads,
    handle_public_ad_models,
    handle_public_ad_start,
    handle_public_ad_kind,
    handle_public_ad_skip,
)

from worker.account import (
    handle_account,
    handle_set_mode,
)

from worker.support import (
    handle_support_start,
    handle_support_topic,
)

from worker.notifications import (
    handle_notifications,
    handle_notification_read,
)

from worker.profile import (
    handle_my_profile,
    handle_set_city,
    handle_pick_city,
)

from worker.requests import (
    handle_my_requests,
)

from worker.store_status import (
    handle_store_status,
    handle_store_status_picked,
)

from worker.product_stats import (
    handle_my_stats,
    handle_stats_home_picked,
    handle_stats_product,
)

from worker.referrals import (
    handle_referral_list,
    handle_referral_stats,
)

from worker.product_management import (
    handle_my_products,
    handle_product_list,
    handle_product_add_start,
    handle_product_add_skip,
    handle_product_edit_menu,
    handle_product_field_start,
    handle_product_stock_menu,
    handle_product_stock_set,
    handle_product_delete,
    handle_product_delete_confirmed,
)

from worker.shop import (
    handle_my_shop,
    handle_shop_view,
    handle_shop_edit_menu,
    handle_shop_edit_start,
    handle_shop_city_start,
    handle_shop_city_pick,
    handle_shop_toggle_active,
)

from worker.ads import (
    handle_ads,
    handle_ad_type_detail,
    handle_ad_confirm,
)

from worker.seller_claims import (
    handle_claim,
    handle_seller_claims_admin,
    handle_seller_claim_detail,
    handle_seller_claim_decision,
)

from worker.admin import (
    handle_admin_home,
    handle_admin_users_menu,
    handle_admin_user_search_start,
    handle_admin_user_list,
    handle_admin_user_view,
)

from worker.admin_ads import (
    handle_ads_admin,
    handle_admin_ad_view,
    handle_admin_ad_price_start,
    handle_admin_ad_duration_start,
    handle_admin_ad_placement_start,
    handle_admin_ad_decision,
)


def _button(
    text: str,
    callback_data: str,
) -> dict[str, str]:
    return {
        "text": text,
        "callback_data": callback_data,
    }


def _main_menu_keyboard() -> dict[str, list[list[dict[str, str]]]]:
    return {
        "inline_keyboard": [
            [
                _button(
                    "🔎 جستجوی محصول",
                    "search",
                )
            ],
            [
                _button(
                    "🏪 فروشگاه‌ها",
                    "sellers:0",
                )
            ],
            [
                _button(
                    "📂 دسته‌بندی‌ها",
                    "cat:0:0",
                )
            ],
            [
                _button(
                    "🔥 داغ‌ترین‌ها",
                    "hot",
                )
            ],
            [
                _button(
                    "🆕 جدیدهای امروز",
                    "newtoday",
                )
            ],
            [
                _button(
                    "⭐ انتخاب ارزانکده",
                    "picks",
                )
            ],
            [
                _button(
                    "📍 نزدیک من",
                    "nearme",
                )
            ],
            [
                _button(
                    "🏆 فروشندگان برتر",
                    "topsellers",
                )
            ],
            [
                _button(
                    "❤️ علاقه‌مندی‌ها",
                    "favorites:0",
                )
            ],
            [
                _button(
                    "⚖️ مقایسه",
                    "comparelist",
                )
            ],
            [
                _button(
                    "🏪 ثبت فروشگاه من",
                    "registerseller",
                )
            ],
            [
                _button(
                    "📢 تبلیغ در ارزانکده",
                    "publicads",
                )
            ],
            [
                _button(
                    "👤 حساب کاربری",
                    "account",
                )
            ],
            [
                _button(
                    "🔄 شروع دوباره",
                    "restart_button",
                )
            ],
        ]
    }


async def _answer_callback(
    telegram: TelegramClient,
    callback_query: dict[str, Any],
) -> None:
    callback_id = callback_query.get("id")

    if not callback_id:
        return

    await telegram.answer_callback_query(
        str(callback_id)
    )


async def _handle_main_menu(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
) -> None:
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}

    chat_id = chat.get("id")
    message_id = message.get("message_id")

    if (
        chat_id is not None
        and message_id is not None
    ):
        await telegram.edit_message_text(
            int(chat_id),
            int(message_id),
            (
                "سلام 👋\n\n"
                "به <b>ارزان‌کده</b> خوش اومدی 🌱\n\n"
                "چی دنبالشی؟"
            ),
            reply_markup=_main_menu_keyboard(),
            parse_mode="HTML",
        )
    else:
        user = callback_query.get("from") or {}
        fallback_chat_id = user.get("id")

        if fallback_chat_id is not None:
            await telegram.send_message(
                int(fallback_chat_id),
                (
                    "سلام 👋\n\n"
                    "به <b>ارزان‌کده</b> خوش اومدی 🌱\n\n"
                    "چی دنبالشی؟"
                ),
                reply_markup=_main_menu_keyboard(),
                parse_mode="HTML",
            )

    await _answer_callback(
        telegram,
        callback_query,
    )


class Default(WorkerEntrypoint):
    async def fetch(
        self,
        request,
    ):
        try:
            method = request.method

            if method == "GET":
                return await self._health_check()

            if method == "POST":
                return await self._handle_webhook(
                    request
                )

            return Response(
                "Method Not Allowed",
                status=405,
            )

        except Exception as exc:
            return Response(
                "ArzanKadeh Worker ERROR\n\n"
                f"{type(exc).__name__}: {exc}",
                status=500,
            )

    async def _health_check(
        self,
    ):
        d1_backend = D1Backend(
            self.env.DB
        )

        backend.set_backend(
            d1_backend
        )

        await backend.connect()

        rows = await backend.fetchall(
            """
            SELECT
                name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name;
            """
        )

        tables = [
            row["name"]
            for row in rows
        ]

        body = (
            "ArzanKadeh Worker + D1Backend OK\n\n"
            f"Tables: {len(tables)}\n"
            f"{', '.join(tables)}"
        )

        return Response(
            body,
            status=200,
        )

    async def _handle_webhook(
        self,
        request,
    ):
        try:
            verify_webhook_secret(
                request,
                self.env,
            )

            update = await parse_webhook_update(
                request
            )

        except UnauthorizedWebhookError:
            return Response(
                "Unauthorized",
                status=401,
            )

        except InvalidWebhookPayloadError:
            return Response(
                "Invalid Telegram update",
                status=400,
            )

        d1_backend = D1Backend(
            self.env.DB
        )

        backend.set_backend(
            d1_backend
        )

        await backend.connect()

        update_type = detect_update_type(
            update
        )

        router = WorkerRouter()

        telegram = TelegramClient(
            self.env
        )

        if update_type == "message":

            async def message_handler(
                message,
            ):
                if _is_start_command(
                    message
                ):
                    return await handle_start(
                        message,
                        telegram,
                    )

                return await handle_message(
                    message,
                    telegram,
                    self.env,
                )

            router.set_message_handler(
                message_handler
            )

        elif update_type == "callback_query":

            async def callback_handler(
                callback_query,
            ):
                return await _handle_callback_query(
                    callback_query,
                    telegram,
                    self.env,
                )

            router.set_callback_handler(
                callback_handler
            )

        await router.dispatch(
            update
        )

        body = build_webhook_response_body(
            update_type
        )

        return Response(
            body,
            status=200,
        )


async def _handle_callback_query(
    callback_query,
    telegram,
    env,
):
    """
    Route all Worker callback queries to
    their corresponding business handlers.
    """

    if not isinstance(
        callback_query,
        dict,
    ):
        return None

    callback_data = callback_query.get(
        "data"
    )

    if not isinstance(
        callback_data,
        str,
    ):
        return None

    data = callback_data

    # Main navigation
    if data in (
        "main",
        "restart_button",
    ):
        return await _handle_main_menu(
            callback_query,
            telegram,
        )

    # Categories
    if data.startswith("cat:"):
        return await handle_category(
            backend,
            telegram,
            callback_query,
        )

    # Public product detail
    if data.startswith("product:"):
        return await handle_product_detail(
            backend,
            telegram,
            callback_query,
        )

    # Product favorites
    if data.startswith("favorite:"):
        return await handle_favorite_add(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("unfavorite:"):
        return await handle_favorite_remove(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("favorites:"):
        return await handle_favorites_list(
            backend,
            telegram,
            callback_query,
        )

    # Seller list / detail
    if data.startswith("sellers:"):
        return await handle_sellers_list(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("seller:"):
        return await handle_seller_detail(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("sfav:"):
        return await handle_seller_favorite_add(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("sunfav:"):
        return await handle_seller_favorite_remove(
            backend,
            telegram,
            callback_query,
        )

    # Reviews
    if data.startswith("reviewstart:"):
        return await handle_review_start(
            callback_query,
            telegram,
        )

    if data.startswith("reviewrate:"):
        return await handle_review_rating(
            callback_query,
            telegram,
        )

    # Reports
    if data.startswith("reportreason:"):
        return await handle_report_reason(
            callback_query,
            telegram,
        )

    if data == "reportskip":
        return await handle_report_skip(
            callback_query,
            telegram,
        )

    if data.startswith("report:"):
        return await handle_report_start(
            callback_query,
            telegram,
        )

    # Compare
    if data == "compare":
        return await handle_compare(
            backend,
            telegram,
            callback_query,
        )

    if data == "comparelist":
        return await handle_compare_list(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("comparestart:"):
        return await handle_compare_start(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("comparedrop:"):
        return await handle_compare_drop(
            backend,
            telegram,
            callback_query,
        )

    if data == "comparereset":
        return await handle_compare_reset(
            backend,
            telegram,
            callback_query,
        )

    # Discovery
    if data == "hot":
        return await handle_hot(
            backend,
            telegram,
            callback_query,
        )

    if data == "newtoday":
        return await handle_new_today(
            backend,
            telegram,
            callback_query,
        )

    if data == "picks":
        return await handle_picks(
            backend,
            telegram,
            callback_query,
        )

    if data == "nearme":
        return await handle_near_me(
            backend,
            telegram,
            callback_query,
        )

    if data == "topsellers":
        return await handle_top_sellers(
            backend,
            telegram,
            callback_query,
        )

    # Seller registration
    if data == "registerseller":
        return await handle_register_seller_start(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("registercity:"):
        return await handle_register_city(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("registerskip:"):
        return await handle_register_skip(
            backend,
            telegram,
            callback_query,
        )

    # Search
    if data == "search":
        return await handle_search_start(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("searchpage:"):
        return await handle_search_page(
            backend,
            telegram,
            callback_query,
        )

    # Public advertising
    if data == "publicads":
        return await handle_public_ads(
            backend,
            telegram,
            callback_query,
        )

    if data == "pubadmodels":
        return await handle_public_ad_models(
            backend,
            telegram,
            callback_query,
        )

    if data == "pubadstart":
        return await handle_public_ad_start(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("pubadkind:"):
        return await handle_public_ad_kind(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("pubadskip:"):
        return await handle_public_ad_skip(
            backend,
            telegram,
            callback_query,
        )

    # Account / modes
    if data == "account":
        return await handle_account(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("setmode:"):
        return await handle_set_mode(
            backend,
            telegram,
            callback_query,
        )

    # Support
    if data.startswith("supportstart:"):
        return await handle_support_start(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("supporttopic:"):
        return await handle_support_topic(
            backend,
            telegram,
            callback_query,
        )

    # Notifications
    if data == "notifications":
        return await handle_notifications(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("notifread:"):
        return await handle_notification_read(
            backend,
            telegram,
            callback_query,
        )

    # Profile
    if data == "myprofile":
        return await handle_my_profile(
            backend,
            telegram,
            callback_query,
        )

    if data == "setcity":
        return await handle_set_city(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("pickcity:"):
        return await handle_pick_city(
            backend,
            telegram,
            callback_query,
        )

    # Requests
    if data == "myrequests":
        return await handle_my_requests(
            backend,
            telegram,
            callback_query,
        )

    # Store status
    if data == "storestatus":
        return await handle_store_status(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("storestat:"):
        return await handle_store_status_picked(
            backend,
            telegram,
            callback_query,
        )

    # Shop toggle callback is generated by shop.py.
    if data.startswith("storetoggle:"):
        return await handle_shop_toggle_active(
            backend,
            telegram,
            callback_query,
        )

    # Product statistics
    if data == "mystats":
        return await handle_my_stats(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("statshome:"):
        return await handle_stats_home_picked(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("statsprod:"):
        return await handle_stats_product(
            backend,
            telegram,
            callback_query,
        )

    # Referrals
    if data == "reflist":
        return await handle_referral_list(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("refstats:"):
        return await handle_referral_stats(
            backend,
            telegram,
            callback_query,
        )

    # Product management
    if data == "myproducts":
        return await handle_my_products(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("prodlist:"):
        return await handle_product_list(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("prodadd:"):
        return await handle_product_add_start(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("prodaddskip:"):
        return await handle_product_add_skip(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("prodedit:"):
        return await handle_product_edit_menu(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("prodfield:"):
        return await handle_product_field_start(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("prodstock:"):
        return await handle_product_stock_menu(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("prodstockset:"):
        return await handle_product_stock_set(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("proddel:"):
        return await handle_product_delete(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("proddelyes:"):
        return await handle_product_delete_confirmed(
            backend,
            telegram,
            callback_query,
        )

    # Shop management
    if data == "myshop":
        return await handle_my_shop(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("shopview:"):
        return await handle_shop_view(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("shopeditmenu:"):
        return await handle_shop_edit_menu(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("shopedit:"):
        return await handle_shop_edit_start(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("shopcity:"):
        return await handle_shop_city_start(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("shopcitypick:"):
        return await handle_shop_city_pick(
            backend,
            telegram,
            callback_query,
        )

    # Seller advertising
    if data == "ads":
        return await handle_ads(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("adtype:"):
        return await handle_ad_type_detail(
            backend,
            telegram,
            callback_query,
        )

    if data.startswith("adconfirm:"):
        return await handle_ad_confirm(
            backend,
            telegram,
            callback_query,
        )

    # Seller claims
    if data == "sellerclaimsadmin":
        return await handle_seller_claims_admin(
            backend,
            telegram,
            callback_query,
            env,
        )

    if data.startswith("sellerclaimdetail:"):
        return await handle_seller_claim_detail(
            backend,
            telegram,
            callback_query,
            env,
        )

    if data.startswith("sellerclaim:"):
        return await handle_seller_claim_decision(
            backend,
            telegram,
            callback_query,
            env,
        )

    if data.startswith("claim:"):
        return await handle_claim(
            backend,
            telegram,
            callback_query,
            env,
        )

    # Core admin
    if data == "adminhome":
        return await handle_admin_home(
            callback_query,
            telegram,
            env,
        )

    if data == "adminusers":
        return await handle_admin_users_menu(
            callback_query,
            telegram,
            env,
        )

    if data == "adminusersearch":
        return await handle_admin_user_search_start(
            callback_query,
            telegram,
            env,
        )

    if data.startswith("adminuserlist:"):
        return await handle_admin_user_list(
            callback_query,
            telegram,
            env,
        )

    if data.startswith("adminuserview:"):
        return await handle_admin_user_view(
            callback_query,
            telegram,
            env,
        )

    # Admin advertising
    if data == "adsadmin":
        return await handle_ads_admin(
            backend,
            telegram,
            callback_query,
            env,
        )

    if data.startswith("adminadview:") or data.startswith(
        "adsadmindetail:"
    ):
        return await handle_admin_ad_view(
            backend,
            telegram,
            callback_query,
            env,
        )

    if data.startswith("adminadprice:"):
        return await handle_admin_ad_price_start(
            backend,
            telegram,
            callback_query,
            env,
        )

    if data.startswith("adminadduration:"):
        return await handle_admin_ad_duration_start(
            backend,
            telegram,
            callback_query,
            env,
        )

    if data.startswith("adminadplacement:"):
        return await handle_admin_ad_placement_start(
            backend,
            telegram,
            callback_query,
            env,
        )

    if data.startswith("adsetprice:"):
        return await handle_admin_ad_price_start(
            backend,
            telegram,
            callback_query,
            env,
        )

    if data.startswith("adsetduration:"):
        return await handle_admin_ad_duration_start(
            backend,
            telegram,
            callback_query,
            env,
        )

    if data.startswith("adsetplacement:"):
        return await handle_admin_ad_placement_start(
            backend,
            telegram,
            callback_query,
            env,
        )

    if data.startswith("adminaddecision:"):
        return await handle_admin_ad_decision(
            backend,
            telegram,
            callback_query,
            env,
        )

    if data.startswith("adminreq:"):
        return await handle_admin_ad_decision(
            backend,
            telegram,
            callback_query,
            env,
        )

    return None


def _is_start_command(
    message,
) -> bool:
    if not isinstance(
        message,
        dict,
    ):
        return False

    text = message.get(
        "text"
    )

    if not isinstance(
        text,
        str,
    ):
        return False

    text = text.strip()

    if not text:
        return False

    command = text.split(
        maxsplit=1
    )[0]

    return (
        command == "/start"
        or command.startswith(
            "/start@"
        )
    )


__all__ = [
    "Default",
]