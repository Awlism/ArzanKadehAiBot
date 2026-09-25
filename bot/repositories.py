# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Data Access / Repository layer
"""

from typing import Optional

from .config import ADMIN_CHAT_ID
from .database import db
from .utils import now_iso


# ======================================================================
# PRODUCTS / SELLERS
# ======================================================================

async def get_product_by_id(product_id: int) -> Optional[dict]:
    return await db.fetchone(
        "SELECT * FROM products WHERE id = ?;",
        (product_id,),
    )


async def get_seller_by_id(seller_id: int) -> Optional[dict]:
    return await db.fetchone(
        "SELECT * FROM sellers WHERE id = ?;",
        (seller_id,),
    )


async def create_product_record(
    seller_id: int,
    name: str,
    **fields,
) -> int:
    now = now_iso()

    cur = await db.execute(
        """
        INSERT INTO products (
            seller_id,
            name,
            description,
            price,
            old_price,
            image_url,
            category_id,
            stock_status,
            rating,
            review_count,
            views,
            created_at,
            updated_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            'AVAILABLE',
            0, 0, 0, ?, ?
        );
        """,
        (
            seller_id,
            name,
            fields.get("description"),
            fields.get("price"),
            fields.get("old_price"),
            fields.get("image_url"),
            fields.get("category_id"),
            now,
            now,
        ),
    )

    return cur.lastrowid


async def delete_product_record(product_id: int) -> None:
    await db.execute(
        "DELETE FROM products WHERE id = ?;",
        (product_id,),
    )


# ======================================================================
# ORDERS
# ======================================================================

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
    total_price: Optional[int] = None,
) -> int:
    now = now_iso()

    cur = await db.execute(
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

    return cur.lastrowid


async def get_order(order_id: int) -> Optional[dict]:
    return await db.fetchone(
        "SELECT * FROM orders WHERE id = ?;",
        (order_id,),
    )


async def update_order_status(
    order_id: int,
    status: str,
) -> bool:
    if status not in ORDER_STATUSES:
        raise ValueError(f"Invalid order status: {status}")

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


async def list_orders_for_buyer(
    buyer_user_id: int,
    limit: int = 20,
) -> list:
    return await db.fetchall(
        """
        SELECT *
        FROM orders
        WHERE buyer_user_id = ?
        ORDER BY created_at DESC
        LIMIT ?;
        """,
        (
            buyer_user_id,
            limit,
        ),
    )


async def list_orders_for_seller(
    seller_id: int,
    limit: int = 20,
) -> list:
    return await db.fetchall(
        """
        SELECT *
        FROM orders
        WHERE seller_id = ?
        ORDER BY created_at DESC
        LIMIT ?;
        """,
        (
            seller_id,
            limit,
        ),
    )


# ======================================================================
# STATISTICS
# ======================================================================

async def get_seller_statistics(seller_id: int) -> dict:
    seller = await get_seller_by_id(seller_id)

    products = await db.fetchall(
        "SELECT * FROM products WHERE seller_id = ?;",
        (seller_id,),
    )

    fav_count = await count_seller_favorites(seller_id)

    request_row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM requests
        WHERE seller_id = ?;
        """,
        (seller_id,),
    )

    completed_orders = await db.fetchone(
        """
        SELECT
            COUNT(*) AS c,
            COALESCE(SUM(total_price), 0) AS revenue
        FROM orders
        WHERE seller_id = ?
          AND status = 'COMPLETED';
        """,
        (seller_id,),
    )

    return {
        "views": seller["views"] if seller else 0,
        "product_count": len(products),
        "active_product_count": sum(
            1
            for product in products
            if product["stock_status"] == "AVAILABLE"
        ),
        "total_product_views": sum(
            product["views"]
            for product in products
        ),
        "favorite_count": fav_count,
        "request_count": request_row["c"] if request_row else 0,
        "completed_order_count": (
            completed_orders["c"]
            if completed_orders
            else 0
        ),
        "completed_order_revenue": (
            completed_orders["revenue"]
            if completed_orders
            else 0
        ),
    }


async def get_product_statistics(product_id: int) -> dict:
    product = await get_product_by_id(product_id)

    fav_row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM favorites
        WHERE product_id = ?;
        """,
        (product_id,),
    )

    completed_orders = await db.fetchone(
        """
        SELECT
            COUNT(*) AS c,
            COALESCE(SUM(quantity), 0) AS units
        FROM orders
        WHERE product_id = ?
          AND status = 'COMPLETED';
        """,
        (product_id,),
    )

    return {
        "views": product["views"] if product else 0,
        "favorite_count": fav_row["c"] if fav_row else 0,
        "completed_order_count": (
            completed_orders["c"]
            if completed_orders
            else 0
        ),
        "completed_units_sold": (
            completed_orders["units"]
            if completed_orders
            else 0
        ),
    }


# ======================================================================
# ROLES
# ======================================================================

VALID_MODES = (
    "buyer",
    "seller",
    "admin",
)


async def user_has_any_seller(user_id: int) -> bool:
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


async def is_admin_user_id(user_id: int) -> bool:
    if not ADMIN_CHAT_ID:
        return False

    row = await db.fetchone(
        """
        SELECT telegram_id
        FROM users
        WHERE id = ?;
        """,
        (user_id,),
    )

    return bool(
        row
        and row["telegram_id"] == ADMIN_CHAT_ID
    )


async def get_active_mode(user_id: int) -> str:
    row = await db.fetchone(
        """
        SELECT active_mode
        FROM users
        WHERE id = ?;
        """,
        (user_id,),
    )

    stored_mode = (
        row["active_mode"]
        if row and row["active_mode"] in VALID_MODES
        else "buyer"
    )

    if (
        stored_mode == "admin"
        and not await is_admin_user_id(user_id)
    ):
        return "buyer"

    return stored_mode


async def set_active_mode(
    user_id: int,
    mode: str,
) -> None:
    if mode not in VALID_MODES:
        raise ValueError(
            f"Invalid mode: {mode}"
        )

    if (
        mode == "admin"
        and not await is_admin_user_id(user_id)
    ):
        raise PermissionError(
            "Only the configured admin (ADMIN_CHAT_ID) "
            "may enter admin mode."
        )

    await db.execute(
        """
        UPDATE users
        SET active_mode = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (
            mode,
            now_iso(),
            user_id,
        ),
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
          AND seller_id = ?;
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
    if await is_seller_favorite(
        user_id,
        seller_id,
    ):
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

    try:
        await db.execute(
            """
            INSERT INTO seller_favorites (
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
    except Exception:
        pass

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

    return row["c"] if row else 0


# ======================================================================
# COMPARE
# ======================================================================

COMPARE_MAX_ITEMS = 2

COMPARE_INTRO_TEXT = (
    "⚖️ مقایسه چیه؟\n"
    "دو محصول رو کنار هم بذار تا راحت‌تر انتخاب کنی. ✨"
)


def compare_add(
    selection: list,
    product_id: int,
) -> tuple:
    selection = list(selection)

    if product_id in selection:
        return selection, "already_in_selection"

    if len(selection) >= COMPARE_MAX_ITEMS:
        return selection, "already_full"

    selection.append(product_id)

    if len(selection) == COMPARE_MAX_ITEMS:
        return selection, "added_ready"

    return selection, "added_need_one_more"


_compare_sessions: dict = {}


def get_compare_selection(
    user_id: int,
) -> list:
    return list(
        _compare_sessions.get(
            user_id,
            [],
        )
    )


def set_compare_selection(
    user_id: int,
    selection: list,
) -> None:
    _compare_sessions[user_id] = list(
        selection
    )


def clear_compare_selection(
    user_id: int,
) -> None:
    _compare_sessions.pop(
        user_id,
        None,
    )


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


# ======================================================================
# REQUESTS / RATE LIMITING
# ======================================================================

REQUEST_STATUS_LABELS = {
    "PENDING": "🟡 در حال بررسی",
    "REJECTED": "🔴 رد شد",
    "APPROVED": "🟢 تأیید شد",
    "COORDINATING": "🔵 در حال هماهنگی",
    "ACTIVE": "🟢 فعال",
    "EXPIRED": "⏰ تمام‌شده",
}


async def has_open_request(
    user_id: int,
    request_type: str,
    topic: Optional[str] = None,
) -> bool:
    if topic:
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
    else:
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

    return row is not None


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
    else:
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

    return row is not None


async def create_request(
    user_id: int,
    request_type: str,
    topic: Optional[str] = None,
    message: Optional[str] = None,
    seller_id: Optional[int] = None,
) -> int:
    now = now_iso()

    cur = await db.execute(
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
        VALUES (
            ?, ?, ?, ?, ?, 'PENDING', ?, ?
        );
        """,
        (
            user_id,
            request_type,
            topic,
            message,
            seller_id,
            now,
            now,
        ),
    )

    return cur.lastrowid


async def list_my_requests(
    user_id: int,
    limit: int = 20,
) -> list:
    requests_rows = await db.fetchall(
        """
        SELECT *
        FROM requests
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?;
        """,
        (
            user_id,
            limit,
        ),
    )

    report_rows = await db.fetchall(
        """
        SELECT *
        FROM reports
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?;
        """,
        (
            user_id,
            limit,
        ),
    )

    items = []

    for row in requests_rows:
        label = {
            "support": "🛟 پشتیبانی",
            "ad": "📢 درخواست تبلیغات",
        }.get(
            row["request_type"],
            row["request_type"],
        )

        status = (
            row["status"]
            if row["status"] in REQUEST_STATUS_LABELS
            else "PENDING"
        )

        items.append(
            {
                "kind": "request",
                "id": row["id"],
                "title": row["topic"] or label,
                "created_at": row["created_at"],
                "status_label": REQUEST_STATUS_LABELS[status],
            }
        )

    for row in report_rows:
        status = (
            row["status"]
            if row["status"] in REQUEST_STATUS_LABELS
            else "PENDING"
        )

        target = (
            "فروشگاه"
            if row["seller_id"]
            else "محصول"
        )

        items.append(
            {
                "kind": "report",
                "id": row["id"],
                "title": f"🚨 گزارش {target}",
                "created_at": row["created_at"],
                "status_label": REQUEST_STATUS_LABELS[status],
            }
        )

    items.sort(
        key=lambda item: item["created_at"],
        reverse=True,
    )

    return items[:limit]