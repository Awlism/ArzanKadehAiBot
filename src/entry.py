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

from worker.router import WorkerRouter
from worker.start import handle_start
from worker.messages import handle_message
from worker.categories import handle_category
from worker.products import (
    handle_product_detail,
    handle_favorite_add,
    handle_favorite_remove,
)
from worker.compare import (
    handle_compare,
    handle_compare_drop,
    handle_compare_list,
    handle_compare_reset,
    handle_compare_start,
)
from worker.seller import (
    handle_sellers_list,
    handle_seller_detail,
    handle_seller_favorite_add,
    handle_seller_favorite_remove,
)
from worker.review import (
    handle_review_start,
    handle_review_rating,
)
from worker.report import (
    handle_report_reason,
    handle_report_skip,
    handle_report_start,
)
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

        router = WorkerRouter()

        telegram = TelegramClient(
            self.env
        )

        if update_type == "message":

            async def message_handler(
                message,
            ):
                if _is_start_command(
                    message
                ):
                    return await handle_start(
                        message,
                        telegram,
                    )

                return await handle_message(
                    message,
                    telegram,
                )

            router.set_message_handler(
                message_handler
            )

        elif update_type == "callback_query":

            async def callback_handler(
                callback_query,
            ):
                return await _handle_callback_query(
                    callback_query,
                    telegram,
                )

            router.set_callback_handler(
                callback_handler
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


async def _handle_callback_query(
    callback_query,
    telegram,
):
    """
    Route Worker callback queries to the
    appropriate business handler.
    """

    if not isinstance(
        callback_query,
        dict,
    ):
        return None

    callback_data = callback_query.get(
        "data"
    )

    if not isinstance(
        callback_data,
        str,
    ):
        return None

    if callback_data.startswith(
        "cat:"
    ):
        return await handle_category(
            backend,
            telegram,
            callback_query,
        )

    if callback_data.startswith(
        "product:"
    ):
        return await handle_product_detail(
            backend,
            telegram,
            callback_query,
        )

    if callback_data.startswith(
        "favorite:"
    ):
        return await handle_favorite_add(
            backend,
            telegram,
            callback_query,
        )

    if callback_data.startswith(
        "unfavorite:"
    ):
        return await handle_favorite_remove(
            backend,
            telegram,
            callback_query,
        )

    if callback_data.startswith(
        "sfav:"
    ):
        return await handle_seller_favorite_add(
            backend,
            telegram,
            callback_query,
        )

    if callback_data.startswith(
        "sunfav:"
    ):
        return await handle_seller_favorite_remove(
            backend,
            telegram,
            callback_query,
        )

    if callback_data.startswith(
        "sellers:"
    ):
        return await handle_sellers_list(
            backend,
            telegram,
            callback_query,
        )

    if callback_data.startswith(
        "seller:"
    ):
        return await handle_seller_detail(
            backend,
            telegram,
            callback_query,
        )

    if callback_data.startswith(
        "reviewstart:"
    ):
        return await handle_review_start(
            callback_query,
            telegram,
        )

    if callback_data.startswith(
        "reviewrate:"
    ):
        return await handle_review_rating(
            callback_query,
            telegram,
        )

    if callback_data.startswith(
        "report:"
    ):
        return await handle_report_start(
            callback_query,
            telegram,
        )

    if callback_data.startswith(
        "reportreason:"
    ):
        return await handle_report_reason(
            callback_query,
            telegram,
        )

    if callback_data == "reportskip":
        return await handle_report_skip(
            callback_query,
            telegram,
        )

    if callback_data == "compare":
        return await handle_compare(
            backend,
            telegram,
            callback_query,
        )

    if callback_data == "comparelist":
        return await handle_compare_list(
            backend,
            telegram,
            callback_query,
        )

    if callback_data.startswith(
        "comparestart:"
    ):
        return await handle_compare_start(
            backend,
            telegram,
            callback_query,
        )

    if callback_data.startswith(
        "comparedrop:"
    ):
        return await handle_compare_drop(
            backend,
            telegram,
            callback_query,
        )

    if callback_data == "comparereset":
        return await handle_compare_reset(
            backend,
            telegram,
            callback_query,
        )

    return None


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