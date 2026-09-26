# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Buyer / discovery handlers
"""

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..constants import (
    EMOJI_CATEGORIES,
    EMOJI_HOT,
    EMOJI_NEAR_ME,
    EMOJI_NEW_TODAY,
    EMOJI_PICKS,
    EMOJI_PRODUCT,
    EMOJI_SELLERS,
    EMOJI_TOP_SELLERS,
    PAGE_SIZE_CATEGORIES,
    PAGE_SIZE_LIST,
    TOP_LIST_LIMIT,
)
from ..database import db
from ..keyboards import kb_add_back, kb_pagination_row
from ..utils import (
    ensure_user,
    format_price,
    log_event,
    parse_int,
    safe_edit,
)


router = Router(name="buyer")


@router.callback_query(F.data.startswith("cat:"))
async def handle_category(callback: CallbackQuery, state) -> None:
    await state.clear()

    parts = callback.data.split(":")
    cat_id = parse_int(parts[1]) if len(parts) > 1 else None
    page = parse_int(parts[2]) if len(parts) > 2 else 0

    if cat_id is None or page is None:
        await callback.answer(
            "⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    if cat_id == 0:
        rows = await db.fetchall(
            """
            SELECT id, name, emoji
            FROM categories
            WHERE parent_id IS NULL
            ORDER BY id;
            """
        )

        offset = page * PAGE_SIZE_CATEGORIES
        page_rows = rows[
            offset:offset + PAGE_SIZE_CATEGORIES
        ]
        has_next = (
            offset + PAGE_SIZE_CATEGORIES
            < len(rows)
        )

        builder = InlineKeyboardBuilder()

        for row in page_rows:
            builder.row(
                InlineKeyboardButton(
                    text=f"{row['emoji']} {row['name']}",
                    callback_data=f"cat:{row['id']}:0",
                )
            )

        kb_pagination_row(
            builder,
            "cat:0",
            page,
            has_next,
        )
        kb_add_back(builder, "main")

        await safe_edit(
            callback,
            (
                f"{EMOJI_CATEGORIES} "
                "<b>دسته‌بندی‌ها</b>\n\n"
                "یک دسته را انتخاب کن:"
            ),
            builder.as_markup(),
        )
        await callback.answer()
        return

    category = await db.fetchone(
        "SELECT * FROM categories WHERE id = ?;",
        (cat_id,),
    )

    if not category:
        await callback.answer(
            "⚠️ این دسته‌بندی یافت نشد.",
            show_alert=True,
        )
        return

    await log_event(
        user_id,
        "category_click",
        "category",
        cat_id,
    )

    children = await db.fetchall(
        """
        SELECT id, name, emoji
        FROM categories
        WHERE parent_id = ?
        ORDER BY id;
        """,
        (cat_id,),
    )

    back_target = (
        f"cat:{category['parent_id']}:0"
        if category["parent_id"]
        else "cat:0:0"
    )

    if children:
        offset = page * PAGE_SIZE_CATEGORIES
        page_rows = children[
            offset:offset + PAGE_SIZE_CATEGORIES
        ]
        has_next = (
            offset + PAGE_SIZE_CATEGORIES
            < len(children)
        )

        builder = InlineKeyboardBuilder()

        for row in page_rows:
            builder.row(
                InlineKeyboardButton(
                    text=f"{row['emoji']} {row['name']}",
                    callback_data=f"cat:{row['id']}:0",
                )
            )

        kb_pagination_row(
            builder,
            f"cat:{cat_id}",
            page,
            has_next,
        )
        kb_add_back(
            builder,
            back_target,
        )

        await safe_edit(
            callback,
            (
                f"{category['emoji']} "
                f"<b>{category['name']}</b>\n\n"
                "یک زیردسته را انتخاب کن:"
            ),
            builder.as_markup(),
        )
        await callback.answer()
        return

    products = await db.fetchall(
        """
        SELECT p.*, s.name AS seller_name
        FROM products p
        JOIN sellers s
          ON s.id = p.seller_id
        WHERE p.category_id = ?
          AND COALESCE(s.is_active, 1) = 1
        ORDER BY p.views DESC, p.id DESC;
        """,
        (cat_id,),
    )

    if not products:
        builder = InlineKeyboardBuilder()
        kb_add_back(
            builder,
            back_target,
        )

        await safe_edit(
            callback,
            (
                f"{category['emoji']} "
                f"<b>{category['name']}</b>\n\n"
                "📦 فعلاً محصولی در این دسته ثبت نشده."
            ),
            builder.as_markup(),
        )
        await callback.answer()
        return

    offset = page * PAGE_SIZE_LIST
    page_rows = products[
        offset:offset + PAGE_SIZE_LIST
    ]
    has_next = (
        offset + PAGE_SIZE_LIST
        < len(products)
    )

    builder = InlineKeyboardBuilder()

    for product in page_rows:
        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{EMOJI_PRODUCT} "
                    f"{product['name']} - "
                    f"{format_price(product['price'])}"
                ),
                callback_data=f"product:{product['id']}",
            )
        )

    kb_pagination_row(
        builder,
        f"cat:{cat_id}",
        page,
        has_next,
    )
    kb_add_back(
        builder,
        back_target,
    )

    await safe_edit(
        callback,
        (
            f"{category['emoji']} "
            f"<b>{category['name']}</b>\n\n"
            "محصولات این دسته:"
        ),
        builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "nearme")
async def handle_near_me(
    callback: CallbackQuery,
    state,
) -> None:
    await state.clear()

    user_id = await ensure_user(
        callback.from_user
    )

    user = await db.fetchone(
        "SELECT city_id FROM users WHERE id = ?;",
        (user_id,),
    )

    if not user or not user["city_id"]:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="📍 انتخاب شهر",
                callback_data="setcity",
            )
        )
        kb_add_back(
            builder,
            "main",
        )

        await safe_edit(
            callback,
            "برای این بخش ابتدا باید شهر خودت رو انتخاب کنی.",
            builder.as_markup(),
        )
        await callback.answer()
        return

    city = await db.fetchone(
        "SELECT name FROM cities WHERE id = ?;",
        (user["city_id"],),
    )

    sellers = await db.fetchall(
        """
        SELECT id, name, status
        FROM sellers
        WHERE city_id = ?
          AND COALESCE(is_active, 1) = 1
        ORDER BY rating DESC
        LIMIT 10;
        """,
        (user["city_id"],),
    )

    builder = InlineKeyboardBuilder()

    if not sellers:
        text = (
            f"{EMOJI_NEAR_ME} "
            f"شهر انتخاب‌شده: {city['name']}\n\n"
            "فعلاً فروشگاهی در این شهر ثبت نشده."
        )
    else:
        text = (
            f"{EMOJI_NEAR_ME} "
            f"شهر انتخاب‌شده: {city['name']}\n\n"
            "فروشگاه‌های این شهر:"
        )

        for seller in sellers:
            badge = (
                "🟢"
                if seller["status"] == "CLAIMED"
                else "⚪"
            )

            builder.row(
                InlineKeyboardButton(
                    text=(
                        f"{EMOJI_SELLERS} "
                        f"{badge} "
                        f"{seller['name']}"
                    ),
                    callback_data=(
                        f"seller:{seller['id']}"
                    ),
                )
            )

    kb_add_back(
        builder,
        "main",
    )

    await safe_edit(
        callback,
        text,
        builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "hot")
async def handle_hot(
    callback: CallbackQuery,
    state,
) -> None:
    await state.clear()
    await ensure_user(
        callback.from_user
    )

    products = await db.fetchall(
        """
        SELECT p.*
        FROM products p
        JOIN sellers s
          ON s.id = p.seller_id
        WHERE COALESCE(s.is_active, 1) = 1
        ORDER BY p.views DESC, p.rating DESC
        LIMIT ?;
        """,
        (TOP_LIST_LIMIT,),
    )

    builder = InlineKeyboardBuilder()

    if not products:
        text = (
            f"{EMOJI_HOT} "
            "هنوز محصولی برای نمایش وجود ندارد."
        )
    else:
        text = f"{EMOJI_HOT} <b>داغ‌ترین‌ها</b>"

        for product in products:
            builder.row(
                InlineKeyboardButton(
                    text=(
                        f"{EMOJI_PRODUCT} "
                        f"{product['name']}"
                    ),
                    callback_data=(
                        f"product:{product['id']}"
                    ),
                )
            )

    kb_add_back(
        builder,
        "main",
    )

    await safe_edit(
        callback,
        text,
        builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "newtoday")
async def handle_new_today(
    callback: CallbackQuery,
    state,
) -> None:
    await state.clear()
    await ensure_user(
        callback.from_user
    )

    products = await db.fetchall(
        """
        SELECT p.*
        FROM products p
        JOIN sellers s
          ON s.id = p.seller_id
        WHERE date(p.created_at) = date('now')
          AND COALESCE(s.is_active, 1) = 1
        ORDER BY p.created_at DESC
        LIMIT ?;
        """,
        (TOP_LIST_LIMIT,),
    )

    builder = InlineKeyboardBuilder()

    if not products:
        text = (
            f"{EMOJI_NEW_TODAY} "
            "امروز محصول جدیدی ثبت نشده."
        )
    else:
        text = (
            f"{EMOJI_NEW_TODAY} "
            "<b>جدیدهای امروز</b>"
        )

        for product in products:
            builder.row(
                InlineKeyboardButton(
                    text=(
                        f"{EMOJI_PRODUCT} "
                        f"{product['name']}"
                    ),
                    callback_data=(
                        f"product:{product['id']}"
                    ),
                )
            )

    kb_add_back(
        builder,
        "main",
    )

    await safe_edit(
        callback,
        text,
        builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "picks")
async def handle_picks(
    callback: CallbackQuery,
    state,
) -> None:
    await state.clear()
    await ensure_user(
        callback.from_user
    )

    products = await db.fetchall(
        """
        SELECT p.*
        FROM products p
        JOIN sellers s
          ON s.id = p.seller_id
        WHERE COALESCE(s.is_active, 1) = 1
        ORDER BY p.rating DESC,
                 p.review_count DESC,
                 p.views DESC
        LIMIT ?;
        """,
        (TOP_LIST_LIMIT,),
    )

    builder = InlineKeyboardBuilder()

    if not products:
        text = (
            f"{EMOJI_PICKS} "
            "فعلاً پیشنهادی برای نمایش وجود ندارد."
        )
    else:
        text = (
            f"{EMOJI_PICKS} "
            "<b>انتخاب ارزانکده</b>"
        )

        for product in products:
            builder.row(
                InlineKeyboardButton(
                    text=(
                        f"{EMOJI_PRODUCT} "
                        f"{product['name']}"
                    ),
                    callback_data=(
                        f"product:{product['id']}"
                    ),
                )
            )

    kb_add_back(
        builder,
        "main",
    )

    await safe_edit(
        callback,
        text,
        builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "topsellers")
async def handle_top_sellers(
    callback: CallbackQuery,
    state,
) -> None:
    await state.clear()
    await ensure_user(
        callback.from_user
    )

    sellers = await db.fetchall(
        """
        SELECT *
        FROM sellers
        WHERE COALESCE(is_active, 1) = 1
        ORDER BY rating DESC,
                 review_count DESC,
                 views DESC
        LIMIT ?;
        """,
        (TOP_LIST_LIMIT,),
    )

    builder = InlineKeyboardBuilder()

    if not sellers:
        text = (
            f"{EMOJI_TOP_SELLERS} "
            "فعلاً فروشنده‌ای برای نمایش وجود ندارد."
        )
    else:
        text = (
            f"{EMOJI_TOP_SELLERS} "
            "<b>فروشندگان برتر</b>"
        )

        for seller in sellers:
            builder.row(
                InlineKeyboardButton(
                    text=(
                        f"{EMOJI_SELLERS} "
                        f"{seller['name']}"
                    ),
                    callback_data=(
                        f"seller:{seller['id']}"
                    ),
                )
            )

    kb_add_back(
        builder,
        "main",
    )

    await safe_edit(
        callback,
        text,
        builder.as_markup(),
    )
    await callback.answer()