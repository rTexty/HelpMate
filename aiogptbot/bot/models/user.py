from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class User(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str]
    full_name: Optional[str]
    status: str
    subscription_until: Optional[datetime]
    daily_message_count: int
    last_activity: Optional[datetime]
    is_banned: bool
    created_at: datetime
