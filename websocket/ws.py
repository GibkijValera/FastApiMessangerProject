import http
import uuid
from typing import List, Set
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
        self.active_connections: dict[str, WebSocket] = {} #словарь {uuid : websocket}
        self.active_sessions: dict[int, Set[str]] = {} #cловарь {user_id: Set[uuid]}

    async def add_new_chat(self, user_ids: List[int], chat_id: int):
        online_users = [user_id for user_id in user_ids if (user_id in self.active_sessions and self.active_sessions[user_id])]
        await redis_manager.subscribe_users_to_chat(online_users, chat_id)

    async def connect(self, websocket: WebSocket, db: AsyncSession, user_id: int):
        session = uuid.uuid4().hex
        self.active_connections[session] = websocket
        if user_id in self.active_sessions:
            self.active_sessions[user_id].add(session)
        else:
            self.active_sessions[user_id] = {session}
            chat_ids = await self.get_user_chats_from_db(user_id, db)
            await redis_manager.subscribe_user_to_chats(user_id, chat_ids)
        return session

    async def disconnect(self, user_id: int, session: str):
        if session in self.active_connections:
            del self.active_connections[session]
        if user_id in self.active_sessions and session in self.active_sessions[user_id]:
            self.active_sessions[user_id].remove(session)
            if not self.active_sessions[user_id]:
                user_chats_key = f"user:{user_id}:chats"
                chat_keys = await redis_manager.get_client().smembers(user_chats_key)
                chat_ids = [int(chat_key.split(":")[1]) for chat_key in chat_keys]
                if chat_ids:
                    await redis_manager.unsubscribe_user_from_chats(user_id, chat_ids)

    async def send_notify(self, chat_id: int, message_data: dict):
        subscribers = await redis_manager.get_chat_subscribers(chat_id)
        for subscriber_id_str in subscribers:
            user_id = int(subscriber_id_str)
            if user_id in self.active_sessions:
                for session in self.active_sessions[user_id]:
                    try:
                        data = json.dumps(message_data)
                        await self.active_connections[session].send_text(data)
                    except Exception:
                        await self.disconnect(user_id, session)

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
    session = None
    try:
        await websocket.accept()
        user_id = await get_current_user_ws(websocket)

        if not user_id:
            await websocket.close(code=4001, reason="Unauthorized")
            return
        print("Starting Connection")
        session = await manager.connect(websocket, db, user_id)
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
        if session and user_id:
            await manager.disconnect(user_id, session)

