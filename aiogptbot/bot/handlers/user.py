from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.markdown import hbold
from aiogram.utils.chat_action import ChatActionSender
from aiogram.enums import ParseMode
from datetime import datetime, timedelta
from ..filters import SadEmotionFilter, PremiumFilter
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
from .onboarding import start_onboarding

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot, state: FSMContext):
    if not message.from_user:
        return
    
    user_id = message.from_user.id
    logger.info(f"--- /start command initiated by user {user_id} ---")
    
    current_state = await state.get_state()
    logger.info(f"User {user_id}: Current state is '{current_state}'. Clearing state.")
    await state.clear() 

    logger.info(f"User {user_id}: Fetching user from DB...")
    user = await db.fetchrow("SELECT * FROM users WHERE telegram_id=$1", user_id)

    # Case 1: New user
    if not user:
        logger.info(f"User {user_id}: Not found in DB. This is a new user.")
        await db.execute(
            "INSERT INTO users (telegram_id, username, full_name, created_at) VALUES ($1, $2, $3, $4)",
            user_id, message.from_user.username, message.from_user.full_name, datetime.now()
        )
        logger.info(f"User {user_id}: DB entry created. Starting onboarding...")
        await start_onboarding(message, state, bot)
        return

    # Case 2: Existing user who hasn't completed onboarding
    onboarding_completed_raw = user.get('onboarding_completed')
    logger.info(f"User {user_id}: Found in DB. Raw 'onboarding_completed' value is '{onboarding_completed_raw}' (type: {type(onboarding_completed_raw)})")
    
    onboarding_completed = bool(onboarding_completed_raw)

    logger.info(f"User {user_id}: Interpreted 'onboarding_completed' as: {onboarding_completed}")
    if not onboarding_completed:
        logger.info(f"User {user_id}: Onboarding not complete. Starting onboarding...")
        await start_onboarding(message, state, bot)
        return

    # Case 3: Existing user who has completed onboarding
    logger.info(f"User {user_id}: Onboarding already completed. Sending welcome back message.")
    async with ChatActionSender(bot=bot, chat_id=message.chat.id):
        await asyncio.sleep(1.0)
        
        welcome_message_row = await db.fetchrow("SELECT value FROM text_settings WHERE key='welcome_message'")
        preferred_name = user.get('preferred_name') or user.get('full_name') or "пользователь"

        if welcome_message_row and welcome_message_row['value']:
            welcome_text = welcome_message_row['value'].replace("{name}", preferred_name)
        else:
             welcome_text = (
                f"<b>С возвращением, {preferred_name}!</b>\n\n"
                "Как твои дела? Что-то случилось? Опишите вашу проблему, и мы вместе найдем решение."
            )
            
        await message.answer(welcome_text, parse_mode=ParseMode.HTML)

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
    name = user.get('preferred_name') or user.get('full_name') or user.get('username') or "Не указано"
    
    sub_text = f"до {sub_until.strftime('%d.%m.%Y')}" if sub_until else "нет"
    await message.answer(
        f"{hbold('Профиль')}\n"
        f"Имя: {name}\n"
        f"Статус: {status}\n"
        f"Подписка: {sub_text}\n"
        f"Сообщений сегодня: {daily_count}/5 (для demo)"
    )

@router.message(F.text)
async def dialog_handler(message: Message, bot: Bot, state: FSMContext):
    if not message.from_user or not message.text:
        return

    # Проверяем, не находится ли пользователь в каком-либо состоянии FSM
    current_state = await state.get_state()
    if current_state is not None:
        logger.debug(f"dialog_handler: User {message.from_user.id} is in state {current_state}, ignoring message.")
        return

    user_id = message.from_user.id
    logger.info(f"--- dialog_handler triggered for user {user_id} in state: {current_state} ---")
    
    user = await db.fetchrow("SELECT * FROM users WHERE telegram_id=$1", user_id)
    if not user:
        await message.answer("Профиль не найден. Напишите /start.")
        return

    if not user['onboarding_completed']:
        await message.answer("Пожалуйста, сначала завершите короткий опрос, чтобы мы могли познакомиться. Нажмите /start")
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
    
    # Добавляем данные о пользователе в системный промпт
    user_info = f"Информация о пользователе: Имя - {user.get('preferred_name', 'Не указано')}, Возраст - {user.get('age', 'Не указан')}, Пол - {user.get('gender', 'Не указан')}."
    system_prompt = f"{system_prompt}\n{user_info}"

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
