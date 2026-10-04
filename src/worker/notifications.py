# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker notification handlers.

This module intentionally does not import aiogram, sqlite,
aiosqlite, or any legacy bot module.
"""

from __future__ import annotations

from html import escape
from typing import Any, Optional

from worker.state import clear_state


NOTIFICATION_LIMIT = 20


def _html(value: Any) -> str:
    if value is None:
        return ""

    return escape(
        str(value),
        quote=False,
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


def _back_button(
    callback_data: str = "main",
) -> list[dict[str, Any]]:
    return [
        _button(
            "🔙 بازگشت",
            callback_data,
        )
    ]


def _parse_int(
    value: Any,
) -> Optional[int]:
    try:
        result = int(
            str(value).strip()
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if result < 1:
        return None

    return result


def _callback_context(
    callback_query: dict[str, Any],
) -> tuple[
    Optional[int],
    Optional[int],
]:
    message = (
        callback_query.get("message")
        or {}
    )

    chat = (
        message.get("chat")
        or {}
    )

    user = (
        callback_query.get("from")
        or {}
    )

    chat_id = _parse_int(
        chat.get("id")
    )

    telegram_user_id = _parse_int(
        user.get("id")
    )

    return (
        chat_id,
        telegram_user_id,
    )


async def _ensure_user(
    db: Any,
    telegram_user_id: int,
    *,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> int:
    from datetime import datetime, timezone

    now = datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )

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
            telegram_user_id,
            username,
            first_name,
            last_name,
            now,
            now,
        ),
    )

    row = await db.fetchone(
        """
        SELECT id
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_user_id,),
    )

    if row is None:
        raise RuntimeError(
            "Failed to resolve internal user id."
        )

    return int(
        row["id"]
    )


async def _answer_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    *,
    text: Optional[str] = None,
    show_alert: bool = False,
) -> None:
    callback_id = callback_query.get(
        "id"
    )

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
    message = (
        callback_query.get("message")
        or {}
    )

    chat = (
        message.get("chat")
        or {}
    )

    chat_id = _parse_int(
        chat.get("id")
    )

    message_id = _parse_int(
        message.get("message_id")
    )

    if (
        chat_id is None
        or message_id is None
    ):
        return

    await telegram.edit_message_text(
        chat_id,
        message_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def _render_notifications(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    *,
    answer_text: Optional[str] = None,
) -> None:
    _, telegram_user_id = _callback_context(
        callback_query
    )

    if telegram_user_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر شناسایی نشد.",
            show_alert=True,
        )
        return

    user = (
        callback_query.get("from")
        or {}
    )

    user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    rows = await db.fetchall(
        """
        SELECT
            id,
            title,
            message,
            notification_type,
            is_read,
            created_at
        FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?;
        """,
        (
            user_id,
            NOTIFICATION_LIMIT,
        ),
    )

    if not rows:
        await clear_state(
            db,
            user_id,
        )

        await _edit_callback(
            telegram,
            callback_query,
            "🔔 اعلان جدیدی نداری.",
            _keyboard(
                [
                    _back_button("main"),
                ]
            ),
        )

        await _answer_callback(
            telegram,
            callback_query,
            text=answer_text,
        )

        return

    lines = [
        "🔔 <b>اعلان‌ها</b>",
        "",
    ]

    rows_keyboard: list[
        list[dict[str, Any]]
    ] = []

    for notification in rows:
        mark = (
            "✅"
            if notification["is_read"]
            else "🆕"
        )

        title = _html(
            notification.get("title")
            or ""
        )

        message = _html(
            notification.get("message")
            or ""
        )

        lines.append(
            f"{mark} <b>{title}</b>\n"
            f"{message}"
        )

        if not notification["is_read"]:
            raw_title = str(
                notification.get(
                    "title"
                )
                or "اعلان"
            )

            button_title = (
                raw_title[:20]
            )

            rows_keyboard.append(
                [
                    _button(
                        f"خواندم: {button_title}",
                        (
                            "notifread:"
                            f"{notification['id']}"
                        ),
                    )
                ]
            )

    rows_keyboard.append(
        _back_button("main")
    )

    await _edit_callback(
        telegram,
        callback_query,
        "\n\n".join(lines),
        _keyboard(
            rows_keyboard
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
        text=answer_text,
    )


async def handle_notifications(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    _, telegram_user_id = _callback_context(
        callback_query
    )

    if telegram_user_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر شناسایی نشد.",
            show_alert=True,
        )
        return

    user = (
        callback_query.get("from")
        or {}
    )

    user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    await clear_state(
        db,
        user_id,
    )

    await _render_notifications(
        db,
        telegram,
        callback_query,
    )


async def handle_notification_read(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(
        callback_query.get("data")
        or ""
    )

    if ":" not in data:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    notification_id = _parse_int(
        data.split(
            ":",
            1,
        )[1]
    )

    if notification_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    _, telegram_user_id = _callback_context(
        callback_query
    )

    if telegram_user_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر شناسایی نشد.",
            show_alert=True,
        )
        return

    user = (
        callback_query.get("from")
        or {}
    )

    user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    result = await db.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE id = ?
          AND user_id = ?
          AND is_read = 0;
        """,
        (
            notification_id,
            user_id,
        ),
    )

    if result.rowcount != 1:
        await _render_notifications(
            db,
            telegram,
            callback_query,
            answer_text=(
                "ℹ️ این اعلان قبلاً خوانده شده "
                "یا دیگر در دسترس نیست."
            ),
        )
        return

    await _render_notifications(
        db,
        telegram,
        callback_query,
        answer_text="علامت خوانده شد ✅",
    )


__all__ = [
    "NOTIFICATION_LIMIT",
    "handle_notifications",
    "handle_notification_read",
]