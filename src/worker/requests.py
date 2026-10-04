# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker "My Requests" handlers.

This module intentionally does not import aiogram, sqlite,
aiosqlite, or any legacy bot module.
"""

from __future__ import annotations

from html import escape
from typing import Any, Optional

from worker.state import clear_state


REQUEST_LIMIT = 20

REQUEST_STATUS_LABELS = {
    "PENDING": "🟡 در حال بررسی",
    "REJECTED": "🔴 رد شد",
    "APPROVED": "🟢 تأیید شد",
    "COORDINATING": "🔵 در حال هماهنگی",
    "ACTIVE": "🟢 فعال",
    "EXPIRED": "⏰ تمام‌شده",
}


def _html(value: Any) -> str:
    if value is None:
        return ""

    return escape(
        str(value),
        quote=False,
    )


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
    callback_data: str = "account",
) -> list[dict[str, Any]]:
    return [
        _button(
            "🔙 بازگشت",
            callback_data,
        )
    ]


def _callback_user_id(
    callback_query: dict[str, Any],
) -> Optional[int]:
    user = (
        callback_query.get("from")
        or {}
    )

    return _parse_int(
        user.get("id")
    )


async def _ensure_user(
    db: Any,
    user: dict[str, Any],
) -> int:
    from datetime import datetime, timezone

    telegram_id = _parse_int(
        user.get("id")
    )

    if telegram_id is None:
        raise ValueError(
            "Invalid Telegram user id."
        )

    username = user.get(
        "username"
    )
    first_name = user.get(
        "first_name"
    )
    last_name = user.get(
        "last_name"
    )

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
        SELECT id
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_id,),
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


def _status_label(
    status: Any,
) -> str:
    value = str(
        status or "PENDING"
    )

    return REQUEST_STATUS_LABELS.get(
        value,
        REQUEST_STATUS_LABELS["PENDING"],
    )


async def _list_my_requests(
    db: Any,
    user_id: int,
) -> list[dict[str, Any]]:
    request_rows = await db.fetchall(
        """
        SELECT
            id,
            request_type,
            topic,
            status,
            created_at
        FROM requests
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?;
        """,
        (
            user_id,
            REQUEST_LIMIT,
        ),
    )

    report_rows = await db.fetchall(
        """
        SELECT
            id,
            seller_id,
            product_id,
            status,
            created_at
        FROM reports
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?;
        """,
        (
            user_id,
            REQUEST_LIMIT,
        ),
    )

    items: list[
        dict[str, Any]
    ] = []

    for row in request_rows:
        request_type = str(
            row["request_type"]
            or ""
        )

        label = {
            "support": "🛟 پشتیبانی",
            "ad": "📢 درخواست تبلیغات",
        }.get(
            request_type,
            request_type or "درخواست",
        )

        items.append(
            {
                "kind": "request",
                "id": row["id"],
                "title": (
                    row["topic"]
                    or label
                ),
                "created_at": (
                    row["created_at"]
                    or ""
                ),
                "status_label": _status_label(
                    row["status"]
                ),
            }
        )

    for row in report_rows:
        target = (
            "فروشگاه"
            if row["seller_id"] is not None
            else "محصول"
        )

        items.append(
            {
                "kind": "report",
                "id": row["id"],
                "title": (
                    f"🚨 گزارش {target}"
                ),
                "created_at": (
                    row["created_at"]
                    or ""
                ),
                "status_label": _status_label(
                    row["status"]
                ),
            }
        )

    items.sort(
        key=lambda item: item["created_at"],
        reverse=True,
    )

    return items[
        :REQUEST_LIMIT
    ]


async def handle_my_requests(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    telegram_user_id = _callback_user_id(
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
        user,
    )

    await clear_state(
        db,
        user_id,
    )

    items = await _list_my_requests(
        db,
        user_id,
    )

    if not items:
        text = (
            "📋 <b>درخواست‌های من</b>\n\n"
            "هنوز درخواستی ثبت نکرده‌اید."
        )

    else:
        lines = [
            "📋 <b>درخواست‌های من</b>",
            "",
        ]

        for item in items:
            created_at = str(
                item["created_at"]
            )

            date_text = (
                created_at[:10]
                if created_at
                else "—"
            )

            lines.append(
                f"{_html(item['title'])} — "
                f"{_html(item['status_label'])}\n"
                f"{_html(date_text)}"
            )

        text = "\n\n".join(
            lines
        )

    await _edit_callback(
        telegram,
        callback_query,
        text,
        _keyboard(
            [
                _back_button("account"),
            ]
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


__all__ = [
    "REQUEST_LIMIT",
    "REQUEST_STATUS_LABELS",
    "handle_my_requests",
]