# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Product handlers
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..constants import (
    EMOJI_CITY,
    EMOJI_COMPARE,
    EMOJI_PRICE,
    EMOJI_PRODUCT,
    EMOJI_REPORT,
    EMOJI_RATING,
    EMOJI_SELLERS,
)
from ..database import db
from ..keyboards import kb_add_back
from ..utils import (
    ensure_user,
    format_price,
    log_event,
    parse_int,
    safe_edit,
    status_badge,
)


router = Router(name="products")


@router.callback_query(F.data.startswith("product:"))
async def handle_product_detail(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await _render_product_detail(callback)


async def _render_product_detail(
    callback: CallbackQuery,
) -> None:
    product_id = parse_int(
        callback.data.split(":")[1]
    )

    if product_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    product = await db.fetchone(
        """
        SELECT
            p.*,
            s.name AS seller_name,
            s.status AS seller_status,
            c.name AS city_name
        FROM products p
        JOIN sellers s
            ON s.id = p.seller_id
        LEFT JOIN cities c
            ON c.id = s.city_id
        WHERE p.id = ?;
        """,
        (product_id,),
    )

    if not product:
        await callback.answer(
            "⚠️ این محصول یافت نشد.",
            show_alert=True,
        )
        return

    await db.execute(
        """
        UPDATE products
        SET views = views + 1
        WHERE id = ?;
        """,
        (product_id,),
    )

    await log_event(
        user_id,
        "view_product",
        "product",
        product_id,
    )

    is_favorite = await db.fetchone(
        """
        SELECT id
        FROM favorites
        WHERE user_id = ?
          AND product_id = ?;
        """,
        (
            user_id,
            product_id,
        ),
    )

    lines = [
        f"{EMOJI_PRODUCT} <b>{product['name']}</b>",
        "",
        product["description"] or "بدون توضیحات",
        "",
        f"{EMOJI_PRICE} {format_price(product['price'])}",
        f"🏪 {product['seller_name']}",
        f"{EMOJI_CITY} {product['city_name'] or 'نامشخص'}",
        (
            f"{EMOJI_RATING} "
            f"{product['rating']:.1f} "
            f"({product['review_count']} نظر)"
        ),
        status_badge(product["seller_status"]),
    ]

    if product["stock_status"] == "OUT_OF_STOCK":
        lines.append("⛔️ ناموجود")

    builder = InlineKeyboardBuilder()

    favorite_text = (
        "💔 حذف از علاقه‌مندی‌ها"
        if is_favorite
        else "❤️ افزودن به علاقه‌مندی‌ها"
    )

    favorite_callback = (
        f"unfavorite:{product_id}"
        if is_favorite
        else f"favorite:{product_id}"
    )

    builder.row(
        InlineKeyboardButton(
            text=favorite_text,
            callback_data=favorite_callback,
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=f"{EMOJI_COMPARE} افزودن به مقایسه",
            callback_data=f"comparestart:{product_id}",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=f"{EMOJI_SELLERS} فروشگاه",
            callback_data=f"seller:{product['seller_id']}",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="⭐ ثبت نظر",
            callback_data=(
                f"reviewstart:product:{product_id}"
            ),
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=f"{EMOJI_REPORT} گزارش",
            callback_data=(
                f"report:product:{product_id}"
            ),
        )
    )

    back_callback = (
        f"cat:{product['category_id']}:0"
        if product["category_id"]
        else "cat:0:0"
    )

    kb_add_back(
        builder,
        back_callback,
    )

    await safe_edit(
        callback,
        "\n".join(lines),
        builder.as_markup(),
    )

    await callback.answer()