# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Generic Telegram message handler for Cloudflare Workers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from typing import Any

from worker.state import get_state
from worker.telegram import TelegramClient
from worker_backend.backend import backend


async def handle_message(
    message: dict[str, Any],
    telegram: TelegramClient,
) -> Any:
    """
    Handle a Telegram message.

    The active persistent Worker state is loaded from D1 so
    multi-request flows can continue across webhook requests.

    Feature-specific state handling is intentionally left to
    the corresponding feature handlers.
    """

    user = message.get("from")

    if not isinstance(user, dict):
        return None

    user_id = user.get("id")

    if user_id is None:
        return None

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None

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
    )


async def _handle_active_state(
    *,
    message: dict[str, Any],
    telegram: TelegramClient,
    state: dict[str, Any],
) -> Any:
    """
    Dispatch an active persistent state.

    Feature-specific states will be connected here one by one.
    """

    state_name = state.get("state")

    if not isinstance(state_name, str):
        return None

    return None


__all__ = [
    "handle_message",
]