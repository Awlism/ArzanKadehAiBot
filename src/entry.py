from aiogram import Bot, Dispatcher
from workers import WorkerEntrypoint, Response


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # Compatibility proof only:
        # verify that aiogram can be imported and its core
        # Bot/Dispatcher classes can be initialized in the
        # Cloudflare Python Worker runtime.

        dp = Dispatcher()
        bot = Bot(token="000000000:TEST")

        await bot.session.close()

        return Response(
            "ArzanKadeh Worker AIogram compatibility OK"
        )