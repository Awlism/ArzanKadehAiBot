# -*- coding: utf-8 -*-

from workers import WorkerEntrypoint, Response


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        try:
            result = await self.env.DB.prepare(
                """
                SELECT
                    name
                FROM sqlite_master
                WHERE type = 'table'
                ORDER BY name;
                """
            ).all()

            tables = [
                row["name"]
                for row in result.results
            ]

            body = (
                "ArzanKadeh Worker + D1 OK\n\n"
                f"Tables: {len(tables)}\n"
                f"{', '.join(tables)}"
            )

            return Response(body)

        except Exception as exc:
            return Response(
                "ArzanKadeh Worker D1 ERROR\n\n"
                f"{type(exc).__name__}: {exc}",
                status=500,
            )