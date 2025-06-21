import asyncio
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
from aiogram.enums import ParseMode
from loguru import logger

from .config import settings
from .db.postgres import db
from .db.redis_client import redis_client
from .logging_config import logger
from .handlers import user, payments
from .services.mailing_service import send_mailing

# Проверка переменных окружения
REQUIRED_ENV = [settings.BOT_TOKEN, settings.OPENAI_API_KEY, settings.POSTGRES_DSN, settings.REDIS_DSN]
if not all(REQUIRED_ENV):
    logger.error("Не все переменные окружения заданы. Проверьте .env файл.")
    sys.exit(1)

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать диалог"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="profile", description="Профиль и подписка")
    ]
    await bot.set_my_commands(commands)

async def on_startup(bot: Bot):
    logger.info("Бот запущен")
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
    await redis_client.close()
    logger.info("Бот остановлен и соединения закрыты")

def register_middlewares(dp: Dispatcher):
    # Здесь будут middlewares: логирование, антифлуд, подписка, фильтрация и т.д.
    pass

def register_handlers(dp: Dispatcher):
    dp.include_router(user.router)
    dp.include_router(payments.router)

async def process_pending_mailings(bot):
    while True:
        # Получаем неотправленные рассылки
        mailings = await db.fetch("SELECT * FROM mailings WHERE sent=FALSE ORDER BY created_at ASC")
        for mailing in mailings:
            # Определяем пользователей, которые писали основному боту
            rows = await db.fetch("SELECT DISTINCT telegram_id FROM users WHERE id IN (SELECT user_id FROM messages)")
            user_ids = [r['telegram_id'] for r in rows]
            # Исключаем админов
            ADMIN_IDS = [int(x) for x in settings.ADMIN_IDS.split(',') if x]
            user_ids = [uid for uid in user_ids if uid not in ADMIN_IDS]
            # Формируем кнопку
            markup = None
            if mailing['button_text'] and mailing['button_url']:
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=mailing['button_text'], url=mailing['button_url'])]])
            sent, failed = 0, 0
            for uid in user_ids:
                try:
                    await bot.send_message(uid, mailing['text'], reply_markup=markup)
                    sent += 1
                except Exception as e:
                    logger.warning(f"Не удалось отправить сообщение {uid}: {e}")
                    failed += 1
            await db.execute("UPDATE mailings SET sent=TRUE WHERE id=$1", mailing['id'])
            logger.info(f"Рассылка {mailing['id']} завершена: отправлено {sent}, ошибок {failed}")
        await asyncio.sleep(20)

async def main():
    bot = Bot(token=settings.BOT_TOKEN, parse_mode=ParseMode.HTML)
    storage = RedisStorage(redis_client)
    dp = Dispatcher(storage=storage)

    register_middlewares(dp)
    register_handlers(dp)


    try:
        await on_startup(bot)  # Сначала подключаем БД и Redis
        asyncio.create_task(process_pending_mailings(bot))
        await dp.start_polling(bot)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка бота...")
    finally:
        await on_shutdown(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f"Ошибка при запуске: {e}")
