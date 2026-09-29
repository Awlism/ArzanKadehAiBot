from workers import WorkerEntrypoint, Response


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        result = await self.env.DB.prepare(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).run()

        tables = [
            row["name"]
            for row in result.results
        ]

        return Response(
            "ArzanKadeh D1 OK\n"
            + "\n".join(tables)
        )  