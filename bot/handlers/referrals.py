# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Referral handlers
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ..database import db
from ..services.referrals import referral_stats_text
from ..utils import ensure_user, parse_int, safe_edit

router = Router(name="referrals")


@router.callback_query(F.data == "reflist")
async def handle_referral_list(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    user_id = await ensure_user(callback.from_user)

    sellers = await db.fetchall(
        """
        SELECT id, name
        FROM sellers
        WHERE created_by_user_id = ?
           OR owner_user_id = ?
        ORDER BY id DESC;
        """,
        (user_id, user_id),
    )

    if not sellers:
        await callback.answer(
            "⚠️ شما هنوز فروشگاهی ثبت نکرده‌اید.",
            show_alert=True,
        )
        return

    if len(sellers) == 1:
        await _render_referral_stats(
            callback,
            sellers[0]["id"],
        )
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    builder = InlineKeyboardBuilder()

    for seller in sellers:
        builder.row(
            InlineKeyboardButton(
                text=f"🏪 {seller['name']}",
                callback_data=f"refstats:{seller['id']}",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="🔙 بازگشت",
            callback_data="account",
        )
    )

    await safe_edit(
        callback,
        "کدوم فروشگاهت رو می‌خوای ببینی؟",
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("refstats:"))
async def handle_referral_stats(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    parts = callback.data.split(":", 1)

    if len(parts) != 2:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    seller_id = parse_int(parts[1])

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    await _render_referral_stats(
        callback,
        seller_id,
    )


async def _render_referral_stats(
    callback: CallbackQuery,
    seller_id: int,
) -> None:
    user_id = await ensure_user(
        callback.from_user
    )

    seller = await db.fetchone(
        """
        SELECT
            id,
            name,
            owner_user_id,
            created_by_user_id
        FROM sellers
        WHERE id = ?;
        """,
        (seller_id,),
    )

    if not seller:
        await callback.answer(
            "⚠️ این فروشگاه یافت نشد.",
            show_alert=True,
        )
        return

    if (
        seller["owner_user_id"] != user_id
        and seller["created_by_user_id"] != user_id
    ):
        await callback.answer(
            "⚠️ شما به این فروشگاه دسترسی ندارید.",
            show_alert=True,
        )
        return

    me = await callback.bot.get_me()

    if not me.username:
        await callback.answer(
            "⚠️ نام کاربری ربات تنظیم نشده است.",
            show_alert=True,
        )
        return

    text = await referral_stats_text(
        me.username,
        seller["id"],
        seller["name"],
    )

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="🔙 بازگشت",
            callback_data="account",
        )
    )

    await safe_edit(
        callback,
        text,
        builder.as_markup(),
    )

    await callback.answer()