# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Cloudflare Worker entrypoint

Current stage:
- Connect Worker -> Worker D1Backend -> D1.
- Do not import Telegram/aiogram application code here yet.
"""

from workers import WorkerEntrypoint, Response

from worker_backend.backend import backend
from worker_backend.d1_backend import D1Backend


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        try:
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

            return Response(body)

        except Exception as exc:
            return Response(
                "ArzanKadeh Worker D1Backend ERROR\n\n"
                f"{type(exc).__name__}: {exc}",
                status=500,
            )