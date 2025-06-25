from typing import Optional
from ..db.postgres import db
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from loguru import logger
from datetime import datetime, timedelta
from ..config import settings
import asyncio

ADMIN_IDS = [int(x) for x in settings.ADMIN_IDS.split(',') if x]

async def get_user_ids(segment: str):
    if segment == 'all':
        rows = await db.fetch("SELECT telegram_id FROM users WHERE is_banned=FALSE")
    elif segment == 'subscribers':
        rows = await db.fetch("SELECT telegram_id FROM users WHERE status='premium' AND is_banned=FALSE")
    elif segment == 'active_7d':
        rows = await db.fetch("SELECT telegram_id FROM users WHERE last_activity > $1 AND is_banned=FALSE", datetime.now() - timedelta(days=7))
    else:
        rows = []
    # Исключаем админов
    return [r['telegram_id'] for r in rows if r['telegram_id'] not in ADMIN_IDS]

async def send_mailing(
    bot: Bot,
    text: str,
    segment: str = 'all',
    button_text: Optional[str] = None,
    button_url: Optional[str] = None
):
    user_ids = await get_user_ids(segment)
    markup = None
    if button_text and button_url:
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=button_text, url=button_url)]])
    sent, failed = 0, 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text, reply_markup=markup)
            sent += 1
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение {uid}: {e}")
            failed += 1
    await db.execute(
        "INSERT INTO mailings (text, button_text, button_url, segment, created_at, sent) VALUES ($1, $2, $3, $4, $5, TRUE)",
        text, button_text, button_url, segment, datetime.now()
    )
    logger.info(f"Рассылка завершена: отправлено {sent}, ошибок {failed}")
    return sent, failed

async def poll_pending_mailings(bot: Bot):
    """
    Запускать как отдельную задачу. Опрашивает БД на наличие неотправленных
    рассылок и отправляет их согласно сегменту.
    """
    await asyncio.sleep(10) # Начальная задержка перед первым запуском
    while True:
        mailings = await db.fetch("SELECT * FROM mailings WHERE sent=FALSE ORDER BY created_at ASC")
        for mailing in mailings:
            logger.info(f"Начинается рассылка {mailing['id']} для сегмента {mailing['segment']}")
            
            user_ids = await get_user_ids(mailing['segment'])
            
            markup = None
            if mailing['button_text'] and mailing['button_url']:
                markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=mailing['button_text'], url=mailing['button_url'])]])
            
            sent, failed = 0, 0
            for uid in user_ids:
                try:
                    await bot.send_message(uid, mailing['text'], reply_markup=markup)
                    sent += 1
                    await asyncio.sleep(0.1) # небольшая задержка между отправками
                except Exception as e:
                    logger.warning(f"Не удалось отправить сообщение {uid} в рамках рассылки {mailing['id']}: {e}")
                    failed += 1
            
            await db.execute("UPDATE mailings SET sent=TRUE WHERE id=$1", mailing['id'])
            logger.info(f"Рассылка {mailing['id']} завершена: отправлено {sent}, ошибок {failed}")
        
        await asyncio.sleep(60) # Пауза между проверками
