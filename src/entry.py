# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker entrypoint

Webhook foundation:
- GET /  -> health check
- POST / -> Telegram webhook foundation
- No aiogram import.
- No Telegram Bot API call yet.
"""

from workers import WorkerEntrypoint, Response

from worker_backend.backend import backend
from worker_backend.d1_backend import D1Backend


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        try:
            method = request.method
            url = request.url

            if method == "GET":
                return await self._health_check()

            if method == "POST":
                return await self._handle_webhook(request)

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

    async def _health_check(self):
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

        return Response(body)

    async def _handle_webhook(self, request):
        secret = self._get_webhook_secret()

        received_secret = request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token"
        )

        if secret:
            if received_secret != secret:
                return Response(
                    "Unauthorized",
                    status=401,
                )

        try:
            update = await request.json()
        except Exception:
            return Response(
                "Invalid JSON",
                status=400,
            )

        if not isinstance(update, dict):
            return Response(
                "Invalid Telegram update",
                status=400,
            )

        update_type = self._detect_update_type(
            update
        )

        body = (
            "ArzanKadeh Webhook OK\n\n"
            f"Update type: {update_type}"
        )

        return Response(
            body,
            status=200,
        )

    def _get_webhook_secret(self):
        try:
            return self.env.TELEGRAM_WEBHOOK_SECRET
        except Exception:
            return None

    @staticmethod
    def _detect_update_type(update):
        update_types = (
            "message",
            "edited_message",
            "channel_post",
            "edited_channel_post",
            "inline_query",
            "chosen_inline_result",
            "callback_query",
            "shipping_query",
            "pre_checkout_query",
            "poll",
            "poll_answer",
            "my_chat_member",
            "chat_member",
            "chat_join_request",
        )

        for update_type in update_types:
            if update_type in update:
                return update_type

        return "unknown"