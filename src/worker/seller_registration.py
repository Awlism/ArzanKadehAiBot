# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker seller registration flow.

This module intentionally does not import aiogram, sqlite,
aiosqlite, or the legacy bot package.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import re
from typing import Any

from worker.state import clear_state, get_state, set_state


STATE_NAME = "seller_registration"


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


def _parse_positive_id(
    callback_data: str,
    prefix: str,
) -> int | None:
    if not callback_data.startswith(
        prefix
    ):
        return None

    value = callback_data[
        len(prefix):
    ]

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed < 1:
        return None

    return parsed


def _normalize_username_url(
    value: Any,
    base_url: str,
    pattern: str,
) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    value = re.sub(
        pattern,
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = value.strip(
        "/"
    ).lstrip("@")

    if not value:
        return None

    if not re.fullmatch(
        r"[A-Za-z0-9._]+",
        value,
    ):
        return None

    return f"{base_url}{value}"


def _instagram_url(
    value: Any,
) -> str | None:
    return _normalize_username_url(
        value,
        "https://instagram.com/",
        r"^https?://(www\.)?instagram\.com/",
    )


def _telegram_url(
    value: Any,
) -> str | None:
    return _normalize_username_url(
        value,
        "https://t.me/",
        r"^https?://(www\.)?t\.me/",
    )


def _website_url(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    if "://" not in value:
        value = f"https://{value}"

    lowered = value.lower()

    if not (
        lowered.startswith("http://")
        or lowered.startswith("https://")
    ):
        return None

    if any(
        char in value
        for char in (
            "\n",
            "\r",
            "\t",
            "<",
            ">",
            '"',
            "'",
        )
    ):
        return None

    return value


def _back_keyboard(
    callback_data: str = "main",
) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🔙 بازگشت",
                    "callback_data": callback_data,
                }
            ]
        ]
    }


def _skip_keyboard(
    field: str,
) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "⏭ رد کردن",
                    "callback_data": (
                        f"registerskip:{field}"
                    ),
                }
            ],
            [
                {
                    "text": "🔙 بازگشت",
                    "callback_data": "main",
                }
            ],
        ]
    }


def _message_context(
    callback_query: dict[str, Any],
) -> tuple[int, int] | None:
    message = callback_query.get(
        "message"
    )

    if not isinstance(
        message,
        dict,
    ):
        return None

    chat = message.get(
        "chat"
    )

    if not isinstance(
        chat,
        dict,
    ):
        return None

    chat_id = chat.get(
        "id"
    )
    message_id = message.get(
        "message_id"
    )

    if (
        chat_id is None
        or message_id is None
    ):
        return None

    return (
        int(chat_id),
        int(message_id),
    )


def _callback_user(
    callback_query: dict[str, Any],
) -> dict[str, Any] | None:
    value = callback_query.get(
        "from"
    )

    if not isinstance(
        value,
        dict,
    ):
        return None

    return value


def _message_user(
    message: dict[str, Any],
) -> dict[str, Any] | None:
    value = message.get(
        "from"
    )

    if not isinstance(
        value,
        dict,
    ):
        return None

    return value


async def _ensure_user(
    db: Any,
    telegram_user: dict[str, Any],
) -> dict[str, Any]:
    telegram_id = telegram_user.get(
        "id"
    )

    try:
        telegram_id = int(
            telegram_id
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "Telegram user id is invalid."
        ) from exc

    if telegram_id < 1:
        raise ValueError(
            "Telegram user id is invalid."
        )

    username = telegram_user.get(
        "username"
    )
    first_name = telegram_user.get(
        "first_name"
    )
    last_name = telegram_user.get(
        "last_name"
    )

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
            "Failed to create or load user."
        )

    return user


async def _answer_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    text: str | None = None,
    show_alert: bool = False,
) -> None:
    callback_id = callback_query.get(
        "id"
    )

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
    reply_markup: dict[str, Any] | None = None,
) -> bool:
    context = _message_context(
        callback_query
    )

    if context is None:
        return False

    chat_id, message_id = context

    await telegram.edit_message_text(
        chat_id,
        message_id,
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )

    return True


async def _send(
    telegram: Any,
    message: dict[str, Any],
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    chat = message.get(
        "chat"
    )

    if not isinstance(
        chat,
        dict,
    ):
        return

    chat_id = chat.get(
        "id"
    )

    if chat_id is None:
        return

    await telegram.send_message(
        int(chat_id),
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


async def _load_state(
    db: Any,
    user_id: int,
) -> dict[str, Any] | None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS worker_states (
            user_id INTEGER PRIMARY KEY,
            state TEXT NOT NULL,
            data TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        );
        """
    )

    return await get_state(
        db,
        user_id,
    )


async def _set_registration_state(
    db: Any,
    user_id: int,
    step: str,
    data: dict[str, Any],
) -> None:
    await set_state(
        db,
        user_id,
        STATE_NAME,
        {
            "step": step,
            **data,
        },
    )


async def _finish_registration(
    db: Any,
    telegram: Any,
    message: dict[str, Any],
    user_id: int,
    data: dict[str, Any],
) -> None:
    name = str(
        data.get(
            "register_name"
        )
        or ""
    ).strip()

    if not name:
        await _send(
            telegram,
            message,
            "⚠️ نام فروشگاه وارد نشده است.",
        )
        return

    city_id = data.get(
        "register_city_id"
    )

    try:
        city_id = int(city_id)
    except (
        TypeError,
        ValueError,
    ):
        city_id = 0

    if city_id < 1:
        await _send(
            telegram,
            message,
            (
                "⚠️ شهر فروشگاه معتبر نیست. "
                "لطفاً دوباره ثبت فروشگاه را شروع کن."
            ),
        )
        return

    city = await db.fetchone(
        """
        SELECT id, name
        FROM cities
        WHERE id = ?
        LIMIT 1;
        """,
        (city_id,),
    )

    if city is None:
        await _send(
            telegram,
            message,
            (
                "⚠️ شهر انتخاب‌شده پیدا نشد. "
                "لطفاً دوباره تلاش کن."
            ),
        )
        return

    description = str(
        data.get(
            "register_description"
        )
        or ""
    ).strip()

    instagram = data.get(
        "register_instagram"
    )
    telegram_username = data.get(
        "register_telegram"
    )
    website = data.get(
        "register_website"
    )

    now = _now_iso()

    existing = await db.fetchone(
        """
        SELECT id
        FROM sellers
        WHERE (
            owner_user_id = ?
            OR created_by_user_id = ?
        )
        AND status != 'REJECTED'
        LIMIT 1;
        """,
        (
            user_id,
            user_id,
        ),
    )

    if existing is not None:
        await clear_state(
            db,
            user_id,
        )

        await _send(
            telegram,
            message,
            "⚠️ شما قبلاً یک فروشگاه ثبت کرده‌اید.",
        )
        return

    try:
        async with db.transaction(
            immediate=True,
        ) as tx:
            existing_tx = await tx.fetchone(
                """
                SELECT id
                FROM sellers
                WHERE (
                    owner_user_id = ?
                    OR created_by_user_id = ?
                )
                AND status != 'REJECTED'
                LIMIT 1;
                """,
                (
                    user_id,
                    user_id,
                ),
            )

            if existing_tx is not None:
                await clear_state(
                    db,
                    user_id,
                )

                await _send(
                    telegram,
                    message,
                    "⚠️ شما قبلاً یک فروشگاه ثبت کرده‌اید.",
                )
                return

            await tx.execute(
                """
                INSERT INTO sellers (
                    name,
                    description,
                    city_id,
                    instagram,
                    telegram,
                    website,
                    owner_user_id,
                    created_by_user_id,
                    status,
                    is_active,
                    rating,
                    review_count,
                    views,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    'UNCLAIMED',
                    1,
                    0,
                    0,
                    0,
                    ?,
                    ?
                );
                """,
                (
                    name,
                    description,
                    city_id,
                    instagram,
                    telegram_username,
                    website,
                    user_id,
                    user_id,
                    now,
                    now,
                ),
            )

            seller = await tx.fetchone(
                """
                SELECT id
                FROM sellers
                WHERE created_by_user_id = ?
                ORDER BY id DESC
                LIMIT 1;
                """,
                (user_id,),
            )

        if seller is None:
            raise RuntimeError(
                "Seller registration returned no seller id."
            )

    except Exception:
        await _send(
            telegram,
            message,
            (
                "⚠️ ثبت فروشگاه انجام نشد. "
                "لطفاً دوباره تلاش کن."
            ),
        )
        return

    seller_id = int(
        seller["id"]
    )

    await clear_state(
        db,
        user_id,
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
            "seller_created",
            "seller",
            seller_id,
            None,
            now,
        ),
    )

    await _send(
        telegram,
        message,
        (
            "🎉 <b>فروشگاهت با موفقیت ثبت شد!</b>\n\n"
            f"🏪 {_html(name)}\n"
            f"📍 {_html(city['name'])}\n\n"
            "حالا می‌تونی محصولاتت رو اضافه کنی "
            "و فروشگاهت رو مدیریت کنی."
        ),
    )


async def handle_register_seller_start(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    user = _callback_user(
        callback_query
    )

    if user is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    try:
        internal_user = await _ensure_user(
            db,
            user,
        )
    except (
        ValueError,
        RuntimeError,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    user_id = int(
        internal_user["id"]
    )

    await _load_state(
        db,
        user_id,
    )

    existing = await db.fetchone(
        """
        SELECT id
        FROM sellers
        WHERE (
            owner_user_id = ?
            OR created_by_user_id = ?
        )
        AND status != 'REJECTED'
        LIMIT 1;
        """,
        (
            user_id,
            user_id,
        ),
    )

    if existing is not None:
        await _edit_callback(
            telegram,
            callback_query,
            (
                "⚠️ شما قبلاً یک فروشگاه ثبت کرده‌اید."
            ),
            _back_keyboard(
                "main"
            ),
        )

        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    await clear_state(
        db,
        user_id,
    )

    await _set_registration_state(
        db,
        user_id,
        "name",
        {},
    )

    await _edit_callback(
        telegram,
        callback_query,
        (
            "🏪 <b>ثبت فروشگاه</b>\n\n"
            "اسم فروشگاهت رو بفرست:"
        ),
        _back_keyboard(
            "main"
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_register_seller_message(
    db: Any,
    telegram: Any,
    message: dict[str, Any],
) -> bool:
    user = _message_user(
        message
    )

    if user is None:
        return False

    try:
        internal_user = await _ensure_user(
            db,
            user,
        )
    except (
        ValueError,
        RuntimeError,
    ):
        return False

    user_id = int(
        internal_user["id"]
    )

    state = await _load_state(
        db,
        user_id,
    )

    if (
        state is None
        or state.get("state") != STATE_NAME
    ):
        return False

    step = str(
        state.get("data", {}).get(
            "step",
            "",
        )
    )

    text = str(
        message.get(
            "text",
            "",
        )
        or ""
    ).strip()

    if text == "/start":
        await clear_state(
            db,
            user_id,
        )
        return True

    if not text:
        await _send(
            telegram,
            message,
            "⚠️ لطفاً متن معتبر بفرست.",
        )
        return True

    data = dict(
        state.get(
            "data",
            {},
        )
    )
    data.pop(
        "step",
        None,
    )

    if step == "name":
        data["register_name"] = text

        await _set_registration_state(
            db,
            user_id,
            "description",
            data,
        )

        await _send(
            telegram,
            message,
            (
                "📝 توضیحات فروشگاه رو بفرست.\n"
                "اگر توضیح نداری بنویس: ندارد"
            ),
        )

        return True

    if step == "description":
        data["register_description"] = (
            ""
            if text == "ندارد"
            else text
        )

        await _set_registration_state(
            db,
            user_id,
            "city",
            data,
        )

        await _send_city_picker(
            db,
            telegram,
            message,
        )

        return True

    if step == "instagram":
        if _instagram_url(text) is None:
            await _send(
                telegram,
                message,
                "⚠️ آیدی یا لینک اینستاگرام معتبر نیست.",
            )
            return True

        data["register_instagram"] = text

        await _set_registration_state(
            db,
            user_id,
            "telegram",
            data,
        )

        await _send(
            telegram,
            message,
            "✈️ آیدی یا لینک تلگرام فروشگاه رو بفرست:",
            _skip_keyboard(
                "telegram"
            ),
        )

        return True

    if step == "telegram":
        if _telegram_url(text) is None:
            await _send(
                telegram,
                message,
                "⚠️ آیدی یا لینک تلگرام معتبر نیست.",
            )
            return True

        data["register_telegram"] = text

        await _set_registration_state(
            db,
            user_id,
            "website",
            data,
        )

        await _send(
            telegram,
            message,
            "🌐 لینک وب‌سایت فروشگاه رو بفرست:",
            _skip_keyboard(
                "website"
            ),
        )

        return True

    if step == "website":
        if _website_url(text) is None:
            await _send(
                telegram,
                message,
                "⚠️ لینک وب‌سایت معتبر نیست.",
            )
            return True

        data["register_website"] = text

        await _finish_registration(
            db,
            telegram,
            message,
            user_id,
            data,
        )

        return True

    return False


async def _send_city_picker(
    db: Any,
    telegram: Any,
    message: dict[str, Any],
) -> None:
    cities = await db.fetchall(
        """
        SELECT id, name
        FROM cities
        ORDER BY name;
        """
    )

    keyboard: list[
        list[dict[str, Any]]
    ] = []

    for city in cities:
        keyboard.append(
            [
                {
                    "text": (
                        f"📍 {_html(city['name'])}"
                    ),
                    "callback_data": (
                        f"registercity:{city['id']}"
                    ),
                }
            ]
        )

    await _send(
        telegram,
        message,
        "📍 شهر فروشگاه رو انتخاب کن:",
        {
            "inline_keyboard": keyboard
        },
    )


async def handle_register_city(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    city_id = _parse_positive_id(
        str(
            callback_query.get(
                "data",
                "",
            )
        ),
        "registercity:",
    )

    if city_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شهر نامعتبر است.",
            True,
        )
        return

    user = _callback_user(
        callback_query
    )

    if user is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    internal_user = await _ensure_user(
        db,
        user,
    )
    user_id = int(
        internal_user["id"]
    )

    city = await db.fetchone(
        """
        SELECT id, name
        FROM cities
        WHERE id = ?
        LIMIT 1;
        """,
        (city_id,),
    )

    if city is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شهر پیدا نشد.",
            True,
        )
        return

    state = await _load_state(
        db,
        user_id,
    )

    if (
        state is None
        or state.get("state") != STATE_NAME
        or state.get("data", {}).get(
            "step"
        ) != "city"
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ مرحله ثبت فروشگاه منقضی شده است.",
            True,
        )
        return

    data = dict(
        state.get(
            "data",
            {},
        )
    )
    data.pop(
        "step",
        None,
    )
    data["register_city_id"] = city_id

    await _set_registration_state(
        db,
        user_id,
        "instagram",
        data,
    )

    await _edit_callback(
        telegram,
        callback_query,
        "📸 آیدی یا لینک اینستاگرام فروشگاه رو بفرست:",
        _skip_keyboard(
            "instagram"
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_register_skip(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data_value = str(
        callback_query.get(
            "data",
            "",
        )
    )

    if not data_value.startswith(
        "registerskip:"
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ گزینه نامعتبر است.",
            True,
        )
        return

    field = data_value.split(
        ":",
        1,
    )[1]

    if field not in (
        "instagram",
        "telegram",
        "website",
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ گزینه نامعتبر است.",
            True,
        )
        return

    user = _callback_user(
        callback_query
    )

    if user is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    internal_user = await _ensure_user(
        db,
        user,
    )
    user_id = int(
        internal_user["id"]
    )

    state = await _load_state(
        db,
        user_id,
    )

    if (
        state is None
        or state.get("state") != STATE_NAME
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ مرحله ثبت فروشگاه منقضی شده است.",
            True,
        )
        return

    data = dict(
        state.get(
            "data",
            {},
        )
    )
    data.pop(
        "step",
        None,
    )

    if field == "instagram":
        data["register_instagram"] = None

        await _set_registration_state(
            db,
            user_id,
            "telegram",
            data,
        )

        await _edit_callback(
            telegram,
            callback_query,
            "✈️ آیدی یا لینک تلگرام فروشگاه رو بفرست:",
            _skip_keyboard(
                "telegram"
            ),
        )

    elif field == "telegram":
        data["register_telegram"] = None

        await _set_registration_state(
            db,
            user_id,
            "website",
            data,
        )

        await _edit_callback(
            telegram,
            callback_query,
            "🌐 لینک وب‌سایت فروشگاه رو بفرست:",
            _skip_keyboard(
                "website"
            ),
        )

    else:
        data["register_website"] = None

        await _finish_registration(
            db,
            telegram,
            callback_query.get(
                "message",
                {},
            ),
            user_id,
            data,
        )

    await _answer_callback(
        telegram,
        callback_query,
    )


__all__ = [
    "handle_register_seller_start",
    "handle_register_seller_message",
    "handle_register_city",
    "handle_register_skip",
]