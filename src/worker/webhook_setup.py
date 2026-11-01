# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Safe, persistent Telegram webhook setup for Cloudflare Workers.
"""

from __future__ import annotations

import re
import uuid

from datetime import datetime, timezone
from typing import Any

from worker.telegram import TelegramClient
from worker.webhook import get_webhook_secret


WEBHOOK_URL = (
    "https://arzankadehaibot.a-shahbazpor.workers.dev/"
)

ALLOWED_UPDATES = [
    "message",
    "callback_query",
]

CLAIM_LEASE_SECONDS = 120

_SECRET_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]{1,256}$"
)


async def ensure_telegram_webhook(
    db: Any,
    env: Any,
) -> bool:
    """
    Configure the Telegram webhook once.

    A persistent D1 lease prevents overlapping scheduled
    invocations from configuring the webhook concurrently.

    Returns True when this invocation configures the webhook.
    Returns False when setup is already complete or another
    invocation currently owns the lease.
    """

    # Validate required credentials before claiming the lease.
    TelegramClient._read_token(env)

    secret = get_webhook_secret(env)

    if (
        secret is None
        or _SECRET_PATTERN.fullmatch(secret) is None
    ):
        raise ValueError(
            "Telegram webhook secret is missing or invalid."
        )

    claim_token = uuid.uuid4().hex

    now = datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )

    await db.execute(
        """
        INSERT INTO worker_webhook_setup (
            id,
            status,
            claim_token,
            lease_expires_at,
            configured_at,
            updated_at
        )
        VALUES (
            1,
            'processing',
            ?,
            unixepoch() + ?,
            NULL,
            ?
        )
        ON CONFLICT(id)
        DO UPDATE SET
            status = 'processing',
            claim_token = excluded.claim_token,
            lease_expires_at = excluded.lease_expires_at,
            configured_at = NULL,
            updated_at = excluded.updated_at
        WHERE worker_webhook_setup.status != 'configured'
          AND (
              worker_webhook_setup.status = 'pending'
              OR worker_webhook_setup.lease_expires_at IS NULL
              OR worker_webhook_setup.lease_expires_at <= unixepoch()
          );
        """,
        (
            claim_token,
            CLAIM_LEASE_SECONDS,
            now,
        ),
    )

    claim = await db.fetchone(
        """
        SELECT status, claim_token
        FROM worker_webhook_setup
        WHERE id = 1
        LIMIT 1;
        """
    )

    if (
        claim is None
        or claim.get("status") != "processing"
        or claim.get("claim_token") != claim_token
    ):
        return False

    try:
        telegram = TelegramClient(env)

        await telegram.call(
            "setWebhook",
            {
                "url": WEBHOOK_URL,
                "secret_token": secret,
                "allowed_updates": ALLOWED_UPDATES,
            },
        )

        configured_at = datetime.now(
            timezone.utc
        ).isoformat(
            timespec="seconds"
        )

        await db.execute(
            """
            UPDATE worker_webhook_setup
            SET
                status = 'configured',
                claim_token = NULL,
                lease_expires_at = NULL,
                configured_at = ?,
                updated_at = ?
            WHERE id = 1
              AND status = 'processing'
              AND claim_token = ?;
            """,
            (
                configured_at,
                configured_at,
                claim_token,
            ),
        )

        result = await db.fetchone(
            """
            SELECT status
            FROM worker_webhook_setup
            WHERE id = 1
            LIMIT 1;
            """
        )

        if (
            result is None
            or result.get("status") != "configured"
        ):
            raise RuntimeError(
                "Telegram webhook setup state could not be confirmed."
            )

        return True

    except Exception:
        # Release only our own claim.
        # Preserve the original exception if release also fails.
        try:
            await db.execute(
                """
                UPDATE worker_webhook_setup
                SET
                    status = 'pending',
                    claim_token = NULL,
                    lease_expires_at = NULL,
                    configured_at = NULL,
                    updated_at = ?
                WHERE id = 1
                  AND status = 'processing'
                  AND claim_token = ?;
                """,
                (
                    datetime.now(
                        timezone.utc
                    ).isoformat(
                        timespec="seconds"
                    ),
                    claim_token,
                ),
            )
        except Exception:
            pass

        raise


__all__ = [
    "WEBHOOK_URL",
    "ALLOWED_UPDATES",
    "CLAIM_LEASE_SECONDS",
    "ensure_telegram_webhook",
]