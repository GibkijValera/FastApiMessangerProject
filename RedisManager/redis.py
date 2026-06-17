import redis.asyncio as redis


class RedisManager:
    def __init__(self):
        self.redis = None

    async def connect(self):
        self.redis = await redis.from_url(
            "redis://localhost:6379",
            decode_responses=True,
            encoding="utf-8"
        )
        await self.redis.ping()
        print("✅ Redis connected")
        return self.redis

    async def disconnect(self):
        if self.redis:
            await self.redis.close()
            print("❌ Redis disconnected")

    def get_redis(self):
        if not self.redis:
            raise RuntimeError("Redis not connected")
        return self.redis


redis_manager = RedisManager()
