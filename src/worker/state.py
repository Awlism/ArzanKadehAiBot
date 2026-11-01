
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
import uuid
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
    processed_at INTEGER,
    claim_token TEXT,
    lease_expires_at INTEGER
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


def _validate_update_id(update_id: int) -> None:
    if (
        isinstance(update_id, bool)
        or not isinstance(update_id, int)
        or update_id < 0
    ):
        raise ValueError(
            "A valid Telegram update_id is required."
        )


def _validate_claim_token(claim_token: str) -> None:
    if (
        not isinstance(claim_token, str)
        or not claim_token.strip()
    ):
        raise ValueError(
            "A valid update claim token is required."
        )


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
    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id < 1
    ):
        raise ValueError(
            "A valid internal user id is required."
        )

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
) -> str | None:
    """
    Atomically claim a Telegram update.

    Returns a unique ownership token when acquired.
    Returns None when another active or completed claim exists.
    """
    _validate_update_id(update_id)

    if (
        isinstance(lease_seconds, bool)
        or not isinstance(lease_seconds, int)
        or lease_seconds < 1
    ):
        raise ValueError(
            "The update claim lease must be a positive integer."
        )

    claim_token = uuid.uuid4().hex

    result = await db.execute(
        """
        INSERT INTO processed_updates (
            update_id,
            status,
            claimed_at,
            processed_at,
            claim_token,
            lease_expires_at
        )
        VALUES (
            ?,
            'processing',
            unixepoch(),
            NULL,
            ?,
            unixepoch() + ?
        )
        ON CONFLICT(update_id)
        DO UPDATE SET
            status = 'processing',
            claimed_at = unixepoch(),
            processed_at = NULL,
            claim_token = excluded.claim_token,
            lease_expires_at = excluded.lease_expires_at
        WHERE
            processed_updates.status = 'processing'
            AND (
                processed_updates.lease_expires_at IS NULL
                OR processed_updates.lease_expires_at <= unixepoch()
            );
        """,
        (
            update_id,
            claim_token,
            lease_seconds,
        ),
    )

    if result is None or result.rowcount <= 0:
        return None

    return claim_token


async def mark_update_processed(
    db: Any,
    update_id: int,
    claim_token: str,
) -> bool:
    """
    Mark an update processed only if the caller still owns its claim.

    A stale worker cannot complete an update reclaimed by another worker.
    """
    _validate_update_id(update_id)
    _validate_claim_token(claim_token)

    await db.execute(
        """
        UPDATE processed_updates
        SET
            status = 'processed',
            processed_at = unixepoch(),
            lease_expires_at = NULL
        WHERE
            update_id = ?
            AND status = 'processing'
            AND claim_token = ?;
        """,
        (
            update_id,
            claim_token,
        ),
    )

    row = await db.fetchone(
        """
        SELECT status, claim_token
        FROM processed_updates
        WHERE update_id = ?
        LIMIT 1;
        """,
        (update_id,),
    )

    if (
        row is not None
        and row.get("status") == "processed"
        and row.get("claim_token") == claim_token
    ):
        return True

    raise RuntimeError(
        "Telegram update processing ownership could not be confirmed."
    )


async def release_update_claim(
    db: Any,
    update_id: int,
    claim_token: str,
) -> bool:
    """
    Release an unfinished claim only if the caller still owns it.

    Processed updates and claims owned by another worker are preserved.
    """
    _validate_update_id(update_id)
    _validate_claim_token(claim_token)

    result = await db.execute(
        """
        DELETE FROM processed_updates
        WHERE
            update_id = ?
            AND status = 'processing'
            AND claim_token = ?;
        """,
        (
            update_id,
            claim_token,
        ),
    )

    return bool(
        result is not None
        and result.rowcount > 0
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
