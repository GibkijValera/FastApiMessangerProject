from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Path
from fastapi import HTTPException, status
import pydantic
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, delete, update
from sqlalchemy.orm import aliased
from databases.databases import get_db, UserModel, ChatModel, ChatMember, MessageModel
from auth.validation import get_current_user


messages_router = APIRouter(prefix="/messages")


class PatchMessageSchema(BaseModel):
    message_id: int = Field(ge=1)
    text: str = Field(min_length=1)


@messages_router.patch("")
async def patch_message(schema: PatchMessageSchema, user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(update(MessageModel).where(
        MessageModel.user_id == user_id, MessageModel.id == schema.message_id).values(text=schema.text))
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found or you don't have permission"
        )
    await db.commit()
    return {"ok": True}


class DeleteMessageSchema(BaseModel):
    message_id: int = Field(ge=1)


@messages_router.delete("")
async def delete_message(schema: DeleteMessageSchema, user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(delete(MessageModel).where(
        MessageModel.user_id == user_id, MessageModel.id == schema.message_id))
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found or you don't have permission"
        )
    await db.commit()
    return {"ok": True}


class GetMessagesSchema(BaseModel):
    limit: int = Field(50, ge=1, le=100)
    before: Optional[float] = None


@messages_router.post("/{chat_id}")
async def get_message(schema: GetMessagesSchema, chat_id: int = Path(ge=1), user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChatMember).where(
        ChatMember.chat_id == chat_id,
        ChatMember.user_id == user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No chat found or you are not a member"
        )
    db_request = select(MessageModel).where(MessageModel.chat_id == chat_id)
    if schema.before is not None:
        db_request = db_request.where(MessageModel.sent_at < datetime.fromtimestamp(schema.before))
    db_request = db_request.order_by(desc(MessageModel.sent_at)).limit(schema.limit)
    result = await db.execute(db_request)
    messages = result.scalars().all()
    print(messages)
    return {
        "messages":
            [
                {
                    "message_id": msg.id,
                    "user_id": msg.user_id,
                    "chat_id":  msg.chat_id,
                    "text": msg.text,
                    "sent_at": msg.sent_at
                }
                for msg in messages
            ],
        "ok": True
    }


class SendMessageSchema(BaseModel):
    text: str = Field(min_length=1, max_length=255)
    chat_id: None | int = Field(ge=1)
    user2_id: None | int = Field(ge=1)


@messages_router.post("")
async def send_message(schema: SendMessageSchema, user_id: int = Depends(get_current_user),db: AsyncSession = Depends(get_db)):
    if not schema.user2_id and not schema.chat_id or schema.user2_id and schema.chat_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect request"
        )
    if schema.chat_id:
        result = await db.execute(select(ChatMember).where(
            ChatMember.chat_id == schema.chat_id,
            ChatMember.user_id == user_id))
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not in this chat"
            )
        result = await db.execute(select(ChatModel).where(ChatModel.id == schema.chat_id))
        chat = result.scalar_one_or_none()
        if chat.status != "opened":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chat is closed"
            )
        new_message = MessageModel(
            user_id=user_id,
            chat_id=schema.chat_id,
            text=schema.text
        )
    else:
        if user_id == schema.user2_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can't create new chat with yourself"
            )
        user_exists = await db.execute(select(UserModel.id).where(UserModel.id == schema.user2_id))
        if not user_exists.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {schema.user2_id} not found")
        cm1 = aliased(ChatMember)
        cm2 = aliased(ChatMember)
        stmt = (
            select(ChatModel.id)
            .join(cm1, ChatModel.id == cm1.chat_id)
            .join(cm2, ChatModel.id == cm2.chat_id)
            .where(
                ChatModel.is_private == True,
                cm1.user_id == user_id,
                cm2.user_id == schema.user2_id
            )
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chat already exists"
            )
        new_chat = ChatModel(is_private=True, name=None)
        db.add(new_chat)
        await db.flush()
        new_model1 = ChatMember(chat_id=new_chat.id, user_id=user_id, role="member")
        new_model2 = ChatMember(chat_id=new_chat.id, user_id=schema.user2_id, role="member")
        db.add(new_model1)
        db.add(new_model2)
        new_message = MessageModel(user_id=user_id, chat_id=new_chat.id, text=schema.text)
    db.add(new_message)
    await db.commit()
    await db.refresh(new_message)
    return {"ok": True, "message_id": new_message.id}
