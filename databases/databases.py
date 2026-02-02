import asyncio
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Index
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
engine = create_async_engine(url="sqlite+aiosqlite:///databases/messanger.db", echo=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


class Base(DeclarativeBase):
    pass


from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class AttachmentModel(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))
    filepath: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int]


class MessageModel(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column()
    sent_at: Mapped[datetime] = mapped_column(default=datetime.now(timezone.utc))


Index("idx_messages_chat_sent", MessageModel.chat_id, MessageModel.sent_at)

class ChatMember(Base):
    __tablename__ = "chat_members"
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    joined_at: Mapped[datetime] = mapped_column(default=datetime.now(timezone.utc))


class ChatModel(Base):
    __tablename__ = "chats"
    id: Mapped[int] = mapped_column(primary_key=True)
    is_private: Mapped[bool] = mapped_column(default=True)
    name: Mapped[str] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default="opened")


class UserFriends(Base):
    __tablename__ = "user_friends"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    friend_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now(timezone.utc))
    status: Mapped[str] = mapped_column(String(20), default="pending")


class UserModel(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(index=True)
    lastname: Mapped[str] = mapped_column(index=True)
    hash_pwd: Mapped[str]
    bio: Mapped[str]
    email: Mapped[str] = mapped_column(index=True)

