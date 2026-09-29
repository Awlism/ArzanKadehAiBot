# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Local SQLite database backup service

This module is intentionally local-only.

Cloudflare Worker deployments use Cloudflare D1 and must not rely on
SQLite filesystem backups. A future Cloudflare backup implementation
can use R2 or another Cloudflare storage service separately.
"""

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import DATABASE_PATH


logger = logging.getLogger("arzankadeh")


def _backup_filename(
    prefix: str = "arzan_kadeh_backup",
) -> str:
    """
    Generate a timestamped SQLite backup filename.
    """

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%d_%H%M%S"
    )

    return f"{prefix}_{timestamp}.db"


async def create_database_backup(
    destination_dir: str = "backups",
    prefix: str = "arzan_kadeh_backup",
) -> Optional[str]:
    """
    Create a consistent SQLite database backup.

    This function is for local SQLite deployments only.

    It does not access Cloudflare D1 and must not be used as part
    of the Cloudflare Worker request or scheduled-maintenance path.

    Returns:
        The created backup path, or None if the backup failed.
    """

    source_path = Path(
        DATABASE_PATH
    )

    if not source_path.exists():
        logger.warning(
            "Database file does not exist: %s",
            source_path,
        )
        return None

    backup_dir = Path(
        destination_dir
    )

    try:
        backup_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
    except Exception as exc:
        logger.error(
            "Failed to create backup directory %s: %s",
            backup_dir,
            exc,
        )
        return None

    destination_path = (
        backup_dir
        / _backup_filename(prefix)
    )

    def _backup() -> str:
        source = None
        destination = None

        try:
            source = sqlite3.connect(
                str(source_path)
            )

            destination = sqlite3.connect(
                str(destination_path)
            )

            with destination:
                source.backup(
                    destination
                )

            return str(
                destination_path
            )

        finally:
            if destination is not None:
                destination.close()

            if source is not None:
                source.close()

    try:
        result = await asyncio.to_thread(
            _backup
        )

        logger.info(
            "Database backup created: %s",
            result,
        )

        return result

    except Exception as exc:
        logger.error(
            "Failed to create database backup: %s",
            exc,
        )

        try:
            if destination_path.exists():
                destination_path.unlink()
        except OSError:
            pass

        return None