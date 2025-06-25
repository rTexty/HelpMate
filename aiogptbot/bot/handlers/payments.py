from aiogram import Router, F, Bot
from aiogram.types import Message, PreCheckoutQuery, CallbackQuery
from aiogram.filters import Command
from ..db.postgres import db
from ..config import settings
from loguru import logger
from datetime import datetime, timedelta
from aiogptbot.bot.services.payment_service import create_telegram_invoice, create_cryptocloud_invoice, record_successful_telegram_payment

router = Router()

# --- Внутренние функции для отправки инвойсов ---

async def _send_telegram_invoice(user_id: int, bot: Bot, message: Message | CallbackQuery):
    """Создает и отправляет инвойс Telegram Stars."""
    invoice_data, error = await create_telegram_invoice(user_id)
    if error or not invoice_data:
        answer_text = error or "Ошибка при создании инвойса. Попробуйте позже."
        if isinstance(message, Message):
            await message.answer(answer_text)
        else:
            await bot.send_message(user_id, answer_text)
        return

    await bot.send_invoice(
        chat_id=user_id,
        title=invoice_data["title"],
        description=invoice_data["description"],
        payload=invoice_data["payload"],
        provider_token="",  # Пустой для Stars
        currency="XTR",
        prices=invoice_data["prices"],
        start_parameter=invoice_data["start_parameter"]
    )

async def _send_cryptocloud_invoice(user_id: int, bot: Bot, message: Message | CallbackQuery):
    """Создает и отправляет инвойс CryptoCloud."""
    result, error = await create_cryptocloud_invoice(user_id)
    if error:
        answer_text = error
    elif result and "url" in result:
        answer_text = f"Оплатите по ссылке (криптовалюта):\n{result['url']}\n\nПосле оплаты подписка будет активирована в течение нескольких минут."
    else:
        answer_text = "Ошибка при создании ссылки на оплату. Попробуйте позже."

    if isinstance(message, Message):
        await message.answer(answer_text)
    else:
        await bot.send_message(user_id, answer_text)


# --- Обработчики команд ---

@router.message(Command("buy_premium"))
async def buy_premium_cmd(message: Message, bot: Bot):
    if not message.from_user: return
    await _send_telegram_invoice(message.from_user.id, bot, message)

@router.message(Command("buy_premium_crypto"))
async def buy_premium_crypto_cmd(message: Message, bot: Bot):
    if not message.from_user: return
    await _send_cryptocloud_invoice(message.from_user.id, bot, message)

# --- Обработчики колбэков (когда пользователь нажимает кнопку в сообщении о лимите) ---

@router.callback_query(F.data == "pay_telegram")
async def pay_telegram_callback(call: CallbackQuery, bot: Bot):
    await _send_telegram_invoice(call.from_user.id, bot, call)
    await call.answer()

@router.callback_query(F.data == "pay_crypto")
async def pay_crypto_callback(call: CallbackQuery, bot: Bot):
    await _send_cryptocloud_invoice(call.from_user.id, bot, call)
    await call.answer()

# --- Обработка успешных платежей ---

@router.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: PreCheckoutQuery):
    if not pre_checkout_query.from_user:
        logger.error("[PreCheckout] Received query without user info.")
        await pre_checkout_query.answer(ok=False, error_message="Не удалось определить пользователя.")
        return
    user_id = pre_checkout_query.from_user.id
    logger.info(f"[PreCheckout] Received for user {user_id} with payload {pre_checkout_query.invoice_payload}")

    user = await db.fetchrow("SELECT status, subscription_until FROM users WHERE telegram_id=$1", user_id)
    now = datetime.now()

    if user and user['status'] == 'premium' and user['subscription_until'] and user['subscription_until'] > now:
        error_message = "У вас уже активна подписка! Дождитесь окончания текущей или напишите в поддержку."
        logger.warning(f"[PreCheckout] User {user_id} already has an active subscription. Rejecting.")
        await pre_checkout_query.answer(ok=False, error_message=error_message)
        return

    logger.info(f"[PreCheckout] Approving for user {user_id}.")
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    if not message.from_user or not message.successful_payment:
        logger.error("[SuccessfulPayment] Received message without user or payment info.")
        return

    user_id = message.from_user.id
    payment_info = message.successful_payment
    logger.info(f"[SuccessfulPayment] Received for user {user_id}. Amount: {payment_info.total_amount} {payment_info.currency}. Charge ID: {payment_info.telegram_payment_charge_id}")

    user = await db.fetchrow("SELECT id, status, subscription_until FROM users WHERE telegram_id=$1", user_id)
    if not user:
        logger.error(f"[SuccessfulPayment] User {user_id} not found in DB!")
        return

    now = datetime.now()
    if user['status'] == 'premium' and user['subscription_until'] and user['subscription_until'] > now:
        logger.warning(f"[SuccessfulPayment] User {user_id} already has an active subscription. No changes made.")
        await message.answer("Спасибо за оплату! У вас уже была активная подписка.")
        return

    real_user_id = user["id"]
    until = now + timedelta(days=30)
    
    logger.info(f"[SuccessfulPayment] Updating user {user_id} (DB ID: {real_user_id}) to premium until {until}.")
    
    update_result = await db.execute(
        "UPDATE users SET status='premium', subscription_until=$1, daily_message_count=0 WHERE telegram_id=$2",
        until, user_id
    )

    logger.info(f"[SuccessfulPayment] User {user_id} update status: {update_result}. Now recording payment.")

    await record_successful_telegram_payment(
        user_id=real_user_id,
        amount=payment_info.total_amount,
        telegram_payment_charge_id=payment_info.telegram_payment_charge_id
    )
    
    await db.execute(
        "INSERT INTO subscriptions (user_id, type, start_date, end_date, is_active) VALUES ($1, 'premium', $2, $3, TRUE)",
        real_user_id, now, until
    )

    await message.answer("Спасибо за оплату! Ваша подписка активирована на 1 месяц.")
    logger.info(f"[SuccessfulPayment] Successfully activated subscription for user {user_id} until {until}.")
