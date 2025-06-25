from ..db.redis_client import redis_client
from ..db.postgres import db
import json
from loguru import logger

MEMORY_LIMIT = 10  # 5 пар (user, assistant)

async def get_user_memory(user_id: int) -> dict:
    """
    Получает историю из Redis и summary из PostgreSQL.
    Гарантированно возвращает словарь с ключами "history" (list) и "summary" (str или None).
    """
    history = []
    summary = None

    # 1. Пытаемся получить историю из Redis
    try:
        history_key = f"memory:{user_id}"
        history_data = await redis_client.get(history_key)
        if history_data:
            loaded_history = json.loads(history_data)
            if isinstance(loaded_history, list):
                history = loaded_history
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Could not decode history from Redis for user {user_id}: {e}")
        history = []

    # 2. Пытаемся получить summary из PostgreSQL
    try:
        user_db_id_row = await db.fetchrow("SELECT id FROM users WHERE telegram_id=$1", user_id)
        if user_db_id_row:
            user_db_id = user_db_id_row['id']
            summary_row = await db.fetchrow("SELECT summary FROM user_memory WHERE user_id=$1", user_db_id)
            if summary_row and summary_row['summary']:
                summary = summary_row['summary']
    except Exception as e:
        logger.error(f"Could not fetch summary from PostgreSQL for user {user_id}: {e}")
        summary = None
    
    return {"history": history, "summary": summary}


async def update_user_memory(user_id: int, history: list, assistant_response: str):
    """
    Обновляет историю в Redis и периодически обновляет резюме диалога в PostgreSQL.
    """
    # 1. Добавляем ответ ассистента и обрезаем историю
    history.append({"role": "assistant", "content": assistant_response})
    if len(history) > MEMORY_LIMIT:
        history = history[-MEMORY_LIMIT:]
    
    # 2. Сохраняем историю в Redis
    history_key = f"memory:{user_id}"
    await redis_client.set(history_key, json.dumps(history), ex=3600)

    # 3. Каждые 10 сообщений (когда история заполнится) обновляем summary
    if len(history) == MEMORY_LIMIT:
        logger.info(f"Updating summary for user {user_id}...")
        # Этот импорт здесь, чтобы избежать циклических зависимостей
        from .openai_service import ask_gpt

        summary_prompt = "Ты — AI-аналитик. Проанализируй предоставленный диалог и сделай очень краткое, но емкое резюме (на русском языке) об интересах, целях и личности пользователя. Это резюме будет использоваться для поддержания контекста в будущих диалогах. Не здоровайся, просто дай резюме."
        new_summary = await ask_gpt(summary_prompt, history)

        user_db_id_row = await db.fetchrow("SELECT id FROM users WHERE telegram_id=$1", user_id)
        if user_db_id_row:
            user_db_id = user_db_id_row['id']
            await db.execute(
                """
                INSERT INTO user_memory (user_id, summary, updated_at) 
                VALUES ($1, $2, NOW()) 
                ON CONFLICT (user_id) DO UPDATE SET summary = EXCLUDED.summary, updated_at = NOW()
                """,
                user_db_id, new_summary
            )
            logger.info(f"Successfully updated summary for user {user_id}.")
