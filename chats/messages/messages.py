import uuid
import aiofiles
import urllib.parse
import json
from datetime import datetime
from typing import Optional
from fastapi.responses import FileResponse
from fastapi import APIRouter, Depends, Path, UploadFile, File, Form, Query
from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, delete, update
from databases.databases import get_db, ChatModel, ChatMember, MessageModel, AttachmentModel
from auth.validation import get_current_user
from pathlib import Path as PathLib
from websocket.ws import manager
messages_router = APIRouter(prefix="/{chat_id}/messages", tags=["messages"])
from media.MediaInfo import MAX_FILE_SIZE, MAX_TOTAL_SIZE, FORBIDDEN_CONTENT_TYPE
from media.MediaInfo import MEDIA_ROOT


class PatchMessageSchema(BaseModel):
    text: str = Field(min_length=1)
    files: list[UploadFile] = []
    delete_file_ids: dict = Field(default_factory=dict)

@messages_router.patch("/{message_id}")
async def patch_message(
    text: str = Form(..., min_length=1),
    files: list[UploadFile] = File(default=None),
    delete_file_ids: str = Form(default='{}'),
    chat_id: int = Path(ge=1),
    message_id: int = Path(ge=1),
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        delete_file_ids_dict = json.loads(delete_file_ids) if delete_file_ids else {}
    except json.JSONDecodeError:
        delete_file_ids_dict = {}
    stmt = select(MessageModel).where(
        MessageModel.id == message_id,
        MessageModel.chat_id == chat_id,
        MessageModel.user_id == user_id
    )
    result = await db.execute(stmt)
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found or you don't have permission"
        )
    if text:
        message.text = text
    files_to_delete = []
    if delete_file_ids_dict and "id" in delete_file_ids_dict:
        file_ids_to_delete = delete_file_ids_dict["id"]
        if isinstance(file_ids_to_delete, list):
            for file_id in file_ids_to_delete:
                attachment_stmt = select(AttachmentModel).where(
                    AttachmentModel.id == file_id,
                    AttachmentModel.message_id == message_id
                )
                attachment_result = await db.execute(attachment_stmt)
                attachment = attachment_result.scalar_one_or_none()

                if attachment:
                    files_to_delete.append(attachment.filepath)
                    await db.delete(attachment)
    attachments = []
    attachment_ids = []

    if files:
        total_size = 0
        for file in files:
            if file.size is None or file.size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large. Max size is {MAX_FILE_SIZE // (1024 * 1024)} MB"
                )
            if file.content_type in FORBIDDEN_CONTENT_TYPE:
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

        PathLib("media/attachments").mkdir(parents=True, exist_ok=True)

        for file in files:
            ext = PathLib(file.filename).suffix.lower() if file.filename else ""
            unique_filename = f"{uuid.uuid4().hex}{ext}"
            filepath = f"attachments/{unique_filename}"
            full_path = PathLib("media") / filepath
            async with aiofiles.open(full_path, "wb") as f:
                await f.write(await file.read())
            attachment = AttachmentModel(
                message_id=message_id,
                filename=file.filename or unique_filename,
                filepath=filepath,
                content_type=file.content_type,
                size=file.size
            )
            db.add(attachment)
            await db.flush()
            attachments.append({
                "id": attachment.id,
                "filename": attachment.filename,
                "content_type": attachment.content_type
            })
            attachment_ids.append(attachment.id)

    await db.commit()

    for filepath in files_to_delete:
        try:
            file_path = PathLib(MEDIA_ROOT) / filepath
            if file_path.is_file():
                file_path.unlink()
        except Exception as e:
            print(f"Error deleting file {filepath}: {e}")
    attachments_result = await db.execute(
        select(AttachmentModel).where(AttachmentModel.message_id == message_id)
    )
    remaining_attachments = attachments_result.scalars().all()
    current_attachments = [
        {"id": att.id, "filename": att.filename, "content_type": att.content_type}
        for att in remaining_attachments
    ]
    data = {
        "action": "patch",
        "user_id": user_id,
        "chat_id": chat_id,
        "text": message.text,
        "time": message.sent_at.isoformat(),
        "id": message_id,
        "attachments": current_attachments
    }
    await manager.patch_to_chat(chat_id=chat_id, message_data=data)

    return {"ok": True, "uploaded_files": attachment_ids}


# class DeleteMessageSchema(BaseModel):
#     message_id: int = Field(ge=1)


@messages_router.delete("/{message_id}")
async def delete_message(message_id: int = Path(ge=1), chat_id: int = Path(ge=1),
                         user_id: int = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(delete(MessageModel).where(MessageModel.chat_id == chat_id,
                                                         MessageModel.user_id == user_id,
                                                         MessageModel.id == message_id))
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found or you don't have permission"
        )
    await db.commit()
    return {"ok": True}


@messages_router.get("/{message_id}/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: int = Path(ge=1),
    message_id: int = Path(ge=1),
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = (select(AttachmentModel).join(MessageModel, MessageModel.id == AttachmentModel.message_id)
            .join(ChatMember, ChatMember.chat_id == MessageModel.chat_id)
            .where(AttachmentModel.id == attachment_id, ChatMember.user_id == user_id, AttachmentModel.message_id == message_id))
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not allowed or does not exist"
        )
    file_path = PathLib(MEDIA_ROOT) / result.filepath
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing")
    return FileResponse(
            path=file_path,
            filename=result.filename,
            media_type=result.content_type or "application/octet-stream"
    )


@messages_router.get("/{message_id}/attachments/{attachment_id}/view")
async def view_attachment(
        attachment_id: int = Path(ge=1),
        message_id: int = Path(ge=1),
        user_id: int = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(AttachmentModel)
        .join(MessageModel, MessageModel.id == AttachmentModel.message_id)
        .join(ChatMember, ChatMember.chat_id == MessageModel.chat_id)
        .where(
            AttachmentModel.id == attachment_id,
            ChatMember.user_id == user_id,
            AttachmentModel.message_id == message_id
        )
    )
    result = await db.execute(stmt)
    result = result.scalar_one_or_none()

    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not allowed or does not exist")

    file_path = PathLib("media") / result.filepath

    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing")

    filename_encoded = urllib.parse.quote(result.filename)
    content_disposition = f"inline; filename*=UTF-8''{filename_encoded}"

    return FileResponse(
        path=file_path,
        media_type=result.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": content_disposition
        }
    )


@messages_router.get("")
async def get_message(limit: int = Query(20, ge=1, le=100), before: Optional[float] = None,
                      chat_id: int = Path(ge=1), user_id: int = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChatMember).where(
        ChatMember.chat_id == chat_id,
        ChatMember.user_id == user_id))
    if not result.scalar_one_or_none():
        print("Error")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No chat found or you are not a member"
        )
    db_request = select(MessageModel).where(MessageModel.chat_id == chat_id)
    if before is not None:
        db_request = db_request.where(MessageModel.sent_at < datetime.fromtimestamp(before))
    db_request = db_request.order_by(desc(MessageModel.sent_at)).limit(limit)
    result = await db.execute(db_request)
    messages = result.scalars().all()
    response = []
    for msg in messages:
        attachments_result = await db.execute(
            select(AttachmentModel).where(AttachmentModel.message_id == msg.id)
        )
        attachments = attachments_result.scalars().all()
        files_data = []
        for att in attachments:
            files_data.append({
                "id": att.id,
                "filename": att.filename,
                "content_type": att.content_type,
                "is_image": att.content_type.startswith("image/") if att.content_type else False
            })

        response.append(
            {
                "message_id": msg.id,
                "user_id": msg.user_id,
                "chat_id": msg.chat_id,
                "text": msg.text,
                "sent_at": msg.sent_at,
                "attachments": files_data
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
        if file.content_type in FORBIDDEN_CONTENT_TYPE:
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
    new_message = MessageModel(user_id=user_id, chat_id=chat_id, text=text)
    db.add(new_message)
    await db.flush()
    data = {"user_id": user_id, "chat_id": chat_id, "text": text, "time": new_message.sent_at.isoformat(), "id": new_message.id}
    PathLib("media/attachments").mkdir(parents=True, exist_ok=True)
    attachments = []
    attachment_ids = []
    for file in files:
        ext = PathLib(file.filename).suffix.lower() if file.filename else ""
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        filepath = f"attachments/{unique_filename}"
        full_path = PathLib("media") / filepath
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(await file.read())
        attachment = AttachmentModel(
            message_id=new_message.id,
            filename=file.filename or unique_filename,
            filepath=filepath,
            content_type=file.content_type,
            size=file.size
        )
        db.add(attachment)
        await db.flush()
        attachments.append({"id": attachment.id, "filename": attachment.filename, "content_type": attachment.content_type})
        attachment_ids.append(attachment.id)
    data["attachments"] = attachments
    await db.commit()
    await manager.send_to_chat(chat_id=chat_id, message_data=data)
    return {"ok": True, "message_id": new_message.id, "uploaded_files": attachment_ids}
