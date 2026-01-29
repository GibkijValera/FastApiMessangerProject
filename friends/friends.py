from fastapi import APIRouter, Depends, Path
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, or_
from auth.validation import get_current_user
from databases.databases import get_db, UserModel, UserFriends

friends_router = APIRouter(prefix="/friends", tags=["friends"])


@friends_router.post("/{user_id}/init")
async def init_friend(user_id: int = Path(ge=1), requester_id: int = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserModel).where(UserModel.id == user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    if requester_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add to friends yourself"
        )
    result = await db.execute(select(UserFriends)
    .where(or_(
        (UserFriends.user_id == user_id) & (UserFriends.friend_id == requester_id),
        (UserFriends.friend_id == user_id) & (UserFriends.user_id == requester_id)
    )
    )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already a friend, or request is being processed"
        )
    friendship = UserFriends(
        user_id=requester_id,
        friend_id=user_id,
        status="pending"
    )
    db.add(friendship)
    await db.commit()
    return {"ok": True}


@friends_router.post("/{user_id}/accept")
async def accept_friend(user_id: int = Path(ge=1), requester_id: int = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserModel).where(UserModel.id == user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    result = await db.execute(update(UserFriends).
                              where(UserFriends.user_id == user_id, UserFriends.friend_id == requester_id,
                                    UserFriends.status == "pending").values(status="accepted"))
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found"
        )
    await db.commit()
    return {"ok": True}


@friends_router.delete("/{user_id}")
async def delete_friend(user_id: int = Path(ge=1), requester_id: int = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    result = await db.execute(delete(UserFriends)
                              .where(or_(
        (UserFriends.user_id == user_id) & (UserFriends.friend_id == requester_id),
        (UserFriends.friend_id == user_id) & (UserFriends.user_id == requester_id)
    ) & (UserFriends.status == "accepted")
                                     )
                              )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Friend not found"
        )
    await db.commit()
    return {"ok": True}
