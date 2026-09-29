# -*- coding: utf-8 -*-

from workers import WorkerEntrypoint, Response


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        from aiogram import Bot, Dispatcher
        from aiogram import __version__ as AIOGRAM_VERSION

        dp = Dispatcher()
        bot = Bot(token="000000000:TEST")

        return Response(
            f"ArzanKadeh dynamic aiogram OK - "
            f"version {AIOGRAM_VERSION} - "
            f"dispatcher={type(dp).__name__} - "
            f"bot={type(bot).__name__}"
        )