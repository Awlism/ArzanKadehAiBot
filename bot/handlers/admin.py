# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Admin handlers
"""

from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from ..config import ADMIN_CHAT_ID
from ..database import db
from ..keyboards import kb_add_back, kb_pagination_row
from ..repositories import (
    REQUEST_STATUS_LABELS,
    get_active_mode,
)
from ..services.notifications import notify_user
from ..services.referrals import (
    get_referral_count,
    get_sellers_owned_by_user,
)
from ..states import (
    AdminAdSettingStates,
    AdminSearchStates,
)
from ..utils import (
    ensure_user,
    format_price,
    is_admin_telegram_id,
    log_audit,
    now_iso,
    parse_int,
    restart_requested,
    safe_edit,
    send_admin_dm,
)

router = Router(name="admin")

PAGE_SIZE_LIST = 10


def _is_admin(callback: CallbackQuery) -> bool:
    return is_admin_telegram_id(callback.from_user.id)


# ======================================================================
# ADMIN REQUEST DECISION
# ======================================================================

@router.callback_query(F.data.startswith("adminreq:"))
async def handle_admin_request_decision(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")

    if len(parts) != 3:
        await callback.answer(
            "⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    _, action, request_id_str = parts

    request_id = parse_int(request_id_str)

    if request_id is None or action not in ("approve", "reject"):
        await callback.answer(
            "⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    if not _is_admin(callback):
        await callback.answer(
            "⛔️ این عملیات فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    admin_user_id = await ensure_user(callback.from_user)

    req = await db.fetchone(
        "SELECT * FROM requests WHERE id = ?;",
        (request_id,),
    )

    if not req:
        await callback.answer(
            "⚠️ این درخواست یافت نشد.",
            show_alert=True,
        )
        return

    is_ad = req["request_type"] in ("ad", "general_ad")

    if action == "reject":
        new_status = "REJECTED"

        await db.execute(
            """
            UPDATE requests
            SET status = ?, updated_at = ?
            WHERE id = ?;
            """,
            (
                new_status,
                now_iso(),
                request_id,
            ),
        )

    elif is_ad and req["ad_duration_days"]:
        new_status = "ACTIVE"

        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(days=req["ad_duration_days"])
        ).isoformat(timespec="seconds")

        await db.execute(
            """
            UPDATE requests
            SET status = ?,
                ad_expires_at = ?,
                updated_at = ?
            WHERE id = ?;
            """,
            (
                new_status,
                expires_at,
                now_iso(),
                request_id,
            ),
        )

    else:
        new_status = "APPROVED"

        await db.execute(
            """
            UPDATE requests
            SET status = ?, updated_at = ?
            WHERE id = ?;
            """,
            (
                new_status,
                now_iso(),
                request_id,
            ),
        )

    await log_audit(
        admin_user_id,
        f"request_{action}d",
        "request",
        request_id,
    )

    if req["request_type"] == "support":

        if action == "approve":
            await notify_user(
                req["user_id"],
                "درخواست پشتیبانی",
                "✅ درخواست پشتیبانی‌ات تأیید شد. تیم ارزانکده به‌زودی باهات در ارتباط خواهد بود.",
            )
        else:
            await notify_user(
                req["user_id"],
                "درخواست پشتیبانی",
                "درخواست پشتیبانی‌ات بررسی شد. اگر همچنان مشکل داری، دوباره از منو درخواست بده.",
            )

    elif req["request_type"] == "general_ad":

        if action == "approve":
            message = (
                "✅ تبلیغت تأیید شد!"
                + (
                    f" برای {req['ad_duration_days']} روز فعال می‌مونه."
                    if new_status == "ACTIVE"
                    else
                    " برای هماهنگی قیمت و مدت نمایش، تیم ارزانکده باهات در ارتباط خواهد بود."
                )
            )

            await notify_user(
                req["user_id"],
                "تبلیغ در ارزانکده",
                message,
            )

        else:
            await notify_user(
                req["user_id"],
                "تبلیغ در ارزانکده",
                "تبلیغت فعلاً امکان‌پذیر نیست. برای جزئیات بیشتر با پشتیبانی در ارتباط باش.",
            )

    else:

        if action == "approve":
            await notify_user(
                req["user_id"],
                "درخواست تبلیغات",
                "✅ درخواست تبلیغاتت تأیید شد. تیم ارزانکده برای هماهنگی قیمت و پرداخت باهات تماس می‌گیره.",
            )
        else:
            await notify_user(
                req["user_id"],
                "درخواست تبلیغات",
                "درخواست تبلیغاتت فعلاً امکان‌پذیر نیست. برای جزئیات بیشتر با پشتیبانی در ارتباط باش.",
            )

    await callback.answer(
        f"وضعیت درخواست #{request_id} به‌روزرسانی شد."
    )

    try:
        await callback.message.edit_text(
            f"{callback.message.text}\n\n"
            f"— تصمیم ثبت شد: {REQUEST_STATUS_LABELS[new_status]}"
        )
    except TelegramBadRequest:
        pass


# ======================================================================
# ADMIN HOME
# ======================================================================

async def _render_admin_home(callback: CallbackQuery) -> None:
    text = "🛡 <b>پنل مدیریت</b>"

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="👥 کاربران",
            callback_data="adminusers",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="📢 تبلیغات",
            callback_data="adsadmin",
        )
    )

    kb_add_back(builder, "main")

    await safe_edit(
        callback,
        text,
        builder.as_markup(),
    )


@router.callback_query(F.data == "adminhome")
async def handle_admin_home(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    if not _is_admin(callback):
        await callback.answer(
            "⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    await _render_admin_home(callback)
    await callback.answer()


# ======================================================================
# USERS
# ======================================================================

@router.callback_query(F.data == "adminusers")
async def handle_admin_users_menu(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    if not _is_admin(callback):
        await callback.answer(
            "⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    text = "👥 <b>کاربران</b>"

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="🔎 جستجوی کاربر",
            callback_data="adminusersearch",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="📋 همه کاربران",
            callback_data="adminuserlist:0",
        )
    )

    kb_add_back(builder, "adminhome")

    await safe_edit(
        callback,
        text,
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(F.data == "adminusersearch")
async def handle_admin_user_search_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if not _is_admin(callback):
        await callback.answer(
            "⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    await state.set_state(
        AdminSearchStates.waiting_user_query
    )

    builder = InlineKeyboardBuilder()
    kb_add_back(builder, "adminusers")

    await safe_edit(
        callback,
        "🔎 نام، username یا آیدی عددی تلگرام کاربر را بفرست:",
        builder.as_markup(),
    )

    await callback.answer()


@router.message(
    StateFilter(AdminSearchStates.waiting_user_query)
)
async def handle_admin_user_search_query(
    message: Message,
    state: FSMContext,
) -> None:
    if await restart_requested(message, state):
        return

    if not is_admin_telegram_id(message.from_user.id):
        await state.clear()
        return

    query = (message.text or "").strip()

    await state.clear()

    if not query:
        await message.answer(
            "⚠️ لطفاً یک متن معتبر بفرست."
        )
        return

    like = f"%{query}%"

    if query.isdigit():
        rows = await db.fetchall(
            """
            SELECT *
            FROM users
            WHERE username LIKE ?
               OR first_name LIKE ?
               OR last_name LIKE ?
               OR CAST(telegram_id AS TEXT) LIKE ?
            ORDER BY id DESC
            LIMIT ?;
            """,
            (
                like,
                like,
                like,
                like,
                PAGE_SIZE_LIST,
            ),
        )
    else:
        rows = await db.fetchall(
            """
            SELECT *
            FROM users
            WHERE username LIKE ?
               OR first_name LIKE ?
               OR last_name LIKE ?
            ORDER BY id DESC
            LIMIT ?;
            """,
            (
                like,
                like,
                like,
                PAGE_SIZE_LIST,
            ),
        )

    builder = InlineKeyboardBuilder()

    if not rows:
        text = (
            f"🔎 نتیجه‌ای برای «{query}» پیدا نشد."
        )

    else:
        text = (
            f"🔎 نتایج جستجو برای «{query}»:"
        )

        for user in rows:
            label = (
                user["first_name"]
                or user["username"]
                or str(user["telegram_id"])
            )

            builder.row(
                InlineKeyboardButton(
                    text=f"👤 {label}",
                    callback_data=f"adminuserview:{user['id']}",
                )
            )

    kb_add_back(builder, "adminusers")

    await message.answer(
        text,
        reply_markup=builder.as_markup(),
    )


@router.callback_query(
    F.data.startswith("adminuserlist:")
)
async def handle_admin_user_list(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    if not _is_admin(callback):
        await callback.answer(
            "⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    page = parse_int(
        callback.data.split(":")[1]
    )

    if page is None:
        await callback.answer(
            "⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    all_users = await db.fetchall(
        "SELECT * FROM users ORDER BY id DESC;"
    )

    offset = page * PAGE_SIZE_LIST

    page_users = all_users[
        offset : offset + PAGE_SIZE_LIST
    ]

    has_next = (
        offset + PAGE_SIZE_LIST
        < len(all_users)
    )

    builder = InlineKeyboardBuilder()

    if not all_users:
        text = "📋 هنوز کاربری ثبت نشده."

    else:
        text = (
            f"📋 <b>همه کاربران</b> "
            f"({len(all_users)} نفر)"
        )

        for user in page_users:
            label = (
                user["first_name"]
                or user["username"]
                or str(user["telegram_id"])
            )

            builder.row(
                InlineKeyboardButton(
                    text=f"👤 {label}",
                    callback_data=f"adminuserview:{user['id']}",
                )
            )

        kb_pagination_row(
            builder,
            "adminuserlist",
            page,
            has_next,
        )

    kb_add_back(builder, "adminusers")

    await safe_edit(
        callback,
        text,
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("adminuserview:")
)
async def handle_admin_user_view(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    if not _is_admin(callback):
        await callback.answer(
            "⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    target_user_id = parse_int(
        callback.data.split(":")[1]
    )

    if target_user_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    user = await db.fetchone(
        """
        SELECT
            u.*,
            c.name AS city_name
        FROM users u
        LEFT JOIN cities c
            ON c.id = u.city_id
        WHERE u.id = ?;
        """,
        (target_user_id,),
    )

    if not user:
        await callback.answer(
            "⚠️ این کاربر یافت نشد.",
            show_alert=True,
        )
        return

    owned_sellers = await get_sellers_owned_by_user(
        target_user_id
    )

    mode = await get_active_mode(
        target_user_id
    )

    request_row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM requests
        WHERE user_id = ?;
        """,
        (target_user_id,),
    )

    report_row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM reports
        WHERE user_id = ?;
        """,
        (target_user_id,),
    )

    referral_total = 0

    for seller in owned_sellers:
        referral_total += await get_referral_count(
            seller["id"]
        )

    name = " ".join(
        filter(
            None,
            [
                user["first_name"],
                user["last_name"],
            ],
        )
    ) or "بدون نام"

    lines = [
        f"👤 <b>{name}</b>",
        f"آیدی تلگرام: {user['telegram_id']}",
    ]

    if user["username"]:
        lines.append(
            f"نام کاربری: @{user['username']}"
        )

    lines += [
        f"شهر: {user['city_name'] or 'ثبت نشده'}",
        (
            "نقش انتخاب‌شده: "
            f"{'بله' if user['role_chosen'] else 'خیر'}"
        ),
        f"حالت فعلی: {mode}",
        f"عضویت از: {user['created_at'][:10]}",
        "",
        (
            "🏪 فروشگاه‌های متعلق به این کاربر: "
            f"{len(owned_sellers)}"
        ),
    ]

    for seller in owned_sellers:
        lines.append(
            f"  • {seller['name']}"
        )

    lines += [
        (
            "📋 تعداد درخواست‌های ثبت‌شده: "
            f"{request_row['c'] if request_row else 0}"
        ),
        (
            "🚨 تعداد گزارش‌های ثبت‌شده توسط این کاربر: "
            f"{report_row['c'] if report_row else 0}"
        ),
        (
            "🎁 مجموع معرفی‌های موفق "
            "(از فروشگاه‌هایش): "
            f"{referral_total}"
        ),
    ]

    builder = InlineKeyboardBuilder()

    kb_add_back(
        builder,
        "adminuserlist:0",
    )

    await safe_edit(
        callback,
        "\n".join(lines),
        builder.as_markup(),
    )

    await callback.answer()


# ======================================================================
# ADVERTISING ADMIN
# ======================================================================

@router.callback_query(
    F.data.startswith("adsetprice:")
)
async def handle_admin_ad_set_price_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if not _is_admin(callback):
        await callback.answer(
            "⛔️ این عملیات فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    request_id = parse_int(
        callback.data.split(":")[1]
    )

    if request_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    await state.update_data(
        adminad_request_id=request_id
    )

    await state.set_state(
        AdminAdSettingStates.waiting_price
    )

    await callback.message.answer(
        "💰 قیمت رو به تومان بفرست (فقط عدد):"
    )

    await callback.answer()


@router.message(
    StateFilter(AdminAdSettingStates.waiting_price)
)
async def handle_admin_ad_set_price_value(
    message: Message,
    state: FSMContext,
) -> None:
    if await restart_requested(message, state):
        return

    if not is_admin_telegram_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()

    request_id = data.get(
        "adminad_request_id"
    )

    await state.clear()

    price = parse_int(
        (message.text or "")
        .strip()
        .replace(",", "")
    )

    if (
        request_id is None
        or price is None
        or price < 0
    ):
        await message.answer(
            "⚠️ لطفاً فقط عدد قیمت رو بفرست."
        )
        return

    await db.execute(
        """
        UPDATE requests
        SET ad_price = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            price,
            now_iso(),
            request_id,
        ),
    )

    admin_user_id = await ensure_user(
        message.from_user
    )

    await log_audit(
        admin_user_id,
        "ad_price_set",
        "request",
        request_id,
        details=str(price),
    )

    await message.answer(
        f"✅ قیمت درخواست #{request_id} ثبت شد: "
        f"{format_price(price)}"
    )


@router.callback_query(
    F.data.startswith("adsetduration:")
)
async def handle_admin_ad_set_duration_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if not _is_admin(callback):
        await callback.answer(
            "⛔️ این عملیات فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    request_id = parse_int(
        callback.data.split(":")[1]
    )

    if request_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    await state.update_data(
        adminad_request_id=request_id
    )

    await state.set_state(
        AdminAdSettingStates.waiting_duration
    )

    await callback.message.answer(
        "⏰ مدت نمایش رو به روز بفرست (فقط عدد):"
    )

    await callback.answer()


@router.message(
    StateFilter(AdminAdSettingStates.waiting_duration)
)
async def handle_admin_ad_set_duration_value(
    message: Message,
    state: FSMContext,
) -> None:
    if await restart_requested(message, state):
        return

    if not is_admin_telegram_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()

    request_id = data.get(
        "adminad_request_id"
    )

    await state.clear()

    days = parse_int(
        (message.text or "").strip()
    )

    if (
        request_id is None
        or days is None
        or days <= 0
    ):
        await message.answer(
            "⚠️ لطفاً فقط عدد روز رو بفرست (مثلاً 7)."
        )
        return

    await db.execute(
        """
        UPDATE requests
        SET ad_duration_days = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            days,
            now_iso(),
            request_id,
        ),
    )

    admin_user_id = await ensure_user(
        message.from_user
    )

    await log_audit(
        admin_user_id,
        "ad_duration_set",
        "request",
        request_id,
        details=str(days),
    )

    req = await db.fetchone(
        "SELECT * FROM requests WHERE id = ?;",
        (request_id,),
    )

    if req and req["status"] == "APPROVED":
        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(days=days)
        ).isoformat(timespec="seconds")

        await db.execute(
            """
            UPDATE requests
            SET status = 'ACTIVE',
                ad_expires_at = ?,
                updated_at = ?
            WHERE id = ?;
            """,
            (
                expires_at,
                now_iso(),
                request_id,
            ),
        )

        await notify_user(
            req["user_id"],
            (
                "تبلیغ در ارزانکده"
                if req["request_type"] == "general_ad"
                else "درخواست تبلیغات"
            ),
            (
                f"✅ تبلیغت فعال شد و برای "
                f"{days} روز نمایش داده می‌شه."
            ),
        )

    await message.answer(
        f"✅ مدت درخواست #{request_id} ثبت شد: {days} روز"
    )


@router.callback_query(
    F.data.startswith("adsetplacement:")
)
async def handle_admin_ad_set_placement_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if not _is_admin(callback):
        await callback.answer(
            "⛔️ این عملیات فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    request_id = parse_int(
        callback.data.split(":")[1]
    )

    if request_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    await state.update_data(
        adminad_request_id=request_id
    )

    await state.set_state(
        AdminAdSettingStates.waiting_placement
    )

    await callback.message.answer(
        "📍 محل نمایش رو بنویس "
        "(مثلاً «صفحه اصلی» یا «نتایج جستجو»):"
    )

    await callback.answer()


@router.message(
    StateFilter(AdminAdSettingStates.waiting_placement)
)
async def handle_admin_ad_set_placement_value(
    message: Message,
    state: FSMContext,
) -> None:
    if await restart_requested(message, state):
        return

    if not is_admin_telegram_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()

    request_id = data.get(
        "adminad_request_id"
    )

    await state.clear()

    placement = (
        message.text or ""
    ).strip()

    if (
        request_id is None
        or not placement
    ):
        await message.answer(
            "⚠️ لطفاً یک متن معتبر بفرست."
        )
        return

    await db.execute(
        """
        UPDATE requests
        SET ad_placement = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            placement,
            now_iso(),
            request_id,
        ),
    )

    admin_user_id = await ensure_user(
        message.from_user
    )

    await log_audit(
        admin_user_id,
        "ad_placement_set",
        "request",
        request_id,
        details=placement,
    )

    await message.answer(
        f"✅ محل نمایش درخواست #{request_id} ثبت شد: "
        f"{placement}"
    )


@router.callback_query(F.data == "adsadmin")
async def handle_ads_admin_panel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    if not _is_admin(callback):
        await callback.answer(
            "⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    pending = await db.fetchall(
        """
        SELECT *
        FROM requests
        WHERE request_type IN ('ad', 'general_ad')
          AND status = 'PENDING'
        ORDER BY created_at DESC
        LIMIT 10;
        """
    )

    active = await db.fetchall(
        """
        SELECT *
        FROM requests
        WHERE request_type IN ('ad', 'general_ad')
          AND status = 'ACTIVE'
        ORDER BY ad_expires_at ASC
        LIMIT 10;
        """
    )

    now = now_iso()

    soon_expiring = [
        row
        for row in active
        if row["ad_expires_at"]
        and row["ad_expires_at"] <= now
    ]

    lines = [
        "📢 <b>تبلیغات</b>",
        "",
        (
            "📋 درخواست‌های در انتظار بررسی: "
            f"{len(pending)}"
        ),
        f"🟢 تبلیغات فعال: {len(active)}",
        (
            "⏰ در حال اتمام: "
            f"{len(soon_expiring)}"
        ),
    ]

    builder = InlineKeyboardBuilder()

    for row in pending[:PAGE_SIZE_LIST]:
        title = (
            row["ad_title"]
            or row["topic"]
            or f"درخواست #{row['id']}"
        )

        builder.row(
            InlineKeyboardButton(
                text=f"📋 {title}",
                callback_data=(
                    f"adsadmindetail:{row['id']}"
                ),
            )
        )

    kb_add_back(
        builder,
        "account",
    )

    await safe_edit(
        callback,
        "\n".join(lines),
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("adsadmindetail:")
)
async def handle_ads_admin_detail(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    if not _is_admin(callback):
        await callback.answer(
            "⛔️ این بخش فقط برای ادمین در دسترس است.",
            show_alert=True,
        )
        return

    request_id = parse_int(
        callback.data.split(":")[1]
    )

    req = (
        await db.fetchone(
            "SELECT * FROM requests WHERE id = ?;",
            (request_id,),
        )
        if request_id
        else None
    )

    if not req:
        await callback.answer(
            "⚠️ این درخواست یافت نشد.",
            show_alert=True,
        )
        return

    ad_kind = (
        req["ad_kind"]
        or req["topic"]
        or "—"
    )

    lines = [
        f"📢 درخواست #{req['id']}",
        f"نوع: {ad_kind}",
        (
            f"عنوان: "
            f"{req['ad_title'] or req['topic'] or '—'}"
        ),
        (
            f"توضیح: "
            f"{req['message'] or '—'}"
        ),
        (
            f"لینک: "
            f"{req['ad_link'] or '—'}"
        ),
        (
            "وضعیت: "
            f"{REQUEST_STATUS_LABELS.get(req['status'], req['status'])}"
        ),
        (
            "💰 قیمت: "
            f"{format_price(req['ad_price']) if req['ad_price'] else 'تعیین‌نشده'}"
        ),
        (
            f"⏰ مدت: "
            f"{req['ad_duration_days']} روز"
            if req["ad_duration_days"]
            else "⏰ مدت: تعیین‌نشده"
        ),
        (
            "📍 محل نمایش: "
            f"{req['ad_placement'] or 'تعیین‌نشده'}"
        ),
    ]

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="🟢 تأیید تبلیغ",
            callback_data=(
                f"adminreq:approve:{req['id']}"
            ),
        ),
        InlineKeyboardButton(
            text="🔴 رد تبلیغ",
            callback_data=(
                f"adminreq:reject:{req['id']}"
            ),
        ),
    )

    builder.row(
        InlineKeyboardButton(
            text="💰 تعیین هزینه",
            callback_data=(
                f"adsetprice:{req['id']}"
            ),
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="⏰ تعیین مدت",
            callback_data=(
                f"adsetduration:{req['id']}"
            ),
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="📍 انتخاب محل نمایش",
            callback_data=(
                f"adsetplacement:{req['id']}"
            ),
        )
    )

    kb_add_back(
        builder,
        "adsadmin",
    )

    await safe_edit(
        callback,
        "\n".join(lines),
        builder.as_markup(),
    )

    await callback.answer()