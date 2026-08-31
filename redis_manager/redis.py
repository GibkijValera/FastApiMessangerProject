import redis.asyncio as redis
from typing import List

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

    async def subscribe_users_to_chat(self, user_ids: List[int], chat_id: int):
        client = self.get_client()
        async with client.pipeline(transaction=False) as pipe:
            for user_id in user_ids:
                pipe.sadd(f"chat:{chat_id}:subscribers", str(user_id))
                pipe.sadd(f"user:{user_id}:chats", f"chat:{chat_id}")
            await pipe.execute()

    async def subscribe_user_to_chats(self, user_id: int, chat_ids: List[int]):
        client = self.get_client()
        async with client.pipeline(transaction=False) as pipe:
            for chat_id in chat_ids:
                pipe.sadd(f"chat:{chat_id}:subscribers", str(user_id))
                pipe.sadd(f"user:{user_id}:chats", f"chat:{chat_id}")
            await pipe.execute()

    async def subscribe_user_to_chat(self, user_id: int, chat_id: int):
        client = self.get_client()
        await client.sadd(f"chat:{chat_id}:subscribers", str(user_id))
        await client.sadd(f"user:{user_id}:chats", f"chat:{chat_id}")

    async def unsubscribe_user_from_chats(self, user_id: int, chat_ids: List[int]):
        client = self.get_client()
        async with client.pipeline(transaction=False) as pipe:
            for chat_id in chat_ids:
                pipe.srem(f"chat:{chat_id}:subscribers", str(user_id))
                pipe.srem(f"user:{user_id}:chats", f"chat:{chat_id}")
            await pipe.execute()

    async def unsubscribe_users_from_chat(self, users_id: List[int], chat_id: int):
        client = self.get_client()
        async with client.pipeline(transaction=False) as pipe:
            for user_id in users_id:
                pipe.srem(f"chat:{chat_id}:subscribers", str(user_id))
                pipe.srem(f"user:{user_id}:chats", f"chat:{chat_id}")
            await pipe.execute()

    async def get_chat_subscribers(self, chat_id: int) -> set[str]:
        client = self.get_client()
        members = await client.smembers(f"chat:{chat_id}:subscribers")
        return members

    async def publish_message(self, channel: str, message: str):
        client = self.get_client()
        await client.publish(channel, message)


redis_manager = RedisManager()
