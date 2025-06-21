from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Prompt(BaseModel):
    id: int
    text: str
    created_at: datetime
    is_active: bool
