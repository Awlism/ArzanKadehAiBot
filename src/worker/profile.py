# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker profile handlers.

This module intentionally does not import aiogram, sqlite,
aiosqlite, or any legacy bot module.
"""

from __future__ import annotations

from html import escape
from typing import Any, Optional

from worker.state import clear_state


CITY_PAGE_SIZE = 24


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

    return (
        _parse_int(chat.get("id")),
        _parse_int(user.get("id")),
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


async def handle_my_profile(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    chat_id, telegram_user_id = _callback_context(
        callback_query
    )

    del chat_id

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

    row = await db.fetchone(
        """
        SELECT
            u.id,
            u.first_name,
            u.last_name,
            u.username,
            u.city_id,
            c.name AS city_name
        FROM users u
        LEFT JOIN cities c
            ON c.id = u.city_id
        WHERE u.id = ?
        LIMIT 1;
        """,
        (user_id,),
    )

    if row is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ پروفایل پیدا نشد.",
            show_alert=True,
        )
        return

    name = " ".join(
        value
        for value in (
            row["first_name"],
            row["last_name"],
        )
        if value
    ).strip()

    if not name:
        name = "کاربر ارزانکده"

    lines = [
        "👤 <b>پروفایل من</b>",
        "",
        f"نام: {_html(name)}",
    ]

    if row["username"]:
        username = str(
            row["username"]
        ).strip().lstrip("@")

        if username:
            lines.append(
                f"نام کاربری: @{_html(username)}"
            )

    lines.append(
        "📍 شهر من: "
        + (
            _html(row["city_name"])
            if row["city_name"]
            else "ثبت نشده"
        )
    )

    await _edit_callback(
        telegram,
        callback_query,
        "\n".join(lines),
        _keyboard(
            [
                [
                    _button(
                        "📍 تغییر شهر",
                        "setcity",
                    )
                ],
                _back_button("account"),
            ]
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_set_city(
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
        user,
    )

    await clear_state(
        db,
        user_id,
    )

    cities = await db.fetchall(
        """
        SELECT id, name
        FROM cities
        ORDER BY name;
        """
    )

    if not cities:
        await _edit_callback(
            telegram,
            callback_query,
            "⚠️ هنوز شهری برای انتخاب ثبت نشده.",
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
        return

    rows: list[
        list[dict[str, Any]]
    ] = []

    current_row: list[
        dict[str, Any]
    ] = []

    for city in cities:
        city_id = _parse_int(
            city["id"]
        )

        if city_id is None:
            continue

        current_row.append(
            _button(
                str(city["name"]),
                f"pickcity:{city_id}",
            )
        )

        if len(current_row) == 3:
            rows.append(
                current_row
            )
            current_row = []

    if current_row:
        rows.append(
            current_row
        )

    rows.append(
        _back_button("account")
    )

    await _edit_callback(
        telegram,
        callback_query,
        "📍 شهر خودت رو انتخاب کن:",
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_pick_city(
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

    city_id = _parse_int(
        data.split(
            ":",
            1,
        )[1]
    )

    if city_id is None:
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
        user,
    )

    city = await db.fetchone(
        """
        SELECT id, name
        FROM cities
        WHERE id = ?
        LIMIT 1;
        """,
        (city_id,),
    )

    if city is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ این شهر یافت نشد.",
            show_alert=True,
        )
        return

    from datetime import datetime, timezone

    now = datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )

    await db.execute(
        """
        UPDATE users
        SET city_id = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            city_id,
            now,
            user_id,
        ),
    )

    await clear_state(
        db,
        user_id,
    )

    await _answer_callback(
        telegram,
        callback_query,
        text=(
            f"شهر شما به "
            f"{city['name']} تغییر کرد ✅"
        ),
    )

    await handle_my_profile(
        db,
        telegram,
        callback_query,
    )


__all__ = [
    "handle_my_profile",
    "handle_set_city",
    "handle_pick_city",
]