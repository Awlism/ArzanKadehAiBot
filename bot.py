# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Main application entry point
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN
from bot.database import (
    db,
    init_schema,
    seed_categories,
    seed_cities,
    seed_demo_data,
)
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
from bot.services.tasks import (
    periodic_ad_expiry_task,
    periodic_backup_task,
)


# ======================================================================
# LOGGING
# ======================================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger("arzankadeh")


# ======================================================================
# STARTUP / SHUTDOWN
# ======================================================================

async def on_startup() -> None:
    """
    Initialize the database and seed required static data.
    """

    logger.info(
        "ArzanKadeh AI starting..."
    )

    await db.connect()

    await init_schema()

    await seed_cities()

    await seed_categories()

    await seed_demo_data()

    logger.info(
        "Database initialized successfully."
    )


async def on_shutdown() -> None:
    """
    Close database resources.
    """

    logger.info(
        "ArzanKadeh AI shutting down..."
    )

    await db.close()

    logger.info(
        "Database connection closed."
    )


# ======================================================================
# GLOBAL ERROR HANDLER
# ======================================================================

async def handle_global_error(event) -> bool:
    """
    Global error handler.

    Prevents unexpected handler exceptions from silently breaking
    the update-processing flow.
    """

    logger.exception(
        "Unhandled exception while processing update %s: %s",
        event.update,
        event.exception,
    )

    try:
        update = event.update

        chat = None
        bot_obj = None

        if update.message:
            chat = update.message.chat
            bot_obj = update.message.bot

        elif (
            update.callback_query
            and update.callback_query.message
        ):
            chat = update.callback_query.message.chat
            bot_obj = update.callback_query.bot

        if (
            chat is not None
            and bot_obj is not None
        ):
            await bot_obj.send_message(
                chat.id,
                (
                    "⚠️ یه مشکل غیرمنتظره پیش اومد.\n\n"
                    "لطفاً دوباره تلاش کن یا از "
                    "«🏠 شروع از اول» استفاده کن."
                ),
            )

        if update.callback_query:
            try:
                await update.callback_query.answer()
            except Exception:
                pass

    except Exception as exc:
        logger.error(
            "Failed to notify user about an unhandled error: %s",
            exc,
        )

    return True


# ======================================================================
# DISPATCHER
# ======================================================================

def create_dispatcher() -> Dispatcher:
    """
    Create and configure the application's Dispatcher.

    Router registration order is intentional:
    specific handlers are registered before generic fallback handlers.
    """

    dp = Dispatcher(
        storage=MemoryStorage(),
    )

    # --------------------------------------------------------------
    # Buyer functionality
    # --------------------------------------------------------------

    dp.include_router(buyer.router)

    dp.include_router(search.router)

    dp.include_router(compare.router)

    dp.include_router(products.router)

    # --------------------------------------------------------------
    # Seller functionality
    # --------------------------------------------------------------

    dp.include_router(seller.router)

    # --------------------------------------------------------------
    # Account / support / referrals / notifications
    # --------------------------------------------------------------

    dp.include_router(account.router)

    dp.include_router(support.router)

    dp.include_router(referrals.router)

    dp.include_router(notifications.router)

    # --------------------------------------------------------------
    # Advertising
    # --------------------------------------------------------------

    dp.include_router(ads.router)

    # --------------------------------------------------------------
    # Administration
    # --------------------------------------------------------------

    dp.include_router(admin.router)

    # --------------------------------------------------------------
    # Navigation / start / fallback
    #
    # IMPORTANT:
    # navigation contains /start, role selection, restart handling,
    # and generic fallback handlers.
    #
    # It must remain at the end.
    # --------------------------------------------------------------

    dp.include_router(navigation.router)

    # --------------------------------------------------------------
    # Global error handler
    # --------------------------------------------------------------

    dp.errors.register(
        handle_global_error,
    )

    return dp


# ======================================================================
# MAIN
# ======================================================================

async def main() -> None:
    """
    Application entry point.
    """

    if not BOT_TOKEN:
        logger.error(
            "BOT_TOKEN is missing. "
            "Please create a .env file with "
            "BOT_TOKEN=<your token> and try again."
        )
        return

    await on_startup()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    dp = create_dispatcher()

    backup_task = asyncio.create_task(
        periodic_backup_task()
    )

    ad_expiry_task = asyncio.create_task(
        periodic_ad_expiry_task()
    )

    try:
        logger.info(
            "Bot is running."
        )

        await dp.start_polling(
            bot,
        )

    except asyncio.CancelledError:
        logger.info(
            "Bot polling cancelled."
        )
        raise

    except Exception:
        logger.exception(
            "Bot polling stopped because of an unexpected error."
        )
        raise

    finally:
        logger.info(
            "Stopping background tasks..."
        )

        backup_task.cancel()
        ad_expiry_task.cancel()

        await asyncio.gather(
            backup_task,
            ad_expiry_task,
            return_exceptions=True,
        )

        try:
            await bot.session.close()
        except Exception:
            logger.exception(
                "Failed to close bot session."
            )

        await on_shutdown()


# ======================================================================
# ENTRY POINT
# ======================================================================

if __name__ == "__main__":
    try:
        asyncio.run(
            main()
        )
    except KeyboardInterrupt:
        logger.info(
            "ArzanKadeh AI stopped by user."
        )