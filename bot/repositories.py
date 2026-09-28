# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Repository / data-access layer
"""

from __future__ import annotations

import aiosqlite

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

    cursor = await db.execute(
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

    return cursor.rowcount == 1


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

    if mode == "admin" and not await is_admin_user_id(user_id):
        raise PermissionError(
            "Admin mode is restricted to the configured admin user."
        )

    cursor = await db.execute(
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

    return cursor.rowcount == 1


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
    if seller_id < 1:
        raise ValueError("Invalid seller_id.")

    name = (name or "").strip()
    if not name:
        raise ValueError("Product name is required.")

    seller = await db.fetchone(
        """
        SELECT id
        FROM sellers
        WHERE id = ?
        LIMIT 1;
        """,
        (seller_id,),
    )

    if seller is None:
        raise ValueError("Seller does not exist.")

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

    category_id = clean_fields.get("category_id")

    if category_id is not None:
        if not isinstance(category_id, int) or category_id < 1:
            raise ValueError("Invalid category_id.")

        category = await db.fetchone(
            """
            SELECT id
            FROM categories
            WHERE id = ?
            LIMIT 1;
            """,
            (category_id,),
        )

        if category is None:
            raise ValueError("Category does not exist.")

    price = clean_fields.get("price")
    old_price = clean_fields.get("old_price")

    if price is not None:
        try:
            price = float(price)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid price.") from exc

        if price < 0:
            raise ValueError("Price cannot be negative.")

        clean_fields["price"] = price

    if old_price is not None:
        try:
            old_price = float(old_price)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid old_price.") from exc

        if old_price < 0:
            raise ValueError("Old price cannot be negative.")

        clean_fields["old_price"] = old_price

    if (
        price is not None
        and old_price is not None
        and old_price < price
    ):
        raise ValueError(
            "Old price cannot be lower than the current price."
        )

    columns = [
        "seller_id",
        "name",
        "created_at",
        "updated_at",
    ]

    now = now_iso()

    values: list[Any] = [
        seller_id,
        name,
        now,
        now,
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
    if product_id < 1:
        return False

    cursor = await db.execute(
        """
        DELETE FROM products
        WHERE id = ?;
        """,
        (product_id,),
    )

    return cursor.rowcount == 1


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
# SELLER CLAIMS
# ============================================================================


async def get_seller_claim(
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
            u.first_name AS claimant_first_name
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


async def get_pending_seller_claims(
    limit: int = 50,
) -> list[dict[str, Any]]:
    if limit < 1:
        return []

    return await db.fetchall(
        """
        SELECT
            sc.*,
            s.name AS seller_name,
            s.status AS seller_status,
            s.owner_user_id,
            s.created_by_user_id,
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
        (limit,),
    )


async def get_seller_claims_for_seller(
    seller_id: int,
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
        WHERE sc.seller_id = ?
        ORDER BY sc.created_at DESC, sc.id DESC;
        """,
        (seller_id,),
    )


async def get_user_seller_claims(
    user_id: int,
) -> list[dict[str, Any]]:
    return await db.fetchall(
        """
        SELECT
            sc.*,
            s.name AS seller_name,
            s.status AS seller_status
        FROM seller_claims sc
        JOIN sellers s
            ON s.id = sc.seller_id
        WHERE sc.user_id = ?
        ORDER BY sc.created_at DESC, sc.id DESC;
        """,
        (user_id,),
    )


async def create_seller_claim(
    seller_id: int,
    user_id: int,
) -> Optional[int]:
    """
    Create a seller-ownership claim.

    Lifecycle rules:

    - Seller must still be UNCLAIMED.
    - Seller owner/creator cannot claim their own seller.
    - Existing PENDING claim returns its existing id.
    - Existing REJECTED claim does not block a new claim.
    - Existing APPROVED claim blocks a new claim.
    - Database-level partial uniqueness prevents duplicate
      PENDING claims for the same seller/user pair.
    """

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

    if seller["status"] != "UNCLAIMED":
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
        status = str(
            existing["status"] or ""
        ).upper()

        if status == "PENDING":
            return int(existing["id"])

        if status == "APPROVED":
            return None

        if status != "REJECTED":
            return None

    now = now_iso()

    try:
        cursor = await db.execute(
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

    except aiosqlite.IntegrityError:
        # Another request may have created the PENDING claim
        # between our read and insert. Re-read the canonical row
        # instead of creating a duplicate audit/claim record.
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

    if cursor.lastrowid is None:
        return None

    return int(cursor.lastrowid)


async def approve_seller_claim(
    claim_id: int,
    admin_user_id: int,
) -> bool:
    if not await is_admin_user_id(admin_user_id):
        raise PermissionError(
            "Only the configured admin can approve seller claims."
        )

    if db.conn is None:
        raise RuntimeError(
            "Database is not connected."
        )

    now = now_iso()

    try:
        await db.conn.execute("BEGIN")

        claim_cursor = await db.conn.execute(
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
        claim_row = await claim_cursor.fetchone()
        await claim_cursor.close()

        if not claim_row:
            await db.conn.rollback()
            return False

        if claim_row["status"] != "PENDING":
            await db.conn.rollback()
            return False

        seller_cursor = await db.conn.execute(
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
            (claim_row["seller_id"],),
        )
        seller_row = await seller_cursor.fetchone()
        await seller_cursor.close()

        if not seller_row:
            await db.conn.rollback()
            return False

        if seller_row["status"] != "UNCLAIMED":
            await db.conn.rollback()
            return False

        if (
            seller_row["owner_user_id"] is not None
            and seller_row["owner_user_id"] != claim_row["user_id"]
        ):
            await db.conn.rollback()
            return False

        if (
            seller_row["created_by_user_id"] is not None
            and seller_row["created_by_user_id"] != claim_row["user_id"]
        ):
            await db.conn.rollback()
            return False

        claim_update = await db.conn.execute(
            """
            UPDATE seller_claims
            SET
                status = 'APPROVED',
                updated_at = ?
            WHERE id = ?
              AND status = 'PENDING';
            """,
            (
                now,
                claim_id,
            ),
        )

        if claim_update.rowcount != 1:
            await db.conn.rollback()
            return False

        seller_update = await db.conn.execute(
            """
            UPDATE sellers
            SET
                owner_user_id = ?,
                status = 'CLAIMED',
                updated_at = ?
            WHERE id = ?
              AND status = 'UNCLAIMED';
            """,
            (
                claim_row["user_id"],
                now,
                claim_row["seller_id"],
            ),
        )

        if seller_update.rowcount != 1:
            await db.conn.rollback()
            return False

        await db.conn.execute(
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
                claim_row["seller_id"],
                claim_id,
            ),
        )

        await db.conn.commit()
        return True

    except Exception:
        await db.conn.rollback()
        raise


async def reject_seller_claim(
    claim_id: int,
    admin_user_id: int,
) -> bool:
    if not await is_admin_user_id(admin_user_id):
        raise PermissionError(
            "Only the configured admin can reject seller claims."
        )

    now = now_iso()

    cursor = await db.execute(
        """
        UPDATE seller_claims
        SET
            status = 'REJECTED',
            updated_at = ?
        WHERE id = ?
          AND status = 'PENDING';
        """,
        (
            now,
            claim_id,
        ),
    )

    return cursor.rowcount == 1


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
    """
    Create one review for either a seller or a product.

    Canonical storage rules:
    - Seller review: seller_id is set, product_id is NULL.
    - Product review: product_id is set, seller_id is NULL.
    """

    if user_id < 1:
        return False

    if not 1 <= rating <= 5:
        return False

    if seller_id < 1:
        return False

    seller = await db.fetchone(
        """
        SELECT id
        FROM sellers
        WHERE id = ?
        LIMIT 1;
        """,
        (seller_id,),
    )

    if seller is None:
        return False

    review_seller_id: Optional[int]
    review_product_id: Optional[int]

    if product_id is None:
        review_seller_id = seller_id
        review_product_id = None

    else:
        if product_id < 1:
            return False

        product = await db.fetchone(
            """
            SELECT id
            FROM products
            WHERE id = ?
              AND seller_id = ?
            LIMIT 1;
            """,
            (
                product_id,
                seller_id,
            ),
        )

        if product is None:
            return False

        review_seller_id = None
        review_product_id = product_id

    existing = await db.fetchone(
        """
        SELECT id
        FROM reviews
        WHERE user_id = ?
          AND (
                (
                    seller_id = ?
                    AND product_id IS NULL
                )
                OR
                (
                    product_id = ?
                    AND seller_id IS NULL
                )
          )
        LIMIT 1;
        """,
        (
            user_id,
            review_seller_id,
            review_product_id,
        ),
    )

    if existing is not None:
        return False

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
            review_seller_id,
            review_product_id,
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
    if target_id < 1:
        return False

    if target_type not in {"seller", "product"}:
        return False

    if not reason or not reason.strip():
        return False

    seller_id: Optional[int] = None
    product_id: Optional[int] = None

    if target_type == "seller":
        seller = await db.fetchone(
            """
            SELECT id
            FROM sellers
            WHERE id = ?
            LIMIT 1;
            """,
            (target_id,),
        )

        if seller is None:
            return False

        seller_id = target_id

    else:
        product = await db.fetchone(
            """
            SELECT id
            FROM products
            WHERE id = ?
            LIMIT 1;
            """,
            (target_id,),
        )

        if product is None:
            return False

        product_id = target_id

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
            reason.strip(),
            now_iso(),
        ),
    )

    return True


async def has_open_report(
    user_id: int,
    seller_id: Optional[int],
    product_id: Optional[int],
) -> bool:
    if seller_id is not None:
        row = await db.fetchone(
            """
            SELECT 1
            FROM reports
            WHERE user_id = ?
              AND seller_id = ?
              AND status = 'PENDING'
            LIMIT 1;
            """,
            (
                user_id,
                seller_id,
            ),
        )
    elif product_id is not None:
        row = await db.fetchone(
            """
            SELECT 1
            FROM reports
            WHERE user_id = ?
              AND product_id = ?
              AND status = 'PENDING'
            LIMIT 1;
            """,
            (
                user_id,
                product_id,
            ),
        )
    else:
        return False

    return row is not None


async def get_pending_reports(
    limit: int = 50,
) -> list[dict[str, Any]]:
    if limit < 1:
        return []

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
    valid_statuses = {
        "PENDING",
        "APPROVED",
        "REJECTED",
    }

    if report_id < 1:
        return False

    if status not in valid_statuses:
        return False

    cursor = await db.execute(
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

    return cursor.rowcount == 1


# ============================================================================
# REQUESTS
# ============================================================================


REQUEST_STATUS_LABELS = {
    "PENDING": "در انتظار بررسی",
    "APPROVED": "تأیید شده",
    "REJECTED": "رد شده",
    "ACTIVE": "فعال",
    "EXPIRED": "منقضی شده",
    "COMPLETED": "تکمیل شده",
    "CANCELLED": "لغو شده",
}


async def has_open_request(
    user_id: int,
    request_type: str,
    topic: Optional[str] = None,
) -> bool:
    if topic is None:
        row = await db.fetchone(
            """
            SELECT 1
            FROM requests
            WHERE user_id = ?
              AND request_type = ?
              AND status = 'PENDING'
            LIMIT 1;
            """,
            (
                user_id,
                request_type,
            ),
        )
    else:
        row = await db.fetchone(
            """
            SELECT 1
            FROM requests
            WHERE user_id = ?
              AND request_type = ?
              AND topic = ?
              AND status = 'PENDING'
            LIMIT 1;
            """,
            (
                user_id,
                request_type,
                topic,
            ),
        )

    return row is not None


async def create_request(
    user_id: int,
    request_type: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    *,
    topic: Optional[str] = None,
    message: Optional[str] = None,
    seller_id: Optional[int] = None,
) -> Optional[int]:
    if user_id < 1:
        return None

    if request_type not in {"support", "ad", "general_ad"}:
        return None

    # Support both the newer explicit topic/message names and
    # the original title/description interface.
    request_topic = (
        topic.strip()
        if topic is not None
        else (title or "").strip()
    )

    if not request_topic:
        return None

    request_message = (
        message.strip()
        if message is not None
        else (
            description.strip()
            if description is not None
            else None
        )
    )

    if seller_id is not None:
        if seller_id < 1:
            return None

        seller = await db.fetchone(
            """
            SELECT id
            FROM sellers
            WHERE id = ?
            LIMIT 1;
            """,
            (seller_id,),
        )

        if seller is None:
            return None

    user = await db.fetchone(
        """
        SELECT id
        FROM users
        WHERE id = ?
        LIMIT 1;
        """,
        (user_id,),
    )

    if user is None:
        return None

    now = now_iso()

    cursor = await db.execute(
        """
        INSERT INTO requests (
            user_id,
            request_type,
            topic,
            message,
            seller_id,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?);
        """,
        (
            user_id,
            request_type,
            request_topic,
            request_message,
            seller_id,
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
    if limit < 1:
        return []

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
    valid_statuses = {
        "PENDING",
        "APPROVED",
        "REJECTED",
        "ACTIVE",
        "EXPIRED",
        "COMPLETED",
        "CANCELLED",
    }

    if request_id < 1:
        return False

    if status not in valid_statuses:
        return False

    cursor = await db.execute(
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

    return cursor.rowcount == 1


# ============================================================================
# NOTIFICATIONS
# ============================================================================


async def get_user_notifications(
    user_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if limit < 1:
        return []

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
    cursor = await db.execute(
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

    return cursor.rowcount == 1


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

    # The product must exist and belong to the supplied seller.
    product = await db.fetchone(
        """
        SELECT
            id,
            seller_id,
            price
        FROM products
        WHERE id = ?
          AND seller_id = ?
        LIMIT 1;
        """,
        (
            product_id,
            seller_id,
        ),
    )

    if product is None:
        return None

    if unit_price is None:
        if product["price"] is None:
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

    cursor = await db.execute(
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

    return cursor.rowcount == 1


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
    if limit < 1:
        return []

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