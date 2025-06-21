from aiogptbot.bot.db.postgres import db
from aiogptbot.bot.config import settings
from aiogram.types import LabeledPrice
from datetime import datetime, timedelta
import httpx
from aiogram import Bot
from loguru import logger
import asyncio


async def create_telegram_invoice(user_id):
    row = await db.fetchrow("SELECT value FROM prices WHERE name='premium_month'")
    if not row:
        return None, "Стоимость подписки не установлена. Обратитесь к администратору."
    price = int(row['value'])
    prices = [LabeledPrice(label="Premium подписка на 1 месяц", amount=price * 100)]
    return {
        "user_id": user_id,
        "title": "Premium подписка",
        "description": "Неограниченный доступ к AI-боту на 1 месяц.",
        "provider_token": settings.TELEGRAM_PAYMENTS_TOKEN,
        "currency": "RUB",
        "prices": prices,
        "start_parameter": "premium-subscription",
        "payload": str(user_id)
    }, None

async def create_cryptocloud_invoice(user_id):
    row = await db.fetchrow("SELECT value FROM prices WHERE name='premium_month'")
    if not row:
        return None, "Стоимость подписки не установлена. Обратитесь к администратору."
    price = int(row['value'])
    api_key = settings.CRYPTOCLOUD_API_KEY
    payload = {
        "shop_id": settings.CRYPTOCLOUD_SHOP_ID,
        "amount": price,
        "currency": "RUB",
        "order_id": str(user_id),
        "desc": "Premium подписка на 1 месяц"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.cryptocloud.plus/v2/invoice/create",
            headers={"Authorization": f"Token {api_key}"},
            json=payload
        )
        data = resp.json()
        if data.get("status") == "success":
            url = data["result"]["link"]
            invoice_id = data["result"]["uuid"]
            user_row = await db.fetchrow("SELECT id FROM users WHERE telegram_id=$1", user_id)
            if not user_row:
                return None, "Пользователь не найден в базе. Попробуйте позже."
            real_user_id = user_row["id"]
            await db.execute(
                "INSERT INTO payments (user_id, amount, currency, payment_method, status, created_at, invoice_id) VALUES ($1, $2, $3, 'cryptocloud', 'pending', $4, $5)",
                real_user_id, price, "RUB", datetime.now(), invoice_id
            )
            return {"url": url, "invoice_id": invoice_id}, None
        else:
            return None, "Ошибка при создании ссылки на оплату. Попробуйте позже."

async def poll_cryptocloud_payments():
    """
    Запускать как отдельную задачу при старте бота.
    Проверяет все pending-платежи CryptoCloud раз в 20 секунд и активирует подписку при оплате.
    """
    bot = Bot(token=settings.BOT_TOKEN)
    while True:
        payments = await db.fetch("SELECT * FROM payments WHERE payment_method='cryptocloud' AND status='pending'")
        api_key = settings.CRYPTOCLOUD_API_KEY
        for payment in payments:
            invoice_id = payment['invoice_id']
            user_id = payment['user_id']
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.cryptocloud.plus/v2/invoice/merchant/info",
                    headers={"Authorization": f"Token {api_key}"},
                    json={"uuids": [invoice_id]}
                )
                data = resp.json()
                if (
                    data.get("status") == "success"
                    and data.get("result")
                    and isinstance(data["result"], list)
                    and len(data["result"]) > 0
                    and data["result"][0].get("status") in ["paid", "overpaid"]
                ):
                    # Получаем telegram_id по user_id
                    user_row = await db.fetchrow("SELECT telegram_id FROM users WHERE id=$1", user_id)
                    if not user_row:
                        continue
                    telegram_id = user_row["telegram_id"]
                    until = datetime.now() + timedelta(days=30)
                    await db.execute(
                        "UPDATE users SET status='premium', subscription_until=$1 WHERE telegram_id=$2",
                        until, telegram_id
                    )
                    await db.execute(
                        "INSERT INTO subscriptions (user_id, type, start_date, end_date, is_active) VALUES ($1, 'premium', $2, $3, TRUE)",
                        user_id, datetime.now(), until
                    )
                    updated = await db.execute(
                        "UPDATE payments SET status='success' WHERE id=$1 AND status='pending'",
                        payment['id']
                    )
                    if updated and (updated == 'UPDATE 1' or updated == 'UPDATE 1;'):
                        try:
                            await bot.send_message(telegram_id, "Ваша подписка активирована! Спасибо за оплату через CryptoCloud. Приятного общения с AI-ботом!")
                        except Exception as e:
                            logger.warning(f"Не удалось отправить уведомление пользователю {telegram_id}: {e}")
        await asyncio.sleep(20) 