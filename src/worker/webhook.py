# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker Telegram webhook foundation.

This module:
- requires a configured Telegram webhook secret
- validates the Telegram webhook secret
- parses Telegram JSON updates
- identifies the update type

It intentionally does not import aiogram.
It does not call the Telegram Bot API.
"""

from typing import Any, Optional


TELEGRAM_UPDATE_TYPES = (
    "message",
    "edited_message",
    "channel_post",
    "edited_channel_post",
    "inline_query",
    "chosen_inline_result",
    "callback_query",
    "shipping_query",
    "pre_checkout_query",
    "poll",
    "poll_answer",
    "my_chat_member",
    "chat_member",
    "chat_join_request",
)


class WebhookError(Exception):
    """Base error for the Worker webhook layer."""


class UnauthorizedWebhookError(WebhookError):
    """Raised when the webhook secret is missing or invalid."""


class InvalidWebhookPayloadError(WebhookError):
    """Raised when the webhook body is not a valid JSON object."""


def get_webhook_secret(
    env: Any,
) -> Optional[str]:
    try:
        secret = env.TELEGRAM_WEBHOOK_SECRET
    except Exception:
        return None

    if secret is None:
        return None

    secret = str(secret).strip()

    if not secret:
        return None

    return secret


def verify_webhook_secret(
    request: Any,
    env: Any,
) -> None:
    expected_secret = get_webhook_secret(env)

    # Fail closed: never accept webhook requests without a configured secret.
    if expected_secret is None:
        raise UnauthorizedWebhookError(
            "Telegram webhook secret is not configured."
        )

    received_secret = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    )

    if received_secret != expected_secret:
        raise UnauthorizedWebhookError(
            "Invalid Telegram webhook secret."
        )


async def parse_webhook_update(
    request: Any,
) -> dict[str, Any]:
    try:
        update = await request.json()
    except Exception as exc:
        raise InvalidWebhookPayloadError(
            "Webhook body is not valid JSON."
        ) from exc

    if not isinstance(update, dict):
        raise InvalidWebhookPayloadError(
            "Telegram webhook update must be a JSON object."
        )

    return update


def detect_update_type(
    update: dict[str, Any],
) -> str:
    for update_type in TELEGRAM_UPDATE_TYPES:
        if update_type in update:
            return update_type

    return "unknown"


def build_webhook_response_body(
    update_type: str,
) -> str:
    return (
        "ArzanKadeh Webhook OK\n\n"
        f"Update type: {update_type}"
    )


__all__ = [
    "TELEGRAM_UPDATE_TYPES",
    "WebhookError",
    "UnauthorizedWebhookError",
    "InvalidWebhookPayloadError",
    "get_webhook_secret",
    "verify_webhook_secret",
    "parse_webhook_update",
    "detect_update_type",
    "build_webhook_response_body",
]
