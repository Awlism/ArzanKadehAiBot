# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Dependency-free time helpers
"""

from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )