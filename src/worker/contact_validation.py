
# -*- coding: utf-8 -*-
"""
Shared validation and normalization for seller contact links.
This module is safe to use in the Cloudflare Worker runtime.
"""

from __future__ import annotations

import re
import ipaddress
from typing import Any
from urllib.parse import urlsplit


def _clean(value: Any) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    if any(
        ord(char) < 32 or ord(char) == 127
        for char in value
    ):
        return None

    return value


def instagram_url(value: Any) -> str | None:
    value = _clean(value)

    if value is None:
        return None

    value = re.sub(
        r"^https?://(?:www\.)?instagram\.com/",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = value.strip("/").lstrip("@")

    if not re.fullmatch(
        r"[A-Za-z0-9._]{1,30}",
        value,
    ):
        return None

    if (
        value.startswith(".")
        or value.endswith(".")
        or ".." in value
    ):
        return None

    return f"https://instagram.com/{value}"


def telegram_url(value: Any) -> str | None:
    value = _clean(value)

    if value is None:
        return None

    value = re.sub(
        r"^https?://(?:www\.)?t\.me/",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = value.strip("/").lstrip("@")

    if not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9_]{3,30}[A-Za-z0-9]",
        value,
    ):
        return None

    return f"https://t.me/{value}"


def website_url(value: Any) -> str | None:
    value = _clean(value)

    if value is None:
        return None

    if any(
        char.isspace() or char in '<>"\''
        for char in value
    ):
        return None

    if "://" not in value:
        value = f"https://{value}"

    try:
        parsed = urlsplit(value)

        if parsed.scheme.lower() not in {"http", "https"}:
            return None

        if not parsed.hostname:
            return None

        if parsed.username is not None or parsed.password is not None:
            return None

        # Accessing .port also validates malformed port values.
        port = parsed.port

        if port is not None and not 1 <= port <= 65535:
            return None

        hostname = parsed.hostname

        if (
            hostname.startswith(".")
            or hostname.endswith(".")
            or ".." in hostname
        ):
            return None

    except (ValueError, TypeError):
        return None

    return value


def whatsapp_url(value: Any) -> str | None:
    value = _clean(value)

    if value is None:
        return None

    if "://" in value:
        try:
            parsed = urlsplit(value)

            if (
                parsed.scheme.lower() != "https"
                or parsed.hostname is None
                or parsed.hostname.lower()
                not in {"wa.me", "api.whatsapp.com"}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port is not None
            ):
                return None

            if parsed.hostname.lower() == "wa.me":
                if not re.fullmatch(
                    r"/[0-9]{7,15}/?",
                    parsed.path,
                ):
                    return None

            else:
                if parsed.path.rstrip("/") != "/send":
                    return None

                from urllib.parse import parse_qs

                query = parse_qs(
                    parsed.query,
                    keep_blank_values=True,
                )
                phones = query.get("phone", [])

                if (
                    len(phones) != 1
                    or not re.fullmatch(
                        r"[0-9]{7,15}",
                        phones[0],
                    )
                ):
                    return None

            return value

        except (ValueError, TypeError):
            return None

    if not re.fullmatch(r"[0-9+\s().-]+", value):
        return None

    digits = re.sub(r"\D", "", value)

    if not re.fullmatch(r"[0-9]{7,15}", digits):
        return None

    return f"https://wa.me/{digits}"
