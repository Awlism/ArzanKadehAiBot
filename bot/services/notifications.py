# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Notification service
"""

import logging
from typing import Optional

from ..database import db
from ..utils import now_iso

logger = logging.getLogger("arzankadeh")


async def notify_user(
    user_id: int,
    title: str,
    message: Optional[str],
    notification_type: str = "info",
) -> bool:
    """
    Store an in-app notification for a user.

    The original bot records notifications in the database here.
    Actual Telegram delivery is handled separately by the caller.
    """
    try:
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
                now_iso(),
            ),
        )
        return True

    except Exception as exc:
        logger.error(
            "Failed to create notification for user %s: %s",
            user_id,
            exc,
        )
        return False


async def get_unread_notifications(
    user_id: int,
) -> list:
    try:
        return await db.fetchall(
            """
            SELECT id, title, message, notification_type, created_at
            FROM notifications
            WHERE user_id = ?
              AND is_read = 0
            ORDER BY id DESC;
            """,
            (user_id,),
        )
    except Exception as exc:
        logger.error(
            "Failed to load notifications for user %s: %s",
            user_id,
            exc,
        )
        return []


async def mark_notification_read(
    notification_id: int,
    user_id: int,
) -> bool:
    try:
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

    except Exception as exc:
        logger.error(
            "Failed to mark notification %s as read: %s",
            notification_id,
            exc,
        )
        return False


async def mark_all_notifications_read(
    user_id: int,
) -> bool:
    try:
        await db.execute(
            """
            UPDATE notifications
            SET is_read = 1
            WHERE user_id = ?
              AND is_read = 0;
            """,
            (user_id,),
        )
        return True

    except Exception as exc:
        logger.error(
            "Failed to mark all notifications as read for user %s",
            user_id,
            exc,
        )
        return False