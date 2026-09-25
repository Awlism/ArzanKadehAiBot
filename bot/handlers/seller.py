# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Seller browsing, favorites, contacts and claims
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..constants import (
    EMOJI_CITY,
    EMOJI_CLAIM,
    EMOJI_FAVORITES,
    EMOJI_LINK,
    EMOJI_RATING,
    EMOJI_REPORT,
    EMOJI_SELLERS,
    PAGE_SIZE_LIST,
)
from ..database import db
from ..keyboards import kb_add_back, kb_pagination_row
from ..repositories import (
    is_seller_favorite,
    toggle_seller_favorite,
)
from ..states import WhatsAppEditStates
from ..utils import (
    ensure_user,
    instagram_url,
    log_audit,
    log_event,
    now_iso,
    parse_int,
    safe_edit,
    status_badge,
    telegram_url,
    whatsapp_url,
    website_url,
)


router = Router(name="seller")


@router.callback_query(F.data.startswith("sellers:"))
async def handle_sellers_list(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    page = parse_int(callback.data.split(":")[1]) or 0
    await ensure_user(callback.from_user)

    sellers = await db.fetchall(
        """
        SELECT *
        FROM sellers
        ORDER BY rating DESC, views DESC, id DESC;
        """
    )

    if not sellers:
        builder = InlineKeyboardBuilder()
        kb_add_back(builder, "main")

        await safe_edit(
            callback,
            f"{EMOJI_SELLERS} فعلاً فروشگاهی ثبت نشده است.",
            builder.as_markup(),
        )
        await callback.answer()
        return

    offset = page * PAGE_SIZE_LIST
    page_rows = sellers[offset:offset + PAGE_SIZE_LIST]
    has_next = offset + PAGE_SIZE_LIST < len(sellers)

    builder = InlineKeyboardBuilder()

    for seller in page_rows:
        badge = (
            "🟢"
            if seller["status"] == "CLAIMED"
            else "⚪"
        )

        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{EMOJI_SELLERS} "
                    f"{badge} "
                    f"{seller['name']}"
                ),
                callback_data=f"seller:{seller['id']}",
            )
        )

    kb_pagination_row(
        builder,
        "sellers",
        page,
        has_next,
    )
    kb_add_back(builder, "main")

    await safe_edit(
        callback,
        f"{EMOJI_SELLERS} <b>فروشگاه‌ها</b>",
        builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("seller:"))
async def handle_seller_detail(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    seller_id = parse_int(
        callback.data.split(":")[1]
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    await _render_seller_detail(
        callback,
        seller_id,
    )


async def _render_seller_detail(
    callback: CallbackQuery,
    seller_id: int,
) -> None:
    user_id = await ensure_user(
        callback.from_user
    )

    seller = await db.fetchone(
        """
        SELECT
            s.*,
            c.name AS city_name
        FROM sellers s
        LEFT JOIN cities c
            ON c.id = s.city_id
        WHERE s.id = ?;
        """,
        (seller_id,),
    )

    if not seller:
        await callback.answer(
            "⚠️ این فروشگاه یافت نشد.",
            show_alert=True,
        )
        return

    await db.execute(
        """
        UPDATE sellers
        SET views = views + 1
        WHERE id = ?;
        """,
        (seller_id,),
    )

    await log_event(
        user_id,
        "view_seller",
        "seller",
        seller_id,
    )

    lines = [
        f"{EMOJI_SELLERS} <b>{seller['name']}</b>",
        "",
        seller["description"] or "بدون توضیحات",
        "",
        f"{EMOJI_CITY} {seller['city_name'] or 'نامشخص'}",
        (
            f"{EMOJI_RATING} "
            f"{seller['rating']:.1f} "
            f"({seller['review_count']} نظر)"
        ),
        status_badge(seller["status"]),
    ]

    if seller["status"] == "UNCLAIMED":
        lines.append(
            "\nاین صفحه هنوز توسط صاحب کسب‌وکار "
            "تأیید نشده است."
        )

    is_owner = user_id in (
        seller["owner_user_id"],
        seller["created_by_user_id"],
    )

    is_active = (
        bool(seller["is_active"])
        if seller["is_active"] is not None
        else True
    )

    if not is_active:
        lines.append(
            "\n🔴 این فروشگاه موقتاً غیرفعال است "
            "و فعلاً امکان ارتباط جدید ندارد."
        )

    builder = InlineKeyboardBuilder()

    instagram = instagram_url(
        seller["instagram"]
    )
    telegram = telegram_url(
        seller["telegram"]
    )
    website = website_url(
        seller["website"]
    )
    whatsapp = whatsapp_url(
        seller["whatsapp"]
    )
    support_telegram = telegram_url(
        seller["telegram_support"]
    )

    show_contacts = is_active or is_owner

    if show_contacts:
        if instagram:
            builder.row(
                InlineKeyboardButton(
                    text="📸 اینستاگرام",
                    callback_data=f"igclick:{seller_id}",
                )
            )

        if telegram:
            builder.row(
                InlineKeyboardButton(
                    text="✈️ تلگرام",
                    callback_data=f"tgclick:{seller_id}",
                )
            )

        if whatsapp:
            builder.row(
                InlineKeyboardButton(
                    text="🟢 واتساپ",
                    callback_data=f"waclick:{seller_id}",
                )
            )

        if website:
            builder.row(
                InlineKeyboardButton(
                    text=f"{EMOJI_LINK} وبسایت",
                    url=website,
                )
            )

        if support_telegram:
            builder.row(
                InlineKeyboardButton(
                    text="💬 پشتیبانی فروشگاه",
                    url=support_telegram,
                )
            )

    is_favorite = await is_seller_favorite(
        user_id,
        seller_id,
    )

    favorite_text = (
        "💔 حذف از علاقه‌مندی‌ها"
        if is_favorite
        else "❤️ ذخیره فروشگاه"
    )

    favorite_callback = (
        f"sunfav:{seller_id}"
        if is_favorite
        else f"sfav:{seller_id}"
    )

    builder.row(
        InlineKeyboardButton(
            text=favorite_text,
            callback_data=favorite_callback,
        )
    )

    if seller["status"] == "UNCLAIMED":
        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{EMOJI_CLAIM} "
                    "درخواست مالکیت فروشگاه"
                ),
                callback_data=f"claim:{seller_id}",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="⭐ ثبت نظر",
            callback_data=(
                f"reviewstart:seller:{seller_id}"
            ),
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=f"{EMOJI_REPORT} گزارش",
            callback_data=(
                f"report:seller:{seller_id}"
            ),
        )
    )

    if is_owner:
        whatsapp_label = (
            "🟢 ویرایش واتساپ"
            if whatsapp
            else "🟢 افزودن واتساپ"
        )

        builder.row(
            InlineKeyboardButton(
                text=whatsapp_label,
                callback_data=f"waedit:{seller_id}",
            )
        )

    kb_add_back(
        builder,
        "sellers:0",
    )

    await safe_edit(
        callback,
        "\n".join(lines),
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("sfav:"))
async def handle_seller_favorite_add(
    callback: CallbackQuery,
) -> None:
    seller_id = parse_int(
        callback.data.split(":")[1]
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    seller = await db.fetchone(
        "SELECT id FROM sellers WHERE id = ?;",
        (seller_id,),
    )

    if not seller:
        await callback.answer(
            "⚠️ این فروشگاه یافت نشد.",
            show_alert=True,
        )
        return

    await toggle_seller_favorite(
        user_id,
        seller_id,
    )

    await log_event(
        user_id,
        "favorite_add",
        "seller",
        seller_id,
    )

    await callback.answer(
        "❤️ ذخیره شد! هر وقت خواستی از بخش "
        "علاقه‌مندی‌ها پیداش می‌کنی.",
        show_alert=True,
    )

    await _render_seller_detail(
        callback,
        seller_id,
    )


@router.callback_query(F.data.startswith("sunfav:"))
async def handle_seller_favorite_remove(
    callback: CallbackQuery,
) -> None:
    seller_id = parse_int(
        callback.data.split(":")[1]
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    await toggle_seller_favorite(
        user_id,
        seller_id,
    )

    await callback.answer(
        "از علاقه‌مندی‌ها حذف شد 💔"
    )

    await _render_seller_detail(
        callback,
        seller_id,
    )


@router.callback_query(F.data.startswith("igclick:"))
async def handle_instagram_click(
    callback: CallbackQuery,
) -> None:
    seller_id = parse_int(
        callback.data.split(":")[1]
    )

    user_id = await ensure_user(
        callback.from_user
    )

    seller = await db.fetchone(
        "SELECT instagram FROM sellers WHERE id = ?;",
        (seller_id,),
    )

    link = (
        instagram_url(seller["instagram"])
        if seller
        else None
    )

    if not link:
        await callback.answer(
            "⚠️ این لینک در دسترس نیست.",
            show_alert=True,
        )
        return

    await log_event(
        user_id,
        "instagram_click",
        "seller",
        seller_id,
    )

    await callback.answer(url=link)


@router.callback_query(F.data.startswith("tgclick:"))
async def handle_telegram_click(
    callback: CallbackQuery,
) -> None:
    seller_id = parse_int(
        callback.data.split(":")[1]
    )

    user_id = await ensure_user(
        callback.from_user
    )

    seller = await db.fetchone(
        "SELECT telegram FROM sellers WHERE id = ?;",
        (seller_id,),
    )

    link = (
        telegram_url(seller["telegram"])
        if seller
        else None
    )

    if not link:
        await callback.answer(
            "⚠️ این لینک در دسترس نیست.",
            show_alert=True,
        )
        return

    await log_event(
        user_id,
        "telegram_click",
        "seller",
        seller_id,
    )

    await callback.answer(url=link)


@router.callback_query(F.data.startswith("waclick:"))
async def handle_whatsapp_click(
    callback: CallbackQuery,
) -> None:
    seller_id = parse_int(
        callback.data.split(":")[1]
    )

    user_id = await ensure_user(
        callback.from_user
    )

    seller = await db.fetchone(
        "SELECT whatsapp FROM sellers WHERE id = ?;",
        (seller_id,),
    )

    link = (
        whatsapp_url(seller["whatsapp"])
        if seller
        else None
    )

    if not link:
        await callback.answer(
            "⚠️ این لینک در دسترس نیست.",
            show_alert=True,
        )
        return

    await log_event(
        user_id,
        "whatsapp_click",
        "seller",
        seller_id,
    )

    await callback.answer(url=link)


@router.callback_query(F.data.startswith("waedit:"))
async def handle_whatsapp_edit_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    seller_id = parse_int(
        callback.data.split(":")[1]
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    seller = await db.fetchone(
        """
        SELECT id, owner_user_id, created_by_user_id
        FROM sellers
        WHERE id = ?;
        """,
        (seller_id,),
    )

    if not seller or user_id not in (
        seller["owner_user_id"],
        seller["created_by_user_id"],
    ):
        await callback.answer(
            "⚠️ این عملیات فقط برای صاحب فروشگاه "
            "در دسترس است.",
            show_alert=True,
        )
        return

    await state.update_data(
        whatsapp_seller_id=seller_id
    )

    await state.set_state(
        WhatsAppEditStates.waiting_number
    )

    builder = InlineKeyboardBuilder()
    kb_add_back(
        builder,
        f"seller:{seller_id}",
    )

    await safe_edit(
        callback,
        "🟢 شماره واتساپ فروشگاه رو با کد کشور "
        "بفرست (مثلاً 989123456789 یا 09123456789):",
        builder.as_markup(),
    )

    await callback.answer()


@router.message(
    StateFilter(
        WhatsAppEditStates.waiting_number
    )
)
async def handle_whatsapp_edit_value(
    message: Message,
    state: FSMContext,
) -> None:
    if (message.text or "").strip() == "/start":
        await state.clear()
        await ensure_user(message.from_user)
        return

    data = await state.get_data()
    seller_id = data.get("whatsapp_seller_id")

    await state.clear()

    if not seller_id:
        await message.answer(
            "⚠️ فرآیند منقضی شده. دوباره از صفحه "
            "فروشگاه تلاش کن."
        )
        return

    user_id = await ensure_user(
        message.from_user
    )

    seller = await db.fetchone(
        """
        SELECT id, owner_user_id, created_by_user_id, name
        FROM sellers
        WHERE id = ?;
        """,
        (seller_id,),
    )

    if not seller or user_id not in (
        seller["owner_user_id"],
        seller["created_by_user_id"],
    ):
        await message.answer(
            "⚠️ این عملیات فقط برای صاحب فروشگاه "
            "در دسترس است."
        )
        return

    raw_number = (
        message.text or ""
    ).strip()

    if not whatsapp_url(raw_number):
        await message.answer(
            "⚠️ شماره معتبر نیست. لطفاً فقط شماره "
            "همراه با کد کشور بفرست."
        )
        return

    await db.execute(
        """
        UPDATE sellers
        SET whatsapp = ?, updated_at = ?
        WHERE id = ?;
        """,
        (
            raw_number,
            now_iso(),
            seller_id,
        ),
    )

    await log_audit(
        user_id,
        "seller_whatsapp_updated",
        "seller",
        seller_id,
    )

    builder = InlineKeyboardBuilder()
    kb_add_back(
        builder,
        f"seller:{seller_id}",
    )

    await message.answer(
        f"✅ شماره واتساپ «{seller['name']}» ذخیره شد.",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("claim:"))
async def handle_claim(
    callback: CallbackQuery,
) -> None:
    seller_id = parse_int(
        callback.data.split(":")[1]
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    seller = await db.fetchone(
        "SELECT id FROM sellers WHERE id = ?;",
        (seller_id,),
    )

    if not seller:
        await callback.answer(
            "⚠️ این فروشگاه یافت نشد.",
            show_alert=True,
        )
        return

    existing = await db.fetchone(
        """
        SELECT id
        FROM seller_claims
        WHERE seller_id = ?
          AND user_id = ?
          AND status = 'PENDING';
        """,
        (
            seller_id,
            user_id,
        ),
    )

    if existing:
        await callback.answer(
            "شما قبلاً برای این فروشگاه درخواست داده‌اید.",
            show_alert=True,
        )
        return

    now = now_iso()

    await db.execute(
        """
        INSERT INTO seller_claims (
            seller_id,
            user_id,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, 'PENDING', ?, ?);
        """,
        (
            seller_id,
            user_id,
            now,
            now,
        ),
    )

    await log_event(
        user_id,
        "claim_request",
        "seller",
        seller_id,
    )

    await callback.answer(
        "درخواست مالکیت شما ثبت شد و در انتظار بررسی است.",
        show_alert=True,
    )