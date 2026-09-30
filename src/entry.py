# -*- coding: utf-8 -*-

from workers import WorkerEntrypoint, Response


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response(
            "ArzanKadeh Worker baseline OK"
        )