import os
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

class Settings(BaseModel):
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_BOT_TOKEN: str = os.getenv("ADMIN_BOT_TOKEN", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    POSTGRES_DSN: str = os.getenv("POSTGRES_DSN", "")  # postgresql://user:pass@host:port/db
    REDIS_DSN: str = os.getenv("REDIS_DSN", "")        # redis://localhost:6379/0
    ADMIN_IDS: str = os.getenv("ADMIN_IDS", "")    # через запятую

settings = Settings()
