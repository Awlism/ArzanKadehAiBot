# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker public advertising flow.

This module intentionally does not import aiogram, sqlite,
aiosqlite, or any legacy bot module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Optional

from worker.state import (
    clear_state,
    get_state,
    set_state,
)


STATE_NAME = "public_ad"

MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 1000
MAX_URL_LENGTH = 2048


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
    "فرق می‌کنه؛ مثلاً صفحه اصلی، نتایج جستجو یا بخش‌های ویژه.\n\n"
    "بعد از ثبت درخواست، تیم ارزانکده جای مناسب نمایش و قیمت دقیق "
    "رو باهات هماهنگ می‌کنه.\n\n"
    "💳 هیچ هزینه‌ای بدون هماهنگی قبلی ازت گرفته نمی‌شه."
)


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


def _keyboard(
    rows: list[list[dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "inline_keyboard": rows,
    }


def _button(
    text: str,
    callback_data: str,
) -> dict[str, Any]:
    return {
        "text": text,
        "callback_data": callback_data,
    }


def _back_button(
    callback_data: str = "main",
) -> list[dict[str, Any]]:
    return [
        _button(
            "🔙 برگردیم",
            callback_data,
        )
    ]


def _message_context(
    message: dict[str, Any],
) -> tuple[Optional[int], Optional[int], Optional[str]]:
    chat = message.get("chat") or {}
    user = message.get("from") or {}

    chat_id = chat.get("id")
    user_tg_id = user.get("id")
    text = message.get("text")

    return (
        int(chat_id) if chat_id is not None else None,
        int(user_tg_id) if user_tg_id is not None else None,
        text,
    )


def _callback_context(
    callback_query: dict[str, Any],
) -> tuple[
    Optional[int],
    Optional[int],
    Optional[int],
]:
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    user = callback_query.get("from") or {}

    chat_id = chat.get("id")
    user_tg_id = user.get("id")
    message_id = message.get("message_id")

    return (
        int(chat_id) if chat_id is not None else None,
        int(user_tg_id) if user_tg_id is not None else None,
        int(message_id) if message_id is not None else None,
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

    return int(row["id"])


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
    message = callback_query.get("message") or {}

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")

    if chat_id is None or message_id is None:
        return

    await telegram.edit_message_text(
        int(chat_id),
        int(message_id),
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


def _valid_url(
    value: str,
) -> Optional[str]:
    value = (value or "").strip()

    if not value:
        return None

    if len(value) > MAX_URL_LENGTH:
        return None

    lowered = value.lower()

    if not (
        lowered.startswith("http://")
        or lowered.startswith("https://")
    ):
        return None

    return value


async def handle_public_ads(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Main public-advertising landing page.
    """

    _, telegram_user_id, _ = _callback_context(
        callback_query
    )

    if telegram_user_id is not None:
        user = callback_query.get("from") or {}

        await _ensure_user(
            db,
            telegram_user_id,
            username=user.get("username"),
            first_name=user.get("first_name"),
            last_name=user.get("last_name"),
        )

    await _edit_callback(
        telegram,
        callback_query,
        (
            "🚀 <b>می‌خوای بیشتر دیده بشی؟</b>\n\n"
            "کسب‌وکارت، پیج، کانال، خدمات یا برندت رو "
            "به کاربرهای ارزانکده معرفی کن.\n\n"
            "ما تبلیغت رو بررسی می‌کنیم و جای نمایش و "
            "هزینه رو باهات هماهنگ می‌کنیم."
        ),
        _keyboard(
            [
                [
                    _button(
                        "📢 ثبت تبلیغ",
                        "pubadstart",
                    )
                ],
                [
                    _button(
                        "💡 مدل‌های تبلیغ",
                        "pubadmodels",
                    )
                ],
                [
                    _button(
                        "🛟 سوالی دارم",
                        "supportstart:buyer",
                    )
                ],
                _back_button("main"),
            ]
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_public_ad_models(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    await _edit_callback(
        telegram,
        callback_query,
        PUBLIC_AD_MODELS_TEXT,
        _keyboard(
            [
                _back_button("publicads"),
            ]
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_public_ad_start(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    chat_id, telegram_user_id, _ = _callback_context(
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

    user = callback_query.get("from") or {}

    user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    await set_state(
        db,
        user_id,
        STATE_NAME,
        {
            "step": "kind",
        },
    )

    rows: list[list[dict[str, Any]]] = []

    buttons = [
        _button(
            label,
            f"pubadkind:{code}",
        )
        for code, label in AD_KIND_LABELS.items()
    ]

    for index in range(0, len(buttons), 2):
        rows.append(
            buttons[index:index + 2]
        )

    rows.append(
        _back_button("publicads")
    )

    await _edit_callback(
        telegram,
        callback_query,
        "🎯 <b>چی رو می‌خوای معرفی کنی؟</b>",
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_public_ad_kind(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data = str(
        callback_query.get("data") or ""
    )

    kind = data.split(
        ":",
        1,
    )[1] if ":" in data else ""

    if kind not in AD_KIND_LABELS:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ گزینه نامعتبر است.",
            show_alert=True,
        )
        return

    _, telegram_user_id, _ = _callback_context(
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

    user = callback_query.get("from") or {}

    user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    await set_state(
        db,
        user_id,
        STATE_NAME,
        {
            "step": "title",
            "kind": kind,
        },
    )

    await _edit_callback(
        telegram,
        callback_query,
        (
            "📝 <b>عنوان تبلیغت چیه؟</b>\n\n"
            "مثلاً اسم کسب‌وکار، پیج یا کانال."
        ),
        None,
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_public_ad_message(
    db: Any,
    telegram: Any,
    message: dict[str, Any],
) -> bool:
    """
    Handle text messages while the public-ad state is active.

    Returns True when the message belongs to this flow.
    """

    chat_id, telegram_user_id, text = _message_context(
        message
    )

    if (
        chat_id is None
        or telegram_user_id is None
    ):
        return False

    user = message.get("from") or {}

    user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    current = await get_state(
        db,
        user_id,
    )

    if (
        current is None
        or current.get("state") != STATE_NAME
    ):
        return False

    data = dict(
        current.get("data") or {}
    )

    step = data.get("step")
    value = (text or "").strip()

    if step == "title":
        if not value:
            await _send(
                telegram,
                chat_id,
                "⚠️ عنوان نمی‌تونه خالی باشه. دوباره بفرست:",
            )
            return True

        if len(value) > MAX_TITLE_LENGTH:
            await _send(
                telegram,
                chat_id,
                (
                    "⚠️ عنوان تبلیغ خیلی طولانیه.\n"
                    "حداکثر ۲۰۰ کاراکتر بفرست:"
                ),
            )
            return True

        data["title"] = value
        data["step"] = "description"

        await set_state(
            db,
            user_id,
            STATE_NAME,
            data,
        )

        await _send(
            telegram,
            chat_id,
            "✏️ یه توضیح کوتاه بنویس که مردم بفهمن چی هستی:",
            _keyboard(
                [
                    [
                        _button(
                            "رد کردن",
                            "pubadskip:description",
                        )
                    ]
                ]
            ),
        )

        return True

    if step == "description":
        if len(value) > MAX_DESCRIPTION_LENGTH:
            await _send(
                telegram,
                chat_id,
                (
                    "⚠️ توضیحات خیلی طولانیه.\n"
                    "حداکثر ۱۰۰۰ کاراکتر بفرست:"
                ),
            )
            return True

        data["description"] = value or None
        data["step"] = "image_url"

        await set_state(
            db,
            user_id,
            STATE_NAME,
            data,
        )

        await _send(
            telegram,
            chat_id,
            "🖼️ لینک تصویر رو بفرست (اختیاری):",
            _keyboard(
                [
                    [
                        _button(
                            "رد کردن",
                            "pubadskip:image_url",
                        )
                    ]
                ]
            ),
        )

        return True

    if step == "image_url":
        image_url = _valid_url(value)

        if image_url is None:
            await _send(
                telegram,
                chat_id,
                (
                    "⚠️ لینک تصویر معتبر نیست.\n"
                    "یک لینک http یا https بفرست، "
                    "یا «رد کردن» رو بزن."
                ),
            )
            return True

        data["image_url"] = image_url
        data["step"] = "link"

        await set_state(
            db,
            user_id,
            STATE_NAME,
            data,
        )

        await _send(
            telegram,
            chat_id,
            "🔗 لینک صفحه/پیج/کانالت رو بفرست (اختیاری):",
            _keyboard(
                [
                    [
                        _button(
                            "رد کردن",
                            "pubadskip:link",
                        )
                    ]
                ]
            ),
        )

        return True

    if step == "link":
        link = _valid_url(value)

        if link is None:
            await _send(
                telegram,
                chat_id,
                (
                    "⚠️ لینک معتبر نیست.\n"
                    "یک لینک http یا https بفرست، "
                    "یا «رد کردن» رو بزن."
                ),
            )
            return True

        data["link"] = link

        await _finish_public_ad(
            db,
            telegram,
            chat_id,
            user_id,
            data,
        )

        return True

    return True


async def handle_public_ad_skip(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    data_value = str(
        callback_query.get("data") or ""
    )

    if ":" not in data_value:
        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    step = data_value.split(
        ":",
        1,
    )[1]

    _, telegram_user_id, _ = _callback_context(
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

    user = callback_query.get("from") or {}

    user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    current = await get_state(
        db,
        user_id,
    )

    if (
        current is None
        or current.get("state") != STATE_NAME
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ این فرم دیگه فعال نیست.",
            show_alert=True,
        )
        return

    state_data = dict(
        current.get("data") or {}
    )

    current_step = state_data.get("step")

    if step != current_step:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ این مرحله دیگه فعال نیست.",
            show_alert=True,
        )
        return

    if step == "description":
        state_data["description"] = None
        state_data["step"] = "image_url"

        await set_state(
            db,
            user_id,
            STATE_NAME,
            state_data,
        )

        await _edit_callback(
            telegram,
            callback_query,
            "🖼️ لینک تصویر رو بفرست (اختیاری):",
            _keyboard(
                [
                    [
                        _button(
                            "رد کردن",
                            "pubadskip:image_url",
                        )
                    ]
                ]
            ),
        )

    elif step == "image_url":
        state_data["image_url"] = None
        state_data["step"] = "link"

        await set_state(
            db,
            user_id,
            STATE_NAME,
            state_data,
        )

        await _edit_callback(
            telegram,
            callback_query,
            "🔗 لینک صفحه/پیج/کانالت رو بفرست (اختیاری):",
            _keyboard(
                [
                    [
                        _button(
                            "رد کردن",
                            "pubadskip:link",
                        )
                    ]
                ]
            ),
        )

    elif step == "link":
        state_data["link"] = None

        await _finish_public_ad(
            db,
            telegram,
            _callback_context(callback_query)[0],
            user_id,
            state_data,
        )

        await _answer_callback(
            telegram,
            callback_query,
        )
        return

    else:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ این مرحله قابل رد کردن نیست.",
            show_alert=True,
        )
        return

    await _answer_callback(
        telegram,
        callback_query,
    )


async def _finish_public_ad(
    db: Any,
    telegram: Any,
    chat_id: Optional[int],
    user_id: int,
    data: dict[str, Any],
) -> None:
    kind = data.get("kind")
    title = data.get("title")

    if (
        kind not in AD_KIND_LABELS
        or not isinstance(title, str)
        or not title.strip()
    ):
        await clear_state(
            db,
            user_id,
        )

        if chat_id is not None:
            await _send(
                telegram,
                chat_id,
                (
                    "⚠️ اطلاعات تبلیغ ناقصه.\n"
                    "لطفاً دوباره از «📢 تبلیغ در ارزانکده» شروع کن."
                ),
                _keyboard(
                    [
                        _back_button("main"),
                    ]
                ),
            )

        return

    open_request = await db.fetchone(
        """
        SELECT 1
        FROM requests
        WHERE user_id = ?
          AND request_type = 'general_ad'
          AND status = 'PENDING'
        LIMIT 1;
        """,
        (user_id,),
    )

    if open_request is not None:
        await clear_state(
            db,
            user_id,
        )

        if chat_id is not None:
            await _send(
                telegram,
                chat_id,
                (
                    "⏳ یه درخواست تبلیغ قبلی‌ات هنوز "
                    "در حال بررسیه.\n\n"
                    "تا اون تعیین‌تکلیف نشده، درخواست جدید "
                    "ثبت نمی‌شه."
                ),
                _keyboard(
                    [
                        _back_button("main"),
                    ]
                ),
            )

        return

    now = _now_iso()

    try:
        async with db.transaction(
            immediate=True
        ) as tx:
            existing = await tx.fetchone(
                """
                SELECT 1
                FROM requests
                WHERE user_id = ?
                  AND request_type = 'general_ad'
                  AND status = 'PENDING'
                LIMIT 1;
                """,
                (user_id,),
            )

            if existing is not None:
                request_already_exists = True
            else:
                request_already_exists = False

                await tx.execute(
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
                        title.strip(),
                        data.get("description"),
                        now,
                        now,
                        kind,
                        title.strip(),
                        data.get("image_url"),
                        data.get("link"),
                    ),
                )

        if request_already_exists:
            await clear_state(
                db,
                user_id,
            )

            if chat_id is not None:
                await _send(
                    telegram,
                    chat_id,
                    (
                        "⏳ یه درخواست تبلیغ قبلی‌ات هنوز "
                        "در حال بررسیه."
                    ),
                    _keyboard(
                        [
                            _back_button("main"),
                        ]
                    ),
                )

            return

        # Read the INSERT result after the D1 transaction commits.
        results = tx.results
        insert_result = (
            results[0]
            if results
            else None
        )

        request_id = (
            insert_result.lastrowid
            if insert_result is not None
            else None
        )

        # Fallback only if D1 did not return the inserted row ID.
        if request_id is None:
            request_row = await db.fetchone(
                """
                SELECT id
                FROM requests
                WHERE user_id = ?
                  AND request_type = 'general_ad'
                  AND status = 'PENDING'
                  AND topic = ?
                  AND message IS ?
                  AND created_at = ?
                ORDER BY id DESC
                LIMIT 1;
                """,
                (
                    user_id,
                    title.strip(),
                    data.get("description"),
                    now,
                ),
            )

            if request_row is not None:
                request_id = request_row["id"]

        if request_id is None:
            raise RuntimeError(
                "Public ad request ID could not be resolved."
            )

        request_id = int(request_id)

    except Exception:
        await clear_state(
            db,
            user_id,
        )

        if chat_id is not None:
            await _send(
                telegram,
                chat_id,
                (
                    "⚠️ ثبت درخواست تبلیغ با مشکل روبه‌رو شد. "
                    "لطفاً دوباره تلاش کن."
                ),
                _keyboard(
                    [
                        _back_button("main"),
                    ]
                ),
            )

        return

    await clear_state(
        db,
        user_id,
    )

    await db.execute(
        """
        INSERT INTO audit_log (
            actor_user_id,
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
            "general_ad_request_created",
            "request",
            request_id,
            title.strip(),
            now,
        ),
    )

    if chat_id is not None:
        await _send(
            telegram,
            chat_id,
            (
                "✅ <b>تبلیغت ثبت شد.</b>\n\n"
                "ما بررسیش می‌کنیم و برای جای نمایش و "
                "هزینه باهات هماهنگ می‌کنیم.\n\n"
                "💳 قبل از هر پرداختی، مبلغ و شرایط بهت گفته می‌شه."
            ),
            _keyboard(
                [
                    _back_button("main"),
                ]
            ),
        )


__all__ = [
    "AD_KIND_LABELS",
    "PUBLIC_AD_MODELS_TEXT",
    "handle_public_ads",
    "handle_public_ad_models",
    "handle_public_ad_start",
    "handle_public_ad_kind",
    "handle_public_ad_message",
    "handle_public_ad_skip",
]