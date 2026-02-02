from fastapi import APIRouter, Depends, Path
from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from databases.databases import get_db, UserModel, ChatModel, ChatMember
from sqlalchemy import select, update, delete
from typing import List, Set
from auth.validation import get_current_user
from chats.messages.messages import messages_router
chats_router = APIRouter(prefix="/chats", tags=["chats"])
chats_router.include_router(messages_router)

class SetChatSchema(BaseModel):
    members_id: Set[int] = Field(min_length=2, max_length=15)
    name: None | str = Field(min_length=1, max_length=64)


@chats_router.post("")
async def create_chat(schema: SetChatSchema, owner_id: int = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    for member in schema.members_id:
        result = await db.execute(select(UserModel).where(UserModel.id == member))
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {member} does not exist"
            )
    if not schema.name:
        result = await db.execute(select(UserModel.name).where(UserModel.id == owner_id))
        name = result.scalar_one_or_none()
        schema.name = name + " chat"
    new_chat = ChatModel(
        is_private=False,
        name=schema.name,
        status="opened"
    )
    db.add(new_chat)
    await db.flush()
    ownership = ChatMember(user_id=owner_id, chat_id=new_chat.id, role="owner")
    db.add(ownership)
    for member in schema.members_id:
        if member == owner_id:
            continue
        new_chat_member = ChatMember(user_id=member, chat_id=new_chat.id, role="member")
        db.add(new_chat_member)
    await db.commit()
    return {"ok": True, "chat_id": new_chat.id}


@chats_router.get("")
async def load_all_chats(user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatMember.chat_id, ChatModel.name, ChatModel.is_private)
        .join(ChatModel, ChatMember.chat_id == ChatModel.id)
        .where(ChatMember.user_id == user_id)
    )
    loaded_chats = [
        {"chat_id": row[0], "chat_name": row[1], "is_private": row[2]}
        for row in result.all()
    ]
    return {
        "ok": True,
        "chat_list": loaded_chats
    }


class PatchChatSchema(BaseModel):
    name: None | str = Field(min_length=1, max_length=64)


@chats_router.patch("/{chat_id}/settings")
async def change_chat_settings(schema: PatchChatSchema, user_id: int = Depends(get_current_user),
                               chat_id: int = Path(ge=1, description="id must be positive"),
                               db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChatModel).join(ChatMember, ChatMember.chat_id == ChatModel.id)
                              .where(ChatModel.id == chat_id, ChatMember.user_id == user_id,
                                     ChatMember.role != "member"))
    data = result.scalar_one_or_none()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied"
        )

    if schema.name:
        data.name = schema.name

    await db.commit()
    return {"ok": True}


class ChangeRole(BaseModel):
    is_admin: bool


@chats_router.patch("/{chat_id}/settings/roles/{user_id}")
async def change_role(schema: ChangeRole, owner_id: int = Depends(get_current_user), chat_id: int = Path(ge=1),
                      user_id: int = Path(ge=1),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChatMember)
                              .where(ChatMember.user_id == owner_id,
                                     ChatMember.chat_id == chat_id, ChatMember.role == "owner"))
    data = result.scalar_one_or_none()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied"
        )
    if user_id == owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сan not make the owner an admin"
        )
    result = await db.execute(select(ChatMember).where(ChatMember.user_id == user_id, ChatMember.chat_id == chat_id))
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not in chat"
        )
    await db.execute(update(ChatMember).where(ChatMember.user_id == user_id, ChatMember.chat_id == chat_id)
                     .values(role="admin" if schema.is_admin else "member"))
    await db.commit()
    return {"ok": True}


@chats_router.delete("/{chat_id}")
async def delete_chat(owner_id: int = Depends(get_current_user),
                      chat_id: int = Path(ge=1), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChatMember)
                              .where(ChatMember.user_id == owner_id,
                                     ChatMember.chat_id == chat_id, ChatMember.role == "owner"))
    data = result.scalar_one_or_none()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied"
        )
    await db.execute(delete(ChatModel).where(ChatModel.id == chat_id))
    await db.commit()
    return {"ok": True}
