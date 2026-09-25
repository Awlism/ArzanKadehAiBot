# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Support and request handlers
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import ADMIN_CHAT_ID
from ..keyboards import kb_add_back
from ..repositories import (
    create_request,
    has_open_request,
    list_my_requests,
)
from ..states import SupportStates
from ..utils import (
    ensure_user,
    log_audit,
    now_iso,
    restart_requested,
    safe_edit,
    send_admin_dm,
)


router = Router(name="support")

SUPPORT_MESSAGE_MAX_LEN = 100

SUPPORT_TOPICS_BUYER = {
    "buy": "🛍️ مشکل خرید",
    "shop": "🏪 مشکل فروشگاه",
    "tech": "⚙️ مشکل فنی",
    "report": "🚨 گزارش مشکل",
    "other": "📝 سایر موارد ضروری",
}

SUPPORT_TOPICS_SELLER = {
    "shop_account": "🏪 مشکل حساب/فروشندگی",
    "ads": "📢 هماهنگی/پرداخت تبلیغات",
    "tech": "⚙️ مشکل فنی ارزانکده",
    "other": "📝 سایر موارد ضروری",
}


@router.callback_query(F.data == "myrequests")
async def handle_my_requests(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    user_id = await ensure_user(
        callback.from_user
    )

    items = await list_my_requests(
        user_id
    )

    builder = InlineKeyboardBuilder()

    if not items:
        text = (
            "📋 <b>درخواست‌های من</b>\n\n"
            "هنوز درخواستی ثبت نکرده‌اید."
        )
    else:
        lines = [
            "📋 <b>درخواست‌های من</b>",
            "",
        ]

        for item in items:
            lines.append(
                f"{item['title']} — "
                f"{item['status_label']}\n"
                f"{item['created_at'][:10]}"
            )

        text = "\n\n".join(lines)

    kb_add_back(
        builder,
        "account",
    )

    await safe_edit(
        callback,
        text,
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("supportstart:")
)
async def handle_support_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    audience = callback.data.split(
        ":",
        1,
    )[1]

    topics = (
        SUPPORT_TOPICS_SELLER
        if audience == "seller"
        else SUPPORT_TOPICS_BUYER
    )

    builder = InlineKeyboardBuilder()

    for code, label in topics.items():
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=(
                    f"supporttopic:"
                    f"{audience}:{code}"
                ),
            )
        )

    kb_add_back(
        builder,
        "account",
    )

    await safe_edit(
        callback,
        "🛟 موضوع مشکلت رو انتخاب کن:",
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("supporttopic:")
)
async def handle_support_topic(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    parts = callback.data.split(":")

    if len(parts) != 3:
        await callback.answer(
            "⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    _, audience, code = parts

    topics = (
        SUPPORT_TOPICS_SELLER
        if audience == "seller"
        else SUPPORT_TOPICS_BUYER
    )

    if code not in topics:
        await callback.answer(
            "⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    topic = topics[code]

    if await has_open_request(
        user_id,
        "support",
        topic=topic,
    ):
        await callback.answer(
            "درخواست پشتیبانی قبلی‌ات برای همین موضوع هنوز تعیین تکلیف نشده.",
            show_alert=True,
        )
        return

    await state.update_data(
        support_topic=topic
    )

    await state.set_state(
        SupportStates.waiting_text
    )

    builder = InlineKeyboardBuilder()

    await safe_edit(
        callback,
        (
            f"دلیل انتخابی: {topic}\n\n"
            "✍️ در یک جمله برامون بنویس "
            "چه مشکلی پیش اومده.\n"
            f"حداکثر {SUPPORT_MESSAGE_MAX_LEN} حرف 👇"
        ),
        builder.as_markup(),
    )

    await callback.answer()


@router.message(
    StateFilter(SupportStates.waiting_text)
)
async def handle_support_text(
    message: Message,
    state: FSMContext,
) -> None:
    if await restart_requested(
        message,
        state,
    ):
        return

    user_id = await ensure_user(
        message.from_user
    )

    data = await state.get_data()

    topic = data.get(
        "support_topic"
    )

    await state.clear()

    if not topic:
        await message.answer(
            "⚠️ فرآیند پشتیبانی منقضی شده. "
            "لطفاً دوباره تلاش کن."
        )
        return

    text = (
        message.text or ""
    ).strip()

    if not text:
        await message.answer(
            "⚠️ لطفاً یک متن معتبر بفرست."
        )
        return

    if len(text) > SUPPORT_MESSAGE_MAX_LEN:
        text = text[
            :SUPPORT_MESSAGE_MAX_LEN
        ]

    request_id = await create_request(
        user_id,
        "support",
        topic=topic,
        message=text,
    )

    await log_audit(
        user_id,
        "support_request_created",
        "request",
        request_id,
        details=topic,
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="🟢 تأیید درخواست",
            callback_data=(
                f"adminreq:approve:{request_id}"
            ),
        ),
        InlineKeyboardButton(
            text="🔴 رد درخواست",
            callback_data=(
                f"adminreq:reject:{request_id}"
            ),
        ),
    )

    if ADMIN_CHAT_ID:
        await send_admin_dm(
            message.bot,
            (
                "🛟 درخواست پشتیبانی جدید\n"
                f"موضوع: {topic}\n"
                f"پیام: {text}\n"
                f"(کاربر داخلی #{user_id})"
            ),
            reply_markup=builder.as_markup(),
        )

    await message.answer(
        "✅ درخواستت برای تیم پشتیبانی "
        "ارزانکده ارسال شد.\n"
        "تا وقتی که بررسی نشده، گفت‌وگوی مستقیم "
        "باز نمی‌شود؛ بعد از تأیید، ادامه‌ی "
        "گفت‌وگو فعال می‌شود."
    )