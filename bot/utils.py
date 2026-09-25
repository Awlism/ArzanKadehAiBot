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
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
)

from .config import ADMIN_CHAT_ID
from .constants import (
    _DANGEROUS_URL_SCHEME_PREFIXES,
    _UNSAFE_URL_CHARS,
)
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


def _normalize_url(
    value: Optional[str],
    scheme: str = "https",
) -> Optional[str]:
    """
    Normalize and validate an HTTP/HTTPS URL.

    Only http and https URLs are accepted.
    Unsafe control characters, whitespace, dangerous schemes,
    malformed hosts, credentials, and invalid ports are rejected.
    """
    if not value:
        return None

    value = value.strip()

    if not value:
        return None

    if any(
        unsafe_char in value
        for unsafe_char in _UNSAFE_URL_CHARS
    ):
        return None

    lowered = value.lower()

    if any(
        lowered.startswith(prefix)
        for prefix in _DANGEROUS_URL_SCHEME_PREFIXES
    ):
        return None

    if "://" not in value:
        value = f"{scheme}://{value}"

    parsed = urlparse(value)

    if parsed.scheme.lower() not in (
        "http",
        "https",
    ):
        return None

    if not parsed.netloc:
        return None

    if parsed.username is not None:
        return None

    if parsed.password is not None:
        return None

    try:
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return None

    if not hostname:
        return None

    hostname = hostname.strip().lower()

    if not hostname:
        return None

    if hostname.startswith(".") or hostname.endswith("."):
        return None

    if ".." in hostname:
        return None

    return value


def instagram_url(
    username: Optional[str],
) -> Optional[str]:
    if not username:
        return None

    username = username.strip()

    username = re.sub(
        r"^https?://(www\.)?instagram\.com/",
        "",
        username,
    )

    username = username.strip("/").lstrip("@")

    if not username:
        return None

    if any(
        unsafe_char in username
        for unsafe_char in _UNSAFE_URL_CHARS
    ):
        return None

    if not re.fullmatch(
        r"[A-Za-z0-9._]+",
        username,
    ):
        return None

    return f"https://instagram.com/{username}"


def telegram_url(
    username: Optional[str],
) -> Optional[str]:
    if not username:
        return None

    username = username.strip()

    username = re.sub(
        r"^https?://(www\.)?t\.me/",
        "",
        username,
    )

    username = username.strip("/").lstrip("@")

    if not username:
        return None

    if any(
        unsafe_char in username
        for unsafe_char in _UNSAFE_URL_CHARS
    ):
        return None

    if not re.fullmatch(
        r"[A-Za-z0-9_]+",
        username,
    ):
        return None

    return f"https://t.me/{username}"


def website_url(
    value: Optional[str],
) -> Optional[str]:
    return _normalize_url(value)


def whatsapp_url(
    value: Optional[str],
) -> Optional[str]:
    if not value:
        return None

    value = value.strip()

    if not value:
        return None

    if value.startswith(
        "http://"
    ) or value.startswith(
        "https://"
    ):
        return _normalize_url(
            value
        )

    if any(
        unsafe_char in value
        for unsafe_char in _UNSAFE_URL_CHARS
    ):
        return None

    digits = re.sub(
        r"\D",
        "",
        value,
    )

    if digits.startswith("00"):
        digits = digits[2:]

    if not digits:
        return None

    if len(digits) < 7 or len(digits) > 15:
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

        try:
            await callback.message.answer(
                text,
                reply_markup=reply_markup,
            )
            return True
        except Exception:
            raise


async def ensure_user(user) -> int:
    telegram_id = user.id

    username = getattr(
        user,
        "username",
        None,
    )

    first_name = getattr(
        user,
        "first_name",
        None,
    )

    last_name = getattr(
        user,
        "last_name",
        None,
    )

    existing = await db.fetchone(
        """
        SELECT id
        FROM users
        WHERE telegram_id = ?;
        """,
        (telegram_id,),
    )

    if existing:
        await db.execute(
            """
            UPDATE users
            SET username = ?,
                first_name = ?,
                last_name = ?,
                updated_at = ?
            WHERE telegram_id = ?;
            """,
            (
                username,
                first_name,
                last_name,
                now_iso(),
                telegram_id,
            ),
        )

        return existing["id"]

    now = now_iso()

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
        VALUES (?, ?, ?, ?, ?, ?);
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

    created = await db.fetchone(
        """
        SELECT id
        FROM users
        WHERE telegram_id = ?;
        """,
        (telegram_id,),
    )

    return created["id"]


async def log_event(
    user_id: Optional[int],
    event_type: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
) -> None:
    try:
        await db.execute(
            """
            INSERT INTO events (
                user_id,
                event_type,
                entity_type,
                entity_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                user_id,
                event_type,
                entity_type,
                entity_id,
                now_iso(),
            ),
        )
    except Exception:
        return


async def log_audit(
    actor_user_id: Optional[int],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[str] = None,
) -> None:
    try:
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
    except Exception:
        return


def is_admin_telegram_id(
    telegram_id: Optional[int],
) -> bool:
    return bool(
        ADMIN_CHAT_ID
        and telegram_id
        and telegram_id == ADMIN_CHAT_ID
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
    if (message.text or "").strip() != "/start":
        return False

    await state.clear()

    await ensure_user(
        message.from_user
    )

    from .keyboards import main_menu_keyboard

    await message.answer(
        "🛍️ <b>به ارزانکده خوش اومدی!</b>\n\n"
        "یک محل ساده برای پیدا کردن فروشگاه‌ها، "
        "محصولات و خدمات ایرانی.\n\n"
        "یکی از گزینه‌های زیر رو انتخاب کن 👇",
        reply_markup=main_menu_keyboard(),
    )

    return True