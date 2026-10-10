# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Report flow for Cloudflare Workers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Optional

from worker.state import clear_state, get_state, set_state
from worker.telegram import TelegramClient
from worker_backend.backend import backend


REPORT_STATE = "report:waiting_description"

REPORT_REASONS = {
    "scam": "🚨 کلاهبرداری",
    "wrong_info": "ℹ️ اطلاعات اشتباه",
    "inappropriate": "🚫 محتوای نامناسب",
    "illegal": "⚠️ فروش کالای غیرمجاز",
    "other": "📝 سایر",
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


def _get_callback_telegram_id(
    callback_query: dict[str, Any],
) -> Optional[int]:
    user = callback_query.get("from")

    if not isinstance(user, dict):
        return None

    try:
        telegram_id = int(user.get("id"))
    except (TypeError, ValueError):
        return None

    if telegram_id < 1:
        return None

    return telegram_id


def _get_message_telegram_id(
    message: dict[str, Any],
) -> Optional[int]:
    user = message.get("from")

    if not isinstance(user, dict):
        return None

    try:
        telegram_id = int(user.get("id"))
    except (TypeError, ValueError):
        return None

    if telegram_id < 1:
        return None

    return telegram_id


def _get_callback_message(
    callback_query: dict[str, Any],
) -> Optional[dict[str, Any]]:
    message = callback_query.get("message")

    if not isinstance(message, dict):
        return None

    return message


def _get_callback_chat_id(
    callback_query: dict[str, Any],
) -> Optional[int]:
    message = _get_callback_message(
        callback_query
    )

    if message is None:
        return None

    chat = message.get("chat")

    if not isinstance(chat, dict):
        return None

    try:
        chat_id = int(chat.get("id"))
    except (TypeError, ValueError):
        return None

    return chat_id


def _get_message_chat_id(
    message: dict[str, Any],
) -> Optional[int]:
    chat = message.get("chat")

    if not isinstance(chat, dict):
        return None

    try:
        chat_id = int(chat.get("id"))
    except (TypeError, ValueError):
        return None

    return chat_id


def _get_callback_query_id(
    callback_query: dict[str, Any],
) -> Optional[str]:
    callback_query_id = callback_query.get("id")

    if callback_query_id is None:
        return None

    value = str(
        callback_query_id
    ).strip()

    return value or None


async def _answer_callback(
    telegram: TelegramClient,
    callback_query: dict[str, Any],
    *,
    text: Optional[str] = None,
    show_alert: bool = False,
) -> None:
    callback_query_id = _get_callback_query_id(
        callback_query
    )

    if callback_query_id is None:
        return

    await telegram.answer_callback_query(
        callback_query_id,
        text=text,
        show_alert=show_alert,
    )


async def _edit_callback_message(
    telegram: TelegramClient,
    callback_query: dict[str, Any],
    text: str,
    reply_markup: Optional[dict[str, Any]] = None,
) -> None:
    message = _get_callback_message(
        callback_query
    )

    if message is None:
        return

    chat = message.get("chat")

    if not isinstance(chat, dict):
        return

    chat_id = chat.get("id")
    message_id = message.get("message_id")

    if (
        chat_id is None
        or message_id is None
    ):
        return

    try:
        chat_id = int(chat_id)
        message_id = int(message_id)
    except (
        TypeError,
        ValueError,
    ):
        return

    await telegram.edit_message_text(
        chat_id,
        message_id,
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


async def _get_internal_user_id(
    telegram_id: int,
) -> Optional[int]:
    row = await backend.fetchone(
        """
        SELECT id
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (
            telegram_id,
        ),
    )

    if row is None:
        return None

    try:
        user_id = int(
            row["id"]
        )
    except (
        TypeError,
        ValueError,
        KeyError,
    ):
        return None

    if user_id < 1:
        return None

    return user_id


async def _is_admin(
    telegram_id: int,
    env: Any,
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
            telegram_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return False


def _parse_report_target(
    callback_data: str,
) -> Optional[tuple[str, int]]:
    parts = callback_data.split(":")

    if len(parts) != 3:
        return None

    if parts[0] != "report":
        return None

    target_type = parts[1]

    if target_type not in {
        "seller",
        "product",
    }:
        return None

    try:
        target_id = int(
            parts[2]
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if target_id < 1:
        return None

    return target_type, target_id


def _parse_report_reason(
    callback_data: str,
) -> Optional[tuple[str, int, str]]:
    parts = callback_data.split(":")

    if len(parts) != 4:
        return None

    if parts[0] != "reportreason":
        return None

    target_type = parts[1]

    if target_type not in {
        "seller",
        "product",
    }:
        return None

    try:
        target_id = int(
            parts[2]
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if target_id < 1:
        return None

    reason_code = parts[3]

    if reason_code not in REPORT_REASONS:
        return None

    return (
        target_type,
        target_id,
        reason_code,
    )


async def _target_exists(
    target_type: str,
    target_id: int,
) -> bool:
    if target_type == "seller":
        row = await backend.fetchone(
            """
            SELECT id
            FROM sellers
            WHERE id = ?
            LIMIT 1;
            """,
            (
                target_id,
            ),
        )
        return row is not None

    if target_type == "product":
        row = await backend.fetchone(
            """
            SELECT id
            FROM products
            WHERE id = ?
            LIMIT 1;
            """,
            (
                target_id,
            ),
        )
        return row is not None

    return False


async def _has_open_report(
    user_id: int,
    target_type: str,
    target_id: int,
) -> bool:
    if target_type == "seller":
        row = await backend.fetchone(
            """
            SELECT 1
            FROM reports
            WHERE user_id = ?
              AND seller_id = ?
              AND status = 'PENDING'
            LIMIT 1;
            """,
            (
                user_id,
                target_id,
            ),
        )
        return row is not None

    if target_type == "product":
        row = await backend.fetchone(
            """
            SELECT 1
            FROM reports
            WHERE user_id = ?
              AND product_id = ?
              AND status = 'PENDING'
            LIMIT 1;
            """,
            (
                user_id,
                target_id,
            ),
        )
        return row is not None

    return False


def _report_reason_keyboard(
    target_type: str,
    target_id: int,
) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []

    for code, label in REPORT_REASONS.items():
        rows.append(
            [
                {
                    "text": label,
                    "callback_data": (
                        f"reportreason:"
                        f"{target_type}:"
                        f"{target_id}:"
                        f"{code}"
                    ),
                }
            ]
        )

    rows.append(
        [
            {
                "text": "↩️ بازگشت",
                "callback_data": (
                    f"{target_type}:{target_id}"
                ),
            }
        ]
    )

    return {
        "inline_keyboard": rows,
    }


def _report_description_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "رد کردن توضیحات",
                    "callback_data": "reportskip",
                }
            ]
        ],
    }


async def _notify_admin_new_report(
    telegram: TelegramClient,
    env: Any,
    report_id: int,
    user_id: int,
    target_type: str,
    target_id: int,
    reason_code: str,
    description: Optional[str],
) -> None:
    """
    Send a newly saved report to the configured admin.

    A notification failure must never undo or hide the saved report.
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

    try:
        user = await backend.fetchone(
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
            (
                user_id,
            ),
        )

        if user is None:
            reporter_label = (
                f"کاربر داخلی #{user_id}"
            )
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

            if username and full_name:
                reporter_label = (
                    f"{full_name} (@{username})"
                )
            elif username:
                reporter_label = f"@{username}"
            elif full_name:
                reporter_label = full_name
            else:
                reporter_label = (
                    f"کاربر داخلی #{user_id}"
                )

            telegram_id = user.get(
                "telegram_id"
            )

            if telegram_id is not None:
                reporter_label += (
                    f" | Telegram ID: {telegram_id}"
                )

        target_label = (
            "فروشگاه"
            if target_type == "seller"
            else "محصول"
        )

        reason_label = REPORT_REASONS.get(
            reason_code,
            reason_code,
        )

        description_text = (
            description.strip()
            if isinstance(description, str)
            and description.strip()
            else "—"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "🟢 تأیید گزارش",
                        "callback_data": (
                            f"adminreport:approve:{report_id}"
                        ),
                    },
                    {
                        "text": "🔴 رد گزارش",
                        "callback_data": (
                            f"adminreport:reject:{report_id}"
                        ),
                    },
                ],
            ],
        }

        text = (
            "🚨 <b>گزارش جدید</b>\n\n"
            f"شناسه گزارش: <b>#{report_id}</b>\n"
            f"نوع مورد: {_html(target_label)}\n"
            f"شناسه مورد: <b>#{target_id}</b>\n"
            f"دلیل: {_html(reason_label)}\n"
            f"توضیحات: {_html(description_text)}\n"
            f"گزارش‌دهنده: {_html(reporter_label)}\n"
            f"شناسه داخلی کاربر: <code>{user_id}</code>"
        )

        await telegram.send_message(
            admin_chat_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    except Exception:
        # The report is already saved.
        # Admin notification errors must not break the user flow.
        return


async def handle_report_start(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
) -> bool:
    callback_data = callback_query.get("data")

    if not isinstance(
        callback_data,
        str,
    ):
        return False

    parsed = _parse_report_target(
        callback_data
    )

    if parsed is None:
        return False

    target_type, target_id = parsed

    telegram_id = _get_callback_telegram_id(
        callback_query
    )

    chat_id = _get_callback_chat_id(
        callback_query
    )

    callback_query_id = _get_callback_query_id(
        callback_query
    )

    if (
        telegram_id is None
        or chat_id is None
    ):
        return False

    if callback_query_id is not None:
        await telegram.answer_callback_query(
            callback_query_id
        )

    user_id = await _get_internal_user_id(
        telegram_id
    )

    if user_id is None:
        await telegram.send_message(
            chat_id,
            "حساب کاربری پیدا نشد. اول /start رو بزن.",
        )
        return True

    if not await _target_exists(
        target_type,
        target_id,
    ):
        await telegram.send_message(
            chat_id,
            "این مورد پیدا نشد.",
        )
        return True

    if await _has_open_report(
        user_id,
        target_type,
        target_id,
    ):
        await telegram.send_message(
            chat_id,
            "گزارش قبلی شما برای همین مورد هنوز در حال بررسی است.",
        )
        return True

    await clear_state(
        backend,
        user_id,
    )

    await telegram.send_message(
        chat_id,
        "دلیل گزارش رو انتخاب کن:",
        reply_markup=_report_reason_keyboard(
            target_type,
            target_id,
        ),
    )

    return True


async def handle_report_reason(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
) -> bool:
    callback_data = callback_query.get("data")

    if not isinstance(
        callback_data,
        str,
    ):
        return False

    parsed = _parse_report_reason(
        callback_data
    )

    if parsed is None:
        return False

    target_type, target_id, reason_code = parsed

    telegram_id = _get_callback_telegram_id(
        callback_query
    )

    chat_id = _get_callback_chat_id(
        callback_query
    )

    callback_query_id = _get_callback_query_id(
        callback_query
    )

    if (
        telegram_id is None
        or chat_id is None
    ):
        return False

    if callback_query_id is not None:
        await telegram.answer_callback_query(
            callback_query_id
        )

    user_id = await _get_internal_user_id(
        telegram_id
    )

    if user_id is None:
        await telegram.send_message(
            chat_id,
            "حساب کاربری پیدا نشد. اول /start رو بزن.",
        )
        return True

    if not await _target_exists(
        target_type,
        target_id,
    ):
        await clear_state(
            backend,
            user_id,
        )
        await telegram.send_message(
            chat_id,
            "این مورد دیگه پیدا نشد. دوباره گزارش رو شروع کن.",
        )
        return True

    if await _has_open_report(
        user_id,
        target_type,
        target_id,
    ):
        await clear_state(
            backend,
            user_id,
        )
        await telegram.send_message(
            chat_id,
            "گزارش قبلی شما برای همین مورد هنوز در حال بررسی است.",
        )
        return True

    await set_state(
        backend,
        user_id,
        REPORT_STATE,
        {
            "target_type": target_type,
            "target_id": target_id,
            "reason_code": reason_code,
        },
    )

    await telegram.send_message(
        chat_id,
        "اگر توضیح بیشتری داری بنویس، یا رد کن:",
        reply_markup=_report_description_keyboard(),
    )

    return True


async def _complete_report(
    user_id: int,
    data: dict[str, Any],
    description: Optional[str],
) -> int:
    target_type = data.get(
        "target_type"
    )

    target_id = data.get(
        "target_id"
    )

    reason_code = data.get(
        "reason_code"
    )

    if target_type not in {
        "seller",
        "product",
    }:
        raise ValueError(
            "Invalid report target type."
        )

    try:
        target_id = int(
            target_id
        )
    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "Invalid report target id."
        )

    if target_id < 1:
        raise ValueError(
            "Invalid report target id."
        )

    if reason_code not in REPORT_REASONS:
        raise ValueError(
            "Invalid report reason."
        )

    if not await _target_exists(
        target_type,
        target_id,
    ):
        raise ValueError(
            "Report target no longer exists."
        )

    if await _has_open_report(
        user_id,
        target_type,
        target_id,
    ):
        raise ValueError(
            "An open report already exists."
        )

    return await _save_report(
        user_id,
        target_type,
        target_id,
        reason_code,
        description,
    )


async def handle_report_skip(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
) -> bool:
    callback_data = callback_query.get("data")

    if callback_data != "reportskip":
        return False

    telegram_id = _get_callback_telegram_id(
        callback_query
    )

    chat_id = _get_callback_chat_id(
        callback_query
    )

    callback_query_id = _get_callback_query_id(
        callback_query
    )

    if (
        telegram_id is None
        or chat_id is None
    ):
        return False

    if callback_query_id is not None:
        await telegram.answer_callback_query(
            callback_query_id
        )

    user_id = await _get_internal_user_id(
        telegram_id
    )

    if user_id is None:
        await telegram.send_message(
            chat_id,
            "حساب کاربری پیدا نشد. اول /start رو بزن.",
        )
        return True

    state = await get_state(
        backend,
        user_id,
    )

    if state is None:
        await telegram.send_message(
            chat_id,
            "این مرحله منقضی شده. دوباره گزارش رو شروع کن.",
        )
        return True

    if state.get("state") != REPORT_STATE:
        return False

    data = state.get("data")

    if not isinstance(
        data,
        dict,
    ):
        await clear_state(
            backend,
            user_id,
        )
        await telegram.send_message(
            chat_id,
            "اطلاعات گزارش ناقصه. دوباره شروع کن.",
        )
        return True

    try:
        await _complete_report(
            user_id,
            data,
            None,
        )
    except ValueError as exc:
        await clear_state(
            backend,
            user_id,
        )

        if str(exc) == "An open report already exists.":
            await telegram.send_message(
                chat_id,
                "گزارش قبلی شما برای همین مورد هنوز در حال بررسی است.",
            )
        else:
            await telegram.send_message(
                chat_id,
                "اطلاعات گزارش نامعتبر یا منقضی شده. دوباره تلاش کن.",
            )

        return True

    await clear_state(
        backend,
        user_id,
    )

    await telegram.send_message(
        chat_id,
        "گزارش شما ثبت شد. ممنون که به امن‌تر شدن ارزانکده کمک می‌کنی.",
    )

    return True


async def handle_report_text(
    message: dict[str, Any],
    telegram: TelegramClient,
) -> bool:
    telegram_id = _get_message_telegram_id(
        message
    )

    chat_id = _get_message_chat_id(
        message
    )

    if (
        telegram_id is None
        or chat_id is None
    ):
        return False

    text = message.get("text")

    if not isinstance(
        text,
        str,
    ):
        await telegram.send_message(
            chat_id,
            "لطفاً توضیح گزارش رو به صورت پیام متنی بفرست.",
        )
        return True

    description = text.strip()

    if not description:
        await telegram.send_message(
            chat_id,
            "توضیح گزارش نمی‌تونه خالی باشه. یا «رد کردن توضیحات» رو بزن.",
        )
        return True

    user_id = await _get_internal_user_id(
        telegram_id
    )

    if user_id is None:
        await telegram.send_message(
            chat_id,
            "حساب کاربری پیدا نشد. اول /start رو بزن.",
        )
        return True

    state = await get_state(
        backend,
        user_id,
    )

    if state is None:
        await telegram.send_message(
            chat_id,
            "این مرحله منقضی شده. دوباره گزارش رو شروع کن.",
        )
        return True

    if state.get("state") != REPORT_STATE:
        return False

    data = state.get("data")

    if not isinstance(
        data,
        dict,
    ):
        await clear_state(
            backend,
            user_id,
        )
        await telegram.send_message(
            chat_id,
            "اطلاعات گزارش ناقصه. دوباره شروع کن.",
        )
        return True

    try:
        await _complete_report(
            user_id,
            data,
            description,
        )
    except ValueError as exc:
        await clear_state(
            backend,
            user_id,
        )

        if str(exc) == "An open report already exists.":
            await telegram.send_message(
                chat_id,
                "گزارش قبلی شما برای همین مورد هنوز در حال بررسی است.",
            )
        else:
            await telegram.send_message(
                chat_id,
                "اطلاعات گزارش نامعتبر یا منقضی شده. دوباره تلاش کن.",
            )

        return True

    await clear_state(
        backend,
        user_id,
    )

    await telegram.send_message(
        chat_id,
        "گزارش شما ثبت شد. ممنون که به امن‌تر شدن ارزانکده کمک می‌کنی.",
    )

    return True


async def handle_admin_report_decision(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
    env: Any,
) -> bool:
    """
    Admin-only approval/rejection handler for reports.

    Supported callbacks:
    - adminreport:approve:<report_id>
    - adminreport:reject:<report_id>
    """

    callback_data = callback_query.get("data")

    if not isinstance(
        callback_data,
        str,
    ):
        return False

    parts = callback_data.split(":")

    if len(parts) != 3:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return True

    prefix, action, report_id_raw = parts

    if prefix != "adminreport":
        return False

    if action not in {
        "approve",
        "reject",
    }:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ عملیات نامعتبر است.",
            show_alert=True,
        )
        return True

    try:
        report_id = int(
            report_id_raw
        )
    except (
        TypeError,
        ValueError,
    ):
        report_id = 0

    if report_id < 1:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ شناسه گزارش نامعتبر است.",
            show_alert=True,
        )
        return True

    telegram_id = _get_callback_telegram_id(
        callback_query
    )

    if telegram_id is None:
        return True

    if not await _is_admin(
        telegram_id,
        env,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text="⛔️ این عملیات فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return True

    admin_user_id = await _get_internal_user_id(
        telegram_id
    )

    if admin_user_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ حساب ادمین پیدا نشد.",
            show_alert=True,
        )
        return True

    report = await backend.fetchone(
        """
        SELECT *
        FROM reports
        WHERE id = ?
        LIMIT 1;
        """,
        (
            report_id,
        ),
    )

    if report is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ این گزارش وجود ندارد.",
            show_alert=True,
        )
        return True

    if report.get("status") != "PENDING":
        status = report.get("status") or "UNKNOWN"

        await _answer_callback(
            telegram,
            callback_query,
            (
                "⚠️ این گزارش قبلاً تعیین‌تکلیف شده: "
                f"{_html(status)}"
            ),
            show_alert=True,
        )
        return True

    new_status = (
        "APPROVED"
        if action == "approve"
        else "REJECTED"
    )

    update_result = await backend.execute(
        """
        UPDATE reports
        SET status = ?
        WHERE id = ?
          AND status = 'PENDING';
        """,
        (
            new_status,
            report_id,
        ),
    )

    # Only the callback that actually changed PENDING may create
    # an audit entry or notify the reporter. A read-after-write status
    # check is insufficient because another concurrent callback may
    # have committed the same requested status first.
    if update_result.rowcount != 1:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ این گزارش قبلاً تعیین‌تکلیف شده است.",
            show_alert=True,
        )
        return True

    audit_action = (
        "report_approved"
        if action == "approve"
        else "report_rejected"
    )

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
            audit_action,
            "report",
            report_id,
            None,
            _now_iso(),
        ),
    )

    if action == "approve":
        notification_title = "نتیجه گزارش شما"
        notification_message = (
            "✅ گزارشت بررسی و تأیید شد. "
            "ممنون که به امن‌تر شدن ارزانکده کمک می‌کنی."
        )
    else:
        notification_title = "نتیجه گزارش شما"
        notification_message = (
            "🚫 گزارشت بررسی شد.\n"
            "بعد از بررسی، مورد گزارش‌شده نیاز به اقدام نداشت."
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
            report["user_id"],
            notification_title,
            notification_message,
            "report",
            _now_iso(),
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
        f"وضعیت گزارش #{report_id} به‌روزرسانی شد.",
    )

    message = _get_callback_message(
        callback_query
    )

    if message is not None:
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
                f"گزارش #{report_id}\n\n"
                f"— تصمیم ثبت شد: {status_label}"
            )
        )

        try:
            await _edit_callback_message(
                telegram,
                callback_query,
                updated_text,
            )
        except Exception:
            pass

    return True


__all__ = [
    "REPORT_REASONS",
    "REPORT_STATE",
    "handle_admin_report_decision",
    "handle_report_reason",
    "handle_report_skip",
    "handle_report_start",
    "handle_report_text",
]