import asyncio
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from alembic.config import Config
from alembic import command

from .config import settings
from .db.postgres import db
from .db.redis_client import redis_client
from .logging_config import logger
from .handlers import user, payments, onboarding
from .services.mailing_service import poll_pending_mailings
from .middlewares import setup_middlewares
from aiogptbot.bot.services.payment_service import poll_cryptocloud_payments
from aiogptbot.bot.services.subscription_service import reset_daily_limits

# Проверка переменных окружения
REQUIRED_ENV = [settings.BOT_TOKEN, settings.OPENAI_API_KEY, settings.POSTGRES_DSN, settings.REDIS_DSN]
if not all(REQUIRED_ENV):
    logger.error("Не все переменные окружения заданы. Проверьте .env файл.")
    sys.exit(1)

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать диалог"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="profile", description="Профиль и подписка"),
        BotCommand(command="buy_premium", description="Купить подписку (Telegram)"),
        BotCommand(command="buy_premium_crypto", description="Купить подписку (CryptoCloud)"),
    ]
    await bot.set_my_commands(commands)

async def on_startup(bot: Bot):
    logger.info("Подключение к PostgreSQL...")
    await db.connect()
    logger.info("Подключение к PostgreSQL установлено")
    
    # Применение миграций Alembic
    logger.info("Применение миграций БД...")
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Миграции БД успешно применены.")
    except Exception as e:
        logger.error(f"Ошибка при применении миграций: {e}")
        # В зависимости от политики, можно либо остановить запуск, либо продолжить
        # sys.exit(1)

    logger.info("Подключение к Redis...")
    try:
        await redis_client.ping()
        logger.info("Подключение к Redis установлено")
    except Exception as e:
        logger.error(f"Ошибка подключения к Redis: {e}")
        sys.exit(1)
        
    await set_commands(bot)
    logger.info("Команды бота установлены")

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(reset_daily_limits, 'cron', hour=0, minute=0)
    scheduler.start()
    logger.info("Планировщик для сброса лимитов запущен.")

    logger.info("Запуск фоновых задач...")
    asyncio.create_task(poll_pending_mailings(bot))
    asyncio.create_task(poll_cryptocloud_payments(bot))
    logger.info("Фоновые задачи запущены")
    logger.info("Бот запущен")

async def on_shutdown(bot: Bot):
    await db.close()
    await redis_client.aclose()
    logger.info("Бот остановлен и соединения закрыты")

def register_middlewares(dp: Dispatcher):
    setup_middlewares(dp)

def register_handlers(dp: Dispatcher):
    dp.include_router(payments.router)
    dp.include_router(onboarding.router)
    dp.include_router(user.router)

async def main():
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = RedisStorage(redis_client)
    dp = Dispatcher(storage=storage)

    register_middlewares(dp)
    register_handlers(dp)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        await dp.start_polling(bot)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка бота...")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f"Ошибка при запуске: {e}")
