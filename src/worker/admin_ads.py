# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker admin advertising management.

This module intentionally does not import aiogram, sqlite,
aiosqlite, or any legacy bot module.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Optional

from worker.state import clear_state, get_state, set_state


STATE_NAME = "admin_ad_setting"

AD_REQUEST_TYPES = (
    "ad",
    "general_ad",
)

AD_EDITABLE_STATUSES = (
    "PENDING",
    "APPROVED",
)

PAGE_SIZE = 10

STATUS_LABELS = {
    "PENDING": "در انتظار بررسی",
    "APPROVED": "تأیید شده",
    "ACTIVE": "فعال",
    "REJECTED": "رد شده",
    "EXPIRED": "منقضی شده",
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


def _parse_int(value: Any) -> Optional[int]:
    try:
        result = int(
            str(value).strip()
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if result < 1:
        return None

    return result


def _parse_non_negative_int(
    value: Any,
) -> Optional[int]:
    try:
        result = int(
            str(value).strip()
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if result < 0:
        return None

    return result


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
            "🔙 بازگشت",
            callback_data,
        )
    ]


def _callback_context(
    callback_query: dict[str, Any],
) -> tuple[
    Optional[int],
    Optional[int],
]:
    message = (
        callback_query.get("message")
        or {}
    )

    chat = (
        message.get("chat")
        or {}
    )

    user = (
        callback_query.get("from")
        or {}
    )

    chat_id = _parse_int(
        chat.get("id")
    )

    telegram_user_id = _parse_int(
        user.get("id")
    )

    return (
        chat_id,
        telegram_user_id,
    )


def _message_context(
    message: dict[str, Any],
) -> tuple[
    Optional[int],
    Optional[int],
    Optional[str],
]:
    chat = (
        message.get("chat")
        or {}
    )

    user = (
        message.get("from")
        or {}
    )

    chat_id = _parse_int(
        chat.get("id")
    )

    telegram_user_id = _parse_int(
        user.get("id")
    )

    text = message.get("text")

    return (
        chat_id,
        telegram_user_id,
        text,
    )


def _is_admin(
    env: Any,
    telegram_user_id: Optional[int],
) -> bool:
    if telegram_user_id is None:
        return False

    configured = getattr(
        env,
        "ADMIN_CHAT_ID",
        None,
    )

    if configured is None:
        return False

    try:
        return int(configured) == int(
            telegram_user_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return False


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

    return int(
        row["id"]
    )


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
    message = (
        callback_query.get("message")
        or {}
    )

    chat = (
        message.get("chat")
        or {}
    )

    chat_id = _parse_int(
        chat.get("id")
    )

    message_id = _parse_int(
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


async def _send(
    telegram: Any,
    chat_id: int,
    text: str,
    keyboard: Optional[dict[str, Any]] = None,
) -> None:
    await telegram.send_message(
        chat_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def _notify_user(
    db: Any,
    user_id: int,
    title: str,
    message: str,
    notification_type: str = "info",
) -> None:
    await db.execute(
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
            user_id,
            title,
            message,
            notification_type,
            _now_iso(),
        ),
    )


async def _audit(
    db: Any,
    admin_user_id: int,
    action: str,
    target_id: int,
    details: Optional[str] = None,
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
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (
            admin_user_id,
            action,
            "request",
            target_id,
            details,
            _now_iso(),
        ),
    )


async def _get_ad_request(
    db: Any,
    request_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT *
        FROM requests
        WHERE id = ?
          AND request_type IN ('ad', 'general_ad')
        LIMIT 1;
        """,
        (request_id,),
    )


def _status_label(
    status: Any,
) -> str:
    value = str(
        status or ""
    ).upper()

    return STATUS_LABELS.get(
        value,
        value or "نامشخص",
    )


def _request_title(
    request: dict[str, Any],
) -> str:
    return (
        request.get("ad_title")
        or request.get("title")
        or request.get("topic")
        or f"درخواست #{request['id']}"
    )


def _request_description(
    request: dict[str, Any],
) -> str:
    return (
        request.get("message")
        or request.get("description")
        or "—"
    )


def _request_link(
    request: dict[str, Any],
) -> str:
    return (
        request.get("ad_link")
        or request.get("link")
        or "—"
    )


def _request_kind(
    request: dict[str, Any],
) -> str:
    return (
        request.get("ad_kind")
        or request.get("kind")
        or request.get("topic")
        or "—"
    )


async def handle_ads_admin(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    env: Any,
) -> None:
    """
    Admin advertising dashboard.
    Callback:
        adsadmin
    """

    _, telegram_user_id = _callback_context(
        callback_query
    )

    if not _is_admin(
        env,
        telegram_user_id,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text="⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    if telegram_user_id is None:
        return

    user = (
        callback_query.get("from")
        or {}
    )

    admin_user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    await clear_state(
        db,
        admin_user_id,
    )

    pending = await db.fetchone(
        """
        SELECT COUNT(*) AS count
        FROM requests
        WHERE request_type IN ('ad', 'general_ad')
          AND status = 'PENDING';
        """
    )

    active = await db.fetchone(
        """
        SELECT COUNT(*) AS count
        FROM requests
        WHERE request_type IN ('ad', 'general_ad')
          AND status = 'ACTIVE';
        """
    )

    soon_limit = (
        datetime.now(timezone.utc)
        + timedelta(hours=24)
    ).isoformat(
        timespec="seconds"
    )

    soon = await db.fetchone(
        """
        SELECT COUNT(*) AS count
        FROM requests
        WHERE request_type IN ('ad', 'general_ad')
          AND status = 'ACTIVE'
          AND ad_expires_at IS NOT NULL
          AND ad_expires_at <= ?
          AND ad_expires_at > ?;
        """,
        (
            soon_limit,
            _now_iso(),
        ),
    )

    pending_count = int(
        (pending or {}).get(
            "count",
            0,
        )
        or 0
    )

    active_count = int(
        (active or {}).get(
            "count",
            0,
        )
        or 0
    )

    soon_count = int(
        (soon or {}).get(
            "count",
            0,
        )
        or 0
    )

    rows = await db.fetchall(
        """
        SELECT
            r.*,
            u.first_name,
            u.last_name,
            u.username
        FROM requests r
        LEFT JOIN users u
            ON u.id = r.user_id
        WHERE r.request_type IN ('ad', 'general_ad')
        ORDER BY r.id DESC
        LIMIT ?;
        """,
        (PAGE_SIZE,),
    )

    lines = [
        "📢 <b>مدیریت تبلیغات</b>",
        "",
        (
            "📋 در انتظار بررسی: "
            f"{pending_count}"
        ),
        (
            "🟢 تبلیغات فعال: "
            f"{active_count}"
        ),
        (
            "⏰ در حال اتمام: "
            f"{soon_count}"
        ),
        "",
    ]

    if not rows:
        lines.append(
            "📭 هنوز درخواست تبلیغی ثبت نشده."
        )

    keyboard_rows: list[
        list[dict[str, Any]]
    ] = []

    for row in rows:
        title = _request_title(
            row
        )

        keyboard_rows.append(
            [
                _button(
                    (
                        f"📢 #{row['id']} "
                        f"{_html(title)[:35]} — "
                        f"{_html(_status_label(row['status']))}"
                    ),
                    f"adminadview:{row['id']}",
                )
            ]
        )

    keyboard_rows.append(
        _back_button("account")
    )

    await _edit_callback(
        telegram,
        callback_query,
        "\n".join(lines),
        _keyboard(keyboard_rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_admin_ad_view(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    env: Any,
) -> None:
    """
    Advertisement detail.
    Callback:
        adminadview:<request_id>
        adsadmindetail:<request_id>
    """

    _, telegram_user_id = _callback_context(
        callback_query
    )

    if not _is_admin(
        env,
        telegram_user_id,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text="⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    data = str(
        callback_query.get("data")
        or ""
    )

    prefix = None

    if data.startswith(
        "adminadview:"
    ):
        prefix = "adminadview:"

    elif data.startswith(
        "adsadmindetail:"
    ):
        prefix = "adsadmindetail:"

    if prefix is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    request_id = _parse_int(
        data.split(
            ":",
            1,
        )[1]
    )

    if request_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ شناسه تبلیغ نامعتبر است.",
            show_alert=True,
        )
        return

    request = await _get_ad_request(
        db,
        request_id,
    )

    if not request:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست تبلیغ یافت نشد.",
            show_alert=True,
        )
        return

    user = await db.fetchone(
        """
        SELECT *
        FROM users
        WHERE id = ?
        LIMIT 1;
        """,
        (request["user_id"],),
    )

    if not user:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر درخواست‌کننده یافت نشد.",
            show_alert=True,
        )
        return

    name = (
        " ".join(
            filter(
                None,
                [
                    user.get("first_name"),
                    user.get("last_name"),
                ],
            )
        )
        or user.get("username")
        or str(user.get("telegram_id"))
    )

    price = request.get(
        "ad_price"
    )

    duration = request.get(
        "ad_duration_days"
    )

    placement = request.get(
        "ad_placement"
    )

    expires_at = request.get(
        "ad_expires_at"
    )

    price_text = (
        f"{price:,} تومان"
        if price is not None
        else "تعیین‌نشده"
    )

    duration_text = (
        f"{duration} روز"
        if duration
        else "تعیین‌نشده"
    )

    placement_text = (
        str(placement)
        if placement
        else "تعیین‌نشده"
    )

    lines = [
        "📢 <b>جزئیات تبلیغ</b>",
        "",
        f"شماره درخواست: #{request['id']}",
        f"ثبت‌کننده: {_html(name)}",
        f"نوع: {_html(_request_kind(request))}",
        f"عنوان: {_html(_request_title(request))}",
        "",
        "<b>توضیحات:</b>",
        _html(_request_description(request)),
        "",
        f"🔗 لینک: {_html(_request_link(request))}",
        "",
        (
            "وضعیت: "
            f"<b>{_html(_status_label(request['status']))}</b>"
        ),
        f"💰 قیمت: {_html(price_text)}",
        f"⏱ مدت: {_html(duration_text)}",
        f"📍 جایگاه: {_html(placement_text)}",
    ]

    if expires_at:
        lines.append(
            f"⏰ انقضا: {_html(expires_at)}"
        )

    keyboard_rows: list[
        list[dict[str, Any]]
    ] = []

    if request["status"] == "PENDING":
        keyboard_rows.append(
            [
                _button(
                    "✅ تأیید",
                    f"adminaddecision:approve:{request_id}",
                ),
                _button(
                    "❌ رد",
                    f"adminaddecision:reject:{request_id}",
                ),
            ]
        )

    if request["status"] in AD_EDITABLE_STATUSES:
        keyboard_rows.append(
            [
                _button(
                    "💰 تعیین قیمت",
                    f"adminadprice:{request_id}",
                ),
                _button(
                    "⏱ تعیین مدت",
                    f"adminadduration:{request_id}",
                ),
            ]
        )

        keyboard_rows.append(
            [
                _button(
                    "📍 تعیین جایگاه",
                    f"adminadplacement:{request_id}",
                )
            ]
        )

        keyboard_rows.append(
            [
                _button(
                    "💰 قیمت",
                    f"adsetprice:{request_id}",
                ),
                _button(
                    "⏱ مدت",
                    f"adsetduration:{request_id}",
                ),
            ]
        )

        keyboard_rows.append(
            [
                _button(
                    "📍 جایگاه",
                    f"adsetplacement:{request_id}",
                )
            ]
        )

    keyboard_rows.append(
        _back_button("adsadmin")
    )

    await _edit_callback(
        telegram,
        callback_query,
        "\n".join(lines),
        _keyboard(keyboard_rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def _set_ad_value(
    db: Any,
    telegram: Any,
    chat_id: int,
    telegram_user_id: int,
    request_id: int,
    field: str,
    value: Any,
    audit_action: str,
    success_text: str,
) -> None:
    request = await _get_ad_request(
        db,
        request_id,
    )

    if not request:
        await _send(
            telegram,
            chat_id,
            "⚠️ درخواست تبلیغاتی پیدا نشد.",
        )
        return

    if request["status"] not in AD_EDITABLE_STATUSES:
        await _send(
            telegram,
            chat_id,
            (
                "⚠️ این درخواست دیگر قابل تنظیم نیست.\n"
                f"وضعیت فعلی: "
                f"{_html(_status_label(request['status']))}"
            ),
        )
        return

    if field not in {
        "ad_price",
        "ad_duration_days",
        "ad_placement",
    }:
        await _send(
            telegram,
            chat_id,
            "⚠️ فیلد نامعتبر است.",
        )
        return

    if field == "ad_duration_days":
        try:
            duration_days = int(value)
        except (TypeError, ValueError):
            duration_days = 0

        if duration_days < 1:
            await _send(
                telegram,
                chat_id,
                "⚠️ مدت تبلیغ باید حداقل یک روز باشد.",
            )
            return

        value = duration_days
        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(days=duration_days)
        ).isoformat(timespec="seconds")
    else:
        expires_at = None

    admin_user_id = await _ensure_user(
        db,
        telegram_user_id,
    )
    now = _now_iso()

    query = (
        "UPDATE requests "
        f"SET {field} = ?, "
        "updated_at = ? "
        "WHERE id = ? "
        "AND request_type IN ('ad', 'general_ad') "
        "AND status IN ('PENDING', 'APPROVED');"
    )

    async with db.transaction() as tx:
        await tx.execute(
            query,
            (
                value,
                now,
                request_id,
            ),
        )

        await tx.execute(
            """
            INSERT INTO audit_log (
                actor_user_id,
                action,
                entity_type,
                entity_id,
                details,
                created_at
            )
            SELECT ?, ?, 'request', ?, ?, ?
            WHERE changes() = 1;
            """,
            (
                admin_user_id,
                audit_action,
                request_id,
                str(value),
                now,
            ),
        )

        if field == "ad_duration_days":
            await tx.execute(
                """
                UPDATE requests
                SET
                    status = 'ACTIVE',
                    ad_expires_at = ?,
                    updated_at = ?
                WHERE id = ?
                  AND status = 'APPROVED'
                  AND request_type IN ('ad', 'general_ad')
                  AND changes() = 1;
                """,
                (
                    expires_at,
                    now,
                    request_id,
                ),
            )

            await tx.execute(
                """
                INSERT INTO notifications (
                    user_id,
                    title,
                    message,
                    notification_type,
                    is_read,
                    created_at
                )
                SELECT ?, ?, ?, 'info', 0, ?
                WHERE changes() = 1;
                """,
                (
                    request["user_id"],
                    (
                        "تبلیغ در ارزانکده"
                        if request["request_type"] == "general_ad"
                        else "درخواست تبلیغات"
                    ),
                    (
                        "✅ تبلیغت فعال شد و برای "
                        f"{value} روز نمایش داده می‌شه."
                    ),
                    now,
                ),
            )

    results = tx.results

    if not results or getattr(
        results[0],
        "rowcount",
        0,
    ) != 1:
        await _send(
            telegram,
            chat_id,
            "⚠️ تغییر انجام نشد؛ وضعیت درخواست احتمالاً عوض شده.",
        )
        return

    await _send(
        telegram,
        chat_id,
        success_text,
    )


async def _start_setting(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    env: Any,
    field: str,
    prompt: str,
) -> None:
    _, telegram_user_id = _callback_context(
        callback_query
    )

    if not _is_admin(
        env,
        telegram_user_id,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text="⛔️ این عملیات فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    if telegram_user_id is None:
        return

    data = str(
        callback_query.get("data")
        or ""
    )

    request_id = _parse_int(
        data.split(
            ":",
            1,
        )[1]
        if ":" in data
        else None
    )

    if request_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    request = await _get_ad_request(
        db,
        request_id,
    )

    if not request:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست تبلیغاتی یافت نشد.",
            show_alert=True,
        )
        return

    if request["status"] not in AD_EDITABLE_STATUSES:
        await _answer_callback(
            telegram,
            callback_query,
            text=(
                "⚠️ این درخواست دیگر قابل تنظیم نیست."
            ),
            show_alert=True,
        )
        return

    user = (
        callback_query.get("from")
        or {}
    )

    admin_user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    await set_state(
        db,
        admin_user_id,
        STATE_NAME,
        {
            "request_id": request_id,
            "field": field,
        },
    )

    chat_id, _ = _callback_context(
        callback_query
    )

    if chat_id is not None:
        await _send(
            telegram,
            chat_id,
            prompt,
        )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_admin_ad_price_start(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    env: Any,
) -> None:
    await _start_setting(
        db,
        telegram,
        callback_query,
        env,
        "ad_price",
        "💰 قیمت رو به تومان بفرست (فقط عدد):",
    )


async def handle_admin_ad_duration_start(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    env: Any,
) -> None:
    await _start_setting(
        db,
        telegram,
        callback_query,
        env,
        "ad_duration_days",
        "⏱ مدت نمایش رو به روز بفرست (فقط عدد):",
    )


async def handle_admin_ad_placement_start(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    env: Any,
) -> None:
    await _start_setting(
        db,
        telegram,
        callback_query,
        env,
        "ad_placement",
        "📍 محل نمایش رو بنویس؛ مثلاً «صفحه اصلی» یا «نتایج جستجو»:",
    )


async def handle_admin_ad_message(
    db: Any,
    telegram: Any,
    message: dict[str, Any],
    env: Any,
) -> bool:
    """
    Handles admin text input for ad price, duration and placement.

    Returns True when the message belongs to the admin-ad flow.
    """

    chat_id, telegram_user_id, text = _message_context(
        message
    )

    if (
        chat_id is None
        or telegram_user_id is None
    ):
        return False

    if not _is_admin(
        env,
        telegram_user_id,
    ):
        return False

    admin_user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=(
            message.get("from") or {}
        ).get("username"),
        first_name=(
            message.get("from") or {}
        ).get("first_name"),
        last_name=(
            message.get("from") or {}
        ).get("last_name"),
    )

    current = await get_state(
        db,
        admin_user_id,
    )

    if (
        current is None
        or current.get("state") != STATE_NAME
    ):
        return False

    state_data = dict(
        current.get("data") or {}
    )

    request_id = _parse_int(
        state_data.get("request_id")
    )

    field = state_data.get(
        "field"
    )

    if (
        request_id is None
        or field not in {
            "ad_price",
            "ad_duration_days",
            "ad_placement",
        }
    ):
        await clear_state(
            db,
            admin_user_id,
        )

        await _send(
            telegram,
            chat_id,
            "⚠️ وضعیت این فرم نامعتبر شده. دوباره وارد مدیریت تبلیغات شو.",
        )

        return True

    value_text = (
        text or ""
    ).strip()

    if field == "ad_price":
        value = _parse_non_negative_int(
            value_text.replace(
                ",",
                "",
            )
        )

        if value is None:
            await _send(
                telegram,
                chat_id,
                "⚠️ لطفاً فقط عدد قیمت رو بفرست.",
            )
            return True

        success_text = (
            f"✅ قیمت درخواست #{request_id} ثبت شد: "
            f"{value:,} تومان"
        )

        audit_action = "ad_price_set"

    elif field == "ad_duration_days":
        value = _parse_int(
            value_text
        )

        if value is None:
            await _send(
                telegram,
                chat_id,
                "⚠️ لطفاً تعداد روز معتبر بفرست؛ مثلاً 7.",
            )
            return True

        success_text = (
            f"✅ مدت درخواست #{request_id} ثبت شد: "
            f"{value} روز"
        )

        audit_action = "ad_duration_set"

    else:
        if not value_text:
            await _send(
                telegram,
                chat_id,
                "⚠️ لطفاً محل نمایش رو وارد کن.",
            )
            return True

        if len(value_text) > 200:
            await _send(
                telegram,
                chat_id,
                "⚠️ محل نمایش خیلی طولانیه؛ حداکثر ۲۰۰ کاراکتر.",
            )
            return True

        value = value_text

        success_text = (
            f"✅ محل نمایش درخواست #{request_id} ثبت شد: "
            f"{_html(value)}"
        )

        audit_action = "ad_placement_set"

    await clear_state(
        db,
        admin_user_id,
    )

    await _set_ad_value(
        db,
        telegram,
        chat_id,
        telegram_user_id,
        request_id,
        field,
        value,
        audit_action,
        success_text,
    )

    return True


async def handle_admin_ad_decision(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    env: Any,
) -> None:
    """
    Approve/reject advertisement requests with atomic database writes.

    Supports:
        adminaddecision:approve:<id>
        adminaddecision:reject:<id>
        adminreq:approve:<id>
    """

    _, telegram_user_id = _callback_context(
        callback_query
    )

    if not _is_admin(
        env,
        telegram_user_id,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text="⛔️ این عملیات فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    data = str(
        callback_query.get("data")
        or ""
    )

    if data.startswith("adminaddecision:"):
        payload = data.split(":", 2)
    elif data.startswith("adminreq:"):
        payload = data.split(":", 2)
    else:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    if len(payload) != 3:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    _, action, request_id_raw = payload

    if action not in ("approve", "reject"):
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ عملیات نامعتبر است.",
            show_alert=True,
        )
        return

    request_id = _parse_int(request_id_raw)

    if request_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ شناسه درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    request = await _get_ad_request(
        db,
        request_id,
    )

    if not request:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست تبلیغاتی یافت نشد.",
            show_alert=True,
        )
        return

    if request["status"] != "PENDING":
        await _answer_callback(
            telegram,
            callback_query,
            text=(
                "⚠️ این درخواست قبلاً تعیین‌تکلیف شده: "
                f"{_status_label(request['status'])}"
            ),
            show_alert=True,
        )
        return

    if telegram_user_id is None:
        return

    admin_user = callback_query.get("from") or {}

    admin_user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=admin_user.get("username"),
        first_name=admin_user.get("first_name"),
        last_name=admin_user.get("last_name"),
    )

    now = _now_iso()
    expires_at = None

    if action == "reject":
        new_status = "REJECTED"
        audit_action = "request_rejected"

        notification_message = (
            "تبلیغت فعلاً امکان‌پذیر نیست. "
            "برای جزئیات بیشتر با پشتیبانی در ارتباط باش."
        )

    elif request.get("ad_duration_days"):
        new_status = "ACTIVE"
        audit_action = "request_approved"

        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(
                days=int(
                    request["ad_duration_days"]
                )
            )
        ).isoformat(
            timespec="seconds"
        )

        notification_message = (
            "✅ تبلیغت تأیید شد و "
            f"برای {request['ad_duration_days']} روز فعال می‌مونه."
        )

    else:
        new_status = "APPROVED"
        audit_action = "request_approved"

        notification_message = (
            "✅ درخواست تبلیغاتت تأیید شد. "
            "تیم ارزانکده برای هماهنگی قیمت و پرداخت "
            "باهات تماس می‌گیره."
        )

    title = (
        "تبلیغ در ارزانکده"
        if request["request_type"] == "general_ad"
        else "درخواست تبلیغات"
    )

    # Queue the guarded update, audit record, and notification
    # in one D1 transaction. The conditional INSERT statements
    # depend on the immediately preceding statement's changes().
    async with db.transaction() as tx:
        if new_status == "ACTIVE":
            await tx.execute(
                """
                UPDATE requests
                SET
                    status = 'ACTIVE',
                    ad_expires_at = ?,
                    updated_at = ?
                WHERE id = ?
                  AND status = 'PENDING'
                  AND request_type IN ('ad', 'general_ad');
                """,
                (
                    expires_at,
                    now,
                    request_id,
                ),
            )
        else:
            await tx.execute(
                """
                UPDATE requests
                SET
                    status = ?,
                    updated_at = ?
                WHERE id = ?
                  AND status = 'PENDING'
                  AND request_type IN ('ad', 'general_ad');
                """,
                (
                    new_status,
                    now,
                    request_id,
                ),
            )

        await tx.execute(
            """
            INSERT INTO audit_log (
                actor_user_id,
                action,
                entity_type,
                entity_id,
                details,
                created_at
            )
            SELECT ?, ?, 'request', ?, ?, ?
            WHERE changes() = 1;
            """,
            (
                admin_user_id,
                audit_action,
                request_id,
                new_status,
                now,
            ),
        )

        await tx.execute(
            """
            INSERT INTO notifications (
                user_id,
                title,
                message,
                notification_type,
                is_read,
                created_at
            )
            SELECT ?, ?, ?, 'info', 0, ?
            WHERE changes() = 1;
            """,
            (
                request["user_id"],
                title,
                notification_message,
                now,
            ),
        )

    statement_results = tx.results

    update_result = (
        statement_results[0]
        if statement_results
        else None
    )

    if (
        update_result is None
        or update_result.rowcount != 1
    ):
        current = await _get_ad_request(
            db,
            request_id,
        )

        await _answer_callback(
            telegram,
            callback_query,
            (
                "⚠️ وضعیت درخواست تغییر کرده است."
                if current
                else "⚠️ درخواست دیگر یافت نشد."
            ),
            show_alert=True,
        )
        return

    await _answer_callback(
        telegram,
        callback_query,
        f"وضعیت درخواست #{request_id} به‌روزرسانی شد.",
    )

    await handle_admin_ad_view(
        db,
        telegram,
        {
            **callback_query,
            "data": f"adminadview:{request_id}",
        },
        env,
    )


__all__ = [
    "handle_ads_admin",
    "handle_admin_ad_view",
    "handle_admin_ad_price_start",
    "handle_admin_ad_duration_start",
    "handle_admin_ad_placement_start",
    "handle_admin_ad_message",
    "handle_admin_ad_decision",
]