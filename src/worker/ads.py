# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker seller advertising flow.

This module intentionally does not import aiogram, sqlite,
aiosqlite, or any legacy bot module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Optional


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
        "detail_title": "🏠 فروشگاهت رو ویژه معرفی کنم",
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


def _now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _html(value: Any) -> str:
    if value is None:
        return ""

    return escape(
        str(value),
        quote=False,
    )


def _button(
    text: str,
    callback_data: str,
) -> dict[str, Any]:
    return {
        "text": text,
        "callback_data": callback_data,
    }


def _keyboard(
    rows: list[list[dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "inline_keyboard": rows,
    }


def _back_button(
    callback_data: str = "account",
) -> list[dict[str, Any]]:
    return [
        _button(
            "🔙 برگردیم",
            callback_data,
        )
    ]


def _parse_int(
    value: Any,
) -> Optional[int]:
    try:
        result = int(
            str(value).strip()
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if result < 1:
        return None

    return result


def _callback_context(
    callback_query: dict[str, Any],
) -> tuple[
    Optional[int],
    Optional[int],
]:
    message = (
        callback_query.get("message")
        or {}
    )

    chat = (
        message.get("chat")
        or {}
    )

    user = (
        callback_query.get("from")
        or {}
    )

    chat_id = _parse_int(
        chat.get("id")
    )

    telegram_user_id = _parse_int(
        user.get("id")
    )

    return (
        chat_id,
        telegram_user_id,
    )


async def _answer_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    *,
    text: Optional[str] = None,
    show_alert: bool = False,
) -> None:
    callback_id = callback_query.get("id")

    if not callback_id:
        return

    await telegram.answer_callback_query(
        str(callback_id),
        text=text,
        show_alert=show_alert,
    )


async def _edit_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    text: str,
    keyboard: Optional[dict[str, Any]] = None,
) -> None:
    message = (
        callback_query.get("message")
        or {}
    )

    chat = (
        message.get("chat")
        or {}
    )

    chat_id = _parse_int(
        chat.get("id")
    )

    message_id = _parse_int(
        message.get("message_id")
    )

    if (
        chat_id is None
        or message_id is None
    ):
        return

    await telegram.edit_message_text(
        chat_id,
        message_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def _send(
    telegram: Any,
    chat_id: int,
    text: str,
    keyboard: Optional[dict[str, Any]] = None,
) -> None:
    await telegram.send_message(
        chat_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def _ensure_user(
    db: Any,
    telegram_user_id: int,
    *,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> int:
    now = _now_iso()

    await db.execute(
        """
        INSERT INTO users (
            telegram_id,
            username,
            first_name,
            last_name,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id)
        DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            updated_at = excluded.updated_at;
        """,
        (
            telegram_user_id,
            username,
            first_name,
            last_name,
            now,
            now,
        ),
    )

    row = await db.fetchone(
        """
        SELECT id
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_user_id,),
    )

    if row is None:
        raise RuntimeError(
            "Failed to resolve internal user id."
        )

    return int(
        row["id"]
    )


async def _get_owned_sellers(
    db: Any,
    user_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT *
        FROM sellers
        WHERE (
            owner_user_id = ?
            OR created_by_user_id = ?
        )
        ORDER BY id ASC;
        """,
        (
            user_id,
            user_id,
        ),
    )


async def _has_open_request(
    db: Any,
    user_id: int,
    request_type: str,
    topic: str,
) -> bool:
    row = await db.fetchone(
        """
        SELECT id
        FROM requests
        WHERE user_id = ?
          AND request_type = ?
          AND topic = ?
          AND status IN (
              'PENDING',
              'APPROVED',
              'ACTIVE'
          )
        LIMIT 1;
        """,
        (
            user_id,
            request_type,
            topic,
        ),
    )

    return row is not None


async def _create_ad_request(
    db: Any,
    user_id: int,
    topic: str,
    seller_id: Optional[int],
) -> Optional[int]:
    now = _now_iso()

    result = await db.execute(
        """
        INSERT INTO requests (
            user_id,
            request_type,
            topic,
            seller_id,
            status,
            created_at,
            updated_at
        )
        VALUES (?, 'ad', ?, ?, 'PENDING', ?, ?);
        """,
        (
            user_id,
            topic,
            seller_id,
            now,
            now,
        ),
    )

    lastrowid = getattr(
        result,
        "lastrowid",
        None,
    )

    if lastrowid is not None:
        return int(lastrowid)

    row = await db.fetchone(
        """
        SELECT id
        FROM requests
        WHERE user_id = ?
          AND request_type = 'ad'
          AND topic = ?
        ORDER BY id DESC
        LIMIT 1;
        """,
        (
            user_id,
            topic,
        ),
    )

    if row is None:
        return None

    return int(
        row["id"]
    )


async def _audit(
    db: Any,
    user_id: int,
    request_id: int,
    code: str,
) -> None:
    await db.execute(
        """
        INSERT INTO audit_log (
            user_id,
            action,
            entity_type,
            entity_id,
            details,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (
            user_id,
            "ad_request_created",
            "request",
            request_id,
            code,
            _now_iso(),
        ),
    )


async def handle_ads(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Seller advertising menu.

    Callback:
        ads
    """

    _, telegram_user_id = _callback_context(
        callback_query
    )

    if telegram_user_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر شناسایی نشد.",
            show_alert=True,
        )
        return

    user = (
        callback_query.get("from")
        or {}
    )

    user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    sellers = await _get_owned_sellers(
        db,
        user_id,
    )

    if not sellers:
        await _edit_callback(
            telegram,
            callback_query,
            (
                "⚠️ هنوز فروشگاهی به حسابت وصل نیست.\n\n"
                "اول فروشگاهت رو ثبت یا مدیریت کن."
            ),
            _keyboard(
                [
                    [
                        _button(
                            "🏪 ثبت فروشگاه من",
                            "registerseller",
                        )
                    ],
                    _back_button("account"),
                ]
            ),
        )

        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    rows: list[
        list[dict[str, Any]]
    ] = []

    for code, info in AD_TYPES.items():
        rows.append(
            [
                _button(
                    info["menu_label"],
                    f"adtype:{code}",
                )
            ]
        )

    rows.append(
        [
            _button(
                "📢 تبلیغ در ارزانکده (عمومی)",
                "publicads",
            )
        ]
    )

    rows.append(
        _back_button("account")
    )

    await _edit_callback(
        telegram,
        callback_query,
        (
            "🚀 <b>می‌خوای بیشتر دیده بشی؟</b>\n\n"
            "اینجا می‌تونی فروشگاه یا محصولت رو "
            "به آدم‌های بیشتری توی ارزانکده نشون بدی."
        ),
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_ad_type_detail(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Advertisement type details.

    Callback:
        adtype:<code>
    """

    data = str(
        callback_query.get("data")
        or ""
    )

    code = (
        data.split(":", 1)[1]
        if ":" in data
        else ""
    )

    info = AD_TYPES.get(code)

    if not info:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ این نوع تبلیغ یافت نشد.",
            show_alert=True,
        )
        return

    await _edit_callback(
        telegram,
        callback_query,
        (
            f"<b>{_html(info['detail_title'])}</b>\n\n"
            f"{_html(info['detail_body'])}"
        ),
        _keyboard(
            [
                [
                    _button(
                        info["pick_button"],
                        f"adconfirm:{code}",
                    )
                ],
                [
                    _button(
                        "🛟 سوالی دارم",
                        "supportstart:seller",
                    )
                ],
                [
                    _button(
                        "🔙 برگردیم",
                        "ads",
                    )
                ],
            ]
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_ad_confirm(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Create a seller advertisement request.

    Callback:
        adconfirm:<code>
    """

    data = str(
        callback_query.get("data")
        or ""
    )

    code = (
        data.split(":", 1)[1]
        if ":" in data
        else ""
    )

    info = AD_TYPES.get(code)

    if not info:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ این نوع تبلیغ یافت نشد.",
            show_alert=True,
        )
        return

    _, telegram_user_id = _callback_context(
        callback_query
    )

    if telegram_user_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر شناسایی نشد.",
            show_alert=True,
        )
        return

    user = (
        callback_query.get("from")
        or {}
    )

    user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    sellers = await _get_owned_sellers(
        db,
        user_id,
    )

    if not sellers:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ هنوز فروشگاهی به حسابت وصل نیست.",
            show_alert=True,
        )
        return

    topic = info["menu_label"]

    if await _has_open_request(
        db,
        user_id,
        "ad",
        topic,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text=(
                "درخواست تبلیغاتی قبلی‌ات برای همین نوع "
                "هنوز تعیین تکلیف نشده."
            ),
            show_alert=True,
        )
        return

    seller_id = int(
        sellers[0]["id"]
    )

    request_id = await _create_ad_request(
        db,
        user_id,
        topic,
        seller_id,
    )

    if request_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ ثبت درخواست انجام نشد. دوباره تلاش کن.",
            show_alert=True,
        )
        return

    await _audit(
        db,
        user_id,
        request_id,
        code,
    )

    chat_id, _ = _callback_context(
        callback_query
    )

    if chat_id is not None:
        await _edit_callback(
            telegram,
            callback_query,
            (
                "✅ درخواست "
                f"«{_html(topic)}» ثبت شد.\n\n"
                "💬 برای قیمت و هماهنگی پرداخت با "
                "پشتیبانی ارزانکده در ارتباط باش.\n"
                "می‌تونی وضعیت درخواستت رو از "
                "«📋 درخواست‌های من» پیگیری کنی."
            ),
            _keyboard(
                [
                    _back_button("account"),
                ]
            ),
        )

    await _answer_callback(
        telegram,
        callback_query,
    )


__all__ = [
    "handle_ads",
    "handle_ad_type_detail",
    "handle_ad_confirm",
]