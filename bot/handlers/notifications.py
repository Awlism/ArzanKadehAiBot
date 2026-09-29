# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Notification handlers
"""

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..backend import backend
from ..keyboards import kb_add_back
from ..utils import ensure_user, parse_int, safe_edit


router = Router(name="notifications")


# ======================================================================
# NOTIFICATIONS
# ======================================================================

@router.callback_query(F.data == "notifications")
async def handle_notifications(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await _render_notifications(callback)


async def _render_notifications(
    callback: CallbackQuery,
    answer_text: str | None = None,
) -> None:
    user_id = await ensure_user(
        callback.from_user
    )

    rows = await backend.fetchall(
        """
        SELECT *
        FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 20;
        """,
        (user_id,),
    )

    if not rows:
        builder = InlineKeyboardBuilder()

        kb_add_back(
            builder,
            "main",
        )

        await safe_edit(
            callback,
            "🔔 اعلان جدیدی نداری.",
            builder.as_markup(),
        )

        if answer_text:
            await callback.answer(answer_text)
        else:
            await callback.answer()

        return

    builder = InlineKeyboardBuilder()

    lines = [
        "🔔 <b>اعلان‌ها</b>",
        "",
    ]

    for notification in rows:
        mark = (
            "✅"
            if notification["is_read"]
            else "🆕"
        )

        title = escape(
            str(notification["title"] or ""),
            quote=False,
        )

        message = escape(
            str(notification["message"] or ""),
            quote=False,
        )

        lines.append(
            f"{mark} <b>{title}</b>\n"
            f"{message}"
        )

        if not notification["is_read"]:
            raw_title = str(
                notification["title"] or "اعلان"
            )

            button_title = raw_title[:20]

            builder.row(
                InlineKeyboardButton(
                    text=f"خواندم: {button_title}",
                    callback_data=(
                        f"notifread:{notification['id']}"
                    ),
                )
            )

    kb_add_back(
        builder,
        "main",
    )

    await safe_edit(
        callback,
        "\n\n".join(lines),
        builder.as_markup(),
    )

    if answer_text:
        await callback.answer(answer_text)
    else:
        await callback.answer()


@router.callback_query(
    F.data.startswith("notifread:")
)
async def handle_notification_read(
    callback: CallbackQuery,
) -> None:
    notif_id = parse_int(
        callback.data.split(":", 1)[1]
    )

    if notif_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    result = await backend.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE id = ?
          AND user_id = ?
          AND is_read = 0;
        """,
        (
            notif_id,
            user_id,
        ),
    )

    if result.rowcount != 1:
        await _render_notifications(
            callback,
            answer_text=(
                "ℹ️ این اعلان قبلاً خوانده شده "
                "یا دیگر در دسترس نیست."
            ),
        )
        return

    await _render_notifications(
        callback,
        answer_text="علامت خوانده شد ✅",
    )