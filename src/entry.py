# -*- coding: utf-8 -*-

from workers import WorkerEntrypoint, Response


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        from aiogram import Bot, Dispatcher
        from aiogram import __version__ as AIOGRAM_VERSION

        from bot.backend import backend
        from bot.d1_backend import D1Backend
        from bot.handlers import (
            account,
            ads,
            admin,
            buyer,
            compare,
            navigation,
            notifications,
            products,
            referrals,
            search,
            seller,
            support,
        )

        # Connect the application backend to Cloudflare D1.
        d1_backend = D1Backend(self.env.DB)
        backend.set_backend(d1_backend)
        await backend.connect()

        cities_count = "SKIPPED"

        dp = Dispatcher()

        routers = [
            buyer.router,
            search.router,
            compare.router,
            products.router,
            seller.router,
            account.router,
            support.router,
            referrals.router,
            notifications.router,
            ads.router,
            admin.router,
            navigation.router,
        ]

        for router in routers:
            dp.include_router(router)

        bot = Bot(token="000000000:TEST")

        return Response(
            f"ArzanKadeh D1 query OK - "
            f"aiogram={AIOGRAM_VERSION} - "
            f"routers={len(routers)} - "
            f"backend={type(backend.active).__name__} - "
            f"cities={cities_count} - "
            f"bot={type(bot).__name__}"
        )