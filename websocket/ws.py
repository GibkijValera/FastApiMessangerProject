import http

from fastapi import WebSocket, Depends, APIRouter, status, WebSocketDisconnect
from fastapi.exceptions import HTTPException
from redis_manager.redis import redis_manager
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from databases.databases import ChatMember, get_db
from auth.validation import get_current_user_ws
import json


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, WebSocket] = {}

    async def connect(self, websocket: WebSocket, db: AsyncSession, user_id: int):
        self.active_connections[user_id] = websocket
        chat_ids = await self.get_user_chats_from_db(user_id, db)
        for chat_id in chat_ids:
            await redis_manager.subscribe_user_to_chat(user_id, chat_id)

    async def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        user_chats_key = f"user:{user_id}:chats"
        chat_keys = await redis_manager.get_client().smembers(user_chats_key)
        for chat_key in chat_keys:
            chat_id = chat_key.split(":")[1]
            await redis_manager.unsubscribe_user_from_chat(user_id, int(chat_id))

    async def send_to_chat(self, chat_id: int, message_data: dict):
        subscribers = await redis_manager.get_chat_subscribers(chat_id)
        print(subscribers)
        for subscriber_id_str in subscribers:
            user_id = int(subscriber_id_str)
            if user_id in self.active_connections:
                try:
                    print(user_id)
                    data = json.dumps(message_data)
                    print("...")
                    await self.active_connections[user_id].send_text(
                        data
                    )
                except Exception:
                    print("oh")
                    await self.disconnect(user_id)

    async def get_user_chats_from_db(self, user_id: int, db: AsyncSession) -> list[int]:
        request = select(ChatMember.chat_id).where(ChatMember.user_id == user_id)
        result = await db.execute(request)
        ans = result.scalars().all()
        return ans


manager = ConnectionManager()

ws_router = APIRouter(prefix="/ws", tags=["WebSocket"])


@ws_router.websocket("/")
async def websocket_endpoint(
        websocket: WebSocket,
        db: AsyncSession = Depends(get_db)
):
    user_id = None
    is_connected = False

    try:
        await websocket.accept()
        user_id = await get_current_user_ws(websocket)

        if not user_id:
            await websocket.close(code=4001, reason="Unauthorized")
            return
        await manager.connect(websocket, db, user_id)
        is_connected = True

        print(f"User {user_id} connected successfully via Cookies")
        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        print(f"User {user_id} disconnected normally")

    except Exception as e:
        print(f"Something went wrong with user {user_id}: {e}")

    finally:
        if is_connected and user_id:
            await manager.disconnect(user_id)

