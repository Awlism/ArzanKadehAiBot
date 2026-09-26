# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Seller browsing, favorites, contacts, shop management,
product management, statistics and seller registration.
"""

from typing import Optional

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import ADMIN_CHAT_ID
from ..constants import (
    EMOJI_CITY,
    EMOJI_CLAIM,
    EMOJI_FAVORITES,
    EMOJI_LINK,
    EMOJI_PRICE,
    EMOJI_RATING,
    EMOJI_REPORT,
    EMOJI_SELLERS,
    PAGE_SIZE_LIST,
    PRODUCT_EDITABLE_FIELDS,
    PRODUCT_UPDATE_QUERIES,
    SHOP_EDITABLE_FIELDS,
    SHOP_UPDATE_QUERIES,
)
from ..database import db
from ..keyboards import kb_add_back, kb_pagination_row
from ..repositories import (
    count_seller_favorites,
    create_product_record,
    delete_product_record,
    get_product_by_id,
    get_product_statistics,
    get_seller_by_id,
    get_seller_statistics,
    get_sellers_owned_by_user,
    is_seller_favorite,
    toggle_seller_favorite,
    user_has_any_seller,
)
from ..services.referrals import referral_stats_text
from ..states import (
    ProductAddStates,
    ProductEditStates,
    RegisterSellerStates,
    ShopEditStates,
    WhatsAppEditStates,
)
from ..utils import (
    ensure_user,
    format_price,
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


# ============================================================================
# CALLBACK PARSING HELPERS
# ============================================================================


def _parse_non_negative_page(data: str) -> int | None:
    parts = data.split(":", 1)
    if len(parts) != 2:
        return None

    page = parse_int(parts[1])
    if page is None or page < 0:
        return None

    return page


def _parse_positive_callback_id(data: str) -> int | None:
    parts = data.split(":", 1)
    if len(parts) != 2:
        return None

    value = parse_int(parts[1])
    if value is None or value < 1:
        return None

    return value


# ============================================================================
# SELLER BROWSING
# ============================================================================


@router.callback_query(F.data.startswith("sellers:"))
async def handle_sellers_list(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    page = _parse_non_negative_page(callback.data)

    if page is None:
        await callback.answer(
            "⚠️ صفحه نامعتبر است.",
            show_alert=True,
        )
        return

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

    seller_id = _parse_positive_callback_id(
        callback.data
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
    answer_text: str | None = None,
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

    rating = seller["rating"] or 0
    review_count = seller["review_count"] or 0

    lines = [
        f"{EMOJI_SELLERS} <b>{seller['name']}</b>",
        "",
        seller["description"] or "بدون توضیحات",
        "",
        f"{EMOJI_CITY} {seller['city_name'] or 'نامشخص'}",
        (
            f"{EMOJI_RATING} "
            f"{float(rating):.1f} "
            f"({review_count} نظر)"
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

    if answer_text:
        await callback.answer(
            answer_text,
            show_alert=True,
        )
    else:
        await callback.answer()


# ============================================================================
# SELLER FAVORITES
# ============================================================================


@router.callback_query(F.data.startswith("sfav:"))
async def handle_seller_favorite_add(
    callback: CallbackQuery,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
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

    await _render_seller_detail(
        callback,
        seller_id,
        answer_text=(
            "❤️ ذخیره شد! هر وقت خواستی از بخش "
            "علاقه‌مندی‌ها پیداش می‌کنی."
        ),
    )


@router.callback_query(F.data.startswith("sunfav:"))
async def handle_seller_favorite_remove(
    callback: CallbackQuery,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
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

    await _render_seller_detail(
        callback,
        seller_id,
        answer_text="از علاقه‌مندی‌ها حذف شد 💔",
    )


# ============================================================================
# SELLER CONTACTS
# ============================================================================


@router.callback_query(F.data.startswith("igclick:"))
async def handle_instagram_click(
    callback: CallbackQuery,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
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
    seller_id = _parse_positive_callback_id(
        callback.data
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
    seller_id = _parse_positive_callback_id(
        callback.data
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


# ============================================================================
# WHATSAPP EDIT
# ============================================================================


@router.callback_query(F.data.startswith("waedit:"))
async def handle_whatsapp_edit_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
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


# ============================================================================
# CLAIM
# ============================================================================


@router.callback_query(F.data.startswith("claim:"))
async def handle_claim(
    callback: CallbackQuery,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
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
        SELECT
            id,
            name,
            status,
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

    if seller["status"] != "UNCLAIMED":
        await callback.answer(
            "⚠️ این فروشگاه قبلاً مالک دارد.",
            show_alert=True,
        )
        return

    if user_id in (
        seller["owner_user_id"],
        seller["created_by_user_id"],
    ):
        await callback.answer(
            "ℹ️ این فروشگاه همین حالا به حساب شما "
            "متصل است.",
            show_alert=True,
        )
        return

    existing = await db.fetchone(
        """
        SELECT id
        FROM seller_claims
        WHERE seller_id = ?
          AND user_id = ?
          AND status = 'PENDING'
        LIMIT 1;
        """,
        (
            seller_id,
            user_id,
        ),
    )

    if existing:
        await callback.answer(
            "⏳ درخواست مالکیت شما قبلاً ثبت شده و "
            "در انتظار بررسی است.",
            show_alert=True,
        )
        return

    await db.execute(
        """
        INSERT INTO seller_claims (
            seller_id,
            user_id,
            status,
            created_at
        )
        VALUES (?, ?, 'PENDING', ?);
        """,
        (
            seller_id,
            user_id,
            now_iso(),
        ),
    )

    await log_audit(
        user_id,
        "seller_claim_requested",
        "seller",
        seller_id,
    )

    if ADMIN_CHAT_ID:
        try:
            bot: Bot = callback.bot
            await bot.send_message(
                ADMIN_CHAT_ID,
                (
                    "📩 <b>درخواست مالکیت جدید</b>\n\n"
                    f"🏪 فروشگاه: {seller['name']}\n"
                    f"🆔 Seller ID: {seller_id}\n"
                    f"👤 User ID: {user_id}"
                ),
            )
        except Exception:
            pass

    await callback.answer(
        "✅ درخواست مالکیت ثبت شد. "
        "بعد از بررسی بهت خبر می‌دیم.",
        show_alert=True,
    )
# ============================================================================
# COMMON SELLER HELPERS
# ============================================================================


async def resolve_single_seller_or_show_picker(
    callback: CallbackQuery,
    user_id: int,
    prefix: str,
) -> Optional[int]:
    sellers = await get_sellers_owned_by_user(user_id)

    if not sellers:
        await callback.answer(
            "⚠️ هنوز فروشگاهی ثبت نکرده‌ای.",
            show_alert=True,
        )
        return None

    if len(sellers) == 1:
        return sellers[0]["id"]

    builder = InlineKeyboardBuilder()

    for seller in sellers:
        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{EMOJI_SELLERS} "
                    f"{seller['name']}"
                ),
                callback_data=f"{prefix}:{seller['id']}",
            )
        )

    kb_add_back(builder, "account")

    await safe_edit(
        callback,
        "🏪 کدوم فروشگاهت رو می‌خوای مدیریت کنی؟",
        builder.as_markup(),
    )
    await callback.answer()

    return None


async def _check_seller_ownership(
    user_id: int,
    seller_id: int,
) -> Optional[dict]:
    seller = await get_seller_by_id(seller_id)

    if not seller:
        return None

    if user_id not in (
        seller["owner_user_id"],
        seller["created_by_user_id"],
    ):
        return None

    return seller


def _seller_name(seller: dict) -> str:
    return seller.get("name") or "فروشگاه"


# ============================================================================
# STORE STATUS
# ============================================================================


@router.callback_query(F.data == "storestatus")
async def handle_store_status(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    user_id = await ensure_user(callback.from_user)

    seller_id = await resolve_single_seller_or_show_picker(
        callback,
        user_id,
        "storestatuspick",
    )

    if seller_id is not None:
        await _render_store_status(
            callback,
            seller_id,
        )


@router.callback_query(F.data.startswith("storestatuspick:"))
async def handle_store_status_picked(
    callback: CallbackQuery,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی به این فروشگاه مجاز نیست.",
            show_alert=True,
        )
        return

    await _render_store_status(
        callback,
        seller_id,
    )


async def _render_store_status(
    callback: CallbackQuery,
    seller_id: int,
    answer_text: str | None = None,
) -> None:
    seller = await get_seller_by_id(seller_id)

    if not seller:
        await callback.answer(
            "⚠️ فروشگاه پیدا نشد.",
            show_alert=True,
        )
        return

    active = (
        bool(seller["is_active"])
        if seller["is_active"] is not None
        else True
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=(
                "🔴 غیرفعال کردن فروشگاه"
                if active
                else "🟢 فعال کردن فروشگاه"
            ),
            callback_data=f"storetoggle:{seller_id}",
        )
    )

    kb_add_back(builder, "account")

    status_text = (
        "🟢 فروشگاه در حال حاضر <b>فعال</b> است."
        if active
        else "🔴 فروشگاه در حال حاضر <b>غیرفعال</b> است."
    )

    await safe_edit(
        callback,
        (
            f"🏪 <b>{_seller_name(seller)}</b>\n\n"
            f"{status_text}\n\n"
            "وقتی فروشگاه غیرفعال باشد، "
            "ارتباطات جدید برای کاربران نمایش داده نمی‌شود."
        ),
        builder.as_markup(),
    )

    if answer_text:
        await callback.answer(
            answer_text,
            show_alert=True,
        )
    else:
        await callback.answer()


@router.callback_query(F.data.startswith("storetoggle:"))
async def handle_store_toggle_active(
    callback: CallbackQuery,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی به این فروشگاه مجاز نیست.",
            show_alert=True,
        )
        return

    current = (
        bool(seller["is_active"])
        if seller["is_active"] is not None
        else True
    )

    await db.execute(
        """
        UPDATE sellers
        SET is_active = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            0 if current else 1,
            now_iso(),
            seller_id,
        ),
    )

    await log_audit(
        user_id,
        "seller_status_changed",
        "seller",
        seller_id,
    )

    await _render_store_status(
        callback,
        seller_id,
        answer_text=(
            "فروشگاه غیرفعال شد 🔴"
            if current
            else "فروشگاه فعال شد 🟢"
        ),
    )


# ============================================================================
# MY SHOP
# ============================================================================


@router.callback_query(F.data == "myshop")
async def handle_my_shop(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    user_id = await ensure_user(callback.from_user)

    seller_id = await resolve_single_seller_or_show_picker(
        callback,
        user_id,
        "shopview",
    )

    if seller_id is not None:
        await _render_shop_view(
            callback,
            seller_id,
        )


@router.callback_query(F.data.startswith("shopview:"))
async def handle_shop_view_picked(
    callback: CallbackQuery,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی به این فروشگاه مجاز نیست.",
            show_alert=True,
        )
        return

    await _render_shop_view(
        callback,
        seller_id,
    )


async def _render_shop_view(
    callback: CallbackQuery,
    seller_id: int,
    answer_text: str | None = None,
) -> None:
    seller = await get_seller_by_id(seller_id)

    if not seller:
        await callback.answer(
            "⚠️ فروشگاه پیدا نشد.",
            show_alert=True,
        )
        return

    active = (
        bool(seller["is_active"])
        if seller["is_active"] is not None
        else True
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="✏️ ویرایش فروشگاه",
            callback_data=f"shopedit:{seller_id}",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="📦 محصولات من",
            callback_data=f"products:{seller_id}",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="📊 آمار فروشگاه",
            callback_data=f"stats:{seller_id}",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=(
                "🔴 غیرفعال کردن"
                if active
                else "🟢 فعال کردن"
            ),
            callback_data=f"storetoggle:{seller_id}",
        )
    )

    kb_add_back(builder, "account")

    await safe_edit(
        callback,
        (
            f"🏪 <b>{_seller_name(seller)}</b>\n\n"
            f"{seller['description'] or 'بدون توضیحات'}\n\n"
            f"{EMOJI_CITY} شهر: "
            f"{seller.get('city_id') or 'نامشخص'}\n"
            f"{status_badge(seller['status'])}"
        ),
        builder.as_markup(),
    )

    if answer_text:
        await callback.answer(
            answer_text,
            show_alert=True,
        )
    else:
        await callback.answer()


# ============================================================================
# SHOP EDIT
# ============================================================================


@router.callback_query(F.data.startswith("shopedit:"))
async def handle_shop_edit_menu(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی به این فروشگاه مجاز نیست.",
            show_alert=True,
        )
        return

    await state.clear()

    builder = InlineKeyboardBuilder()

    for field, title in SHOP_EDITABLE_FIELDS.items():
        builder.row(
            InlineKeyboardButton(
                text=f"✏️ {title}",
                callback_data=f"shopfield:{seller_id}:{field}",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="📍 تغییر شهر",
            callback_data=f"shopcity:{seller_id}",
        )
    )

    kb_add_back(
        builder,
        f"shopview:{seller_id}",
    )

    await safe_edit(
        callback,
        f"✏️ <b>ویرایش {_seller_name(seller)}</b>\n\n"
        "قسمتی که می‌خوای تغییر بدی رو انتخاب کن:",
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("shopfield:"))
async def handle_shop_edit_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    parts = callback.data.split(":", 2)

    if len(parts) != 3:
        await callback.answer(
            "⚠️ اطلاعات نامعتبر است.",
            show_alert=True,
        )
        return

    seller_id = parse_int(parts[1])
    field = parts[2]

    if (
        seller_id is None
        or seller_id < 1
        or field not in SHOP_EDITABLE_FIELDS
    ):
        await callback.answer(
            "⚠️ گزینه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی به این فروشگاه مجاز نیست.",
            show_alert=True,
        )
        return

    await state.update_data(
        shop_seller_id=seller_id,
        shop_field=field,
    )

    await state.set_state(
        ShopEditStates.waiting_value
    )

    builder = InlineKeyboardBuilder()
    kb_add_back(
        builder,
        f"shopedit:{seller_id}",
    )

    current_value = seller.get(field)

    await safe_edit(
        callback,
        (
            f"✏️ <b>{SHOP_EDITABLE_FIELDS[field]}</b>\n\n"
            f"مقدار فعلی:\n"
            f"{current_value or 'ثبت نشده'}\n\n"
            "مقدار جدید رو بفرست:"
        ),
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("shopcity:"))
async def handle_shop_city_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی به این فروشگاه مجاز نیست.",
            show_alert=True,
        )
        return

    cities = await db.fetchall(
        """
        SELECT id, name
        FROM cities
        ORDER BY name;
        """
    )

    builder = InlineKeyboardBuilder()

    for city in cities:
        builder.row(
            InlineKeyboardButton(
                text=f"{EMOJI_CITY} {city['name']}",
                callback_data=f"shopcitypick:{seller_id}:{city['id']}",
            )
        )

    kb_add_back(
        builder,
        f"shopedit:{seller_id}",
    )

    await safe_edit(
        callback,
        "📍 شهر جدید فروشگاه رو انتخاب کن:",
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("shopcitypick:"))
async def handle_shop_edit_city_pick(
    callback: CallbackQuery,
) -> None:
    parts = callback.data.split(":", 2)

    if len(parts) != 3:
        await callback.answer(
            "⚠️ اطلاعات نامعتبر است.",
            show_alert=True,
        )
        return

    seller_id = parse_int(parts[1])
    city_id = parse_int(parts[2])

    if (
        seller_id is None
        or seller_id < 1
        or city_id is None
        or city_id < 1
    ):
        await callback.answer(
            "⚠️ اطلاعات نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    city = await db.fetchone(
        "SELECT id, name FROM cities WHERE id = ?;",
        (city_id,),
    )

    if not city:
        await callback.answer(
            "⚠️ شهر پیدا نشد.",
            show_alert=True,
        )
        return

    await db.execute(
        """
        UPDATE sellers
        SET city_id = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            city_id,
            now_iso(),
            seller_id,
        ),
    )

    await log_audit(
        user_id,
        "seller_city_updated",
        "seller",
        seller_id,
    )

    await _render_shop_view(
        callback,
        seller_id,
        answer_text="شهر فروشگاه تغییر کرد ✅",
    )


@router.message(
    StateFilter(
        ShopEditStates.waiting_value
    )
)
async def handle_shop_edit_value(
    message: Message,
    state: FSMContext,
) -> None:
    if (message.text or "").strip() == "/start":
        await state.clear()
        await ensure_user(message.from_user)
        return

    data = await state.get_data()

    seller_id = data.get("shop_seller_id")
    field = data.get("shop_field")

    await state.clear()

    if not seller_id or field not in SHOP_EDITABLE_FIELDS:
        await message.answer(
            "⚠️ فرآیند ویرایش منقضی شده."
        )
        return

    user_id = await ensure_user(message.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await message.answer(
            "⚠️ دسترسی به این فروشگاه مجاز نیست."
        )
        return

    value = (
        message.text
        if message.text is not None
        else ""
    ).strip()

    if not value:
        await message.answer(
            "⚠️ مقدار نمی‌تواند خالی باشد."
        )
        return

    query = SHOP_UPDATE_QUERIES.get(field)

    if not query:
        await message.answer(
            "⚠️ این فیلد قابل ویرایش نیست."
        )
        return

    await db.execute(
        query,
        (
            value,
            now_iso(),
            seller_id,
        ),
    )

    await log_audit(
        user_id,
        "seller_field_updated",
        "seller",
        seller_id,
    )

    builder = InlineKeyboardBuilder()
    kb_add_back(
        builder,
        f"shopview:{seller_id}",
    )

    await message.answer(
        f"✅ {SHOP_EDITABLE_FIELDS[field]} با موفقیت "
        "به‌روزرسانی شد.",
        reply_markup=builder.as_markup(),
    )
    if not query:
        await message.answer(
            "⚠️ این فیلد قابل ویرایش نیست."
        )
        return

    await db.execute(
        query,
        (
            value,
            now_iso(),
            seller_id,
        ),
    )

    await log_audit(
        user_id,
        "seller_field_updated",
        "seller",
        seller_id,
    )

    builder = InlineKeyboardBuilder()
    kb_add_back(
        builder,
        f"shopview:{seller_id}",
    )

    await message.answer(
        f"✅ {SHOP_EDITABLE_FIELDS[field]} فروشگاه "
        "با موفقیت تغییر کرد.",
        reply_markup=builder.as_markup(),
    )


# ============================================================================
# MY PRODUCTS
# ============================================================================


@router.callback_query(F.data.startswith("products:"))
async def handle_my_products(
    callback: CallbackQuery,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    await _render_product_list(
        callback,
        seller_id,
    )


@router.callback_query(F.data.startswith("productlist:"))
async def handle_product_list_picked(
    callback: CallbackQuery,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    await _render_product_list(
        callback,
        seller_id,
    )


async def _render_product_list(
    callback: CallbackQuery,
    seller_id: int,
    answer_text: str | None = None,
) -> None:
    seller = await get_seller_by_id(seller_id)

    if not seller:
        await callback.answer(
            "⚠️ فروشگاه پیدا نشد.",
            show_alert=True,
        )
        return

    products = await db.fetchall(
        """
        SELECT *
        FROM products
        WHERE seller_id = ?
        ORDER BY created_at DESC, id DESC;
        """,
        (seller_id,),
    )

    builder = InlineKeyboardBuilder()

    if products:
        for product in products:
            price = format_price(product["price"])

            builder.row(
                InlineKeyboardButton(
                    text=(
                        f"📦 {product['name']} "
                        f"— {price}"
                    ),
                    callback_data=f"productedit:{product['id']}",
                )
            )
    else:
        builder.row(
            InlineKeyboardButton(
                text="📦 هنوز محصولی نداری",
                callback_data=f"productadd:{seller_id}",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="➕ افزودن محصول",
            callback_data=f"productadd:{seller_id}",
        )
    )

    kb_add_back(
        builder,
        f"shopview:{seller_id}",
    )

    await safe_edit(
        callback,
        (
            f"📦 <b>محصولات {_seller_name(seller)}</b>\n\n"
            f"تعداد محصولات: {len(products)}"
        ),
        builder.as_markup(),
    )

    if answer_text:
        await callback.answer(
            answer_text,
            show_alert=True,
        )
    else:
        await callback.answer()


# ============================================================================
# PRODUCT ADD
# ============================================================================


@router.callback_query(F.data.startswith("productadd:"))
async def handle_product_add_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    await state.clear()
    await state.update_data(
        product_seller_id=seller_id
    )
    await state.set_state(
        ProductAddStates.waiting_name
    )

    builder = InlineKeyboardBuilder()
    kb_add_back(
        builder,
        f"products:{seller_id}",
    )

    await safe_edit(
        callback,
        "📦 <b>افزودن محصول</b>\n\n"
        "اسم محصول رو بفرست:",
        builder.as_markup(),
    )

    await callback.answer()


@router.message(
    StateFilter(
        ProductAddStates.waiting_name
    )
)
async def handle_product_add_name(
    message: Message,
    state: FSMContext,
) -> None:
    if (message.text or "").strip() == "/start":
        await state.clear()
        return

    name = (message.text or "").strip()

    if not name:
        await message.answer(
            "⚠️ اسم محصول نمی‌تواند خالی باشد."
        )
        return

    await state.update_data(
        product_name=name
    )
    await state.set_state(
        ProductAddStates.waiting_description
    )

    await message.answer(
        "📝 توضیحات محصول رو بفرست.\n"
        "اگر توضیحی نداره بنویس: ندارد"
    )


@router.message(
    StateFilter(
        ProductAddStates.waiting_description
    )
)
async def handle_product_add_description(
    message: Message,
    state: FSMContext,
) -> None:
    description = (message.text or "").strip()

    if description == "ندارد":
        description = ""

    await state.update_data(
        product_description=description
    )
    await state.set_state(
        ProductAddStates.waiting_price
    )

    await message.answer(
        f"{EMOJI_PRICE} قیمت محصول رو به تومان بفرست:"
    )


@router.message(
    StateFilter(
        ProductAddStates.waiting_price
    )
)
async def handle_product_add_price(
    message: Message,
    state: FSMContext,
) -> None:
    price = parse_int(
        (message.text or "").replace(",", "")
    )

    if price is None or price < 0:
        await message.answer(
            "⚠️ قیمت معتبر نیست. فقط عدد بفرست."
        )
        return

    await state.update_data(
        product_price=price
    )
    await state.set_state(
        ProductAddStates.waiting_old_price
    )

    await message.answer(
        "💰 اگر قیمت قبلی دارد، آن را بفرست.\n"
        "اگر ندارد بنویس: ندارد"
    )


@router.message(
    StateFilter(
        ProductAddStates.waiting_old_price
    )
)
async def handle_product_add_old_price(
    message: Message,
    state: FSMContext,
) -> None:
    raw = (message.text or "").strip()

    old_price = None

    if raw not in (
        "",
        "ندارد",
        "-",
        "ندارم",
    ):
        old_price = parse_int(
            raw.replace(",", "")
        )

        if old_price is None or old_price < 0:
            await message.answer(
                "⚠️ قیمت قبلی معتبر نیست."
            )
            return

    await state.update_data(
        product_old_price=old_price
    )
    await state.set_state(
        ProductAddStates.waiting_image_url
    )

    await message.answer(
        "🖼️ لینک تصویر محصول رو بفرست.\n"
        "اگر تصویر نداره بنویس: ندارد"
    )


@router.message(
    StateFilter(
        ProductAddStates.waiting_image_url
    )
)
async def handle_product_add_image(
    message: Message,
    state: FSMContext,
) -> None:
    raw = (message.text or "").strip()

    image_url = None

    if raw not in (
        "",
        "ندارد",
        "-",
        "ندارم",
    ):
        image_url = raw

    await state.update_data(
        product_image_url=image_url
    )

    await _finish_product_add(
        message,
        state,
    )


@router.message(
    StateFilter(
        ProductAddStates.waiting_image_url
    ),
    F.text.in_({"ندارد", "-", "ندارم"}),
)
async def handle_product_add_skip(
    message: Message,
    state: FSMContext,
) -> None:
    await state.update_data(
        product_image_url=None
    )

    await _finish_product_add(
        message,
        state,
    )


async def _finish_product_add(
    message: Message,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    await state.clear()

    seller_id = data.get("product_seller_id")

    if not seller_id:
        await message.answer(
            "⚠️ فرآیند افزودن محصول منقضی شده."
        )
        return

    user_id = await ensure_user(message.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await message.answer(
            "⚠️ دسترسی مجاز نیست."
        )
        return

    product_id = await create_product_record(
        seller_id=seller_id,
        name=data["product_name"],
        description=data.get("product_description"),
        price=data.get("product_price"),
        old_price=data.get("product_old_price"),
        image_url=data.get("product_image_url"),
    )

    await log_audit(
        user_id,
        "product_created",
        "product",
        product_id,
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="📦 مشاهده محصولات",
            callback_data=f"products:{seller_id}",
        )
    )

    await message.answer(
        f"✅ محصول «{data['product_name']}» با موفقیت اضافه شد.",
        reply_markup=builder.as_markup(),
    )


# ============================================================================
# PRODUCT EDIT
# ============================================================================


@router.callback_query(F.data.startswith("productedit:"))
async def handle_product_edit_menu(
    callback: CallbackQuery,
) -> None:
    product_id = _parse_positive_callback_id(
        callback.data
    )

    if product_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    product = await get_product_by_id(product_id)

    if not product:
        await callback.answer(
            "⚠️ محصول پیدا نشد.",
            show_alert=True,
        )
        return

    seller = await _check_seller_ownership(
        user_id,
        product["seller_id"],
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    builder = InlineKeyboardBuilder()

    for field, title in PRODUCT_EDITABLE_FIELDS.items():
        builder.row(
            InlineKeyboardButton(
                text=f"✏️ {title}",
                callback_data=f"productfield:{product_id}:{field}",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="📦 وضعیت موجودی",
            callback_data=f"productstock:{product_id}",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🗑 حذف محصول",
            callback_data=f"productdelete:{product_id}",
        )
    )

    kb_add_back(
        builder,
        f"products:{product['seller_id']}",
    )

    await safe_edit(
        callback,
        (
            f"📦 <b>{product['name']}</b>\n\n"
            f"قیمت: {format_price(product['price'])}\n"
            f"وضعیت: {product['stock_status']}"
        ),
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("productfield:"))
async def handle_product_field_edit_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    parts = callback.data.split(":", 2)

    if len(parts) != 3:
        await callback.answer(
            "⚠️ اطلاعات نامعتبر است.",
            show_alert=True,
        )
        return

    product_id = parse_int(parts[1])
    field = parts[2]

    if (
        product_id is None
        or product_id < 1
        or field not in PRODUCT_EDITABLE_FIELDS
    ):
        await callback.answer(
            "⚠️ گزینه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    product = await get_product_by_id(product_id)

    if not product:
        await callback.answer(
            "⚠️ محصول پیدا نشد.",
            show_alert=True,
        )
        return

    seller = await _check_seller_ownership(
        user_id,
        product["seller_id"],
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    await state.update_data(
        product_id=product_id,
        product_field=field,
    )

    await state.set_state(
        ProductEditStates.waiting_value
    )

    builder = InlineKeyboardBuilder()
    kb_add_back(
        builder,
        f"productedit:{product_id}",
    )

    current_value = product.get(field)

    await safe_edit(
        callback,
        (
            f"✏️ <b>{PRODUCT_EDITABLE_FIELDS[field]}</b>\n\n"
            f"مقدار فعلی:\n"
            f"{current_value or 'ثبت نشده'}\n\n"
            "مقدار جدید رو بفرست:"
        ),
        builder.as_markup(),
    )

    await callback.answer()


@router.message(
    StateFilter(
        ProductEditStates.waiting_value
    )
)
async def handle_product_field_edit_value(
    message: Message,
    state: FSMContext,
) -> None:
    if (message.text or "").strip() == "/start":
        await state.clear()
        return

    data = await state.get_data()
    product_id = data.get("product_id")
    field = data.get("product_field")

    await state.clear()

    if not product_id or field not in PRODUCT_EDITABLE_FIELDS:
        await message.answer(
            "⚠️ فرآیند ویرایش منقضی شده."
        )
        return

    user_id = await ensure_user(message.from_user)

    product = await get_product_by_id(product_id)

    if not product:
        await message.answer(
            "⚠️ محصول پیدا نشد."
        )
        return

    seller = await _check_seller_ownership(
        user_id,
        product["seller_id"],
    )

    if not seller:
        await message.answer(
            "⚠️ دسترسی مجاز نیست."
        )
        return

    value = (message.text or "").strip()

    if not value:
        await message.answer(
            "⚠️ مقدار نمی‌تواند خالی باشد."
        )
        return

    if field in ("price", "old_price"):
        parsed = parse_int(
            value.replace(",", "")
        )

        if parsed is None or parsed < 0:
            await message.answer(
                "⚠️ قیمت معتبر نیست."
            )
            return

        value = parsed

    query = PRODUCT_UPDATE_QUERIES.get(field)

    if not query:
        await message.answer(
            "⚠️ این فیلد قابل ویرایش نیست."
        )
        return

    await db.execute(
        query,
        (
            value,
            now_iso(),
            product_id,
        ),
    )

    await log_audit(
        user_id,
        "product_field_updated",
        "product",
        product_id,
    )

    builder = InlineKeyboardBuilder()

    kb_add_back(
        builder,
        f"productedit:{product_id}",
    )

    await message.answer(
        f"✅ {PRODUCT_EDITABLE_FIELDS[field]} "
        "با موفقیت تغییر کرد.",
        reply_markup=builder.as_markup(),
    )


# ============================================================================
# PRODUCT STOCK
# ============================================================================


@router.callback_query(F.data.startswith("productstock:"))
async def handle_product_stock_menu(
    callback: CallbackQuery,
) -> None:
    product_id = _parse_positive_callback_id(
        callback.data
    )

    if product_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    product = await get_product_by_id(product_id)

    if not product:
        await callback.answer(
            "⚠️ محصول پیدا نشد.",
            show_alert=True,
        )
        return

    seller = await _check_seller_ownership(
        user_id,
        product["seller_id"],
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="🟢 موجود",
            callback_data=f"stockset:{product_id}:IN_STOCK",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🟡 کمبود موجودی",
            callback_data=f"stockset:{product_id}:LOW_STOCK",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🔴 ناموجود",
            callback_data=f"stockset:{product_id}:OUT_OF_STOCK",
        )
    )

    kb_add_back(
        builder,
        f"productedit:{product_id}",
    )

    await safe_edit(
        callback,
        (
            f"📦 <b>وضعیت موجودی</b>\n\n"
            f"محصول: {product['name']}\n"
            f"وضعیت فعلی: {product['stock_status']}"
        ),
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("stockset:"))
async def handle_product_stock_set(
    callback: CallbackQuery,
) -> None:
    parts = callback.data.split(":", 2)

    if len(parts) != 3:
        await callback.answer(
            "⚠️ اطلاعات نامعتبر است.",
            show_alert=True,
        )
        return

    product_id = parse_int(parts[1])
    stock_status = parts[2]

    allowed_statuses = {
        "IN_STOCK",
        "LOW_STOCK",
        "OUT_OF_STOCK",
    }

    if (
        product_id is None
        or product_id < 1
        or stock_status not in allowed_statuses
    ):
        await callback.answer(
            "⚠️ وضعیت نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    product = await get_product_by_id(product_id)

    if not product:
        await callback.answer(
            "⚠️ محصول پیدا نشد.",
            show_alert=True,
        )
        return

    seller = await _check_seller_ownership(
        user_id,
        product["seller_id"],
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    await db.execute(
        """
        UPDATE products
        SET stock_status = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            stock_status,
            now_iso(),
            product_id,
        ),
    )

    await log_audit(
        user_id,
        "product_stock_updated",
        "product",
        product_id,
    )

    status_labels = {
        "IN_STOCK": "🟢 موجود",
        "LOW_STOCK": "🟡 کمبود موجودی",
        "OUT_OF_STOCK": "🔴 ناموجود",
    }

    await callback.answer(
        f"وضعیت موجودی تغییر کرد: "
        f"{status_labels[stock_status]}",
        show_alert=True,
    )

    await handle_product_edit_menu(
        callback,
    )


@router.callback_query(F.data.startswith("productdelete:"))
async def handle_product_delete_start(
    callback: CallbackQuery,
) -> None:
    product_id = _parse_positive_callback_id(
        callback.data
    )

    if product_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    product = await get_product_by_id(product_id)

    if not product:
        await callback.answer(
            "⚠️ محصول پیدا نشد.",
            show_alert=True,
        )
        return

    seller = await _check_seller_ownership(
        user_id,
        product["seller_id"],
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="❌ بله، حذف شود",
            callback_data=f"productdeleteconfirm:{product_id}",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="↩️ انصراف",
            callback_data=f"productedit:{product_id}",
        )
    )

    await safe_edit(
        callback,
        (
            f"🗑 <b>حذف محصول</b>\n\n"
            f"مطمئنی می‌خوای «{product['name']}» "
            "رو حذف کنی؟\n\n"
            "این عملیات قابل بازگشت نیست."
        ),
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("productdeleteconfirm:"))
async def handle_product_delete_confirmed(
    callback: CallbackQuery,
) -> None:
    product_id = _parse_positive_callback_id(
        callback.data
    )

    if product_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    product = await get_product_by_id(product_id)

    if not product:
        await callback.answer(
            "⚠️ محصول پیدا نشد.",
            show_alert=True,
        )
        return

    seller = await _check_seller_ownership(
        user_id,
        product["seller_id"],
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    seller_id = product["seller_id"]

    await delete_product_record(
        product_id,
    )

    await log_audit(
        user_id,
        "product_deleted",
        "product",
        product_id,
    )

    await _render_product_list(
        callback,
        seller_id,
        answer_text="محصول با موفقیت حذف شد 🗑️",
    )
    builder.row(
        InlineKeyboardButton(
            text="🔴 ناموجود",
            callback_data=f"stockset:{product_id}:OUT_OF_STOCK",
        )
    )

    kb_add_back(
        builder,
        f"productedit:{product_id}",
    )

    await safe_edit(
        callback,
        (
            f"📦 وضعیت موجودی «{product['name']}»\n\n"
            f"وضعیت فعلی: {product['stock_status']}"
        ),
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("stockset:"))
async def handle_product_stock_set(
    callback: CallbackQuery,
) -> None:
    parts = callback.data.split(":")

    if len(parts) != 3:
        await callback.answer(
            "⚠️ اطلاعات نامعتبر است.",
            show_alert=True,
        )
        return

    product_id = parse_int(parts[1])
    stock_status = parts[2]

    if (
        product_id is None
        or product_id < 1
        or stock_status not in (
            "AVAILABLE",
            "OUT_OF_STOCK",
        )
    ):
        await callback.answer(
            "⚠️ وضعیت نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    product = await get_product_by_id(product_id)

    if not product:
        await callback.answer(
            "⚠️ محصول پیدا نشد.",
            show_alert=True,
        )
        return

    seller = await _check_seller_ownership(
        user_id,
        product["seller_id"],
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    await db.execute(
        """
        UPDATE products
        SET stock_status = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            stock_status,
            now_iso(),
            product_id,
        ),
    )

    await log_audit(
        user_id,
        "product_stock_updated",
        "product",
        product_id,
    )

    await handle_product_edit_menu(
        callback,
        answer_text="وضعیت موجودی تغییر کرد ✅",
    )


# ============================================================================
# PRODUCT DELETE
# ============================================================================


@router.callback_query(F.data.startswith("productdelete:"))
async def handle_product_delete_confirm_screen(
    callback: CallbackQuery,
) -> None:
    product_id = _parse_positive_callback_id(
        callback.data
    )

    if product_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    product = await get_product_by_id(product_id)

    if not product:
        await callback.answer(
            "⚠️ محصول پیدا نشد.",
            show_alert=True,
        )
        return

    seller = await _check_seller_ownership(
        user_id,
        product["seller_id"],
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="❌ بله، حذف شود",
            callback_data=f"productdeleteconfirm:{product_id}",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="↩️ لغو",
            callback_data=f"productedit:{product_id}",
        )
    )

    await safe_edit(
        callback,
        (
            f"🗑 <b>حذف محصول</b>\n\n"
            f"مطمئنی می‌خوای «{product['name']}» رو حذف کنی؟\n\n"
            "این عملیات قابل بازگشت نیست."
        ),
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("productdeletecancel:"))
async def handle_product_delete_cancel(
    callback: CallbackQuery,
) -> None:
    product_id = _parse_positive_callback_id(
        callback.data
    )

    if product_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    await handle_product_edit_menu(
        callback
    )


@router.callback_query(F.data.startswith("productdeleteconfirm:"))
async def handle_product_delete_confirmed(
    callback: CallbackQuery,
) -> None:
    product_id = _parse_positive_callback_id(
        callback.data
    )

    if product_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    product = await get_product_by_id(product_id)

    if not product:
        await callback.answer(
            "⚠️ محصول قبلاً حذف شده است.",
            show_alert=True,
        )
        return

    seller = await _check_seller_ownership(
        user_id,
        product["seller_id"],
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    await delete_product_record(product_id)

    await log_audit(
        user_id,
        "product_deleted",
        "product",
        product_id,
    )

    await _render_product_list(
        callback,
        product["seller_id"],
        answer_text="محصول حذف شد 🗑️",
    )


# ============================================================================
# SELLER STATISTICS
# ============================================================================


@router.callback_query(F.data.startswith("stats:"))
async def handle_my_stats(
    callback: CallbackQuery,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    await _render_stats_home(
        callback,
        seller_id,
    )


@router.callback_query(F.data.startswith("statspick:"))
async def handle_stats_home_picked(
    callback: CallbackQuery,
) -> None:
    seller_id = _parse_positive_callback_id(
        callback.data
    )

    if seller_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    await _render_stats_home(
        callback,
        seller_id,
    )


async def _render_stats_home(
    callback: CallbackQuery,
    seller_id: int,
) -> None:
    user_id = await ensure_user(callback.from_user)

    seller = await _check_seller_ownership(
        user_id,
        seller_id,
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    stats = await get_seller_statistics(
        seller_id
    )

    builder = InlineKeyboardBuilder()

    products = await db.fetchall(
        """
        SELECT id, name
        FROM products
        WHERE seller_id = ?
        ORDER BY created_at DESC;
        """,
        (seller_id,),
    )

    for product in products:
        builder.row(
            InlineKeyboardButton(
                text=f"📦 {product['name']}",
                callback_data=f"statsproduct:{product['id']}",
            )
        )

    kb_add_back(
        builder,
        f"shopview:{seller_id}",
    )

    await safe_edit(
        callback,
        (
            f"📊 <b>آمار {_seller_name(seller)}</b>\n\n"
            f"👁 بازدید فروشگاه: {stats['views']}\n"
            f"📦 تعداد محصولات: {stats['product_count']}\n"
            f"🟢 محصولات موجود: {stats['active_product_count']}\n"
            f"👁 بازدید محصولات: {stats['total_product_views']}\n"
            f"❤️ علاقه‌مندی‌ها: {stats['favorite_count']}\n"
            f"📨 درخواست‌ها: {stats['request_count']}\n"
            f"🛒 سفارش‌های تکمیل‌شده: "
            f"{stats['completed_order_count']}\n"
            f"💰 درآمد تکمیل‌شده: "
            f"{format_price(stats['completed_order_revenue'])}"
        ),
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("statsproduct:"))
async def handle_stats_product(
    callback: CallbackQuery,
) -> None:
    product_id = _parse_positive_callback_id(
        callback.data
    )

    if product_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(callback.from_user)

    product = await get_product_by_id(product_id)

    if not product:
        await callback.answer(
            "⚠️ محصول پیدا نشد.",
            show_alert=True,
        )
        return

    seller = await _check_seller_ownership(
        user_id,
        product["seller_id"],
    )

    if not seller:
        await callback.answer(
            "⚠️ دسترسی مجاز نیست.",
            show_alert=True,
        )
        return

    stats = await get_product_statistics(
        product_id
    )

    builder = InlineKeyboardBuilder()

    kb_add_back(
        builder,
        f"stats:{product['seller_id']}",
    )

    await safe_edit(
        callback,
        (
            f"📊 <b>آمار {product['name']}</b>\n\n"
            f"👁 بازدید: {stats['views']}\n"
            f"❤️ علاقه‌مندی‌ها: {stats['favorite_count']}\n"
            f"🛒 سفارش تکمیل‌شده: "
            f"{stats['completed_order_count']}\n"
            f"📦 تعداد فروخته‌شده: "
            f"{stats['completed_units_sold']}"
        ),
        builder.as_markup(),
    )

    await callback.answer()


# ============================================================================
# SELLER REGISTRATION
# ============================================================================


@router.callback_query(F.data == "registerseller")
async def handle_register_seller_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    await state.set_state(
        RegisterSellerStates.name
    )

    builder = InlineKeyboardBuilder()
    kb_add_back(builder, "account")

    await safe_edit(
        callback,
        "🏪 <b>ثبت فروشگاه</b>\n\n"
        "اسم فروشگاهت رو بفرست:",
        builder.as_markup(),
    )

    await callback.answer()


@router.message(
    StateFilter(
        RegisterSellerStates.name
    )
)
async def handle_register_name(
    message: Message,
    state: FSMContext,
) -> None:
    name = (message.text or "").strip()

    if not name:
        await message.answer(
            "⚠️ اسم فروشگاه نمی‌تواند خالی باشد."
        )
        return

    await state.update_data(
        register_name=name
    )

    await state.set_state(
        RegisterSellerStates.description
    )

    await message.answer(
        "📝 توضیحات فروشگاه رو بفرست.\n"
        "اگر توضیح نداری بنویس: ندارد"
    )


@router.message(
    StateFilter(
        RegisterSellerStates.description
    )
)
async def handle_register_description(
    message: Message,
    state: FSMContext,
) -> None:
    description = (message.text or "").strip()

    if description == "ندارد":
        description = ""

    await state.update_data(
        register_description=description
    )

    await state.set_state(
        RegisterSellerStates.city
    )

    cities = await db.fetchall(
        """
        SELECT id, name
        FROM cities
        ORDER BY name;
        """
    )

    builder = InlineKeyboardBuilder()

    for city in cities:
        builder.row(
            InlineKeyboardButton(
                text=f"{EMOJI_CITY} {city['name']}",
                callback_data=f"registercity:{city['id']}",
            )
        )

    await message.answer(
        "📍 شهر فروشگاه رو انتخاب کن:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("registercity:"))
async def handle_pick_city(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    city_id = _parse_positive_callback_id(
        callback.data
    )

    if city_id is None:
        await callback.answer(
            "⚠️ شهر نامعتبر است.",
            show_alert=True,
        )
        return

    city = await db.fetchone(
        "SELECT id, name FROM cities WHERE id = ?;",
        (city_id,),
    )

    if not city:
        await callback.answer(
            "⚠️ شهر پیدا نشد.",
            show_alert=True,
        )
        return

    await state.update_data(
        register_city_id=city_id
    )

    await state.set_state(
        RegisterSellerStates.instagram
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="⏭ رد کردن",
            callback_data="registerskip:instagram",
        )
    )

    await safe_edit(
        callback,
        "📸 آیدی یا لینک اینستاگرام فروشگاه رو بفرست:",
        builder.as_markup(),
    )

    await callback.answer()


@router.message(
    StateFilter(
        RegisterSellerStates.instagram
    )
)
async def handle_register_instagram(
    message: Message,
    state: FSMContext,
) -> None:
    value = (message.text or "").strip()

    await state.update_data(
        register_instagram=value
    )

    await state.set_state(
        RegisterSellerStates.telegram
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="⏭ رد کردن",
            callback_data="registerskip:telegram",
        )
    )

    await message.answer(
        "✈️ آیدی یا لینک تلگرام فروشگاه رو بفرست:",
        reply_markup=builder.as_markup(),
    )


@router.message(
    StateFilter(
        RegisterSellerStates.telegram
    )
)
async def handle_register_telegram(
    message: Message,
    state: FSMContext,
) -> None:
    value = (message.text or "").strip()

    await state.update_data(
        register_telegram=value
    )

    await state.set_state(
        RegisterSellerStates.website
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="⏭ رد کردن",
            callback_data="registerskip:website",
        )
    )

    await message.answer(
        "🌐 لینک وب‌سایت فروشگاه رو بفرست:",
        reply_markup=builder.as_markup(),
    )


@router.message(
    StateFilter(
        RegisterSellerStates.website
    )
)
async def handle_register_website(
    message: Message,
    state: FSMContext,
) -> None:
    value = (message.text or "").strip()

    await state.update_data(
        register_website=value
    )

    await _finish_register_seller(
        message,
        state,
    )


@router.callback_query(F.data.startswith("registerskip:"))
async def handle_register_skip(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    parts = callback.data.split(":", 1)

    if len(parts) != 2:
        await callback.answer(
            "⚠️ گزینه نامعتبر است.",
            show_alert=True,
        )
        return

    field = parts[1]

    if field == "instagram":
        await state.update_data(
            register_instagram=None
        )
        await state.set_state(
            RegisterSellerStates.telegram
        )

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="⏭ رد کردن",
                callback_data="registerskip:telegram",
            )
        )

        await safe_edit(
            callback,
            "✈️ آیدی یا لینک تلگرام فروشگاه رو بفرست:",
            builder.as_markup(),
        )

    elif field == "telegram":
        await state.update_data(
            register_telegram=None
        )
        await state.set_state(
            RegisterSellerStates.website
        )

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="⏭ رد کردن",
                callback_data="registerskip:website",
            )
        )

        await safe_edit(
            callback,
            "🌐 لینک وب‌سایت فروشگاه رو بفرست:",
            builder.as_markup(),
        )

    elif field == "website":
        await state.update_data(
            register_website=None
        )

        await _finish_register_seller(
            callback.message,
            state,
        )

    else:
        await callback.answer(
            "⚠️ گزینه نامعتبر است.",
            show_alert=True,
        )
        return

    await callback.answer()


async def _finish_register_seller(
    message: Message,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    await state.clear()

    user_id = await ensure_user(
        message.from_user
    )

    existing = await db.fetchone(
        """
        SELECT id
        FROM sellers
        WHERE (
            owner_user_id = ?
            OR created_by_user_id = ?
        )
        AND status != 'REJECTED'
        LIMIT 1;
        """,
        (
            user_id,
            user_id,
        ),
    )

    if existing:
        await message.answer(
            "⚠️ شما قبلاً یک فروشگاه ثبت کرده‌اید."
        )
        return

    now = now_iso()

    cur = await db.execute(
        """
        INSERT INTO sellers (
            name,
            description,
            city_id,
            instagram,
            telegram,
            website,
            owner_user_id,
            created_by_user_id,
            status,
            is_active,
            rating,
            review_count,
            views,
            created_at,
            updated_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, 'UNCLAIMED', 1, 0, 0, 0, ?, ?
        );
        """,
        (
            data.get("register_name"),
            data.get("register_description"),
            data.get("register_city_id"),
            data.get("register_instagram"),
            data.get("register_telegram"),
            data.get("register_website"),
            user_id,
            user_id,
            now,
            now,
        ),
    )

    seller_id = cur.lastrowid

    await log_audit(
        user_id,
        "seller_created",
        "seller",
        seller_id,
    )

    await message.answer(
        "🎉 <b>فروشگاهت با موفقیت ثبت شد!</b>\n\n"
        f"🏪 {data.get('register_name')}\n\n"
        "حالا می‌تونی محصولاتت رو اضافه کنی و "
        "فروشگاهت رو مدیریت کنی."
    )

    try:
        stats_text = await referral_stats_text(
            seller_id
        )

        if stats_text:
            await message.answer(
                stats_text
            )
    except Exception:
        pass