import asyncpg
from ..config import settings

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(dsn=settings.POSTGRES_DSN)

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def execute(self, query, *args, **kwargs):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args, **kwargs)

    async def fetch(self, query, *args, **kwargs):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args, **kwargs)

    async def fetchrow(self, query, *args, **kwargs):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args, **kwargs)

db = Database()
