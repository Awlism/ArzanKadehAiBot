# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Utility helpers
"""

import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from .config import ADMIN_CHAT_ID
from .database import db


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def format_price(value) -> str:
    if value is None:
        return "قیمت نامشخص"

    try:
        number = int(value)
    except (TypeError, ValueError):
        return str(value)

    return f"{number:,} تومان"


def status_badge(status: str) -> str:
    badges = {
        "PENDING": "🟡",
        "REJECTED": "🔴",
        "APPROVED": "🟢",
        "COORDINATING": "🔵",
        "ACTIVE": "🟢",
        "EXPIRED": "⚫",
        "CONFIRMED": "🔵",
        "COMPLETED": "✅",
        "CANCELLED": "❌",
        "running": "🟢",
        "active": "🟢",
        "inactive": "⚪",
    }
    return badges.get(status, "⚪")


def _normalize_url(value: Optional[str], scheme: str = "https") -> Optional[str]:
    if not value:
        return None

    value = value.strip()
    if not value:
        return None

    if "://" not in value:
        value = f"{scheme}://{value}"

    parsed = urlparse(value)

    if not parsed.netloc:
        return None

    return value


def instagram_url(username: Optional[str]) -> Optional[str]:
    if not username:
        return None

    username = username.strip()
    username = re.sub(r"^https?://(www\.)?instagram\.com/", "", username)
    username = username.strip("/").lstrip("@")

    if not username:
        return None

    return f"https://instagram.com/{username}"


def telegram_url(username: Optional[str]) -> Optional[str]:
    if not username:
        return None

    username = username.strip()
    username = re.sub(r"^https?://(www\.)?t\.me/", "", username)
    username = username.strip("/").lstrip("@")

    if not username:
        return None

    return f"https://t.me/{username}"


def website_url(value: Optional[str]) -> Optional[str]:
    return _normalize_url(value)


def whatsapp_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    value = value.strip()

    if value.startswith("http://") or value.startswith("https://"):
        return value

    digits = re.sub(r"\D", "", value)

    if not digits:
        return None

    return f"https://wa.me/{digits}"


async def safe_edit(
    callback: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> bool:
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
        )
        return True
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return False
        raise


async def ensure_user(user) -> int:
    user_id = user.id
    username = getattr(user, "username", None)
    first_name = getattr(user, "first_name", None)

    existing = await db.fetchone(
        "SELECT id FROM users WHERE id = ?;",
        (user_id,),
    )

    if existing:
        await db.execute(
            """
            UPDATE users
            SET username = ?,
                first_name = ?,
                updated_at = ?
            WHERE id = ?;
            """,
            (
                username,
                first_name,
                now_iso(),
                user_id,
            ),
        )
        return user_id

    now = now_iso()

    await db.execute(
        """
        INSERT INTO users (
            id,
            username,
            first_name,
            active_mode,
            has_seen_compare_intro,
            role_chosen,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, 'buyer', 0, 0, ?, ?);
        """,
        (
            user_id,
            username,
            first_name,
            now,
            now,
        ),
    )

    return user_id


async def log_event(
    user_id: Optional[int],
    event_type: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    metadata: Optional[str] = None,
) -> None:
    await db.execute(
        """
        INSERT INTO events (
            user_id,
            event_type,
            entity_type,
            entity_id,
            metadata,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (
            user_id,
            event_type,
            entity_type,
            entity_id,
            metadata,
            now_iso(),
        ),
    )


async def notify_user(
    user_id: int,
    text: str,
    bot=None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> bool:
    if bot is None:
        return False

    try:
        await bot.send_message(
            user_id,
            text,
            reply_markup=reply_markup,
        )

        await db.execute(
            """
            INSERT INTO notifications (
                user_id,
                message,
                is_read,
                created_at
            )
            VALUES (?, ?, 0, ?);
            """,
            (
                user_id,
                text,
                now_iso(),
            ),
        )

        return True

    except Exception:
        return False


async def log_audit(
    actor_user_id: Optional[int],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[str] = None,
) -> None:
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
            actor_user_id,
            action,
            entity_type,
            entity_id,
            details,
            now_iso(),
        ),
    )


async def send_admin_dm(
    bot,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> bool:
    if not ADMIN_CHAT_ID:
        return False

    try:
        await bot.send_message(
            ADMIN_CHAT_ID,
            text,
            reply_markup=reply_markup,
        )
        return True
    except Exception:
        return False


async def restart_requested(
    message: Message,
    state: FSMContext,
) -> bool:
    if (message.text or "").strip() == "/start":
        await state.clear()
        await ensure_user(message.from_user)

        from .keyboards import main_menu_keyboard

        await message.answer(
            "🛍️ <b>به ارزانکده خوش اومدی!</b>\n\n"
            "یک محل ساده برای پیدا کردن فروشگاه‌ها، محصولات و خدمات ایرانی.\n\n"
            "یکی از گزینه‌های زیر رو انتخاب کن 👇",
            reply_markup=main_menu_keyboard(),
        )

        return True

    return False