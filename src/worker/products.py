# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker-side product handlers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from html import escape
from typing import Any


def _html(value: Any) -> str:
    if value is None:
        return ""

    return escape(
        str(value),
        quote=False,
    )


def _parse_product_id(
    callback_data: str,
) -> int | None:
    if ":" not in callback_data:
        return None

    _, value = callback_data.split(
        ":",
        1,
    )

    try:
        product_id = int(value)
    except (TypeError, ValueError):
        return None

    if product_id < 1:
        return None

    return product_id


def _format_price(
    value: Any,
) -> str:
    if value is None:
        return "توافقی"

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if number.is_integer():
        return f"{int(number):,} تومان"

    return f"{number:,.2f} تومان"


def _back_keyboard(
    callback_data: str,
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


async def _is_favorite(
    db: Any,
    user_id: int,
    product_id: int,
) -> bool:
    row = await db.fetchone(
        """
        SELECT id
        FROM favorites
        WHERE user_id = ?
          AND product_id = ?
        LIMIT 1;
        """,
        (
            user_id,
            product_id,
        ),
    )

    return row is not None


def _product_keyboard(
    product: dict[str, Any],
    is_favorite: bool = False,
) -> dict[str, Any]:
    product_id = int(
        product["id"]
    )

    category_id = product.get(
        "category_id"
    )

    if category_id:
        back_callback = (
            f"cat:{category_id}:0"
        )
    else:
        back_callback = "main"

    favorite_text = (
        "💔 حذف از علاقه‌مندی‌ها"
        if is_favorite
        else "❤️ افزودن به علاقه‌مندی‌ها"
    )

    favorite_callback = (
        f"unfavorite:{product_id}"
        if is_favorite
        else f"favorite:{product_id}"
    )

    return {
        "inline_keyboard": [
            [
                {
                    "text": favorite_text,
                    "callback_data": favorite_callback,
                }
            ],
            [
                {
                    "text": "⚖️ افزودن به مقایسه",
                    "callback_data": (
                        f"comparestart:{product_id}"
                    ),
                }
            ],
            [
                {
                    "text": "🏪 فروشگاه",
                    "callback_data": (
                        f"seller:{product['seller_id']}"
                    ),
                }
            ],
            [
                {
                    "text": "⭐ ثبت نظر",
                    "callback_data": (
                        f"reviewstart:product:{product_id}"
                    ),
                }
            ],
            [
                {
                    "text": "🚩 گزارش",
                    "callback_data": (
                        f"report:product:{product_id}"
                    ),
                }
            ],
            [
                {
                    "text": "🔙 بازگشت",
                    "callback_data": back_callback,
                }
            ],
        ]
    }


async def _get_user_by_telegram_id(
    db: Any,
    telegram_id: int,
) -> dict[str, Any] | None:
    return await db.fetchone(
        """
        SELECT *
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_id,),
    )


async def _ensure_user(
    db: Any,
    user: dict[str, Any],
) -> dict[str, Any]:
    telegram_id = user.get(
        "id"
    )

    if telegram_id is None:
        raise ValueError(
            "Telegram user id is required."
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

    existing = await _get_user_by_telegram_id(
        db,
        telegram_id,
    )

    now = _now_iso()

    username = user.get(
        "username"
    )
    first_name = user.get(
        "first_name"
    )
    last_name = user.get(
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

    user_row = await _get_user_by_telegram_id(
        db,
        telegram_id,
    )

    if user_row is None:
        raise RuntimeError(
            "Failed to create or load user."
        )

    return user_row


async def _get_product(
    db: Any,
    product_id: int,
) -> dict[str, Any] | None:
    return await db.fetchone(
        """
        SELECT
            p.*,
            s.name AS seller_name,
            s.status AS seller_status,
            c.name AS city_name
        FROM products p
        JOIN sellers s
            ON s.id = p.seller_id
        LEFT JOIN cities c
            ON c.id = s.city_id
        WHERE p.id = ?
          AND COALESCE(s.is_active, 1) = 1;
        """,
        (product_id,),
    )


async def handle_product_detail(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Render the product detail screen.
    """

    callback_data = str(
        callback_query.get(
            "data",
            "",
        )
    )

    product_id = _parse_product_id(
        callback_data
    )

    if product_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شناسه نامعتبر است.",
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

    product = await _get_product(
        db,
        product_id,
    )

    if product is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ این محصول یافت نشد.",
            True,
        )
        return

    now = _now_iso()

    result = await db.execute(
        """
        UPDATE products
        SET views = COALESCE(views, 0) + 1,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            now,
            product_id,
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
            "view_product",
            "product",
            product_id,
            None,
            now,
        ),
    )

    product = await _get_product(
        db,
        product_id,
    )

    if product is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ این محصول دیگر در دسترس نیست.",
            True,
        )
        return

    is_favorite = await _is_favorite(
        db,
        int(user["id"]),
        product_id,
    )

    rating = product.get(
        "rating"
    )

    review_count = product.get(
        "review_count"
    )

    if rating is None:
        rating_text = "0.0"
    else:
        try:
            rating_text = f"{float(rating):.1f}"
        except (
            TypeError,
            ValueError,
        ):
            rating_text = "0.0"

    if review_count is None:
        review_count = 0

    stock_status = product.get(
        "stock_status"
    )

    lines = [
        (
            "🛍️ <b>"
            f"{_html(product.get('name'))}"
            "</b>"
        ),
        "",
        _html(
            product.get(
                "description"
            )
            or "بدون توضیحات"
        ),
        "",
        (
            "💰 "
            f"{_format_price(product.get('price'))}"
        ),
        (
            "🏪 "
            f"{_html(product.get('seller_name'))}"
        ),
        (
            "📍 "
            f"{_html(product.get('city_name') or 'نامشخص')}"
        ),
        (
            "⭐ "
            f"{rating_text}"
            f" ({_html(review_count)} نظر)"
        ),
    ]

    seller_status = product.get(
        "seller_status"
    )

    if seller_status:
        lines.append(
            f"🔹 وضعیت فروشنده: "
            f"{_html(seller_status)}"
        )

    if stock_status == "OUT_OF_STOCK":
        lines.append(
            "⛔️ ناموجود"
        )

    await _edit_callback_message(
        telegram,
        callback_query,
        "\n".join(lines),
        _product_keyboard(
            product,
            is_favorite=is_favorite,
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_favorite_add(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Add a product to the user's favorites.
    """

    callback_data = str(
        callback_query.get(
            "data",
            "",
        )
    )

    product_id = _parse_product_id(
        callback_data
    )

    if product_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شناسه نامعتبر است.",
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

    product = await _get_product(
        db,
        product_id,
    )

    if product is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ این محصول یافت نشد.",
            True,
        )
        return

    try:
        await db.execute(
            """
            INSERT INTO favorites (
                user_id,
                product_id,
                created_at
            )
            VALUES (?, ?, ?);
            """,
            (
                int(user["id"]),
                product_id,
                _now_iso(),
            ),
        )
    except Exception as exc:
        message = str(exc).lower()

        if (
            "unique" in message
            or "constraint" in message
        ):
            await _answer_callback(
                telegram,
                callback_query,
                "این محصول از قبل در علاقه‌مندی‌هاست ❤️",
                True,
            )

            await _render_product_after_action(
                db,
                telegram,
                callback_query,
                int(user["id"]),
                product_id,
            )
            return

        raise

    await _answer_callback(
        telegram,
        callback_query,
        "❤️ به علاقه‌مندی‌ها اضافه شد.",
        True,
    )

    await _render_product_after_action(
        db,
        telegram,
        callback_query,
        int(user["id"]),
        product_id,
    )


async def handle_favorite_remove(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Remove a product from the user's favorites.
    """

    callback_data = str(
        callback_query.get(
            "data",
            "",
        )
    )

    product_id = _parse_product_id(
        callback_data
    )

    if product_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شناسه نامعتبر است.",
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

    result = await db.execute(
        """
        DELETE FROM favorites
        WHERE user_id = ?
          AND product_id = ?;
        """,
        (
            int(user["id"]),
            product_id,
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
            "این محصول دیگر در علاقه‌مندی‌ها نیست.",
            True,
        )

        await _render_product_after_action(
            db,
            telegram,
            callback_query,
            int(user["id"]),
            product_id,
        )
        return

    await _answer_callback(
        telegram,
        callback_query,
        "💔 از علاقه‌مندی‌ها حذف شد.",
        True,
    )

    await _render_product_after_action(
        db,
        telegram,
        callback_query,
        int(user["id"]),
        product_id,
    )


async def _render_product_after_action(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    user_id: int,
    product_id: int,
) -> None:
    product = await _get_product(
        db,
        product_id,
    )

    if product is None:
        return

    is_favorite = await _is_favorite(
        db,
        user_id,
        product_id,
    )

    rating = product.get(
        "rating"
    )

    review_count = product.get(
        "review_count"
    )

    if rating is None:
        rating_text = "0.0"
    else:
        try:
            rating_text = f"{float(rating):.1f}"
        except (
            TypeError,
            ValueError,
        ):
            rating_text = "0.0"

    if review_count is None:
        review_count = 0

    lines = [
        (
            "🛍️ <b>"
            f"{_html(product.get('name'))}"
            "</b>"
        ),
        "",
        _html(
            product.get(
                "description"
            )
            or "بدون توضیحات"
        ),
        "",
        (
            "💰 "
            f"{_format_price(product.get('price'))}"
        ),
        (
            "🏪 "
            f"{_html(product.get('seller_name'))}"
        ),
        (
            "📍 "
            f"{_html(product.get('city_name') or 'نامشخص')}"
        ),
        (
            "⭐ "
            f"{rating_text}"
            f" ({_html(review_count)} نظر)"
        ),
    ]

    seller_status = product.get(
        "seller_status"
    )

    if seller_status:
        lines.append(
            f"🔹 وضعیت فروشنده: "
            f"{_html(seller_status)}"
        )

    if product.get("stock_status") == "OUT_OF_STOCK":
        lines.append(
            "⛔️ ناموجود"
        )

    await _edit_callback_message(
        telegram,
        callback_query,
        "\n".join(lines),
        _product_keyboard(
            product,
            is_favorite=is_favorite,
        ),
    )


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
        callback_id,
        text=text,
        show_alert=show_alert,
    )


async def _edit_callback_message(
    telegram: Any,
    callback_query: dict[str, Any],
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> None:
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

    if chat_id is None:
        return

    if not isinstance(
        message_id,
        int,
    ):
        return

    await telegram.edit_message_text(
        chat_id,
        message_id,
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


def _now_iso() -> str:
    from datetime import (
        datetime,
        timezone,
    )

    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


__all__ = [
    "handle_product_detail",
    "handle_favorite_add",
    "handle_favorite_remove",
]