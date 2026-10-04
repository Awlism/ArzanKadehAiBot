# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker support / user requests flow.

This module intentionally does not import aiogram, sqlite,
aiosqlite, or any legacy bot module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Optional

from worker.state import clear_state, get_state, set_state


STATE_NAME = "support"
SUPPORT_MESSAGE_MAX_LEN = 100

VALID_SUPPORT_AUDIENCES = {
    "buyer",
    "seller",
}

SUPPORT_TOPICS_BUYER = {
    "buy": "🛍️ مشکل خرید",
    "shop": "🏪 مشکل فروشگاه",
    "tech": "⚙️ مشکل فنی",
    "report": "🚨 گزارش مشکل",
    "other": "📝 سایر موارد ضروری",
}

SUPPORT_TOPICS_SELLER = {
    "shop_account": "🏪 مشکل حساب/فروشندگی",
    "ads": "📢 هماهنگی/پرداخت تبلیغات",
    "tech": "⚙️ مشکل فنی ارزانکده",
    "other": "📝 سایر موارد ضروری",
}


def _now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _html(value: Any) -> str:
    if value is None:
        return ""

    return escape(
        str(value),
        quote=False,
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


def _back_button(
    callback_data: str = "account",
) -> list[dict[str, Any]]:
    return [
        _button(
            "🔙 برگردیم",
            callback_data,
        )
    ]


def _message_context(
    callback_query: dict[str, Any],
) -> tuple[
    Optional[int],
    Optional[int],
]:
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    user = callback_query.get("from") or {}

    chat_id = chat.get("id")
    telegram_user_id = user.get("id")

    return (
        int(chat_id)
        if chat_id is not None
        else None,
        int(telegram_user_id)
        if telegram_user_id is not None
        else None,
    )


async def _ensure_user(
    db: Any,
    telegram_user_id: int,
    *,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> int:
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
            telegram_user_id,
            username,
            first_name,
            last_name,
            now,
            now,
        ),
    )

    row = await db.fetchone(
        """
        SELECT id
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_user_id,),
    )

    if row is None:
        raise RuntimeError(
            "Failed to resolve internal user id."
        )

    return int(row["id"])


async def _answer_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    *,
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

    chat_id = chat.get("id")
    message_id = message.get("message_id")

    if (
        chat_id is None
        or message_id is None
    ):
        return

    await telegram.edit_message_text(
        int(chat_id),
        int(message_id),
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def _get_request_topics(
    db: Any,
    user_id: int,
    request_type: str,
) -> list[dict[str, Any]]:
    rows = await db.fetchall(
        """
        SELECT
            id,
            type,
            topic,
            message,
            status,
            created_at
        FROM requests
        WHERE user_id = ?
          AND type = ?
        ORDER BY id DESC
        LIMIT 20;
        """,
        (
            user_id,
            request_type,
        ),
    )

    return rows


async def _has_open_request(
    db: Any,
    user_id: int,
    request_type: str,
    *,
    topic: Optional[str] = None,
) -> bool:
    open_statuses = (
        "PENDING",
        "OPEN",
        "IN_PROGRESS",
        "APPROVED",
    )

    if topic is None:
        placeholders = ", ".join(
            "?" for _ in open_statuses
        )

        row = await db.fetchone(
            f"""
            SELECT 1
            FROM requests
            WHERE user_id = ?
              AND type = ?
              AND status IN ({placeholders})
            LIMIT 1;
            """,
            (
                user_id,
                request_type,
                *open_statuses,
            ),
        )
    else:
        placeholders = ", ".join(
            "?" for _ in open_statuses
        )

        row = await db.fetchone(
            f"""
            SELECT 1
            FROM requests
            WHERE user_id = ?
              AND type = ?
              AND topic = ?
              AND status IN ({placeholders})
            LIMIT 1;
            """,
            (
                user_id,
                request_type,
                topic,
                *open_statuses,
            ),
        )

    return row is not None


def _status_label(
    status: Any,
) -> str:
    value = str(
        status or ""
    ).strip().upper()

    labels = {
        "PENDING": "⏳ در انتظار بررسی",
        "OPEN": "🟢 باز",
        "IN_PROGRESS": "🔄 در حال بررسی",
        "APPROVED": "✅ تأیید شده",
        "REJECTED": "❌ رد شده",
        "RESOLVED": "✅ حل شده",
        "CLOSED": "🔒 بسته شده",
        "CANCELLED": "🚫 لغو شده",
    }

    return labels.get(
        value,
        value or "نامشخص",
    )


async def handle_my_requests(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    chat_id, telegram_user_id = _message_context(
        callback_query
    )

    if telegram_user_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر شناسایی نشد.",
            show_alert=True,
        )
        return

    user = callback_query.get("from") or {}

    user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    await clear_state(
        db,
        user_id,
    )

    items = await _get_request_topics(
        db,
        user_id,
        "support",
    )

    if not items:
        text = (
            "📋 <b>درخواست‌های من</b>\n\n"
            "هنوز درخواست پشتیبانی ثبت نکردی."
        )
    else:
        lines = [
            "📋 <b>درخواست‌های من</b>",
            "",
        ]

        for item in items:
            topic = _html(
                item.get("topic")
            )

            status = _status_label(
                item.get("status")
            )

            created_at = str(
                item.get("created_at") or ""
            )

            date_text = (
                created_at[:10]
                if created_at
                else ""
            )

            if topic:
                lines.append(
                    f"• {topic}\n"
                    f"  وضعیت: {status}\n"
                    f"  تاریخ: {date_text}"
                )
            else:
                lines.append(
                    f"• درخواست پشتیبانی\n"
                    f"  وضعیت: {status}\n"
                    f"  تاریخ: {date_text}"
                )

        text = "\n\n".join(lines)

    await _edit_callback(
        telegram,
        callback_query,
        text,
        _keyboard(
            [
                _back_button("account"),
            ]
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_support_start(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    _, telegram_user_id = _message_context(
        callback_query
    )

    if telegram_user_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر شناسایی نشد.",
            show_alert=True,
        )
        return

    user = callback_query.get("from") or {}

    user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    await clear_state(
        db,
        user_id,
    )

    data = str(
        callback_query.get("data") or ""
    )

    if ":" not in data:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    audience = data.split(
        ":",
        1,
    )[1].strip().lower()

    if audience not in VALID_SUPPORT_AUDIENCES:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    topics = (
        SUPPORT_TOPICS_SELLER
        if audience == "seller"
        else SUPPORT_TOPICS_BUYER
    )

    rows = [
        [
            _button(
                label,
                f"supporttopic:{audience}:{code}",
            )
        ]
        for code, label in topics.items()
    ]

    rows.append(
        _back_button("account")
    )

    await _edit_callback(
        telegram,
        callback_query,
        "🛟 <b>موضوع مشکلت رو انتخاب کن:</b>",
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_support_topic(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(
        callback_query.get("data") or ""
    )

    parts = data.split(":")

    if len(parts) != 3:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    _, audience, code = parts

    audience = audience.strip().lower()
    code = code.strip().lower()

    if audience not in VALID_SUPPORT_AUDIENCES:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    topics = (
        SUPPORT_TOPICS_SELLER
        if audience == "seller"
        else SUPPORT_TOPICS_BUYER
    )

    if code not in topics:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ موضوع نامعتبر است.",
            show_alert=True,
        )
        return

    _, telegram_user_id = _message_context(
        callback_query
    )

    if telegram_user_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر شناسایی نشد.",
            show_alert=True,
        )
        return

    user = callback_query.get("from") or {}

    user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    topic = topics[code]

    if await _has_open_request(
        db,
        user_id,
        "support",
        topic=topic,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text=(
                "درخواست قبلی‌ات برای همین "
                "موضوع هنوز تعیین تکلیف نشده."
            ),
            show_alert=True,
        )
        return

    await set_state(
        db,
        user_id,
        STATE_NAME,
        {
            "audience": audience,
            "topic": topic,
        },
    )

    await _edit_callback(
        telegram,
        callback_query,
        (
            f"موضوع انتخابی: <b>{_html(topic)}</b>\n\n"
            "✍️ در یک جمله برامون بنویس "
            "چه مشکلی پیش اومده.\n"
            f"حداکثر {SUPPORT_MESSAGE_MAX_LEN} حرف 👇"
        ),
        None,
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_support_text(
    db: Any,
    telegram: Any,
    message: dict[str, Any],
) -> None:
    chat = message.get("chat") or {}
    from_user = message.get("from") or {}

    chat_id = chat.get("id")
    telegram_user_id = from_user.get("id")

    if telegram_user_id is None:
        return

    user_id = await _ensure_user(
        db,
        int(telegram_user_id),
        username=from_user.get("username"),
        first_name=from_user.get("first_name"),
        last_name=from_user.get("last_name"),
    )

    current_state = await get_state(
        db,
        user_id,
    )

    if (
        current_state is None
        or current_state.get("state")
        != STATE_NAME
    ):
        return

    data = current_state.get(
        "data"
    ) or {}

    topic = data.get("topic")

    if not topic:
        await clear_state(
            db,
            user_id,
        )

        if chat_id is not None:
            await telegram.send_message(
                int(chat_id),
                (
                    "⚠️ فرآیند پشتیبانی منقضی شده. "
                    "لطفاً دوباره تلاش کن."
                ),
            )

        return

    text = str(
        message.get("text") or ""
    ).strip()

    if not text:
        if chat_id is not None:
            await telegram.send_message(
                int(chat_id),
                "⚠️ لطفاً یک متن معتبر بفرست.",
            )

        return

    if len(text) > SUPPORT_MESSAGE_MAX_LEN:
        text = text[
            :SUPPORT_MESSAGE_MAX_LEN
        ]

    if await _has_open_request(
        db,
        user_id,
        "support",
        topic=topic,
    ):
        await clear_state(
            db,
            user_id,
        )

        if chat_id is not None:
            await telegram.send_message(
                int(chat_id),
                (
                    "⚠️ برای این موضوع یک "
                    "درخواست باز داری و فعلاً "
                    "درخواست جدید ثبت نمی‌شه."
                ),
            )

        return

    now = _now_iso()

    async with db.transaction(
        immediate=True
    ):
        result = await db.execute(
            """
            INSERT INTO requests (
                user_id,
                type,
                topic,
                message,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                user_id,
                "support",
                topic,
                text,
                "PENDING",
                now,
                now,
            ),
        )

        request_id = int(
            result.lastrowid
        )

        await db.execute(
            """
            INSERT INTO audit_log (
                actor_user_id,
                action,
                entity_type,
                entity_id,
                details,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                user_id,
                "support_request_created",
                "request",
                request_id,
                topic,
                now,
            ),
        )

        await clear_state(
            db,
            user_id,
        )

    if chat_id is not None:
        await telegram.send_message(
            int(chat_id),
            (
                "✅ درخواستت برای تیم پشتیبانی "
                "ارزانکده ارسال شد.\n\n"
                "تا وقتی بررسی نشده، درخواست "
                "جدید برای همین موضوع ثبت نمی‌شه."
            ),
        )


__all__ = [
    "STATE_NAME",
    "SUPPORT_MESSAGE_MAX_LEN",
    "VALID_SUPPORT_AUDIENCES",
    "SUPPORT_TOPICS_BUYER",
    "SUPPORT_TOPICS_SELLER",
    "handle_my_requests",
    "handle_support_start",
    "handle_support_topic",
    "handle_support_text",
]