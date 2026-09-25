# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
/start and role-selection handlers
"""

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from ..keyboards import main_menu_keyboard
from ..utils import ensure_user, log_event


router = Router(name="start")


async def _show_main_menu(message: Message) -> None:
    await message.answer(
        "🛍️ <b>به ارزانکده خوش اومدی!</b>\n\n"
        "یک محل ساده برای پیدا کردن فروشگاه‌ها، محصولات و خدمات ایرانی.\n\n"
        "یکی از گزینه‌های زیر رو انتخاب کن 👇",
        reply_markup=main_menu_keyboard(),
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user_id = await ensure_user(message.from_user)

    await log_event(
        user_id,
        "start",
    )

    await _show_main_menu(message)


@router.callback_query(F.data == "restart_button")
async def restart_button(callback: CallbackQuery) -> None:
    user_id = await ensure_user(callback.from_user)

    await log_event(
        user_id,
        "restart",
    )

    await callback.answer()

    await callback.message.edit_text(
        "🛍️ <b>به ارزانکده خوش اومدی!</b>\n\n"
        "یک محل ساده برای پیدا کردن فروشگاه‌ها، محصولات و خدمات ایرانی.\n\n"
        "یکی از گزینه‌های زیر رو انتخاب کن 👇",
        reply_markup=main_menu_keyboard(),
    )