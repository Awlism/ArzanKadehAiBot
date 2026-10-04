# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Review flow for Cloudflare Workers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from typing import Any, Optional

from worker.state import get_state, set_state
from worker.telegram import TelegramClient
from worker_backend.backend import backend


REVIEW_STATE = "review:waiting_text"


def _get_callback_telegram_id(
    callback_query: dict[str, Any],
) -> Optional[int]:
    user = callback_query.get("from")

    if not isinstance(user, dict):
        return None

    telegram_id = user.get("id")

    try:
        telegram_id = int(telegram_id)
    except (TypeError, ValueError):
        return None

    if telegram_id < 1:
        return None

    return telegram_id


async def _get_internal_user_id(
    telegram_id: int,
) -> Optional[int]:
    row = await backend.fetchone(
        """
        SELECT id
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_id,),
    )

    if row is None:
        return None

    try:
        user_id = int(row["id"])
    except (TypeError, ValueError):
        return None

    if user_id < 1:
        return None

    return user_id


def _get_callback_message(
    callback_query: dict[str, Any],
) -> Optional[dict[str, Any]]:
    message = callback_query.get("message")

    if not isinstance(message, dict):
        return None

    return message


def _get_chat_id(
    callback_query: dict[str, Any],
) -> Optional[int]:
    message = _get_callback_message(
        callback_query
    )

    if message is None:
        return None

    chat = message.get("chat")

    if not isinstance(chat, dict):
        return None

    chat_id = chat.get("id")

    try:
        return int(chat_id)
    except (TypeError, ValueError):
        return None


def _get_callback_query_id(
    callback_query: dict[str, Any],
) -> Optional[str]:
    callback_query_id = callback_query.get(
        "id"
    )

    if callback_query_id is None:
        return None

    value = str(
        callback_query_id
    ).strip()

    return value or None


def _parse_review_start(
    callback_data: str,
) -> Optional[tuple[str, int]]:
    parts = callback_data.split(":")

    if len(parts) != 3:
        return None

    if parts[0] != "reviewstart":
        return None

    target_type = parts[1]

    if target_type not in {
        "product",
        "seller",
    }:
        return None

    try:
        target_id = int(parts[2])
    except (TypeError, ValueError):
        return None

    if target_id < 1:
        return None

    return (
        target_type,
        target_id,
    )


def _parse_review_rate(
    callback_data: str,
) -> Optional[int]:
    parts = callback_data.split(":")

    if len(parts) != 2:
        return None

    if parts[0] != "reviewrate":
        return None

    try:
        rating = int(parts[1])
    except (TypeError, ValueError):
        return None

    if rating < 1 or rating > 5:
        return None

    return rating


async def _get_target(
    target_type: str,
    target_id: int,
) -> Optional[dict[str, Any]]:
    if target_type == "product":
        return await backend.fetchone(
            """
            SELECT
                id,
                name,
                seller_id
            FROM products
            WHERE id = ?
            LIMIT 1;
            """,
            (
                target_id,
            ),
        )

    if target_type == "seller":
        return await backend.fetchone(
            """
            SELECT
                id,
                name
            FROM sellers
            WHERE id = ?
            LIMIT 1;
            """,
            (
                target_id,
            ),
        )

    return None


async def _has_existing_review(
    user_id: int,
    target_type: str,
    target_id: int,
) -> bool:
    if target_type == "product":
        row = await backend.fetchone(
            """
            SELECT id
            FROM reviews
            WHERE user_id = ?
              AND product_id = ?
              AND seller_id IS NULL
            LIMIT 1;
            """,
            (
                user_id,
                target_id,
            ),
        )

        return row is not None

    if target_type == "seller":
        row = await backend.fetchone(
            """
            SELECT id
            FROM reviews
            WHERE user_id = ?
              AND seller_id = ?
              AND product_id IS NULL
            LIMIT 1;
            """,
            (
                user_id,
                target_id,
            ),
        )

        return row is not None

    return False


def _rating_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "⭐ 1",
                    "callback_data": "reviewrate:1",
                },
                {
                    "text": "⭐ 2",
                    "callback_data": "reviewrate:2",
                },
                {
                    "text": "⭐ 3",
                    "callback_data": "reviewrate:3",
                },
                {
                    "text": "⭐ 4",
                    "callback_data": "reviewrate:4",
                },
                {
                    "text": "⭐ 5",
                    "callback_data": "reviewrate:5",
                },
            ],
        ],
    }


async def handle_review_start(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
) -> bool:
    callback_data = callback_query.get(
        "data"
    )

    if not isinstance(
        callback_data,
        str,
    ):
        return False

    parsed = _parse_review_start(
        callback_data
    )

    if parsed is None:
        return False

    target_type, target_id = parsed

    telegram_id = _get_callback_telegram_id(
        callback_query
    )

    chat_id = _get_chat_id(
        callback_query
    )

    callback_query_id = _get_callback_query_id(
        callback_query
    )

    if (
        telegram_id is None
        or chat_id is None
    ):
        return False

    if callback_query_id is not None:
        await telegram.answer_callback_query(
            callback_query_id
        )

    user_id = await _get_internal_user_id(
        telegram_id
    )

    if user_id is None:
        await telegram.send_message(
            chat_id,
            "حساب کاربری پیدا نشد. اول /start رو بزن.",
        )
        return True

    target = await _get_target(
        target_type,
        target_id,
    )

    if target is None:
        await telegram.send_message(
            chat_id,
            "این مورد پیدا نشد.",
        )
        return True

    if await _has_existing_review(
        user_id,
        target_type,
        target_id,
    ):
        await telegram.send_message(
            chat_id,
            "قبلاً برای این مورد نظر ثبت کردی.",
        )
        return True

    await set_state(
        backend,
        user_id,
        "review:waiting_rating",
        {
            "target_type": target_type,
            "target_id": target_id,
            "target_name": str(
                target.get("name") or ""
            ),
        },
    )

    target_name = str(
        target.get("name") or "این مورد"
    )

    await telegram.send_message(
        chat_id,
        (
            f"برای «{target_name}» چه امتیازی می‌دی؟\n\n"
            "امتیازت رو از ۱ تا ۵ انتخاب کن ⭐"
        ),
        reply_markup=_rating_keyboard(),
    )

    return True


async def handle_review_rating(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
) -> bool:
    callback_data = callback_query.get(
        "data"
    )

    if not isinstance(
        callback_data,
        str,
    ):
        return False

    rating = _parse_review_rate(
        callback_data
    )

    if rating is None:
        return False

    telegram_id = _get_callback_telegram_id(
        callback_query
    )

    chat_id = _get_chat_id(
        callback_query
    )

    callback_query_id = _get_callback_query_id(
        callback_query
    )

    if (
        telegram_id is None
        or chat_id is None
    ):
        return False

    if callback_query_id is not None:
        await telegram.answer_callback_query(
            callback_query_id
        )

    user_id = await _get_internal_user_id(
        telegram_id
    )

    if user_id is None:
        await telegram.send_message(
            chat_id,
            "حساب کاربری پیدا نشد. اول /start رو بزن.",
        )
        return True

    state = await get_state(
        backend,
        user_id,
    )

    if state is None:
        await telegram.send_message(
            chat_id,
            "این مرحله منقضی شده. دوباره ثبت نظر رو شروع کن.",
        )
        return True

    if state.get("state") != "review:waiting_rating":
        await telegram.send_message(
            chat_id,
            "این مرحله دیگه فعال نیست. دوباره ثبت نظر رو شروع کن.",
        )
        return True

    data = state.get("data")

    if not isinstance(
        data,
        dict,
    ):
        await telegram.send_message(
            chat_id,
            "اطلاعات ثبت نظر ناقصه. دوباره شروع کن.",
        )
        return True

    target_type = data.get(
        "target_type"
    )

    target_id = data.get(
        "target_id"
    )

    if target_type not in {
        "product",
        "seller",
    }:
        await telegram.send_message(
            chat_id,
            "اطلاعات ثبت نظر نامعتبره. دوباره شروع کن.",
        )
        return True

    try:
        target_id = int(target_id)
    except (TypeError, ValueError):
        await telegram.send_message(
            chat_id,
            "اطلاعات ثبت نظر نامعتبره. دوباره شروع کن.",
        )
        return True

    if await _has_existing_review(
        user_id,
        target_type,
        target_id,
    ):
        await telegram.send_message(
            chat_id,
            "قبلاً برای این مورد نظر ثبت کردی.",
        )
        return True

    await set_state(
        backend,
        user_id,
        REVIEW_STATE,
        {
            "target_type": target_type,
            "target_id": target_id,
            "target_name": str(
                data.get("target_name") or ""
            ),
            "rating": rating,
        },
    )

    await telegram.send_message(
        chat_id,
        (
            f"امتیاز {rating} از ۵ ثبت شد ⭐\n\n"
            "حالا نظرت رو در یک پیام برام بنویس:"
        ),
    )

    return True


__all__ = [
    "REVIEW_STATE",
    "handle_review_rating",
    "handle_review_start",
]