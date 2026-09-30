# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Lightweight Telegram Bot API client for Cloudflare Workers.

This module intentionally does not import aiogram.
"""

from __future__ import annotations

from typing import Any, Optional

from workers import fetch


class TelegramAPIError(Exception):
    """Base error for Telegram Bot API failures."""

    def __init__(
        self,
        message: str,
        *,
        method: Optional[str] = None,
        error_code: Optional[int] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)

        self.method = method
        self.error_code = error_code
        self.parameters = parameters or {}


class TelegramClient:
    """
    Lightweight asynchronous Telegram Bot API client.

    The bot token is read from the Worker environment and is
    never stored in source code.
    """

    def __init__(
        self,
        env: Any,
    ) -> None:
        self._token = self._read_token(
            env
        )

        self._base_url = (
            "https://api.telegram.org/bot"
            f"{self._token}"
        )

    @staticmethod
    def _read_token(
        env: Any,
    ) -> str:
        try:
            token = env.BOT_TOKEN
        except Exception as exc:
            raise TelegramAPIError(
                "BOT_TOKEN is not configured."
            ) from exc

        if token is None:
            raise TelegramAPIError(
                "BOT_TOKEN is not configured."
            )

        token = str(token).strip()

        if not token:
            raise TelegramAPIError(
                "BOT_TOKEN is not configured."
            )

        return token

    async def call(
        self,
        method: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> Any:
        if not method:
            raise ValueError(
                "Telegram API method is required."
            )

        url = (
            f"{self._base_url}/{method}"
        )

        body = payload or {}

        response = await fetch(
            url,
            {
                "method": "POST",
                "headers": {
                    "Content-Type": (
                        "application/json"
                    ),
                },
                "body": _json_dumps(body),
            },
        )

        data = await _read_json(
            response
        )

        if not isinstance(data, dict):
            raise TelegramAPIError(
                "Telegram API returned an invalid response.",
                method=method,
            )

        if not data.get("ok"):
            raise TelegramAPIError(
                str(
                    data.get(
                        "description",
                        "Telegram API request failed.",
                    )
                ),
                method=method,
                error_code=data.get(
                    "error_code"
                ),
                parameters=data.get(
                    "parameters"
                ),
            )

        return data.get("result")

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        reply_markup: Optional[
            dict[str, Any]
        ] = None,
        parse_mode: Optional[str] = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
        }

        if reply_markup is not None:
            payload["reply_markup"] = (
                reply_markup
            )

        if parse_mode is not None:
            payload["parse_mode"] = parse_mode

        return await self.call(
            "sendMessage",
            payload,
        )

    async def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        *,
        reply_markup: Optional[
            dict[str, Any]
        ] = None,
        parse_mode: Optional[str] = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }

        if reply_markup is not None:
            payload["reply_markup"] = (
                reply_markup
            )

        if parse_mode is not None:
            payload["parse_mode"] = parse_mode

        return await self.call(
            "editMessageText",
            payload,
        )

    async def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> Any:
        payload: dict[str, Any] = {
            "callback_query_id": (
                callback_query_id
            ),
            "show_alert": show_alert,
        }

        if text is not None:
            payload["text"] = text

        return await self.call(
            "answerCallbackQuery",
            payload,
        )


async def _read_json(
    response: Any,
) -> Any:
    try:
        return await response.json()
    except Exception as exc:
        raise TelegramAPIError(
            "Telegram API returned invalid JSON."
        ) from exc


def _json_dumps(
    value: Any,
) -> str:
    import json

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
    )


__all__ = [
    "TelegramAPIError",
    "TelegramClient",
]