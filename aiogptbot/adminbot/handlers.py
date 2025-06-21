from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.markdown import hbold
from datetime import datetime, timedelta
from .filters import AdminFilter
from ..bot.db.postgres import db
from ..bot.services.openai_service import ask_gpt
from ..bot.services.mailing_service import send_mailing
from ..bot.utils.csv_export import export_users_csv
from ..bot.config import settings
from aiogram import Bot
import io
import re
import tempfile
import os

# --- FSM ---
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

class PromptStates(StatesGroup):
    waiting_for_prompt = State()
    waiting_for_mailing = State()
    waiting_for_test_prompt = State()

class PriceStates(StatesGroup):
    waiting_for_price = State()

router = Router()

# --- Промпты ---
@router.message(AdminFilter(), Command("get_prompt"))
async def get_prompt(message: Message):
    prompt = await db.fetchrow("SELECT text FROM prompts WHERE is_active=TRUE ORDER BY id DESC LIMIT 1")
    if prompt:
        await message.answer(f"Текущий промпт:\n\n{prompt['text']}")
    else:
        await message.answer("Промпт не найден.")

@router.message(AdminFilter(), Command("set_prompt"))
async def set_prompt(message: Message, state: FSMContext):
    await message.answer("Введите новый системный промпт:")
    await state.set_state(PromptStates.waiting_for_prompt)

@router.message(AdminFilter(), PromptStates.waiting_for_prompt)
async def save_prompt(message: Message, state: FSMContext):
    text = message.text
    await db.execute("UPDATE prompts SET is_active=FALSE")
    await db.execute("INSERT INTO prompts (text, is_active) VALUES ($1, TRUE)", text)
    await message.answer("Промпт обновлён и активирован.")
    await state.clear()

@router.message(AdminFilter(), Command("history_prompt"))
async def history_prompt(message: Message):
    rows = await db.fetch("SELECT id, text, created_at FROM prompts ORDER BY id DESC LIMIT 5")
    if not rows:
        await message.answer("История промптов пуста.")
        return
    text = "\n\n".join([f"#{r['id']} ({r['created_at'].strftime('%d.%m.%Y %H:%M')}):\n{r['text']}" for r in rows])
    await message.answer(f"Последние 5 версий промпта:\n\n{text}")

@router.message(AdminFilter(), F.text.regexp(r"^/restore_prompt_(\\d+)$"))
async def restore_prompt(message: Message):
    match = re.match(r"/restore_prompt_(\\d+)", message.text or "")
    if not match:
        await message.answer("Неверная команда.")
        return
    prompt_id = int(match.group(1))
    row = await db.fetchrow("SELECT text FROM prompts WHERE id=$1", prompt_id)
    if not row:
        await message.answer("Промпт не найден.")
        return
    await db.execute("UPDATE prompts SET is_active=FALSE")
    await db.execute("INSERT INTO prompts (text, is_active) VALUES ($1, TRUE)", row['text'])
    await message.answer("Промпт восстановлен и активирован.")

# --- Рассылка ---
@router.message(AdminFilter(), Command("mailing"))
async def mailing_start(message: Message, state: FSMContext):
    await message.answer(
        "Введите текст рассылки.\n\nЕсли хотите добавить кнопку, напишите на новой строке: Кнопка:Текст|https://url.ru\n\nПример:\nВсем привет!\nКнопка:Подробнее|https://site.ru"
    )
    await state.set_state(PromptStates.waiting_for_mailing)

@router.message(AdminFilter(), PromptStates.waiting_for_mailing)
async def process_mailing(message: Message, state: FSMContext):
    text = message.text or ""
    # Парсим кнопку, если есть
    button_text = button_url = None
    lines = text.splitlines()
    main_text = []
    for line in lines:
        if line.startswith("Кнопка:"):
            btn = line.replace("Кнопка:", "", 1).strip()
            if "|" in btn:
                button_text, button_url = btn.split("|", 1)
                button_text = button_text.strip()
                button_url = button_url.strip()
        else:
            main_text.append(line)
    mailing_text = "\n".join(main_text).strip()
    if not mailing_text:
        await message.answer("Текст рассылки не может быть пустым.")
        return
    # Запрашиваем сегмент
    await message.answer(
        "Выберите сегмент для рассылки:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Все", callback_data="mailing_segment_all")],
                [InlineKeyboardButton(text="Подписчики", callback_data="mailing_segment_subscribers")],
                [InlineKeyboardButton(text="Активные 7 дней", callback_data="mailing_segment_active_7d")],
            ]
        )
    )
    await state.update_data(mailing_text=mailing_text, button_text=button_text, button_url=button_url)
    await state.set_state("waiting_for_mailing_segment")

@router.callback_query(AdminFilter(), F.data.startswith("mailing_segment_"))
async def mailing_segment_callback(call, state: FSMContext):
    data = await state.get_data()
    mailing_text = data.get("mailing_text") or ""
    button_text = data.get("button_text")
    button_url = data.get("button_url")
    segment = call.data.replace("mailing_segment_", "")
    # Сохраняем рассылку в БД (отправка будет выполнена основным ботом)
    await db.execute(
        "INSERT INTO mailings (text, button_text, button_url, segment, created_at, sent) VALUES ($1, $2, $3, $4, $5, FALSE)",
        mailing_text, button_text, button_url, segment, datetime.now()
    )
    await call.message.answer(f"Рассылка поставлена в очередь и будет отправлена пользователям основного бота по сегменту: {segment}.")
    await state.clear()
    await call.answer()

# --- Статистика ---
@router.message(AdminFilter(), Command("stats"))
async def stats(message: Message):
    row = await db.fetchrow("SELECT COUNT(*) AS count FROM users")
    total = row["count"] if row else 0
    row = await db.fetchrow("SELECT COUNT(*) AS count FROM users WHERE status='premium'")
    premium = row["count"] if row else 0
    row = await db.fetchrow("SELECT COUNT(*) AS count FROM users WHERE last_activity > $1", datetime.now() - timedelta(days=7))
    active_7d = row["count"] if row else 0
    row = await db.fetchrow("SELECT AVG(cnt) AS avg_cnt FROM (SELECT COUNT(*) as cnt FROM messages GROUP BY user_id) t")
    avg_dialog = row["avg_cnt"] if row else 0
    row = await db.fetchrow("SELECT COUNT(*) AS count FROM payments WHERE created_at::date = CURRENT_DATE AND status='success'")
    payments_today = row["count"] if row else 0
    await message.answer(
        f"{hbold('Статистика')}\n"
        f"Всего пользователей: {total}\n"
        f"Подписчиков: {premium}\n"
        f"Средняя длина диалога: {round(avg_dialog, 1) if avg_dialog is not None else 0}\n"
        f"Активные за 7 дней: {active_7d}\n"
        f"Оплаты сегодня: {payments_today}"
    )

@router.message(AdminFilter(), Command("download_csv"))
async def download_csv(message: Message):
    csv_bytes = await export_users_csv()
    # Сохраняем во временный файл для передачи через FSInputFile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(csv_bytes)
        tmp_path = tmp.name
    try:
        file = FSInputFile(tmp_path, filename="users.csv")
        await message.answer_document(file)
    finally:
        os.remove(tmp_path)

# --- Пользователи ---
@router.message(AdminFilter(), Command("find_user"))
async def find_user(message: Message, command: CommandObject):
    arg = command.args
    if not arg:
        await message.answer("Укажите username или ID: /find_user @username или /find_user 123456")
        return
    if arg.startswith('@'):
        user = await db.fetchrow("SELECT * FROM users WHERE username=$1", arg[1:])
    else:
        try:
            uid = int(arg)
            user = await db.fetchrow("SELECT * FROM users WHERE telegram_id=$1", uid)
        except Exception:
            user = None
    if not user:
        await message.answer("Пользователь не найден.")
        return
    last = user['last_activity'].strftime('%d.%m.%Y') if user['last_activity'] else 'нет данных'
    sub = user['subscription_until'].strftime('%d.%m.%Y') if user['subscription_until'] else 'нет'
    await message.answer(
        f"@{user['username']}\n"
        f"Последняя активность: {last}\n"
        f"Подписка: {'активна до ' + sub if user['status']=='premium' else user['status']}"
    )

@router.message(AdminFilter(), Command("ban_user"))
async def ban_user(message: Message, command: CommandObject):
    arg = command.args
    if not arg:
        await message.answer("Укажите username: /ban_user @username")
        return
    username = arg.lstrip('@')
    user = await db.fetchrow("SELECT * FROM users WHERE username=$1", username)
    if not user:
        await message.answer("Пользователь с таким username не найден.")
        return
    await db.execute("UPDATE users SET is_banned=TRUE WHERE username=$1", username)
    await message.answer(f"Пользователь @{username} заблокирован.")

@router.message(AdminFilter(), Command("unban_user"))
async def unban_user(message: Message, command: CommandObject):
    arg = command.args
    if not arg:
        await message.answer("Укажите username: /unban_user @username")
        return
    username = arg.lstrip('@')
    user = await db.fetchrow("SELECT * FROM users WHERE username=$1", username)
    if not user:
        await message.answer("Пользователь с таким username не найден.")
        return
    await db.execute("UPDATE users SET is_banned=FALSE WHERE username=$1", username)
    await message.answer(f"Пользователь @{username} разблокирован.")

# --- Тестовый промпт ---
@router.message(AdminFilter(), Command("test_prompt"))
async def test_prompt(message: Message, state: FSMContext):
    await message.answer("Введите тестовый запрос к GPT:")
    await state.set_state(PromptStates.waiting_for_test_prompt)

@router.message(AdminFilter(), PromptStates.waiting_for_test_prompt)
async def process_test_prompt(message: Message, state: FSMContext):
    user_input = message.text
    # Получаем текущий активный промпт
    prompt_row = await db.fetchrow("SELECT text FROM prompts WHERE is_active=TRUE ORDER BY id DESC LIMIT 1")
    system_prompt = prompt_row["text"] if prompt_row else ""
    # Отправляем запрос к OpenAI
    reply = await ask_gpt(system_prompt, history=[{"role": "user", "content": user_input}])
    await message.answer(f"Ответ GPT-4o:\n\n{reply}")
    await state.clear()

# --- Рестарт ---
@router.message(AdminFilter(), Command("restart_bot"))
async def restart_bot(message: Message):
    await message.answer("Основной бот будет перезапущен.")
    import os
    os.system("./restart_userbot.sh")

@router.message(AdminFilter(), Command("get_price"))
async def get_price(message: Message):
    row = await db.fetchrow("SELECT value FROM prices WHERE name='premium_month'")
    if row:
        await message.answer(f"Текущая стоимость подписки: {row['value']} руб.")
    else:
        await message.answer("Стоимость подписки не установлена.")

@router.message(AdminFilter(), Command("set_price"))
async def set_price(message: Message, state: FSMContext):
    await message.answer("Введите новую стоимость подписки в рублях (целое число):")
    await state.set_state(PriceStates.waiting_for_price)

@router.message(AdminFilter(), PriceStates.waiting_for_price)
async def save_price(message: Message, state: FSMContext):
    try:
        price = int(message.text)
        if price <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введите корректное положительное число!")
        return
    await db.execute(
        "INSERT INTO prices (name, value, updated_at) VALUES ('premium_month', $1, NOW()) ON CONFLICT (name) DO UPDATE SET value=$1, updated_at=NOW()",
        price
    )
    await message.answer(f"Стоимость подписки обновлена: {price} руб.")
    await state.clear()