# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker-side seller store status and activation handlers.

This module intentionally does not import aiogram, sqlite, or aiosqlite.
"""

from __future__ import annotations

from html import escape
from typing import Any, Optional


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


def _parse_callback_id(
    callback_query: dict[str, Any],
    prefix: str,
) -> Optional[int]:
    callback_data = str(
        callback_query.get("data", "")
    )

    if not callback_data.startswith(prefix):
        return None

    value = callback_data[len(prefix):]

    return _parse_id(value)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


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
    message = (
        callback_query.get("message")
        or {}
    )

    chat = (
        message.get("chat")
        or {}
    )

    chat_id = _parse_id(
        chat.get("id")
    )

    message_id = _parse_id(
        message.get("message_id")
    )

    if (
        chat_id is None
        or message_id is None
    ):
        return

    await telegram.edit_message_text(
        chat_id,
        message_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


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
            "Failed to resolve user."
        )

    return user


async def _get_owned_sellers(
    db: Any,
    user_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT
            id,
            name
        FROM sellers
        WHERE created_by_user_id = ?
           OR owner_user_id = ?
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
    seller = await db.fetchone(
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

    return seller


async def _show_seller_picker(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    user_id: int,
    *,
    title: str,
    callback_prefix: str,
) -> None:
    sellers = await _get_owned_sellers(
        db,
        user_id,
    )

    if not sellers:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شما هنوز فروشگاهی ثبت نکرده‌اید.",
            True,
        )
        return

    if len(sellers) == 1:
        seller_id = _parse_id(
            sellers[0].get("id")
        )

        if seller_id is not None:
            if callback_prefix == "storestat:":
                await _render_store_status(
                    db,
                    telegram,
                    callback_query,
                    seller_id,
                    user_id,
                )
                return

            if callback_prefix == "storetoggle:":
                await _toggle_store_active(
                    db,
                    telegram,
                    callback_query,
                    seller_id,
                    user_id,
                )
                return

    rows: list[
        list[dict[str, Any]]
    ] = []

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
                    f"{callback_prefix}{seller_id}",
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
        title,
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def _count_events(
    db: Any,
    event_type: str,
    entity_type: str,
    entity_id: int,
) -> int:
    row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM events
        WHERE event_type = ?
          AND entity_type = ?
          AND entity_id = ?;
        """,
        (
            event_type,
            entity_type,
            entity_id,
        ),
    )

    if row is None:
        return 0

    return int(
        row["c"] or 0
    )


async def _render_store_status(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    seller_id: int,
    user_id: int,
) -> None:
    seller = await _get_owned_seller(
        db,
        user_id,
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

    favorite_row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM seller_favorites
        WHERE seller_id = ?;
        """,
        (seller_id,),
    )

    favorite_count = (
        int(favorite_row["c"] or 0)
        if favorite_row
        else 0
    )

    instagram_clicks = await _count_events(
        db,
        "instagram_click",
        "seller",
        seller_id,
    )

    telegram_clicks = await _count_events(
        db,
        "telegram_click",
        "seller",
        seller_id,
    )

    whatsapp_clicks = await _count_events(
        db,
        "whatsapp_click",
        "seller",
        seller_id,
    )

    products = await db.fetchall(
        """
        SELECT
            id,
            views,
            stock_status
        FROM products
        WHERE seller_id = ?;
        """,
        (seller_id,),
    )

    total_product_views = sum(
        int(product["views"] or 0)
        for product in products
    )

    active_products = sum(
        1
        for product in products
        if str(
            product["stock_status"] or ""
        ).upper() == "AVAILABLE"
    )

    request_row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM requests
        WHERE seller_id = ?;
        """,
        (seller_id,),
    )

    request_count = (
        int(request_row["c"] or 0)
        if request_row
        else 0
    )

    seller_views = int(
        seller["views"] or 0
    )

    is_active = (
        bool(seller["is_active"])
        if seller.get("is_active") is not None
        else True
    )

    status_text = (
        "🟢 فعال"
        if is_active
        else "🔴 غیرفعال"
    )

    text = (
        "👀 <b>ببینیم فروشگاهت چطور پیش میره!</b>\n\n"
        f"🏪 <b>{_html(seller['name'])}</b>\n"
        f"📌 وضعیت: {status_text}\n\n"
        f"👀 بازدید فروشگاه: {seller_views}\n"
        f"🛍️ تعداد محصولات: {len(products)}\n"
        f"✅ محصولات موجود: {active_products}\n"
        f"❤️ ذخیره‌ها: {favorite_count}\n"
        f"📦 بازدید محصولات: {total_product_views}\n"
        f"📸 کلیک Instagram: {instagram_clicks}\n"
        f"✈️ کلیک Telegram: {telegram_clicks}\n"
        f"🟢 کلیک WhatsApp: {whatsapp_clicks}\n"
        f"📋 درخواست‌های ثبت‌شده: {request_count}\n"
    )

    rows: list[
        list[dict[str, Any]]
    ] = []

    if products:
        rows.append(
            [
                _button(
                    "📊 آمار تک‌تک محصولات",
                    f"statshome:{seller_id}",
                )
            ]
        )

    rows.append(
        [
            _button(
                (
                    "🔴 غیرفعال کردن فروشگاه"
                    if is_active
                    else "🟢 فعال کردن فروشگاه"
                ),
                f"storetoggle:{seller_id}",
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
        text,
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_store_status(
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
        user["id"]
    )

    await _show_seller_picker(
        db,
        telegram,
        callback_query,
        user_id,
        title="📊 کدوم فروشگاهت رو می‌خوای ببینی؟",
        callback_prefix="storestat:",
    )


async def handle_store_status_picked(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    seller_id = _parse_callback_id(
        callback_query,
        "storestat:",
    )

    if seller_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شناسه فروشگاه نامعتبر است.",
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

    await _render_store_status(
        db,
        telegram,
        callback_query,
        seller_id,
        int(user["id"]),
    )


async def _toggle_store_active(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    seller_id: int,
    user_id: int,
) -> None:
    seller = await _get_owned_seller(
        db,
        user_id,
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

    current_active = (
        bool(seller["is_active"])
        if seller.get("is_active") is not None
        else True
    )

    new_active = not current_active

    await db.execute(
        """
        UPDATE sellers
        SET is_active = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            1 if new_active else 0,
            _now_iso(),
            seller_id,
        ),
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
            (
                "store_activated"
                if new_active
                else "store_deactivated"
            ),
            "seller",
            seller_id,
            None,
            _now_iso(),
        ),
    )

    await _render_store_status(
        db,
        telegram,
        callback_query,
        seller_id,
        user_id,
    )

    await _answer_callback(
        telegram,
        callback_query,
        (
            "🟢 فروشگاهت فعال شد."
            if new_active
            else "🔴 فروشگاهت غیرفعال شد."
        ),
        True,
    )


async def handle_store_toggle_active(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    seller_id = _parse_callback_id(
        callback_query,
        "storetoggle:",
    )

    if seller_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ شناسه فروشگاه نامعتبر است.",
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

    await _toggle_store_active(
        db,
        telegram,
        callback_query,
        seller_id,
        int(user["id"]),
    )


__all__ = [
    "handle_store_status",
    "handle_store_status_picked",
    "handle_store_toggle_active",
]