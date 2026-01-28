
from fastapi import APIRouter, Depends, Path
from fastapi import HTTPException, status

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from auth.validation import get_current_user
from databases.databases import get_db, UserModel
users_router = APIRouter(prefix="/users")


class PatchUserProfileSchema(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    lastname: str = Field(min_length=1, max_length=32)
    bio: None | str = Field(max_length=256)


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
