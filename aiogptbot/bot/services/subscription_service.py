from ..db.postgres import db
from datetime import datetime, timedelta

# Проверка и обновление статуса подписки пользователя
def get_user_status(user):
    if user['status'] == 'premium' and user['subscription_until'] and user['subscription_until'] < datetime.now():
        return 'expired'
    return user['status']

async def check_user_subscription(user_id):
    user = await db.fetchrow("SELECT * FROM users WHERE telegram_id=$1", user_id)
    if user['status'] == 'premium' and user['subscription_until'] and user['subscription_until'] < datetime.now():
        await db.execute("UPDATE users SET status='expired' WHERE telegram_id=$1", user_id)

# Инкремент лимита сообщений
def get_daily_limit(user):
    return 5 if user['status'] == 'demo' else 9999

async def increment_message_count(user_id):
    await db.execute("UPDATE users SET daily_message_count = daily_message_count + 1 WHERE telegram_id=$1", user_id)

# Сброс лимита сообщений (вызывать по крону)
async def reset_daily_limits():
    await db.execute("UPDATE users SET daily_message_count=0")

# Получить инфо о подписке
async def get_subscription_info(user_id):
    user = await db.fetchrow("SELECT * FROM users WHERE telegram_id=$1", user_id)
    return user['status'], user['subscription_until']
