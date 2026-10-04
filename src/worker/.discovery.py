# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker-side discovery handlers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


TOP_LIST_LIMIT = 10
TEHRAN_TIMEZONE = ZoneInfo("Asia/Tehran")


def _html(value: Any) -> str:
    from html import escape

    if value is None:
        return ""

    return escape(
        str(value),
        quote=False,
    )


def _now_iso() -> str:
    return datetime.now(
        ZoneInfo("UTC"),
    ).isoformat(
        timespec="seconds"
    )


def _today_tehran() -> str:
    return datetime.now(
        TEHRAN_TIMEZONE
    ).date().isoformat()


async def _ensure_user(
    db: Any,
    user: dict[str, Any],
) -> dict[str, Any]:
    telegram_id = user.get("id")

    if telegram_id is None:
        raise ValueError(
            "Telegram user id is required."
        )

    try:
        telegram_id = int(telegram_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Telegram user id is invalid."
        ) from exc

    if telegram_id < 1:
        raise ValueError(
            "Telegram user id is invalid."
        )

    username = user.get("username")
    first_name = user.get("first_name")
    last_name = user.get("last_name")

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

    row = await db.fetchone(
        """
        SELECT *
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_id,),
    )

    if row is None:
        raise RuntimeError(
            "Failed to create or load user."
        )

    return row


def _keyboard(
    rows: list[list[dict[str, Any]]],
    back_callback: str = "main",
) -> dict[str, Any]:
    keyboard = list(rows)

    keyboard.append(
        [
            {
                "text": "🔙 بازگشت",
                "callback_data": back_callback,
            }
        ]
    )

    return {
        "inline_keyboard": keyboard,
    }


async def _answer_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    text: str | None = None,
    show_alert: bool = False,
) -> None:
    callback_id = callback_query.get("id")

    if not callback_id:
        return

    await telegram.answer_callback_query(
        callback_id,
        text=text,
        show_alert=show_alert,
    )


async def _edit_callback_message(
    telegram: Any,
    callback_query: dict[str, Any],
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    message = callback_query.get("message")

    if not isinstance(message, dict):
        return

    chat = message.get("chat")

    if not isinstance(chat, dict):
        return

    chat_id = chat.get("id")
    message_id = message.get("message_id")

    if chat_id is None or message_id is None:
        return

    try:
        chat_id = int(chat_id)
        message_id = int(message_id)
    except (TypeError, ValueError):
        return

    await telegram.edit_message_text(
        chat_id,
        message_id,
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


def _valid_callback_user(
    callback_query: dict[str, Any],
) -> dict[str, Any] | None:
    user = callback_query.get("from")

    if not isinstance(user, dict):
        return None

    return user


async def handle_near_me(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Show active sellers in the user's selected city.
    """

    user_data = _valid_callback_user(
        callback_query
    )

    if user_data is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    try:
        user = await _ensure_user(
            db,
            user_data,
        )
    except (ValueError, RuntimeError):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    city_id = user.get("city_id")

    if not city_id:
        keyboard = _keyboard(
            [
                [
                    {
                        "text": "📍 انتخاب شهر",
                        "callback_data": "setcity",
                    }
                ]
            ]
        )

        await _edit_callback_message(
            telegram,
            callback_query,
            (
                "برای این بخش ابتدا باید "
                "شهر خودت رو انتخاب کنی."
            ),
            keyboard,
        )

        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    city = await db.fetchone(
        """
        SELECT name
        FROM cities
        WHERE id = ?
        LIMIT 1;
        """,
        (city_id,),
    )

    if not city:
        await _edit_callback_message(
            telegram,
            callback_query,
            (
                "⚠️ شهر انتخاب‌شده دیگر معتبر نیست. "
                "لطفاً دوباره شهر خودت رو انتخاب کن."
            ),
            _keyboard([]),
        )

        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    sellers = await db.fetchall(
        """
        SELECT
            id,
            name,
            status
        FROM sellers
        WHERE city_id = ?
          AND COALESCE(is_active, 1) = 1
        ORDER BY rating DESC
        LIMIT 10;
        """,
        (city_id,),
    )

    rows: list[list[dict[str, Any]]] = []

    for seller in sellers:
        badge = (
            "🟢"
            if seller.get("status") == "approved"
            else "⚪"
        )

        rows.append(
            [
                {
                    "text": (
                        "🏪 "
                        f"{badge} "
                        f"{seller['name']}"
                    ),
                    "callback_data": (
                        f"seller:{seller['id']}"
                    ),
                }
            ]
        )

    if not sellers:
        text = (
            "📍 "
            f"شهر انتخاب‌شده: "
            f"{_html(city['name'])}\n\n"
            "فعلاً فروشگاهی در این شهر ثبت نشده."
        )
    else:
        text = (
            "📍 "
            f"شهر انتخاب‌شده: "
            f"{_html(city['name'])}\n\n"
            "فروشگاه‌های این شهر:"
        )

    await _edit_callback_message(
        telegram,
        callback_query,
        text,
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_new_today(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Show products created today using Tehran local date.
    """

    user_data = _valid_callback_user(
        callback_query
    )

    if user_data is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    try:
        await _ensure_user(
            db,
            user_data,
        )
    except (ValueError, RuntimeError):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    today = _today_tehran()

    products = await db.fetchall(
        """
        SELECT
            p.*
        FROM products p
        JOIN sellers s
          ON s.id = p.seller_id
        WHERE date(p.created_at) = ?
          AND COALESCE(s.is_active, 1) = 1
        ORDER BY p.created_at DESC
        LIMIT ?;
        """,
        (
            today,
            TOP_LIST_LIMIT,
        ),
    )

    rows: list[list[dict[str, Any]]] = []

    for product in products:
        rows.append(
            [
                {
                    "text": (
                        "🛍️ "
                        f"{product['name']}"
                    ),
                    "callback_data": (
                        f"product:{product['id']}"
                    ),
                }
            ]
        )

    if not products:
        text = (
            "🆕 امروز محصول جدیدی ثبت نشده."
        )
    else:
        text = (
            "🆕 <b>جدیدهای امروز</b>"
        )

    await _edit_callback_message(
        telegram,
        callback_query,
        text,
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_picks(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Show ArzanKadeh's recommended products.
    """

    user_data = _valid_callback_user(
        callback_query
    )

    if user_data is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    try:
        await _ensure_user(
            db,
            user_data,
        )
    except (ValueError, RuntimeError):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    products = await db.fetchall(
        """
        SELECT
            p.*
        FROM products p
        JOIN sellers s
          ON s.id = p.seller_id
        WHERE COALESCE(s.is_active, 1) = 1
        ORDER BY
            p.rating DESC,
            p.review_count DESC,
            p.views DESC
        LIMIT ?;
        """,
        (TOP_LIST_LIMIT,),
    )

    rows: list[list[dict[str, Any]]] = []

    for product in products:
        rows.append(
            [
                {
                    "text": (
                        "🛍️ "
                        f"{product['name']}"
                    ),
                    "callback_data": (
                        f"product:{product['id']}"
                    ),
                }
            ]
        )

    if not products:
        text = (
            "⭐ فعلاً پیشنهادی برای نمایش وجود ندارد."
        )
    else:
        text = (
            "⭐ <b>انتخاب ارزانکده</b>"
        )

    await _edit_callback_message(
        telegram,
        callback_query,
        text,
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_top_sellers(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Show the top active sellers.
    """

    user_data = _valid_callback_user(
        callback_query
    )

    if user_data is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    try:
        await _ensure_user(
            db,
            user_data,
        )
    except (ValueError, RuntimeError):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    sellers = await db.fetchall(
        """
        SELECT *
        FROM sellers
        WHERE COALESCE(is_active, 1) = 1
        ORDER BY
            rating DESC,
            review_count DESC,
            views DESC
        LIMIT ?;
        """,
        (TOP_LIST_LIMIT,),
    )

    rows: list[list[dict[str, Any]]] = []

    for seller in sellers:
        rows.append(
            [
                {
                    "text": (
                        "🏪 "
                        f"{seller['name']}"
                    ),
                    "callback_data": (
                        f"seller:{seller['id']}"
                    ),
                }
            ]
        )

    if not sellers:
        text = (
            "🏆 فعلاً فروشنده‌ای برای نمایش وجود ندارد."
        )
    else:
        text = (
            "🏆 <b>فروشندگان برتر</b>"
        )

    await _edit_callback_message(
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
    "handle_near_me",
    "handle_new_today",
    "handle_picks",
    "handle_top_sellers",
]