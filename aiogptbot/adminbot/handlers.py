from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.markdown import hbold
from aiogram.enums import ParseMode
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

class WelcomeMessageStates(StatesGroup):
    waiting_for_welcome_message = State()

router = Router()

# --- Промпты ---
@router.message(AdminFilter(), Command("get_prompt"))
async def get_prompt(message: Message):
    prompt = await db.fetchrow("SELECT text FROM prompts WHERE is_active=TRUE ORDER BY id DESC LIMIT 1")
    if prompt and prompt['text']:
        full_text = f"Текущий промпт:\n\n{prompt['text']}"
        if len(full_text) > 4096:
            await message.answer("Текущий промпт (слишком длинный, будет отправлен по частям):")
            # Отправляем основной текст по частям
            for i in range(0, len(prompt['text']), 4000):
                await message.answer(prompt['text'][i:i + 4000])
        else:
            await message.answer(full_text)
    else:
        await message.answer("Промпт не найден.")

@router.message(AdminFilter(), Command("set_prompt"))
async def set_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt_parts=[])
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Сохранить промпт")]],
        resize_keyboard=True
    )
    await message.answer(
        "Отправьте текст нового системного промпта. Можно разбить на несколько сообщений. Когда закончите, нажмите кнопку «Сохранить промпт».",
        reply_markup=keyboard
    )
    await state.set_state(PromptStates.waiting_for_prompt)

# Этот обработчик будет накапливать части промпта
@router.message(AdminFilter(), PromptStates.waiting_for_prompt, F.text, ~F.text.startswith('/'), F.text != "Сохранить промпт")
async def accumulate_prompt_parts(message: Message, state: FSMContext):
    data = await state.get_data()
    parts = data.get("prompt_parts", [])
    if message.text:
        parts.append(message.text)
        await state.update_data(prompt_parts=parts)
        # Опционально: можно добавить реакцию, чтобы подтвердить получение части
        # await message.react([types.ReactionTypeEmoji(emoji="👍")])
    else:
        await message.answer("Пожалуйста, отправьте текстовое сообщение.")

# Этот обработчик сохранит полный промпт
@router.message(AdminFilter(), PromptStates.waiting_for_prompt, F.text == "Сохранить промпт")
async def save_full_prompt(message: Message, state: FSMContext):
    data = await state.get_data()
    parts = data.get("prompt_parts", [])
    if not parts:
        await message.answer(
            "Промпт пустой. Отправка отменена. Чтобы ввести промпт заново, используйте /set_prompt.",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return

    text = "\n\n".join(parts)
    await db.execute("UPDATE prompts SET is_active=FALSE")
    await db.execute("INSERT INTO prompts (text, is_active) VALUES ($1, TRUE)", text)
    await message.answer("Промпт обновлён и активирован.", reply_markup=ReplyKeyboardRemove())
    await state.clear()

@router.message(AdminFilter(), Command("history_prompt"))
async def history_prompt(message: Message):
    rows = await db.fetch("SELECT id, text, created_at FROM prompts ORDER BY id DESC LIMIT 5")
    if not rows:
        await message.answer("История промптов пуста.")
        return

    full_text = "Последние 5 версий промпта:\n\n" + "\n\n---\n\n".join(
        [f"#{r['id']} ({r['created_at'].strftime('%d.%m.%Y %H:%M')}):\n{r['text']}" for r in rows]
    )

    if len(full_text) > 4096:
        await message.answer("История промптов слишком длинная, будет отправлена по частям.")
        for i in range(0, len(full_text), 4000):
            await message.answer(full_text[i:i + 4000])
    else:
        await message.answer(full_text)

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

@router.message(AdminFilter(), Command("get_prices"))
async def get_prices(message: Message):
    stars_row = await db.fetchrow("SELECT value FROM prices WHERE name='premium_month_stars'")
    crypto_row = await db.fetchrow("SELECT value FROM prices WHERE name='premium_month_crypto'")
    
    stars_price = f"{stars_row['value']} XTR" if stars_row else "не установлена"
    crypto_price = f"{crypto_row['value']} RUB" if crypto_row else "не установлена"

    await message.answer(
        f"{hbold('Текущие цены на подписку')}\n\n"
        f"Через Telegram Stars: {stars_price}\n"
        f"Через CryptoCloud: {crypto_price}"
    )

@router.message(AdminFilter(), Command("set_price"))
async def set_price_start(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Telegram Stars (XTR)", callback_data="set_price_stars")],
        [InlineKeyboardButton(text="CryptoCloud (RUB)", callback_data="set_price_crypto")]
    ])
    await message.answer("Какую цену вы хотите установить?", reply_markup=keyboard)

@router.callback_query(AdminFilter(), F.data.startswith("set_price_"))
async def set_price_method_callback(call: CallbackQuery, state: FSMContext):
    price_type = call.data.replace("set_price_", "")
    
    if price_type == 'stars':
        prompt_text = "Введите новую стоимость подписки в Telegram Stars (целое число):"
        db_key = 'premium_month_stars'
    else:
        prompt_text = "Введите новую стоимость подписки в рублях (целое число):"
        db_key = 'premium_month_crypto'

    await state.update_data(price_db_key=db_key)
    await call.message.answer(prompt_text)
    await state.set_state(PriceStates.waiting_for_price)
    await call.answer()

@router.message(AdminFilter(), PriceStates.waiting_for_price)
async def save_price(message: Message, state: FSMContext):
    try:
        price = int(message.text)
        if price <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введите корректное положительное число!")
        return

    data = await state.get_data()
    price_db_key = data.get("price_db_key")

    if not price_db_key:
        await message.answer("Произошла ошибка. Попробуйте снова, начав с команды /set_price.")
        await state.clear()
        return

    await db.execute(
        "INSERT INTO prices (name, value, updated_at) VALUES ($1, $2, NOW()) ON CONFLICT (name) DO UPDATE SET value=$2, updated_at=NOW()",
        price_db_key, price
    )
    
    currency = "XTR" if "stars" in price_db_key else "руб."
    await message.answer(f"Стоимость подписки обновлена: {price} {currency}")
    await state.clear()

# --- Приветствие ---
@router.message(AdminFilter(), Command("get_welcome_message"))
async def get_welcome_message(message: Message):
    setting = await db.fetchrow("SELECT value FROM text_settings WHERE key='welcome_message'")
    if setting and setting['value']:
        await message.answer(f"Текущее приветствие (как его увидит пользователь):")
        try:
            await message.answer(setting['value'], parse_mode=ParseMode.HTML)
        except Exception as e:
            await message.answer(f"Не удалось отобразить форматирование. Исходный текст:\n\n{setting['value']}\n\nОшибка: {e}")
    else:
        await message.answer("Приветствие не найдено.")

@router.message(AdminFilter(), Command("set_welcome_message"))
async def set_welcome_message(message: Message, state: FSMContext):
    await message.answer("Введите новый текст приветствия (можно использовать HTML-теги для форматирования):\n\nОбязательно укажите {name} в качестве обращения к пользователю, вместо {name} будет имя пользователя\n\nПример:\n<b>С возвращением, {name}!</b>\n\nКак твои дела? Что-то случилось? Опишите вашу проблему, и мы вместе найдем решение.\n\n ")
    await state.set_state(WelcomeMessageStates.waiting_for_welcome_message)

@router.message(AdminFilter(), WelcomeMessageStates.waiting_for_welcome_message)
async def save_welcome_message(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Сообщение не может быть пустым. Попробуйте еще раз.")
        return
        
    text = message.text
    await db.execute(
        "INSERT INTO text_settings (key, value, updated_at) VALUES ('welcome_message', $1, NOW()) ON CONFLICT (key) DO UPDATE SET value=$1, updated_at=NOW()",
        text
    )
    await message.answer("Приветственное сообщение обновлено.")
    await state.clear()