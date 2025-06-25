from aiogram import BaseMiddleware
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from loguru import logger
from .services.subscription_service import check_user_subscription, increment_message_count
from .services.emotion_service import filter_bad_words, detect_emotion
from .db.postgres import db
import time
from .config import settings

class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # if isinstance(event, Message) and event.from_user is not None:
        #     user = event.from_user
        #     logger.info(f"User {user.id} (@{user.username}): {event.text}")
        return await handler(event, data)

class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not isinstance(event, Message) or event.from_user is None or not event.text:
            return await handler(event, data)

        user_id = event.from_user.id
        # Игнорируем команды, чтобы они работали всегда
        if event.text.startswith('/'):
            logger.debug(f"User {user_id} sent a command, skipping subscription check.")
            return await handler(event, data)

        user = await db.fetchrow("SELECT * FROM users WHERE telegram_id=$1", user_id)
        if not user:
            logger.info(f"New user {user_id}, creating DB entry.")
            await db.execute("INSERT INTO users (telegram_id, username, full_name) VALUES ($1, $2, $3)",
                             user_id, event.from_user.username, event.from_user.full_name)
            user = await db.fetchrow("SELECT * FROM users WHERE telegram_id=$1", user_id)
        
        logger.debug(f"[SubCheck] User {user_id}: Initial status is '{user['status']}', message count is {user['daily_message_count']}.")

        # Если пользователь - админ, пропускаем все проверки
        admin_ids = [int(x) for x in settings.ADMIN_IDS.split(',') if x]
        if user_id in admin_ids:
            logger.debug(f"User {user_id} is an admin. Skipping all checks.")
            return await handler(event, data)

        # Проверка бана
        if user['is_banned']:
            logger.warning(f"[SubCheck] User {user_id} is banned. Blocking.")
            await event.answer(f"Вы заблокированы. Свяжитесь с {settings.ADMIN_USERNAME} для разблокировки.")
            return None

        # Проверка и обновление статуса подписки
        user = await check_user_subscription(user)
        logger.debug(f"[SubCheck] User {user_id}: Status after check_user_subscription is '{user['status']}'.")

        # Проверка лимитов
        limit = 5
        is_limit_reached = user['daily_message_count'] >= limit
        
        if user['status'] in ['demo', 'expired'] and is_limit_reached:
            logger.info(f"[SubCheck] User {user_id} (status: {user['status']}) has reached the daily limit of {limit}. Sending payment prompt.")
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Оплатить через Telegram", callback_data="pay_telegram"),
                        InlineKeyboardButton(text="Оплатить криптой", callback_data="pay_crypto")
                    ]
                ]
            )
            text = "Доступно только 5 сообщений в день. Оформите подписку для неограниченного доступа."
            if user['status'] == 'expired':
                text = "Ваша подписка на бота закончилась. Далее вам доступно 5 сообщений в день.\n\nЛимит сообщений на сегодня исчерпан. Для продления подписки выберите способ оплаты:"

            await event.answer(text, reply_markup=markup)
            return None

        await increment_message_count(user_id)
        logger.debug(f"[SubCheck] User {user_id} message allowed. Incrementing count.")
        return await handler(event, data)

class FilterMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not isinstance(event, Message) or not event.text:
            return await handler(event, data)
        # Фильтрация мата и грубостей
        filtered_text, replaced = filter_bad_words(event.text)
        if replaced:
            await event.answer("Давайте общаться вежливо.")
            event.text = filtered_text
        return await handler(event, data)

class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self, rate_limit=1.0):
        self.rate_limit = rate_limit
        self.last_time = {}

    async def __call__(self, handler, event, data):
        if not isinstance(event, Message) or event.from_user is None:
            return await handler(event, data)
        user_id = event.from_user.id
        now = time.time()
        last = self.last_time.get(user_id, 0)
        if now - last < self.rate_limit:
            await event.answer("Пожалуйста, не флудите.")
            return None
        self.last_time[user_id] = now
        return await handler(event, data)

def setup_middlewares(dp):
    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(AntiFloodMiddleware(rate_limit=1.0))
    dp.message.middleware(SubscriptionMiddleware())
    dp.message.middleware(FilterMiddleware())
