# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker-side product comparison handlers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any


COMPARE_MAX_ITEMS = 4

COMPARE_INTRO_TEXT = (
    "⚖️ مقایسه چیه؟\n"
    "تا چهار محصول رو کنار هم بذار تا راحت‌تر انتخاب کنی. ✨"
)


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


def _now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


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
    telegram_id = user.get("id")

    if not isinstance(
        telegram_id,
        int,
    ):
        raise ValueError(
            "Telegram user id is required."
        )

    existing = await _get_user_by_telegram_id(
        db,
        telegram_id,
    )

    username = user.get("username")
    first_name = user.get("first_name")
    last_name = user.get("last_name")

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

    existing = await _get_user_by_telegram_id(
        db,
        telegram_id,
    )

    if existing is None:
        raise RuntimeError(
            "Failed to create or load user."
        )

    return existing


async def _get_selection(
    db: Any,
    user_id: int,
) -> list[int]:
    rows = await db.fetchall(
        """
        SELECT product_id
        FROM compare_selections
        WHERE user_id = ?
        ORDER BY position ASC, id ASC;
        """,
        (user_id,),
    )

    return [
        int(row["product_id"])
        for row in rows
    ]


async def _set_selection(
    db: Any,
    user_id: int,
    selection: list[int],
) -> None:
    normalized: list[int] = []

    for product_id in selection:
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            continue

        if product_id < 1:
            continue

        if product_id in normalized:
            continue

        normalized.append(product_id)

        if len(normalized) >= COMPARE_MAX_ITEMS:
            break

    now = _now_iso()

    async with db.transaction() as transaction:
        await transaction.execute(
            """
            DELETE FROM compare_selections
            WHERE user_id = ?;
            """,
            (user_id,),
        )

        for position, product_id in enumerate(
            normalized,
            start=1,
        ):
            await transaction.execute(
                """
                INSERT INTO compare_selections (
                    user_id,
                    product_id,
                    position,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    user_id,
                    product_id,
                    position,
                    now,
                    now,
                ),
            )


async def _clear_selection(
    db: Any,
    user_id: int,
) -> None:
    await db.execute(
        """
        DELETE FROM compare_selections
        WHERE user_id = ?;
        """,
        (user_id,),
    )


def _compare_add(
    selection: list[int],
    product_id: int,
) -> tuple[list[int], str]:
    current = list(selection)

    if product_id in current:
        return (
            current,
            "already_in_selection",
        )

    if len(current) >= COMPARE_MAX_ITEMS:
        return (
            current,
            "already_full",
        )

    current.append(product_id)

    if len(current) >= COMPARE_MAX_ITEMS:
        return (
            current,
            "added_ready",
        )

    return (
        current,
        "added_need_more",
    )


async def _has_seen_intro(
    db: Any,
    user_id: int,
) -> bool:
    row = await db.fetchone(
        """
        SELECT has_seen_compare_intro
        FROM users
        WHERE id = ?
        LIMIT 1;
        """,
        (user_id,),
    )

    return bool(
        row
        and row["has_seen_compare_intro"]
    )


async def _mark_intro_seen(
    db: Any,
    user_id: int,
) -> None:
    await db.execute(
        """
        UPDATE users
        SET has_seen_compare_intro = 1,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            _now_iso(),
            user_id,
        ),
    )


async def _get_available_product(
    db: Any,
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
          AND COALESCE(s.is_active, 1) = 1;
        """,
        (product_id,),
    )


async def _get_compare_products(
    db: Any,
    selection: list[int],
) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []

    for product_id in selection:
        row = await _get_available_product(
            db,
            product_id,
        )

        if row is not None:
            products.append(row)

    return products


def _main_back_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "↩️ بازگشت",
                    "callback_data": "main",
                }
            ]
        ]
    }


def _compare_list_keyboard(
    products: list[dict[str, Any]],
) -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = []

    for product in products:
        product_id = int(
            product["id"]
        )

        name = _html(
            product["name"]
        )

        rows.append(
            [
                {
                    "text": f"❌ حذف {name}",
                    "callback_data": (
                        f"comparedrop:{product_id}"
                    ),
                }
            ]
        )

    rows.append(
        [
            {
                "text": "↩️ بازگشت",
                "callback_data": "main",
            }
        ]
    )

    return {
        "inline_keyboard": rows
    }


def _compare_ready_keyboard(
    products: list[dict[str, Any]],
) -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = []

    for product in products:
        product_id = int(
            product["id"]
        )

        product_name = _html(
            product["name"]
        )

        rows.append(
            [
                {
                    "text": f"🛍️ {product_name}",
                    "callback_data": (
                        f"product:{product_id}"
                    ),
                }
            ]
        )

    rows.append(
        [
            {
                "text": "🔄 شروع مقایسه جدید",
                "callback_data": "comparereset",
            }
        ]
    )

    rows.append(
        [
            {
                "text": "↩️ بازگشت",
                "callback_data": "main",
            }
        ]
    )

    return {
        "inline_keyboard": rows
    }


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


async def handle_compare(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Legacy compare callback.

    It redirects to the compare list.
    """

    await handle_compare_list(
        db,
        telegram,
        callback_query,
    )


async def handle_compare_list(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    answer_text: str | None = None,
) -> None:
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

    user = await _ensure_user(
        db,
        callback_user,
    )

    user_id = int(
        user["id"]
    )

    if not await _has_seen_intro(
        db,
        user_id,
    ):
        await _mark_intro_seen(
            db,
            user_id,
        )

        await _edit_callback_message(
            telegram,
            callback_query,
            COMPARE_INTRO_TEXT,
            _main_back_keyboard(),
        )

        await _answer_callback(
            telegram,
            callback_query,
            answer_text or "",
        )
        return

    selection = await _get_selection(
        db,
        user_id,
    )

    if not selection:
        await _edit_callback_message(
            telegram,
            callback_query,
            (
                "⚖️ هنوز محصولی برای مقایسه "
                "انتخاب نکردی.\n\n"
                "از روی صفحه هر محصول، دکمه "
                "«افزودن به مقایسه» رو بزن."
            ),
            _main_back_keyboard(),
        )

        await _answer_callback(
            telegram,
            callback_query,
            answer_text or "",
        )
        return

    products = await _get_compare_products(
        db,
        selection,
    )

    valid_product_ids = [
        int(product["id"])
        for product in products
    ]

    if len(products) != len(selection):
        await _set_selection(
            db,
            user_id,
            valid_product_ids,
        )

    if not products:
        await _edit_callback_message(
            telegram,
            callback_query,
            (
                "⚠️ محصولات انتخاب‌شده دیگر "
                "در دسترس نیستند.\n\n"
                "مقایسه پاک شد؛ می‌تونی دوباره "
                "محصولات جدید انتخاب کنی."
            ),
            _main_back_keyboard(),
        )

        await _answer_callback(
            telegram,
            callback_query,
            answer_text or "",
        )
        return

    if len(products) < COMPARE_MAX_ITEMS:
        selected_names = "\n".join(
            f"• {_html(product['name'])}"
            for product in products
        )

        remaining = (
            COMPARE_MAX_ITEMS
            - len(products)
        )

        await _edit_callback_message(
            telegram,
            callback_query,
            (
                "⚖️ برای شروع مقایسه، "
                f"{remaining} محصول دیگه انتخاب کن."
                "\n\n"
                "انتخاب فعلی:"
                f"\n{selected_names}"
            ),
            _compare_list_keyboard(
                products
            ),
        )

        await _answer_callback(
            telegram,
            callback_query,
            answer_text or "",
        )
        return

    lines = [
        "⚖️ <b>مقایسه محصولات</b>",
        "",
        (
            f"📊 مقایسه {len(products)} محصول"
        ),
        "",
    ]

    for index, product in enumerate(
        products,
        start=1,
    ):
        product_name = _html(
            product["name"]
        )

        seller_name = _html(
            product["seller_name"]
        )

        rating = product.get(
            "rating"
        )

        review_count = product.get(
            "review_count"
        )

        try:
            rating_text = (
                f"{float(rating):.1f}"
            )
        except (
            TypeError,
            ValueError,
        ):
            rating_text = "—"

        try:
            review_text = str(
                int(review_count or 0)
            )
        except (
            TypeError,
            ValueError,
        ):
            review_text = "0"

        lines.extend(
            [
                f"<b>{index}. {product_name}</b>",
                (
                    "💰 قیمت: "
                    f"{_format_price(product.get('price'))}"
                ),
                (
                    "⭐ امتیاز: "
                    f"{rating_text}"
                    f" ({review_text} نظر)"
                ),
                (
                    "🏪 فروشنده: "
                    f"{seller_name}"
                ),
                "",
            ]
        )

    await _edit_callback_message(
        telegram,
        callback_query,
        "\n".join(lines).strip(),
        _compare_ready_keyboard(
            products
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
        answer_text or "",
    )


async def handle_compare_start(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
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

    product = await _get_available_product(
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

    user = await _ensure_user(
        db,
        callback_user,
    )

    user_id = int(
        user["id"]
    )

    if not await _has_seen_intro(
        db,
        user_id,
    ):
        await _mark_intro_seen(
            db,
            user_id,
        )

    selection = await _get_selection(
        db,
        user_id,
    )

    new_selection, outcome = _compare_add(
        selection,
        product_id,
    )

    if outcome == "already_in_selection":
        await _answer_callback(
            telegram,
            callback_query,
            "این محصول قبلاً به مقایسه اضافه شده.",
            True,
        )
        return

    if outcome == "already_full":
        await _answer_callback(
            telegram,
            callback_query,
            (
                "مقایسه همزمان فقط برای "
                f"{COMPARE_MAX_ITEMS} محصول امکان‌پذیره."
            ),
            True,
        )
        return

    await _set_selection(
        db,
        user_id,
        new_selection,
    )

    if outcome == "added_ready":
        await _answer_callback(
            telegram,
            callback_query,
            (
                "✅ محصول چهارم اضافه شد! "
                "حالا مقایسه آماده‌ست."
            ),
            True,
        )
        return

    remaining = (
        COMPARE_MAX_ITEMS
        - len(new_selection)
    )

    await _answer_callback(
        telegram,
        callback_query,
        (
            "✅ اضافه شد! "
            f"{remaining} محصول دیگه انتخاب کن."
        ),
        True,
    )


async def handle_compare_drop(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    callback_data = str(
        callback_query.get(
            "data",
            "",
        )
    )

    product_id = _parse_product_id(
        callback_data
    )

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

    user = await _ensure_user(
        db,
        callback_user,
    )

    user_id = int(
        user["id"]
    )

    if product_id is not None:
        selection = await _get_selection(
            db,
            user_id,
        )

        selection = [
            selected_id
            for selected_id in selection
            if selected_id != product_id
        ]

        await _set_selection(
            db,
            user_id,
            selection,
        )

    await handle_compare_list(
        db,
        telegram,
        callback_query,
        answer_text="حذف شد.",
    )


async def handle_compare_reset(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
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

    user = await _ensure_user(
        db,
        callback_user,
    )

    await _clear_selection(
        db,
        int(user["id"]),
    )

    await handle_compare_list(
        db,
        telegram,
        callback_query,
        answer_text="مقایسه پاک شد.",
    )


__all__ = [
    "handle_compare",
    "handle_compare_list",
    "handle_compare_start",
    "handle_compare_drop",
    "handle_compare_reset",
    "COMPARE_MAX_ITEMS",
    "COMPARE_INTRO_TEXT",
]