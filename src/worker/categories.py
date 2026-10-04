# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker-side category handlers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from html import escape
from typing import Any


PAGE_SIZE_CATEGORIES = 8
PAGE_SIZE_PRODUCTS = 8


def _html(value: Any) -> str:
    if value is None:
        return ""

    return escape(
        str(value),
        quote=False,
    )


def _parse_category_callback(
    callback_data: str,
) -> tuple[int | None, int | None]:
    parts = callback_data.split(":")

    if len(parts) != 3:
        return None, None

    try:
        category_id = int(parts[1])
        page = int(parts[2])
    except (TypeError, ValueError):
        return None, None

    if category_id < 0 or page < 0:
        return None, None

    return category_id, page


def _pagination_keyboard(
    base_callback: str,
    page: int,
    has_next: bool,
) -> list[dict[str, Any]]:
    row: list[dict[str, Any]] = []

    if page > 0:
        row.append(
            {
                "text": "◀️ قبلی",
                "callback_data": (
                    f"{base_callback}:{page - 1}"
                ),
            }
        )

    if has_next:
        row.append(
            {
                "text": "بعدی ▶️",
                "callback_data": (
                    f"{base_callback}:{page + 1}"
                ),
            }
        )

    return row


def _keyboard(
    rows: list[list[dict[str, Any]]],
    back_callback: str,
    pagination: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    keyboard = list(rows)

    if pagination:
        keyboard.append(pagination)

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


async def _get_category(
    db: Any,
    category_id: int,
) -> dict[str, Any] | None:
    return await db.fetchone(
        """
        SELECT
            id,
            parent_id,
            name,
            emoji
        FROM categories
        WHERE id = ?
        LIMIT 1;
        """,
        (category_id,),
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

    user_row = await db.fetchone(
        """
        SELECT *
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_id,),
    )

    if user_row is None:
        raise RuntimeError(
            "Failed to create or load user."
        )

    return user_row


async def _log_category_click(
    db: Any,
    user_id: int,
    category_id: int,
) -> None:
    await db.execute(
        """
        INSERT INTO events (
            user_id,
            event_type,
            entity_type,
            entity_id,
            created_at
        )
        VALUES (?, ?, ?, ?, ?);
        """,
        (
            user_id,
            "category_click",
            "category",
            category_id,
            _now_iso(),
        ),
    )


async def _render_categories_root(
    db: Any,
    page: int,
) -> tuple[str, dict[str, Any]]:
    rows = await db.fetchall(
        """
        SELECT
            id,
            name,
            emoji
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

    keyboard_rows: list[list[dict[str, Any]]] = []

    for row in page_rows:
        keyboard_rows.append(
            [
                {
                    "text": (
                        f"{row['emoji']} "
                        f"{row['name']}"
                    ),
                    "callback_data": (
                        f"cat:{row['id']}:0"
                    ),
                }
            ]
        )

    pagination = _pagination_keyboard(
        "cat:0",
        page,
        has_next,
    )

    return (
        "🗂 <b>دسته‌بندی‌ها</b>\n\n"
        "یک دسته را انتخاب کن:",
        _keyboard(
            keyboard_rows,
            "main",
            pagination,
        ),
    )


async def _render_category_children(
    db: Any,
    category: dict[str, Any],
    page: int,
) -> tuple[str, dict[str, Any]] | None:
    category_id = int(
        category["id"]
    )

    children = await db.fetchall(
        """
        SELECT
            id,
            name,
            emoji
        FROM categories
        WHERE parent_id = ?
        ORDER BY id;
        """,
        (category_id,),
    )

    if not children:
        return None

    offset = page * PAGE_SIZE_CATEGORIES

    page_rows = children[
        offset:offset + PAGE_SIZE_CATEGORIES
    ]

    has_next = (
        offset + PAGE_SIZE_CATEGORIES
        < len(children)
    )

    keyboard_rows: list[list[dict[str, Any]]] = []

    for row in page_rows:
        keyboard_rows.append(
            [
                {
                    "text": (
                        f"{row['emoji']} "
                        f"{row['name']}"
                    ),
                    "callback_data": (
                        f"cat:{row['id']}:0"
                    ),
                }
            ]
        )

    parent_id = category.get("parent_id")

    back_callback = (
        f"cat:{int(parent_id)}:0"
        if parent_id
        else "cat:0:0"
    )

    pagination = _pagination_keyboard(
        f"cat:{category_id}",
        page,
        has_next,
    )

    return (
        f"{_html(category.get('emoji'))} "
        f"<b>{_html(category.get('name'))}</b>\n\n"
        "یک زیردسته را انتخاب کن:",
        _keyboard(
            keyboard_rows,
            back_callback,
            pagination,
        ),
    )


async def _render_category_products(
    db: Any,
    category: dict[str, Any],
    page: int,
) -> tuple[str, dict[str, Any]]:
    category_id = int(
        category["id"]
    )

    products = await db.fetchall(
        """
        SELECT
            p.id,
            p.name,
            p.price,
            p.seller_id,
            s.name AS seller_name
        FROM products p
        JOIN sellers s
          ON s.id = p.seller_id
        WHERE p.category_id = ?
          AND COALESCE(s.is_active, 1) = 1
        ORDER BY p.views DESC,
                 p.id DESC;
        """,
        (category_id,),
    )

    parent_id = category.get("parent_id")

    back_callback = (
        f"cat:{int(parent_id)}:0"
        if parent_id
        else "cat:0:0"
    )

    if not products:
        return (
            f"{_html(category.get('emoji'))} "
            f"<b>{_html(category.get('name'))}</b>\n\n"
            "📦 فعلاً محصولی در این دسته ثبت نشده.",
            _keyboard(
                [],
                back_callback,
            ),
        )

    offset = page * PAGE_SIZE_PRODUCTS

    page_rows = products[
        offset:offset + PAGE_SIZE_PRODUCTS
    ]

    has_next = (
        offset + PAGE_SIZE_PRODUCTS
        < len(products)
    )

    keyboard_rows: list[list[dict[str, Any]]] = []

    for product in page_rows:
        price = product.get("price")

        if price is None:
            price_text = "توافقی"
        else:
            try:
                number = float(price)

                if number.is_integer():
                    price_text = (
                        f"{int(number):,} تومان"
                    )
                else:
                    price_text = (
                        f"{number:,.2f} تومان"
                    )
            except (
                TypeError,
                ValueError,
            ):
                price_text = str(price)

        keyboard_rows.append(
            [
                {
                    "text": (
                        "🛍️ "
                        f"{product['name']}"
                        " - "
                        f"{price_text}"
                    ),
                    "callback_data": (
                        f"product:{product['id']}"
                    ),
                }
            ]
        )

    pagination = _pagination_keyboard(
        f"cat:{category_id}",
        page,
        has_next,
    )

    return (
        f"{_html(category.get('emoji'))} "
        f"<b>{_html(category.get('name'))}</b>\n\n"
        "محصولات این دسته:",
        _keyboard(
            keyboard_rows,
            back_callback,
            pagination,
        ),
    )


async def handle_category(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Handle category navigation and category product listings.

    Supported callbacks:
        cat:0:<page>
        cat:<category_id>:<page>
    """

    callback_data = str(
        callback_query.get(
            "data",
            "",
        )
    )

    category_id, page = _parse_category_callback(
        callback_data
    )

    if category_id is None or page is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ درخواست نامعتبر است.",
            True,
        )
        return

    callback_user = callback_query.get(
        "from"
    )

    if not isinstance(
        callback_user,
        dict,
    ):
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
            callback_user,
        )
    except (
        ValueError,
        RuntimeError,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    if category_id == 0:
        text, keyboard = await _render_categories_root(
            db,
            page,
        )

        await _edit_callback_message(
            telegram,
            callback_query,
            text,
            keyboard,
        )

        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    category = await _get_category(
        db,
        category_id,
    )

    if category is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ این دسته‌بندی یافت نشد.",
            True,
        )
        return

    await _log_category_click(
        db,
        int(user["id"]),
        category_id,
    )

    child_result = await _render_category_children(
        db,
        category,
        page,
    )

    if child_result is not None:
        text, keyboard = child_result

        await _edit_callback_message(
            telegram,
            callback_query,
            text,
            keyboard,
        )

        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    text, keyboard = await _render_category_products(
        db,
        category,
        page,
    )

    await _edit_callback_message(
        telegram,
        callback_query,
        text,
        keyboard,
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def _answer_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    text: str | None = None,
    show_alert: bool = False,
) -> None:
    callback_id = callback_query.get(
        "id"
    )

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
    message = callback_query.get(
        "message"
    )

    if not isinstance(
        message,
        dict,
    ):
        return

    chat = message.get(
        "chat"
    )

    if not isinstance(
        chat,
        dict,
    ):
        return

    chat_id = chat.get(
        "id"
    )

    message_id = message.get(
        "message_id"
    )

    if chat_id is None:
        return

    try:
        chat_id = int(chat_id)
        message_id = int(message_id)
    except (
        TypeError,
        ValueError,
    ):
        return

    await telegram.edit_message_text(
        chat_id,
        message_id,
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


def _now_iso() -> str:
    from datetime import (
        datetime,
        timezone,
    )

    return datetime.now(
        timezone.utc,
    ).isoformat(
        timespec="seconds"
    )


__all__ = [
    "handle_category",
]