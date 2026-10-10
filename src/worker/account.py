# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker account / active-mode flow.

This module intentionally does not import aiogram, sqlite,
aiosqlite, or any legacy bot module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Optional

from worker.state import clear_state


VALID_MODES = {
    "buyer",
    "seller",
    "admin",
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
    callback_data: str = "main",
) -> list[dict[str, Any]]:
    return [
        _button(
            "🔙 برگردیم",
            callback_data,
        )
    ]


def _message_context(
    callback_query: dict[str, Any],
) -> tuple[
    Optional[int],
    Optional[int],
]:
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    user = callback_query.get("from") or {}

    chat_id = chat.get("id")
    telegram_user_id = user.get("id")

    return (
        int(chat_id)
        if chat_id is not None
        else None,
        int(telegram_user_id)
        if telegram_user_id is not None
        else None,
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


async def _get_user(
    db: Any,
    telegram_user_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT
            id,
            telegram_id,
            username,
            first_name,
            last_name,
            active_mode,
            role_chosen
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_user_id,),
    )


async def _get_active_mode(
    db: Any,
    user_id: int,
) -> str:
    row = await db.fetchone(
        """
        SELECT active_mode
        FROM users
        WHERE id = ?
        LIMIT 1;
        """,
        (user_id,),
    )

    if row is None:
        return "buyer"

    mode = str(
        row.get("active_mode") or "buyer"
    ).strip().lower()

    if mode not in VALID_MODES:
        return "buyer"

    return mode


async def _is_admin(
    env: Any,
    telegram_user_id: int,
) -> bool:
    """
    Authorize admin mode from the Worker environment.

    ADMIN_CHAT_ID is the same configuration source used
    by the Worker admin modules.
    """

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


async def _user_has_any_seller(
    db: Any,
    user_id: int,
) -> bool:
    row = await db.fetchone(
        """
        SELECT 1
        FROM sellers
        WHERE (
            owner_user_id = ?
            OR created_by_user_id = ?
        )
        LIMIT 1;
        """,
        (
            user_id,
            user_id,
        ),
    )

    return row is not None


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

    if chat_id is None:
        return

    if message_id is None:
        await telegram.send_message(
            int(chat_id),
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    await telegram.edit_message_text(
        int(chat_id),
        int(message_id),
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


def _mode_switch_button(
    current_mode: str,
) -> dict[str, Any]:
    if current_mode == "buyer":
        return _button(
            "🏪 حالت فروشندگی",
            "setmode:seller",
        )

    return _button(
        "👤 حالت خرید",
        "setmode:buyer",
    )


async def _render_buyer_panel(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    user_id: int,
) -> None:
    rows: list[list[dict[str, Any]]] = [
        [
            _mode_switch_button("buyer"),
        ],
        [
            _button(
                "❤️ علاقه‌مندی‌ها",
                "favorites:0",
            )
        ],
        [
            _button(
                "⚖️ مقایسه",
                "comparelist",
            )
        ],
        [
            _button(
                "💬 پیام‌های من",
                "notifications",
            )
        ],
        [
            _button(
                "📋 درخواست‌های من",
                "myrequests",
            )
        ],
        [
            _button(
                "🛟 پشتیبانی ارزانکده",
                "supportstart:buyer",
            )
        ],
        [
            _button(
                "👤 پروفایل من",
                "myprofile",
            )
        ],
        _back_button("main"),
        [
            _button(
                "🔄 شروع دوباره",
                "restart_button",
            )
        ],
    ]

    await _edit_callback(
        telegram,
        callback_query,
        (
            "👤 <b>حساب من</b>\n\n"
            "👤 حالت خرید\n\n"
            "اینجا می‌تونی حساب و فعالیت‌های خریدت "
            "رو مدیریت کنی."
        ),
        _keyboard(rows),
    )


async def _render_seller_panel(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    user_id: int,
) -> None:
    has_store = await _user_has_any_seller(
        db,
        user_id,
    )

    rows: list[list[dict[str, Any]]] = [
        [
            _mode_switch_button("seller"),
        ]
    ]

    text = (
        "👋 <b>خب، رسیدیم به فروشگاهت!</b>\n\n"
        "همه‌چی که برای بهتر شدن فروشگاهت لازمه، "
        "همینجاست."
    )

    if not has_store:
        text += (
            "\n\nهنوز فروشگاهی ثبت نکردی؛ "
            "هر وقت آماده بودی از همینجا شروع کن 👇"
        )

        rows.append(
            [
                _button(
                    "➕ ثبت فروشگاه من",
                    "registerseller",
                )
            ]
        )

    rows.extend(
        [
            [
                _button(
                    "📦 محصولاتم",
                    "myproducts",
                )
            ],
            [
                _button(
                    "🏪 فروشگاهم",
                    "myshop",
                )
            ],
            [
                _button(
                    "👀 چقدر دیده شدم",
                    "storestatus",
                )
            ],
            [
                _button(
                    "📣 بیشتر دیده بشم",
                    "ads",
                )
            ],
            [
                _button(
                    "🛟 کمک می‌خوام",
                    "supportstart:seller",
                )
            ],
            [
                _button(
                    "📋 درخواست‌های من",
                    "myrequests",
                )
            ],
            [
                _button(
                    "🛍️ برم خرید کنم",
                    "setmode:buyer",
                )
            ],
            _back_button("main"),
            [
                _button(
                    "🔄 شروع دوباره",
                    "restart_button",
                )
            ],
        ]
    )

    await _edit_callback(
        telegram,
        callback_query,
        text,
        _keyboard(rows),
    )


async def _render_admin_panel(
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    """
    Temporary integration boundary for the future Worker
    admin module.

    The admin panel itself will be migrated separately.
    """

    await _edit_callback(
        telegram,
        callback_query,
        (
            "🛡️ <b>پنل مدیریت</b>\n\n"
            "پنل مدیریت در حال انتقال به نسخه Cloudflare است."
        ),
        _keyboard(
            [
                [
                    _button(
                        "👤 حالت خرید",
                        "setmode:buyer",
                    )
                ],
                _back_button("main"),
            ]
        ),
    )


async def render_active_mode(
    db: Any,
    telegram: Any,
    chat_id: int,
    user_id: int,
    mode: str,
    telegram_user_id: Optional[int] = None,
) -> None:
    """
    Render an active account mode from a normal message context.

    This is used by /start so returning users reach the same
    Worker account panels used by the account/mode callbacks.
    """

    normalized_mode = str(
        mode or "buyer"
    ).strip().lower()

    if normalized_mode not in VALID_MODES:
        normalized_mode = "buyer"

    if telegram_user_id is None:
        row = await db.fetchone(
            """
            SELECT telegram_id
            FROM users
            WHERE id = ?
            LIMIT 1;
            """,
            (user_id,),
        )

        if row is None:
            raise RuntimeError(
                "Failed to resolve Telegram user id."
            )

        telegram_user_id = int(
            row["telegram_id"]
        )

    callback_query = {
        "message": {
            "chat": {
                "id": int(chat_id),
            }
        },
        "from": {
            "id": int(
                telegram_user_id
            ),
        },
    }

    if normalized_mode == "admin":
        await _render_admin_panel(
            telegram,
            callback_query,
        )
        return

    if normalized_mode == "seller":
        await _render_seller_panel(
            db,
            telegram,
            callback_query,
            user_id,
        )
        return

    await _render_buyer_panel(
        db,
        telegram,
        callback_query,
        user_id,
    )


async def handle_account(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    env: Any,
) -> None:
    """
    Role-aware account entry point.

    Buyer, seller and admin are modes of the same user
    identity. Seller mode does not require an existing store.
    """

    chat_id, telegram_user_id = _message_context(
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

    await clear_state(
        db,
        user_id,
    )

    mode = await _get_active_mode(
        db,
        user_id,
    )

    if mode == "admin":
        if await _is_admin(
            env,
            telegram_user_id,
        ):
            await _render_admin_panel(
                telegram,
                callback_query,
            )
        else:
            await db.execute(
                """
                UPDATE users
                SET active_mode = 'buyer',
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    _now_iso(),
                    user_id,
                ),
            )

            await _render_buyer_panel(
                db,
                telegram,
                callback_query,
                user_id,
            )

    elif mode == "seller":
        await _render_seller_panel(
            db,
            telegram,
            callback_query,
            user_id,
        )

    else:
        await _render_buyer_panel(
            db,
            telegram,
            callback_query,
            user_id,
        )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_set_mode(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
    env: Any,
) -> None:
    """
    Switch the active mode of the current user.

    Seller mode is available even when the user does not
    own a seller yet.

    Admin mode is never granted through an ordinary user
    callback.
    """

    data = str(
        callback_query.get("data") or ""
    )

    if ":" not in data:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ حالت نامعتبر است.",
            show_alert=True,
        )
        return

    mode = data.split(
        ":",
        1,
    )[1].strip().lower()

    if mode not in VALID_MODES:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ حالت نامعتبر است.",
            show_alert=True,
        )
        return

    _, telegram_user_id = _message_context(
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

    await clear_state(
        db,
        user_id,
    )

    if mode == "admin":
        if not await _is_admin(
            env,
            telegram_user_id,
        ):
            await _answer_callback(
                telegram,
                callback_query,
                text=(
                    "⛔️ این حالت فقط برای ادمین "
                    "در دسترس است."
                ),
                show_alert=True,
            )
            return

    await db.execute(
        """
        UPDATE users
        SET active_mode = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            mode,
            _now_iso(),
            user_id,
        ),
    )

    if mode == "admin":
        await _render_admin_panel(
            telegram,
            callback_query,
        )

    elif mode == "seller":
        await _render_seller_panel(
            db,
            telegram,
            callback_query,
            user_id,
        )

    else:
        await _render_buyer_panel(
            db,
            telegram,
            callback_query,
            user_id,
        )

    await _answer_callback(
        telegram,
        callback_query,
    )


__all__ = [
    "VALID_MODES",
    "handle_account",
    "handle_set_mode",
    "render_active_mode",
]