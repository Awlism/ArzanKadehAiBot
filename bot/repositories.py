# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Repository / data-access layer
"""

from __future__ import annotations

from typing import Any, Optional

from .config import ADMIN_CHAT_ID
from .constants import (
    COMPARE_MAX_ITEMS,
    VALID_MODES,
)
from .database import db
from .utils import now_iso


# ============================================================================
# USERS
# ============================================================================


async def get_user(
    user_id: int,
) -> Optional[dict[str, Any]]:
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
    last_name: Optional[str] = None,
) -> dict[str, Any]:
    user = await get_user(user_id)

    if user:
        return user

    now = now_iso()

    await db.execute(
        """
        INSERT OR IGNORE INTO users (
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
            user_id,
            username,
            first_name,
            last_name,
            now,
            now,
        ),
    )

    user = await get_user(user_id)

    if not user:
        raise RuntimeError(
            f"Failed to create user {user_id}"
        )

    return user


async def update_user_role(
    user_id: int,
    role: str,
) -> bool:
    if role not in VALID_MODES:
        return False

    await db.execute(
        """
        UPDATE users
        SET active_mode = ?,
            role_chosen = 1,
            updated_at = ?
        WHERE telegram_id = ?;
        """,
        (
            role,
            now_iso(),
            user_id,
        ),
    )

    return True


async def user_has_any_seller(
    user_id: int,
) -> bool:
    row = await db.fetchone(
        """
        SELECT 1
        FROM sellers
        WHERE owner_user_id = ?
           OR created_by_user_id = ?
        LIMIT 1;
        """,
        (
            user_id,
            user_id,
        ),
    )

    return row is not None


async def get_active_mode(
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

    if row and row["active_mode"] in VALID_MODES:
        return row["active_mode"]

    admin = await db.fetchone(
        """
        SELECT telegram_id
        FROM users
        WHERE id = ?
        LIMIT 1;
        """,
        (user_id,),
    )

    if (
        admin
        and ADMIN_CHAT_ID
        and admin["telegram_id"] == ADMIN_CHAT_ID
    ):
        return "admin"

    return "seller" if await user_has_any_seller(user_id) else "buyer"


async def set_active_mode(
    user_id: int,
    mode: str,
) -> bool:
    if mode not in VALID_MODES:
        return False

    await db.execute(
        """
        UPDATE users
        SET active_mode = ?,
            role_chosen = 1,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            mode,
            now_iso(),
            user_id,
        ),
    )

    return True


async def is_admin_user_id(
    user_id: int,
) -> bool:
    row = await db.fetchone(
        """
        SELECT telegram_id
        FROM users
        WHERE id = ?
        LIMIT 1;
        """,
        (user_id,),
    )

    return bool(
        row
        and ADMIN_CHAT_ID
        and row["telegram_id"] == ADMIN_CHAT_ID
    )


# ============================================================================
# PRODUCTS
# ============================================================================


async def get_product_by_id(
    product_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT
            p.*,
            s.name AS seller_name,
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


async def get_product(
    product_id: int,
) -> Optional[dict[str, Any]]:
    return await get_product_by_id(product_id)


async def get_products_by_ids(
    product_ids: list[int],
) -> list[dict[str, Any]]:
    if not product_ids:
        return []

    normalized_ids: list[int] = []

    for product_id in product_ids:
        if product_id < 1:
            continue

        if product_id not in normalized_ids:
            normalized_ids.append(product_id)

    if not normalized_ids:
        return []

    placeholders = ",".join(
        "?" for _ in normalized_ids
    )

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
        tuple(normalized_ids),
    )


async def create_product_record(
    seller_id: int,
    name: str,
    **fields: Any,
) -> int:
    allowed_fields = {
        "description",
        "category_id",
        "price",
        "old_price",
        "image_url",
        "stock_status",
    }

    clean_fields = {
        key: value
        for key, value in fields.items()
        if key in allowed_fields
    }

    columns = [
        "seller_id",
        "name",
        "created_at",
        "updated_at",
    ]

    values: list[Any] = [
        seller_id,
        name,
        now_iso(),
        now_iso(),
    ]

    for field in (
        "description",
        "category_id",
        "price",
        "old_price",
        "image_url",
        "stock_status",
    ):
        if field in clean_fields:
            columns.append(field)
            values.append(clean_fields[field])

    placeholders = ", ".join(
        "?" for _ in columns
    )

    cursor = await db.execute(
        f"""
        INSERT INTO products (
            {", ".join(columns)}
        )
        VALUES ({placeholders});
        """,
        tuple(values),
    )

    if cursor.lastrowid is None:
        raise RuntimeError(
            "Failed to create product."
        )

    return int(cursor.lastrowid)


async def delete_product_record(
    product_id: int,
) -> bool:
    await db.execute(
        """
        DELETE FROM products
        WHERE id = ?;
        """,
        (product_id,),
    )

    return True


async def increment_product_views(
    product_id: int,
) -> bool:
    await db.execute(
        """
        UPDATE products
        SET views = COALESCE(views, 0) + 1,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            now_iso(),
            product_id,
        ),
    )

    return True


async def get_product_statistics(
    product_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT
            p.id,
            p.name,
            p.views,
            p.rating,
            p.review_count,
            COUNT(DISTINCT f.id) AS favorite_count,
            COUNT(DISTINCT o.id) AS order_count
        FROM products p
        LEFT JOIN favorites f
            ON f.product_id = p.id
        LEFT JOIN orders o
            ON o.product_id = p.id
        WHERE p.id = ?
        GROUP BY
            p.id,
            p.name,
            p.views,
            p.rating,
            p.review_count;
        """,
        (product_id,),
    )


# ============================================================================
# SELLERS
# ============================================================================


async def get_seller_by_id(
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


async def get_seller(
    seller_id: int,
) -> Optional[dict[str, Any]]:
    return await get_seller_by_id(seller_id)


async def get_sellers_owned_by_user(
    user_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT *
        FROM sellers
        WHERE owner_user_id = ?
           OR created_by_user_id = ?
        ORDER BY id DESC;
        """,
        (
            user_id,
            user_id,
        ),
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


async def get_seller_statistics(
    seller_id: int,
) -> Optional[dict[str, Any]]:
    return await db.fetchone(
        """
        SELECT
            s.id,
            s.name,
            s.views,
            s.rating,
            s.review_count,
            COUNT(DISTINCT p.id) AS product_count,
            COUNT(DISTINCT sf.id) AS favorite_count,
            COUNT(DISTINCT o.id) AS order_count
        FROM sellers s
        LEFT JOIN products p
            ON p.seller_id = s.id
        LEFT JOIN seller_favorites sf
            ON sf.seller_id = s.id
        LEFT JOIN orders o
            ON o.seller_id = s.id
        WHERE s.id = ?
        GROUP BY
            s.id,
            s.name,
            s.views,
            s.rating,
            s.review_count;
        """,
        (seller_id,),
    )


# ============================================================================
# PRODUCT FAVORITES
# ============================================================================


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


# ============================================================================
# SELLER FAVORITES
# ============================================================================


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


async def toggle_seller_favorite(
    user_id: int,
    seller_id: int,
) -> bool:
    existing = await is_seller_favorite(
        user_id,
        seller_id,
    )

    if existing:
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
        return False

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


async def count_seller_favorites(
    seller_id: int,
) -> int:
    row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM seller_favorites
        WHERE seller_id = ?;
        """,
        (seller_id,),
    )

    return int(row["c"]) if row else 0


async def get_user_seller_favorites(
    user_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT s.*
        FROM seller_favorites sf
        JOIN sellers s
            ON s.id = sf.seller_id
        WHERE sf.user_id = ?
        ORDER BY sf.created_at DESC;
        """,
        (user_id,),
    )


# ============================================================================
# REVIEWS
# ============================================================================


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
            ON u.id = r.user_id
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
            ON u.id = r.user_id
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
            comment,
            now_iso(),
        ),
    )

    return True


# ============================================================================
# REPORTS
# ============================================================================


async def create_report(
    user_id: int,
    target_type: str,
    target_id: int,
    reason: str,
) -> bool:
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

    if seller_id is None and product_id is None:
        return False

    await db.execute(
        """
        INSERT INTO reports (
            user_id,
            seller_id,
            product_id,
            reason,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, 'PENDING', ?);
        """,
        (
            user_id,
            seller_id,
            product_id,
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
        WHERE status = 'PENDING'
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


# ============================================================================
# REQUESTS
# ============================================================================


REQUEST_STATUS_LABELS = {
    "PENDING": "در انتظار بررسی",
    "APPROVED": "تأیید شده",
    "REJECTED": "رد شده",
    "ACTIVE": "فعال",
    "COMPLETED": "تکمیل شده",
    "CANCELLED": "لغو شده",
}


async def create_request(
    user_id: int,
    request_type: str,
    title: str,
    description: Optional[str] = None,
) -> Optional[int]:
    now = now_iso()

    cursor = await db.execute(
        """
        INSERT INTO requests (
            user_id,
            request_type,
            topic,
            message,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, 'PENDING', ?, ?);
        """,
        (
            user_id,
            request_type,
            title,
            description,
            now,
            now,
        ),
    )

    return (
        int(cursor.lastrowid)
        if cursor and cursor.lastrowid is not None
        else None
    )


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


async def list_my_requests(
    user_id: int,
) -> list[dict[str, Any]]:
    return await get_user_requests(user_id)


async def get_pending_requests(
    limit: int = 50,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT *
        FROM requests
        WHERE status = 'PENDING'
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
        SET status = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            status,
            now_iso(),
            request_id,
        ),
    )

    return True


# ============================================================================
# NOTIFICATIONS
# ============================================================================


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


# ============================================================================
# REFERRALS
# ============================================================================


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


async def get_referral_count(
    seller_id: int,
) -> int:
    row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM referrals
        WHERE seller_id = ?;
        """,
        (seller_id,),
    )

    return int(row["c"]) if row else 0


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


# ============================================================================
# ORDERS
# ============================================================================


ORDER_STATUSES = (
    "PENDING",
    "CONFIRMED",
    "COMPLETED",
    "CANCELLED",
)


async def create_order(
    buyer_user_id: int,
    seller_id: int,
    product_id: int,
    quantity: int = 1,
    unit_price: Optional[int] = None,
) -> Optional[int]:
    if quantity < 1:
        return None

    if unit_price is None:
        product = await db.fetchone(
            """
            SELECT price
            FROM products
            WHERE id = ?
            LIMIT 1;
            """,
            (product_id,),
        )

        if not product or product["price"] is None:
            return None

        unit_price = int(product["price"])

    total_price = int(unit_price) * int(quantity)
    now = now_iso()

    cursor = await db.execute(
        """
        INSERT INTO orders (
            buyer_user_id,
            seller_id,
            product_id,
            quantity,
            total_price,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?);
        """,
        (
            buyer_user_id,
            seller_id,
            product_id,
            quantity,
            total_price,
            now,
            now,
        ),
    )

    return (
        int(cursor.lastrowid)
        if cursor and cursor.lastrowid is not None
        else None
    )


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


async def list_orders_for_buyer(
    buyer_user_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT
            o.*,
            p.name AS product_name,
            s.name AS seller_name
        FROM orders o
        LEFT JOIN products p
            ON p.id = o.product_id
        LEFT JOIN sellers s
            ON s.id = o.seller_id
        WHERE o.buyer_user_id = ?
        ORDER BY o.created_at DESC;
        """,
        (buyer_user_id,),
    )


async def list_orders_for_seller(
    seller_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT
            o.*,
            p.name AS product_name,
            u.telegram_id AS buyer_telegram_id
        FROM orders o
        LEFT JOIN products p
            ON p.id = o.product_id
        LEFT JOIN users u
            ON u.id = o.buyer_user_id
        WHERE o.seller_id = ?
        ORDER BY o.created_at DESC;
        """,
        (seller_id,),
    )


async def get_user_orders(
    user_id: int,
) -> list[dict[str, Any]]:
    return await list_orders_for_buyer(user_id)


async def get_seller_orders(
    seller_id: int,
) -> list[dict[str, Any]]:
    return await list_orders_for_seller(seller_id)


async def update_order_status(
    order_id: int,
    status: str,
) -> bool:
    if status not in ORDER_STATUSES:
        return False

    await db.execute(
        """
        UPDATE orders
        SET status = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            status,
            now_iso(),
            order_id,
        ),
    )

    return True


# ============================================================================
# AUDIT LOG
# ============================================================================


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


# ============================================================================
# ADMIN
# ============================================================================


async def get_admin_chat_id() -> Optional[int]:
    return ADMIN_CHAT_ID


# ============================================================================
# COMPARE
# ============================================================================


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
        if product_id < 1:
            continue

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
        WHERE id = ?
        LIMIT 1;
        """,
        (user_id,),
    )

    return bool(
        row
        and row["has_seen_compare_intro"]
    )


async def mark_compare_intro_seen(
    user_id: int,
) -> None:
    await db.execute(
        """
        UPDATE users
        SET has_seen_compare_intro = 1,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            now_iso(),
            user_id,
        ),
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

    normalized_ids: list[int] = []

    for product_id in product_ids:
        if product_id < 1:
            continue

        if product_id in normalized_ids:
            continue

        normalized_ids.append(product_id)

        if len(normalized_ids) >= COMPARE_MAX_ITEMS:
            break

    if not normalized_ids:
        return []

    placeholders = ",".join(
        "?" for _ in normalized_ids
    )

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
        tuple(normalized_ids),
    )


# ============================================================================
# GENERIC HELPERS
# ============================================================================


async def execute(
    query: str,
    params: tuple[Any, ...] = (),
):
    return await db.execute(
        query,
        params,
    )


async def fetchone(
    query: str,
    params: tuple[Any, ...] = (),
):
    return await db.fetchone(
        query,
        params,
    )


async def fetchall(
    query: str,
    params: tuple[Any, ...] = (),
):
    return await db.fetchall(
        query,
        params,
    )