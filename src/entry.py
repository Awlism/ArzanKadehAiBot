from aiogram import Dispatcher
from aiogram import __version__ as AIOGRAM_VERSION
from workers import WorkerEntrypoint, Response


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response(
            f"ArzanKadeh aiogram Dispatcher import OK - version {AIOGRAM_VERSION}"
        )