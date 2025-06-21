import csv
import io
from ..db.postgres import db

async def export_users_csv():
    rows = await db.fetch("SELECT telegram_id, username, full_name, status, subscription_until, daily_message_count, last_activity, is_banned, created_at FROM users")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["telegram_id", "username", "full_name", "status", "subscription_until", "daily_message_count", "last_activity", "is_banned", "created_at"])
    for r in rows:
        writer.writerow([
            r['telegram_id'],
            r['username'],
            r['full_name'],
            r['status'],
            r['subscription_until'],
            r['daily_message_count'],
            r['last_activity'],
            r['is_banned'],
            r['created_at']
        ])
    return output.getvalue().encode("utf-8") 