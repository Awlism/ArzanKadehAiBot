# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker-side hot products handler.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from typing import Any


TOP_LIST_LIMIT = 10


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


def _keyboard(
    products: list[dict[str, Any]],
) -> dict[str, Any]:
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

    rows.append(
        [
            {
                "text": "🔙 بازگشت",
                "callback_data": "main",
            }
        ]
    )

    return {
        "inline_keyboard": rows,
    }


async def handle_hot(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Show the hottest products.

    Selection is compatible with the legacy buyer handler:
    active sellers only, ordered by views DESC and rating DESC,
    limited to TOP_LIST_LIMIT products.
    """

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
        await _ensure_user(
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

    products = await db.fetchall(
        """
        SELECT
            p.*
        FROM products p
        JOIN sellers s
          ON s.id = p.seller_id
        WHERE COALESCE(s.is_active, 1) = 1
        ORDER BY
            p.views DESC,
            p.rating DESC
        LIMIT ?;
        """,
        (TOP_LIST_LIMIT,),
    )

    if not products:
        text = (
            "🔥 هنوز محصولی برای نمایش وجود ندارد."
        )
    else:
        text = (
            "🔥 <b>داغ‌ترین‌ها</b>"
        )

    await _edit_callback_message(
        telegram,
        callback_query,
        text,
        _keyboard(products),
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

    if chat_id is None or message_id is None:
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
    "handle_hot",
]