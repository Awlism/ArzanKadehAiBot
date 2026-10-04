# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker-side seller statistics handlers.

This module intentionally does not import aiogram, sqlite, or aiosqlite.
"""

from __future__ import annotations

from html import escape
from typing import Any, Optional


PAGE_SIZE_LIST = 8


def _html(value: Any) -> str:
    if value is None:
        return ""

    return escape(str(value), quote=False)


def _parse_id(value: Any) -> Optional[int]:
    try:
        result = int(str(value).strip())
    except (TypeError, ValueError):
        return None

    if result < 1:
        return None

    return result


def _callback_id(
    callback_query: dict[str, Any],
    prefix: str,
) -> Optional[int]:
    data = str(callback_query.get("data", ""))

    if not data.startswith(prefix):
        return None

    return _parse_id(data[len(prefix):])


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def _ensure_user(
    db: Any,
    telegram_user: dict[str, Any],
) -> dict[str, Any]:
    telegram_id = _parse_id(telegram_user.get("id"))

    if telegram_id is None:
        raise ValueError("Invalid Telegram user id.")

    username = telegram_user.get("username")
    first_name = telegram_user.get("first_name")
    last_name = telegram_user.get("last_name")

    username = (
        str(username).strip()
        if username is not None
        else None
    )
    first_name = (
        str(first_name).strip()
        if first_name is not None
        else None
    )
    last_name = (
        str(last_name).strip()
        if last_name is not None
        else None
    )

    now = _now_iso()

    await db.execute(
        """
        INSERT INTO users (
            telegram_id,
            username,
            first_name,
            last_name,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id)
        DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            updated_at = excluded.updated_at;
        """,
        (
            telegram_id,
            username,
            first_name,
            last_name,
            now,
            now,
        ),
    )

    user = await db.fetchone(
        """
        SELECT *
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_id,),
    )

    if user is None:
        raise RuntimeError("Failed to resolve user.")

    return user


async def _get_owned_sellers(
    db: Any,
    user_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT
            id,
            name
        FROM sellers
        WHERE owner_user_id = ?
           OR created_by_user_id = ?
        ORDER BY id ASC;
        """,
        (
            user_id,
            user_id,
        ),
    )


async def _get_owned_seller(
    db: Any,
    user_id: int,
    seller_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT *
        FROM sellers
        WHERE id = ?
          AND (
              owner_user_id = ?
              OR created_by_user_id = ?
          )
        LIMIT 1;
        """,
        (
            seller_id,
            user_id,
            user_id,
        ),
    )


async def _get_owned_product(
    db: Any,
    user_id: int,
    product_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT
            p.*
        FROM products AS p
        INNER JOIN sellers AS s
            ON s.id = p.seller_id
        WHERE p.id = ?
          AND (
              s.owner_user_id = ?
              OR s.created_by_user_id = ?
          )
        LIMIT 1;
        """,
        (
            product_id,
            user_id,
            user_id,
        ),
    )


async def _answer_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    text: Optional[str] = None,
    show_alert: bool = False,
) -> None:
    callback_id = callback_query.get("id")

    if not callback_id:
        return

    await telegram.answer_callback_query(
        str(callback_id),
        text=text,
        show_alert=show_alert,
    )


async def _edit_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    text: str,
    keyboard: Optional[dict[str, Any]] = None,
) -> None:
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}

    chat_id = _parse_id(chat.get("id"))
    message_id = _parse_id(message.get("message_id"))

    if chat_id is None or message_id is None:
        return

    await telegram.edit_message_text(
        chat_id,
        message_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


def _button(
    text: str,
    callback_data: str,
) -> dict[str, Any]:
    return {
        "text": text,
        "callback_data": callback_data,
    }


def _keyboard(
    rows: list[list[dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "inline_keyboard": rows,
    }


async def _render_stats_home(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    seller_id: int,
    user_id: int,
) -> None:
    seller = await _get_owned_seller(
        db,
        user_id,
        seller_id,
    )

    if seller is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شما به این فروشگاه دسترسی ندارید.",
            True,
        )
        return

    products = await db.fetchall(
        """
        SELECT *
        FROM products
        WHERE seller_id = ?
        ORDER BY views DESC;
        """,
        (seller_id,),
    )

    favorite_row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM seller_favorites
        WHERE seller_id = ?;
        """,
        (seller_id,),
    )

    favorite_count = (
        int(favorite_row["c"] or 0)
        if favorite_row
        else 0
    )

    total_product_views = sum(
        int(product["views"] or 0)
        for product in products
    )

    active_products = sum(
        1
        for product in products
        if str(
            product["stock_status"] or ""
        ).upper() == "AVAILABLE"
    )

    request_row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM requests
        WHERE seller_id = ?;
        """,
        (seller_id,),
    )

    request_count = (
        int(request_row["c"] or 0)
        if request_row
        else 0
    )

    text = (
        "📈 <b>آمار فروشگاه</b>\n\n"
        f"🏪 <b>{_html(seller['name'])}</b>\n"
        f"👀 بازدید فروشگاه: {int(seller['views'] or 0)}\n"
        f"❤️ ذخیره فروشگاه: {favorite_count}\n"
        f"📦 مجموع بازدید محصولات: {total_product_views}\n"
        f"🛍️ تعداد محصولات: {len(products)}\n"
        f"✅ محصولات موجود (فعال): {active_products}\n"
        f"📋 تعداد درخواست‌های ثبت‌شده: {request_count}\n"
    )

    if products:
        text += "\nبرای دیدن آمار هر محصول، روی اسمش بزن:"

    rows: list[list[dict[str, Any]]] = []

    for product in products[:PAGE_SIZE_LIST]:
        product_id = _parse_id(product.get("id"))

        if product_id is None:
            continue

        rows.append(
            [
                _button(
                    f"📊 {_html(product.get('name') or 'محصول')}",
                    f"statsprod:{product_id}",
                )
            ]
        )

    rows.append(
        [
            _button(
                "🔙 بازگشت",
                "account",
            )
        ]
    )

    await _edit_callback(
        telegram,
        callback_query,
        text,
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_my_stats(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    callback_user = callback_query.get("from") or {}

    try:
        user = await _ensure_user(
            db,
            callback_user,
        )
    except (ValueError, RuntimeError):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    user_id = int(user["id"])

    sellers = await _get_owned_sellers(
        db,
        user_id,
    )

    if not sellers:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شما هنوز فروشگاهی ثبت نکرده‌اید.",
            True,
        )
        return

    if len(sellers) == 1:
        seller_id = _parse_id(sellers[0].get("id"))

        if seller_id is not None:
            await _render_stats_home(
                db,
                telegram,
                callback_query,
                seller_id,
                user_id,
            )

        return

    rows: list[list[dict[str, Any]]] = []

    for seller in sellers:
        seller_id = _parse_id(seller.get("id"))

        if seller_id is None:
            continue

        rows.append(
            [
                _button(
                    f"🏪 {_html(seller.get('name') or 'فروشگاه')}",
                    f"statshome:{seller_id}",
                )
            ]
        )

    rows.append(
        [
            _button(
                "🔙 بازگشت",
                "account",
            )
        ]
    )

    await _edit_callback(
        telegram,
        callback_query,
        "📊 کدوم فروشگاهت رو می‌خوای ببینی؟",
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_stats_home_picked(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    seller_id = _callback_id(
        callback_query,
        "statshome:",
    )

    if seller_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شناسه فروشگاه نامعتبر است.",
            True,
        )
        return

    callback_user = callback_query.get("from") or {}

    try:
        user = await _ensure_user(
            db,
            callback_user,
        )
    except (ValueError, RuntimeError):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    await _render_stats_home(
        db,
        telegram,
        callback_query,
        seller_id,
        int(user["id"]),
    )


async def handle_stats_product(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    product_id = _callback_id(
        callback_query,
        "statsprod:",
    )

    if product_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شناسه محصول نامعتبر است.",
            True,
        )
        return

    callback_user = callback_query.get("from") or {}

    try:
        user = await _ensure_user(
            db,
            callback_user,
        )
    except (ValueError, RuntimeError):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    user_id = int(user["id"])

    product = await _get_owned_product(
        db,
        user_id,
        product_id,
    )

    if product is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شما به این محصول دسترسی ندارید.",
            True,
        )
        return

    favorite_row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM favorites
        WHERE product_id = ?;
        """,
        (product_id,),
    )

    favorite_count = (
        int(favorite_row["c"] or 0)
        if favorite_row
        else 0
    )

    text = (
        f"📊 <b>{_html(product['name'])}</b>\n\n"
        f"👀 بازدید: {int(product['views'] or 0)}\n"
        f"❤️ ذخیره: {favorite_count}\n"
        "📸 کلیک Instagram: 0\n"
        "✈️ کلیک Telegram: 0\n"
        "🟢 کلیک WhatsApp: 0\n"
    )

    rows = [
        [
            _button(
                "🔙 بازگشت به آمار فروشگاه",
                "mystats",
            )
        ],
        [
            _button(
                "🏠 حساب کاربری",
                "account",
            )
        ],
    ]

    await _edit_callback(
        telegram,
        callback_query,
        text,
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


__all__ = [
    "handle_my_stats",
    "handle_stats_home_picked",
    "handle_stats_product",
]