# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Background task helpers

Cloudflare-compatible design:
- Database access goes through the shared backend abstraction.
- Maintenance operations are one-shot and can be triggered by
  a scheduler / Cron Worker.
- No infinite background loops are required by the Worker runtime.
- SQLite filesystem backups are kept out of the Cloudflare task path.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from ..backend import backend
from ..utils import now_iso
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

    Kept for compatibility with older local tooling.

    Cloudflare Worker deployments must not rely on local filesystem
    SQLite backups.
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
    Delete old local backup_*.db files beyond the configured
    retention count.

    This helper is intentionally local-filesystem-only and is not
    used by the Cloudflare Worker maintenance path.

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

    This is intentionally a one-shot operation.

    A scheduler such as Cloudflare Cron can invoke this function
    periodically instead of keeping an asyncio loop alive.

    Only requests that are still ACTIVE at the moment of the UPDATE
    are transitioned to EXPIRED.

    Returns the number of successfully expired requests.
    Never raises.
    """

    try:
        now = now_iso()

        rows = await backend.fetchall(
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

        expired_count = 0

        for row in rows:
            result = await backend.execute(
                """
                UPDATE requests
                SET status = 'EXPIRED',
                    updated_at = ?
                WHERE id = ?
                  AND status = 'ACTIVE'
                  AND ad_expires_at IS NOT NULL
                  AND ad_expires_at <= ?;
                """,
                (
                    now,
                    row["id"],
                    now,
                ),
            )

            if result.rowcount != 1:
                continue

            expired_count += 1

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

        return expired_count

    except Exception as exc:
        logger.error(
            "Failed to expire overdue ads: %s",
            exc,
        )

        return 0


async def run_scheduled_maintenance() -> int:
    """
    Run one scheduled maintenance cycle.

    This function is the Cloudflare-compatible replacement for the
    old infinite periodic_ad_expiry_task() loop.

    A future Worker Cron handler can call this function once per
    scheduled invocation.

    Returns the number of advertisements expired during this run.
    """

    return await expire_overdue_ads()


# ======================================================================
# LEGACY LOCAL COMPATIBILITY
# ======================================================================

async def periodic_ad_expiry_task() -> int:
    """
    Compatibility wrapper for older callers.

    The old implementation created an infinite asyncio loop.
    That model is not appropriate for Cloudflare Workers.

    The function now performs exactly one maintenance cycle and
    returns its result.
    """

    return await expire_overdue_ads()


async def backup_database() -> Optional[str]:
    """
    Cloudflare-safe backup placeholder.

    SQLite filesystem backups are intentionally not performed here
    because Cloudflare Workers do not provide the persistent local
    filesystem expected by the old SQLite backup implementation.

    A future backup implementation can target a Cloudflare storage
    service such as R2 without changing the maintenance flow.
    """

    logger.info(
        "SQLite filesystem backup skipped; "
        "Cloudflare storage backup is not configured."
    )

    return None


async def periodic_backup_task() -> Optional[str]:
    """
    Compatibility wrapper for older callers.

    Performs one backup attempt only.

    No infinite asyncio loop is created because persistent background
    loops are not appropriate for Cloudflare Workers.
    """

    return await backup_database()