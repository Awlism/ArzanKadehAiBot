# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Account / buyer mode / seller mode handlers
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import ADMIN_CHAT_ID
from ..constants import VALID_MODES
from ..keyboards import kb_add_back, restart_button
from ..repositories import (
    get_active_mode,
    set_active_mode,
    user_has_any_seller,
)
from ..utils import ensure_user, safe_edit
from .admin import _render_admin_home


router = Router(name="account")


# ======================================================================
# ACCOUNT
# ======================================================================

@router.callback_query(F.data == "account")
async def handle_account(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    Role-aware account entry point.

    Renders:
    - Buyer panel for buyer mode
    - Seller panel for seller mode
    - Admin panel for admin mode

    A user without a seller always remains able to access the buyer
    panel. Seller mode and owning a seller are separate concerns.
    """
    await state.clear()

    user_id = await ensure_user(callback.from_user)
    mode = await get_active_mode(user_id)

    if mode == "admin":
        await _render_admin_home(callback)

    elif mode == "seller":
        await _render_seller_panel(callback, user_id)

    else:
        await _render_buyer_panel(callback, user_id)

    await callback.answer()


# ======================================================================
# MODE SWITCH
# ======================================================================

def _mode_switch_button(
    current_mode: str,
) -> InlineKeyboardButton:
    if current_mode == "buyer":
        return InlineKeyboardButton(
            text="🏪 حالت فروشندگی",
            callback_data="setmode:seller",
        )

    return InlineKeyboardButton(
        text="👤 حالت خرید",
        callback_data="setmode:buyer",
    )


@router.callback_query(F.data.startswith("setmode:"))
async def handle_set_mode(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    mode = callback.data.split(":", 1)[1]

    if mode not in VALID_MODES:
        await callback.answer(
            "⚠️ حالت نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    # Seller mode and owning a seller are deliberately separate.
    # A user may enter seller mode before registering a store.
    try:
        await set_active_mode(user_id, mode)

    except PermissionError:
        await callback.answer(
            "⛔️ این حالت فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    if mode == "seller":
        await _render_seller_panel(
            callback,
            user_id,
        )

    else:
        await _render_buyer_panel(
            callback,
            user_id,
        )

    await callback.answer()


# ======================================================================
# BUYER PANEL
# ======================================================================

async def _render_buyer_panel(
    callback: CallbackQuery,
    user_id: int,
) -> None:
    lines = [
        "👤 <b>حساب من</b>",
        "",
        "👤 حالت خرید",
    ]

    builder = InlineKeyboardBuilder()

    # Seller mode is NOT gated by store ownership.
    # A user can switch to seller mode even before registering a store.
    builder.row(
        _mode_switch_button("buyer")
    )

    builder.row(
        InlineKeyboardButton(
            text="❤️ علاقه‌مندی‌ها",
            callback_data="favorites:0",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="⚖️ مقایسه",
            callback_data="comparelist",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="💬 پیام‌های من",
            callback_data="notifications",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="📋 درخواست‌های من",
            callback_data="myrequests",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🛟 پشتیبانی ارزانکده",
            callback_data="supportstart:buyer",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="👤 پروفایل من",
            callback_data="myprofile",
        )
    )

    if (
        ADMIN_CHAT_ID
        and callback.from_user.id == ADMIN_CHAT_ID
    ):
        builder.row(
            InlineKeyboardButton(
                text="📢 مدیریت تبلیغات (ادمین)",
                callback_data="adsadmin",
            )
        )

    kb_add_back(
        builder,
        "main",
    )

    builder.row(
        restart_button()
    )

    await safe_edit(
        callback,
        "\n".join(lines),
        builder.as_markup(),
    )


# ======================================================================
# SELLER PANEL
# ======================================================================

async def _render_seller_panel(
    callback: CallbackQuery,
    user_id: int,
) -> None:
    lines = [
        "👋 <b>خب، رسیدیم به فروشگاهت!</b>",
        "همه‌چی که برای بهتر شدن فروشگاهت لازم داری، همینجاست.",
    ]

    builder = InlineKeyboardBuilder()

    builder.row(
        _mode_switch_button("seller")
    )

    has_store = await user_has_any_seller(user_id)

    if not has_store:
        lines.append(
            "\nهنوز فروشگاهی ثبت نکردی؛ "
            "هر وقت آماده بودی از همینجا شروع کن 👇"
        )

        builder.row(
            InlineKeyboardButton(
                text="➕ ثبت فروشگاه من",
                callback_data="registerseller",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="📦 محصولاتم",
            callback_data="myproducts",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🏪 فروشگاهم",
            callback_data="myshop",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="👀 چقدر دیده شدم",
            callback_data="storestatus",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="📣 بیشتر دیده بشم",
            callback_data="ads",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🛟 کمک می‌خوام",
            callback_data="supportstart:seller",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="📋 درخواست‌های من",
            callback_data="myrequests",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🛍️ برم خرید کنم",
            callback_data="setmode:buyer",
        )
    )

    kb_add_back(
        builder,
        "main",
    )

    builder.row(
        restart_button()
    )

    await safe_edit(
        callback,
        "\n".join(lines),
        builder.as_markup(),
    )