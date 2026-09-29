from aiogram import Bot, Dispatcher
from aiogram import __version__ as AIOGRAM_VERSION
from workers import WorkerEntrypoint, Response


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        dp = Dispatcher()
        bot = Bot(token="000000000:TEST")

        return Response(
            f"ArzanKadeh aiogram Dispatcher/Bot OK - version {AIOGRAM_VERSION}"
        )