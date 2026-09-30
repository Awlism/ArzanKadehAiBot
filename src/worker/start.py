# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Lightweight /start handler for Cloudflare Workers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from typing import Any, Optional

from worker_backend.backend import backend
from worker.telegram import TelegramClient


START_TEXT = (
    "سلام 👋\n"
    "به ارزان‌کده خوش اومدی 🌱\n\n"
    "برای شروع، چند لحظه صبر کن..."
)


def _get_message_user(
    message: dict[str, Any],
) -> Optional[dict[str, Any]]:
    user = message.get("from")

    if not isinstance(user, dict):
        return None

    telegram_id = user.get("id")

    if telegram_id is None:
        return None

    try:
        telegram_id = int(telegram_id)
    except (TypeError, ValueError):
        return None

    if telegram_id < 1:
        return None

    return user


def _get_chat_id(
    message: dict[str, Any],
) -> Optional[int]:
    chat = message.get("chat")

    if not isinstance(chat, dict):
        return None

    chat_id = chat.get("id")

    if chat_id is None:
        return None

    try:
        return int(chat_id)
    except (TypeError, ValueError):
        return None


def _get_start_parameter(
    message: dict[str, Any],
) -> Optional[str]:
    text = message.get("text")

    if not isinstance(text, str):
        return None

    text = text.strip()

    if not text.startswith("/start"):
        return None

    parts = text.split(
        maxsplit=1
    )

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

    existing = await backend.fetchone(
        """
        SELECT *
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_id,),
    )

    now = _now_iso()

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

    if existing is not None:
        await backend.execute(
            """
            UPDATE users
            SET
                username = ?,
                first_name = ?,
                last_name = ?,
                updated_at = ?
            WHERE telegram_id = ?;
            """,
            (
                username,
                first_name,
                last_name,
                now,
                telegram_id,
            ),
        )

        return await backend.fetchone(
            """
            SELECT *
            FROM users
            WHERE telegram_id = ?
            LIMIT 1;
            """,
            (telegram_id,),
        )

    await backend.execute(
        """
        INSERT INTO users (
            telegram_id,
            username,
            first_name,
            last_name,
            active_mode,
            role_chosen,
            created_at,
            updated_at
        )
        VALUES (
            ?,
            ?,
            ?,
            ?,
            NULL,
            0,
            ?,
            ?
        );
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

    return await backend.fetchone(
        """
        SELECT *
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_id,),
    )


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

    if user is None or chat_id is None:
        return False

    await _ensure_user(
        user
    )

    start_parameter = _get_start_parameter(
        message
    )

    if start_parameter:
        await _handle_start_parameter(
            user,
            start_parameter,
        )

    await telegram.send_message(
        chat_id,
        START_TEXT,
    )

    return True


async def _handle_start_parameter(
    user: dict[str, Any],
    parameter: str,
) -> None:
    """
    Handle Telegram /start deep-link parameters.

    Seller referral/deep-link behavior will be migrated
    here in a later step.
    """

    del user
    del parameter


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


__all__ = [
    "START_TEXT",
    "handle_start",
]