import redis.asyncio as redis
from ..config import settings

redis_client = redis.from_url(settings.REDIS_DSN, decode_responses=True)
