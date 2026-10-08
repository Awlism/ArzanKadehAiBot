# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker admin panel.

This module intentionally does not import aiogram, sqlite,
or any legacy bot module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Optional

from worker.state import clear_state, set_state
from worker.telegram import TelegramClient
from worker_backend.backend import backend


PAGE_SIZE = 10
ADMIN_USER_SEARCH_STATE = "admin:user_search"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(
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


def _back_row(
    callback_data: str,
) -> list[dict[str, Any]]:
    return [
        _button(
            "🔙 برگردیم",
            callback_data,
        )
    ]


def _message_context(
    callback_query: dict[str, Any],
) -> tuple[Optional[int], Optional[int]]:
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


async def _answer_callback(
    telegram: TelegramClient,
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
    telegram: TelegramClient,
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


async def _send(
    telegram: TelegramClient,
    chat_id: int,
    text: str,
    keyboard: Optional[dict[str, Any]] = None,
) -> Any:
    return await telegram.send_message(
        chat_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def _is_admin(
    env: Any,
    telegram_user_id: int,
) -> bool:
    try:
        admin_chat_id = getattr(
            env,
            "ADMIN_CHAT_ID",
            None,
        )
    except Exception:
        admin_chat_id = None

    if admin_chat_id is None:
        return False

    try:
        return int(admin_chat_id) == int(
            telegram_user_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return False


async def _ensure_user(
    telegram_user_id: int,
    *,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> int:
    now = _now_iso()

    await backend.execute(
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

    row = await backend.fetchone(
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


def _user_label(
    user: dict[str, Any],
) -> str:
    first_name = str(
        user.get("first_name") or ""
    ).strip()

    last_name = str(
        user.get("last_name") or ""
    ).strip()

    username = str(
        user.get("username") or ""
    ).strip()

    if first_name or last_name:
        full_name = (
            f"{first_name} {last_name}"
        ).strip()

        if username:
            return f"{full_name} (@{username})"

        return full_name

    if username:
        return f"@{username}"

    return str(
        user.get("telegram_id") or user.get("id")
    )


def _pagination_row(
    prefix: str,
    page: int,
    has_previous: bool,
    has_next: bool,
) -> list[dict[str, Any]]:
    buttons: list[dict[str, Any]] = []

    if has_previous:
        buttons.append(
            _button(
                "◀️ قبلی",
                f"{prefix}:{page - 1}",
            )
        )

    buttons.append(
        _button(
            f"صفحه {page + 1}",
            f"{prefix}:{page}",
        )
    )

    if has_next:
        buttons.append(
            _button(
                "بعدی ▶️",
                f"{prefix}:{page + 1}",
            )
        )

    return buttons


async def handle_admin_home(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
    env: Any,
) -> Any:
    _, telegram_user_id = _message_context(
        callback_query
    )

    if telegram_user_id is None:
        return None

    if not await _is_admin(
        env,
        telegram_user_id,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text="⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return None

    user_id = await _ensure_user(
        telegram_user_id
    )

    await clear_state(
        backend,
        user_id,
    )

    keyboard = _keyboard(
        [
            [
                _button(
                    "👥 کاربران",
                    "adminusers",
                )
            ],
            [
                _button(
                    "🏪 مالکیت فروشگاه‌ها",
                    "sellerclaimsadmin",
                )
            ],
            [
                _button(
                    "📢 تبلیغات",
                    "adsadmin",
                )
            ],
            _back_row("main"),
        ]
    )

    await _edit_callback(
        telegram,
        callback_query,
        "🛡 <b>پنل مدیریت</b>",
        keyboard,
    )

    await _answer_callback(
        telegram,
        callback_query,
    )

    return None


async def handle_admin_users_menu(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
    env: Any,
) -> Any:
    _, telegram_user_id = _message_context(
        callback_query
    )

    if telegram_user_id is None:
        return None

    if not await _is_admin(
        env,
        telegram_user_id,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text="⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return None

    user_id = await _ensure_user(
        telegram_user_id
    )

    await clear_state(
        backend,
        user_id,
    )

    keyboard = _keyboard(
        [
            [
                _button(
                    "🔎 جستجوی کاربر",
                    "adminusersearch",
                )
            ],
            [
                _button(
                    "📋 همه کاربران",
                    "adminuserlist:0",
                )
            ],
            _back_row("adminhome"),
        ]
    )

    await _edit_callback(
        telegram,
        callback_query,
        "👥 <b>کاربران</b>",
        keyboard,
    )

    await _answer_callback(
        telegram,
        callback_query,
    )

    return None


async def handle_admin_user_search_start(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
    env: Any,
) -> Any:
    chat_id, telegram_user_id = _message_context(
        callback_query
    )

    if (
        chat_id is None
        or telegram_user_id is None
    ):
        return None

    if not await _is_admin(
        env,
        telegram_user_id,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text="⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return None

    user_id = await _ensure_user(
        telegram_user_id
    )

    await set_state(
        backend,
        user_id,
        ADMIN_USER_SEARCH_STATE,
        {},
    )

    keyboard = _keyboard(
        [
            _back_row("adminusers"),
        ]
    )

    await _edit_callback(
        telegram,
        callback_query,
        (
            "🔎 <b>جستجوی کاربر</b>\n\n"
            "نام، username یا آیدی عددی تلگرام "
            "کاربر را بفرست:"
        ),
        keyboard,
    )

    await _answer_callback(
        telegram,
        callback_query,
    )

    return None


async def handle_admin_user_search_message(
    message: dict[str, Any],
    telegram: TelegramClient,
    env: Any,
) -> Any:
    user = message.get("from") or {}

    telegram_user_id = user.get("id")

    if telegram_user_id is None:
        return None

    try:
        telegram_user_id = int(
            telegram_user_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if not await _is_admin(
        env,
        telegram_user_id,
    ):
        return None

    user_id = await _ensure_user(
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    state = await _get_state_for_user(
        user_id
    )

    if state is None:
        return None

    if state.get("state") != ADMIN_USER_SEARCH_STATE:
        return None

    query = str(
        message.get("text") or ""
    ).strip()

    await clear_state(
        backend,
        user_id,
    )

    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if chat_id is None:
        return None

    if not query:
        await _send(
            telegram,
            int(chat_id),
            "⚠️ لطفاً یک متن معتبر برای جستجو بفرست.",
            _keyboard(
                [
                    _back_row("adminusers"),
                ]
            ),
        )
        return None

    like = f"%{query}%"

    if query.isdigit():
        rows = await backend.fetchall(
            """
            SELECT *
            FROM users
            WHERE username LIKE ?
               OR first_name LIKE ?
               OR last_name LIKE ?
               OR CAST(telegram_id AS TEXT) LIKE ?
            ORDER BY id DESC
            LIMIT ?;
            """,
            (
                like,
                like,
                like,
                like,
                PAGE_SIZE,
            ),
        )
    else:
        rows = await backend.fetchall(
            """
            SELECT *
            FROM users
            WHERE username LIKE ?
               OR first_name LIKE ?
               OR last_name LIKE ?
            ORDER BY id DESC
            LIMIT ?;
            """,
            (
                like,
                like,
                like,
                PAGE_SIZE,
            ),
        )

    rows_keyboard: list[list[dict[str, Any]]] = []

    for row in rows:
        rows_keyboard.append(
            [
                _button(
                    f"👤 {_html(_user_label(row))}",
                    f"adminuserview:{row['id']}",
                )
            ]
        )

    rows_keyboard.append(
        _back_row("adminusers")
    )

    if not rows:
        text = (
            "🔎 نتیجه‌ای برای "
            f"«{_html(query)}» پیدا نشد."
        )
    else:
        text = (
            "🔎 نتایج جستجو برای "
            f"«{_html(query)}»:"
        )

    await _send(
        telegram,
        int(chat_id),
        text,
        _keyboard(rows_keyboard),
    )

    return None


async def handle_admin_user_list(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
    env: Any,
) -> Any:
    _, telegram_user_id = _message_context(
        callback_query
    )

    if telegram_user_id is None:
        return None

    if not await _is_admin(
        env,
        telegram_user_id,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text="⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return None

    user_id = await _ensure_user(
        telegram_user_id
    )

    await clear_state(
        backend,
        user_id,
    )

    data = callback_query.get("data") or ""
    parts = data.split(":")

    if len(parts) != 2:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return None

    try:
        page = int(parts[1])
    except (TypeError, ValueError):
        page = -1

    if page < 0:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ صفحه نامعتبر است.",
            show_alert=True,
        )
        return None

    total_row = await backend.fetchone(
        "SELECT COUNT(*) AS total FROM users;"
    )

    total = int(
        (total_row or {}).get("total") or 0
    )

    offset = page * PAGE_SIZE

    rows = await backend.fetchall(
        """
        SELECT *
        FROM users
        ORDER BY id DESC
        LIMIT ? OFFSET ?;
        """,
        (
            PAGE_SIZE,
            offset,
        ),
    )

    has_previous = page > 0
    has_next = (
        offset + PAGE_SIZE < total
    )

    keyboard_rows: list[list[dict[str, Any]]] = []

    for row in rows:
        keyboard_rows.append(
            [
                _button(
                    f"👤 {_html(_user_label(row))}",
                    f"adminuserview:{row['id']}",
                )
            ]
        )

    if total:
        keyboard_rows.append(
            _pagination_row(
                "adminuserlist",
                page,
                has_previous,
                has_next,
            )
        )

    keyboard_rows.append(
        _back_row("adminusers")
    )

    if not total:
        text = "📋 هنوز کاربری ثبت نشده."
    else:
        text = (
            f"📋 <b>همه کاربران</b> "
            f"({total} نفر)"
        )

    await _edit_callback(
        telegram,
        callback_query,
        text,
        _keyboard(keyboard_rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )

    return None


async def handle_admin_user_view(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
    env: Any,
) -> Any:
    _, telegram_user_id = _message_context(
        callback_query
    )

    if telegram_user_id is None:
        return None

    if not await _is_admin(
        env,
        telegram_user_id,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text="⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return None

    data = callback_query.get("data") or ""
    parts = data.split(":")

    if len(parts) != 2:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return None

    try:
        target_user_id = int(parts[1])
    except (TypeError, ValueError):
        target_user_id = 0

    if target_user_id < 1:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ شناسه کاربر نامعتبر است.",
            show_alert=True,
        )
        return None

    user = await backend.fetchone(
        """
        SELECT *
        FROM users
        WHERE id = ?
        LIMIT 1;
        """,
        (target_user_id,),
    )

    if user is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر پیدا نشد.",
            show_alert=True,
        )
        return None

    seller_count_row = await backend.fetchone(
        """
        SELECT COUNT(*) AS total
        FROM sellers
        WHERE owner_user_id = ?
           OR created_by_user_id = ?;
        """,
        (
            target_user_id,
            target_user_id,
        ),
    )

    favorite_count_row = await backend.fetchone(
        """
        SELECT COUNT(*) AS total
        FROM favorites
        WHERE user_id = ?;
        """,
        (target_user_id,),
    )

    request_count_row = await backend.fetchone(
        """
        SELECT COUNT(*) AS total
        FROM requests
        WHERE user_id = ?;
        """,
        (target_user_id,),
    )

    seller_count = int(
        (seller_count_row or {}).get("total") or 0
    )

    favorite_count = int(
        (favorite_count_row or {}).get("total") or 0
    )

    request_count = int(
        (request_count_row or {}).get("total") or 0
    )

    name = _user_label(user)

    username = user.get("username")
    city_id = user.get("city_id")
    active_mode = (
        user.get("active_mode")
        or "buyer"
    )

    city_name = None

    if city_id is not None:
        city = await backend.fetchone(
            """
            SELECT name
            FROM cities
            WHERE id = ?
            LIMIT 1;
            """,
            (city_id,),
        )

        if city:
            city_name = city.get("name")

    lines = [
        "👤 <b>اطلاعات کاربر</b>",
        "",
        f"نام: {_html(name)}",
        f"Telegram ID: {_html(user.get('telegram_id'))}",
    ]

    if username:
        lines.append(
            f"Username: @{_html(username)}"
        )

    if city_name:
        lines.append(
            f"شهر: {_html(city_name)}"
        )

    lines.extend(
        [
            f"حالت فعلی: {_html(active_mode)}",
            f"فروشگاه‌ها: {seller_count}",
            f"علاقه‌مندی‌ها: {favorite_count}",
            f"درخواست‌ها: {request_count}",
            f"تاریخ عضویت: {_html(user.get('created_at'))}",
        ]
    )

    keyboard = _keyboard(
        [
            _back_row("adminusers"),
        ]
    )

    await _edit_callback(
        telegram,
        callback_query,
        "\n".join(lines),
        keyboard,
    )

    await _answer_callback(
        telegram,
        callback_query,
    )

    return None


async def _get_state_for_user(
    user_id: int,
) -> Optional[dict[str, Any]]:
    row = await backend.fetchone(
        """
        SELECT state, data, updated_at
        FROM worker_states
        WHERE user_id = ?
        LIMIT 1;
        """,
        (user_id,),
    )

    if row is None:
        return None

    data = row.get("data")

    if isinstance(data, dict):
        state_data = data
    else:
        import json

        try:
            state_data = json.loads(
                data or "{}"
            )
        except (
            TypeError,
            ValueError,
        ):
            state_data = {}

    return {
        "state": row.get("state"),
        "data": state_data,
        "updated_at": row.get("updated_at"),
    }


async def handle_admin_request_decision(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
    env: Any,
) -> Any:
    """
    Generic admin request decision handler.

    Support requests are handled here because they are not
    advertisement requests.

    Advertisement requests are delegated to the existing
    advertisement decision handler so their current behavior
    remains unchanged.
    """

    _, telegram_user_id = _message_context(
        callback_query
    )

    if telegram_user_id is None:
        return None

    if not await _is_admin(
        env,
        telegram_user_id,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text="⛔️ این عملیات فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return None

    data = str(
        callback_query.get("data")
        or ""
    )

    parts = data.split(":")

    if len(parts) != 3:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return None

    _, action, request_id_raw = parts

    if action not in (
        "approve",
        "reject",
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ عملیات نامعتبر است.",
            show_alert=True,
        )
        return None

    try:
        request_id = int(request_id_raw)
    except (
        TypeError,
        ValueError,
    ):
        request_id = 0

    if request_id < 1:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ شناسه درخواست نامعتبر است.",
            show_alert=True,
        )
        return None

    request = await backend.fetchone(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        LIMIT 1;
        """,
        (request_id,),
    )

    if request is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ این درخواست یافت نشد.",
            show_alert=True,
        )
        return None

    if request.get("status") != "PENDING":
        status = request.get("status") or "UNKNOWN"

        await _answer_callback(
            telegram,
            callback_query,
            (
                "⚠️ این درخواست قبلاً تعیین‌تکلیف شده: "
                f"{_html(status)}"
            ),
            show_alert=True,
        )
        return None

    request_type = str(
        request.get("request_type")
        or ""
    ).strip().lower()

    if request_type in (
        "ad",
        "general_ad",
    ):
        from worker.admin_ads import (
            handle_admin_ad_decision,
        )

        return await handle_admin_ad_decision(
            db=backend,
            telegram=telegram,
            callback_query=callback_query,
            env=env,
        )

    admin_user_id = await _ensure_user(
        telegram_user_id,
        username=(
            callback_query.get("from") or {}
        ).get("username"),
        first_name=(
            callback_query.get("from") or {}
        ).get("first_name"),
        last_name=(
            callback_query.get("from") or {}
        ).get("last_name"),
    )

    new_status = (
        "APPROVED"
        if action == "approve"
        else "REJECTED"
    )

    result = await backend.execute(
        """
        UPDATE requests
        SET
            status = ?,
            updated_at = ?
        WHERE id = ?
          AND status = 'PENDING';
        """,
        (
            new_status,
            _now_iso(),
            request_id,
        ),
    )

    if getattr(
        result,
        "rowcount",
        0,
    ) != 1:
        current = await backend.fetchone(
            """
            SELECT status
            FROM requests
            WHERE id = ?
            LIMIT 1;
            """,
            (request_id,),
        )

        if current is None:
            await _answer_callback(
                telegram,
                callback_query,
                "⚠️ این درخواست دیگر یافت نشد.",
                show_alert=True,
            )
        else:
            await _answer_callback(
                telegram,
                callback_query,
                (
                    "⚠️ این درخواست قبلاً "
                    "تعیین‌تکلیف شده است."
                ),
                show_alert=True,
            )

        return None

    await backend.execute(
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
            admin_user_id,
            (
                "request_approved"
                if action == "approve"
                else "request_rejected"
            ),
            "request",
            request_id,
            None,
            _now_iso(),
        ),
    )

    if request_type == "support":
        if action == "approve":
            notification_title = "درخواست پشتیبانی"
            notification_message = (
                "✅ درخواست پشتیبانی‌ات تأیید شد. "
                "تیم ارزانکده به‌زودی باهات در ارتباط خواهد بود."
            )
        else:
            notification_title = "درخواست پشتیبانی"
            notification_message = (
                "درخواست پشتیبانی‌ات بررسی شد. "
                "اگر همچنان مشکل داری، دوباره از منو درخواست بده."
            )

        await backend.execute(
            """
            INSERT INTO notifications (
                user_id,
                title,
                message,
                notification_type,
                is_read,
                created_at
            )
            VALUES (?, ?, ?, ?, 0, ?);
            """,
            (
                request["user_id"],
                notification_title,
                notification_message,
                "support",
                _now_iso(),
            ),
        )

    await _answer_callback(
        telegram,
        callback_query,
        f"وضعیت درخواست #{request_id} به‌روزرسانی شد.",
    )

    message = callback_query.get("message") or {}
    current_text = str(
        message.get("text")
        or ""
    ).strip()

    status_label = (
        "تأیید شد"
        if new_status == "APPROVED"
        else "رد شد"
    )

    updated_text = (
        f"{current_text}\n\n"
        f"— تصمیم ثبت شد: {status_label}"
        if current_text
        else
        (
            f"درخواست #{request_id}\n\n"
            f"— تصمیم ثبت شد: {status_label}"
        )
    )

    try:
        await _edit_callback(
            telegram,
            callback_query,
            updated_text,
            None,
        )
    except Exception:
        pass

    return None


__all__ = [
    "handle_admin_home",
    "handle_admin_users_menu",
    "handle_admin_user_search_start",
    "handle_admin_user_search_message",
    "handle_admin_user_list",
    "handle_admin_user_view",
    "handle_admin_request_decision",
]