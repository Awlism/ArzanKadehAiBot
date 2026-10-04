# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker persistent state layer.

This module stores temporary multi-step Worker state in Cloudflare D1.
It intentionally does not import aiogram, sqlite, or aiosqlite.
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
        data = json.loads(
            str(value)
        )
    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
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
    """
    Ensure the persistent Worker state table exists.

    This is safe to call more than once.
    """

    await db.execute(
        STATE_TABLE_SQL
    )


async def get_state(
    db: Any,
    user_id: int,
) -> dict[str, Any] | None:
    """
    Return the current persistent state for a user.

    Returns:
        {
            "state": str,
            "data": dict,
            "updated_at": str,
        }

        or None when no state exists.
    """

    row = await db.fetchone(
        """
        SELECT
            state,
            data,
            updated_at
        FROM worker_states
        WHERE user_id = ?
        LIMIT 1;
        """,
        (user_id,),
    )

    if row is None:
        return None

    return {
        "state": str(
            row["state"]
        ),
        "data": _deserialize_data(
            row["data"]
        ),
        "updated_at": str(
            row["updated_at"]
        ),
    }


async def set_state(
    db: Any,
    user_id: int,
    state: str,
    data: dict[str, Any] | None = None,
) -> None:
    """
    Create or replace the current persistent state for a user.

    A user has exactly one active Worker state.
    """

    if not isinstance(
        user_id,
        int,
    ) or user_id < 1:
        raise ValueError(
            "A valid internal user id is required."
        )

    if not isinstance(
        state,
        str,
    ) or not state.strip():
        raise ValueError(
            "A non-empty Worker state is required."
        )

    serialized_data = _serialize_data(
        data
    )

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
    """
    Remove the current persistent state for a user.
    """

    if not isinstance(
        user_id,
        int,
    ) or user_id < 1:
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


__all__ = [
    "STATE_TABLE_SQL",
    "ensure_state_table",
    "get_state",
    "set_state",
    "clear_state",
]