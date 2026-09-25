# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Advertising handlers
"""

from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..database import db
from ..keyboards import kb_add_back
from ..repositories import (
    create_request,
    has_open_request,
)
from ..services.referrals import get_sellers_owned_by_user
from ..states import GeneralAdStates
from ..utils import (
    ensure_user,
    log_audit,
    now_iso,
    restart_requested,
    safe_edit,
    send_admin_dm,
)

router = Router(name="ads")


AD_TYPES = {
    "featured_product": {
        "menu_label": "⭐ محصولم رو بیشتر دیده کن",
        "detail_title": "🔥 محصولت رو بیشتر دیده کن",
        "detail_body": (
            "می‌خوای این محصول بیشتر جلوی چشم خریدارها باشه؟ 👀\n\n"
            "با این گزینه، محصولت می‌تونه بالاتر از بقیه محصولات در "
            "دسته‌بندی و جستجو دیده بشه.\n\n"
            "✨ این یعنی احتمال اینکه آدم‌های بیشتری محصولت رو ببینن، "
            "بیشتر می‌شه.\n\n"
            "⏰ نمایش ویژه برای مدت مشخص انجام می‌شه.\n\n"
            "💰 قیمت و نحوه پرداخت رو قبل از ثبت بهت می‌گیم."
        ),
        "pick_button": "🟢 انتخاب محصول",
    },
    "featured_seller": {
        "menu_label": "🏪 فروشگاهم رو بیشتر دیده کن",
        "detail_title": "⭐ فروشگاهت رو بیشتر دیده کن",
        "detail_body": (
            "می‌خوای آدم‌های بیشتری فروشگاهت رو ببینن؟ 👀\n\n"
            "با نمایش ویژه، فروشگاهت بالاتر از بقیه فروشگاه‌ها نمایش "
            "داده می‌شه و شانس دیده شدنت بیشتر می‌شه.\n\n"
            "⏰ برای مدت مشخص فعال می‌شه.\n\n"
            "💰 قیمت و نحوه پرداخت قبل از ثبت بهت گفته می‌شه."
        ),
        "pick_button": "🟢 انتخاب فروشگاه",
    },
    "regional_ad": {
        "menu_label": "📍 توی شهرم بیشتر دیده بشم",
        "detail_title": "📍 توی شهرم بیشتر دیده بشم",
        "detail_body": (
            "می‌خوای آدم‌های بیشتری از شهر خودت ببیننت؟ 👀\n\n"
            "با این گزینه، فروشگاه یا محصولت بیشتر به کاربرهای "
            "همون شهر و اطرافش نشون داده می‌شه.\n\n"
            "⏰ برای مدت مشخص فعاله.\n\n"
            "💰 قیمت و نحوه پرداخت قبل از ثبت گفته می‌شه."
        ),
        "pick_button": "🟢 انتخاب تبلیغ",
    },
    "intro_feature": {
        "menu_label": "🏠 فروشگاهم رو ویژه معرفی کنم",
        "detail_title": "🏠 فروشگاهم رو ویژه معرفی کنم",
        "detail_body": (
            "✨ می‌خوای فروشگاهت رو بهتر به بقیه معرفی کنیم؟\n\n"
            "با این گزینه، فروشگاهت در بخش‌های ویژه ارزانکده معرفی "
            "می‌شه تا آدم‌های بیشتری با کسب‌وکارت آشنا بشن. 👀\n\n"
            "🌱 برای فروشگاه‌های تازه‌کار یا معرفی‌های ویژه خیلی خوبه.\n\n"
            "💰 هزینه و نحوه پرداخت قبل از ثبت گفته می‌شه."
        ),
        "pick_button": "🟢 انتخاب معرفی",
    },
}


@router.callback_query(F.data == "ads")
async def handle_ads(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await ensure_user(callback.from_user)

    text = (
        "🚀 <b>می‌خوای بیشتر دیده بشی؟</b>\n\n"
        "اینجا می‌تونی فروشگاه یا محصولت رو به آدم‌های بیشتری "
        "توی ارزانکده نشون بدی."
    )

    builder = InlineKeyboardBuilder()

    for code, info in AD_TYPES.items():
        builder.row(
            InlineKeyboardButton(
                text=info["menu_label"],
                callback_data=f"adtype:{code}",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="📢 تبلیغ در ارزانکده (عمومی)",
            callback_data="publicads",
        )
    )

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
    F.data.startswith("adtype:")
)
async def handle_ad_type_detail(
    callback: CallbackQuery,
) -> None:
    code = callback.data.split(
        ":",
        1,
    )[1]

    info = AD_TYPES.get(code)

    if not info:
        await callback.answer(
            "⚠️ این نوع تبلیغ یافت نشد.",
            show_alert=True,
        )
        return

    text = (
        f"{info['detail_title']}\n\n"
        f"{info['detail_body']}"
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=info["pick_button"],
            callback_data=f"adconfirm:{code}",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🛟 سوالی دارم",
            callback_data="supportstart:seller",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🔙 برگردیم",
            callback_data="ads",
        )
    )

    await safe_edit(
        callback,
        text,
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("adconfirm:")
)
async def handle_ad_confirm(
    callback: CallbackQuery,
) -> None:
    code = callback.data.split(
        ":",
        1,
    )[1]

    info = AD_TYPES.get(code)

    if not info:
        await callback.answer(
            "⚠️ این نوع تبلیغ یافت نشد.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    topic = info["menu_label"]

    if await has_open_request(
        user_id,
        "ad",
        topic=topic,
    ):
        await callback.answer(
            "درخواست تبلیغاتی قبلی‌ات برای همین نوع "
            "هنوز تعیین تکلیف نشده.",
            show_alert=True,
        )
        return

    sellers = await get_sellers_owned_by_user(
        user_id
    )

    seller_id = (
        sellers[0]["id"]
        if sellers
        else None
    )

    request_id = await create_request(
        user_id,
        "ad",
        topic=topic,
        seller_id=seller_id,
    )

    await log_audit(
        user_id,
        "ad_request_created",
        "request",
        request_id,
        details=code,
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

    admin_text = (
        "📢 درخواست تبلیغات جدید\n"
        f"نوع: {topic}\n"
        f"(کاربر داخلی #{user_id}"
        + (
            f"، فروشگاه #{seller_id}"
            if seller_id
            else ""
        )
        + ")"
    )

    await send_admin_dm(
        callback.bot,
        admin_text,
        reply_markup=builder.as_markup(),
    )

    back_builder = InlineKeyboardBuilder()

    kb_add_back(
        back_builder,
        "account",
    )

    await safe_edit(
        callback,
        (
            f"✅ درخواست «{topic}» ثبت شد.\n\n"
            "💬 برای قیمت و هماهنگی پرداخت با "
            "پشتیبانی ارزانکده در ارتباط باش.\n"
            "می‌تونی وضعیت درخواستت رو از "
            "«📋 درخواست‌های من» پیگیری کنی."
        ),
        back_builder.as_markup(),
    )

    await callback.answer()


# ================================================================
# تبلیغات عمومی
# ================================================================

AD_KIND_LABELS = {
    "business": "🏪 کسب‌وکار",
    "page": "📱 پیج",
    "channel": "📣 کانال",
    "service": "🛠️ خدمات",
    "brand": "✨ برند",
    "other": "➕ چیز دیگه",
}


PUBLIC_AD_MODELS_TEXT = (
    "💡 <b>مدل‌های تبلیغ</b>\n\n"
    "قیمت و مدت نمایش بسته به جایی که می‌خوای تبلیغت دیده بشه "
    "فرق می‌کنه (مثلاً صفحه اصلی، نتایج جستجو، یا بخش‌های ویژه). "
    "بعد از ثبت درخواست، تیم ارزانکده بهترین جا رو باهات هماهنگ "
    "می‌کنه و قیمت دقیق رو قبل از هر پرداختی بهت می‌گه. "
    "هیچ هزینه‌ای بدون هماهنگی قبلی از تو گرفته نمی‌شه."
)


@router.callback_query(
    F.data == "publicads"
)
async def handle_public_ads(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await ensure_user(callback.from_user)

    text = (
        "🚀 <b>می‌خوای بیشتر دیده بشی؟</b>\n\n"
        "کسب‌وکارت، پیج، کانال، خدمات یا برندت رو "
        "به کاربرهای ارزانکده معرفی کن.\n\n"
        "ما تبلیغت رو بررسی می‌کنیم و جای نمایش و "
        "هزینه رو باهات هماهنگ می‌کنیم."
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="📢 ثبت تبلیغ",
            callback_data="pubadstart",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="💡 مدل‌های تبلیغ",
            callback_data="pubadmodels",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🛟 سوالی دارم",
            callback_data="supportstart:buyer",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🔙 برگردیم",
            callback_data="main",
        )
    )

    await safe_edit(
        callback,
        text,
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(
    F.data == "pubadmodels"
)
async def handle_public_ad_models(
    callback: CallbackQuery,
) -> None:
    builder = InlineKeyboardBuilder()

    kb_add_back(
        builder,
        "publicads",
    )

    await safe_edit(
        callback,
        PUBLIC_AD_MODELS_TEXT,
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(
    F.data == "pubadstart"
)
async def handle_public_ad_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await ensure_user(callback.from_user)

    builder = InlineKeyboardBuilder()

    for code, label in AD_KIND_LABELS.items():
        builder.button(
            text=label,
            callback_data=f"pubadkind:{code}",
        )

    builder.adjust(2)

    kb_add_back(
        builder,
        "publicads",
    )

    await safe_edit(
        callback,
        "🎯 چی رو می‌خوای معرفی کنی؟",
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("pubadkind:")
)
async def handle_public_ad_kind(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    kind = callback.data.split(
        ":",
        1,
    )[1]

    if kind not in AD_KIND_LABELS:
        await callback.answer(
            "⚠️ گزینه نامعتبر است.",
            show_alert=True,
        )
        return

    await state.update_data(
        pubad_kind=kind
    )

    await state.set_state(
        GeneralAdStates.waiting_title
    )

    builder = InlineKeyboardBuilder()

    await safe_edit(
        callback,
        (
            "عنوان تبلیغت چیه؟ "
            "(مثلاً اسم کسب‌وکار/پیج/کانال)"
        ),
        builder.as_markup(),
    )

    await callback.answer()


@router.message(
    StateFilter(GeneralAdStates.waiting_title)
)
async def handle_public_ad_title(
    message: Message,
    state: FSMContext,
) -> None:
    if await restart_requested(
        message,
        state,
    ):
        return

    title = (
        message.text or ""
    ).strip()

    if not title:
        await message.answer(
            "⚠️ عنوان نمی‌تواند خالی باشد. "
            "دوباره بفرست:"
        )
        return

    await state.update_data(
        pubad_title=title
    )

    await state.set_state(
        GeneralAdStates.waiting_description
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="رد کردن",
            callback_data=(
                "pubadskip:description"
            ),
        )
    )

    await message.answer(
        "یه توضیح کوتاه بنویس که مردم "
        "بفهمن چی هستی:",
        reply_markup=builder.as_markup(),
    )


@router.message(
    StateFilter(GeneralAdStates.waiting_description)
)
async def handle_public_ad_description(
    message: Message,
    state: FSMContext,
) -> None:
    if await restart_requested(
        message,
        state,
    ):
        return

    await state.update_data(
        pubad_description=(
            (message.text or "").strip()
            or None
        )
    )

    await state.set_state(
        GeneralAdStates.waiting_image_url
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="رد کردن",
            callback_data=(
                "pubadskip:image_url"
            ),
        )
    )

    await message.answer(
        "یه تصویر داری؟ لینکش رو بفرست "
        "(اختیاری):",
        reply_markup=builder.as_markup(),
    )


@router.message(
    StateFilter(GeneralAdStates.waiting_image_url)
)
async def handle_public_ad_image(
    message: Message,
    state: FSMContext,
) -> None:
    if await restart_requested(
        message,
        state,
    ):
        return

    await state.update_data(
        pubad_image_url=(
            (message.text or "").strip()
            or None
        )
    )

    await state.set_state(
        GeneralAdStates.waiting_link
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="رد کردن",
            callback_data=(
                "pubadskip:link"
            ),
        )
    )

    await message.answer(
        "لینک صفحه/پیج/کانالت رو بفرست "
        "(اختیاری):",
        reply_markup=builder.as_markup(),
    )


@router.message(
    StateFilter(GeneralAdStates.waiting_link)
)
async def handle_public_ad_link(
    message: Message,
    state: FSMContext,
) -> None:
    if await restart_requested(
        message,
        state,
    ):
        return

    await state.update_data(
        pubad_link=(
            (message.text or "").strip()
            or None
        )
    )

    await _finish_public_ad(
        message.from_user,
        state,
        message=message,
    )


@router.callback_query(
    F.data.startswith("pubadskip:")
)
async def handle_public_ad_skip(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    field = callback.data.split(
        ":",
        1,
    )[1]

    if field == "description":
        await state.update_data(
            pubad_description=None
        )

        await state.set_state(
            GeneralAdStates.waiting_image_url
        )

        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(
                text="رد کردن",
                callback_data=(
                    "pubadskip:image_url"
                ),
            )
        )

        await safe_edit(
            callback,
            "یه تصویر داری؟ لینکش رو بفرست (اختیاری):",
            builder.as_markup(),
        )

        await callback.answer()
        return

    if field == "image_url":
        await state.update_data(
            pubad_image_url=None
        )

        await state.set_state(
            GeneralAdStates.waiting_link
        )

        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(
                text="رد کردن",
                callback_data=(
                    "pubadskip:link"
                ),
            )
        )

        await safe_edit(
            callback,
            "لینک صفحه/پیج/کانالت رو بفرست (اختیاری):",
            builder.as_markup(),
        )

        await callback.answer()
        return

    if field == "link":
        await state.update_data(
            pubad_link=None
        )

        await _finish_public_ad(
            callback.from_user,
            state,
            callback=callback,
        )
        return

    await callback.answer(
        "⚠️ درخواست نامعتبر است.",
        show_alert=True,
    )


async def _finish_public_ad(
    tg_user,
    state: FSMContext,
    callback: Optional[CallbackQuery] = None,
    message: Optional[Message] = None,
) -> None:
    user_id = await ensure_user(
        tg_user
    )

    data = await state.get_data()

    await state.clear()

    kind = data.get("pubad_kind")
    title = data.get("pubad_title")

    if not kind or not title:
        text = (
            "⚠️ اطلاعات تبلیغ ناقص است. "
            "لطفاً دوباره از "
            "«📢 تبلیغ در ارزانکده» تلاش کن."
        )

        if callback:
            await safe_edit(
                callback,
                text,
                InlineKeyboardBuilder().as_markup(),
            )
            await callback.answer()

        elif message:
            await message.answer(text)

        return

    if await has_open_request(
        user_id,
        "general_ad",
    ):
        text = (
            "یه درخواست تبلیغ قبلی‌ات هنوز "
            "در حال بررسیه. تا اون تعیین‌تکلیف "
            "نشده، درخواست جدید ثبت نمی‌شه."
        )

        if callback:
            await safe_edit(
                callback,
                text,
                InlineKeyboardBuilder().as_markup(),
            )
            await callback.answer()

        elif message:
            await message.answer(text)

        return

    now = now_iso()

    cursor = await db.execute(
        """
        INSERT INTO requests (
            user_id,
            request_type,
            topic,
            message,
            status,
            created_at,
            updated_at,
            ad_kind,
            ad_title,
            ad_image_url,
            ad_link
        )
        VALUES (
            ?,
            'general_ad',
            ?,
            ?,
            'PENDING',
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        );
        """,
        (
            user_id,
            AD_KIND_LABELS[kind],
            data.get("pubad_description"),
            now,
            now,
            kind,
            title,
            data.get("pubad_image_url"),
            data.get("pubad_link"),
        ),
    )

    request_id = cursor.lastrowid

    await log_audit(
        user_id,
        "general_ad_request_created",
        "request",
        request_id,
        details=title,
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="🟢 تأیید تبلیغ",
            callback_data=(
                f"adminreq:approve:{request_id}"
            ),
        ),
        InlineKeyboardButton(
            text="🔴 رد تبلیغ",
            callback_data=(
                f"adminreq:reject:{request_id}"
            ),
        ),
    )

    ad_summary = (
        "📢 تبلیغ عمومی جدید\n"
        f"نوع: {AD_KIND_LABELS[kind]}\n"
        f"عنوان: {title}\n"
        f"توضیح: "
        f"{data.get('pubad_description') or '—'}\n"
        f"لینک: "
        f"{data.get('pubad_link') or '—'}\n"
        f"(کاربر داخلی #{user_id}, "
        f"درخواست #{request_id})"
    )

    bot_obj = (
        callback.bot
        if callback
        else message.bot
    )

    await send_admin_dm(
        bot_obj,
        ad_summary,
        reply_markup=builder.as_markup(),
    )

    text = (
        "✅ تبلیغت ثبت شد.\n\n"
        "ما بررسیش می‌کنیم و برای جای نمایش "
        "و هزینه باهات هماهنگ می‌کنیم.\n"
        "می‌تونی وضعیتش رو از "
        "«📋 درخواست‌های من» پیگیری کنی."
    )

    back_builder = InlineKeyboardBuilder()

    kb_add_back(
        back_builder,
        "main",
    )

    if callback:
        await safe_edit(
            callback,
            text,
            back_builder.as_markup(),
        )
        await callback.answer()

    elif message:
        await message.answer(
            text,
            reply_markup=back_builder.as_markup(),
        )