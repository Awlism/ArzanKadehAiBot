# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker-side favorites handlers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


PAGE_SIZE = 8
UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(
        UTC,
    ).isoformat(
        timespec="seconds"
    )


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


def _parse_id(
    callback_data: str,
    prefix: str,
) -> int | None:
    if not callback_data.startswith(prefix):
        return None

    value = callback_data[len(prefix):]

    try:
        number = int(value)
    except (TypeError, ValueError):
        return None

    if number < 1:
        return None

    return number


def _parse_page(
    callback_data: str,
) -> int | None:
    if not callback_data.startswith("favorites:"):
        return None

    value = callback_data.split(
        ":",
        1,
    )[1]

    try:
        page = int(value)
    except (TypeError, ValueError):
        return None

    if page < 0:
        return None

    return page


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


def _pagination_keyboard(
    rows: list[list[dict[str, Any]]],
    page: int,
    has_next: bool,
) -> dict[str, Any]:
    keyboard = list(rows)

    navigation: list[dict[str, Any]] = []

    if page > 0:
        navigation.append(
            {
                "text": "⬅️ قبلی",
                "callback_data": (
                    f"favorites:{page - 1}"
                ),
            }
        )

    if has_next:
        navigation.append(
            {
                "text": "بعدی ➡️",
                "callback_data": (
                    f"favorites:{page + 1}"
                ),
            }
        )

    if navigation:
        keyboard.append(navigation)

    keyboard.append(
        [
            {
                "text": "🔙 بازگشت",
                "callback_data": "main",
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


async def _get_product(
    db: Any,
    product_id: int,
) -> dict[str, Any] | None:
    return await db.fetchone(
        """
        SELECT
            p.id,
            p.name,
            p.seller_id
        FROM products p
        JOIN sellers s
          ON s.id = p.seller_id
        WHERE p.id = ?
          AND COALESCE(s.is_active, 1) = 1
        LIMIT 1;
        """,
        (product_id,),
    )


async def handle_favorite_add(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Add a product to the user's favorites.
    """

    product_id = _parse_id(
        str(callback_query.get("data") or ""),
        "favorite:",
    )

    if product_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شناسه محصول نامعتبر است.",
            True,
        )
        return

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

    product = await _get_product(
        db,
        product_id,
    )

    if product is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ این محصول یافت نشد.",
            True,
        )
        return

    existing = await db.fetchone(
        """
        SELECT id
        FROM favorites
        WHERE user_id = ?
          AND product_id = ?
        LIMIT 1;
        """,
        (
            user["id"],
            product_id,
        ),
    )

    if existing:
        await _answer_callback(
            telegram,
            callback_query,
            "این محصول از قبل در علاقه‌مندی‌هاست ❤️",
            True,
        )
        return

    try:
        result = await db.execute(
            """
            INSERT INTO favorites (
                user_id,
                product_id,
                created_at
            )
            VALUES (?, ?, ?);
            """,
            (
                user["id"],
                product_id,
                _now_iso(),
            ),
        )
    except Exception:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ ذخیره علاقه‌مندی انجام نشد.",
            True,
        )
        return

    if result.rowcount != 1:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ ذخیره علاقه‌مندی انجام نشد.",
            True,
        )
        return

    await _answer_callback(
        telegram,
        callback_query,
        "❤️ به علاقه‌مندی‌ها اضافه شد.",
        True,
    )


async def handle_favorite_remove(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Remove a product from the user's favorites.
    """

    product_id = _parse_id(
        str(callback_query.get("data") or ""),
        "unfavorite:",
    )

    if product_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شناسه محصول نامعتبر است.",
            True,
        )
        return

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

    result = await db.execute(
        """
        DELETE FROM favorites
        WHERE user_id = ?
          AND product_id = ?;
        """,
        (
            user["id"],
            product_id,
        ),
    )

    if result.rowcount != 1:
        await _answer_callback(
            telegram,
            callback_query,
            "این محصول دیگر در علاقه‌مندی‌ها نیست.",
            True,
        )
        return

    await _answer_callback(
        telegram,
        callback_query,
        "💔 از علاقه‌مندی‌ها حذف شد.",
        True,
    )


async def handle_favorites_list(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Show the user's favorite products with pagination.
    """

    callback_data = str(
        callback_query.get("data") or ""
    )

    page = _parse_page(
        callback_data
    )

    if page is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ صفحه نامعتبر است.",
            True,
        )
        return

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

    products = await db.fetchall(
        """
        SELECT
            p.id,
            p.name,
            f.created_at
        FROM favorites f
        JOIN products p
          ON p.id = f.product_id
        JOIN sellers s
          ON s.id = p.seller_id
        WHERE f.user_id = ?
          AND COALESCE(s.is_active, 1) = 1
        ORDER BY f.created_at DESC;
        """,
        (user["id"],),
    )

    if not products:
        await _edit_callback_message(
            telegram,
            callback_query,
            (
                "❤️ <b>علاقه‌مندی‌ها</b>\n\n"
                "هنوز محصولی به علاقه‌مندی‌ها "
                "اضافه نکردی."
            ),
            _keyboard([]),
        )

        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    offset = page * PAGE_SIZE
    page_rows = products[
        offset:offset + PAGE_SIZE
    ]

    if not page_rows:
        await _edit_callback_message(
            telegram,
            callback_query,
            "⚠️ این صفحه وجود ندارد.",
            _keyboard([]),
        )

        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    has_next = (
        offset + PAGE_SIZE
        < len(products)
    )

    rows: list[list[dict[str, Any]]] = []

    for product in page_rows:
        name = str(
            product.get("name") or "بدون نام"
        )

        rows.append(
            [
                {
                    "text": f"🛍️ {name}",
                    "callback_data": (
                        f"product:{product['id']}"
                    ),
                }
            ]
        )

    await _edit_callback_message(
        telegram,
        callback_query,
        "❤️ <b>علاقه‌مندی‌ها</b>",
        _pagination_keyboard(
            rows,
            page,
            has_next,
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


__all__ = [
    "handle_favorite_add",
    "handle_favorite_remove",
    "handle_favorites_list",
]