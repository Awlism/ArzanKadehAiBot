# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Navigation / start / fallback handlers
"""

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..database import db
from ..repositories import (
    get_active_mode,
    set_active_mode,
)
from ..services.referrals import (
    REFERRAL_DEEP_LINK_RE,
    record_referral_if_new,
)
from ..utils import (
    ensure_user,
    is_admin_telegram_id,
    now_iso,
    notify_user,
    safe_edit,
    send_main_menu,
)
from .account import _render_seller_panel
from .admin import _render_admin_home


logger = logging.getLogger(__name__)

router = Router(
    name="navigation"
)


# ======================================================================
# MAIN / ROLE PICKING
# ======================================================================

SELLER_MODE_LANDING_TEXT = (
    "🏪 خب، حالا حالت فروشندگی فعاله!\n\n"
    "برای اینکه فروشگاهت روی ارزانکده دیده بشه، باید اول ثبتش کنی -- "
    "هر وقت آماده بودی، از همینجا شروع کن."
)

ADMIN_MODE_PLACEHOLDER_TEXT = (
    "🛡 حالت ادمین فعاله.\n\n"
    "پنل کامل مدیریت هنوز در حال ساخته شدنه؛ فعلاً می‌تونی از همون "
    "امکانات مدیریتی موجود (تأیید/رد گزارش‌ها و درخواست‌ها) که از "
    "طریق پیام‌های ادمین برات ارسال می‌شه استفاده کنی."
)


@router.callback_query(F.data == "main")
async def handle_main_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    await ensure_user(
        callback.from_user
    )

    await send_main_menu(
        callback
    )

    await callback.answer()


ROLE_PICK_TEXT = (
    "👋 خوش اومدی به ارزانکده!\n"
    "اینجا می‌تونی چیزی که می‌خوای پیدا کنی، یا کسب‌وکارت رو به "
    "آدم‌های بیشتری معرفی کنی.\n\n"
    "امروز برای چی اومدی؟ 😊"
)


def role_pick_keyboard(
    show_admin_option: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="🛍️ می‌خوام خرید کنم",
            callback_data="rolepick:buyer",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🏪 می‌خوام فروشنده باشم",
            callback_data="rolepick:seller",
        )
    )

    if show_admin_option:
        builder.row(
            InlineKeyboardButton(
                text="🛡 ادمین",
                callback_data="rolepick:admin",
            )
        )

    return builder.as_markup()


def restart_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text="🏠 شروع از اول",
        callback_data="restartmain",
    )


@router.callback_query(
    F.data.startswith("rolepick:")
)
async def handle_role_pick(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    role = callback.data.split(
        ":",
        1,
    )[1]

    if role not in (
        "buyer",
        "seller",
        "admin",
    ):
        await callback.answer(
            "⚠️ گزینه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    await db.execute(
        """
        UPDATE users
        SET role_chosen = 1,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            now_iso(),
            user_id,
        ),
    )

    if role == "buyer":
        await set_active_mode(
            user_id,
            "buyer",
        )

        await send_main_menu(
            callback
        )

        await callback.answer()
        return

    if role == "admin":
        if not is_admin_telegram_id(
            callback.from_user.id
        ):
            await callback.answer(
                "⛔️ این گزینه فقط برای ادمین در دسترس است.",
                show_alert=True,
            )
            return

        await set_active_mode(
            user_id,
            "admin",
        )

        await _render_admin_home(
            callback
        )

        await callback.answer()
        return

    # role == "seller"

    await set_active_mode(
        user_id,
        "seller",
    )

    await _render_seller_panel(
        callback,
        user_id,
    )

    await callback.answer()


# ======================================================================
# RESTART
# ======================================================================

@router.callback_query(
    F.data == "restart_button"
)
@router.callback_query(
    F.data == "restartmain"
)
async def handle_restart_main(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    user_id = await ensure_user(
        callback.from_user
    )

    await _go_to_start(
        callback,
        user_id,
    )

    await callback.answer()


# ======================================================================
# START
# ======================================================================

async def _go_to_start(
    target,
    user_id: int,
) -> None:
    """
    Shared entry point for /start and "شروع از اول".

    First-time users see the role picker.
    Returning users go to their current mode.

    This function does not delete account/store/product/order data.
    """

    from_user_id = (
        target.from_user.id
        if isinstance(
            target,
            (CallbackQuery, Message),
        )
        else None
    )

    row = await db.fetchone(
        """
        SELECT role_chosen
        FROM users
        WHERE id = ?;
        """,
        (user_id,),
    )

    if not row or not row["role_chosen"]:
        show_admin = (
            is_admin_telegram_id(
                from_user_id
            )
            if from_user_id is not None
            else False
        )

        keyboard = role_pick_keyboard(
            show_admin_option=show_admin,
        )

        if isinstance(
            target,
            CallbackQuery,
        ):
            await safe_edit(
                target,
                ROLE_PICK_TEXT,
                keyboard,
            )
        else:
            await target.answer(
                ROLE_PICK_TEXT,
                reply_markup=keyboard,
            )

        return

    mode = await get_active_mode(
        user_id
    )

    if mode == "seller":
        if isinstance(
            target,
            CallbackQuery,
        ):
            await _render_seller_panel(
                target,
                user_id,
            )
        else:
            await send_main_menu(
                target
            )

    elif mode == "admin":
        if isinstance(
            target,
            CallbackQuery,
        ):
            await _render_admin_home(
                target
            )
        else:
            await send_main_menu(
                target
            )

    else:
        await send_main_menu(
            target
        )


@router.message(
    CommandStart()
)
async def handle_start(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()

    user_id = await ensure_user(
        message.from_user
    )

    await _handle_referral_deep_link(
        message,
        user_id,
    )

    await _go_to_start(
        message,
        user_id,
    )


async def _handle_referral_deep_link(
    message: Message,
    user_id: int,
) -> None:
    """
    Parses /start shop_<seller_id> deep links.

    Invalid or missing referral payloads are ignored.
    """

    text = (
        message.text or ""
    ).strip()

    parts = text.split(
        maxsplit=1
    )

    if len(parts) != 2:
        return

    match = REFERRAL_DEEP_LINK_RE.match(
        parts[1].strip()
    )

    if not match:
        return

    seller_id = int(
        match.group(1)
    )

    seller = await db.fetchone(
        """
        SELECT id, owner_user_id
        FROM sellers
        WHERE id = ?;
        """,
        (seller_id,),
    )

    if not seller:
        return

    if seller["owner_user_id"] == user_id:
        return

    recorded = await record_referral_if_new(
        seller_id,
        user_id,
    )

    if (
        recorded
        and seller["owner_user_id"]
    ):
        await notify_user(
            seller["owner_user_id"],
            "🎉 معرفی جدید",
            "یک کاربر جدید از طریق لینک اختصاصی فروشگاه شما وارد ارزانکده شد!",
            ntype="referral",
        )


# ======================================================================
# UNKNOWN / FALLBACK HANDLERS
# ======================================================================

@router.callback_query()
async def handle_unknown_callback(
    callback: CallbackQuery,
) -> None:
    """
    MUST remain the last callback handler.

    A bare callback_query handler matches any callback that was not
    handled by an earlier, more specific handler.
    """

    logger.warning(
        "Unknown callback_data received: %s",
        callback.data,
    )

    await callback.answer(
        "⚠️ این گزینه هنوز فعال نیست.",
        show_alert=True,
    )


@router.message()
async def handle_unknown_message(
    message: Message,
    state: FSMContext,
) -> None:
    """
    MUST remain the last generic message handler.

    Messages belonging to an active FSM state are intentionally ignored
    here so that they can be handled by their state-specific handlers.
    """

    current_state = await state.get_state()

    if current_state is not None:
        return

    await ensure_user(
        message.from_user
    )

    await send_main_menu(
        message
    )