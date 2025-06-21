from aiogram.filters import BaseFilter
from aiogram.types import Message
from ..bot.config import settings

ADMIN_IDS = [int(x) for x in settings.ADMIN_IDS.split(',') if x]

# Фильтр: только для админов
class AdminFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return False
        return message.from_user.id in ADMIN_IDS 