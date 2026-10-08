# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker /start and initial role flow.

This module intentionally does not import aiogram, sqlite,
aiosqlite, or any legacy bot module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from worker.state import clear_state
from worker.referrals import record_referral_if_new
from worker.telegram import TelegramClient
from worker_backend.backend import backend


ROLE_PICK_TEXT = (
    "👋 خوش اومدی به ارزانکده!\n"
    "اینجا می‌تونی چیزی که می‌خوای پیدا کنی، یا کسب‌وکارت رو به "
    "آدم‌های بیشتری معرفی کنی.\n\n"
    "امروز برای چی اومدی؟ 😊"
)

START_TEXT = (
    "سلام 👋\n"
    "به ارزان‌کده خوش اومدی 🌱"
)


def _now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
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


def _get_message_user(
    message: dict[str, Any],
) -> Optional[dict[str, Any]]:
    user = message.get("from")

    if not isinstance(
        user,
        dict,
    ):
        return None

    telegram_id = user.get(
        "id"
    )

    if telegram_id is None:
        return None

    try:
        telegram_id = int(
            telegram_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if telegram_id < 1:
        return None

    return user


def _get_chat_id(
    message: dict[str, Any],
) -> Optional[int]:
    chat = message.get(
        "chat"
    )

    if not isinstance(
        chat,
        dict,
    ):
        return None

    chat_id = chat.get(
        "id"
    )

    if chat_id is None:
        return None

    try:
        return int(
            chat_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


def _get_start_parameter(
    message: dict[str, Any],
) -> Optional[str]:
    text = message.get(
        "text"
    )

    if not isinstance(
        text,
        str,
    ):
        return None

    text = text.strip()

    if not text:
        return None

    parts = text.split(
        maxsplit=1
    )

    command = parts[0]

    if (
        command != "/start"
        and not command.startswith(
            "/start@"
        )
    ):
        return None

    if len(parts) < 2:
        return None

    parameter = parts[1].strip()

    return parameter or None


async def _ensure_user(
    user: dict[str, Any],
) -> Optional[dict[str, Any]]:
    telegram_id = int(
        user["id"]
    )

    first_name = user.get(
        "first_name"
    )
    last_name = user.get(
        "last_name"
    )
    username = user.get(
        "username"
    )

    first_name = (
        str(first_name).strip()
        if first_name is not None
        else None
    )

    last_name = (
        str(last_name).strip()
        if last_name is not None
        else None
    )

    username = (
        str(username).strip()
        if username is not None
        else None
    )

    now = _now_iso()

    await backend.execute(
        """
        INSERT INTO users (
            telegram_id,
            username,
            first_name,
            last_name,
            created_at,
            updated_at
        )
        VALUES (
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        )
        ON CONFLICT(telegram_id)
        DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            updated_at = excluded.updated_at;
        """,
        (
            telegram_id,
            username,
            first_name,
            last_name,
            now,
            now,
        ),
    )

    return await backend.fetchone(
        """
        SELECT *
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (
            telegram_id,
        ),
    )


async def _is_admin(
    env: Any,
    telegram_user_id: int,
) -> bool:
    admin_chat_id = getattr(
        env,
        "ADMIN_CHAT_ID",
        None,
    )

    if admin_chat_id is None:
        return False

    admin_chat_id = str(
        admin_chat_id
    ).strip()

    if not admin_chat_id:
        return False

    try:
        return int(admin_chat_id) == int(
            telegram_user_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return False


def _role_pick_keyboard(
    show_admin_option: bool = False,
) -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = [
        [
            _button(
                "🛍️ می‌خوام خرید کنم",
                "rolepick:buyer",
            )
        ],
        [
            _button(
                "🏪 می‌خوام فروشنده باشم",
                "rolepick:seller",
            )
        ],
    ]

    if show_admin_option:
        rows.append(
            [
                _button(
                    "🛡 ادمین",
                    "rolepick:admin",
                )
            ]
        )

    return _keyboard(rows)


def _main_menu_keyboard() -> dict[str, Any]:
    return _keyboard(
        [
            [
                _button(
                    "🔎 جستجو",
                    "search",
                ),
                _button(
                    "🏪 فروشگاه‌ها",
                    "sellers:0",
                ),
            ],
            [
                _button(
                    "📂 دسته‌بندی‌ها",
                    "cat:0",
                )
            ],
            [
                _button(
                    "🔥 داغ‌ها",
                    "hot",
                ),
                _button(
                    "🆕 جدیدها",
                    "newtoday",
                ),
            ],
            [
                _button(
                    "✨ پیشنهادهای ارزانکده",
                    "picks",
                )
            ],
            [
                _button(
                    "📍 نزدیک من",
                    "nearme",
                ),
                _button(
                    "🏆 فروشنده‌های برتر",
                    "topsellers",
                ),
            ],
            [
                _button(
                    "❤️ علاقه‌مندی‌ها",
                    "favorites:0",
                ),
                _button(
                    "⚖️ مقایسه",
                    "comparelist",
                ),
            ],
            [
                _button(
                    "🏪 ثبت فروشگاه",
                    "registerseller",
                )
            ],
            [
                _button(
                    "📣 تبلیغات عمومی",
                    "publicads",
                )
            ],
            [
                _button(
                    "👤 حساب من",
                    "account",
                )
            ],
            [
                _button(
                    "🔄 شروع از اول",
                    "restart_button",
                )
            ],
        ]
    )


async def _send_main_menu(
    telegram: TelegramClient,
    chat_id: int,
) -> None:
    await telegram.send_message(
        chat_id,
        (
            "سلام 👋\n\n"
            "به <b>ارزان‌کده</b> خوش اومدی 🌱\n\n"
            "چی دنبالشی؟"
        ),
        reply_markup=_main_menu_keyboard(),
        parse_mode="HTML",
    )


async def _show_role_picker(
    telegram: TelegramClient,
    chat_id: int,
    *,
    show_admin_option: bool,
) -> None:
    await telegram.send_message(
        chat_id,
        ROLE_PICK_TEXT,
        reply_markup=_role_pick_keyboard(
            show_admin_option=show_admin_option,
        ),
    )


async def _get_active_mode(
    user_id: int,
) -> str:
    row = await backend.fetchone(
        """
        SELECT active_mode
        FROM users
        WHERE id = ?
        LIMIT 1;
        """,
        (
            user_id,
        ),
    )

    if row is None:
        return "buyer"

    mode = str(
        row.get("active_mode") or "buyer"
    ).strip().lower()

    if mode not in (
        "buyer",
        "seller",
        "admin",
    ):
        return "buyer"

    return mode


async def _go_to_start(
    telegram: TelegramClient,
    chat_id: int,
    user: dict[str, Any],
    env: Any,
) -> None:
    user_id = int(
        user["id"]
    )

    role_chosen = bool(
        user.get("role_chosen")
    )

    telegram_user_id = int(
        user["telegram_id"]
    )

    if not role_chosen:
        await _show_role_picker(
            telegram,
            chat_id,
            show_admin_option=await _is_admin(
                env,
                telegram_user_id,
            ),
        )
        return

    await _send_main_menu(
        telegram,
        chat_id,
    )


async def handle_start(
    message: dict[str, Any],
    telegram: TelegramClient,
    env: Any = None,
) -> bool:
    user = _get_message_user(
        message
    )

    chat_id = _get_chat_id(
        message
    )

    if (
        user is None
        or chat_id is None
    ):
        return False

    db_user = await _ensure_user(
        user
    )

    if db_user is None:
        return False

    user_id = db_user.get(
        "id"
    )

    if user_id is None:
        return False

    try:
        user_id = int(
            user_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return False

    # /start is a hard navigation boundary.
    # Temporary multi-step Worker state must never survive it.
    await clear_state(
        backend,
        user_id,
    )

    start_parameter = _get_start_parameter(
        message
    )

    if start_parameter:
        await _handle_start_parameter(
            db_user,
            start_parameter,
        )

    await _go_to_start(
        telegram,
        chat_id,
        db_user,
        env,
    )

    return True


async def _handle_start_parameter(
    user: dict[str, Any],
    parameter: str,
) -> None:
    """
    Handle Telegram /start deep-link parameters.

    Supported referral format:
        /start shop_<seller_id>

    A successful new referral also creates a notification
    for the seller owner.
    """

    if not parameter.startswith(
        "shop_"
    ):
        return

    seller_id_text = parameter[
        len("shop_"):
    ].strip()

    try:
        seller_id = int(
            seller_id_text
        )
    except (
        TypeError,
        ValueError,
    ):
        return

    if seller_id < 1:
        return

    referred_user_id = user.get(
        "id"
    )

    try:
        referred_user_id = int(
            referred_user_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return

    if referred_user_id < 1:
        return

    seller = await backend.fetchone(
        """
        SELECT
            id,
            owner_user_id,
            created_by_user_id
        FROM sellers
        WHERE id = ?
        LIMIT 1;
        """,
        (
            seller_id,
        ),
    )

    if seller is None:
        return

    owner_user_id = seller.get(
        "owner_user_id"
    )

    try:
        owner_user_id = (
            int(owner_user_id)
            if owner_user_id is not None
            else None
        )
    except (
        TypeError,
        ValueError,
    ):
        owner_user_id = None

    if (
        owner_user_id == referred_user_id
    ):
        return

    recorded = await record_referral_if_new(
        backend,
        seller_id,
        referred_user_id,
    )

    if (
        not recorded
        or owner_user_id is None
        or owner_user_id < 1
    ):
        return

    await backend.execute(
        """
        INSERT INTO notifications (
            user_id,
            title,
            message,
            notification_type,
            is_read,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (
            owner_user_id,
            "🎉 معرفی جدید",
            (
                "یک کاربر جدید از طریق لینک اختصاصی "
                "فروشگاه شما وارد ارزانکده شد!"
            ),
            "referral",
            0,
            _now_iso(),
        ),
    )


async def handle_role_pick(
    callback_query: dict[str, Any],
    telegram: TelegramClient,
    env: Any,
) -> Any:
    """
    Persist the first selected role.

    This handler is exported for entry.py routing.
    """

    data = str(
        callback_query.get("data") or ""
    )

    if not data.startswith(
        "rolepick:"
    ):
        return None

    role = data.split(
        ":",
        1,
    )[1].strip().lower()

    if role not in (
        "buyer",
        "seller",
        "admin",
    ):
        await telegram.answer_callback_query(
            str(callback_query.get("id")),
            text="⚠️ گزینه نامعتبر است.",
            show_alert=True,
        )
        return None

    callback_user = (
        callback_query.get("from")
        or {}
    )

    telegram_user_id = callback_user.get(
        "id"
    )

    if telegram_user_id is None:
        return None

    try:
        telegram_user_id = int(
            telegram_user_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    db_user = await _ensure_user(
        callback_user
    )

    if db_user is None:
        return None

    user_id = db_user.get(
        "id"
    )

    if user_id is None:
        return None

    user_id = int(
        user_id
    )

    await clear_state(
        backend,
        user_id,
    )

    if role == "admin":
        if not await _is_admin(
            env,
            telegram_user_id,
        ):
            await telegram.answer_callback_query(
                str(callback_query.get("id")),
                text=(
                    "⛔️ این گزینه فقط برای ادمین "
                    "در دسترس است."
                ),
                show_alert=True,
            )
            return None

    await backend.execute(
        """
        UPDATE users
        SET active_mode = ?,
            role_chosen = 1,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            role,
            _now_iso(),
            user_id,
        ),
    )

    message = callback_query.get(
        "message"
    ) or {}

    chat = message.get(
        "chat"
    ) or {}

    chat_id = chat.get(
        "id"
    )

    message_id = message.get(
        "message_id"
    )

    if (
        chat_id is not None
        and message_id is not None
    ):
        await telegram.edit_message_text(
            int(chat_id),
            int(message_id),
            (
                "✅ نقش شما ذخیره شد.\n\n"
                "حالا می‌تونیم شروع کنیم 🌱"
            ),
            parse_mode="HTML",
        )

    if role == "buyer":
        if chat_id is not None:
            await _send_main_menu(
                telegram,
                int(chat_id),
            )

    elif role == "seller":
        if chat_id is not None:
            await telegram.send_message(
                int(chat_id),
                (
                    "🏪 خب، حالا حالت فروشندگی فعاله!\n\n"
                    "برای اینکه فروشگاهت روی ارزانکده دیده بشه، "
                    "باید اول ثبتش کنی -- هر وقت آماده بودی، "
                    "از همینجا شروع کن."
                ),
                reply_markup=_keyboard(
                    [
                        [
                            _button(
                                "➕ ثبت فروشگاه من",
                                "registerseller",
                            )
                        ],
                        [
                            _button(
                                "🔙 منوی اصلی",
                                "main",
                            )
                        ],
                    ]
                ),
            )

    else:
        if chat_id is not None:
            await telegram.send_message(
                int(chat_id),
                (
                    "🛡 حالت ادمین فعاله.\n\n"
                    "پنل مدیریت در حال انتقال به نسخه Cloudflare است."
                ),
                reply_markup=_keyboard(
                    [
                        [
                            _button(
                                "🛍️ حالت خرید",
                                "setmode:buyer",
                            )
                        ],
                        [
                            _button(
                                "🔙 منوی اصلی",
                                "main",
                            )
                        ],
                    ]
                ),
            )

    await telegram.answer_callback_query(
        str(callback_query.get("id")),
    )

    return None


__all__ = [
    "ROLE_PICK_TEXT",
    "START_TEXT",
    "handle_start",
    "handle_role_pick",
]