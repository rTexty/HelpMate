import asyncio
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
from aiogram.enums import ParseMode
from loguru import logger

from ..bot.config import settings
from ..bot.db.postgres import db
from ..bot.db.redis_client import redis_client
from ..bot.logging_config import logger
from .handlers import router as admin_router

# Проверка переменных окружения
REQUIRED_ENV = [getattr(settings, 'ADMIN_BOT_TOKEN', None), settings.OPENAI_API_KEY, settings.POSTGRES_DSN, settings.REDIS_DSN]
if not all(REQUIRED_ENV):
    logger.error("Не все переменные окружения заданы. Проверьте .env файл (ADMIN_BOT_TOKEN и др.)")
    sys.exit(1)

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="get_prompt", description="Текущий промпт"),
        BotCommand(command="set_prompt", description="Изменить промпт"),
        BotCommand(command="history_prompt", description="История промптов"),
        BotCommand(command="download_csv", description="Выгрузить базу"),
        BotCommand(command="find_user", description="Найти пользователя"),
        BotCommand(command="ban_user", description="Заблокировать пользователя"),
        BotCommand(command="unban_user", description="Разблокировать пользователя"),
        BotCommand(command="test_prompt", description="Тестовый запрос к GPT"),
        BotCommand(command="restart_bot", description="Перезапуск бота"),
        BotCommand(command="mailing", description="Рассылка"),
        BotCommand(command="stats", description="Статистика")
    ]
    await bot.set_my_commands(commands)

async def on_startup(bot: Bot):
    logger.info("Админ-бот запущен")
    await set_commands(bot)
    await db.connect()
    logger.info("Подключение к PostgreSQL установлено")
    try:
        await redis_client.ping()
        logger.info("Подключение к Redis установлено")
    except Exception as e:
        logger.error(f"Ошибка подключения к Redis: {e}")
        sys.exit(1)

async def on_shutdown(bot: Bot):
    await db.close()
    await redis_client.aclose()
    logger.info("Бот остановлен и соединения закрыты")

def register_handlers(dp: Dispatcher):
    dp.include_router(admin_router)

async def main():
    bot = Bot(token=getattr(settings, 'ADMIN_BOT_TOKEN', ''), parse_mode=ParseMode.HTML)
    storage = RedisStorage(redis_client)
    dp = Dispatcher(storage=storage)

    register_handlers(dp)

    try:
        await on_startup(bot)
        await dp.start_polling(bot)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка админ-бота...")
    finally:
        await on_shutdown(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f"Ошибка при запуске: {e}") 