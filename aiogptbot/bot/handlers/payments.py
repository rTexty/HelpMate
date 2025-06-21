from aiogram import Router, F
from aiogram.types import Message, PreCheckoutQuery, SuccessfulPayment, LabeledPrice, ShippingOption, ShippingQuery
from aiogram.filters import Command
from ..db.postgres import db
from ..config import settings
from loguru import logger
from datetime import datetime, timedelta
import httpx
import asyncio
from aiogram import Bot
from aiogptbot.bot.services.payment_service import create_cryptocloud_invoice

router = Router()

# --- Telegram Payments ---

@router.message(Command("buy_premium"))
async def buy_premium(message: Message):
    row = await db.fetchrow("SELECT value FROM prices WHERE name='premium_month'")
    if not row:
        await message.answer("Стоимость подписки не установлена. Обратитесь к администратору.")
        return
    price = int(row['value'])
    prices = [LabeledPrice(label="Premium подписка на 1 месяц", amount=price * 100)]
    await message.answer_invoice(
        title="Premium подписка",
        description="Неограниченный доступ к AI-боту на 1 месяц.",
        provider_token=settings.TELEGRAM_PAYMENTS_TOKEN,
        currency="RUB",
        prices=prices,
        start_parameter="premium-subscription",
        payload=str(message.from_user.id)
    )

@router.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def successful_payment(message: Message):
    user_id = message.from_user.id
    user_row = await db.fetchrow("SELECT id FROM users WHERE telegram_id=$1", user_id)
    if not user_row:
        await message.answer("Пользователь не найден в базе. Попробуйте позже.")
        return
    real_user_id = user_row["id"]
    amount = message.successful_payment.total_amount / 100
    currency = message.successful_payment.currency
    await db.execute(
        "INSERT INTO payments (user_id, amount, currency, payment_method, status, created_at) VALUES ($1, $2, $3, 'telegram', 'success', $4)",
        real_user_id, amount, currency, datetime.now()
    )
    # Обновляем подписку
    until = datetime.now() + timedelta(days=30)
    await db.execute(
        "UPDATE users SET status='premium', subscription_until=$1 WHERE telegram_id=$2",
        until, user_id
    )
    await db.execute(
        "INSERT INTO subscriptions (user_id, type, start_date, end_date, is_active) VALUES ($1, 'premium', $2, $3, TRUE)",
        real_user_id, datetime.now(), until
    )
    await message.answer("Спасибо за оплату! Ваша подписка активирована на 1 месяц.")
    logger.info(f"User {user_id} оплатил подписку через Telegram Payments.")

# --- Stripe/ЮKassa (заготовка) ---
@router.message(Command("buy_premium_stripe"))
async def buy_premium_stripe(message: Message):
    await message.answer("Для оплаты через Stripe/ЮKassa обратитесь к администратору или используйте Telegram Payments.")

# --- CryptoCloud ---
@router.message(Command("buy_premium_crypto"))
async def buy_premium_crypto(message: Message):
    user_id = message.from_user.id
    result, error = await create_cryptocloud_invoice(user_id)
    if error:
        await message.answer(error)
        return
    await message.answer(f"Оплатите по ссылке (криптовалюта):\n{result['url']}\n\nПосле оплаты подписка будет активирована в течение нескольких минут.")
