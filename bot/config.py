# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Configuration

This module reads configuration values directly from the process
environment.

IMPORTANT:
- Do not import python-dotenv here.
- Cloudflare Workers provide environment values directly.
- Local environments can provide the same variables through their
  shell/environment configuration.
"""

from __future__ import annotations

import os
from typing import Optional


# ======================================================================
# TELEGRAM
# ======================================================================

# Telegram bot token.
#
# Required in every real deployment.
BOT_TOKEN: Optional[str] = (
    os.getenv("BOT_TOKEN", "").strip()
    or None
)


# ======================================================================
# DATABASE
# ======================================================================

# Local SQLite database path.
#
# Cloudflare Worker/D1 does not use this value for database access.
DATABASE_PATH: str = (
    os.getenv(
        "DATABASE_PATH",
        "arzan_kadeh.db",
    ).strip()
    or "arzan_kadeh.db"
)


# ======================================================================
# DEMO DATA
# ======================================================================

# Optional demo data seeding.
#
# Disabled by default.
SEED_DEMO_DATA: bool = (
    os.getenv(
        "SEED_DEMO_DATA",
        "false",
    )
    .strip()
    .lower()
    == "true"
)


# ======================================================================
# ADMIN
# ======================================================================

# Numeric Telegram chat ID of the main admin.
#
# Telegram Bot API delivery uses the numeric chat ID.
#
# If the value is missing or invalid:
# - requests are still stored in the database
# - live admin DM delivery is skipped
# - the bot does not crash
_admin_chat_id_raw = (
    os.getenv(
        "ADMIN_CHAT_ID",
        "",
    ).strip()
)

try:
    ADMIN_CHAT_ID: Optional[int] = (
        int(_admin_chat_id_raw)
        if _admin_chat_id_raw
        else None
    )
except ValueError:
    ADMIN_CHAT_ID = None


# Public display username only.
#
# This is not a secret and is not used for Bot API delivery.
ADMIN_USERNAME: str = (
    os.getenv(
        "ADMIN_USERNAME",
        "@awlism",
    ).strip()
    or "@awlism"
)