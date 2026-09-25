# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Database backup service
"""

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import DATABASE_PATH

logger = logging.getLogger("arzankadeh")


def _backup_filename(prefix: str = "arzan_kadeh_backup") -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.db"


async def create_database_backup(
    destination_dir: str = "backups",
    prefix: str = "arzan_kadeh_backup",
) -> Optional[str]:
    """
    Create a consistent SQLite backup without changing the active database.
    """

    source_path = Path(DATABASE_PATH)

    if not source_path.exists():
        logger.warning(
            "Database file does not exist: %s",
            source_path,
        )
        return None

    backup_dir = Path(destination_dir)
    backup_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination_path = backup_dir / _backup_filename(prefix)

    def _backup() -> str:
        source = sqlite3.connect(str(source_path))
        destination = sqlite3.connect(str(destination_path))

        try:
            with destination:
                source.backup(destination)

            return str(destination_path)

        finally:
            destination.close()
            source.close()

    try:
        result = await asyncio.to_thread(_backup)

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