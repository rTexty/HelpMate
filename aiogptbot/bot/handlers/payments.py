from aiogram import Router, F
from aiogram.types import Message, PreCheckoutQuery, SuccessfulPayment, LabeledPrice, ShippingOption, ShippingQuery
from aiogram.filters import Command
from ..db.postgres import db
from ..config import settings
from loguru import logger
from datetime import datetime, timedelta

router = Router()

# --- Telegram Payments ---

PRICES = [LabeledPrice(label="Premium подписка на 1 месяц", amount=49900)]  # 499 руб

@router.message(Command("buy_premium"))
async def buy_premium(message: Message):
    await message.answer_invoice(
        title="Premium подписка",
        description="Неограниченный доступ к AI-боту на 1 месяц.",
        provider_token=settings.BOT_TOKEN,  # Для теста: замените на свой provider_token
        currency="RUB",
        prices=PRICES,
        start_parameter="premium-subscription",
        payload=str(message.from_user.id)
    )

@router.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def successful_payment(message: Message):
    user_id = message.from_user.id
    amount = message.successful_payment.total_amount / 100
    currency = message.successful_payment.currency
    await db.execute(
        "INSERT INTO payments (user_id, amount, currency, payment_method, status, created_at) VALUES ((SELECT id FROM users WHERE telegram_id=$1), $2, $3, 'telegram', 'success', $4)",
        user_id, amount, currency, datetime.now()
    )
    # Обновляем подписку
    until = datetime.now() + timedelta(days=30)
    await db.execute(
        "UPDATE users SET status='premium', subscription_until=$1 WHERE telegram_id=$2",
        until, user_id
    )
    await db.execute(
        "INSERT INTO subscriptions (user_id, type, start_date, end_date, is_active) VALUES ((SELECT id FROM users WHERE telegram_id=$1), 'premium', $2, $3, TRUE)",
        user_id, datetime.now(), until
    )
    await message.answer("Спасибо за оплату! Ваша подписка активирована на 1 месяц.")
    logger.info(f"User {user_id} оплатил подписку через Telegram Payments.")

# --- Stripe/ЮKassa (заготовка) ---
@router.message(Command("buy_premium_stripe"))
async def buy_premium_stripe(message: Message):
    await message.answer("Для оплаты через Stripe/ЮKassa обратитесь к администратору или используйте Telegram Payments.")

# --- Крипта (заготовка) ---
@router.message(Command("buy_premium_crypto"))
async def buy_premium_crypto(message: Message):
    await message.answer("Для оплаты криптовалютой обратитесь к администратору или используйте Telegram Payments.")
