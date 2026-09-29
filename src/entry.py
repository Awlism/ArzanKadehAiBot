from aiogram import Dispatcher
from aiogram import __version__ as AIOGRAM_VERSION
from workers import WorkerEntrypoint, Response


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        dp = Dispatcher()

        return Response(
            f"ArzanKadeh aiogram Dispatcher OK - version {AIOGRAM_VERSION}"
        )