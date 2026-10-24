# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Shared advertisement lookup and rendering helpers for Cloudflare Workers.

Reads active advertisements from the existing D1 requests table.
Does not create tables, change request statuses, or send Telegram messages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Optional
from urllib.parse import urlsplit


ACTIVE_AD_REQUEST_TYPES = (
    "ad",
    "general_ad",
)

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
    ).isoformat(
        timespec="seconds"
    )


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

    if limit < 1:
        return 1

    return min(limit, MAX_AD_LIMIT)


def _placement_matches(
    stored_placement: Any,
    requested_placement: str,
) -> bool:
    """
    Match a stored placement against a supported placement.
    Unknown or blank placements are not displayed.
    """

    if requested_placement not in PLACEMENT_ALIASES:
        return False

    placement = _normalize_text(stored_placement)

    if not placement:
        return False

    aliases = {
        _normalize_text(alias)
        for alias in PLACEMENT_ALIASES[requested_placement]
    }

    aliases.add(
        _normalize_text(requested_placement)
    )

    for alias in aliases:
        if not alias:
            continue

        if placement == alias:
            return True

        if len(alias) >= 5 and alias in placement:
            return True

    return False


def _safe_http_url(
    value: Any,
) -> Optional[str]:
    """Accept only absolute HTTP(S) URLs without embedded credentials."""

    if value is None:
        return None

    url = str(value).strip()

    if not url or len(url) > 2048:
        return None

    try:
        parsed = urlsplit(url)
    except ValueError:
        return None

    if parsed.scheme.lower() not in {
        "http",
        "https",
    }:
        return None

    if not parsed.netloc:
        return None

    if (
        parsed.username is not None
        or parsed.password is not None
    ):
        return None

    return url


async def get_active_ads(
    db: Any,
    placement: str,
    *,
    limit: int = DEFAULT_AD_LIMIT,
) -> list[dict[str, Any]]:
    """
    Return active, unexpired advertisements for a supported placement.

    Only reads existing rows from requests.
    Does not activate approved ads or mutate records.
    """

    if placement not in PLACEMENT_ALIASES:
        return []

    safe_limit = _positive_limit(limit)
    now = _now_iso()

    rows = await db.fetchall(
        """
        SELECT *
        FROM requests
        WHERE request_type IN (?, ?)
          AND status = 'ACTIVE'
          AND ad_expires_at IS NOT NULL
          AND TRIM(ad_expires_at) <> ''
          AND ad_expires_at > ?
          AND ad_placement IS NOT NULL
          AND TRIM(ad_placement) <> ''
        ORDER BY ad_expires_at ASC, id ASC
        LIMIT ?;
        """,
        (
            ACTIVE_AD_REQUEST_TYPES[0],
            ACTIVE_AD_REQUEST_TYPES[1],
            now,
            MAX_AD_LIMIT * 10,
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
    """Return a validated image URL, if one was saved."""

    return _safe_http_url(
        ad.get("ad_image_url")
    )


def get_ad_link_url(
    ad: dict[str, Any],
) -> Optional[str]:
    """Return a validated destination URL, if one was saved."""

    return _safe_http_url(
        ad.get("ad_link") or ad.get("link")
    )


def render_ad_text(
    ad: dict[str, Any],
) -> str:
    """Build an HTML-safe Telegram advertisement message."""

    title = (
        ad.get("ad_title")
        or ad.get("title")
        or ad.get("topic")
        or ""
    )

    description = (
        ad.get("message")
        or ad.get("description")
        or ad.get("ad_description")
        or ""
    )

    title = str(title).strip()
    description = str(description).strip()

    lines = [
        "📢 <b>تبلیغ</b>",
    ]

    if title:
        lines.append(
            f"\n<b>{escape(title)}</b>"
        )

    if description:
        lines.append(
            f"\n{escape(description)}"
        )

    link = get_ad_link_url(ad)

    if link:
        safe_link = escape(
            link,
            quote=True,
        )

        lines.append(
            f'\n\n<a href="{safe_link}">مشاهده تبلیغ</a>'
        )

    return "\n".join(lines)


__all__ = [
    "DEFAULT_AD_LIMIT",
    "MAX_AD_LIMIT",
    "PLACEMENT_ALIASES",
    "get_active_ads",
    "get_ad_image_url",
    "get_ad_link_url",
    "render_ad_text",
]