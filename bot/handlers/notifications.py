# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Notification handlers
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..database import db
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
) -> None:
    user_id = await ensure_user(callback.from_user)

    rows = await db.fetchall(
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

        lines.append(
            f"{mark} <b>{notification['title']}</b>\n"
            f"{notification['message'] or ''}"
        )

        if not notification["is_read"]:
            title = notification["title"] or "اعلان"

            builder.row(
                InlineKeyboardButton(
                    text=f"خواندم: {title[:20]}",
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

    user_id = await ensure_user(callback.from_user)

    await db.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE id = ?
          AND user_id = ?;
        """,
        (
            notif_id,
            user_id,
        ),
    )

    await callback.answer(
        "علامت خوانده شد ✅"
    )

    await _render_notifications(callback)