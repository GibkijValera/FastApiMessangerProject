import redis.asyncio as redis


class RedisManager:
    def __init__(self):
        self.redis: redis.Redis | None = None

    async def connect(self):
        self.redis = redis.from_url(
            "redis://localhost:6379",
            decode_responses=True,
            encoding="utf-8"
        )
        try:
            await self.redis.ping()
            print("✅ Redis connected successfully")
        except Exception as e:
            print(f"❌ Failed to connect to Redis: {e}")
            raise e
        return self.redis

    async def disconnect(self):
        if self.redis:
            await self.redis.aclose()
            print("❌ Redis connection closed")

    def get_client(self) -> redis.Redis:
        if not self.redis:
            raise RuntimeError("Redis is not connected. Call connect() first.")
        return self.redis

    async def subscribe_user_to_chat(self, user_id: int, chat_id: int):
        client = self.get_client()
        await client.sadd(f"chat:{chat_id}:subscribers", str(user_id))
        await client.sadd(f"user:{user_id}:chats", f"chat:{chat_id}")

    async def unsubscribe_user_from_chat(self, user_id: int, chat_id: int):
        client = self.get_client()
        await client.srem(f"chat:{chat_id}:subscribers", str(user_id))
        await client.srem(f"user:{user_id}:chats", f"chat:{chat_id}")

    async def get_chat_subscribers(self, chat_id: int) -> set[str]:
        client = self.get_client()
        members = await client.smembers(f"chat:{chat_id}:subscribers")
        return members

    async def publish_message(self, channel: str, message: str):
        client = self.get_client()
        await client.publish(channel, message)


redis_manager = RedisManager()
