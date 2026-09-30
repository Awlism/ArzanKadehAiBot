# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Lightweight Telegram update router for Cloudflare Workers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from typing import Any


class WorkerRouter:
    """
    Routes Telegram updates to Worker-side handlers.

    Handlers are registered per request so that
    Cloudflare Worker requests do not share state.
    """

    def __init__(
        self,
    ) -> None:
        self._message_handler = None
        self._callback_handler = None

    def set_message_handler(
        self,
        handler: Any,
    ) -> None:
        self._message_handler = handler

    def set_callback_handler(
        self,
        handler: Any,
    ) -> None:
        self._callback_handler = handler

    async def dispatch(
        self,
        update: dict[str, Any],
    ) -> Any:
        if "message" in update:
            return await self._dispatch_message(
                update["message"]
            )

        if "callback_query" in update:
            return await self._dispatch_callback_query(
                update["callback_query"]
            )

        return None

    async def _dispatch_message(
        self,
        message: Any,
    ) -> Any:
        if self._message_handler is None:
            return None

        return await self._message_handler(
            message
        )

    async def _dispatch_callback_query(
        self,
        callback_query: Any,
    ) -> Any:
        if self._callback_handler is None:
            return None

        return await self._callback_handler(
            callback_query
        )


router = WorkerRouter()


__all__ = [
    "WorkerRouter",
    "router",
]