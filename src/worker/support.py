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

    try:
        chat_id = int(chat_id)
    except (
        TypeError,
        ValueError,
    ):
        chat_id = None

    try:
        telegram_user_id = int(telegram_user_id)
    except (
        TypeError,
        ValueError,
    ):
        telegram_user_id = None

    return (
        chat_id,
        telegram_user_id,
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


async def _send_admin_support_request(
    db: Any,
    telegram: Any,
    env: Any,
    request_id: int,
    user_id: int,
    topic: str,
    message_text: str,
) -> None:
    """
    Notify the configured admin about a new support request.

    ADMIN_CHAT_ID is read from the Worker environment.
    No token or secret is handled here.
    """

    admin_chat_id = getattr(
        env,
        "ADMIN_CHAT_ID",
        None,
    )

    if admin_chat_id is None:
        return

    try:
        admin_chat_id = int(
            admin_chat_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return

    if admin_chat_id < 1:
        return

    user = await db.fetchone(
        """
        SELECT
            telegram_id,
            username,
            first_name,
            last_name
        FROM users
        WHERE id = ?
        LIMIT 1;
        """,
        (user_id,),
    )

    if user is None:
        user_label = f"کاربر داخلی #{user_id}"
    else:
        first_name = str(
            user.get("first_name") or ""
        ).strip()

        last_name = str(
            user.get("last_name") or ""
        ).strip()

        username = str(
            user.get("username") or ""
        ).strip()

        full_name = " ".join(
            part
            for part in (
                first_name,
                last_name,
            )
            if part
        )

        if username:
            user_label = (
                f"{full_name} "
                f"(@{username})"
                if full_name
                else f"@{username}"
            )
        elif full_name:
            user_label = full_name
        else:
            user_label = (
                f"کاربر داخلی #{user_id}"
            )

    keyboard = _keyboard(
        [
            [
                _button(
                    "✅ تأیید",
                    f"adminreq:approve:{request_id}",
                ),
                _button(
                    "❌ رد",
                    f"adminreq:reject:{request_id}",
                ),
            ],
        ]
    )

    text = (
        "🛟 <b>درخواست پشتیبانی جدید</b>\n\n"
        f"<b>موضوع:</b> {_html(topic)}\n"
        f"<b>پیام:</b> {_html(message_text)}\n\n"
        f"<b>کاربر:</b> {_html(user_label)}\n"
        f"<b>شناسه داخلی:</b> #{user_id}\n"
        f"<b>درخواست:</b> #{request_id}"
    )

    try:
        await telegram.send_message(
            admin_chat_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except Exception:
        # Failure to notify the admin must not roll back
        # an already-created support request.
        return


async def _get_request_topics(
    db: Any,
    user_id: int,
    request_type: str,
) -> list[dict[str, Any]]:
    rows = await db.fetchall(
        """
        SELECT
            id,
            request_type,
            topic,
            message,
            status,
            created_at
        FROM requests
        WHERE user_id = ?
          AND request_type = ?
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

    placeholders = ", ".join(
        "?"
        for _ in open_statuses
    )

    if topic is None:
        row = await db.fetchone(
            f"""
            SELECT 1
            FROM requests
            WHERE user_id = ?
              AND request_type = ?
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
        row = await db.fetchone(
            f"""
            SELECT 1
            FROM requests
            WHERE user_id = ?
              AND request_type = ?
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
                    "• درخواست پشتیبانی\n"
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
    env: Any,
) -> None:
    chat = message.get("chat") or {}
    from_user = message.get("from") or {}

    chat_id = chat.get("id")
    telegram_user_id = from_user.get("id")

    if telegram_user_id is None:
        return

    try:
        telegram_user_id = int(
            telegram_user_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return

    user_id = await _ensure_user(
        db,
        telegram_user_id,
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
    ) as tx:
        await tx.execute(
            """
            INSERT INTO requests (
                user_id,
                request_type,
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

    request_row = await db.fetchone(
        """
        SELECT id
        FROM requests
        WHERE user_id = ?
          AND request_type = 'support'
          AND topic = ?
          AND message = ?
          AND status = 'PENDING'
          AND created_at = ?
        ORDER BY id DESC
        LIMIT 1;
        """,
        (
            user_id,
            topic,
            text,
            now,
        ),
    )

    request_id = (
        int(request_row["id"])
        if request_row is not None
        else None
    )

    if request_id is None:
        await clear_state(
            db,
            user_id,
        )

        if chat_id is not None:
            await telegram.send_message(
                int(chat_id),
                (
                    "⚠️ درخواست ثبت نشد. "
                    "لطفاً دوباره تلاش کن."
                ),
            )

        return

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

    # First notify the admin so the request immediately appears
    # with approve/reject controls.
    await _send_admin_support_request(
        db,
        telegram,
        env,
        request_id,
        user_id,
        topic,
        text,
    )

    if chat_id is not None:
        await telegram.send_message(
            int(chat_id),
            (
                "✅ درخواستت برای تیم پشتیبانی "
                "ارزانکده ارسال شد.\n\n"
                "تا وقتی که بررسی نشده، گفت‌وگوی مستقیم "
                "باز نمی‌شود؛ بعد از تأیید، ادامه‌ی "
                "گفت‌وگو فعال می‌شود."
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