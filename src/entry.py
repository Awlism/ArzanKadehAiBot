# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker entrypoint.

Routes:
- GET  / -> D1 health check
- POST / -> Telegram webhook router

No aiogram is imported here.
"""

from workers import WorkerEntrypoint, Response

from worker_backend.backend import backend
from worker_backend.d1_backend import D1Backend

from worker.webhook import (
    InvalidWebhookPayloadError,
    UnauthorizedWebhookError,
    build_webhook_response_body,
    detect_update_type,
    parse_webhook_update,
    verify_webhook_secret,
)

from worker.router import router
from worker.start import handle_start
from worker.telegram import TelegramClient


class Default(WorkerEntrypoint):
    async def fetch(
        self,
        request,
    ):
        try:
            method = request.method

            if method == "GET":
                return await self._health_check()

            if method == "POST":
                return await self._handle_webhook(
                    request
                )

            return Response(
                "Method Not Allowed",
                status=405,
            )

        except Exception as exc:
            return Response(
                "ArzanKadeh Worker ERROR\n\n"
                f"{type(exc).__name__}: {exc}",
                status=500,
            )

    async def _health_check(
        self,
    ):
        d1_backend = D1Backend(
            self.env.DB
        )

        backend.set_backend(
            d1_backend
        )

        await backend.connect()

        rows = await backend.fetchall(
            """
            SELECT
                name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name;
            """
        )

        tables = [
            row["name"]
            for row in rows
        ]

        body = (
            "ArzanKadeh Worker + D1Backend OK\n\n"
            f"Tables: {len(tables)}\n"
            f"{', '.join(tables)}"
        )

        return Response(
            body,
            status=200,
        )

    async def _handle_webhook(
        self,
        request,
    ):
        try:
            verify_webhook_secret(
                request,
                self.env,
            )

            update = await parse_webhook_update(
                request
            )

        except UnauthorizedWebhookError:
            return Response(
                "Unauthorized",
                status=401,
            )

        except InvalidWebhookPayloadError:
            return Response(
                "Invalid Telegram update",
                status=400,
            )

        d1_backend = D1Backend(
            self.env.DB
        )

        backend.set_backend(
            d1_backend
        )

        await backend.connect()

        update_type = detect_update_type(
            update
        )

        if (
            update_type == "message"
            and _is_start_command(
                update["message"]
            )
        ):
            telegram = TelegramClient(
                self.env
            )

            router.set_message_handler(
                lambda message: handle_start(
                    message,
                    telegram,
                )
            )

        await router.dispatch(
            update
        )

        body = build_webhook_response_body(
            update_type
        )

        return Response(
            body,
            status=200,
        )


def _is_start_command(
    message,
) -> bool:
    if not isinstance(
        message,
        dict,
    ):
        return False

    text = message.get(
        "text"
    )

    if not isinstance(
        text,
        str,
    ):
        return False

    text = text.strip()

    if not text:
        return False

    command = text.split(
        maxsplit=1
    )[0]

    return (
        command == "/start"
        or command.startswith(
            "/start@"
        )
    )


__all__ = [
    "Default",
]