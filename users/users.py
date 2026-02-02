import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, Path, UploadFile, File, Form
from fastapi import HTTPException, status

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, or_
from sqlalchemy.orm import aliased
from chats.messages.attachments import MAX_FILE_SIZE, MAX_TOTAL_SIZE, ALLOWED_CONTENT_TYPES
from auth.validation import get_current_user
from databases.databases import get_db, UserModel, UserFriends, ChatMember, ChatModel, MessageModel, AttachmentModel
from pathlib import Path as PathLib
users_router = APIRouter(prefix="/users", tags=["users"])


@users_router.post("/{user2_id}/message")
async def lazy_creation_chat(text: Annotated[str, Form()],  files: List[UploadFile] = File(default=None),
                             user2_id: int = Path(ge=1), user_id: int = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    if files is None:
        files = []
    result = await db.execute(select(UserModel.id).where(UserModel.id == user2_id))
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user_id == user2_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot create chat with yourself")
    cm1 = aliased(ChatMember)
    cm2 = aliased(ChatMember)
    request = (
        select(ChatModel.id)
        .join(cm1, ChatModel.id == cm1.chat_id)
        .join(cm2, ChatModel.id == cm2.chat_id)
        .where(
            ChatModel.is_private == True,
            cm1.user_id == user_id,
            cm2.user_id == user2_id
        )
    )
    result = await db.execute(request)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="chat already exists"
        )
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
    new_chat = ChatModel(
        is_private=True,
        name=None,
        status="opened"
    )
    db.add(new_chat)
    await db.flush()
    new_message = MessageModel(user_id=user_id, chat_id=new_chat.id, text=text)
    db.add(new_message)
    await db.flush()
    member1 = ChatMember(chat_id=new_chat.id, user_id=user_id, role="member")
    member2 = ChatMember(chat_id=new_chat.id, user_id=user2_id, role="member")
    db.add(member1)
    db.add(member2)
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
    return {"ok": True, "chat_id": new_chat.id, "message_id": new_message.id, "uploaded_files": attachment_urls}

class PatchUserProfileSchema(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    lastname: str = Field(min_length=1, max_length=32)
    bio: None | str = Field(max_length=255)


@users_router.patch("/profile")
async def patch_user_profile(schema: PatchUserProfileSchema, user_id: int = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    result = await db.execute(update(UserModel).where(UserModel.id == user_id)
                              .values(name=schema.name, lastname=schema.lastname, bio=schema.bio))
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile found"
        )
    await db.commit()
    return{"ok": True}


@users_router.delete("/profile")
async def delete_user_profile(user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(delete(UserModel).where(UserModel.id == user_id))
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found"
        )
    await db.commit()
    return {"ok": True}


@users_router.get("/profile")
async def get_user_profile(user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserModel).where(UserModel.id == user_id))
    data = result.scalar_one_or_none()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile found"
        )
    return {
        "ok": True,
        "id": data.id,
        "name": data.name,
        "lastname": data.lastname,
        "bio": data.bio,
        "email": data.email
    }


@users_router.get("/{user_id}")
async def get_user(user_id: int = Path(ge=1), requester_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserModel).where(UserModel.id == user_id))
    data = result.scalar_one_or_none()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found"
        )
    return {
        "ok": True,
        "id": data.id,
        "name": data.name,
        "lastname": data.lastname,
        "bio": data.bio
        }

