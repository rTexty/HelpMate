from aiogram import Router, F, Bot, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.utils.chat_action import ChatActionSender
from ..db.postgres import db
import asyncio
from loguru import logger

class OnboardingStates(StatesGroup):
    start_intro = State()
    second_intro = State()
    waiting_for_name = State()
    name_confirmation = State()
    waiting_for_age = State()
    waiting_for_gender = State()

router = Router()

@router.message(Command("start"), OnboardingStates.start_intro)
@router.message(Command("start"), OnboardingStates.second_intro)
@router.message(Command("start"), OnboardingStates.waiting_for_name)
@router.message(Command("start"), OnboardingStates.name_confirmation)
@router.message(Command("start"), OnboardingStates.waiting_for_age)
@router.message(Command("start"), OnboardingStates.waiting_for_gender)
async def restart_onboarding_during_state(message: Message, state: FSMContext, bot: Bot):
    """
    Handles the /start command during any of the onboarding steps,
    effectively resetting and restarting the process.
    """
    if not message.from_user:
        return
        
    logger.info(f"User {message.from_user.id} sent /start during onboarding. Restarting process.")
    await state.clear()
    # Просто запускаем онбординг заново
    await start_onboarding(message, state, bot)

async def start_onboarding(message: Message, state: FSMContext, bot: Bot):
    """Initiates the onboarding process."""
    if not message.from_user:
        return
    logger.info(f"--- Function start_onboarding called for user {message.from_user.id} ---")
    
    bot_name_row = await db.fetchrow("SELECT value FROM text_settings WHERE key='bot_name'")
    bot_name = bot_name_row['value'] if bot_name_row else "Маша"
    
    async with ChatActionSender(bot=bot, chat_id=message.chat.id):
        await asyncio.sleep(1)
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"Привет, {bot_name}!", callback_data="intro_1_next")]])
        await message.answer(f"Привет! Меня зовут {bot_name} 😊 Я буду твоим виртуальным психологом и другом.", reply_markup=markup)
    await state.set_state(OnboardingStates.start_intro)

@router.callback_query(OnboardingStates.start_intro, F.data == "intro_1_next")
async def handle_intro_1(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not call.message:
        return
    # Удаляем предыдущее сообщение с кнопкой
    # await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)

    async with ChatActionSender(bot=bot, chat_id=call.message.chat.id):
        await asyncio.sleep(1)
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Здорово!", callback_data="intro_2_next")]])
        await bot.send_message(call.message.chat.id, "💫 Я была обучена специально для того, чтобы оказывать помощь, как настоящий психолог. Наш диалог максимально приближен к процессу терапии. Я постараюсь услышать тебя, понять и помочь тебе справиться с жизненным затруднением.", reply_markup=markup)
    await state.set_state(OnboardingStates.second_intro)
    await call.answer()

@router.callback_query(OnboardingStates.second_intro, F.data == "intro_2_next")
async def handle_intro_2(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not call.message:
        return
    # await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
    async with ChatActionSender(bot=bot, chat_id=call.message.chat.id):
        await asyncio.sleep(1)
        await bot.send_message(call.message.chat.id, "Как я могу обращаться к тебе? Напиши только имя, например \"Маша\".")
    await state.set_state(OnboardingStates.waiting_for_name)
    await call.answer()

@router.message(OnboardingStates.waiting_for_name, F.text)
async def handle_name(message: Message, state: FSMContext, bot: Bot):
    if not message.text or not message.from_user:
        return
    logger.info(f"--- handle_name triggered for user {message.from_user.id} ---")
    name = message.text.strip()
    if len(name) > 50:
        await message.answer("Имя слишком длинное. Попробуй еще раз.")
        return
    
    await state.update_data(name=name)
    
    async with ChatActionSender(bot=bot, chat_id=message.chat.id):
        # await bot.send_sticker(message.chat.id, "CAACAgIAAxkBAAEMAbZmZt921Lp2Gj1j2eWq-mYtW_zdDQACVgwAAg3S2UqD29_A-EEi9zQE")
        await asyncio.sleep(1)
        await message.answer(f"Я очень рада с тобой познакомиться, {name}!")
        await asyncio.sleep(1.5)
        await message.answer("Скажи, пожалуйста, сколько тебе лет? Укажи цифру.\n\nЭто необходимо мне для настройки контента")
        
    await state.set_state(OnboardingStates.waiting_for_age)
    
@router.message(OnboardingStates.waiting_for_age, F.text)
async def handle_age(message: Message, state: FSMContext, bot: Bot):
    if not message.text or not message.text.isdigit() or not message.from_user:
        await message.answer("Пожалуйста, укажи возраст цифрами.")
        return
    
    age = int(message.text)
    if not 10 <= age <= 100:
        await message.answer("Укажи, пожалуйста, реальный возраст (от 10 до 100 лет).")
        return
        
    await state.update_data(age=age)
    
    async with ChatActionSender(bot=bot, chat_id=message.chat.id):
        await asyncio.sleep(1)
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Женский", callback_data="gender_female")],
            [InlineKeyboardButton(text="Мужской", callback_data="gender_male")]
        ])
        await message.answer("Отлично. А в каком роде я могу к тебе обращаться – в мужском или женском? 😇", reply_markup=markup)

    await state.set_state(OnboardingStates.waiting_for_gender)
    logger.info(f"User {message.from_user.id}: State set to 'waiting_for_gender'.")

@router.callback_query(OnboardingStates.waiting_for_gender, F.data.startswith("gender_"))
async def handle_gender(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not call.data or not call.message or not call.from_user:
        return
        
    user_id = call.from_user.id
    logger.info(f"--- handle_gender triggered for user {user_id} with data: {call.data} ---")
    
    gender = call.data.replace("gender_", "")
    data = await state.get_data()
    name = data.get("name")
    age_str = data.get("age")

    try:
        age = int(age_str) if age_str else None
    except (ValueError, TypeError):
        age = None
    
    logger.info(f"User {user_id}: Data from state: Name='{name}', Age={age}, Gender='{gender}'")

    if age is not None and age < 14:
        logger.info(f"User {user_id}: Age is below 14. Aborting onboarding.")
        await bot.send_message(
            chat_id=call.message.chat.id,
            text=(
                "Благодарю за честность. К сожалению, наш сервис предназначен для пользователей старше 14 лет. "
                "Это связано с особенностями психологической поддержки, которую я оказываю.\n\n"
                "Обязательно возвращайся, когда немного подрастешь! Всего доброго. 😊"
            )
        )
        await call.answer()
        # Не сохраняем данные и сбрасываем состояние
        await state.clear()
        return

    try:
        logger.info(f"User {user_id}: Preparing to update DB record.")
        update_query = "UPDATE users SET preferred_name=$1, age=$2, gender=$3, onboarding_completed=TRUE WHERE telegram_id=$4"
        logger.debug(f"User {user_id}: Executing SQL: {update_query} with params: [{name}, {age}, {gender}, {user_id}]")
        
        await db.execute(update_query, name, age, gender, user_id)
        
        logger.info(f"User {user_id}: DB record updated successfully. Preparing final message.")
    except Exception as e:
        logger.error(f"User {user_id}: DB update FAILED: {e}")
        await call.answer("Произошла ошибка при сохранении данных. Попробуйте позже.", show_alert=True)
        await state.clear()
        return

    # await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
    try:
        async with ChatActionSender(bot=bot, chat_id=call.message.chat.id):
            await asyncio.sleep(1)
            logger.info(f"User {user_id}: Sending final confirmation message.")
            await bot.send_message(
                chat_id=call.message.chat.id,
                text=f"Спасибо, {name}! Я всё записала. Теперь мы можем начать 😊\n\n"
                     "Напиши, что тебя беспокоит, и я постараюсь помочь.",
                reply_markup=ReplyKeyboardRemove()
            )
        logger.info(f"User {user_id}: Final message sent. Clearing state.")
    except Exception as e:
        logger.error(f"User {user_id}: FAILED to send final message: {e}")

    await state.clear()
    await call.answer() 