
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

CLAIM_LEASE_SECONDS = 300

_SECRET_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]{1,256}$"
)


def _utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="microseconds"
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

    stage = "initial_status_check"

    try:
        # Avoid requiring credentials after setup is complete.
        current = await db.fetchone(
            """
            SELECT status
            FROM worker_webhook_setup
            WHERE id = 1
            LIMIT 1;
            """
        )

        if (
            current is not None
            and current.get("status") == "configured"
        ):
            return False

        # Validate credentials before claiming the lease.
        stage = "bot_token_validation"
        TelegramClient._read_token(env)

        stage = "webhook_secret_validation"
        secret = get_webhook_secret(env)

        if (
            secret is None
            or _SECRET_PATTERN.fullmatch(secret) is None
        ):
            raise ValueError(
                "Telegram webhook secret is missing or invalid."
            )

        claim_token = uuid.uuid4().hex
        now = _utc_now()

        stage = "claim_registration"
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

        stage = "claim_verification"
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
            stage = "telegram_set_webhook"
            telegram = TelegramClient(env)

            await telegram.call(
                "setWebhook",
                {
                    "url": WEBHOOK_URL,
                    "secret_token": secret,
                    "allowed_updates": ALLOWED_UPDATES,
                },
            )

            configured_at = _utc_now()

            stage = "database_configuration_update"
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

            stage = "configuration_confirmation"
            result = await db.fetchone(
                """
                SELECT status, configured_at
                FROM worker_webhook_setup
                WHERE id = 1
                LIMIT 1;
                """
            )

            if (
                result is None
                or result.get("status") != "configured"
                or result.get("configured_at") != configured_at
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
                        _utc_now(),
                        claim_token,
                    ),
                )
            except Exception:
                pass

            raise

    except Exception as exc:
        # Never log credentials, request payloads, or exception messages.
        error_type = type(exc).__name__
        error_code = getattr(exc, "error_code", None)
        method = getattr(exc, "method", None)

        diagnostic = (
            "Telegram webhook setup diagnostic: "
            f"stage={stage}, "
            f"error_type={error_type}"
        )

        if error_code is not None:
            diagnostic += f", error_code={error_code}"

        if method is not None:
            diagnostic += f", method={method}"

        print(diagnostic)
        raise


__all__ = [
    "WEBHOOK_URL",
    "ALLOWED_UPDATES",
    "CLAIM_LEASE_SECONDS",
    "ensure_telegram_webhook",
]
