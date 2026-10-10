# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Shared admin authorization helpers for Cloudflare Workers.

ADMIN_USER_ID:
    Telegram numeric user ID authorized to perform admin actions.

ADMIN_CHAT_ID:
    Legacy fallback for existing deployments. This variable may
    also be used by notification flows as the destination chat ID.

Authorization always compares a positive Telegram user ID.
Missing or invalid configuration fails closed.
"""

from __future__ import annotations

from typing import Any, Optional


def _positive_int(value: Any) -> Optional[int]:
    """Return a positive integer, or None for invalid values."""

    if value is None:
        return None

    if isinstance(value, bool):
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


def is_admin_user(
    env: Any,
    telegram_user_id: Any,
) -> bool:
    """
    Check whether a Telegram user is authorized for admin actions.

    ADMIN_USER_ID takes precedence when configured.
    ADMIN_CHAT_ID is supported only as a legacy fallback.

    An explicitly configured but invalid ADMIN_USER_ID denies access;
    it does not silently fall back to the legacy setting.
    """

    user_id = _positive_int(telegram_user_id)

    if user_id is None:
        return False

    configured_user_id = _get_env_value(
        env,
        "ADMIN_USER_ID",
    )

    if configured_user_id is not None and str(
        configured_user_id
    ).strip():
        admin_user_id = _positive_int(
            configured_user_id
        )
    else:
        admin_user_id = _positive_int(
            _get_env_value(
                env,
                "ADMIN_CHAT_ID",
            )
        )

    if admin_user_id is None:
        return False

    return user_id == admin_user_id


__all__ = [
    "is_admin_user",
]
