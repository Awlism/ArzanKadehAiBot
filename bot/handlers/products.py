# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Product handlers
"""

from typing import Optional

import aiosqlite
from aiogram import F, Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import ADMIN_CHAT_ID
from ..constants import (
    EMOJI_CITY,
    EMOJI_COMPARE,
    EMOJI_FAVORITES,
    EMOJI_PRICE,
    EMOJI_PRODUCT,
    EMOJI_RATING,
    EMOJI_REPORT,
    EMOJI_SELLERS,
    PAGE_SIZE_LIST,
)
from ..database import db
from ..keyboards import kb_add_back, kb_pagination_row
from ..repositories import has_open_report
from ..services.notifications import notify_user
from ..states import ReportStates, ReviewStates
from ..utils import (
    ensure_user,
    format_price,
    is_admin_telegram_id,
    log_audit,
    log_event,
    now_iso,
    parse_int,
    restart_requested,
    safe_edit,
    send_admin_dm,
    status_badge,
)


router = Router(name="products")


REPORT_REASONS = {
    "scam": "🚨 کلاهبرداری",
    "fake": "❌ محصول یا اطلاعات جعلی",
    "inappropriate": "⚠️ محتوای نامناسب",
    "wrong_info": "📝 اطلاعات نادرست",
    "other": "🔹 سایر",
}


REQUEST_STATUS_LABELS = {
    "PENDING": "🟡 در حال بررسی",
    "APPROVED": "🟢 تأیید شده",
    "REJECTED": "🔴 رد شده",
    "ACTIVE": "🟢 فعال",
    "EXPIRED": "⚪ منقضی شده",
}


def _is_admin(callback: CallbackQuery) -> bool:
    return is_admin_telegram_id(
        callback.from_user.id,
        ADMIN_CHAT_ID,
    )


# ======================================================================
# PRODUCT DETAIL
# ======================================================================

@router.callback_query(F.data.startswith("product:"))
async def handle_product_detail(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await _render_product_detail(callback)


async def _render_product_detail(
    callback: CallbackQuery,
) -> None:
    product_id = parse_int(
        callback.data.split(":")[1]
    )

    if product_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    product = await db.fetchone(
        """
        SELECT
            p.*,
            s.name AS seller_name,
            s.status AS seller_status,
            c.name AS city_name
        FROM products p
        JOIN sellers s
            ON s.id = p.seller_id
        LEFT JOIN cities c
            ON c.id = s.city_id
        WHERE p.id = ?
          AND COALESCE(s.is_active, 1) = 1;
        """,
        (product_id,),
    )

    if not product:
        await callback.answer(
            "⚠️ این محصول یافت نشد.",
            show_alert=True,
        )
        return

    await db.execute(
        """
        UPDATE products
        SET views = views + 1
        WHERE id = ?;
        """,
        (product_id,),
    )

    await log_event(
        user_id,
        "view_product",
        "product",
        product_id,
    )

    is_favorite = await db.fetchone(
        """
        SELECT id
        FROM favorites
        WHERE user_id = ?
          AND product_id = ?;
        """,
        (
            user_id,
            product_id,
        ),
    )

    lines = [
        f"{EMOJI_PRODUCT} <b>{product['name']}</b>",
        "",
        product["description"] or "بدون توضیحات",
        "",
        f"{EMOJI_PRICE} {format_price(product['price'])}",
        f"🏪 {product['seller_name']}",
        f"{EMOJI_CITY} {product['city_name'] or 'نامشخص'}",
        (
            f"{EMOJI_RATING} "
            f"{product['rating']:.1f} "
            f"({product['review_count']} نظر)"
        ),
        status_badge(product["seller_status"]),
    ]

    if product["stock_status"] == "OUT_OF_STOCK":
        lines.append("⛔️ ناموجود")

    builder = InlineKeyboardBuilder()

    favorite_text = (
        "💔 حذف از علاقه‌مندی‌ها"
        if is_favorite
        else "❤️ افزودن به علاقه‌مندی‌ها"
    )

    favorite_callback = (
        f"unfavorite:{product_id}"
        if is_favorite
        else f"favorite:{product_id}"
    )

    builder.row(
        InlineKeyboardButton(
            text=favorite_text,
            callback_data=favorite_callback,
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=f"{EMOJI_COMPARE} افزودن به مقایسه",
            callback_data=f"comparestart:{product_id}",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=f"{EMOJI_SELLERS} فروشگاه",
            callback_data=f"seller:{product['seller_id']}",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="⭐ ثبت نظر",
            callback_data=(
                f"reviewstart:product:{product_id}"
            ),
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=f"{EMOJI_REPORT} گزارش",
            callback_data=(
                f"report:product:{product_id}"
            ),
        )
    )

    back_callback = (
        f"cat:{product['category_id']}:0"
        if product["category_id"]
        else "cat:0:0"
    )

    kb_add_back(
        builder,
        back_callback,
    )

    await safe_edit(
        callback,
        "\n".join(lines),
        builder.as_markup(),
    )

    await callback.answer()


# ======================================================================
# FAVORITES
# ======================================================================

@router.callback_query(F.data.startswith("favorite:"))
async def handle_favorite_add(
    callback: CallbackQuery,
) -> None:
    product_id = parse_int(
        callback.data.split(":")[1]
    )

    if product_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    product = await db.fetchone(
        "SELECT id FROM products WHERE id = ?;",
        (product_id,),
    )

    if not product:
        await callback.answer(
            "⚠️ این محصول یافت نشد.",
            show_alert=True,
        )
        return

    try:
        await db.execute(
            """
            INSERT INTO favorites (
                user_id,
                product_id,
                created_at
            )
            VALUES (?, ?, ?);
            """,
            (
                user_id,
                product_id,
                now_iso(),
            ),
        )

        await log_event(
            user_id,
            "favorite_add",
            "product",
            product_id,
        )

    except aiosqlite.IntegrityError:
        pass

    await callback.answer(
        "به علاقه‌مندی‌ها اضافه شد ❤️"
    )

    await _render_product_detail(callback)


@router.callback_query(F.data.startswith("unfavorite:"))
async def handle_favorite_remove(
    callback: CallbackQuery,
) -> None:
    product_id = parse_int(
        callback.data.split(":")[1]
    )

    if product_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    await db.execute(
        """
        DELETE FROM favorites
        WHERE user_id = ?
          AND product_id = ?;
        """,
        (
            user_id,
            product_id,
        ),
    )

    await callback.answer(
        "از علاقه‌مندی‌ها حذف شد 💔"
    )

    await _render_product_detail(callback)


@router.callback_query(F.data.startswith("favorites:"))
async def handle_favorites_list(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    page = (
        parse_int(
            callback.data.split(":")[1]
        )
        or 0
    )

    user_id = await ensure_user(
        callback.from_user
    )

    products = await db.fetchall(
        """
        SELECT p.*
        FROM favorites f
        JOIN products p
            ON p.id = f.product_id
        JOIN sellers s
            ON s.id = p.seller_id
        WHERE f.user_id = ?
          AND COALESCE(s.is_active, 1) = 1
        ORDER BY f.created_at DESC;
        """,
        (user_id,),
    )

    if not products:
        builder = InlineKeyboardBuilder()

        kb_add_back(
            builder,
            "main",
        )

        await safe_edit(
            callback,
            f"{EMOJI_FAVORITES} هنوز محصولی به علاقه‌مندی‌ها اضافه نکردی.",
            builder.as_markup(),
        )

        await callback.answer()
        return

    offset = page * PAGE_SIZE_LIST

    page_rows = products[
        offset: offset + PAGE_SIZE_LIST
    ]

    has_next = (
        offset + PAGE_SIZE_LIST
        < len(products)
    )

    builder = InlineKeyboardBuilder()

    for product in page_rows:
        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{EMOJI_PRODUCT} "
                    f"{product['name']}"
                ),
                callback_data=(
                    f"product:{product['id']}"
                ),
            )
        )

    kb_pagination_row(
        builder,
        "favorites",
        page,
        has_next,
    )

    kb_add_back(
        builder,
        "main",
    )

    await safe_edit(
        callback,
        f"{EMOJI_FAVORITES} <b>علاقه‌مندی‌ها</b>",
        builder.as_markup(),
    )

    await callback.answer()


# ======================================================================
# REVIEWS
# ======================================================================

@router.callback_query(F.data.startswith("reviewstart:"))
async def handle_review_start(
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

    _, target_type, target_id_str = parts

    target_id = parse_int(
        target_id_str
    )

    if (
        target_id is None
        or target_type not in ("seller", "product")
    ):
        await callback.answer(
            "⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    await state.update_data(
        review_target_type=target_type,
        review_target_id=target_id,
    )

    await state.set_state(
        ReviewStates.waiting_rating
    )

    builder = InlineKeyboardBuilder()

    for number in range(1, 6):
        builder.row(
            InlineKeyboardButton(
                text="⭐" * number,
                callback_data=f"reviewrate:{number}",
            )
        )

    kb_add_back(
        builder,
        f"{target_type}:{target_id}",
    )

    await safe_edit(
        callback,
        "امتیاز خودت رو انتخاب کن:",
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("reviewrate:"),
    StateFilter(ReviewStates.waiting_rating),
)
async def handle_review_rate(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    rating = parse_int(
        callback.data.split(":")[1]
    )

    if rating is None or not 1 <= rating <= 5:
        await callback.answer(
            "⚠️ امتیاز نامعتبر است.",
            show_alert=True,
        )
        return

    await state.update_data(
        review_rating=rating
    )

    await state.set_state(
        ReviewStates.waiting_text
    )

    await safe_edit(
        callback,
        "متن نظرت رو بنویس و بفرست:",
        InlineKeyboardBuilder().as_markup(),
    )

    await callback.answer()


@router.message(
    StateFilter(ReviewStates.waiting_text)
)
async def handle_review_text(
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

    target_type = data.get(
        "review_target_type"
    )
    target_id = data.get(
        "review_target_id"
    )
    rating = data.get(
        "review_rating"
    )

    await state.clear()

    if (
        not target_type
        or not target_id
        or not rating
    ):
        await message.answer(
            "⚠️ فرآیند ثبت نظر منقضی شده. لطفاً دوباره تلاش کن."
        )
        return

    seller_id = (
        target_id
        if target_type == "seller"
        else None
    )

    product_id = (
        target_id
        if target_type == "product"
        else None
    )

    if target_type == "seller":
        duplicate_query = """
            SELECT id
            FROM reviews
            WHERE user_id = ?
              AND seller_id = ?;
        """
    else:
        duplicate_query = """
            SELECT id
            FROM reviews
            WHERE user_id = ?
              AND product_id = ?;
        """

    existing = await db.fetchone(
        duplicate_query,
        (
            user_id,
            target_id,
        ),
    )

    if existing:
        await message.answer(
            "شما قبلاً برای این مورد نظر ثبت کرده‌اید."
        )
        return

    await db.execute(
        """
        INSERT INTO reviews (
            user_id,
            seller_id,
            product_id,
            rating,
            text,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (
            user_id,
            seller_id,
            product_id,
            rating,
            (message.text or "").strip(),
            now_iso(),
        ),
    )

    if target_type == "seller":
        await db.execute(
            """
            UPDATE sellers
            SET
                rating = (
                    SELECT AVG(rating)
                    FROM reviews
                    WHERE seller_id = ?
                ),
                review_count = (
                    SELECT COUNT(*)
                    FROM reviews
                    WHERE seller_id = ?
                )
            WHERE id = ?;
            """,
            (
                target_id,
                target_id,
                target_id,
            ),
        )

    else:
        await db.execute(
            """
            UPDATE products
            SET
                rating = (
                    SELECT AVG(rating)
                    FROM reviews
                    WHERE product_id = ?
                ),
                review_count = (
                    SELECT COUNT(*)
                    FROM reviews
                    WHERE product_id = ?
                )
            WHERE id = ?;
            """,
            (
                target_id,
                target_id,
                target_id,
            ),
        )

    await log_event(
        user_id,
        "review",
        target_type,
        target_id,
    )

    await message.answer(
        "✅ ممنون! نظر شما با موفقیت ثبت شد."
    )


# ======================================================================
# REPORTS
# ======================================================================

@router.callback_query(F.data.startswith("report:"))
async def handle_report_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    parts = callback.data.split(":")

    if len(parts) != 3:
        await callback.answer(
            "⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    _, target_type, target_id_str = parts

    target_id = parse_int(
        target_id_str
    )

    if (
        target_id is None
        or target_type not in ("seller", "product")
    ):
        await callback.answer(
            "⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    seller_id = (
        target_id
        if target_type == "seller"
        else None
    )

    product_id = (
        target_id
        if target_type == "product"
        else None
    )

    if await has_open_report(
        user_id,
        seller_id,
        product_id,
    ):
        await callback.answer(
            "گزارش قبلی شما برای همین مورد هنوز در حال بررسی است.",
            show_alert=True,
        )
        return

    builder = InlineKeyboardBuilder()

    for code, label in REPORT_REASONS.items():
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=(
                    f"reportreason:"
                    f"{target_type}:"
                    f"{target_id}:"
                    f"{code}"
                ),
            )
        )

    kb_add_back(
        builder,
        f"{target_type}:{target_id}",
    )

    await safe_edit(
        callback,
        "دلیل گزارش رو انتخاب کن:",
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("reportreason:"))
async def handle_report_reason(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    parts = callback.data.split(":")

    if len(parts) != 4:
        await callback.answer(
            "⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    (
        _,
        target_type,
        target_id_str,
        reason_code,
    ) = parts

    target_id = parse_int(
        target_id_str
    )

    if (
        target_id is None
        or target_type not in ("seller", "product")
        or reason_code not in REPORT_REASONS
    ):
        await callback.answer(
            "⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    await state.update_data(
        report_target_type=target_type,
        report_target_id=target_id,
        report_reason=reason_code,
    )

    await state.set_state(
        ReportStates.waiting_description
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="رد کردن توضیحات",
            callback_data="reportskip",
        )
    )

    await safe_edit(
        callback,
        "اگر توضیح بیشتری داری بنویس، یا رد کن:",
        builder.as_markup(),
    )

    await callback.answer()


async def _save_report(
    user_id: int,
    data: dict,
    description: Optional[str],
    bot: Optional[Bot] = None,
) -> None:
    target_type = data.get(
        "report_target_type"
    )

    target_id = data.get(
        "report_target_id"
    )

    reason_code = data.get(
        "report_reason"
    )

    seller_id = (
        target_id
        if target_type == "seller"
        else None
    )

    product_id = (
        target_id
        if target_type == "product"
        else None
    )

    cursor = await db.execute(
        """
        INSERT INTO reports (
            user_id,
            seller_id,
            product_id,
            reason,
            description,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, 'PENDING', ?);
        """,
        (
            user_id,
            seller_id,
            product_id,
            reason_code,
            description,
            now_iso(),
        ),
    )

    report_id = cursor.lastrowid

    await log_event(
        user_id,
        "report",
        target_type,
        target_id,
    )

    await log_audit(
        user_id,
        "report_created",
        target_type,
        target_id,
        details=reason_code,
    )

    if bot is not None:
        target_label = (
            "فروشگاه"
            if seller_id
            else "محصول"
        )

        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(
                text="🟢 تأیید گزارش",
                callback_data=(
                    f"adminreport:approve:{report_id}"
                ),
            ),
            InlineKeyboardButton(
                text="🔴 رد گزارش",
                callback_data=(
                    f"adminreport:reject:{report_id}"
                ),
            ),
        )

        await send_admin_dm(
            bot,
            (
                f"🚨 گزارش جدید "
                f"({target_label} #{target_id})\n"
                f"دلیل: "
                f"{REPORT_REASONS.get(reason_code, reason_code)}\n"
                f"توضیح: "
                f"{description or '—'}"
            ),
            reply_markup=builder.as_markup(),
        )


@router.callback_query(
    F.data == "reportskip",
    StateFilter(ReportStates.waiting_description),
)
async def handle_report_skip(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    user_id = await ensure_user(
        callback.from_user
    )

    data = await state.get_data()

    await state.clear()

    await _save_report(
        user_id,
        data,
        None,
        bot=callback.bot,
    )

    builder = InlineKeyboardBuilder()

    kb_add_back(
        builder,
        "main",
    )

    await safe_edit(
        callback,
        "گزارش شما ثبت شد. ممنون که به امن‌تر شدن ارزانکده کمک می‌کنی.",
        builder.as_markup(),
    )

    await callback.answer()


@router.message(
    StateFilter(ReportStates.waiting_description)
)
async def handle_report_description(
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

    await state.clear()

    await _save_report(
        user_id,
        data,
        (message.text or "").strip(),
        bot=message.bot,
    )

    await message.answer(
        "گزارش شما ثبت شد. ممنون که به امن‌تر شدن ارزانکده کمک می‌کنی."
    )


@router.callback_query(F.data.startswith("adminreport:"))
async def handle_admin_report_decision(
    callback: CallbackQuery,
) -> None:
    """
    Admin-only report decision.

    Access is gated by ADMIN_CHAT_ID. If it is not configured,
    the action is refused rather than left open.
    """

    parts = callback.data.split(":")

    if len(parts) != 3:
        await callback.answer(
            "⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    _, action, report_id_str = parts

    report_id = parse_int(
        report_id_str
    )

    if (
        report_id is None
        or action not in ("approve", "reject")
    ):
        await callback.answer(
            "⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    admin_user_id = await ensure_user(
        callback.from_user
    )

    if not _is_admin(callback):
        await callback.answer(
            "⛔️ این عملیات فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    report = await db.fetchone(
        "SELECT * FROM reports WHERE id = ?;",
        (report_id,),
    )

    if not report:
        await callback.answer(
            "⚠️ این گزارش یافت نشد.",
            show_alert=True,
        )
        return

    new_status = (
        "APPROVED"
        if action == "approve"
        else "REJECTED"
    )

    await db.execute(
        """
        UPDATE reports
        SET status = ?
        WHERE id = ?;
        """,
        (
            new_status,
            report_id,
        ),
    )

    await log_audit(
        admin_user_id,
        f"report_{action}d",
        "report",
        report_id,
    )

    if action == "approve":
        await notify_user(
            report["user_id"],
            "نتیجه گزارش شما",
            (
                "✅ گزارشت بررسی و تأیید شد. "
                "ممنون که به امن‌تر شدن ارزانکده کمک می‌کنی."
            ),
        )
    else:
        await notify_user(
            report["user_id"],
            "نتیجه گزارش شما",
            (
                "🚫 گزارشت بررسی شد.\n"
                "بعد از بررسی، مورد گزارش‌شده نیاز به اقدام نداشت."
            ),
        )

    await callback.answer(
        f"وضعیت گزارش #{report_id} به‌روزرسانی شد."
    )

    try:
        await callback.message.edit_text(
            (
                f"{callback.message.text}\n\n"
                f"— تصمیم ثبت شد: "
                f"{REQUEST_STATUS_LABELS[new_status]}"
            )
        )
    except TelegramBadRequest:
        pass