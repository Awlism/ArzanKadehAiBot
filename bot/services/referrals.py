# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Referral / seller growth service
"""

import logging
import re

from ..database import db
from ..utils import now_iso

logger = logging.getLogger("arzankadeh")


REFERRAL_REWARD_RULES = [
    (5, "⭐ امتیاز"),
    (20, "🔥 Boost رایگان"),
    (50, "⭐ Featured چندروزه"),
    (100, "🏆 فروشنده ویژه"),
]

REFERRAL_DEEP_LINK_RE = re.compile(r"^shop_(\d+)$")


def build_referral_link(
    bot_username: str,
    seller_id: int,
) -> str:
    return f"https://t.me/{bot_username}?start=shop_{seller_id}"


async def get_referral_count(
    seller_id: int,
) -> int:
    row = await db.fetchone(
        """
        SELECT COUNT(*) AS c
        FROM referrals
        WHERE seller_id = ?;
        """,
        (seller_id,),
    )

    return row["c"] if row else 0


def next_referral_milestone(count: int):
    for threshold, label in REFERRAL_REWARD_RULES:
        if count < threshold:
            return threshold, label

    return None


async def record_referral_if_new(
    seller_id: int,
    referred_user_id: int,
) -> bool:
    try:
        seller = await db.fetchone(
            """
            SELECT
                id,
                owner_user_id,
                created_by_user_id
            FROM sellers
            WHERE id = ?;
            """,
            (seller_id,),
        )

        if not seller:
            return False

        if (
            seller["owner_user_id"] == referred_user_id
            or seller["created_by_user_id"] == referred_user_id
        ):
            return False

        existing = await db.fetchone(
            """
            SELECT id
            FROM referrals
            WHERE referred_user_id = ?;
            """,
            (referred_user_id,),
        )

        if existing:
            return False

        await db.execute(
            """
            INSERT INTO referrals (
                seller_id,
                referred_user_id,
                source,
                created_at
            )
            VALUES (?, ?, 'deep_link', ?);
            """,
            (
                seller_id,
                referred_user_id,
                now_iso(),
            ),
        )

        return True

    except Exception as exc:
        logger.error(
            "Failed to record referral for seller %s: %s",
            seller_id,
            exc,
        )
        return False


async def get_sellers_owned_by_user(
    user_id: int,
) -> list:
    return await db.fetchall(
        """
        SELECT id, name
        FROM sellers
        WHERE created_by_user_id = ?
           OR owner_user_id = ?
        ORDER BY id DESC;
        """,
        (
            user_id,
            user_id,
        ),
    )


async def referral_stats_text(
    bot_username: str,
    seller_id: int,
    seller_name: str,
) -> str:
    count = await get_referral_count(seller_id)
    link = build_referral_link(
        bot_username,
        seller_id,
    )
    milestone = next_referral_milestone(count)

    lines = [
        f"🎁 لینک اختصاصی فروشگاه «{seller_name}»",
        "",
        "این لینک را در استوری اینستاگرام یا کانال تلگرامت منتشر کن تا افراد بیشتری فروشگاهت را پیدا کنند.",
        "",
        f"🔗 لینک اختصاصی فروشگاه:\n{link}",
        "",
        "📊 آمار معرفی:",
        f"👥 کاربران معرفی‌شده: {count}",
    ]

    if milestone:
        threshold, label = milestone
        lines.append(
            f"🏁 مرحله بعدی: {threshold} معرفی ← {label}"
        )

    return "\n".join(lines)