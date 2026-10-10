# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Shared admin authorization and notification helpers for Cloudflare Workers.

ADMIN_USER_ID:
    Telegram numeric user ID authorized to perform admin actions.

ADMIN_CHAT_ID:
    Destination chat ID for admin notifications.
    May be a positive user chat ID or a negative group/supergroup chat ID.

ADMIN_USER_ID takes precedence for authorization.
ADMIN_CHAT_ID remains a legacy authorization fallback only when
ADMIN_USER_ID is not configured.
"""

from __future__ import annotations

from typing import Any, Optional


def _positive_int(value: Any) -> Optional[int]:
    """Return a positive integer, or None for invalid values."""

    if value is None or isinstance(value, bool):
        return None

    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if result < 1:
        return None

    return result


def _get_env_value(env: Any, name: str) -> Any:
    """Read an environment binding without exposing its value."""

    if env is None:
        return None

    if isinstance(env, dict):
        return env.get(name)

    return getattr(env, name, None)


def _configured_value(env: Any, name: str) -> Any:
    """Return a configured value, treating blank strings as missing."""

    value = _get_env_value(env, name)

    if value is None:
        return None

    if isinstance(value, str) and not value.strip():
        return None

    return value


def get_admin_chat_id(env: Any) -> Optional[int]:
    """
    Return a valid notification destination chat ID.

    Positive personal chat IDs and negative group chat IDs are accepted.
    Zero and invalid values are rejected.
    """

    value = _configured_value(env, "ADMIN_CHAT_ID")

    if value is None or isinstance(value, bool):
        return None

    try:
        chat_id = int(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if chat_id == 0:
        return None

    return chat_id


def is_admin_user(
    env: Any,
    telegram_user_id: Any,
) -> bool:
    """
    Check whether a Telegram user is authorized for admin actions.

    ADMIN_USER_ID takes precedence when configured.
    ADMIN_CHAT_ID is supported only as a legacy fallback.

    An explicitly configured but invalid ADMIN_USER_ID denies access
    rather than silently falling back to ADMIN_CHAT_ID.
    """

    user_id = _positive_int(telegram_user_id)

    if user_id is None:
        return False

    configured_user_id = _configured_value(
        env,
        "ADMIN_USER_ID",
    )

    if configured_user_id is not None:
        admin_user_id = _positive_int(configured_user_id)
    else:
        admin_user_id = _positive_int(
            _configured_value(env, "ADMIN_CHAT_ID")
        )

    if admin_user_id is None:
        return False

    return user_id == admin_user_id


__all__ = [
    "get_admin_chat_id",
    "is_admin_user",
]