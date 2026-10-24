
# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Advertisement lookup and delivery helpers for Cloudflare Workers.

Only displays active, unexpired public advertisements.
Never activates, approves, or modifies advertisements.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Optional
from urllib.parse import urlsplit


ACTIVE_AD_REQUEST_TYPES = ("general_ad",)

DEFAULT_AD_LIMIT = 3
MAX_AD_LIMIT = 10

PLACEMENT_ALIASES = {
    "home": (
        "صفحه اصلی",
        "صفحه‌اصلی",
        "خانه",
        "home",
        "main",
    ),
    "search": (
        "نتایج جستجو",
        "نتایج جست‌وجو",
        "جستجو",
        "جست‌وجو",
        "search",
    ),
}


def _now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip().lower()
    text = (
        text
        .replace("ي", "ی")
        .replace("ك", "ک")
        .replace("\u200c", " ")
    )

    return " ".join(text.split())


def _positive_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_AD_LIMIT

    return max(1, min(limit, MAX_AD_LIMIT))


def _placement_matches(
    stored_placement: Any,
    requested_placement: str,
) -> bool:
    if requested_placement not in PLACEMENT_ALIASES:
        return False

    placement = _normalize_text(stored_placement)

    if not placement:
        return False

    aliases = {
        _normalize_text(alias)
        for alias in PLACEMENT_ALIASES[requested_placement]
    }
    aliases.add(_normalize_text(requested_placement))

    return placement in aliases


def _safe_http_url(value: Any) -> Optional[str]:
    if value is None:
        return None

    url = str(value).strip()

    if not url or len(url) > 2048:
        return None

    try:
        parsed = urlsplit(url)
    except ValueError:
        return None

    if parsed.scheme.lower() not in {"http", "https"}:
        return None

    if not parsed.hostname:
        return None

    if parsed.username is not None or parsed.password is not None:
        return None

    return url


async def get_active_ads(
    db: Any,
    placement: str,
    *,
    limit: int = DEFAULT_AD_LIMIT,
) -> list[dict[str, Any]]:
    """
    Return active, unexpired public ads for a supported placement.

    Does not change statuses or create database records.
    """

    if placement not in PLACEMENT_ALIASES:
        return []

    safe_limit = _positive_limit(limit)
    now = _now_iso()

    rows = await db.fetchall(
        """
        SELECT *
        FROM requests
        WHERE request_type = ?
          AND status = 'ACTIVE'
          AND ad_expires_at IS NOT NULL
          AND TRIM(ad_expires_at) <> ''
          AND julianday(ad_expires_at) > julianday(?)
          AND ad_placement IS NOT NULL
          AND TRIM(ad_placement) <> ''
        ORDER BY julianday(ad_expires_at) ASC, id ASC;
        """,
        (
            ACTIVE_AD_REQUEST_TYPES[0],
            now,
        ),
    )

    matched: list[dict[str, Any]] = []

    for row in rows or []:
        if not isinstance(row, dict):
            continue

        if not _placement_matches(
            row.get("ad_placement"),
            placement,
        ):
            continue

        matched.append(dict(row))

        if len(matched) >= safe_limit:
            break

    return matched


def get_ad_image_url(
    ad: dict[str, Any],
) -> Optional[str]:
    return _safe_http_url(ad.get("ad_image_url"))


def get_ad_link_url(
    ad: dict[str, Any],
) -> Optional[str]:
    return _safe_http_url(
        ad.get("ad_link") or ad.get("link")
    )


def render_ad_text(
    ad: dict[str, Any],
) -> str:
    """Build an HTML-safe Telegram advertisement message."""

    title = str(
        ad.get("ad_title")
        or ad.get("title")
        or ad.get("topic")
        or ""
    ).strip()

    description = str(
        ad.get("message")
        or ad.get("description")
        or ad.get("ad_description")
        or ""
    ).strip()

    lines = ["📢 <b>تبلیغ</b>"]

    if title:
        lines.append(f"\n<b>{escape(title)}</b>")

    if description:
        lines.append(f"\n{escape(description)}")

    link = get_ad_link_url(ad)

    if link:
        safe_link = escape(link, quote=True)
        lines.append(
            f'\n\n<a href="{safe_link}">مشاهده تبلیغ</a>'
        )

    return "\n".join(lines)


async def send_placement_ads(
    db: Any,
    telegram: Any,
    chat_id: int,
    placement: str,
    *,
    limit: int = 1,
) -> int:
    """
    Send active public ads to a Telegram chat.

    Delivery failures must not interrupt the main flow.
    Returns the number of ads successfully sent.
    """

    try:
        ads = await get_active_ads(
            db,
            placement,
            limit=limit,
        )
    except Exception:
        return 0

    sent = 0

    for ad in ads:
        text = render_ad_text(ad)
        image_url = get_ad_image_url(ad)

        try:
            if image_url:
                caption = text

                if len(caption) > 1024:
                    caption = "📢 <b>تبلیغ</b>"

                await telegram.call(
                    "sendPhoto",
                    {
                        "chat_id": int(chat_id),
                        "photo": image_url,
                        "caption": caption,
                        "parse_mode": "HTML",
                    },
                )

                if len(text) > 1024:
                    await telegram.send_message(
                        int(chat_id),
                        text,
                        parse_mode="HTML",
                    )
            else:
                await telegram.send_message(
                    int(chat_id),
                    text,
                    parse_mode="HTML",
                )

            sent += 1

        except Exception:
            if image_url:
                try:
                    await telegram.send_message(
                        int(chat_id),
                        text,
                        parse_mode="HTML",
                    )
                    sent += 1
                except Exception:
                    pass

    return sent


__all__ = [
    "DEFAULT_AD_LIMIT",
    "MAX_AD_LIMIT",
    "PLACEMENT_ALIASES",
    "get_active_ads",
    "get_ad_image_url",
    "get_ad_link_url",
    "render_ad_text",
    "send_placement_ads",
]
