# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker-side seller shop management.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any

from worker.state import clear_state, get_state, set_state


STATE_NAME = "shop_edit"

SHOP_EDITABLE_FIELDS = {
    "name": "🏪 نام فروشگاه",
    "description": "📝 توضیحات فروشگاه",
    "instagram": "📸 اینستاگرام",
    "telegram": "📢 کانال/ربات تلگرام",
    "telegram_support": "💬 پشتیبانی تلگرام",
    "whatsapp": "🟢 واتساپ",
    "website": "🌐 وبسایت",
    "phone": "📞 تلفن",
    "location_text": "📍 لوکیشن",
    "coverage_area": "🗺️ محدوده کاری",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _html(value: Any) -> str:
    if value is None:
        return ""
    return escape(str(value), quote=False)


def _parse_id(value: Any) -> int | None:
    try:
        result = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _button(text: str, callback_data: str) -> dict[str, Any]:
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


def _back(callback_data: str = "account") -> list[dict[str, Any]]:
    return [
        _button("🔙 بازگشت", callback_data)
    ]


async def _answer(
    telegram: Any,
    callback_query: dict[str, Any],
    text: str | None = None,
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


def _context(
    callback_query: dict[str, Any],
) -> tuple[int, int] | None:
    message = callback_query.get("message")

    if not isinstance(message, dict):
        return None

    chat = message.get("chat")

    if not isinstance(chat, dict):
        return None

    chat_id = _parse_id(chat.get("id"))
    message_id = _parse_id(message.get("message_id"))

    if chat_id is None or message_id is None:
        return None

    return chat_id, message_id


async def _edit(
    telegram: Any,
    callback_query: dict[str, Any],
    text: str,
    keyboard: dict[str, Any] | None = None,
) -> None:
    context = _context(callback_query)

    if context is None:
        return

    chat_id, message_id = context

    await telegram.edit_message_text(
        chat_id,
        message_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def _send(
    telegram: Any,
    message: dict[str, Any],
    text: str,
    keyboard: dict[str, Any] | None = None,
) -> None:
    chat = message.get("chat")

    if not isinstance(chat, dict):
        return

    chat_id = _parse_id(chat.get("id"))

    if chat_id is None:
        return

    await telegram.send_message(
        chat_id,
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
        raise ValueError("Invalid Telegram user id.")

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
            telegram_user.get("username"),
            telegram_user.get("first_name"),
            telegram_user.get("last_name"),
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
        raise RuntimeError("Failed to resolve user.")

    return user


async def _owned_sellers(
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
        (user_id, user_id),
    )


async def _owned_seller(
    db: Any,
    user_id: int,
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
        WHERE s.id = ?
          AND (
              s.owner_user_id = ?
              OR s.created_by_user_id = ?
          )
        LIMIT 1;
        """,
        (seller_id, user_id, user_id),
    )


async def _audit(
    db: Any,
    user_id: int,
    action: str,
    seller_id: int,
    details: str | None = None,
) -> None:
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
        VALUES (?, ?, 'seller', ?, ?, ?);
        """,
        (
            user_id,
            action,
            seller_id,
            details,
            _now_iso(),
        ),
    )


async def _show_seller_picker(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    sellers: list[dict[str, Any]],
) -> None:
    rows: list[list[dict[str, Any]]] = []

    for seller in sellers:
        seller_id = _parse_id(seller.get("id"))

        if seller_id is None:
            continue

        rows.append(
            [
                _button(
                    f"🏪 {_html(seller.get('name') or 'فروشگاه')}",
                    f"shopview:{seller_id}",
                )
            ]
        )

    rows.append(_back())

    await _edit(
        telegram,
        callback_query,
        "کدوم فروشگاهت رو می‌خوای مدیریت کنی؟",
        _keyboard(rows),
    )

    await _answer(
        telegram,
        callback_query,
    )


async def handle_my_shop(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    user_data = callback_query.get("from") or {}

    try:
        user = await _ensure_user(
            db,
            user_data,
        )
    except (ValueError, RuntimeError):
        await _answer(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    user_id = int(user["id"])

    await clear_state(
        db,
        user_id,
    )

    sellers = await _owned_sellers(
        db,
        user_id,
    )

    if not sellers:
        await _edit(
            telegram,
            callback_query,
            (
                "🏪 هنوز فروشگاهی برای مدیریت نداری.\n\n"
                "اول فروشگاهت رو ثبت کن."
            ),
            _keyboard(
                [
                    [
                        _button(
                            "➕ ثبت فروشگاه",
                            "registerseller",
                        )
                    ],
                    _back(),
                ]
            ),
        )

        await _answer(
            telegram,
            callback_query,
        )
        return

    if len(sellers) > 1:
        await _show_seller_picker(
            db,
            telegram,
            callback_query,
            sellers,
        )
        return

    await _render_shop_view(
        db,
        telegram,
        callback_query,
        user_id,
        int(sellers[0]["id"]),
    )


async def handle_shop_view(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(callback_query.get("data", ""))
    parts = data.split(":")

    if len(parts) != 2:
        await _answer(
            telegram,
            callback_query,
            "⚠️ درخواست نامعتبر است.",
            True,
        )
        return

    seller_id = _parse_id(parts[1])

    if seller_id is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شناسه فروشگاه نامعتبر است.",
            True,
        )
        return

    user_data = callback_query.get("from") or {}

    try:
        user = await _ensure_user(
            db,
            user_data,
        )
    except (ValueError, RuntimeError):
        await _answer(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    user_id = int(user["id"])

    await clear_state(
        db,
        user_id,
    )

    seller = await _owned_seller(
        db,
        user_id,
        seller_id,
    )

    if seller is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شما به این فروشگاه دسترسی ندارید.",
            True,
        )
        return

    await _render_shop_view(
        db,
        telegram,
        callback_query,
        user_id,
        seller_id,
    )


async def _render_shop_view(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    user_id: int,
    seller_id: int,
) -> None:
    seller = await _owned_seller(
        db,
        user_id,
        seller_id,
    )

    if seller is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ این فروشگاه یافت نشد.",
            True,
        )
        return

    is_active = bool(
        seller.get("is_active", 1)
    )

    has_contact = any(
        [
            seller.get("instagram"),
            seller.get("telegram"),
            seller.get("whatsapp"),
        ]
    )

    lines = [
        "🏪 <b>فروشگاهت این شکلیه 👇</b>",
        "اگر چیزی نیاز به تغییر داره، از همین‌جا درستش کنیم.",
        "",
        f"<b>{_html(seller.get('name'))}</b>",
        _html(
            seller.get("description")
            or "هنوز معرفی کوتاهی ننوشتی."
        ),
        "",
        f"📸 اینستاگرام: {_html(seller.get('instagram') or '—')}",
        f"📢 کانال/ربات تلگرام: {_html(seller.get('telegram') or '—')}",
        f"💬 پشتیبانی تلگرام: {_html(seller.get('telegram_support') or '—')}",
        f"🟢 واتساپ: {_html(seller.get('whatsapp') or '—')}",
        f"🌐 وبسایت: {_html(seller.get('website') or '—')}",
        f"📞 تلفن: {_html(seller.get('phone') or '—')}",
        f"📍 لوکیشن: {_html(seller.get('location_text') or '—')}",
        f"🗺️ محدوده کاری: {_html(seller.get('coverage_area') or '—')}",
        f"🏙️ شهر: {_html(seller.get('city_name') or '—')}",
        (
            "وضعیت: 🟢 فعال"
            if is_active
            else "وضعیت: 🔴 غیرفعال"
        ),
    ]

    if not has_contact:
        lines.append(
            "\n⚠️ حداقل یکی از اینستاگرام، تلگرام یا واتساپ "
            "رو تکمیل کن تا خریدارها بتونن باهات در ارتباط باشن."
        )

    toggle_text = (
        "🔴 غیرفعال کردن فروشگاه"
        if is_active
        else "🟢 فعال کردن فروشگاه"
    )

    rows = [
        [
            _button(
                "✏️ یه چیزی رو تغییر بدم",
                f"shopeditmenu:{seller_id}",
            )
        ],
        [
            _button(
                "📍 شهرم رو عوض کنم",
                f"shopcity:{seller_id}",
            )
        ],
        [
            _button(
                toggle_text,
                f"storetoggle:{seller_id}",
            )
        ],
        [
            _button(
                "🔗 لینک فروشگاهم",
                "reflist",
            )
        ],
        _back(),
    ]

    await _edit(
        telegram,
        callback_query,
        "\n".join(lines),
        _keyboard(rows),
    )

    await _answer(
        telegram,
        callback_query,
    )


async def handle_shop_edit_menu(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(callback_query.get("data", ""))
    seller_id = _parse_id(
        data.split(":", 1)[1]
        if ":" in data
        else None
    )

    if seller_id is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شناسه نامعتبر است.",
            True,
        )
        return

    user_data = callback_query.get("from") or {}

    try:
        user = await _ensure_user(
            db,
            user_data,
        )
    except (ValueError, RuntimeError):
        await _answer(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    user_id = int(user["id"])

    seller = await _owned_seller(
        db,
        user_id,
        seller_id,
    )

    if seller is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شما به این فروشگاه دسترسی ندارید.",
            True,
        )
        return

    await clear_state(
        db,
        user_id,
    )

    rows: list[list[dict[str, Any]]] = []
    current_row: list[dict[str, Any]] = []

    for field, label in SHOP_EDITABLE_FIELDS.items():
        current_row.append(
            _button(
                label,
                f"shopedit:{seller_id}:{field}",
            )
        )

        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)

    rows.append(
        _back(f"shopview:{seller_id}")
    )

    await _edit(
        telegram,
        callback_query,
        "کدوم بخش رو می‌خوای تغییر بدی؟",
        _keyboard(rows),
    )

    await _answer(
        telegram,
        callback_query,
    )


async def handle_shop_edit_start(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(callback_query.get("data", ""))
    parts = data.split(":")

    if len(parts) != 3:
        await _answer(
            telegram,
            callback_query,
            "⚠️ درخواست نامعتبر است.",
            True,
        )
        return

    seller_id = _parse_id(parts[1])
    field = parts[2]

    if (
        seller_id is None
        or field not in SHOP_EDITABLE_FIELDS
    ):
        await _answer(
            telegram,
            callback_query,
            "⚠️ درخواست نامعتبر است.",
            True,
        )
        return

    user_data = callback_query.get("from") or {}

    try:
        user = await _ensure_user(
            db,
            user_data,
        )
    except (ValueError, RuntimeError):
        await _answer(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    user_id = int(user["id"])

    seller = await _owned_seller(
        db,
        user_id,
        seller_id,
    )

    if seller is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شما به این فروشگاه دسترسی ندارید.",
            True,
        )
        return

    await set_state(
        db,
        user_id,
        STATE_NAME,
        {
            "step": "waiting_value",
            "seller_id": seller_id,
            "field": field,
        },
    )

    await _edit(
        telegram,
        callback_query,
        f"{SHOP_EDITABLE_FIELDS[field]} رو بفرست:",
        _keyboard(
            [
                _back(
                    f"shopview:{seller_id}"
                )
            ]
        ),
    )

    await _answer(
        telegram,
        callback_query,
    )


async def handle_shop_city_start(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(callback_query.get("data", ""))

    seller_id = _parse_id(
        data.split(":", 1)[1]
        if ":" in data
        else None
    )

    if seller_id is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ درخواست نامعتبر است.",
            True,
        )
        return

    user_data = callback_query.get("from") or {}

    try:
        user = await _ensure_user(
            db,
            user_data,
        )
    except (ValueError, RuntimeError):
        await _answer(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    user_id = int(user["id"])

    seller = await _owned_seller(
        db,
        user_id,
        seller_id,
    )

    if seller is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شما به این فروشگاه دسترسی ندارید.",
            True,
        )
        return

    cities = await db.fetchall(
        """
        SELECT id, name
        FROM cities
        ORDER BY name;
        """
    )

    rows: list[list[dict[str, Any]]] = []
    current_row: list[dict[str, Any]] = []

    for city in cities:
        city_id = _parse_id(city.get("id"))

        if city_id is None:
            continue

        current_row.append(
            _button(
                _html(city.get("name")),
                f"shopcitypick:{seller_id}:{city_id}",
            )
        )

        if len(current_row) == 3:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)

    rows.append(
        _back(f"shopview:{seller_id}")
    )

    await _edit(
        telegram,
        callback_query,
        "📍 شهر فروشگاه رو انتخاب کن:",
        _keyboard(rows),
    )

    await _answer(
        telegram,
        callback_query,
    )


async def handle_shop_city_pick(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(callback_query.get("data", ""))
    parts = data.split(":")

    if len(parts) != 3:
        await _answer(
            telegram,
            callback_query,
            "⚠️ درخواست نامعتبر است.",
            True,
        )
        return

    seller_id = _parse_id(parts[1])
    city_id = _parse_id(parts[2])

    if seller_id is None or city_id is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شناسه نامعتبر است.",
            True,
        )
        return

    user_data = callback_query.get("from") or {}

    try:
        user = await _ensure_user(
            db,
            user_data,
        )
    except (ValueError, RuntimeError):
        await _answer(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    user_id = int(user["id"])

    seller = await _owned_seller(
        db,
        user_id,
        seller_id,
    )

    if seller is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شما به این فروشگاه دسترسی ندارید.",
            True,
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
        await _answer(
            telegram,
            callback_query,
            "⚠️ شهر پیدا نشد.",
            True,
        )
        return

    await db.execute(
        """
        UPDATE sellers
        SET city_id = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            city_id,
            _now_iso(),
            seller_id,
        ),
    )

    await clear_state(
        db,
        user_id,
    )

    await _audit(
        db,
        user_id,
        "shop_city_updated",
        seller_id,
        str(city.get("name") or ""),
    )

    await _answer(
        telegram,
        callback_query,
        "✅ شهر فروشگاه تغییر کرد.",
        True,
    )

    await _render_shop_view(
        db,
        telegram,
        callback_query,
        user_id,
        seller_id,
    )


async def handle_shop_toggle_active(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(callback_query.get("data", ""))

    seller_id = _parse_id(
        data.split(":", 1)[1]
        if ":" in data
        else None
    )

    if seller_id is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شناسه نامعتبر است.",
            True,
        )
        return

    user_data = callback_query.get("from") or {}

    try:
        user = await _ensure_user(
            db,
            user_data,
        )
    except (ValueError, RuntimeError):
        await _answer(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    user_id = int(user["id"])

    seller = await _owned_seller(
        db,
        user_id,
        seller_id,
    )

    if seller is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شما به این فروشگاه دسترسی ندارید.",
            True,
        )
        return

    current = bool(
        seller.get("is_active", 1)
    )

    new_value = 0 if current else 1

    await db.execute(
        """
        UPDATE sellers
        SET is_active = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            new_value,
            _now_iso(),
            seller_id,
        ),
    )

    action = (
        "store_deactivated"
        if current
        else "store_activated"
    )

    await _audit(
        db,
        user_id,
        action,
        seller_id,
    )

    await _answer(
        telegram,
        callback_query,
        (
            "🔴 فروشگاه غیرفعال شد."
            if current
            else "🟢 فروشگاه فعال شد."
        ),
        True,
    )

    await _render_shop_view(
        db,
        telegram,
        callback_query,
        user_id,
        seller_id,
    )


async def handle_shop_edit_message(
    db: Any,
    telegram: Any,
    message: dict[str, Any],
) -> bool:
    telegram_user = message.get("from") or {}

    try:
        user = await _ensure_user(
            db,
            telegram_user,
        )
    except (ValueError, RuntimeError):
        return False

    user_id = int(user["id"])

    state = await get_state(
        db,
        user_id,
    )

    if not state or state.get("state") != STATE_NAME:
        return False

    data = state.get("data") or {}

    if data.get("step") != "waiting_value":
        return False

    seller_id = _parse_id(
        data.get("seller_id")
    )
    field = data.get("field")

    if (
        seller_id is None
        or field not in SHOP_EDITABLE_FIELDS
    ):
        await clear_state(
            db,
            user_id,
        )

        await _send(
            telegram,
            message,
            "⚠️ فرآیند ویرایش منقضی شده. دوباره تلاش کن.",
        )

        return True

    seller = await _owned_seller(
        db,
        user_id,
        seller_id,
    )

    if seller is None:
        await clear_state(
            db,
            user_id,
        )

        await _send(
            telegram,
            message,
            "⚠️ شما به این فروشگاه دسترسی ندارید.",
        )

        return True

    value = str(
        message.get("text") or ""
    ).strip()

    if field == "name" and not value:
        await _send(
            telegram,
            message,
            "⚠️ نام فروشگاه نمی‌تونه خالی باشه. دوباره بفرست:",
        )
        return True

    value_to_store = value or None

    await db.execute(
        f"""
        UPDATE sellers
        SET {field} = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            value_to_store,
            _now_iso(),
            seller_id,
        ),
    )

    await clear_state(
        db,
        user_id,
    )

    await _audit(
        db,
        user_id,
        "shop_field_updated",
        seller_id,
        field,
    )

    await _send(
        telegram,
        message,
        "✅ به‌روزرسانی شد.",
        _keyboard(
            [
                [
                    _button(
                        "🏪 مشاهده فروشگاه",
                        f"shopview:{seller_id}",
                    )
                ],
                _back(),
            ]
        ),
    )

    # Legacy behavior: if Telegram channel/account is entered
    # while Telegram support is empty, request the support account.
    if (
        field == "telegram"
        and value_to_store
        and not seller.get("telegram_support")
    ):
        await set_state(
            db,
            user_id,
            STATE_NAME,
            {
                "step": "waiting_value",
                "seller_id": seller_id,
                "field": "telegram_support",
            },
        )

        await _send(
            telegram,
            message,
            (
                "چون کانال/ربات تلگرام رو وارد کردی، "
                "آیدی تلگرام پشتیبانی هم لازمه:\n"
                "💬 پشتیبانی تلگرام رو بفرست:"
            ),
        )

    return True


__all__ = [
    "STATE_NAME",
    "SHOP_EDITABLE_FIELDS",
    "handle_my_shop",
    "handle_shop_view",
    "handle_shop_edit_menu",
    "handle_shop_edit_start",
    "handle_shop_city_start",
    "handle_shop_city_pick",
    "handle_shop_toggle_active",
    "handle_shop_edit_message",
]