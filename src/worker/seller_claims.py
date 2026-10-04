# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker seller-ownership claim handlers.

This module intentionally does not import aiogram, sqlite,
aiosqlite, or any legacy bot module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Optional

from worker.telegram import TelegramClient


PAGE_SIZE = 10


def _html(value: Any) -> str:
    if value is None:
        return ""

    return escape(str(value), quote=False)


def _button(text: str, callback_data: str) -> dict[str, Any]:
    return {
        "text": text,
        "callback_data": callback_data,
    }


def _keyboard(rows: list[list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "inline_keyboard": rows,
    }


def _back_button(callback_data: str) -> list[dict[str, Any]]:
    return [
        _button("🔙 بازگشت", callback_data)
    ]


def _parse_positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None

    if parsed < 1:
        return None

    return parsed


def _callback_context(
    callback_query: dict[str, Any],
) -> tuple[Optional[int], Optional[int]]:
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    user = callback_query.get("from") or {}

    chat_id = _parse_positive_int(chat.get("id"))
    telegram_user_id = _parse_positive_int(user.get("id"))

    return chat_id, telegram_user_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    telegram: TelegramClient,
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
    telegram: TelegramClient,
    callback_query: dict[str, Any],
    text: str,
    keyboard: Optional[dict[str, Any]] = None,
) -> None:
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}

    chat_id = _parse_positive_int(chat.get("id"))
    message_id = _parse_positive_int(message.get("message_id"))

    if chat_id is None or message_id is None:
        return

    await telegram.edit_message_text(
        chat_id,
        message_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def _audit(
    db: Any,
    actor_user_id: Optional[int],
    action: str,
    entity_id: Optional[int],
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
        VALUES (?, ?, 'seller_claim', ?, ?, ?);
        """,
        (
            actor_user_id,
            action,
            entity_id,
            details,
            _now_iso(),
        ),
    )


async def _notify_user(
    db: Any,
    user_id: int,
    title: str,
    message: str,
    notification_type: str = "info",
) -> None:
    await db.execute(
        """
        INSERT INTO notifications (
            user_id,
            title,
            message,
            notification_type,
            is_read,
            created_at
        )
        VALUES (?, ?, ?, ?, 0, ?);
        """,
        (
            user_id,
            title,
            message,
            notification_type,
            _now_iso(),
        ),
    )


def _is_admin(
    env: Any,
    telegram_user_id: int,
) -> bool:
    try:
        configured = env.ADMIN_CHAT_ID
    except Exception:
        return False

    if configured is None:
        return False

    try:
        return int(configured) == int(telegram_user_id)
    except (TypeError, ValueError):
        return False


async def _get_seller_claim(
    db: Any,
    claim_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT
            sc.*,
            s.name AS seller_name,
            s.status AS seller_status,
            s.owner_user_id,
            s.created_by_user_id,
            u.telegram_id AS claimant_telegram_id,
            u.username AS claimant_username,
            u.first_name AS claimant_first_name,
            u.last_name AS claimant_last_name
        FROM seller_claims sc
        JOIN sellers s
            ON s.id = sc.seller_id
        JOIN users u
            ON u.id = sc.user_id
        WHERE sc.id = ?
        LIMIT 1;
        """,
        (claim_id,),
    )


async def _get_pending_claims(
    db: Any,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT
            sc.*,
            s.name AS seller_name,
            s.status AS seller_status,
            u.telegram_id AS claimant_telegram_id,
            u.username AS claimant_username,
            u.first_name AS claimant_first_name
        FROM seller_claims sc
        JOIN sellers s
            ON s.id = sc.seller_id
        JOIN users u
            ON u.id = sc.user_id
        WHERE sc.status = 'PENDING'
        ORDER BY sc.created_at ASC, sc.id ASC
        LIMIT ?;
        """,
        (PAGE_SIZE,),
    )


async def _create_claim(
    db: Any,
    seller_id: int,
    user_id: int,
) -> Optional[int]:
    seller = await db.fetchone(
        """
        SELECT
            id,
            status,
            owner_user_id,
            created_by_user_id
        FROM sellers
        WHERE id = ?
        LIMIT 1;
        """,
        (seller_id,),
    )

    if not seller:
        return None

    if str(seller["status"] or "").upper() != "UNCLAIMED":
        return None

    if user_id in (
        seller["owner_user_id"],
        seller["created_by_user_id"],
    ):
        return None

    existing = await db.fetchone(
        """
        SELECT
            id,
            status
        FROM seller_claims
        WHERE seller_id = ?
          AND user_id = ?
        ORDER BY id DESC
        LIMIT 1;
        """,
        (
            seller_id,
            user_id,
        ),
    )

    if existing:
        status = str(existing["status"] or "").upper()

        if status == "PENDING":
            return int(existing["id"])

        if status == "APPROVED":
            return None

        if status != "REJECTED":
            return None

    now = _now_iso()

    try:
        result = await db.execute(
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
    except Exception:
        pending = await db.fetchone(
            """
            SELECT id
            FROM seller_claims
            WHERE seller_id = ?
              AND user_id = ?
              AND status = 'PENDING'
            ORDER BY id DESC
            LIMIT 1;
            """,
            (
                seller_id,
                user_id,
            ),
        )

        if pending is None:
            return None

        return int(pending["id"])

    if result.lastrowid is not None:
        return int(result.lastrowid)

    pending = await db.fetchone(
        """
        SELECT id
        FROM seller_claims
        WHERE seller_id = ?
          AND user_id = ?
          AND status = 'PENDING'
        ORDER BY id DESC
        LIMIT 1;
        """,
        (
            seller_id,
            user_id,
        ),
    )

    if pending is None:
        return None

    return int(pending["id"])


async def handle_claim(
    db: Any,
    telegram: TelegramClient,
    callback_query: dict[str, Any],
    env: Any,
) -> None:
    data = str(callback_query.get("data") or "")
    parts = data.split(":", 1)

    if len(parts) != 2:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    seller_id = _parse_positive_int(parts[1])

    if seller_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ شناسه فروشگاه نامعتبر است.",
            show_alert=True,
        )
        return

    user = callback_query.get("from") or {}

    telegram_user_id = _parse_positive_int(user.get("id"))

    if telegram_user_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر شناسایی نشد.",
            show_alert=True,
        )
        return

    user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )

    seller = await db.fetchone(
        """
        SELECT *
        FROM sellers
        WHERE id = ?
        LIMIT 1;
        """,
        (seller_id,),
    )

    if not seller:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ این فروشگاه یافت نشد.",
            show_alert=True,
        )
        return

    status = str(seller.get("status") or "").upper()

    if status != "UNCLAIMED":
        await _answer_callback(
            telegram,
            callback_query,
            text=(
                "⚠️ این فروشگاه دیگر برای "
                "درخواست مالکیت در دسترس نیست."
            ),
            show_alert=True,
        )
        return

    if user_id in (
        seller["owner_user_id"],
        seller["created_by_user_id"],
    ):
        await _answer_callback(
            telegram,
            callback_query,
            text=(
                "ℹ️ این فروشگاه همین حالا "
                "به حساب شما متصل است."
            ),
            show_alert=True,
        )
        return

    claim_id = await _create_claim(
        db,
        seller_id,
        user_id,
    )

    if claim_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text=(
                "⚠️ درخواست مالکیت ثبت نشد. "
                "ممکن است وضعیت فروشگاه تغییر کرده باشد."
            ),
            show_alert=True,
        )
        return

    await _audit(
        db,
        user_id,
        "seller_claim_requested",
        claim_id,
        details=f"seller_id={seller_id}",
    )

    admin_chat_id = None

    try:
        configured = env.ADMIN_CHAT_ID
        if configured is not None:
            admin_chat_id = int(configured)
    except (AttributeError, TypeError, ValueError):
        admin_chat_id = None

    if admin_chat_id:
        try:
            await telegram.send_message(
                admin_chat_id,
                (
                    "📩 <b>درخواست مالکیت جدید</b>\n\n"
                    f"🏪 فروشگاه: {_html(seller['name'])}\n"
                    f"🆔 Seller ID: {seller_id}\n"
                    f"👤 User ID: {user_id}\n"
                    f"📋 Claim ID: {claim_id}"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

    await _answer_callback(
        telegram,
        callback_query,
        text=(
            "✅ درخواست مالکیت ثبت شد. "
            "بعد از بررسی بهت خبر می‌دیم."
        ),
        show_alert=True,
    )


async def handle_seller_claims_admin(
    db: Any,
    telegram: TelegramClient,
    callback_query: dict[str, Any],
    env: Any,
) -> None:
    _, telegram_user_id = _callback_context(callback_query)

    if telegram_user_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر شناسایی نشد.",
            show_alert=True,
        )
        return

    if not _is_admin(env, telegram_user_id):
        await _answer_callback(
            telegram,
            callback_query,
            text=(
                "⛔️ این بخش فقط برای ادمین "
                "در دسترس است."
            ),
            show_alert=True,
        )
        return

    claims = await _get_pending_claims(db)

    rows: list[list[dict[str, Any]]] = []

    if not claims:
        text = (
            "🏪 <b>مالکیت فروشگاه‌ها</b>\n\n"
            "📭 درخواست مالکیتی در انتظار بررسی نیست."
        )
    else:
        lines = [
            "🏪 <b>مالکیت فروشگاه‌ها</b>",
            "",
        ]

        for claim in claims:
            claimant = (
                claim["claimant_first_name"]
                or (
                    f"@{claim['claimant_username']}"
                    if claim["claimant_username"]
                    else str(claim["claimant_telegram_id"])
                )
            )

            lines.append(
                f"📋 #{claim['id']} — "
                f"{_html(claim['seller_name'])}"
            )

            rows.append(
                [
                    _button(
                        (
                            f"🏪 "
                            f"{str(claim['seller_name'])[:30]}"
                        ),
                        f"sellerclaimdetail:{claim['id']}",
                    )
                ]
            )

            rows.append(
                [
                    _button(
                        f"👤 {str(claimant)[:30]}",
                        f"sellerclaimdetail:{claim['id']}",
                    )
                ]
            )

        text = "\n".join(lines)

    rows.append(_back_button("adminhome"))

    await _edit_callback(
        telegram,
        callback_query,
        text,
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_seller_claim_detail(
    db: Any,
    telegram: TelegramClient,
    callback_query: dict[str, Any],
    env: Any,
) -> None:
    _, telegram_user_id = _callback_context(callback_query)

    if telegram_user_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر شناسایی نشد.",
            show_alert=True,
        )
        return

    if not _is_admin(env, telegram_user_id):
        await _answer_callback(
            telegram,
            callback_query,
            text=(
                "⛔️ این بخش فقط برای ادمین "
                "در دسترس است."
            ),
            show_alert=True,
        )
        return

    data = str(callback_query.get("data") or "")
    parts = data.split(":", 1)

    if len(parts) != 2:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ شناسه درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    claim_id = _parse_positive_int(parts[1])

    if claim_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ شناسه درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    claim = await _get_seller_claim(
        db,
        claim_id,
    )

    if not claim:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ این درخواست مالکیت یافت نشد.",
            show_alert=True,
        )
        return

    claimant_name = (
        claim["claimant_first_name"]
        or (
            f"@{claim['claimant_username']}"
            if claim["claimant_username"]
            else str(claim["claimant_telegram_id"])
        )
    )

    status = str(claim["status"] or "").upper()

    status_labels = {
        "PENDING": "در انتظار بررسی",
        "APPROVED": "تأیید شده",
        "REJECTED": "رد شده",
    }

    lines = [
        "🏪 <b>جزئیات درخواست مالکیت</b>",
        "",
        f"فروشگاه: <b>{_html(claim['seller_name'])}</b>",
        f"درخواست‌دهنده: {_html(claimant_name)}",
        f"آیدی تلگرام: {_html(claim['claimant_telegram_id'])}",
        (
            "وضعیت: "
            f"{_html(status_labels.get(status, status))}"
        ),
        f"تاریخ ثبت: {_html(claim['created_at'])}",
    ]

    if claim.get("message"):
        lines.extend(
            [
                "",
                "💬 <b>توضیحات درخواست‌دهنده:</b>",
                _html(claim["message"]),
            ]
        )

    rows: list[list[dict[str, Any]]] = []

    if status == "PENDING":
        rows.append(
            [
                _button(
                    "✅ تأیید مالکیت",
                    f"sellerclaim:approve:{claim_id}",
                ),
                _button(
                    "❌ رد مالکیت",
                    f"sellerclaim:reject:{claim_id}",
                ),
            ]
        )

    rows.append(_back_button("sellerclaimsadmin"))

    await _edit_callback(
        telegram,
        callback_query,
        "\n".join(lines),
        _keyboard(rows),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def _approve_claim(
    db: Any,
    claim_id: int,
) -> bool:
    now = _now_iso()

    async with db.transaction() as transaction:
        claim = await transaction.fetchone(
            """
            SELECT
                id,
                seller_id,
                user_id,
                status
            FROM seller_claims
            WHERE id = ?
            LIMIT 1;
            """,
            (claim_id,),
        )

        if not claim:
            return False

        if claim["status"] != "PENDING":
            return False

        seller = await transaction.fetchone(
            """
            SELECT
                id,
                status,
                owner_user_id,
                created_by_user_id
            FROM sellers
            WHERE id = ?
            LIMIT 1;
            """,
            (claim["seller_id"],),
        )

        if not seller:
            return False

        if seller["status"] != "UNCLAIMED":
            return False

        if (
            seller["owner_user_id"] is not None
            and seller["owner_user_id"] != claim["user_id"]
        ):
            return False

        approved = await transaction.execute(
            """
            UPDATE seller_claims
            SET
                status = 'APPROVED',
                updated_at = ?
            WHERE id = ?
              AND status = 'PENDING'
              AND EXISTS (
                  SELECT 1
                  FROM sellers
                  WHERE id = ?
                    AND status = 'UNCLAIMED'
                    AND (
                        owner_user_id IS NULL
                        OR owner_user_id = ?
                    )
              );
            """,
            (
                now,
                claim_id,
                claim["seller_id"],
                claim["user_id"],
            ),
        )

        if approved.rowcount != 1:
            return False

        seller_updated = await transaction.execute(
            """
            UPDATE sellers
            SET
                owner_user_id = ?,
                status = 'CLAIMED',
                updated_at = ?
            WHERE id = ?
              AND status = 'UNCLAIMED'
              AND (
                  owner_user_id IS NULL
                  OR owner_user_id = ?
              )
              AND EXISTS (
                  SELECT 1
                  FROM seller_claims
                  WHERE id = ?
                    AND seller_id = ?
                    AND user_id = ?
                    AND status = 'APPROVED'
              );
            """,
            (
                claim["user_id"],
                now,
                claim["seller_id"],
                claim["user_id"],
                claim_id,
                claim["seller_id"],
                claim["user_id"],
            ),
        )

        if seller_updated.rowcount != 1:
            return False

        await transaction.execute(
            """
            UPDATE seller_claims
            SET
                status = 'REJECTED',
                updated_at = ?
            WHERE seller_id = ?
              AND status = 'PENDING'
              AND id != ?;
            """,
            (
                now,
                claim["seller_id"],
                claim_id,
            ),
        )

    return True


async def _reject_claim(
    db: Any,
    claim_id: int,
) -> bool:
    result = await db.execute(
        """
        UPDATE seller_claims
        SET
            status = 'REJECTED',
            updated_at = ?
        WHERE id = ?
          AND status = 'PENDING';
        """,
        (
            _now_iso(),
            claim_id,
        ),
    )

    return result.rowcount == 1


async def handle_seller_claim_decision(
    db: Any,
    telegram: TelegramClient,
    callback_query: dict[str, Any],
    env: Any,
) -> None:
    _, telegram_user_id = _callback_context(callback_query)

    if telegram_user_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ کاربر شناسایی نشد.",
            show_alert=True,
        )
        return

    if not _is_admin(env, telegram_user_id):
        await _answer_callback(
            telegram,
            callback_query,
            text=(
                "⛔️ این عملیات فقط برای ادمین "
                "در دسترس است."
            ),
            show_alert=True,
        )
        return

    data = str(callback_query.get("data") or "")
    parts = data.split(":")

    if len(parts) != 3:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    _, action, claim_id_raw = parts

    if action not in ("approve", "reject"):
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ عملیات نامعتبر است.",
            show_alert=True,
        )
        return

    claim_id = _parse_positive_int(claim_id_raw)

    if claim_id is None:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ شناسه درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    claim = await _get_seller_claim(
        db,
        claim_id,
    )

    if not claim:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ این درخواست مالکیت یافت نشد.",
            show_alert=True,
        )
        return

    if claim["status"] != "PENDING":
        await _answer_callback(
            telegram,
            callback_query,
            text=(
                "⚠️ این درخواست قبلاً "
                "تعیین‌تکلیف شده است."
            ),
            show_alert=True,
        )
        return

    admin_user_id = await _ensure_user(
        db,
        telegram_user_id,
        username=(callback_query.get("from") or {}).get("username"),
        first_name=(callback_query.get("from") or {}).get("first_name"),
        last_name=(callback_query.get("from") or {}).get("last_name"),
    )

    if action == "approve":
        updated = await _approve_claim(
            db,
            claim_id,
        )
    else:
        updated = await _reject_claim(
            db,
            claim_id,
        )

    if not updated:
        await _answer_callback(
            telegram,
            callback_query,
            text="⚠️ به‌روزرسانی درخواست انجام نشد.",
            show_alert=True,
        )
        return

    await _audit(
        db,
        admin_user_id,
        f"seller_claim_{action}d",
        claim_id,
    )

    if action == "approve":
        await _notify_user(
            db,
            claim["user_id"],
            "مالکیت فروشگاه",
            (
                "✅ درخواست مالکیت فروشگاهت تأیید شد. "
                "از این به بعد می‌تونی فروشگاه رو مدیریت کنی."
            ),
        )

        answer_text = "✅ مالکیت فروشگاه با موفقیت تأیید شد."

    else:
        await _notify_user(
            db,
            claim["user_id"],
            "مالکیت فروشگاه",
            (
                "❌ درخواست مالکیت فروشگاهت رد شد. "
                "اگر مدرک یا توضیح بیشتری داری، "
                "می‌تونی دوباره درخواست ثبت کنی."
            ),
        )

        answer_text = "❌ درخواست مالکیت رد شد."

    await _answer_callback(
        telegram,
        callback_query,
        text=answer_text,
        show_alert=True,
    )


__all__ = [
    "handle_claim",
    "handle_seller_claims_admin",
    "handle_seller_claim_detail",
    "handle_seller_claim_decision",
]