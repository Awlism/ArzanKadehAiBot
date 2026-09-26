# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Background tasks and maintenance helpers
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from ..database import db
from ..utils import now_iso
from .backups import create_database_backup
from .notifications import notify_user


logger = logging.getLogger("arzankadeh")


# ======================================================================
# BACKUP CONFIG
# ======================================================================

BACKUP_DIR = os.getenv(
    "BACKUP_DIR",
    "backups",
)

BACKUP_KEEP_COUNT = int(
    os.getenv(
        "BACKUP_KEEP_COUNT",
        "7",
    )
    or "7"
)

BACKUP_INTERVAL_HOURS = float(
    os.getenv(
        "BACKUP_INTERVAL_HOURS",
        "24",
    )
    or "24"
)


def backup_filename(
    when: Optional[datetime] = None,
) -> str:
    """
    Generate a deterministic daily backup filename.

    Kept for compatibility with the original bot backup helpers.
    """

    when = when or datetime.now(timezone.utc)

    return (
        f"backup_{when.strftime('%Y-%m-%d')}.db"
    )


def prune_old_backups(
    backup_dir: str = BACKUP_DIR,
    keep: int = BACKUP_KEEP_COUNT,
) -> list:
    """
    Delete old backup_*.db files beyond the configured retention count.

    Returns the filenames that were deleted.
    Never raises.
    """

    deleted = []

    try:
        if (
            not os.path.isdir(backup_dir)
            or keep <= 0
        ):
            return deleted

        files = sorted(
            filename
            for filename in os.listdir(
                backup_dir
            )
            if (
                filename.startswith("backup_")
                and filename.endswith(".db")
            )
        )

        old_files = (
            files[:-keep]
            if len(files) > keep
            else []
        )

        for filename in old_files:
            path = os.path.join(
                backup_dir,
                filename,
            )

            os.remove(path)
            deleted.append(filename)

    except Exception as exc:
        logger.error(
            "Failed to prune old backups: %s",
            exc,
        )

    return deleted


async def backup_database() -> Optional[str]:
    """
    Create a safe database backup.

    Uses the existing backup service rather than copying the active
    SQLite database file directly.
    """

    try:
        path = await create_database_backup(
            destination_dir=BACKUP_DIR,
            prefix="backup",
        )

        if path:
            logger.info(
                "Database backup created: %s",
                path,
            )

            prune_old_backups()

        return path

    except Exception as exc:
        logger.error(
            "Database backup failed: %s",
            exc,
        )

        return None


async def periodic_backup_task() -> None:
    """
    Background task:
    create one backup immediately, then repeat periodically.
    """

    await backup_database()

    while True:
        await asyncio.sleep(
            BACKUP_INTERVAL_HOURS * 3600
        )

        await backup_database()


# ======================================================================
# AD EXPIRY
# ======================================================================

AD_EXPIRY_CHECK_INTERVAL_MINUTES = float(
    os.getenv(
        "AD_EXPIRY_CHECK_INTERVAL_MINUTES",
        "60",
    )
    or "60"
)


async def expire_overdue_ads() -> int:
    """
    Expire active advertisement requests whose display period ended.

    Returns the number of expired requests.
    Never raises.
    """

    try:
        now = now_iso()

        rows = await db.fetchall(
            """
            SELECT
                id,
                user_id,
                request_type
            FROM requests
            WHERE status = 'ACTIVE'
              AND ad_expires_at IS NOT NULL
              AND ad_expires_at <= ?;
            """,
            (now,),
        )

        for row in rows:
            updated_at = now_iso()

            await db.execute(
                """
                UPDATE requests
                SET status = 'EXPIRED',
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    updated_at,
                    row["id"],
                ),
            )

            if row["request_type"] == "general_ad":
                title = "تبلیغ در ارزانکده"
            else:
                title = "درخواست تبلیغات"

            await notify_user(
                row["user_id"],
                title,
                (
                    "⏰ مدت نمایش تبلیغت تموم شد. "
                    "اگه دوست داری دوباره فعالش کنیم، "
                    "از «📣 بیشتر دیده بشم» یا "
                    "«📢 تبلیغ در ارزانکده» یه درخواست جدید بده."
                ),
            )

        return len(rows)

    except Exception as exc:
        logger.error(
            "Failed to expire overdue ads: %s",
            exc,
        )

        return 0


async def periodic_ad_expiry_task() -> None:
    """
    Background task:
    periodically checks for expired advertisements.
    """

    while True:
        await expire_overdue_ads()

        await asyncio.sleep(
            AD_EXPIRY_CHECK_INTERVAL_MINUTES * 60
        )