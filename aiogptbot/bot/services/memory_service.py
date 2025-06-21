from ..db.redis_client import redis_client
from ..db.postgres import db
from .openai_service import ask_gpt
import json

MEMORY_LIMIT = 10

async def get_user_memory(user_id):
    key = f"memory:{user_id}"
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    # Если нет в Redis — пробуем из PostgreSQL
    row = await db.fetchrow("SELECT summary FROM user_memory WHERE user_id=(SELECT id FROM users WHERE telegram_id=$1)", user_id)
    if row and row['summary']:
        return {"history": [], "summary": row['summary']}
    return {"history": [], "summary": None}

async def update_user_memory(user_id, history, last_gpt_response):
    key = f"memory:{user_id}"
    # Обрезаем историю до MEMORY_LIMIT
    history = history[-MEMORY_LIMIT:]
    # Каждые 10 сообщений — обновляем summary через GPT
    if len(history) % MEMORY_LIMIT == 0:
        summary = await ask_gpt(
            "Сделай краткое резюме интересов и целей пользователя на русском языке.",
            history
        )
        await db.execute(
            "INSERT INTO user_memory (user_id, summary, updated_at) VALUES ((SELECT id FROM users WHERE telegram_id=$1), $2, NOW()) ON CONFLICT (user_id) DO UPDATE SET summary=$2, updated_at=NOW()",
            user_id, summary
        )
    else:
        row = await db.fetchrow("SELECT summary FROM user_memory WHERE user_id=(SELECT id FROM users WHERE telegram_id=$1)", user_id)
        summary = row['summary'] if row else None
    # Сохраняем в Redis
    await redis_client.set(key, json.dumps({"history": history, "summary": summary}), ex=86400)
