from fastapi import APIRouter, Depends, Path, Request
from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from databases.databases import get_db, UserModel, ChatModel, ChatMember, MessageModel
from sqlalchemy import select, update, delete, func, and_
from typing import List, Set
from auth.validation import get_current_user
from chats.messages.messages import messages_router
from core.core import templates
chats_router = APIRouter(prefix="/chats", tags=["chats"])
chats_router.include_router(messages_router)


class SetChatSchema(BaseModel):
    members_id: Set[int] = Field(min_length=2, max_length=15)
    name: None | str = Field(min_length=1, max_length=64)


@chats_router.get("")
async def chat_page(request: Request, user_id: int = Depends(get_current_user)):
    return templates.TemplateResponse("chats.html", {"request": request, "title": "Чаты"})


@chats_router.post("/create")
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


@chats_router.get("/load")
async def load_all_chats(user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    chats_query = (
        select(ChatMember.chat_id, ChatModel.name, ChatModel.is_private)
        .join(ChatModel, ChatMember.chat_id == ChatModel.id)
        .where(ChatMember.user_id == user_id)
    )
    chats_result = await db.execute(chats_query)
    chats_rows = chats_result.all()

    if not chats_rows:
        return {"ok": True, "chat_list": []}

    chat_ids = [row[0] for row in chats_rows]
    subquery = (
        select(
            MessageModel.chat_id,
            func.max(MessageModel.id).label('max_msg_id')
        )
        .where(MessageModel.chat_id.in_(chat_ids))
        .group_by(MessageModel.chat_id)
        .subquery()
    )

    last_messages_query = (
        select(MessageModel.chat_id, MessageModel.text, MessageModel.user_id, MessageModel.sent_at)
        .join(subquery, and_(
            MessageModel.chat_id == subquery.c.chat_id,
            MessageModel.id == subquery.c.max_msg_id
        ))
    )

    messages_result = await db.execute(last_messages_query)
    last_msg_map = {}
    for row in messages_result.all():
        last_msg_map[row.chat_id] = {
            "text": row.text,
            "user_id": row.user_id,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None
        }
    loaded_chats = []

    for row in chats_rows:
        chat_id, chat_name_db, is_private = row
        final_chat_name = chat_name_db
        if is_private:
            user_res = await db.execute(
                select(UserModel.name, UserModel.lastname)
                .join(ChatMember, ChatMember.user_id == UserModel.id)
                .where(ChatMember.chat_id == chat_id, UserModel.id != user_id)
            )
            user_row = user_res.first()
            if user_row:
                final_chat_name = f"{user_row.name} {user_row.lastname}"
        last_msg = last_msg_map.get(chat_id)

        loaded_chats.append({
            "chat_id": chat_id,
            "chat_name": final_chat_name,
            "is_private": is_private,
            "last_message": last_msg
        })

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
