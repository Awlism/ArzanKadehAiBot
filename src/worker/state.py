# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker persistent state layer.

Stores:
- temporary multi-step user state
- Telegram webhook update processing state

This module does not import aiogram, sqlite, or aiosqlite.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


STATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS worker_states (
    user_id INTEGER PRIMARY KEY,
    state TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);
"""

PROCESSED_UPDATES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS processed_updates (
    update_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL
        CHECK (status IN ('processing', 'processed')),
    claimed_at INTEGER NOT NULL,
    processed_at INTEGER
);
"""

UPDATE_CLAIM_LEASE_SECONDS = 300


def _now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def _serialize_data(
    data: dict[str, Any] | None,
) -> str:
    if data is None:
        data = {}

    if not isinstance(data, dict):
        raise TypeError(
            "Worker state data must be a dictionary."
        )

    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _deserialize_data(
    value: Any,
) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    try:
        data = json.loads(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Stored Worker state data is not valid JSON."
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "Stored Worker state data must be a JSON object."
        )

    return data


async def ensure_state_table(
    db: Any,
) -> None:
    """Ensure the persistent user-state table exists."""
    await db.execute(STATE_TABLE_SQL)


async def ensure_processed_updates_table(
    db: Any,
) -> None:
    """Ensure the webhook deduplication table exists."""
    await db.execute(PROCESSED_UPDATES_TABLE_SQL)


async def get_state(
    db: Any,
    user_id: int,
) -> dict[str, Any] | None:
    """Return a user's current state, or None if absent."""
    row = await db.fetchone(
        """
        SELECT state, data, updated_at
        FROM worker_states
        WHERE user_id = ?
        LIMIT 1;
        """,
        (user_id,),
    )

    if row is None:
        return None

    return {
        "state": str(row["state"]),
        "data": _deserialize_data(row["data"]),
        "updated_at": str(row["updated_at"]),
    }


async def set_state(
    db: Any,
    user_id: int,
    state: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Create or replace a user's active Worker state."""
    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id < 1
    ):
        raise ValueError(
            "A valid internal user id is required."
        )

    if not isinstance(state, str) or not state.strip():
        raise ValueError(
            "A non-empty Worker state is required."
        )

    serialized_data = _serialize_data(data)

    await db.execute(
        """
        INSERT INTO worker_states (
            user_id,
            state,
            data,
            updated_at
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET
            state = excluded.state,
            data = excluded.data,
            updated_at = excluded.updated_at;
        """,
        (
            user_id,
            state.strip(),
            serialized_data,
            _now_iso(),
        ),
    )


async def clear_state(
    db: Any,
    user_id: int,
) -> None:
    """Remove a user's current Worker state."""
    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id < 1
    ):
        raise ValueError(
            "A valid internal user id is required."
        )

    await db.execute(
        """
        DELETE FROM worker_states
        WHERE user_id = ?;
        """,
        (user_id,),
    )


async def claim_update(
    db: Any,
    update_id: int,
    lease_seconds: int = UPDATE_CLAIM_LEASE_SECONDS,
) -> bool:
    """
    Atomically claim a Telegram update for processing.

    Returns True if this request acquired the claim.
    Returns False if the update is already processing or processed.

    A stale processing claim may be reclaimed after its lease expires.
    """
    if (
        isinstance(update_id, bool)
        or not isinstance(update_id, int)
        or update_id < 0
    ):
        raise ValueError(
            "A valid Telegram update_id is required."
        )

    if (
        isinstance(lease_seconds, bool)
        or not isinstance(lease_seconds, int)
        or lease_seconds < 1
    ):
        raise ValueError(
            "The update claim lease must be a positive integer."
        )

    result = await db.execute(
        """
        INSERT INTO processed_updates (
            update_id,
            status,
            claimed_at,
            processed_at
        )
        VALUES (
            ?,
            'processing',
            unixepoch(),
            NULL
        )
        ON CONFLICT(update_id)
        DO UPDATE SET
            status = 'processing',
            claimed_at = unixepoch(),
            processed_at = NULL
        WHERE
            processed_updates.status = 'processing'
            AND processed_updates.claimed_at
                < unixepoch() - ?;
        """,
        (
            update_id,
            lease_seconds,
        ),
    )

    return result.rowcount > 0


async def mark_update_processed(
    db: Any,
    update_id: int,
) -> None:
    """Mark a successfully dispatched Telegram update as processed."""
    await db.execute(
        """
        UPDATE processed_updates
        SET
            status = 'processed',
            processed_at = unixepoch()
        WHERE
            update_id = ?
            AND status = 'processing';
        """,
        (update_id,),
    )


async def release_update_claim(
    db: Any,
    update_id: int,
) -> None:
    """
    Release an unfinished claim so Telegram can retry the update.

    Processed updates are never deleted by this function.
    """
    await db.execute(
        """
        DELETE FROM processed_updates
        WHERE
            update_id = ?
            AND status = 'processing';
        """,
        (update_id,),
    )


__all__ = [
    "STATE_TABLE_SQL",
    "PROCESSED_UPDATES_TABLE_SQL",
    "UPDATE_CLAIM_LEASE_SECONDS",
    "ensure_state_table",
    "ensure_processed_updates_table",
    "get_state",
    "set_state",
    "clear_state",
    "claim_update",
    "mark_update_processed",
    "release_update_claim",
]