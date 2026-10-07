# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Review flow for Cloudflare Workers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from worker.state import clear_state, get_state, set_state
from worker.telegram import TelegramClient
from worker_backend.backend import backend


REVIEW_STATE = "review:waiting_text"


def _now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _get_callback_telegram_id(
    callback_query: dict[str, Any],
) -> Optional[int]:
    user = callback_query.get("from")

    if not isinstance(
        user,
        dict,
    ):
        return None

    telegram_id = user.get("id")

    try:
        telegram_id = int(telegram_id)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if telegram_id < 1:
        return None

    return telegram_id


def _get_message_telegram_id(
    message: dict[str, Any],
) -> Optional[int]:
    user = message.get("from")

    if not isinstance(
        user,
        dict,
    ):
        return None

    telegram_id = user.get("id")

    try:
        telegram_id = int(telegram_id)
    except (
        TypeError,
        ValueError,
    ):
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
    ):
        return None

    if user_id < 1:
        return None

    return user_id


def _get_callback_message(
    callback_query: dict[str, Any],
) -> Optional[dict[str, Any]]:
    message = callback_query.get("message")

    if not isinstance(
        message,
        dict,
    ):
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

    if not isinstance(
        chat,
        dict,
    ):
        return None

    chat_id = chat.get("id")

    try:
        return int(chat_id)
    except (
        TypeError,
        ValueError,
    ):
        return None


def _get_message_chat_id(
    message: dict[str, Any],
) -> Optional[int]:
    chat = message.get("chat")

    if not isinstance(
        chat,
        dict,
    ):
        return None

    chat_id = chat.get("id")

    try:
        return int(chat_id)
    except (
        TypeError,
        ValueError,
    ):
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
    except (
        TypeError,
        ValueError,
    ):
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
    except (
        TypeError,
        ValueError,
    ):
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

    if callback_query_id is not None:
        await telegram.answer_callback_query(
            callback_query_id
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
    except (
        TypeError,
        ValueError,
    ):
        await telegram.send_message(
            chat_id,
            "اطلاعات ثبت نظر نامعتبره. دوباره شروع کن.",
        )
        return True

    if target_id < 1:
        await telegram.send_message(
            chat_id,
            "اطلاعات ثبت نظر نامعتبره. دوباره شروع کن.",
        )
        return True

    target = await _get_target(
        target_type,
        target_id,
    )

    if target is None:
        await clear_state(
            backend,
            user_id,
        )
        await telegram.send_message(
            chat_id,
            "این مورد دیگه پیدا نشد. دوباره ثبت نظر رو شروع کن.",
        )
        return True

    if await _has_existing_review(
        user_id,
        target_type,
        target_id,
    ):
        await clear_state(
            backend,
            user_id,
        )
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
                data.get("target_name")
                or target.get("name")
                or ""
            ),
            "rating": rating,
        },
    )

    if callback_query_id is not None:
        await telegram.answer_callback_query(
            callback_query_id
        )

    await telegram.send_message(
        chat_id,
        (
            f"امتیاز {rating} از ۵ ثبت شد ⭐\n\n"
            "حالا نظرت رو در یک پیام برام بنویس:"
        ),
    )

    return True


async def handle_review_text(
    message: dict[str, Any],
    telegram: TelegramClient,
) -> bool:
    """
    Complete the review after the user sends the review text.
    """

    telegram_id = _get_message_telegram_id(
        message
    )

    chat_id = _get_message_chat_id(
        message
    )

    if (
        telegram_id is None
        or chat_id is None
    ):
        return False

    text = message.get(
        "text"
    )

    if not isinstance(
        text,
        str,
    ):
        await telegram.send_message(
            chat_id,
            "لطفاً متن نظرت رو به صورت پیام متنی بفرست.",
        )
        return True

    review_text = text.strip()

    if not review_text:
        await telegram.send_message(
            chat_id,
            "متن نظر نمی‌تونه خالی باشه. دوباره بنویس.",
        )
        return True

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

    if state.get("state") != REVIEW_STATE:
        return False

    data = state.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):
        await clear_state(
            backend,
            user_id,
        )
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

    rating = data.get(
        "rating"
    )

    if target_type not in {
        "product",
        "seller",
    }:
        await clear_state(
            backend,
            user_id,
        )
        await telegram.send_message(
            chat_id,
            "اطلاعات ثبت نظر نامعتبره. دوباره شروع کن.",
        )
        return True

    try:
        target_id = int(target_id)
        rating = int(rating)
    except (
        TypeError,
        ValueError,
    ):
        await clear_state(
            backend,
            user_id,
        )
        await telegram.send_message(
            chat_id,
            "اطلاعات ثبت نظر نامعتبره. دوباره شروع کن.",
        )
        return True

    if (
        target_id < 1
        or rating < 1
        or rating > 5
    ):
        await clear_state(
            backend,
            user_id,
        )
        await telegram.send_message(
            chat_id,
            "اطلاعات ثبت نظر نامعتبره. دوباره شروع کن.",
        )
        return True

    target = await _get_target(
        target_type,
        target_id,
    )

    if target is None:
        await clear_state(
            backend,
            user_id,
        )
        await telegram.send_message(
            chat_id,
            "این مورد دیگه پیدا نشد. دوباره ثبت نظر رو شروع کن.",
        )
        return True

    if await _has_existing_review(
        user_id,
        target_type,
        target_id,
    ):
        await clear_state(
            backend,
            user_id,
        )
        await telegram.send_message(
            chat_id,
            "قبلاً برای این مورد نظر ثبت کردی.",
        )
        return True

    now = _now_iso()

    if target_type == "product":
        insert_params = (
            user_id,
            None,
            target_id,
            rating,
            review_text,
            now,
        )

        update_sql = """
            UPDATE products
            SET rating = COALESCE(
                    (
                        SELECT AVG(rating)
                        FROM reviews
                        WHERE product_id = ?
                          AND seller_id IS NULL
                    ),
                    0
                ),
                review_count = (
                    SELECT COUNT(*)
                    FROM reviews
                    WHERE product_id = ?
                      AND seller_id IS NULL
                ),
                updated_at = ?
            WHERE id = ?;
        """

        update_params = (
            target_id,
            target_id,
            now,
            target_id,
        )

        event_entity_type = "product"

    else:
        insert_params = (
            user_id,
            target_id,
            None,
            rating,
            review_text,
            now,
        )

        update_sql = """
            UPDATE sellers
            SET rating = COALESCE(
                    (
                        SELECT AVG(rating)
                        FROM reviews
                        WHERE seller_id = ?
                          AND product_id IS NULL
                    ),
                    0
                ),
                review_count = (
                    SELECT COUNT(*)
                    FROM reviews
                    WHERE seller_id = ?
                      AND product_id IS NULL
                ),
                updated_at = ?
            WHERE id = ?;
        """

        update_params = (
            target_id,
            target_id,
            now,
            target_id,
        )

        event_entity_type = "seller"

    try:
        async with backend.transaction(
            immediate=True
        ) as transaction:
            await transaction.execute(
                """
                INSERT INTO reviews (
                    user_id,
                    seller_id,
                    product_id,
                    rating,
                    text,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                insert_params,
            )

            await transaction.execute(
                update_sql,
                update_params,
            )

            await transaction.execute(
                """
                INSERT INTO events (
                    user_id,
                    event_type,
                    entity_type,
                    entity_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    user_id,
                    "review",
                    event_entity_type,
                    target_id,
                    now,
                ),
            )

            await transaction.execute(
                """
                DELETE FROM worker_states
                WHERE user_id = ?;
                """,
                (
                    user_id,
                ),
            )

    except Exception as exc:
        message_text = str(exc).lower()

        if (
            "unique" in message_text
            or "constraint" in message_text
        ):
            await clear_state(
                backend,
                user_id,
            )
            await telegram.send_message(
                chat_id,
                "قبلاً برای این مورد نظر ثبت کردی.",
            )
            return True

        raise

    target_name = str(
        target.get("name")
        or data.get("target_name")
        or "این مورد"
    )

    await telegram.send_message(
        chat_id,
        (
            "✅ نظرت با موفقیت ثبت شد.\n\n"
            f"⭐ امتیاز: {rating} از ۵\n"
            f"📌 {target_name}\n\n"
            "مرسی که تجربه‌ات رو با بقیه به اشتراک گذاشتی ❤️"
        ),
    )

    return True


__all__ = [
    "REVIEW_STATE",
    "handle_review_rating",
    "handle_review_start",
    "handle_review_text",
]