# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Repository / data-access layer
"""

from __future__ import annotations

from typing import Any, Optional

from .config import ADMIN_CHAT_ID
from .constants import COMPARE_MAX_ITEMS
from .database import db
from .utils import now_iso


# ======================================================================
# USERS
# ======================================================================


async def get_user(user_id: int) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT *
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (user_id,),
    )


async def ensure_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> dict[str, Any]:
    user = await get_user(user_id)

    if user:
        return user

    await db.execute(
        """
        INSERT OR IGNORE INTO users (
            telegram_id,
            username,
            first_name,
            role,
            created_at
        )
        VALUES (?, ?, ?, 'user', ?);
        """,
        (
            user_id,
            username,
            first_name,
            now_iso(),
        ),
    )

    user = await get_user(user_id)

    if not user:
        raise RuntimeError(f"Failed to create user {user_id}")

    return user


async def update_user_role(
    user_id: int,
    role: str,
) -> bool:
    await db.execute(
        """
        UPDATE users
        SET role = ?
        WHERE telegram_id = ?;
        """,
        (
            role,
            user_id,
        ),
    )

    return True


# ======================================================================
# PRODUCTS
# ======================================================================


async def get_product(
    product_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT
            p.*,
            s.name AS seller_name,
            s.telegram_id AS seller_telegram_id,
            c.name AS category_name
        FROM products p
        LEFT JOIN sellers s
            ON s.id = p.seller_id
        LEFT JOIN categories c
            ON c.id = p.category_id
        WHERE p.id = ?
        LIMIT 1;
        """,
        (product_id,),
    )


async def get_products_by_ids(
    product_ids: list[int],
) -> list[dict[str, Any]]:
    if not product_ids:
        return []

    placeholders = ",".join("?" for _ in product_ids)

    return await db.fetchall(
        f"""
        SELECT
            p.*,
            s.name AS seller_name,
            c.name AS category_name
        FROM products p
        LEFT JOIN sellers s
            ON s.id = p.seller_id
        LEFT JOIN categories c
            ON c.id = p.category_id
        WHERE p.id IN ({placeholders});
        """,
        tuple(product_ids),
    )


async def get_products_for_compare(
    product_ids: list[int],
) -> list[dict[str, Any]]:
    if not product_ids:
        return []

    product_ids = product_ids[:COMPARE_MAX_ITEMS]

    placeholders = ",".join("?" for _ in product_ids)

    return await db.fetchall(
        f"""
        SELECT
            p.*,
            s.name AS seller_name,
            s.telegram_id AS seller_telegram_id,
            c.name AS category_name
        FROM products p
        LEFT JOIN sellers s
            ON s.id = p.seller_id
        LEFT JOIN categories c
            ON c.id = p.category_id
        WHERE p.id IN ({placeholders})
        ORDER BY p.id ASC;
        """,
        tuple(product_ids),
    )


async def increment_product_views(
    product_id: int,
) -> bool:
    await db.execute(
        """
        UPDATE products
        SET views = COALESCE(views, 0) + 1
        WHERE id = ?;
        """,
        (product_id,),
    )

    return True


# ======================================================================
# SELLERS
# ======================================================================


async def get_seller(
    seller_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT *
        FROM sellers
        WHERE id = ?
        LIMIT 1;
        """,
        (seller_id,),
    )


async def get_seller_by_telegram_id(
    telegram_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT *
        FROM sellers
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (telegram_id,),
    )


async def get_seller_products(
    seller_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT *
        FROM products
        WHERE seller_id = ?
        ORDER BY id DESC;
        """,
        (seller_id,),
    )


# ======================================================================
# FAVORITES
# ======================================================================


async def is_favorite(
    user_id: int,
    product_id: int,
) -> bool:
    row = await db.fetchone(
        """
        SELECT 1
        FROM favorites
        WHERE user_id = ?
          AND product_id = ?
        LIMIT 1;
        """,
        (
            user_id,
            product_id,
        ),
    )

    return row is not None


async def add_favorite(
    user_id: int,
    product_id: int,
) -> bool:
    await db.execute(
        """
        INSERT OR IGNORE INTO favorites (
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

    return True


async def remove_favorite(
    user_id: int,
    product_id: int,
) -> bool:
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

    return True


async def get_user_favorites(
    user_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT
            p.*,
            s.name AS seller_name,
            c.name AS category_name
        FROM favorites f
        JOIN products p
            ON p.id = f.product_id
        LEFT JOIN sellers s
            ON s.id = p.seller_id
        LEFT JOIN categories c
            ON c.id = p.category_id
        WHERE f.user_id = ?
        ORDER BY f.created_at DESC;
        """,
        (user_id,),
    )


# ======================================================================
# SELLER FAVORITES
# ======================================================================


async def is_seller_favorite(
    user_id: int,
    seller_id: int,
) -> bool:
    row = await db.fetchone(
        """
        SELECT 1
        FROM seller_favorites
        WHERE user_id = ?
          AND seller_id = ?
        LIMIT 1;
        """,
        (
            user_id,
            seller_id,
        ),
    )

    return row is not None


async def add_seller_favorite(
    user_id: int,
    seller_id: int,
) -> bool:
    await db.execute(
        """
        INSERT OR IGNORE INTO seller_favorites (
            user_id,
            seller_id,
            created_at
        )
        VALUES (?, ?, ?);
        """,
        (
            user_id,
            seller_id,
            now_iso(),
        ),
    )

    return True


async def remove_seller_favorite(
    user_id: int,
    seller_id: int,
) -> bool:
    await db.execute(
        """
        DELETE FROM seller_favorites
        WHERE user_id = ?
          AND seller_id = ?;
        """,
        (
            user_id,
            seller_id,
        ),
    )

    return True


async def get_user_seller_favorites(
    user_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT
            s.*
        FROM seller_favorites sf
        JOIN sellers s
            ON s.id = sf.seller_id
        WHERE sf.user_id = ?
        ORDER BY sf.created_at DESC;
        """,
        (user_id,),
    )


# ======================================================================
# REVIEWS
# ======================================================================


async def get_seller_reviews(
    seller_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT
            r.*,
            u.first_name,
            u.username
        FROM reviews r
        LEFT JOIN users u
            ON u.telegram_id = r.user_id
        WHERE r.seller_id = ?
        ORDER BY r.created_at DESC;
        """,
        (seller_id,),
    )


async def get_product_reviews(
    product_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT
            r.*,
            u.first_name,
            u.username
        FROM reviews r
        LEFT JOIN users u
            ON u.telegram_id = r.user_id
        WHERE r.product_id = ?
        ORDER BY r.created_at DESC;
        """,
        (product_id,),
    )


async def create_review(
    user_id: int,
    seller_id: int,
    product_id: Optional[int],
    rating: int,
    comment: Optional[str],
) -> bool:
    await db.execute(
        """
        INSERT INTO reviews (
            user_id,
            seller_id,
            product_id,
            rating,
            comment,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (
            user_id,
            seller_id,
            product_id,
            rating,
            comment,
            now_iso(),
        ),
    )

    return True


# ======================================================================
# REPORTS
# ======================================================================


async def create_report(
    user_id: int,
    target_type: str,
    target_id: int,
    reason: str,
) -> bool:
    await db.execute(
        """
        INSERT INTO reports (
            user_id,
            target_type,
            target_id,
            reason,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, 'pending', ?);
        """,
        (
            user_id,
            target_type,
            target_id,
            reason,
            now_iso(),
        ),
    )

    return True


async def get_pending_reports(
    limit: int = 50,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT *
        FROM reports
        WHERE status = 'pending'
        ORDER BY created_at ASC
        LIMIT ?;
        """,
        (limit,),
    )


async def update_report_status(
    report_id: int,
    status: str,
) -> bool:
    await db.execute(
        """
        UPDATE reports
        SET status = ?
        WHERE id = ?;
        """,
        (
            status,
            report_id,
        ),
    )

    return True


# ======================================================================
# REQUESTS
# ======================================================================


async def create_request(
    user_id: int,
    request_type: str,
    title: str,
    description: Optional[str] = None,
) -> Optional[int]:
    cursor = await db.execute(
        """
        INSERT INTO requests (
            user_id,
            request_type,
            title,
            description,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, 'pending', ?);
        """,
        (
            user_id,
            request_type,
            title,
            description,
            now_iso(),
        ),
    )

    return cursor.lastrowid if cursor else None


async def get_request(
    request_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT *
        FROM requests
        WHERE id = ?
        LIMIT 1;
        """,
        (request_id,),
    )


async def get_user_requests(
    user_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT *
        FROM requests
        WHERE user_id = ?
        ORDER BY created_at DESC;
        """,
        (user_id,),
    )


async def get_pending_requests(
    limit: int = 50,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT *
        FROM requests
        WHERE status = 'pending'
        ORDER BY created_at ASC
        LIMIT ?;
        """,
        (limit,),
    )


async def update_request_status(
    request_id: int,
    status: str,
) -> bool:
    await db.execute(
        """
        UPDATE requests
        SET status = ?
        WHERE id = ?;
        """,
        (
            status,
            request_id,
        ),
    )

    return True


# ======================================================================
# NOTIFICATIONS
# ======================================================================


async def get_user_notifications(
    user_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT *
        FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?;
        """,
        (
            user_id,
            limit,
        ),
    )


async def mark_notification_read(
    notification_id: int,
    user_id: int,
) -> bool:
    await db.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE id = ?
          AND user_id = ?;
        """,
        (
            notification_id,
            user_id,
        ),
    )

    return True


# ======================================================================
# REFERRALS
# ======================================================================


async def get_referral_by_seller(
    seller_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT *
        FROM referrals
        WHERE seller_id = ?
        LIMIT 1;
        """,
        (seller_id,),
    )


async def get_referral_rewards(
    seller_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT *
        FROM referral_rewards
        WHERE seller_id = ?
        ORDER BY created_at DESC;
        """,
        (seller_id,),
    )


# ======================================================================
# ORDERS
# ======================================================================


async def create_order(
    buyer_user_id: int,
    seller_id: int,
    product_id: int,
    quantity: int = 1,
    unit_price: Optional[int] = None,
) -> Optional[int]:
    cursor = await db.execute(
        """
        INSERT INTO orders (
            buyer_user_id,
            seller_id,
            product_id,
            quantity,
            unit_price,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, 'pending', ?);
        """,
        (
            buyer_user_id,
            seller_id,
            product_id,
            quantity,
            unit_price,
            now_iso(),
        ),
    )

    return cursor.lastrowid if cursor else None


async def get_order(
    order_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        LIMIT 1;
        """,
        (order_id,),
    )


async def get_user_orders(
    user_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT *
        FROM orders
        WHERE buyer_user_id = ?
        ORDER BY created_at DESC;
        """,
        (user_id,),
    )


async def get_seller_orders(
    seller_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT *
        FROM orders
        WHERE seller_id = ?
        ORDER BY created_at DESC;
        """,
        (seller_id,),
    )


async def update_order_status(
    order_id: int,
    status: str,
) -> bool:
    await db.execute(
        """
        UPDATE orders
        SET status = ?
        WHERE id = ?;
        """,
        (
            status,
            order_id,
        ),
    )

    return True


# ======================================================================
# AUDIT LOG
# ======================================================================


async def create_audit_log(
    actor_user_id: Optional[int],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[str] = None,
) -> bool:
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

    return True


async def get_audit_logs(
    limit: int = 100,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT *
        FROM audit_log
        ORDER BY created_at DESC
        LIMIT ?;
        """,
        (limit,),
    )


# ======================================================================
# ADMIN HELPERS
# ======================================================================


async def get_admin_chat_id() -> Optional[int]:
    return ADMIN_CHAT_ID


# ======================================================================
# COMPARE
# ======================================================================

COMPARE_INTRO_TEXT = (
    "⚖️ مقایسه چیه؟\n"
    "دو محصول رو کنار هم بذار تا راحت‌تر انتخاب کنی. ✨"
)


_compare_sessions: dict[int, list[int]] = {}


def get_compare_selection(
    user_id: int,
) -> list[int]:
    return list(
        _compare_sessions.get(
            user_id,
            [],
        )
    )


def set_compare_selection(
    user_id: int,
    selection: list[int],
) -> None:
    normalized: list[int] = []

    for product_id in selection:
        if product_id in normalized:
            continue

        normalized.append(product_id)

        if len(normalized) >= COMPARE_MAX_ITEMS:
            break

    if normalized:
        _compare_sessions[user_id] = normalized
    else:
        _compare_sessions.pop(
            user_id,
            None,
        )


def clear_compare_selection(
    user_id: int,
) -> None:
    _compare_sessions.pop(
        user_id,
        None,
    )


def compare_add(
    selection: list[int],
    product_id: int,
) -> tuple[list[int], str]:
    current = list(selection)

    if product_id in current:
        return current, "already_in_selection"

    if len(current) >= COMPARE_MAX_ITEMS:
        return current, "already_full"

    current.append(product_id)

    if len(current) >= COMPARE_MAX_ITEMS:
        return current, "added_ready"

    return current, "added_need_one_more"


async def has_seen_compare_intro(
    user_id: int,
) -> bool:
    row = await db.fetchone(
        """
        SELECT has_seen_compare_intro
        FROM users
        WHERE id = ?;
        """,
        (user_id,),
    )

    return bool(
        row and row["has_seen_compare_intro"]
    )


async def mark_compare_intro_seen(
    user_id: int,
) -> None:
    await db.execute(
        """
        UPDATE users
        SET has_seen_compare_intro = 1
        WHERE id = ?;
        """,
        (user_id,),
    )


async def get_compare_products(
    product_ids: list[int],
) -> list[dict[str, Any]]:
    """
    Fetch products for comparison.

    The maximum number of products is controlled centrally by
    bot.constants.COMPARE_MAX_ITEMS.
    """
    if not product_ids:
        return []

    product_ids = product_ids[:COMPARE_MAX_ITEMS]

    placeholders = ",".join("?" for _ in product_ids)

    return await db.fetchall(
        f"""
        SELECT
            p.*,
            s.name AS seller_name,
            c.name AS category_name
        FROM products p
        LEFT JOIN sellers s
            ON s.id = p.seller_id
        LEFT JOIN categories c
            ON c.id = p.category_id
        WHERE p.id IN ({placeholders})
        ORDER BY p.id ASC;
        """,
        tuple(product_ids),
    )


# ======================================================================
# GENERIC HELPERS
# ======================================================================


async def execute(
    query: str,
    params: tuple[Any, ...] = (),
):
    return await db.execute(query, params)


async def fetchone(
    query: str,
    params: tuple[Any, ...] = (),
):
    return await db.fetchone(query, params)


async def fetchall(
    query: str,
    params: tuple[Any, ...] = (),
):
    return await db.fetchall(query, params)