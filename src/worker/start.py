# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Lightweight /start handler for Cloudflare Workers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from typing import Any, Optional

from worker_backend.backend import backend
from worker.referrals import record_referral_if_new
from worker.telegram import TelegramAPIError, TelegramClient


START_TEXT = (
    "سلام 👋\n"
    "به ارزان‌کده خوش اومدی 🌱\n\n"
    "برای شروع، چند لحظه صبر کن..."
)


def _get_message_user(
    message: dict[str, Any],
) -> Optional[dict[str, Any]]:
    user = message.get("from")

    if not isinstance(
        user,
        dict,
    ):
        return None

    telegram_id = user.get(
        "id"
    )

    if telegram_id is None:
        return None

    try:
        telegram_id = int(
            telegram_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if telegram_id < 1:
        return None

    return user


def _get_chat_id(
    message: dict[str, Any],
) -> Optional[int]:
    chat = message.get(
        "chat"
    )

    if not isinstance(
        chat,
        dict,
    ):
        return None

    chat_id = chat.get(
        "id"
    )

    if chat_id is None:
        return None

    try:
        return int(
            chat_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


def _get_start_parameter(
    message: dict[str, Any],
) -> Optional[str]:
    text = message.get(
        "text"
    )

    if not isinstance(
        text,
        str,
    ):
        return None

    text = text.strip()

    if not text:
        return None

    parts = text.split(
        maxsplit=1
    )

    command = parts[0]

    if (
        command != "/start"
        and not command.startswith(
            "/start@"
        )
    ):
        return None

    if len(parts) < 2:
        return None

    parameter = parts[1].strip()

    return parameter or None


async def _ensure_user(
    user: dict[str, Any],
) -> Optional[dict[str, Any]]:
    telegram_id = int(
        user["id"]
    )

    first_name = user.get(
        "first_name"
    )
    last_name = user.get(
        "last_name"
    )
    username = user.get(
        "username"
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

    username = (
        str(username).strip()
        if username is not None
        else None
    )

    now = _now_iso()

    result = await backend.execute(
        """
        INSERT INTO users (
            telegram_id,
            username,
            first_name,
            last_name,
            created_at,
            updated_at
        )
        VALUES (
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        )
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

    db_user = await backend.fetchone(
        """
        SELECT *
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (
            telegram_id,
        ),
    )

    if db_user is None:
        raise RuntimeError(
            "D1 user write diagnostic: "
            f"telegram_id={telegram_id}, "
            f"rowcount={result.rowcount}, "
            f"lastrowid={result.lastrowid}, "
            "post_write_read=none"
        )

    return db_user


async def handle_start(
    message: dict[str, Any],
    telegram: TelegramClient,
) -> bool:
    user = _get_message_user(
        message
    )

    chat_id = _get_chat_id(
        message
    )

    if (
        user is None
        or chat_id is None
    ):
        return False

    db_user = await _ensure_user(
        user
    )

    if db_user is None:
        return False

    start_parameter = _get_start_parameter(
        message
    )

    if start_parameter:
        await _handle_start_parameter(
            db_user,
            start_parameter,
        )

    try:
        await telegram.send_message(
            chat_id,
            START_TEXT,
        )
    except TelegramAPIError as exc:
        diagnostic = {
            "telegram_id": db_user.get("telegram_id"),
            "id": db_user.get("id"),
            "username": db_user.get("username"),
            "first_name": db_user.get("first_name"),
            "last_name": db_user.get("last_name"),
            "created_at": db_user.get("created_at"),
            "updated_at": db_user.get("updated_at"),
        }

        raise RuntimeError(
            "Telegram send failed after D1 user read: "
            f"{diagnostic}; "
            f"telegram_error={exc}"
        ) from exc

    return True


async def _handle_start_parameter(
    user: dict[str, Any],
    parameter: str,
) -> None:
    """
    Handle Telegram /start deep-link parameters.

    Supported referral format:
        /start shop_<seller_id>
    """

    if not parameter.startswith(
        "shop_"
    ):
        return

    seller_id_text = parameter[
        len("shop_"):
    ].strip()

    try:
        seller_id = int(
            seller_id_text
        )
    except (
        TypeError,
        ValueError,
    ):
        return

    if seller_id < 1:
        return

    user_id = user.get(
        "id"
    )

    try:
        referred_user_id = int(
            user_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return

    if referred_user_id < 1:
        return

    await record_referral_if_new(
        backend,
        seller_id,
        referred_user_id,
    )


def _now_iso() -> str:
    from datetime import (
        datetime,
        timezone,
    )

    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


__all__ = [
    "START_TEXT",
    "handle_start",
]