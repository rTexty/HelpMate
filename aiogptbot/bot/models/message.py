from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class MessageModel(BaseModel):
    id: int
    user_id: int
    role: str  # user, assistant, system
    content: str
    created_at: datetime
