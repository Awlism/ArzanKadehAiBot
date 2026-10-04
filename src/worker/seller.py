# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker-side seller browsing handler.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from html import escape
import re
from typing import Any


PAGE_SIZE_LIST = 8


def _html(value: Any) -> str:
    if value is None:
        return ""

    return escape(
        str(value),
        quote=False,
    )


def _parse_seller_id(
    callback_data: str,
) -> int | None:
    if ":" not in callback_data:
        return None

    _, value = callback_data.split(
        ":",
        1,
    )

    try:
        seller_id = int(value)
    except (TypeError, ValueError):
        return None

    if seller_id < 1:
        return None

    return seller_id


def _parse_sellers_page(
    callback_data: str,
) -> int | None:
    if not callback_data.startswith(
        "sellers:"
    ):
        return None

    _, value = callback_data.split(
        ":",
        1,
    )

    try:
        page = int(value)
    except (TypeError, ValueError):
        return None

    if page < 0:
        return None

    return page


def _status_badge(
    status: Any,
) -> str:
    value = str(
        status or ""
    ).upper()

    return {
        "APPROVED": "🟢",
        "CLAIMED": "🟢",
        "PENDING": "🟡",
        "REJECTED": "🔴",
        "UNCLAIMED": "⚪",
    }.get(
        value,
        "⚪",
    )


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

    value = value.strip("/").lstrip("@")

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


def _whatsapp_url(
    value: Any,
) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    if value.startswith(
        ("http://", "https://")
    ):
        return value

    digits = re.sub(
        r"[^0-9+]",
        "",
        value,
    )

    if not digits:
        return None

    return (
        "https://wa.me/"
        + digits.lstrip("+")
    )


def _back_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🔙 بازگشت",
                    "callback_data": "sellers:0",
                }
            ]
        ]
    }


async def _ensure_user(
    db: Any,
    telegram_user: dict[str, Any],
) -> dict[str, Any]:
    telegram_id = telegram_user.get("id")

    try:
        telegram_id = int(telegram_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Telegram user id is invalid."
        ) from exc

    if telegram_id < 1:
        raise ValueError(
            "Telegram user id is invalid."
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

    existing = await db.fetchone(
        """
        SELECT *
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_id,),
    )

    now = _now_iso()

    if existing is None:
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
    else:
        await db.execute(
            """
            UPDATE users
            SET username = ?,
                first_name = ?,
                last_name = ?,
                updated_at = ?
            WHERE telegram_id = ?;
            """,
            (
                username,
                first_name,
                last_name,
                now,
                telegram_id,
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


async def _get_seller(
    db: Any,
    seller_id: int,
) -> dict[str, Any] | None:
    return await db.fetchone(
        """
        SELECT
            s.*,
            c.name AS city_name
        FROM sellers s
        LEFT JOIN cities c
            ON c.id = s.city_id
        WHERE s.id = ?;
        """,
        (seller_id,),
    )


async def _seller_keyboard(
    db: Any,
    seller: dict[str, Any],
    user_id: int,
) -> dict[str, Any]:
    seller_id = int(
        seller["id"]
    )

    is_active = (
        bool(seller["is_active"])
        if seller.get("is_active") is not None
        else True
    )

    keyboard: list[list[dict[str, Any]]] = []

    is_favorite = await _is_seller_favorite(
        db,
        user_id,
        seller_id,
    )

    favorite_text = (
        "💔 حذف از علاقه‌مندی‌ها"
        if is_favorite
        else "❤️ ذخیره فروشگاه"
    )

    favorite_callback = (
        f"sunfav:{seller_id}"
        if is_favorite
        else f"sfav:{seller_id}"
    )

    if is_active:
        instagram = _instagram_url(
            seller.get("instagram")
        )

        telegram = _telegram_url(
            seller.get("telegram")
        )

        whatsapp = _whatsapp_url(
            seller.get("whatsapp")
        )

        website = _website_url(
            seller.get("website")
        )

        support_telegram = _telegram_url(
            seller.get("telegram_support")
        )

        if instagram:
            keyboard.append(
                [
                    {
                        "text": "📸 اینستاگرام",
                        "url": instagram,
                    }
                ]
            )

        if telegram:
            keyboard.append(
                [
                    {
                        "text": "✈️ تلگرام",
                        "url": telegram,
                    }
                ]
            )

        if whatsapp:
            keyboard.append(
                [
                    {
                        "text": "🟢 واتساپ",
                        "url": whatsapp,
                    }
                ]
            )

        if website:
            keyboard.append(
                [
                    {
                        "text": "🔗 وبسایت",
                        "url": website,
                    }
                ]
            )

        if support_telegram:
            keyboard.append(
                [
                    {
                        "text": "💬 پشتیبانی فروشگاه",
                        "url": support_telegram,
                    }
                ]
            )

    keyboard.append(
        [
            {
                "text": favorite_text,
                "callback_data": favorite_callback,
            }
        ]
    )

    keyboard.append(
        [
            {
                "text": "⭐ ثبت نظر",
                "callback_data": (
                    f"reviewstart:seller:{seller_id}"
                ),
            }
        ]
    )

    keyboard.append(
        [
            {
                "text": "🔙 بازگشت",
                "callback_data": "sellers:0",
            }
        ]
    )

    return {
        "inline_keyboard": keyboard
    }


async def _is_seller_favorite(
    db: Any,
    user_id: int,
    seller_id: int,
) -> bool:
    row = await db.fetchone(
        """
        SELECT 1
        FROM seller_favorites
        WHERE user_id = ?
          AND seller_id = ?
        LIMIT 1;
        """,
        (
            user_id,
            seller_id,
        ),
    )

    return row is not None


async def handle_sellers_list(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Render the paginated public seller list.

    Callback format:
        sellers:<page>
    """

    callback_data = str(
        callback_query.get(
            "data",
            "",
        )
    )

    page = _parse_sellers_page(
        callback_data
    )

    if page is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ صفحه نامعتبر است.",
            True,
        )
        return

    callback_user = callback_query.get(
        "from"
    )

    if not isinstance(
        callback_user,
        dict,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    try:
        await _ensure_user(
            db,
            callback_user,
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

    sellers = await db.fetchall(
        """
        SELECT
            *
        FROM sellers
        ORDER BY
            rating DESC,
            views DESC,
            id DESC;
        """
    )

    message = callback_query.get(
        "message"
    )

    if not isinstance(
        message,
        dict,
    ):
        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    chat = message.get(
        "chat"
    )

    if not isinstance(
        chat,
        dict,
    ):
        await _answer_callback(
            telegram,
            callback_query,
        )
        return

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
        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    if not sellers:
        await telegram.edit_message_text(
            chat_id,
            int(message_id),
            "🏪 <b>فروشگاه‌ها</b>\n\n"
            "فعلاً فروشگاهی ثبت نشده است.",
            reply_markup=_back_keyboard(),
            parse_mode="HTML",
        )

        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    total = len(sellers)
    total_pages = (
        total + PAGE_SIZE_LIST - 1
    ) // PAGE_SIZE_LIST

    if page >= total_pages:
        page = total_pages - 1

    offset = (
        page * PAGE_SIZE_LIST
    )

    page_rows = sellers[
        offset:offset + PAGE_SIZE_LIST
    ]

    keyboard: list[
        list[dict[str, Any]]
    ] = []

    for seller in page_rows:
        seller_id = int(
            seller["id"]
        )

        status = str(
            seller.get("status") or ""
        ).upper()

        badge = _status_badge(
            status
        )

        seller_name = (
            seller.get("name")
            or "فروشگاه بدون نام"
        )

        keyboard.append(
            [
                {
                    "text": (
                        f"🏪 {badge} "
                        f"{_html(seller_name)}"
                    ),
                    "callback_data": (
                        f"seller:{seller_id}"
                    ),
                }
            ]
        )

    pagination: list[
        dict[str, Any]
    ] = []

    if page > 0:
        pagination.append(
            {
                "text": "◀️ قبلی",
                "callback_data": (
                    f"sellers:{page - 1}"
                ),
            }
        )

    if page + 1 < total_pages:
        pagination.append(
            {
                "text": "بعدی ▶️",
                "callback_data": (
                    f"sellers:{page + 1}"
                ),
            }
        )

    if pagination:
        keyboard.append(
            pagination
        )

    if page > 0:
        keyboard.append(
            [
                {
                    "text": "🔙 صفحه اول",
                    "callback_data": "sellers:0",
                }
            ]
        )

    start_number = offset + 1
    end_number = offset + len(
        page_rows
    )

    text = (
        "🏪 <b>فروشگاه‌ها</b>\n\n"
        f"نمایش {start_number} تا {end_number} "
        f"از {total} فروشگاه\n"
        f"صفحه {page + 1} از {total_pages}"
    )

    await telegram.edit_message_text(
        chat_id,
        int(message_id),
        text,
        reply_markup={
            "inline_keyboard": keyboard
        },
        parse_mode="HTML",
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_seller_favorite_add(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    callback_data = str(callback_query.get("data", ""))
    seller_id = _parse_seller_id(callback_data)

    if seller_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شناسه فروشگاه نامعتبر است.",
            True,
        )
        return

    callback_user = callback_query.get("from")

    if not isinstance(callback_user, dict):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

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

    seller = await _get_seller(
        db,
        seller_id,
    )

    if seller is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ این فروشگاه یافت نشد.",
            True,
        )
        return

    await db.execute(
        """
        INSERT OR IGNORE INTO seller_favorites (
            user_id,
            seller_id,
            created_at
        )
        VALUES (?, ?, ?);
        """,
        (
            int(user["id"]),
            seller_id,
            _now_iso(),
        ),
    )

    await db.execute(
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
            int(user["id"]),
            "favorite_add",
            "seller",
            seller_id,
            _now_iso(),
        ),
    )

    await _render_seller_detail(
        db,
        telegram,
        callback_query,
        seller_id,
        int(user["id"]),
    )

    await _answer_callback(
        telegram,
        callback_query,
        "❤️ ذخیره شد!",
        True,
    )


async def handle_seller_favorite_remove(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    callback_data = str(callback_query.get("data", ""))
    seller_id = _parse_seller_id(callback_data)

    if seller_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شناسه فروشگاه نامعتبر است.",
            True,
        )
        return

    callback_user = callback_query.get("from")

    if not isinstance(callback_user, dict):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

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

    seller = await _get_seller(
        db,
        seller_id,
    )

    if seller is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ این فروشگاه یافت نشد.",
            True,
        )
        return

    result = await db.execute(
        """
        DELETE FROM seller_favorites
        WHERE user_id = ?
          AND seller_id = ?;
        """,
        (
            int(user["id"]),
            seller_id,
        ),
    )

    if getattr(
        result,
        "rowcount",
        0,
    ) != 1:
        await _answer_callback(
            telegram,
            callback_query,
            "این فروشگاه دیگر در علاقه‌مندی‌ها نیست.",
            True,
        )
        return

    await db.execute(
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
            int(user["id"]),
            "favorite_remove",
            "seller",
            seller_id,
            _now_iso(),
        ),
    )

    await _render_seller_detail(
        db,
        telegram,
        callback_query,
        seller_id,
        int(user["id"]),
    )

    await _answer_callback(
        telegram,
        callback_query,
        "از علاقه‌مندی‌ها حذف شد 💔",
        True,
    )


async def _render_seller_detail(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    seller_id: int,
    user_id: int,
) -> None:
    seller = await _get_seller(
        db,
        seller_id,
    )

    if seller is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ این فروشگاه یافت نشد.",
            True,
        )
        return

    message = callback_query.get(
        "message"
    )

    if not isinstance(
        message,
        dict,
    ):
        return

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
    message_id = message.get(
        "message_id"
    )

    if (
        chat_id is None
        or message_id is None
    ):
        return

    status = str(
        seller.get("status") or ""
    ).upper()

    lines = [
        (
            f"🏪 <b>{_html(seller.get('name') or 'فروشگاه')}</b>"
        ),
        "",
        (
            _html(seller.get("description"))
            if seller.get("description")
            else "بدون توضیحات"
        ),
        "",
        (
            f"📍 {_html(seller.get('city_name') or 'نامشخص')}"
        ),
        (
            f"⭐ {float(seller.get('rating') or 0):.1f} "
            f"({_html(seller.get('review_count') or 0)} نظر)"
        ),
        (
            f"{_status_badge(status)} "
            f"{_html(status)}"
        ),
    ]

    if status == "UNCLAIMED":
        lines.extend(
            [
                "",
                "این صفحه هنوز توسط صاحب کسب‌وکار تأیید نشده است.",
            ]
        )

    is_active = (
        bool(seller["is_active"])
        if seller.get("is_active") is not None
        else True
    )

    if not is_active:
        lines.extend(
            [
                "",
                (
                    "🔴 این فروشگاه موقتاً غیرفعال است "
                    "و فعلاً امکان ارتباط جدید ندارد."
                ),
            ]
        )

    await telegram.edit_message_text(
        chat_id,
        int(message_id),
        "\n".join(lines),
        reply_markup=await _seller_keyboard(
            db,
            seller,
            user_id,
        ),
        parse_mode="HTML",
    )


async def handle_seller_detail(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Render the public seller detail screen.

    Seller favorite actions are handled by dedicated
    Worker handlers.
    """

    callback_data = str(
        callback_query.get(
            "data",
            "",
        )
    )

    seller_id = _parse_seller_id(
        callback_data
    )

    if seller_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شناسه فروشگاه نامعتبر است.",
            True,
        )
        return

    callback_user = callback_query.get(
        "from"
    )

    if not isinstance(
        callback_user,
        dict,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    try:
        user = await _ensure_user(
            db,
            callback_user,
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

    seller = await _get_seller(
        db,
        seller_id,
    )

    if seller is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ این فروشگاه یافت نشد.",
            True,
        )
        return

    now = _now_iso()

    result = await db.execute(
        """
        UPDATE sellers
        SET views = COALESCE(views, 0) + 1,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            now,
            seller_id,
        ),
    )

    if getattr(
        result,
        "rowcount",
        0,
    ) != 1:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ ثبت بازدید انجام نشد. لطفاً دوباره تلاش کن.",
            True,
        )
        return

    status = str(
        seller.get("status") or ""
    ).upper()

    rating = seller.get("rating") or 0
    review_count = seller.get("review_count") or 0

    lines = [
        (
            f"🏪 <b>{_html(seller.get('name') or 'فروشگاه')}</b>"
        ),
        "",
        (
            _html(seller.get("description"))
            if seller.get("description")
            else "بدون توضیحات"
        ),
        "",
        (
            f"📍 {_html(seller.get('city_name') or 'نامشخص')}"
        ),
        (
            f"⭐ {float(rating):.1f} "
            f"({_html(review_count)} نظر)"
        ),
        (
            f"{_status_badge(status)} "
            f"{_html(status)}"
        ),
    ]

    if status == "UNCLAIMED":
        lines.extend(
            [
                "",
                (
                    "این صفحه هنوز توسط صاحب "
                    "کسب‌وکار تأیید نشده است."
                ),
            ]
        )

    is_active = (
        bool(seller.get("is_active"))
        if seller.get("is_active") is not None
        else True
    )

    if not is_active:
        lines.extend(
            [
                "",
                (
                    "🔴 این فروشگاه موقتاً غیرفعال است "
                    "و فعلاً امکان ارتباط جدید ندارد."
                ),
            ]
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
            int(user["id"]),
            "view_seller",
            "seller",
            seller_id,
            None,
            now,
        ),
    )

    message = callback_query.get(
        "message"
    )

    if not isinstance(
        message,
        dict,
    ):
        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    chat = message.get(
        "chat"
    )

    if not isinstance(
        chat,
        dict,
    ):
        await _answer_callback(
            telegram,
            callback_query,
        )
        return

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
        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    await telegram.edit_message_text(
        chat_id,
        int(message_id),
        "\n".join(lines),
        reply_markup=await _seller_keyboard(
            db,
            seller,
            int(user["id"]),
        ),
        parse_mode="HTML",
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def _answer_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    text: str | None = None,
    show_alert: bool = False,
) -> None:
    callback_query_id = callback_query.get(
        "id"
    )

    if not callback_query_id:
        return

    await telegram.answer_callback_query(
        str(callback_query_id),
        text=text,
        show_alert=show_alert,
    )


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


__all__ = [
    "handle_sellers_list",
    "handle_seller_detail",
    "handle_seller_favorite_add",
    "handle_seller_favorite_remove",
]