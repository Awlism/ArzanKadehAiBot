# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Configuration
"""

import os
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


BOT_TOKEN: Optional[str] = os.getenv("BOT_TOKEN")

DATABASE_PATH: str = os.getenv(
    "DATABASE_PATH",
    "arzan_kadeh.db",
)

# Optional demo data seeding.
# Disabled by default.
SEED_DEMO_DATA: bool = (
    os.getenv("SEED_DEMO_DATA", "false")
    .strip()
    .lower()
    == "true"
)


# Numeric Telegram chat ID of the main admin.
#
# Telegram Bot API cannot reliably deliver a message to an arbitrary
# @username unless that user has already started a conversation with
# the bot. Therefore the actual numeric chat ID is read from .env.
#
# If ADMIN_CHAT_ID is missing or invalid:
# - requests are still stored in the database
# - live admin DM delivery is skipped
# - the bot does not crash
_admin_chat_id_raw = os.getenv("ADMIN_CHAT_ID", "").strip()

try:
    ADMIN_CHAT_ID: Optional[int] = (
        int(_admin_chat_id_raw)
        if _admin_chat_id_raw
        else None
    )
except ValueError:
    ADMIN_CHAT_ID = None


# Public display username only.
# This is NOT a secret and is NOT used for Bot API delivery.
ADMIN_USERNAME = "@awlism"