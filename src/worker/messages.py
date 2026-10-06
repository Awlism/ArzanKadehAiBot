# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Generic Telegram message handler for Cloudflare Workers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

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
from worker.state import ensure_state_table, get_state
from worker.support import handle_support_text
from worker.telegram import TelegramClient
from worker_backend.backend import backend


async def handle_message(
    message: dict[str, Any],
    telegram: TelegramClient,
    env: Optional[Any] = None,
) -> Any:
    """
    Handle a Telegram message.

    The active persistent Worker state is loaded from D1 so
    multi-request flows can continue across webhook requests.
    """

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

    user_row = await backend.fetchone(
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

    if user_row is None:
        return None

    try:
        user_id = int(
            user_row["id"]
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    await ensure_state_table(
        backend
    )

    state = await get_state(
        backend,
        user_id,
    )

    if state is None:
        return None

    return await _handle_active_state(
        message=message,
        telegram=telegram,
        state=state,
        env=env,
    )


async def _handle_active_state(
    *,
    message: dict[str, Any],
    telegram: TelegramClient,
    state: dict[str, Any],
    env: Optional[Any] = None,
) -> Any:
    """
    Dispatch an active persistent state.
    """

    state_name = state.get(
        "state"
    )

    if not isinstance(
        state_name,
        str,
    ):
        return None

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
        return await handle_support_text(
            backend,
            telegram,
            message,
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

    return None


__all__ = [
    "handle_message",
]