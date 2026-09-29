# -*- coding: utf-8 -*-

from workers import WorkerEntrypoint, Response


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        from aiogram import Bot, Dispatcher
        from aiogram import __version__ as AIOGRAM_VERSION

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
            f"ArzanKadeh handlers OK - "
            f"aiogram={AIOGRAM_VERSION} - "
            f"routers={len(routers)} - "
            f"dispatcher={type(dp).__name__} - "
            f"bot={type(bot).__name__}"
        )