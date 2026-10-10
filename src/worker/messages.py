# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Generic Telegram message handler for Cloudflare Workers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from worker.admin import handle_admin_user_search_message
from worker.admin_ads import handle_admin_ad_message
from worker.product_management import handle_product_message
from worker.publicads import handle_public_ad_message
from worker.report import handle_report_text
from worker.review import handle_review_text
from worker.search import handle_search_message
from worker.seller_registration import handle_register_seller_message
from worker.shop import handle_shop_edit_message
from worker.start import _send_main_menu
from worker.state import (
    clear_state,
    ensure_state_table,
    get_state,
)
from worker.support import handle_support_text
from worker.telegram import TelegramClient
from worker_backend.backend import backend


def _now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


async def _ensure_message_user(
    message: dict[str, Any],
) -> Optional[int]:
    user = message.get("from")

    if not isinstance(
        user,
        dict,
    ):
        return None

    telegram_id = user.get(
        "id"
    )

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

    now = _now_iso()

    await backend.execute(
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

    row = await backend.fetchone(
        """
        SELECT id
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (
            telegram_id,
        ),
    )

    if row is None:
        return None

    try:
        user_id = int(
            row["id"]
        )
    except (
        TypeError,
        ValueError,
        KeyError,
    ):
        return None

    if user_id < 1:
        return None

    return user_id


async def handle_message(
    message: dict[str, Any],
    telegram: TelegramClient,
    env: Optional[Any] = None,
) -> Any:
    """
    Handle a Telegram message.

    The active persistent Worker state is loaded from D1 so
    multi-request flows can continue across webhook requests.

    If no active state exists, or an unknown state is found,
    the user is returned to the main menu.
    """

    user_id = await _ensure_message_user(
        message
    )

    if user_id is None:
        return None

    await ensure_state_table(
        backend
    )

    state = await get_state(
        backend,
        user_id,
    )

    chat = message.get(
        "chat"
    ) or {}

    chat_id = chat.get(
        "id"
    )

    if chat_id is None:
        return None

    try:
        chat_id = int(
            chat_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if state is None:
        await _send_main_menu(
            telegram,
            chat_id,
        )

        return None

    return await _handle_active_state(
        message=message,
        telegram=telegram,
        state=state,
        user_id=user_id,
        chat_id=chat_id,
        env=env,
    )


async def _handle_active_state(
    *,
    message: dict[str, Any],
    telegram: TelegramClient,
    state: dict[str, Any],
    user_id: int,
    chat_id: int,
    env: Optional[Any] = None,
) -> Any:
    """
    Dispatch an active persistent state.

    Unknown or malformed states are cleared to prevent a
    user from becoming stuck in an unsupported conversation flow.
    """

    state_name = state.get(
        "state"
    )

    if not isinstance(
        state_name,
        str,
    ) or not state_name.strip():
        await clear_state(
            backend,
            user_id,
        )

        await _send_main_menu(
            telegram,
            chat_id,
        )

        return None

    state_name = state_name.strip()

    if state_name == "review:waiting_text":
        return await handle_review_text(
            message,
            telegram,
        )

    if state_name == "report:waiting_description":
        return await handle_report_text(
            message,
            telegram,
        )

    if state_name == "search":
        return await handle_search_message(
            backend,
            telegram,
            message,
        )

    if state_name == "seller_registration":
        return await handle_register_seller_message(
            backend,
            telegram,
            message,
        )

    if state_name == "product_management":
        return await handle_product_message(
            backend,
            telegram,
            message,
        )

    if state_name == "shop_edit":
        return await handle_shop_edit_message(
            backend,
            telegram,
            message,
        )

    if state_name == "support":
        if env is None:
            return None

        return await handle_support_text(
            backend,
            telegram,
            message,
            env,
        )

    if state_name == "public_ad":
        return await handle_public_ad_message(
            backend,
            telegram,
            message,
        )

    if state_name == "admin:user_search":
        if env is None:
            return None

        return await handle_admin_user_search_message(
            message,
            telegram,
            env,
        )

    if state_name == "admin_ad_setting":
        if env is None:
            return None

        return await handle_admin_ad_message(
            backend,
            telegram,
            message,
            env,
        )

    # A state not handled by this Worker version is stale.
    # Clear it and give the user a safe way to continue.
    await clear_state(
        backend,
        user_id,
    )

    await _send_main_menu(
        telegram,
        chat_id,
    )

    return None


__all__ = [
    "handle_message",
]