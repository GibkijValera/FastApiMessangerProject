import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Path, UploadFile, File, Form
from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, delete, update
from sqlalchemy.orm import aliased
from databases.databases import get_db, UserModel, ChatModel, ChatMember, MessageModel, AttachmentModel
from auth.validation import get_current_user
from pathlib import Path as PathLib

messages_router = APIRouter(prefix="/{chat_id}/messages", tags=["messages"])
from chats.messages.attachments import MAX_FILE_SIZE, MAX_TOTAL_SIZE, ALLOWED_CONTENT_TYPES


class PatchMessageSchema(BaseModel):
    message_id: int = Field(ge=1)
    text: str = Field(min_length=1)


@messages_router.patch("")
async def patch_message(schema: PatchMessageSchema, chat_id: int = Path(ge=1), user_id: int = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    result = await db.execute(update(MessageModel).where(
        MessageModel.user_id == user_id, MessageModel.chat_id == chat_id, MessageModel.id == schema.message_id).values(
        text=schema.text))
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
async def delete_message(schema: DeleteMessageSchema, chat_id: int = Path(ge=1),
                         user_id: int = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(delete(MessageModel).where(MessageModel.chat_id == chat_id,
                                                         MessageModel.user_id == user_id,
                                                         MessageModel.id == schema.message_id))
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


@messages_router.post("")
async def get_message(schema: GetMessagesSchema, chat_id: int = Path(ge=1), user_id: int = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
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
    response = []
    for msg in messages:
        attachments = await db.execute(select(AttachmentModel).where(AttachmentModel.message_id == msg.id))
        attachments = attachments.scalars().all()
        response.append(
            {
                "message_id": msg.id,
                "user_id": msg.user_id,
                "chat_id": msg.chat_id,
                "text": msg.text,
                "sent_at": msg.sent_at,
                "attachment_ids": [att.id for att in attachments]
            }
        )
    return {
        "messages": response,
        "ok": True
    }


@messages_router.post("")
async def send_message(
        text: str = Form(..., min_length=1, max_length=255),
        chat_id: int = Path(ge=1),
        files: list[UploadFile] = File(default=[]),
        user_id: int = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    total_size = 0
    for file in files:
        if file.size is None or file.size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Max size is {MAX_FILE_SIZE // (1024 * 1024)} MB"
            )
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File type not allowed"
            )
        total_size += file.size

    if total_size > MAX_TOTAL_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Total files size too large. Max total size is {MAX_TOTAL_SIZE // (1024 * 1024)} MB"
        )

    result = await db.execute(
        select(ChatMember).where(
            ChatMember.chat_id == chat_id,
            ChatMember.user_id == user_id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not in this chat"
        )
    result = await db.execute(select(ChatModel).where(ChatModel.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat or chat.status != "opened":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chat is closed"
        )
        # if user_id == user2_id:
        #     raise HTTPException(
        #         status_code=status.HTTP_400_BAD_REQUEST,
        #         detail="Can't create new chat with yourself"
        #     )
        # user_exists = await db.execute(select(UserModel.id).where(UserModel.id == user2_id))
        # if not user_exists.scalar_one_or_none():
        #     raise HTTPException(
        #         status_code=status.HTTP_404_NOT_FOUND,
        #         detail=f"User {user2_id} not found"
        #     )
        # cm1 = aliased(ChatMember)
        # cm2 = aliased(ChatMember)
        # stmt = (
        #     select(ChatModel.id)
        #     .join(cm1, ChatModel.id == cm1.chat_id)
        #     .join(cm2, ChatModel.id == cm2.chat_id)
        #     .where(
        #         ChatModel.is_private == True,
        #         cm1.user_id == user_id,
        #         cm2.user_id == user2_id
        #     )
        # )
        # result = await db.execute(stmt)
        # if result.scalar_one_or_none():
        #     raise HTTPException(
        #         status_code=status.HTTP_400_BAD_REQUEST,
        #         detail="Chat already exists"
        #     )
        # new_chat = ChatModel(is_private=True, name=None)
        # db.add(new_chat)
        # await db.flush()
        # member1 = ChatMember(chat_id=new_chat.id, user_id=user_id, role="member")
        # member2 = ChatMember(chat_id=new_chat.id, user_id=user2_id, role="member")
        # db.add(member1)
        # db.add(member2)
        # target_chat_id = new_chat.id

    new_message = MessageModel(user_id=user_id, chat_id=chat_id, text=text)
    db.add(new_message)
    await db.flush()

    PathLib("media/attachments").mkdir(parents=True, exist_ok=True)
    attachment_urls = []
    for file in files:
        ext = PathLib(file.filename).suffix.lower() if file.filename else ""
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        filepath = f"attachments/{unique_filename}"
        full_path = PathLib("media") / filepath
        with open(full_path, "wb") as f:
            f.write(await file.read())
        attachment = AttachmentModel(
            message_id=new_message.id,
            filename=file.filename or unique_filename,
            filepath=filepath,
            content_type=file.content_type,
            size=file.size
        )
        db.add(attachment)
        attachment_urls.append(f"/media/{filepath}")

    await db.commit()
    return {"ok": True, "message_id": new_message.id, "uploaded_files": attachment_urls}
