# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker-side seller referral handlers.

This module intentionally does not import aiogram, sqlite, or aiosqlite.
"""

from __future__ import annotations

from html import escape
from typing import Any, Optional
from urllib.parse import quote


BOT_USERNAME = "ArzanKadehAiBot"
REFERRAL_SOURCE = "deep_link"

REFERRAL_MILESTONES = (
    (5, "⭐ امتیاز"),
    (20, "🔥 Boost رایگان"),
    (50, "⭐ Featured چندروزه"),
    (100, "🏆 فروشنده ویژه"),
)


def _html(value: Any) -> str:
    if value is None:
        return ""

    return escape(
        str(value),
        quote=False,
    )


def _parse_id(value: Any) -> Optional[int]:
    try:
        result = int(str(value).strip())
    except (TypeError, ValueError):
        return None

    if result < 1:
        return None

    return result


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _button(
    text: str,
    callback_data: str,
) -> dict[str, Any]:
    return {
        "text": text,
        "callback_data": callback_data,
    }


def _keyboard(
    rows: list[list[dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "inline_keyboard": rows,
    }


async def _answer_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    text: Optional[str] = None,
    show_alert: bool = False,
) -> None:
    callback_id = callback_query.get("id")

    if not callback_id:
        return

    await telegram.answer_callback_query(
        str(callback_id),
        text=text,
        show_alert=show_alert,
    )


async def _edit_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    text: str,
    keyboard: Optional[dict[str, Any]] = None,
) -> None:
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}

    chat_id = _parse_id(chat.get("id"))
    message_id = _parse_id(message.get("message_id"))

    if chat_id is None or message_id is None:
        return

    await telegram.edit_message_text(
        chat_id,
        message_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def _ensure_user(
    db: Any,
    telegram_user: dict[str, Any],
) -> dict[str, Any]:
    telegram_id = _parse_id(
        telegram_user.get("id")
    )

    if telegram_id is None:
        raise ValueError(
            "Invalid Telegram user id."
        )

    username = telegram_user.get("username")
    first_name = telegram_user.get("first_name")
    last_name = telegram_user.get("last_name")

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

    await db.execute(
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

    user = await db.fetchone(
        """
        SELECT *
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_id,),
    )

    if user is None:
        raise RuntimeError(
            "Failed to resolve user."
        )

    return user


async def get_sellers_owned_by_user(
    db: Any,
    user_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT *
        FROM sellers
        WHERE owner_user_id = ?
           OR created_by_user_id = ?
        ORDER BY id ASC;
        """,
        (
            user_id,
            user_id,
        ),
    )


async def _get_owned_seller(
    db: Any,
    user_id: int,
    seller_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT *
        FROM sellers
        WHERE id = ?
          AND (
              owner_user_id = ?
              OR created_by_user_id = ?
          )
        LIMIT 1;
        """,
        (
            seller_id,
            user_id,
            user_id,
        ),
    )


async def get_referral_count(
    db: Any,
    seller_id: int,
) -> int:
    row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM referrals
        WHERE seller_id = ?;
        """,
        (seller_id,),
    )

    if not row:
        return 0

    try:
        return int(row["c"] or 0)
    except (TypeError, ValueError):
        return 0


def build_referral_link(
    bot_username: str,
    seller_id: int,
) -> str:
    username = str(
        bot_username or BOT_USERNAME
    ).strip().lstrip("@")

    return (
        f"https://t.me/{username}"
        f"?start=shop_{seller_id}"
    )


def next_referral_milestone(
    count: int,
) -> Optional[tuple[int, str]]:
    for milestone, reward in REFERRAL_MILESTONES:
        if count < milestone:
            return milestone, reward

    return None


async def referral_stats_text(
    db: Any,
    bot_username: str,
    seller_id: int,
    seller_name: str,
) -> str:
    count = await get_referral_count(
        db,
        seller_id,
    )

    link = build_referral_link(
        bot_username,
        seller_id,
    )

    milestone = next_referral_milestone(
        count
    )

    lines = [
        "🎁 <b>معرفی فروشگاه</b>",
        "",
        f"🏪 فروشگاه: <b>{_html(seller_name)}</b>",
        f"👥 معرفی‌های موفق: <b>{count}</b>",
        "",
        "🔗 <b>لینک اختصاصی فروشگاه:</b>",
        f"<code>{_html(link)}</code>",
    ]

    if milestone is not None:
        target, reward = milestone
        remaining = target - count

        lines.extend(
            [
                "",
                (
                    f"🎯 تا پاداش بعدی "
                    f"<b>{target}</b> معرفی فاصله داری."
                ),
                f"🔥 {remaining} معرفی دیگه → {reward}",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "🏆 همه‌ی مراحل معرفی رو رد کردی!",
            ]
        )

    return "\n".join(lines)


async def record_referral_if_new(
    db: Any,
    seller_id: int,
    referred_user_id: int,
) -> bool:
    seller = await db.fetchone(
        """
        SELECT id, owner_user_id, created_by_user_id
        FROM sellers
        WHERE id = ?
        LIMIT 1;
        """,
        (seller_id,),
    )

    if seller is None:
        return False

    owner_user_id = _parse_id(
        seller.get("owner_user_id")
    )
    created_by_user_id = _parse_id(
        seller.get("created_by_user_id")
    )

    if (
        owner_user_id == referred_user_id
        or created_by_user_id == referred_user_id
    ):
        return False

    existing = await db.fetchone(
        """
        SELECT id
        FROM referrals
        WHERE referred_user_id = ?
        LIMIT 1;
        """,
        (referred_user_id,),
    )

    if existing is not None:
        return False

    try:
        await db.execute(
            """
            INSERT INTO referrals (
                seller_id,
                referred_user_id,
                source,
                created_at
            )
            VALUES (?, ?, ?, ?);
            """,
            (
                seller_id,
                referred_user_id,
                REFERRAL_SOURCE,
                _now_iso(),
            ),
        )
    except Exception as exc:
        message = str(exc).lower()

        if (
            "unique" in message
            or "constraint" in message
        ):
            return False

        raise

    return True


async def handle_referral_list(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    callback_user = (
        callback_query.get("from")
        or {}
    )

    try:
        user = await _ensure_user(
            db,
            callback_user,
        )
    except (ValueError, RuntimeError):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    sellers = await get_sellers_owned_by_user(
        db,
        int(user["id"]),
    )

    if not sellers:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ هنوز فروشگاهی برای معرفی نداری.",
            True,
        )
        return

    if len(sellers) == 1:
        seller = sellers[0]

        seller_id = _parse_id(
            seller.get("id")
        )

        if seller_id is None:
            await _answer_callback(
                telegram,
                callback_query,
                "⚠️ شناسه فروشگاه نامعتبر است.",
                True,
            )
            return

        text = await referral_stats_text(
            db,
            BOT_USERNAME,
            seller_id,
            str(
                seller.get("name")
                or "فروشگاه"
            ),
        )

        await _edit_callback(
            telegram,
            callback_query,
            text,
            _keyboard(
                [
                    [
                        _button(
                            "🔙 بازگشت",
                            "account",
                        )
                    ]
                ]
            ),
        )

        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    rows: list[list[dict[str, Any]]] = []

    for seller in sellers:
        seller_id = _parse_id(
            seller.get("id")
        )

        if seller_id is None:
            continue

        rows.append(
            [
                _button(
                    (
                        "🏪 "
                        f"{_html(seller.get('name') or 'فروشگاه')}"
                    ),
                    f"refstats:{seller_id}",
                )
            ]
        )

    rows.append(
        [
            _button(
                "🔙 بازگشت",
                "account",
            )
        ]
    )

    await _edit_callback(
        telegram,
        callback_query,
        "🎁 کدوم فروشگاهت رو می‌خوای برای معرفی ببینی؟",
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_referral_stats(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(
        callback_query.get("data", "")
    )

    if not data.startswith(
        "refstats:"
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ گزینه نامعتبر است.",
            True,
        )
        return

    seller_id = _parse_id(
        data.split(
            ":",
            1,
        )[1]
    )

    if seller_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شناسه نامعتبر است.",
            True,
        )
        return

    callback_user = (
        callback_query.get("from")
        or {}
    )

    try:
        user = await _ensure_user(
            db,
            callback_user,
        )
    except (ValueError, RuntimeError):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    seller = await _get_owned_seller(
        db,
        int(user["id"]),
        seller_id,
    )

    if seller is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شما به این فروشگاه دسترسی ندارید.",
            True,
        )
        return

    text = await referral_stats_text(
        db,
        BOT_USERNAME,
        seller_id,
        str(
            seller.get("name")
            or "فروشگاه"
        ),
    )

    await _edit_callback(
        telegram,
        callback_query,
        text,
        _keyboard(
            [
                [
                    _button(
                        "🔙 بازگشت به فروشگاه‌ها",
                        "reflist",
                    )
                ],
                [
                    _button(
                        "🏠 حساب کاربری",
                        "account",
                    )
                ],
            ]
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


__all__ = [
    "BOT_USERNAME",
    "REFERRAL_SOURCE",
    "REFERRAL_MILESTONES",
    "build_referral_link",
    "get_referral_count",
    "next_referral_milestone",
    "referral_stats_text",
    "record_referral_if_new",
    "get_sellers_owned_by_user",
    "handle_referral_list",
    "handle_referral_stats",
]