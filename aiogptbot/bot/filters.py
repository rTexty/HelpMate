from aiogram.filters import BaseFilter
from aiogram.types import Message
from .config import settings
import re

ADMIN_IDS = [int(x) for x in settings.ADMIN_IDS.split(',') if x]

# Фильтр: только для админов
class AdminFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return False
        return message.from_user.id in ADMIN_IDS

# Фильтр: эмоции по ключевым словам
SAD_KEYWORDS = [
    'грустно', 'печально', 'тяжело', 'депрессия', 'плохо', 'одиноко', 'устал', 'нет сил', 'разочарован',
    'тоска', 'слёзы', 'слезы', 'плакать', 'не хочу жить', 'безнадежно', 'безнадёжно', 'боль', 'страх', 'тревога'
]

class SadEmotionFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        text = message.text.lower() if message.text else ''
        return any(word in text for word in SAD_KEYWORDS)

# Фильтр: мат и грубости
BAD_WORDS = [
    'блять', 'сука', 'хуй', 'пизд', 'еба', 'ебл', 'гандон', 'мудак', 'долбоёб', 'долбаёб', 'идиот', 'тварь',
    'сволочь', 'чмо', 'мразь', 'ублюдок', 'гнида', 'шлюха', 'проститутка', 'сучка', 'гавно', 'говно', 'дерьмо'
]
BAD_WORDS_RE = re.compile(r'(' + '|'.join(BAD_WORDS) + r')', re.IGNORECASE)

class BadWordFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        text = message.text.lower() if message.text else ''
        return bool(BAD_WORDS_RE.search(text))

# Фильтр: только для подписчиков (premium)
class PremiumFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return False
        from .db.postgres import db
        user = await db.fetchrow("SELECT * FROM users WHERE telegram_id=$1", message.from_user.id)
        return user and user['status'] == 'premium'
