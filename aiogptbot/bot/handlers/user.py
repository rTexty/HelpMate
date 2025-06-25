from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.markdown import hbold
from aiogram.utils.chat_action import ChatActionSender
from datetime import datetime, timedelta
from ..filters import SadEmotionFilter, BadWordFilter, PremiumFilter
from ..db.postgres import db
from ..db.redis_client import redis_client
from ..services.openai_service import ask_gpt
from ..services.memory_service import get_user_memory, update_user_memory
from ..services.subscription_service import get_user_status, get_daily_limit, get_subscription_info
from loguru import logger
import asyncio
from aiogptbot.bot.config import settings
import httpx
from aiogptbot.bot.services.payment_service import create_telegram_invoice, create_cryptocloud_invoice

router = Router()

bad_word_filter = BadWordFilter()

@router.message(Command("start"))
async def cmd_start(message: Message):
    logger.info(f"START COMMAND")
    if not message.from_user:
        return
    user_id = message.from_user.id
    user = await db.fetchrow("SELECT * FROM users WHERE telegram_id=$1", user_id)
    if not user:
        await db.execute(
            "INSERT INTO users (telegram_id, username, full_name, created_at) VALUES ($1, $2, $3, $4)",
            user_id, message.from_user.username, message.from_user.full_name, datetime.now()
        )
    await message.answer(
        f"{hbold('Добро пожаловать!')}\n\n"
        "Я — ваш AI-собеседник. Нажмите 'Начать диалог', чтобы поговорить.\n"
        "В демо-режиме доступно 5 сообщений в день. Для неограниченного доступа — оформите подписку."
    )

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    if not message.from_user:
        return
    user_id = message.from_user.id
    user = await db.fetchrow("SELECT * FROM users WHERE telegram_id=$1", user_id)
    if not user:
        await message.answer("Профиль не найден. Напишите /start.")
        return
    status = user['status']
    sub_until = user['subscription_until']
    daily_count = user['daily_message_count']
    sub_text = f"до {sub_until.strftime('%d.%m.%Y')}" if sub_until else "нет"
    await message.answer(
        f"{hbold('Профиль')}\n"
        f"Статус: {status}\n"
        f"Подписка: {sub_text}\n"
        f"Сообщений сегодня: {daily_count}/5 (для demo)"
    )

@router.message(F.text)
async def dialog_handler(message: Message, bot: Bot):
    if not message.from_user or not message.text:
        return

    user_id = message.from_user.id
    user = await db.fetchrow("SELECT * FROM users WHERE telegram_id=$1", user_id)
    if not user:
        await message.answer("Профиль не найден. Напишите /start.")
        return

    try:
        await db.execute(
            "INSERT INTO messages (user_id, role, content, created_at) VALUES ($1, $2, $3, $4)",
            user['id'], 'user', message.text, datetime.now()
        )
    except Exception as e:
        logger.error(f"Ошибка при вставке сообщения пользователя: {e}")
        return # Если не удалось сохранить сообщение, не продолжаем

    # 1. Получаем из Redis историю (список) и из Postgres summary (строку)
    memory_data = await get_user_memory(user_id)
    history = memory_data["history"] 
    summary = memory_data["summary"]

    # 2. Добавляем текущее сообщение пользователя в историю
    history.append({"role": "user", "content": message.text})

    # 3. Получаем системный промпт
    prompt_row = await db.fetchrow("SELECT text FROM prompts WHERE is_active=TRUE ORDER BY id DESC LIMIT 1")
    system_prompt = prompt_row['text'] if prompt_row else "Ты дружелюбный AI-собеседник."
    
    # 4. Отправляем запрос к GPT с историей и summary
    text_len = len(message.text)
    delay = 3 if text_len > 100 else 1.5
    async with ChatActionSender(bot=bot, chat_id=message.chat.id):
        await asyncio.sleep(delay)
        gpt_response = await ask_gpt(system_prompt, history, summary)
        await message.answer(gpt_response)

    # 5. Сохраняем сообщение ассистента в БД
    try:
        await db.execute(
            "INSERT INTO messages (user_id, role, content, created_at) VALUES ($1, $2, $3, $4)",
            user['id'], 'assistant', gpt_response, datetime.now()
        )
    except Exception as e:
        logger.error(f"Ошибка при вставке сообщения ассистента: {e}")

    # 6. Обновляем память (историю в Redis, summary в Postgres) и last_activity
    await update_user_memory(user_id, history, gpt_response)
    await db.execute(
        "UPDATE users SET last_activity = $1 WHERE telegram_id = $2",
        datetime.now(), user_id
    )
    logger.info(f"User {user_id} получил ответ от GPT")

@router.callback_query(F.data == "pay_telegram")
async def pay_telegram_callback(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    invoice_data, error = await create_telegram_invoice(user_id)
    if error or not invoice_data:
        await bot.send_message(user_id, error or "Ошибка при создании инвойса. Попробуйте позже.")
        await callback.answer()
        return
    await bot.send_invoice(
        invoice_data["user_id"],
        invoice_data["title"],
        invoice_data["description"],
        invoice_data["payload"],
        invoice_data["provider_token"],
        invoice_data["currency"],
        invoice_data["prices"],
        start_parameter=invoice_data["start_parameter"]
    )
    await callback.answer()

@router.callback_query(F.data == "pay_crypto")
async def pay_crypto_callback(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    result, error = await create_cryptocloud_invoice(user_id)
    if error:
        await bot.send_message(user_id, error)
        await callback.answer()
        return
    if result and "url" in result:
        await bot.send_message(user_id, f"Оплатите по ссылке (криптовалюта):\n{result['url']}\n\nПосле оплаты подписка будет активирована в течение нескольких минут.")
    else:
        await bot.send_message(user_id, "Ошибка при создании ссылки на оплату. Попробуйте позже.")
    await callback.answer()
