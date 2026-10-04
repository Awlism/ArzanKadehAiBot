# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker-side seller product management.

This module intentionally does not import aiogram, sqlite, or aiosqlite.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any

from worker.state import clear_state, get_state, set_state


STATE_NAME = "product_management"
PAGE_SIZE = 8

STOCK_LABELS = {
    "AVAILABLE": "موجود",
    "OUT_OF_STOCK": "ناموجود",
    "PREORDER": "پیش‌فروش",
}

EDITABLE_FIELDS = {
    "name": "🏷️ نام محصول",
    "description": "📝 توضیحات محصول",
    "price": "💰 قیمت",
    "old_price": "💸 قیمت قبل از تخفیف",
    "image_url": "🖼️ لینک تصویر محصول",
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


def _parse_id(value: Any) -> int | None:
    try:
        result = int(str(value).strip())
    except (TypeError, ValueError):
        return None

    return result if result > 0 else None


def _format_price(value: Any) -> str:
    if value is None:
        return "توافقی"

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if number.is_integer():
        return f"{int(number):,} تومان"

    return f"{number:,.2f} تومان"


def _keyboard(
    rows: list[list[dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "inline_keyboard": rows,
    }


def _button(
    text: str,
    callback_data: str,
) -> dict[str, Any]:
    return {
        "text": text,
        "callback_data": callback_data,
    }


def _back(
    callback_data: str = "account",
) -> list[dict[str, Any]]:
    return [
        _button(
            "🔙 بازگشت",
            callback_data,
        )
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
        raise ValueError(
            "Invalid Telegram user id."
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
        raise RuntimeError(
            "Failed to resolve user."
        )

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
        (
            user_id,
            user_id,
        ),
    )


async def _owned_seller(
    db: Any,
    user_id: int,
    seller_id: int,
) -> dict[str, Any] | None:
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


async def _owned_product(
    db: Any,
    user_id: int,
    product_id: int,
) -> dict[str, Any] | None:
    return await db.fetchone(
        """
        SELECT
            p.*,
            s.name AS seller_name
        FROM products p
        JOIN sellers s
          ON s.id = p.seller_id
        WHERE p.id = ?
          AND (
              s.owner_user_id = ?
              OR s.created_by_user_id = ?
          )
        LIMIT 1;
        """,
        (
            product_id,
            user_id,
            user_id,
        ),
    )


async def _audit(
    db: Any,
    user_id: int,
    action: str,
    entity_id: int,
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
        VALUES (?, ?, 'product', ?, ?, ?);
        """,
        (
            user_id,
            action,
            entity_id,
            details,
            _now_iso(),
        ),
    )


async def _set_state(
    db: Any,
    user_id: int,
    step: str,
    data: dict[str, Any] | None = None,
) -> None:
    await set_state(
        db,
        user_id,
        STATE_NAME,
        {
            "step": step,
            **(data or {}),
        },
    )


async def _show_seller_picker(
    telegram: Any,
    callback_query: dict[str, Any],
    sellers: list[dict[str, Any]],
) -> None:
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
                    f"🏪 {_html(seller.get('name') or 'فروشگاه')}",
                    f"prodlist:{seller_id}",
                )
            ]
        )

    rows.append(_back())

    await _edit(
        telegram,
        callback_query,
        "📦 کدوم فروشگاهت رو می‌خوای مدیریت کنی؟",
        _keyboard(rows),
    )

    await _answer(
        telegram,
        callback_query,
    )


async def handle_my_products(
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

    await clear_state(
        db,
        int(user["id"]),
    )

    sellers = await _owned_sellers(
        db,
        int(user["id"]),
    )

    if not sellers:
        await _edit(
            telegram,
            callback_query,
            (
                "📦 هنوز فروشگاهی برای مدیریت نداری.\n\n"
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
            telegram,
            callback_query,
            sellers,
        )
        return

    await _render_product_list(
        db,
        telegram,
        callback_query,
        int(sellers[0]["id"]),
        0,
    )


async def handle_product_list(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(
        callback_query.get("data", "")
    )

    parts = data.split(":")

    if len(parts) < 2:
        await _answer(
            telegram,
            callback_query,
            "⚠️ درخواست نامعتبر است.",
            True,
        )
        return

    seller_id = _parse_id(parts[1])
    page = (
        _parse_id(parts[2])
        if len(parts) > 2
        else 1
    )

    if seller_id is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شناسه فروشگاه نامعتبر است.",
            True,
        )
        return

    page_index = max(
        0,
        (page or 1) - 1,
    )

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

    seller = await _owned_seller(
        db,
        int(user["id"]),
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
        int(user["id"]),
    )

    await _render_product_list(
        db,
        telegram,
        callback_query,
        seller_id,
        page_index,
    )


async def _render_product_list(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    seller_id: int,
    page: int,
) -> None:
    products = await db.fetchall(
        """
        SELECT *
        FROM products
        WHERE seller_id = ?
        ORDER BY created_at DESC;
        """,
        (seller_id,),
    )

    rows: list[list[dict[str, Any]]] = [
        [
            _button(
                "➕ افزودن محصول",
                f"prodadd:{seller_id}",
            )
        ]
    ]

    if not products:
        text = (
            "📦 هنوز محصولی اینجا نیست.\n\n"
            "بیا اولین محصولت رو اضافه کنیم 😊"
        )
    else:
        start = page * PAGE_SIZE
        page_rows = products[
            start:start + PAGE_SIZE
        ]

        for product in page_rows:
            product_id = _parse_id(
                product.get("id")
            )

            if product_id is None:
                continue

            stock = STOCK_LABELS.get(
                product.get("stock_status"),
                str(
                    product.get("stock_status")
                    or ""
                ),
            )

            rows.append(
                [
                    _button(
                        (
                            "🛍️ "
                            f"{_html(product.get('name'))}"
                            " — "
                            f"{_format_price(product.get('price'))}"
                            f" ({_html(stock)})"
                        ),
                        f"product:{product_id}",
                    )
                ]
            )

            rows.append(
                [
                    _button(
                        "✏️ ویرایش",
                        f"prodedit:{product_id}",
                    ),
                    _button(
                        "🗑️ حذف",
                        f"proddel:{product_id}",
                    ),
                ]
            )

        has_previous = page > 0
        has_next = (
            start + PAGE_SIZE
            < len(products)
        )

        navigation: list[dict[str, Any]] = []

        if has_previous:
            navigation.append(
                _button(
                    "⬅️ قبلی",
                    f"prodlist:{seller_id}:{page}",
                )
            )

        if has_next:
            navigation.append(
                _button(
                    "بعدی ➡️",
                    f"prodlist:{seller_id}:{page + 2}",
                )
            )

        if navigation:
            rows.append(navigation)

        text = (
            "📦 <b>محصولات فروشگاه</b>\n\n"
            "محصولی که می‌خوای رو انتخاب کن."
        )

    rows.append(_back())

    await _edit(
        telegram,
        callback_query,
        text,
        _keyboard(rows),
    )

    await _answer(
        telegram,
        callback_query,
    )


async def handle_product_add_start(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(
        callback_query.get("data", "")
    )

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

    seller = await _owned_seller(
        db,
        int(user["id"]),
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

    await _set_state(
        db,
        int(user["id"]),
        "add_name",
        {
            "seller_id": seller_id,
        },
    )

    await _edit(
        telegram,
        callback_query,
        "🏷️ نام محصول رو بفرست:",
        _keyboard(
            [
                _back(
                    f"prodlist:{seller_id}"
                )
            ]
        ),
    )

    await _answer(
        telegram,
        callback_query,
    )


async def handle_product_add_skip(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(
        callback_query.get("data", "")
    )

    parts = data.split(":")

    if len(parts) != 2:
        await _answer(
            telegram,
            callback_query,
            "⚠️ درخواست نامعتبر است.",
            True,
        )
        return

    field = parts[1]

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

    state = await get_state(
        db,
        int(user["id"]),
    )

    if not state or state.get("state") != STATE_NAME:
        await _answer(
            telegram,
            callback_query,
            "⚠️ فرآیند منقضی شده. دوباره شروع کن.",
            True,
        )
        return

    state_data = state.get("data") or {}

    if field == "description":
        state_data["description"] = None

        await _set_state(
            db,
            int(user["id"]),
            "add_price",
            state_data,
        )

        await _edit(
            telegram,
            callback_query,
            "💰 قیمت محصول رو بفرست (فقط عدد، تومان):",
            _keyboard(
                [
                    _back(
                        f"prodlist:{state_data['seller_id']}"
                    )
                ]
            ),
        )

    elif field == "old_price":
        state_data["old_price"] = None

        await _set_state(
            db,
            int(user["id"]),
            "add_image",
            state_data,
        )

        await _edit(
            telegram,
            callback_query,
            "🖼️ لینک تصویر محصول رو بفرست، یا رد کن:",
            _keyboard(
                [
                    [
                        _button(
                            "⏭ رد کردن",
                            "prodaddskip:image",
                        )
                    ],
                    _back(
                        f"prodlist:{state_data['seller_id']}"
                    ),
                ]
            ),
        )

    elif field == "image":
        state_data["image_url"] = None

        await _finish_product_add(
            db,
            telegram,
            callback_query,
            int(user["id"]),
            state_data,
        )
    else:
        await _answer(
            telegram,
            callback_query,
            "⚠️ گزینه نامعتبر است.",
            True,
        )
        return

    await _answer(
        telegram,
        callback_query,
    )


async def _finish_product_add(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    user_id: int,
    data: dict[str, Any],
) -> None:
    seller_id = _parse_id(
        data.get("seller_id")
    )

    name = str(
        data.get("name")
        or ""
    ).strip()

    if seller_id is None or not name:
        await clear_state(
            db,
            user_id,
        )

        await _answer(
            telegram,
            callback_query,
            "⚠️ اطلاعات محصول ناقص است.",
            True,
        )
        return

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

        await _answer(
            telegram,
            callback_query,
            "⚠️ شما به این فروشگاه دسترسی ندارید.",
            True,
        )
        return

    now = _now_iso()

    result = await db.execute(
        """
        INSERT INTO products (
            seller_id,
            name,
            description,
            price,
            old_price,
            image_url,
            stock_status,
            rating,
            review_count,
            views,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'AVAILABLE', 0, 0, 0, ?, ?);
        """,
        (
            seller_id,
            name,
            data.get("description"),
            data.get("price"),
            data.get("old_price"),
            data.get("image_url"),
            now,
            now,
        ),
    )

    product_id = getattr(
        result,
        "lastrowid",
        None,
    )

    if product_id is None:
        await clear_state(
            db,
            user_id,
        )

        await _answer(
            telegram,
            callback_query,
            "⚠️ ثبت محصول انجام نشد.",
            True,
        )
        return

    await _audit(
        db,
        user_id,
        "product_created",
        int(product_id),
        name,
    )

    await clear_state(
        db,
        user_id,
    )

    await _edit(
        telegram,
        callback_query,
        (
            "✅ محصول با موفقیت اضافه شد.\n\n"
            f"🛍️ <b>{_html(name)}</b>"
        ),
        _keyboard(
            [
                [
                    _button(
                        "📦 محصولاتم",
                        f"prodlist:{seller_id}",
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


async def handle_product_edit_menu(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(
        callback_query.get("data", "")
    )

    product_id = _parse_id(
        data.split(":", 1)[1]
        if ":" in data
        else None
    )

    if product_id is None:
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

    product = await _owned_product(
        db,
        int(user["id"]),
        product_id,
    )

    if product is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شما به این محصول دسترسی ندارید.",
            True,
        )
        return

    rows = []

    for field, label in EDITABLE_FIELDS.items():
        rows.append(
            [
                _button(
                    label,
                    f"prodfield:{product_id}:{field}",
                )
            ]
        )

    rows.append(
        [
            _button(
                "📦 وضعیت موجودی",
                f"prodstock:{product_id}",
            )
        ]
    )

    rows.append(
        _back(
            f"prodlist:{product['seller_id']}"
        )
    )

    await _edit(
        telegram,
        callback_query,
        (
            f"✏️ <b>ویرایش محصول</b>\n\n"
            f"🛍️ {_html(product.get('name'))}\n\n"
            "کدوم بخش رو می‌خوای تغییر بدی؟"
        ),
        _keyboard(rows),
    )

    await _answer(
        telegram,
        callback_query,
    )


async def handle_product_field_start(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(
        callback_query.get("data", "")
    )

    parts = data.split(":")

    if len(parts) != 3:
        await _answer(
            telegram,
            callback_query,
            "⚠️ درخواست نامعتبر است.",
            True,
        )
        return

    product_id = _parse_id(parts[1])
    field = parts[2]

    if product_id is None or field not in EDITABLE_FIELDS:
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

    product = await _owned_product(
        db,
        int(user["id"]),
        product_id,
    )

    if product is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شما به این محصول دسترسی ندارید.",
            True,
        )
        return

    await _set_state(
        db,
        int(user["id"]),
        "edit_value",
        {
            "product_id": product_id,
            "field": field,
        },
    )

    await _edit(
        telegram,
        callback_query,
        (
            f"{EDITABLE_FIELDS[field]} رو بفرست:"
        ),
        _keyboard(
            [
                _back(
                    f"prodedit:{product_id}"
                )
            ]
        ),
    )

    await _answer(
        telegram,
        callback_query,
    )


async def handle_product_stock_menu(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(
        callback_query.get("data", "")
    )

    product_id = _parse_id(
        data.split(":", 1)[1]
        if ":" in data
        else None
    )

    if product_id is None:
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

    product = await _owned_product(
        db,
        int(user["id"]),
        product_id,
    )

    if product is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شما به این محصول دسترسی ندارید.",
            True,
        )
        return

    rows = [
        [
            _button(
                "✅ موجود",
                f"prodstockset:{product_id}:AVAILABLE",
            )
        ],
        [
            _button(
                "⛔️ ناموجود",
                f"prodstockset:{product_id}:OUT_OF_STOCK",
            )
        ],
        [
            _button(
                "⏳ پیش‌فروش",
                f"prodstockset:{product_id}:PREORDER",
            )
        ],
        _back(
            f"prodedit:{product_id}"
        ),
    ]

    await _edit(
        telegram,
        callback_query,
        "📦 وضعیت موجودی رو انتخاب کن:",
        _keyboard(rows),
    )

    await _answer(
        telegram,
        callback_query,
    )


async def handle_product_stock_set(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(
        callback_query.get("data", "")
    )

    parts = data.split(":")

    if len(parts) != 3:
        await _answer(
            telegram,
            callback_query,
            "⚠️ درخواست نامعتبر است.",
            True,
        )
        return

    product_id = _parse_id(parts[1])
    status = parts[2]

    if (
        product_id is None
        or status not in STOCK_LABELS
    ):
        await _answer(
            telegram,
            callback_query,
            "⚠️ وضعیت نامعتبر است.",
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

    product = await _owned_product(
        db,
        int(user["id"]),
        product_id,
    )

    if product is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شما به این محصول دسترسی ندارید.",
            True,
        )
        return

    await db.execute(
        """
        UPDATE products
        SET stock_status = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            status,
            _now_iso(),
            product_id,
        ),
    )

    await _audit(
        db,
        int(user["id"]),
        "product_updated",
        product_id,
        "stock_status",
    )

    await _answer(
        telegram,
        callback_query,
        "✅ وضعیت موجودی به‌روزرسانی شد.",
        True,
    )

    await handle_product_edit_menu(
        db,
        telegram,
        callback_query,
    )


async def handle_product_delete(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(
        callback_query.get("data", "")
    )

    product_id = _parse_id(
        data.split(":", 1)[1]
        if ":" in data
        else None
    )

    if product_id is None:
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

    product = await _owned_product(
        db,
        int(user["id"]),
        product_id,
    )

    if product is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شما به این محصول دسترسی ندارید.",
            True,
        )
        return

    await _edit(
        telegram,
        callback_query,
        (
            f"🗑️ حذف «<b>{_html(product.get('name'))}</b>»؟\n\n"
            "مطمئنی می‌خوای این محصول حذف بشه؟"
        ),
        _keyboard(
            [
                [
                    _button(
                        "🗑️ آره، حذفش کن",
                        f"proddelyes:{product_id}",
                    )
                ],
                [
                    _button(
                        "❌ نه، برگرد",
                        f"prodedit:{product_id}",
                    )
                ],
            ]
        ),
    )

    await _answer(
        telegram,
        callback_query,
    )


async def handle_product_delete_confirmed(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(
        callback_query.get("data", "")
    )

    product_id = _parse_id(
        data.split(":", 1)[1]
        if ":" in data
        else None
    )

    if product_id is None:
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

    product = await _owned_product(
        db,
        int(user["id"]),
        product_id,
    )

    if product is None:
        await _answer(
            telegram,
            callback_query,
            "⚠️ شما به این محصول دسترسی ندارید.",
            True,
        )
        return

    seller_id = int(
        product["seller_id"]
    )

    await db.execute(
        """
        DELETE FROM products
        WHERE id = ?;
        """,
        (product_id,),
    )

    await _audit(
        db,
        int(user["id"]),
        "product_deleted",
        product_id,
        str(
            product.get("name")
            or ""
        ),
    )

    await _answer(
        telegram,
        callback_query,
        "🗑️ محصول حذف شد.",
        True,
    )

    await _render_product_list(
        db,
        telegram,
        callback_query,
        seller_id,
        0,
    )


async def handle_product_message(
    db: Any,
    telegram: Any,
    message: dict[str, Any],
) -> bool:
    """
    Handles persistent text states belonging to product management.

    Returns True when the message belongs to this module.
    """

    telegram_user = message.get("from") or {}

    try:
        user = await _ensure_user(
            db,
            telegram_user,
        )
    except (ValueError, RuntimeError):
        return False

    user_id = int(
        user["id"]
    )

    state = await get_state(
        db,
        user_id,
    )

    if not state or state.get("state") != STATE_NAME:
        return False

    data = state.get("data") or {}
    step = data.get("step")
    text = str(
        message.get("text") or ""
    ).strip()

    if step == "add_name":
        if not text:
            await _send(
                telegram,
                message,
                "⚠️ نام محصول نمی‌تونه خالی باشه. دوباره بفرست:",
            )
            return True

        data["name"] = text

        await _set_state(
            db,
            user_id,
            "add_description",
            data,
        )

        await _send(
            telegram,
            message,
            "📝 توضیح کوتاه محصول (اختیاری):",
            _keyboard(
                [
                    [
                        _button(
                            "⏭ رد کردن",
                            "prodaddskip:description",
                        )
                    ]
                ]
            ),
        )

        return True

    if step == "add_description":
        data["description"] = text or None

        await _set_state(
            db,
            user_id,
            "add_price",
            data,
        )

        await _send(
            telegram,
            message,
            "💰 قیمت محصول رو بفرست (فقط عدد، تومان):",
        )

        return True

    if step == "add_price":
        normalized = text.replace(
            ",",
            "",
        )

        try:
            price = int(normalized)
        except (TypeError, ValueError):
            price = -1

        if price < 0:
            await _send(
                telegram,
                message,
                "⚠️ لطفاً فقط عدد قیمت رو بفرست:",
            )
            return True

        data["price"] = price

        await _set_state(
            db,
            user_id,
            "add_old_price",
            data,
        )

        await _send(
            telegram,
            message,
            "💸 قیمت قبل از تخفیف (اختیاری):",
            _keyboard(
                [
                    [
                        _button(
                            "⏭ رد کردن",
                            "prodaddskip:old_price",
                        )
                    ]
                ]
            ),
        )

        return True

    if step == "add_old_price":
        if text in (
            "",
            "0",
            "-",
            "حذف",
        ):
            data["old_price"] = None
        else:
            try:
                old_price = int(
                    text.replace(",", "")
                )
            except (TypeError, ValueError):
                old_price = -1

            if old_price < 0:
                await _send(
                    telegram,
                    message,
                    "⚠️ لطفاً فقط عدد بفرست یا «رد کردن» رو بزن:",
                )
                return True

            data["old_price"] = old_price

        await _set_state(
            db,
            user_id,
            "add_image",
            data,
        )

        await _send(
            telegram,
            message,
            "🖼️ لینک تصویر محصول رو بفرست، یا رد کن:",
            _keyboard(
                [
                    [
                        _button(
                            "⏭ رد کردن",
                            "prodaddskip:image",
                        )
                    ]
                ]
            ),
        )

        return True

    if step == "add_image":
        data["image_url"] = text or None

        callback_query = {
            "id": None,
            "from": telegram_user,
            "message": message,
        }

        await _finish_product_add(
            db,
            telegram,
            callback_query,
            user_id,
            data,
        )

        return True

    if step == "edit_value":
        product_id = _parse_id(
            data.get("product_id")
        )
        field = data.get("field")

        if (
            product_id is None
            or field not in EDITABLE_FIELDS
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

        product = await _owned_product(
            db,
            user_id,
            product_id,
        )

        if product is None:
            await clear_state(
                db,
                user_id,
            )

            await _send(
                telegram,
                message,
                "⚠️ شما به این محصول دسترسی ندارید.",
            )

            return True

        if field == "name":
            if not text:
                await _send(
                    telegram,
                    message,
                    "⚠️ نام محصول نمی‌تونه خالی باشه:",
                )
                return True

            value: Any = text

        elif field in (
            "price",
            "old_price",
        ):
            if (
                field == "old_price"
                and text in (
                    "",
                    "0",
                    "-",
                    "حذف",
                )
            ):
                value = None
            else:
                try:
                    value = int(
                        text.replace(",", "")
                    )
                except (TypeError, ValueError):
                    value = -1

                if value < 0:
                    await _send(
                        telegram,
                        message,
                        "⚠️ لطفاً فقط عدد بفرست:",
                    )
                    return True

        else:
            value = text or None

        await db.execute(
            f"""
            UPDATE products
            SET {field} = ?,
                updated_at = ?
            WHERE id = ?;
            """,
            (
                value,
                _now_iso(),
                product_id,
            ),
        )

        await _audit(
            db,
            user_id,
            "product_updated",
            product_id,
            field,
        )

        await clear_state(
            db,
            user_id,
        )

        await _send(
            telegram,
            message,
            "✅ محصول با موفقیت به‌روزرسانی شد.",
            _keyboard(
                [
                    [
                        _button(
                            "✏️ ویرایش دوباره",
                            f"prodedit:{product_id}",
                        )
                    ],
                    [
                        _button(
                            "📦 محصولاتم",
                            f"prodlist:{product['seller_id']}",
                        )
                    ],
                    _back(),
                ]
            ),
        )

        return True

    return False


__all__ = [
    "STATE_NAME",
    "handle_my_products",
    "handle_product_list",
    "handle_product_add_start",
    "handle_product_add_skip",
    "handle_product_edit_menu",
    "handle_product_field_start",
    "handle_product_stock_menu",
    "handle_product_stock_set",
    "handle_product_delete",
    "handle_product_delete_confirmed",
    "handle_product_message",
]